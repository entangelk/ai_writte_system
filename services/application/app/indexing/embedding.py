"""Application-side embedding provider adapters.

`DeterministicFakeEmbeddingProvider` (in service.py) stays the unit-test /
no-infra provider. `RemoteEmbeddingProvider` calls a separate embedding service
container (real model, e.g. dragonkue/BGE-m3-ko) over HTTP so the deployed
vector backend produces real semantic vectors. `embed` stays synchronous (the
`EmbeddingProvider` Protocol) because an embedding call is short; a sync
httpx.Client avoids an async ripple through indexing and context search.
See docs/plans/04-real-vector-backend-decisions.md (B.1).
"""

from __future__ import annotations

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
