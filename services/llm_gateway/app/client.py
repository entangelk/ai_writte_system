"""Minimal llama.cpp provider using an injected async JSON transport."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
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
        # 창(`n_ctx`)은 서버 기동 설정이라 호출마다 바뀌지 않는다 → 한 번만 조회해 캐시한다.
        # `_UNPROBED` 센티널을 쓰는 이유: 조회에 실패해 `None`을 얻은 것과 아직 조회하지
        # 않은 것을 구분해야 **실패를 매 호출 재시도하지 않는다**.
        self._context_window: int | None = None
        self._window_probed = False

    async def _probe_context_window(self) -> int | None:
        """llama.cpp `/props`에서 per-slot `n_ctx`를 한 번 읽어 캐시한다.

        **이 조회는 생성을 깨뜨릴 수 없다.** 창은 관측용 부가 정보이고, 그것을 못 읽었다고
        멀쩡한 생성 요청을 실패시키면 관측이 기능을 망가뜨리는 것이 된다(감사 격리와 같은
        원칙). 실패하면 `None`("모른다")으로 남기고 다시 시도하지 않는다.
        """
        if self._window_probed:
            return self._context_window
        self._window_probed = True
        try:
            response = await self._transport.get_json("/props")
            if 200 <= response.status_code < 300:
                settings = _mapping(_mapping(response.body)["default_generation_settings"])
                self._context_window = _token_count(settings["n_ctx"])
        except Exception:  # noqa: BLE001 — 관측이 기능을 깨뜨리지 않는 경계
            self._context_window = None
        return self._context_window

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

        return replace(
            self._parse_response(response),
            context_window=await self._probe_context_window(),
        )

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
