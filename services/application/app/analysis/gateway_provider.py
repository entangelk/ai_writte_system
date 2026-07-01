"""Application-side provider adapter for the LLM Gateway `/v1/generate` API."""

from __future__ import annotations

from typing import Any

import httpx

from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.payload import ChatCompletionRequest
from services.llm_gateway.app.provider import GenerationResult, TokenUsage


class GatewayGenerateProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 120.0,
        trust_env: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._trust_env = trust_env
        self._transport = transport

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        payload = {
            "messages": [
                message.to_payload()
                for message in request.messages
            ],
            "model": request.model,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "thinking": request.thinking,
            "chat_template_kwargs": (
                dict(request.chat_template_kwargs)
                if request.chat_template_kwargs is not None
                else None
            ),
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=self._trust_env,
                transport=self._transport,
            ) as client:
                response = await client.post("/v1/generate", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code=ProviderErrorCode.TIMEOUT,
                message="gateway request timed out",
                retryable=True,
                provider="llm_gateway",
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="gateway is unavailable",
                retryable=True,
                provider="llm_gateway",
            ) from exc

        if response.status_code >= 400:
            raise _provider_error_from_response(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                code=ProviderErrorCode.INVALID_RESPONSE,
                message="gateway response is invalid",
                retryable=False,
                provider="llm_gateway",
            ) from exc
        return _generation_result(body)


def _provider_error_from_response(response: httpx.Response) -> ProviderError:
    try:
        detail = response.json()["detail"]
        if isinstance(detail, dict):
            code = ProviderErrorCode(detail["code"])
            message = str(detail["message"])
            retryable = bool(detail["retryable"])
            provider = detail.get("provider")
            if provider is not None and not isinstance(provider, str):
                provider = None
            return ProviderError(
                code=code,
                message=message,
                retryable=retryable,
                provider=provider,
            )
    except (KeyError, TypeError, ValueError):
        pass
    code = (
        ProviderErrorCode.REQUEST_REJECTED
        if response.status_code == 400
        else ProviderErrorCode.INVALID_RESPONSE
    )
    return ProviderError(
        code=code,
        message=f"gateway returned HTTP {response.status_code}",
        retryable=response.status_code >= 500,
        provider="llm_gateway",
    )


def _generation_result(body: Any) -> GenerationResult:
    try:
        if not isinstance(body, dict):
            raise TypeError("body must be an object")
        usage = body["usage"]
        if not isinstance(usage, dict):
            raise TypeError("usage must be an object")
        return GenerationResult(
            model=_string(body["model"]),
            content=_string(body["text"]),
            finish_reason=_string(body["finish_reason"]),
            usage=TokenUsage(
                prompt_tokens=_token_count(usage["prompt_tokens"]),
                completion_tokens=_token_count(usage["completion_tokens"]),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(
            code=ProviderErrorCode.INVALID_RESPONSE,
            message="gateway response is invalid",
            retryable=False,
            provider="llm_gateway",
        ) from exc


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value


def _token_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token count must be a non-negative integer")
    return value
