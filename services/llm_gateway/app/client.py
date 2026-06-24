"""Minimal llama.cpp provider using an injected async JSON transport."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .payload import ChatCompletionRequest, build_llama_payload
from .provider import GenerationResult, TokenUsage
from .transport import (
    JsonResponse,
    JsonTransport,
    TransportFailure,
    TransportFailureKind,
    error_from_http_status,
    error_from_transport_failure,
)


class LlamaCppProvider:
    def __init__(
        self,
        *,
        transport: JsonTransport,
        default_model: str,
        default_thinking: bool,
        provider_name: str,
    ) -> None:
        self._transport = transport
        self._default_model = default_model
        self._default_thinking = default_thinking
        self._provider_name = provider_name

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> GenerationResult:
        payload = build_llama_payload(
            request,
            default_model=self._default_model,
            default_thinking=self._default_thinking,
        )
        try:
            response = await self._transport.post_json(
                "/v1/chat/completions",
                payload,
            )
        except TransportFailure as exc:
            error = error_from_transport_failure(
                exc.kind,
                provider=self._provider_name,
            )
            raise error from exc

        if response.status_code >= 400:
            raise error_from_http_status(
                response.status_code,
                provider=self._provider_name,
            )
        if not 200 <= response.status_code < 300:
            raise error_from_transport_failure(
                TransportFailureKind.INVALID_RESPONSE,
                provider=self._provider_name,
            )

        return self._parse_response(response)

    def _parse_response(self, response: JsonResponse) -> GenerationResult:
        try:
            body = _mapping(response.body)
            model = _string(body["model"])
            choices = body["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError("choices must be a non-empty list")

            choice = _mapping(choices[0])
            message = _mapping(choice["message"])
            content = _string(message["content"])
            finish_reason = _string(choice["finish_reason"])

            usage = _mapping(body["usage"])
            prompt_tokens = _token_count(usage["prompt_tokens"])
            completion_tokens = _token_count(usage["completion_tokens"])
        except (KeyError, TypeError, ValueError) as exc:
            error = error_from_transport_failure(
                TransportFailureKind.INVALID_RESPONSE,
                provider=self._provider_name,
            )
            raise error from exc

        return GenerationResult(
            model=model,
            content=content,
            finish_reason=finish_reason,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("value must be an object")
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value


def _token_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token count must be a non-negative integer")
    return value
