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
