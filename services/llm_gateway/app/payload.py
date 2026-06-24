"""Build the non-streaming llama.cpp chat payload used by the gateway.

The thinking behavior is adapted from the local ``gemma4_12b`` reference at
commit ``485c4e2``.  This module is self-contained and has no runtime dependency
on that repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str | None = None

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("message role must not be empty")

    def to_payload(self) -> dict[str, str]:
        payload = {"role": self.role}
        if self.content is not None:
            payload["content"] = self.content
        return payload


@dataclass(frozen=True, slots=True)
class ChatCompletionRequest:
    messages: tuple[ChatMessage, ...]
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    thinking: bool | None = None
    chat_template_kwargs: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("messages must not be empty")
        if self.stream:
            raise ValueError("streaming is not supported by the gateway")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("max_tokens must be greater than zero")


def build_llama_payload(
    request: ChatCompletionRequest,
    *,
    default_model: str,
    default_thinking: bool,
) -> dict[str, Any]:
    """Translate the stable gateway request into a llama.cpp payload."""

    if not default_model:
        raise ValueError("default_model must not be empty")

    effective_thinking = (
        request.thinking
        if request.thinking is not None
        else default_thinking
    )
    template_kwargs = dict(request.chat_template_kwargs or {})
    template_kwargs.setdefault("enable_thinking", effective_thinking)

    payload: dict[str, Any] = {
        "model": request.model or default_model,
        "messages": [message.to_payload() for message in request.messages],
        "chat_template_kwargs": template_kwargs,
        "stream": False,
    }

    optional_fields = {
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value

    return payload
