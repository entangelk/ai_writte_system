"""게이트웨이가 아는 모델 사실(창·토큰 계수)을 앱이 캐시해서 쓰는 얇은 클라이언트.

**왜 앱이 직접 알면 안 되는가**(오너 결정 2026-07-31, R-a = (ii)+(iii)): 창은 배포마다
다르고(알파 8192/16384/32768 · 베타 외부 서버 16384) 토큰 계수는 모델마다 다르다. 앱이
`LLAMA_CTX_SIZE`를 자기 env로 복제하면 **머신을 옮기는 순간 두 값이 갈린다** — 이 프로젝트가
반복해서 데인 실패 방식이고, 그래서 R-a의 상수안(i)이 탈락했다.

**모르는 것은 모른다고 말한다.** 조회가 실패하면 `None`이고, 호출자는 그때 자기 추정이나
요청값으로 떨어진다. 관측·최적화가 자기 실패로 기능을 깨뜨리지 않는다는 것은 이 트랙에서
이미 한 번 값을 치르고 배운 계약이다(K-3 가드의 "판정할 수 없으면 통과시킨다").
"""

from __future__ import annotations

import asyncio

import httpx


class ModelCapabilities:
    """창과 토큰 계수를 **프로세스 수명 동안 한 번씩만** 묻는다.

    창은 서버 기동 설정이고, 계수를 묻는 대상은 **고정 문자열**(report system 템플릿)이므로
    둘 다 요청마다 다시 물을 이유가 없다. 캐시가 없으면 요청 경로에 왕복이 하나 붙는다.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        trust_env: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._transport = transport
        self._window: int | None = None
        self._window_probed = False
        self._token_counts: dict[str, int] = {}
        # 동시 요청이 같은 값을 여러 번 묻지 않게 한다(첫 요청 폭주 시 왕복 N배 방지).
        self._lock = asyncio.Lock()

    async def context_window(self) -> int | None:
        if self._window_probed:
            return self._window
        async with self._lock:
            if self._window_probed:
                return self._window
            self._window_probed = True
            body = await self._get("/v1/capabilities")
            if body is not None:
                window = body.get("context_window")
                if isinstance(window, int) and not isinstance(window, bool) and window > 0:
                    self._window = window
        return self._window

    async def count_tokens(self, text: str) -> int | None:
        """`text`의 실제 토큰 수. **고정 문자열에만 쓴다** — 캐시 키가 본문이기 때문이다."""
        cached = self._token_counts.get(text)
        if cached is not None:
            return cached
        body = await self._post("/v1/tokenize", {"text": text})
        if body is None:
            return None
        tokens = body.get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            return None
        self._token_counts[text] = tokens
        return tokens

    async def _get(self, path: str) -> dict | None:
        return await self._request(lambda client: client.get(path))

    async def _post(self, path: str, payload: dict) -> dict | None:
        return await self._request(lambda client: client.post(path, json=payload))

    async def _request(self, send) -> dict | None:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=self._trust_env,
                transport=self._transport,
            ) as client:
                response = await send(client)
            if not 200 <= response.status_code < 300:
                return None
            body = response.json()
        except Exception:  # noqa: BLE001 — 조회 실패가 요청을 깨뜨리지 않는 경계
            return None
        return body if isinstance(body, dict) else None
