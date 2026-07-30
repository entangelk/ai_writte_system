"""Stable provider error contract shared by gateway callers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProviderErrorCode(StrEnum):
    UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "provider_timeout"
    OVERLOADED = "provider_overloaded"
    INVALID_RESPONSE = "provider_invalid_response"
    REQUEST_REJECTED = "provider_request_rejected"
    # K-3 창 가드(오너 2026-07-30). **우리가** 모델을 부르기 전에 거부한 경우로,
    # `REQUEST_REJECTED`(모델 서버가 거부 — 왕복 1회를 이미 쓴 상태)와 **구분해야 한다**:
    # 비용이 이 가드의 이유이므로 "누가 거부했는가"가 곧 그 가드가 일했는지의 신호다.
    CONTEXT_WINDOW_EXCEEDED = "provider_context_window_exceeded"


@dataclass(frozen=True, slots=True)
class ProviderErrorEnvelope:
    code: ProviderErrorCode
    message: str
    retryable: bool
    provider: str | None = None

    def to_dict(self) -> dict[str, dict[str, Any]]:
        error: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.provider is not None:
            error["provider"] = self.provider
        return {"error": error}


class ProviderError(RuntimeError):
    """Provider failure safe to expose through the stable error envelope."""

    def __init__(
        self,
        *,
        code: ProviderErrorCode,
        message: str,
        retryable: bool,
        provider: str | None = None,
    ) -> None:
        if not message:
            raise ValueError("provider error message must not be empty")
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.provider = provider

    def to_envelope(self) -> ProviderErrorEnvelope:
        return ProviderErrorEnvelope(
            code=self.code,
            message=str(self),
            retryable=self.retryable,
            provider=self.provider,
        )
