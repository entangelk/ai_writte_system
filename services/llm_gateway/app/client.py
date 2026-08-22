"""Minimal llama.cpp provider using an injected async JSON transport."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .errors import ProviderError, ProviderErrorCode
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


# 창 가드가 판정에 쓸 수 있는 시간(K-3). 판정에는 왕복이 필요하고(실측 6~67ms), 그 왕복이
# 느려질 때 **생성을 붙잡아 두는 것이 더 나쁘다** — 1b(B1)에서 이미 한 번 그렇게 깨졌다.
# 예산을 넘기면 가드는 판정을 포기하고 요청을 통과시킨다.
_GUARD_BUDGET_SECONDS = 5.0


class LlamaCppProvider:
    def __init__(
        self,
        *,
        transport: JsonTransport,
        default_model: str,
        default_thinking: bool,
        provider_name: str,
        chat_path: str = "/v1/chat/completions",
        llama_extras: bool = True,
    ) -> None:
        # `chat_path` 는 기본(llama.cpp·OpenAI·OpenRouter 의 /v1/chat/completions)에서
        # 벗어나는 벤더를 위한 자리다 — 구글 Gemini API 의 OpenAI 호환 루트는
        # /v1beta/openai 라 접미 /v1 이 없다. 조립(main._chat_endpoint)이 계산해 넣는다.
        #
        # `llama_extras=False`(LLAMA_API_FORMAT=openai)면 llama.cpp 전용 확장을 안 보낸다
        # — `chat_template_kwargs` 를 OpenAI 호환 서버에 보내면 400 "Unknown name" 이다
        # (구글 실측 2026-08-22). /props·/tokenize 프로브도 마찬가지로 llama.cpp 전용이라
        # 끄면 창·토큰수는 "모른다"(None)로 내려간다 — 지어내는 것보다 정직하다.
        self._transport = transport
        self._default_model = default_model
        self._default_thinking = default_thinking
        self._provider_name = provider_name
        self._chat_path = chat_path
        self._llama_extras = llama_extras
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
        if self._llama_extras:
            self._start_context_window_probe()
        payload = build_llama_payload(
            request,
            default_model=self._default_model,
            default_thinking=self._default_thinking,
        )
        if not self._llama_extras:
            # OpenAI 호환 서버는 모르는 필드를 400 으로 거부한다(구글 실측). thinking
            # 토글은 llama.cpp 의 스위치다 — 이 형식에서는 표현 수단이 없다.
            payload.pop("chat_template_kwargs", None)
        # 넘는 요청은 **모델을 부르지 않고** 여기서 거부한다(K-3). 비용이 이유다.
        await self._reject_if_window_exceeded(payload)
        try:
            response = await self._transport.post_json(
                self._chat_path,
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

    async def _reject_if_window_exceeded(self, payload: Mapping[str, Any]) -> None:
        """`입력 + 출력상한 ≤ 창`을 **모델을 부르기 전에** 판정한다(K-3, 오너 2026-07-30).

        왜 `입력 ≤ 창`으로는 부족한가(§1 실측): llama.cpp는 **프롬프트 단독 초과는 400으로
        거부**하지만(왕복 1회를 이미 쓴 뒤다) **`프롬프트 + 출력`이 창을 넘으면 200을 주고
        출력만 조용히 자른다**(`truncated: true`). 후자는 에러가 아니라 **망가진 결과**로
        돌아오므로 가드가 없으면 아무도 모른다.

        **판정할 수 없으면 통과시킨다** — 창을 모르거나(`/props` 실패), 토큰을 못 세거나,
        예산 안에 못 끝나면 가드는 아무 말도 하지 않는다. 방어가 자기 실패로 기능을 깨뜨리면
        안 되며, 그것이 1b(B1)에서 실제로 깨졌던 계약이다. 출력 상한이 없는 요청도
        (`max_tokens` 미지정) `입력+출력` 식을 세울 수 없어 판정 대상이 아니다 — 앱의 모든
        호출부는 상한을 명시한다.
        """
        max_output = payload.get("max_tokens")
        if max_output is None:
            return
        try:
            decision = await asyncio.wait_for(
                self._window_decision(payload, max_output),
                timeout=_GUARD_BUDGET_SECONDS,
            )
        except Exception:  # noqa: BLE001 — 가드의 실패가 생성을 막지 않는 경계
            return
        # 판정은 `_window_decision` 안에서 raise하지 않고 **돌려받아 여기서** 던진다.
        # 위 `except`가 자기 판정까지 삼켜 버리면 가드가 조용히 사라진다.
        if decision is not None:
            raise decision

    async def _window_decision(
        self, payload: Mapping[str, Any], max_output: int
    ) -> ProviderError | None:
        window = self._guard_window()
        if window is None:
            return None
        input_tokens = await self._count_prompt_tokens(payload)
        if input_tokens is None:
            return None
        if input_tokens + max_output <= window:
            return None
        return ProviderError(
            code=ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED,
            message=(
                f"context window exceeded before the call: input {input_tokens} + "
                f"output cap {max_output} = {input_tokens + max_output} > "
                f"window {window}"
            ),
            retryable=False,
            provider=self._provider_name,
        )

    def _guard_window(self) -> int | None:
        """가드가 쓸 창. **기다리지 않는다.**

        기다리고 싶은 유혹이 있다 — 창을 모르면 가드가 판정을 못 하기 때문이다. 그러나 1b
        계약(SoT v1.7.60)이 `/props` 조회를 **"생성과 동시에 시작하고 결과를 기다리지
        않는다"**로 못박았고, 가드를 위해 그것을 기다리면 느린 `/props`가 **다시 생성을
        붙잡는다** — B1이 고친 바로 그 증상이다(실측: 짧은 예산으로 묶어도
        `test_a_slow_probe_does_not_delay_or_fail_the_generate`가 그 예산만큼 매달린다).

        **그래서 창을 아직/끝내 모르는 호출은 가드 밖에 있다.** 두 경우가 있고 둘 다 의도된
        결과다: ① 게이트웨이 프로세스의 **첫 생성 1회**(그 뒤로는 캐시가 찬다), ② `/props`
        조회가 **실패한 프로세스**에서는 계속(1b가 "실패를 재시도하지 않는다"로 정했으므로).
        ②를 닫으려면 가드가 창을 짧은 예산 안에서 기다려야 하고 그것은 v1.7.60의 "기다리지
        않는다"를 **가드 경로에 한해 개정하는 오너 결정**이다 — 임의로 뒤집지 않고 추적
        부채로 남긴다.
        """
        return self._context_window

    async def context_window(self) -> int | None:
        """이 서버의 창(`n_ctx`). **여기서는 조회를 기다린다.**

        생성 경로가 기다리지 않는 것(v1.7.60의 1b 계약)과 모순이 아니다 — 그 계약은
        **생성을 창 조회 때문에 지연시키지 않는다**는 것이고, 이 호출은 창 자체를 묻는
        호출이라 기다리지 않으면 답이 없다. 캐시가 이미 차 있으면 왕복도 없다.
        """
        if not self._window_probed:
            self._window_probed = True
            await self._probe_context_window()
        elif self._probe_task is not None and not self._probe_task.done():
            # 생성이 띄워 둔 조회가 아직 돌고 있으면 그것을 기다린다(중복 조회 금지).
            try:
                await self._probe_task
            except Exception:  # noqa: BLE001 — 실패는 "모른다"로 떨어진다
                return None
        return self._context_window

    async def count_tokens(self, text: str) -> int | None:
        """이 서버의 토크나이저가 `text`를 몇 토큰으로 세는가. **추정이 아니다.**

        채팅 템플릿을 적용하지 않는 raw 계수다 — 호출자가 재는 것은 프롬프트 전체가 아니라
        **그 안에 들어갈 조각**(예: 고정 system 템플릿)이기 때문이다. 못 세면 `None`이며
        호출자는 그때 자기 추정으로 떨어진다(계수 실패가 기능을 막지 않는다).
        """
        if not self._llama_extras:
            # /tokenize 는 llama.cpp 전용 — OpenAI 호환 서버에는 그 경로가 없다.
            return None
        try:
            counted = await self._transport.post_json(
                "/tokenize", {"content": text, "add_special": False}
            )
            if not 200 <= counted.status_code < 300:
                return None
            tokens = _mapping(counted.body)["tokens"]
            if not isinstance(tokens, list):
                return None
            return len(tokens)
        except Exception:  # noqa: BLE001 — 셀 수 없으면 "모른다"
            return None

    async def _count_prompt_tokens(self, payload: Mapping[str, Any]) -> int | None:
        """서버가 실제로 셀 프롬프트 토큰 수. **추정이 아니다.**

        `/apply-template`으로 채팅 템플릿이 적용된 프롬프트를 받아 `/tokenize`로 센다.
        세 가지를 맞춰야 실제 `usage.prompt_tokens`와 일치한다(2026-07-30 실측 delta **0**:
        51/51 · 49/49 · 6,143/6,143):

        ① **같은 `chat_template_kwargs`를 함께 보낸다** — `enable_thinking`이 렌더링을 바꾼다
           (실측: 같은 messages가 51 vs 49). 안 보내면 다른 프롬프트를 센다.
        ② **`add_special`로 BOS를 포함**시킨다(빼면 정확히 −1).
        ③ 메시지 내용만 세면 템플릿 몫이 빠져 **과소평가**된다(실측 −16 ~ −80). 과소평가는
           가드가 늦게 걸리는 방향이라 특히 나쁘다 — 이것이 `len/4` 추정을 쓰지 않는 이유이며,
           그래서 이 가드는 밀도 보정(K-1) 트랙과 **독립**이다.
        """
        try:
            applied = await self._transport.post_json(
                "/apply-template",
                {
                    "messages": payload["messages"],
                    "chat_template_kwargs": payload["chat_template_kwargs"],
                },
            )
            if not 200 <= applied.status_code < 300:
                return None
            prompt = _string(_mapping(applied.body)["prompt"])
            counted = await self._transport.post_json(
                "/tokenize",
                {"content": prompt, "add_special": True},
            )
            if not 200 <= counted.status_code < 300:
                return None
            tokens = _mapping(counted.body)["tokens"]
            if not isinstance(tokens, list):
                return None
            return len(tokens)
        except Exception:  # noqa: BLE001 — 셀 수 없으면 판정하지 않는다(통과)
            return None

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
            if not self._llama_extras:
                # OpenAI 호환 형식에는 thinking 을 끄는 스위치가 없다(구글은 이 모델에
                # reasoning_effort 도 400 으로 거부한다 — 실측 2026-08-22). llama.cpp 의
                # enable_thinking=False 와 같은 계약(content = 답변)을 마크업 제거로 지킨다.
                content = _strip_thought_block(content)
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


def _strip_thought_block(content: str) -> str:
    """`<thought>…</thought>` 한 덩어리를 걷어낸다(OpenAI 호환 형식 전용).

    구글 gemma-4 는 content 를 `<thought>…사고…</thought>답변` 모양으로 준다(실측
    2026-08-22). 닫힌 블록이면 앞뒤를 잇고, **닫히지 않았으면 빈 문자열**이다 —
    창이 사고 도중에 끊겼다는 뜻이고(finish_reason=length), 지어낸 답을 만들지
    않는다. 태그가 없으면 그대로 돌려준다.
    """
    start = content.find("<thought>")
    if start == -1:
        return content
    end = content.find("</thought>", start)
    if end == -1:
        return ""
    return (content[:start] + content[end + len("</thought>") :]).strip()


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value


def _token_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token count must be a non-negative integer")
    return value
