"""Application-side embedding provider adapters.

`DeterministicFakeEmbeddingProvider` (in service.py) stays the unit-test /
no-infra provider. `RemoteEmbeddingProvider` calls a separate embedding service
container (real model, e.g. dragonkue/BGE-m3-ko) over HTTP so the deployed
vector backend produces real semantic vectors. `embed` stays synchronous (the
`EmbeddingProvider` Protocol) because an embedding call is short; a sync
httpx.Client avoids an async ripple through indexing and context search.
`build_embedding_provider_from_env` is the **only** place that turns env into a
provider. Six assembly sites used to each read the same four variables and call
the constructor themselves, and one of them
(`scripts/calibrate_character_identity_threshold.py`) sat broken for over a month
because nothing ran it — that is the defect decision 4=A closes structurally, not
by remembering to look. `tests/test_embedding_assembly.py` asserts no site calls
a provider constructor directly.

See docs/plans/04-real-vector-backend-decisions.md (B.1) and
docs/plans/embedding-adapter-slice-decisions.md (decisions 1=A, 4=A).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from services.application.app.key_rotation import (
    KEY_REJECTED_COOLDOWN_SECONDS,
    RATE_LIMIT_COOLDOWN_SECONDS,
    SyncSlidingWindowLimiter,
    split_env_list,
)


_log = logging.getLogger(__name__)


#: `EMBEDDING_API_FORMAT` 의 값. 기본은 자체 형식이라 기존 배포가 env 를 안 건드려도
#: 그대로 돈다. **형식은 키 유무로 추론하지 않는다** — 추론하면 키를 지운 순간 형식이
#: 조용히 바뀌고, 그 실패는 "왜 갑자기 404 인가" 로 나타난다.
NATIVE_FORMAT = "native"
OPENAI_FORMAT = "openai"


class EmbeddingProviderError(RuntimeError):
    """Raised when the embedding service is unreachable or returns a bad body.

    `status_code`/`network` 는 키 회전 계층이 **이 오류를 키를 바꿔 재시도할 만한가**를
    판단하는 근거다(오너 2026-08-22). 메시지 문자열은 그대로 — 기존 진단·테스트 호환.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        network: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.network = network

    @property
    def key_rotatable(self) -> bool:
        """키를 바꾸면 고쳐질 수 있는 실패인가 — 네트워크·401/403/408/429·5xx.

        차원 가드·본문 계약 위반은 `False`다 — 어느 키로 보내도 같은 결과고,
        회전은 진단을 늦출 뿐이다(over-strict 가드가 잠근다).
        """
        if self.network:
            return True
        if self.status_code in (401, 403, 408, 429):
            return True
        return self.status_code is not None and self.status_code >= 500


class RemoteEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        trust_env: bool = False,
        expected_dimensions: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._expected_dimensions = expected_dimensions
        self._transport = transport

    def embed(self, text: str) -> tuple[float, ...]:
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=self._trust_env,
                transport=self._transport,
            ) as client:
                response = client.post("/embed", json={"text": text})
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError(
                "embedding request timed out", network=True
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError(
                "embedding service is unavailable", network=True
            ) from exc

        if response.status_code >= 400:
            raise EmbeddingProviderError(
                f"embedding service returned status {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("embedding response is not JSON") from exc
        return self._vector_from_body(body)

    def _vector_from_body(self, body: Any) -> tuple[float, ...]:
        if not isinstance(body, dict):
            raise EmbeddingProviderError("embedding response must be an object")
        embedding = body.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise EmbeddingProviderError(
                "embedding response must include a non-empty 'embedding' array"
            )
        return _vector_from_numbers(embedding, self._expected_dimensions)


def _vector_from_numbers(
    values: list[Any], expected_dimensions: int | None
) -> tuple[float, ...]:
    """Shared by both providers: coerce, reject non-numbers, check the dimension.

    The wire *shape* differs between our own service and the OpenAI format, but
    what counts as a valid vector does not — and the dimension guard is the one
    thing that must not drift between them (docs/plans/embedding-adapter-slice-
    decisions.md decision 3=A: the guard is the whole mechanism there).
    """

    vector = []
    for value in values:
        # bool is an int subclass; reject it so a malformed body is not
        # silently coerced to 0.0/1.0.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EmbeddingProviderError("embedding values must be numbers")
        vector.append(float(value))
    if expected_dimensions is not None and len(vector) != expected_dimensions:
        raise EmbeddingProviderError(
            f"embedding has {len(vector)} dimensions, "
            f"expected {expected_dimensions}"
        )
    return tuple(vector)


class OpenAIEmbeddingProvider:
    """OpenAI-format embedding API behind the same single-text `embed` seam.

    Four things differ from our own service — path, request key, response shape
    and auth — which is why this is a second class rather than a `wire_format`
    branch inside the first one (decision 1=A).

    **`base_url` is the host root, not the `/v1` prefix.** `POST /v1/embeddings`
    is appended here, matching how the LLM gateway holds `LLAMA_BASE_URL` and
    posts `/v1/chat/completions`. Vendor docs usually print the base *with* `/v1`,
    so a pasted address would double the prefix; the assembly helper strips one
    trailing `/v1` for that reason.

    Still one text per call (decision 2=A). The format accepts an array and the
    temptation to batch here is exactly what that decision pre-empted: the seam
    is `embed(text) -> vector` in three Protocols, and widening it is additive
    later, once a reindex measurement says it hurts.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        trust_env: bool = False,
        expected_dimensions: int | None = None,
        embeddings_path: str = "/v1/embeddings",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._expected_dimensions = expected_dimensions
        # `embeddings_path` 는 기본(OpenAI·OpenRouter 의 /v1/embeddings)에서 벗어나는
        # 벤더를 위한 자리다 — 구글의 OpenAI 호환 루트는 /v1beta/openai 라 /v1 이 없다.
        # 조립(build_embedding_provider_from_env)이 계산해 넣는다.
        self._embeddings_path = embeddings_path
        self._transport = transport

    def embed(self, text: str) -> tuple[float, ...]:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body: dict[str, object] = {"input": text, "model": self._model}
        if self._expected_dimensions is not None:
            # 안 보내면 벤더 기본값으로 나온다(구글 gemini-embedding-2 는 3072). 기대
            # 차원을 요청에 실어 고정한다 — 차원 가드와 요청이 같은 값을 말한다.
            # 이 파라미터가 없는 벤더는 400 으로 크게 실패한다(조용한 불일치보다 낫다).
            body["dimensions"] = self._expected_dimensions
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=self._trust_env,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = client.post(
                    self._embeddings_path,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError(
                "embedding request timed out", network=True
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError(
                "embedding service is unavailable", network=True
            ) from exc

        if response.status_code >= 400:
            # The body can carry the vendor's reason, but it can also carry the
            # prompt back. Only the status goes into the message — the same rule
            # the rest of this file follows.
            raise EmbeddingProviderError(
                f"embedding service returned status {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("embedding response is not JSON") from exc
        return self._vector_from_body(body)

    def _vector_from_body(self, body: Any) -> tuple[float, ...]:
        if not isinstance(body, dict):
            raise EmbeddingProviderError("embedding response must be an object")
        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise EmbeddingProviderError(
                "embedding response must include a non-empty 'data' array"
            )
        first = data[0]
        if not isinstance(first, dict):
            raise EmbeddingProviderError("embedding response 'data' must hold objects")
        embedding = first.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise EmbeddingProviderError(
                "embedding response must include a non-empty 'embedding' array"
            )
        return _vector_from_numbers(embedding, self._expected_dimensions)


class KeyRotatingEmbeddingProvider:
    """키 회전(오너 2026-08-22) — `embed` seam 을 N개 provider 앞에서 라운드로빈으로.

    게이트웨이 형제(`llm_gateway/app/fallback.py`)와 같은 정책: 시작 키 라운드로빈
    배분(한 키로 집중되지 않게 — 오너 정정 2026-08-22), 키당 RPM 슬라이딩 60초 창,
    401/403 장기(600s)·429 단기(60s) 쿨다운 — 네트워크·408·5xx는 쿨다운 없이 다음
    조합(2026-08-23 B1 정렬) — 소진 fail-fast.
    **모델 폴백은 없다** — 임베딩 모델을 바꾸면 차원이 변하고 그 길은 재색인 절차
    (plans/embedding-adapter-slice-decisions.md 결정 3=A)의 영역이다.

    `key_rotatable` 이 아닌 오류(차원 가드·400류)는 즉시 재발생한다 — 어느 키로
    보내도 같은 결과고, 회전은 진단을 늦출 뿐이다.
    """

    def __init__(
        self,
        *,
        providers: list[Any],
        limiter: SyncSlidingWindowLimiter,
        budget_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self._providers = providers
        self._limiter = limiter
        self._budget_seconds = budget_seconds
        self._clock = clock
        self._next_start = 0
        # sync endpoint 는 스레드풀에서 돌아 동시 embed() 가 실재한다 — 카운터도 잠근다.
        self._start_lock = threading.Lock()

    def embed(self, text: str) -> tuple[float, ...]:
        with self._start_lock:
            start = self._next_start
            self._next_start = (self._next_start + 1) % len(self._providers)
        count = len(self._providers)
        deadline = self._clock() + self._budget_seconds
        last_error: EmbeddingProviderError | None = None
        attempted = False
        for offset in range(count):
            slot = (start + offset) % count
            if not self._limiter.try_acquire(slot):
                continue
            if attempted and self._clock() >= deadline:
                # 예산 소진 — 시작하지 않는 시도. 첫 시도는 항상 돈다(예산이 0이어도).
                break
            attempted = True
            try:
                return self._providers[slot].embed(text)
            except EmbeddingProviderError as exc:
                if not exc.key_rotatable:
                    raise
                last_error = exc
                # 키 인덱스만 남긴다 — 키 값은 로그에 오지 않는다(게이트웨이와 같은 규칙).
                _log.warning(
                    "embedding key rotation failed: key_index=%d status=%s",
                    slot,
                    exc.status_code,
                )
                # 쿨다운은 상태 코드가 말하는 "키의 문제"에만 건다(브리프 §1,
                # 2026-08-23 검증 B1 — 오너 ⓑ 코드 정렬). 401/403=키 치명(장기),
                # 429=한도(단기), 네트워크·408·5xx는 키가 아니라 상태의 문제라
                # 쿨다운 없이 다음 조합이 즉시 시도된다(게이트웨이 형제와 같은 정책).
                if exc.status_code in (401, 403):
                    self._limiter.cool(slot, KEY_REJECTED_COOLDOWN_SECONDS)
                elif exc.status_code == 429:
                    self._limiter.cool(slot, RATE_LIMIT_COOLDOWN_SECONDS)
        if last_error is not None:
            # 시도는 했으나 전부 실패 — 마지막 오류를 그대로 돌려 보내면 인덱스 재시도
            # backoff(service.py 의 (60, 300)s)가 원인별로 판단할 수 있다.
            raise last_error
        raise EmbeddingProviderError(
            "all embedding keys are rate-limited or cooling down",
            status_code=429,
        )


def _embeddings_endpoint(raw: str) -> tuple[str, str]:
    """`EMBEDDING_SERVICE_URL` → (base_url, embeddings_path). **붙여넣은 벤더 주소가
    그대로 동작해야 한다** — 게이트웨이의 `_chat_endpoint`(llm_gateway/main.py)와
    같은 관례다:

    - `…/embeddings` 으로 끝나면 → 전체 엔드포인트로 보고 그 결론을 유지한다.
    - `/v1beta/openai` 로 끝나면(구글 Gemini API 의 OpenAI 호환 루트 — **접미 `/v1`
      이 없다**) → `/embeddings` 를 붙인다.
    - 그 외(OpenAI·OpenRouter) → 접미 `/v1` 하나를 벗기고 `/v1/embeddings` 를 붙인다.

    ★ 구글은 **호스트 루트만 붙여넣으면 동작하지 않는다**(`/v1/embeddings 경로가
    없다) — 문서가 인쇄하는 `…/v1beta/openai` 까지 넣는다(실측 2026-08-22).
    """
    trimmed = raw.rstrip("/")
    if trimmed.endswith("/embeddings"):
        return trimmed[: -len("/embeddings")], "/embeddings"
    if trimmed.endswith("/v1beta/openai"):
        return trimmed, "/embeddings"
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed, "/v1/embeddings"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_embedding_provider_from_env(
    *, base_url: str | None = None, required: bool = False
) -> Any:
    """The single assembly point: env (plus an optional explicit address) -> provider.

    `base_url` overrides `EMBEDDING_SERVICE_URL` — the calibration script takes
    the address as a CLI argument, and forcing it through the environment just to
    reach this helper would be worse than passing it.

    With no address at all: `required=True` raises, otherwise the deterministic
    fake comes back (the convention `create_app` already used — an unset service
    URL means "no infrastructure here", not "misconfigured").

    Deliberately does **only** env -> provider. Reindex policy, dimension
    decisions and batching do not belong here; putting them in would make this a
    second assembly point, which is the thing it exists to prevent
    (docs/plans/embedding-adapter-slice-decisions.md decision 4=A).
    """

    resolved = base_url or os.environ.get("EMBEDDING_SERVICE_URL")
    if not resolved:
        if required:
            raise ValueError(
                "EMBEDDING_SERVICE_URL is required for real embedding"
            )
        # Imported here rather than at module scope: the fake lives in
        # indexing.service, which pulls in core_sot, and the scripts that call
        # this helper do not all need that chain.
        from services.application.app.indexing.service import (
            DeterministicFakeEmbeddingProvider,
        )

        return DeterministicFakeEmbeddingProvider()

    timeout_seconds = _env_float("EMBEDDING_TIMEOUT_SECONDS", 30.0)
    trust_env = _env_bool("EMBEDDING_TRUST_ENV", False)
    expected_dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))

    wire_format = os.environ.get("EMBEDDING_API_FORMAT", NATIVE_FORMAT).strip().lower()
    # 키 리스트(오너 2026-08-22). native 형식은 키를 안 쓰므로 리스트가 명시된 것은
    # 설정 실수다 — 조용히 무시하면 "넣었는데 왜 회전하지 않나"가 된다.
    keys: list[str | None] = split_env_list(os.environ.get("EMBEDDING_API_KEYS"))
    if keys and wire_format == NATIVE_FORMAT:
        raise ValueError(
            "EMBEDDING_API_KEYS requires "
            f"EMBEDDING_API_FORMAT={OPENAI_FORMAT} "
            "(the native service takes no key)"
        )
    if wire_format == NATIVE_FORMAT:
        return RemoteEmbeddingProvider(
            base_url=resolved,
            timeout_seconds=timeout_seconds,
            trust_env=trust_env,
            expected_dimensions=expected_dimensions,
        )
    if wire_format != OPENAI_FORMAT:
        raise ValueError(
            f"EMBEDDING_API_FORMAT must be {NATIVE_FORMAT!r} or {OPENAI_FORMAT!r}, "
            f"got {wire_format!r}"
        )

    model = os.environ.get("EMBEDDING_API_MODEL")
    if not model:
        # The OpenAI format sends the model per request, so there is no default
        # to fall back on. Failing here beats sending `"model": null` and reading
        # a vendor error that says nothing about our configuration.
        raise ValueError(
            f"EMBEDDING_API_MODEL is required when "
            f"EMBEDDING_API_FORMAT={OPENAI_FORMAT}"
        )
    if not keys:
        # 리스트가 비면 오늘의 단일 키 변수로 내려간다(기존 배포 무변).
        keys = [os.environ.get("EMBEDDING_API_KEY") or None]

    base_url, embeddings_path = _embeddings_endpoint(resolved)
    providers = [
        OpenAIEmbeddingProvider(
            base_url=base_url,
            model=model,
            api_key=key,
            timeout_seconds=timeout_seconds,
            trust_env=trust_env,
            expected_dimensions=expected_dimensions,
            embeddings_path=embeddings_path,
        )
        for key in keys
    ]
    if len(providers) <= 1:
        return providers[0]

    rpm = _env_float("EMBEDDING_KEY_RPM", 30.0)
    if rpm < 1:
        # 0을 명시한 것은 설정 실수 — 모든 키를 조용히 막는 대신 기동에서 거부한다.
        raise ValueError("EMBEDDING_KEY_RPM must be at least 1")
    return KeyRotatingEmbeddingProvider(
        providers=providers,
        limiter=SyncSlidingWindowLimiter(slots=len(providers), limit=int(rpm)),
        # 첫 시도는 항상 돌고 그 뒤의 시도는 이 예산 안에서만 — N키 × 타임아웃의 지연
        # 누적을 막는다(재색인처럼 길게 도는 호출에서 특히 문제가 된다).
        budget_seconds=timeout_seconds,
    )
