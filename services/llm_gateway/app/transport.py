"""Map transport failures to the stable provider error contract."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from .errors import ProviderError, ProviderErrorCode


class TransportFailureKind(StrEnum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status_code: int
    body: Any


@runtime_checkable
class JsonTransport(Protocol):
    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> JsonResponse:
        """POST a JSON object and return a decoded JSON response."""

        ...


class TransportFailure(RuntimeError):
    def __init__(self, kind: TransportFailureKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


class FakeTransportExhausted(RuntimeError):
    """Raised when a test calls the fake more times than configured."""


TransportOutcome = JsonResponse | TransportFailure


class FakeJsonTransport:
    """Return queued JSON responses or transport failures in FIFO order."""

    def __init__(self, outcomes: Iterable[TransportOutcome]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> JsonResponse:
        self.requests.append((path, dict(payload)))
        if not self._outcomes:
            raise FakeTransportExhausted("fake transport has no queued outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, TransportFailure):
            raise outcome
        return outcome


def error_from_transport_failure(
    kind: TransportFailureKind,
    *,
    provider: str | None = None,
) -> ProviderError:
    if kind is TransportFailureKind.TIMEOUT:
        return ProviderError(
            code=ProviderErrorCode.TIMEOUT,
            message="provider request timed out",
            retryable=True,
            provider=provider,
        )
    if kind is TransportFailureKind.CONNECTION:
        return ProviderError(
            code=ProviderErrorCode.UNAVAILABLE,
            message="provider is unavailable",
            retryable=True,
            provider=provider,
        )
    return ProviderError(
        code=ProviderErrorCode.INVALID_RESPONSE,
        message="provider returned an invalid response",
        retryable=False,
        provider=provider,
    )


def error_from_http_status(
    status_code: int,
    *,
    provider: str | None = None,
) -> ProviderError:
    if status_code < 400:
        raise ValueError(
            f"HTTP status {status_code} does not represent a provider error"
        )
    if status_code in (408, 504):
        return ProviderError(
            code=ProviderErrorCode.TIMEOUT,
            message="provider request timed out",
            retryable=True,
            provider=provider,
        )
    if status_code == 429:
        return ProviderError(
            code=ProviderErrorCode.OVERLOADED,
            message="provider is overloaded",
            retryable=True,
            provider=provider,
        )
    if status_code < 500:
        return ProviderError(
            code=ProviderErrorCode.REQUEST_REJECTED,
            message="provider rejected the request",
            retryable=False,
            provider=provider,
        )
    return ProviderError(
        code=ProviderErrorCode.UNAVAILABLE,
        message="provider is unavailable",
        retryable=True,
        provider=provider,
    )
