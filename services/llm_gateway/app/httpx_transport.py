"""Async JSON transport backed by httpx."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from .transport import JsonResponse, TransportFailure, TransportFailureKind


class HttpxJsonTransport:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 120.0,
        trust_env: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=trust_env,
            transport=transport,
        )

    async def __aenter__(self) -> HttpxJsonTransport:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> JsonResponse:
        try:
            response = await self._client.post(path, json=dict(payload))
        except httpx.TimeoutException as exc:
            raise TransportFailure(TransportFailureKind.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise TransportFailure(TransportFailureKind.CONNECTION) from exc

        try:
            body = response.json()
        except ValueError as exc:
            if 200 <= response.status_code < 300:
                raise TransportFailure(
                    TransportFailureKind.INVALID_RESPONSE
                ) from exc
            body = None

        return JsonResponse(
            status_code=response.status_code,
            body=body,
        )
