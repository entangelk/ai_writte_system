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

import os
from typing import Any

import httpx


#: `EMBEDDING_API_FORMAT` 의 값. 기본은 자체 형식이라 기존 배포가 env 를 안 건드려도
#: 그대로 돈다. **형식은 키 유무로 추론하지 않는다** — 추론하면 키를 지운 순간 형식이
#: 조용히 바뀌고, 그 실패는 "왜 갑자기 404 인가" 로 나타난다.
NATIVE_FORMAT = "native"
OPENAI_FORMAT = "openai"


class EmbeddingProviderError(RuntimeError):
    """Raised when the embedding service is unreachable or returns a bad body."""


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
            raise EmbeddingProviderError("embedding request timed out") from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError("embedding service is unavailable") from exc

        if response.status_code >= 400:
            raise EmbeddingProviderError(
                f"embedding service returned status {response.status_code}"
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
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._expected_dimensions = expected_dimensions
        self._transport = transport

    def embed(self, text: str) -> tuple[float, ...]:
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
                    "/v1/embeddings",
                    json={"input": text, "model": self._model},
                )
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError("embedding request timed out") from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError("embedding service is unavailable") from exc

        if response.status_code >= 400:
            # The body can carry the vendor's reason, but it can also carry the
            # prompt back. Only the status goes into the message — the same rule
            # the rest of this file follows.
            raise EmbeddingProviderError(
                f"embedding service returned status {response.status_code}"
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


def _strip_version_suffix(base_url: str) -> str:
    """Drop one trailing `/v1` so a pasted vendor base URL does not double it.

    Vendor docs print `https://api.openai.com/v1`, but this repo's convention —
    set by the LLM gateway — is that the configured address is the host root and
    the client owns the path. Both spellings therefore have to work; the
    alternative is a 404 whose cause is invisible in the address someone copied
    from the docs.
    """

    trimmed = base_url.rstrip("/")
    return trimmed[: -len("/v1")] if trimmed.endswith("/v1") else trimmed


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
    return OpenAIEmbeddingProvider(
        base_url=_strip_version_suffix(resolved),
        model=model,
        api_key=os.environ.get("EMBEDDING_API_KEY") or None,
        timeout_seconds=timeout_seconds,
        trust_env=trust_env,
        expected_dimensions=expected_dimensions,
    )
