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
        vector = []
        for value in embedding:
            # bool is an int subclass; reject it so a malformed body is not
            # silently coerced to 0.0/1.0.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingProviderError("embedding values must be numbers")
            vector.append(float(value))
        if (
            self._expected_dimensions is not None
            and len(vector) != self._expected_dimensions
        ):
            raise EmbeddingProviderError(
                f"embedding has {len(vector)} dimensions, "
                f"expected {self._expected_dimensions}"
            )
        return tuple(vector)


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

    return RemoteEmbeddingProvider(
        base_url=resolved,
        timeout_seconds=_env_float("EMBEDDING_TIMEOUT_SECONDS", 30.0),
        trust_env=_env_bool("EMBEDDING_TRUST_ENV", False),
        expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
    )
