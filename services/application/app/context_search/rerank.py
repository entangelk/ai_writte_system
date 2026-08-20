"""뉴럴 리랭커 seam 과 외부 API 어댑터 (D5 · 리랭커 슬라이스 결정 2=A · 3=A).

**이 파일이 하는 일은 "순서를 다시 매기는 것" 하나다.** 무엇을 검색할지도, 몇 개를
가져올지도 정하지 않는다 — 그것은 이미 `retrieve()` seam 뒤에서 끝나 있고, 여기서는
그 결과를 **질의-문서 쌍으로 다시 읽어** 재정렬한다. 지금 "리랭킹" 이라 불리던 RRF
융합은 **두 순위의 합의**를 보는 것이지 쌍을 다시 읽는 것이 아니다.

**★ 로컬 기본은 no-op 이다**(결정 2=A). 주소가 없으면 `build_rerank_provider_from_env`
가 `None` 을 돌려주고 조립이 감싸지 않는다 — **끄기가 조립에서 끝난다**(결정 3=A 를
고른 이유 중 하나). 그래서 이 파일이 있다는 사실만으로는 검색이 달라지지 않는다.

**★ 실패는 열려 있다(fail-open) — 이 단계 전체가 그렇다.** 리랭커가 죽든, 응답이
계약을 벗어나든, **텍스트 투영이 던지든** 원래 순서가 그대로 나간다. 재정렬은 품질
향상이지 정확성 요건이 아니므로, 그것 때문에 검색이 죽으면 손해가 이득보다 크다.
결정 4-① 이 잠그는 세 축 중 하나가 이것이다.

**범위가 "프로바이더 실패" 가 아니라 "단계 전체" 인 것은 독립 검증이 잡아 준 것이다**
(2026-08-20 조건 C1). 종전에는 `RerankProviderError` 만 잡아서 **투영이 던지면 검색
경로가 죽었고**, 그 호출은 이 슬라이스가 새로 넣은 것이었다. **다만 조용히 삼키지는
않는다** — `logging.WARNING` 으로 남긴다.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Protocol, Sequence, TypeVar

import httpx

_log = logging.getLogger(__name__)

#: 재정렬할 것이 없으면 부르지 않는다 — 0·1개는 순서가 하나뿐이다.
_MINIMUM_TO_REORDER = 2


class RerankProviderError(RuntimeError):
    """리랭커가 도달 불가이거나 응답이 계약을 벗어났을 때."""


class RerankProvider(Protocol):
    def rerank(self, *, query: str, documents: Sequence[str]) -> tuple[int, ...]:
        """`documents` 의 인덱스를 **좋은 것부터** 나열해 돌려준다.

        점수가 아니라 순서를 돌려주는 이유: 이 seam 의 유일한 소비자가 재정렬이고,
        점수를 흘리면 **그 점수로 자르는 두 번째 정책**(임계값·top-k)이 곧 붙는다.
        top-k 는 브리프가 **지연 실측 뒤로** 미룬 결정이라, 지금 그 문을 열지 않는다.
        """
        ...


T = TypeVar("T")


class RerankingRetriever:
    """`retrieve()` seam 을 감싸 결과 순서만 바꾸는 데코레이터 (결정 3=A).

    **도메인 코드는 0줄 바뀐다.** 정본 memory 와 검토 대기 candidate 두 융합 자리는
    seam 이 **완전히 같아서**(`retrieve(*, project_id, query, limit)`) 한 데코레이터가
    둘 다 덮는다 — 그것이 결정 3 에서 A 를 고른 첫째 이유다. 항목 타입이 서로 달라
    텍스트 투영만 `text_of` 로 주입받는다(memory 는 `derive_memory_index_text`,
    candidate 는 `candidate_index_text` — **색인이 쓴 것과 같은 투영**이라야 리랭커가
    색인이 본 것과 같은 글을 읽는다).

    **Hybrid 클래스 안에 넣지 않은 이유**(선택지 B): 두 클래스에 같은 코드가 복제되고,
    **vector-only·lexical-only 구성에서는 리랭킹이 안 걸린다.** 데코레이터는 구성과
    무관하게 seam 하나만 본다.
    """

    def __init__(
        self,
        *,
        inner: Any,
        provider: RerankProvider,
        text_of: Callable[[T], str],
    ) -> None:
        self._inner = inner
        self._provider = provider
        self._text_of = text_of

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[Any, ...]:
        items = self._inner.retrieve(
            project_id=project_id, query=query, limit=limit
        )
        if len(items) < _MINIMUM_TO_REORDER:
            return items
        try:
            # ★ 투영까지 이 안에 있다. 2026-08-20 독립 검증(조건 C1)이 지적한
            # 자리다 — 종전에는 `RerankProviderError` 만 잡아서 **`text_of` 가 던지면
            # 검색 경로가 죽었다.** 투영은 이 슬라이스가 검색 경로에 **새로 넣은
            # 호출**이므로, 그것 때문에 죽는 길도 이 슬라이스가 만든 것이다.
            documents = [self._text_of(item) for item in items]
            order = self._provider.rerank(query=query, documents=documents)
            if not _is_permutation(order, len(items)):
                # 순열이 아니면 항목이 **빠지거나 겹친다.** 부분 응답(`top_n`)을
                # 그대로 받으면 검색 결과가 조용히 줄어드는데, 그것은 재정렬이 아니라
                # 필터링이고 이 seam 이 약속한 일이 아니다.
                raise RerankProviderError(
                    f"rerank order is not a permutation of {len(items)} documents"
                )
            reordered = tuple(items[index] for index in order)
        except Exception:  # noqa: BLE001 — 결정 4-① 의 fail-open 경계
            # 좁히면 이 **선택적 개선 단계**의 예외가 검색을 죽인다. 재정렬은 품질
            # 향상이지 정확성 요건이 아니므로, 그 때문에 검색이 죽으면 손해가 이득보다
            # 크다. 같은 형태의 선례: activity/log.py 의 A4=A 격리 경계.
            #
            # **조용히 삼키지는 않는다** — 로그가 없으면 리랭킹이 영원히 no-op 인 채로
            # 아무도 모른다(그것이 이 저장소가 오늘 네 번 만난 실패 모양이다).
            _log.warning("reranking failed; falling back to fusion order",
                         exc_info=True)
            return items
        return reordered


def _is_permutation(order: Sequence[int], size: int) -> bool:
    return len(order) == size and sorted(order) == list(range(size))


class HttpRerankProvider:
    """외부 리랭커 API 어댑터 — `POST /v1/rerank` (D2=A 의 generic).

    **★ "OpenAI 호환" 이라 부르지 않는다 — OpenAI 에는 rerank 엔드포인트가 없다.**
    D2=A 가 뜻한 것은 *"벤더 전용이 아니라 여럿이 공유하는 형식"* 이고, 리랭킹에서 그
    자리를 차지한 것은 Cohere 가 낸 형태다(Jina·Voyage·TEI·infinity 가 같은 모양을
    말한다). 그래서 generic 은 이쪽이고, 벤더 전용 어댑터는 그 뒤에 additive 다.

        요청  {"model": …, "query": …, "documents": [str, …]}
        응답  {"results": [{"index": int, "relevance_score": float}, …]}

    `base_url` 은 **호스트 루트**이고 `/v1/rerank` 는 이 클래스가 소유한다 — 임베딩
    어댑터·LLM 게이트웨이와 같은 관례다.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        trust_env: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._transport = transport

    def rerank(self, *, query: str, documents: Sequence[str]) -> tuple[int, ...]:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=self._trust_env,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = client.post(
                    "/v1/rerank",
                    json={
                        "model": self._model,
                        "query": query,
                        "documents": list(documents),
                    },
                )
        except httpx.TimeoutException as exc:
            raise RerankProviderError("rerank request timed out") from exc
        except httpx.RequestError as exc:
            raise RerankProviderError("rerank service is unavailable") from exc

        if response.status_code >= 400:
            # 본문에는 우리가 보낸 문서가 되돌아올 수 있다 — 상태만 싣는다.
            raise RerankProviderError(
                f"rerank service returned status {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RerankProviderError("rerank response is not JSON") from exc
        return _order_from_body(body, len(documents))


def _order_from_body(body: Any, size: int) -> tuple[int, ...]:
    if not isinstance(body, dict):
        raise RerankProviderError("rerank response must be an object")
    results = body.get("results")
    if not isinstance(results, list):
        raise RerankProviderError("rerank response must include a 'results' array")
    ranked = []
    for entry in results:
        if not isinstance(entry, dict):
            raise RerankProviderError("rerank 'results' must hold objects")
        index = entry.get("index")
        score = entry.get("relevance_score")
        # bool 은 int 의 하위형이라 걸러내지 않으면 인덱스 0/1 로 들어온다.
        if isinstance(index, bool) or not isinstance(index, int):
            raise RerankProviderError("rerank result index must be an integer")
        if not 0 <= index < size:
            raise RerankProviderError(
                f"rerank result index {index} is outside the request"
            )
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RerankProviderError("rerank relevance_score must be a number")
        ranked.append((float(score), index))
    # 서버가 이미 정렬해 주는 것이 보통이지만 계약은 그것을 약속하지 않는다.
    #
    # 동률에서는 **응답에 담긴 순서**를 유지한다(안정 정렬 + 인덱스 tie-break 없음).
    # 요청 순서가 아니다 — 2026-08-20 검증 H2 의 정정이다. 응답이 요청 순서로 올
    # 때만 둘이 같고, 계약은 그것도 약속하지 않는다. 중요한 것은 **같은 응답이
    # 언제나 같은 순서를 낸다**는 것이며, 그것이 여기서 잠그는 성질이다.
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(index for _score, index in ranked)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_rerank_provider_from_env() -> RerankProvider | None:
    """단일 조립 지점: env -> provider, 또는 **`None`(= 리랭킹 없음)**.

    `None` 이 정상값이라는 것이 이 슬라이스의 핵심이다 — 주소가 없으면 조립이
    데코레이터를 씌우지 않고, 검색은 **지금과 완전히 똑같이** 동작한다(결정 2=A).
    임베딩 헬퍼가 fake 로 내려가는 것과 다르다: 리랭킹에는 "가짜 재정렬" 이라는
    쓸모 있는 대체물이 없고, 무작위로 섞는 것은 no-op 보다 나쁘다.
    """

    base_url = os.environ.get("RERANK_API_URL")
    if not base_url:
        return None
    model = os.environ.get("RERANK_API_MODEL")
    if not model:
        raise ValueError("RERANK_API_MODEL is required when RERANK_API_URL is set")
    return HttpRerankProvider(
        base_url=_strip_version_suffix(base_url),
        model=model,
        api_key=os.environ.get("RERANK_API_KEY") or None,
        timeout_seconds=_env_float("RERANK_TIMEOUT_SECONDS", 10.0),
        trust_env=_env_bool("RERANK_TRUST_ENV", False),
    )


def _strip_version_suffix(base_url: str) -> str:
    """벤더 문서가 인쇄하는 접미 `/v1` 하나를 벗긴다(임베딩 어댑터와 같은 이유)."""

    trimmed = base_url.rstrip("/")
    return trimmed[: -len("/v1")] if trimmed.endswith("/v1") else trimmed
