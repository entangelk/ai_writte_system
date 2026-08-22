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

    async def get_json(self, path: str) -> JsonResponse:
        """GET a decoded JSON response (llama.cpp ``/props`` 등 읽기 전용 조회)."""

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

    def __init__(
        self,
        outcomes: Iterable[TransportOutcome],
        *,
        get_outcomes: Iterable[TransportOutcome] | None = None,
    ) -> None:
        self._outcomes = deque(outcomes)
        # GET은 큐를 따로 쓴다. 같은 큐를 공유하면 창 조회 한 번이 생성 응답을 먹어
        # 테스트가 엉뚱한 곳에서 깨진다.
        self._get_outcomes = deque(get_outcomes or ())
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.get_requests: list[str] = []

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

    async def get_json(self, path: str) -> JsonResponse:
        self.get_requests.append(path)
        if not self._get_outcomes:
            raise FakeTransportExhausted("fake transport has no queued GET outcome")

        outcome = self._get_outcomes.popleft()
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
    if status_code in (401, 403):
        return ProviderError(
            code=ProviderErrorCode.KEY_REJECTED,
            message="provider rejected the api key",
            retryable=False,
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
