"""Minimal llama.cpp provider using an injected async JSON transport."""

from __future__ import annotations

import asyncio
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
        # `_window_probed`는 "조회에 실패해 None을 얻음"과 "아직 조회 안 함"을 구분한다 —
        # 그래야 **실패를 매 호출 재시도하지 않는다**(죽은 서버에 왕복을 쌓지 않는다).
        self._context_window: int | None = None
        self._window_probed = False
        self._probe_task: asyncio.Task[None] | None = None

    def _start_context_window_probe(self) -> None:
        """창 조회를 **생성과 동시에** 띄우고 기다리지 않는다.

        ★ 이 비동기성이 계약이다(독립 검증 B1, 2026-07-29). 종전 구현은 생성이 **이미
        성공한 뒤** 반환 경로에서 `await probe`를 했는데, `/props`가 느리면 게이트웨이의
        응답이 그만큼 늦어지고 **앱의 상위 deadline(둘 다 120s)을 넘겨 성공한 생성이
        timeout 실패로 뒤집힌다.** 관측용 부가 정보가 기능을 깨뜨리는 것이며 SoT
        §관측 KPI의 격리 조항 위반이다.

        지금은 생성 요청 직전에 조회를 띄우고 **결과를 기다리지 않는다**. 생성은 보통
        초 단위, `/props`는 밀리초 단위이므로 실제로는 첫 호출부터 값이 준비된다. 준비되지
        않았으면 그 호출의 창은 `None`("모른다")이고 **그것이 정직한 답**이다 — 창 하나
        때문에 생성을 붙잡아 두지 않는다.
        """
        if self._window_probed:
            return
        self._window_probed = True
        self._probe_task = asyncio.ensure_future(self._probe_context_window())

    async def _probe_context_window(self) -> None:
        """llama.cpp `/props`에서 per-slot `n_ctx`를 읽어 캐시한다(실패는 삼킨다)."""
        try:
            response = await self._transport.get_json("/props")
            if 200 <= response.status_code < 300:
                settings = _mapping(_mapping(response.body)["default_generation_settings"])
                self._context_window = _token_count(settings["n_ctx"])
        except Exception:  # noqa: BLE001 — 관측이 기능을 깨뜨리지 않는 경계
            self._context_window = None

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> GenerationResult:
        # 생성과 **동시에** 창을 조회한다(기다리지 않는다 — `_start_context_window_probe`).
        self._start_context_window_probe()
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

        # 기다리지 않는다 — 준비됐으면 값, 아니면 `None`("모른다").
        return replace(
            self._parse_response(response),
            context_window=self._context_window,
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
