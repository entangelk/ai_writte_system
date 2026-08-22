import asyncio
import unittest

from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider
from services.llm_gateway.app.transport import (
    FakeJsonTransport,
    JsonResponse,
    TransportFailure,
    TransportFailureKind,
)


def _request(*, thinking: bool = False) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=(ChatMessage(role="user", content="안녕"),),
        thinking=thinking,
        max_tokens=64,
    )


def _valid_response(content: str = "반가워요") -> JsonResponse:
    return JsonResponse(
        status_code=200,
        body={
            "model": "gemma-live",
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        },
    )


class LlamaCppProviderTests(unittest.IsolatedAsyncioTestCase):
    """Cover valid generation and each failure boundary without live HTTP."""

    def _provider(self, outcomes, *, get_outcomes=None):
        transport = FakeJsonTransport(outcomes, get_outcomes=get_outcomes)
        provider = LlamaCppProvider(
            transport=transport,
            default_model="gemma-default",
            default_thinking=True,
            provider_name="gemma_local",
        )
        return provider, transport

    def test_client_satisfies_provider_protocol(self):
        provider, _ = self._provider([_valid_response()])

        self.assertIsInstance(provider, LLMProvider)

    async def test_a_custom_chat_path_is_posted_as_given(self):
        # 구글 Gemini API 의 OpenAI 호환 루트에는 접미 /v1 이 없다(/v1beta/openai).
        # 조립이 계산해 준 경로를 provider 가 그대로 써야 한다 — 기본 경로를 하드코딩된
        # 것으로 되돌리면 이 셀이 재실패한다(붙여넣은 주소 관례, 2026-08-22).
        transport = FakeJsonTransport([_valid_response()])
        provider = LlamaCppProvider(
            transport=transport,
            default_model="gemma-4-31b-it",
            default_thinking=False,
            provider_name="google",
            chat_path="/chat/completions",
        )

        await provider.generate(_request())

        path, _payload = transport.requests[0]
        self.assertEqual(path, "/chat/completions")

    async def test_valid_response_is_parsed_and_payload_is_recorded(self):
        provider, transport = self._provider([_valid_response()])

        result = await provider.generate(_request(thinking=False))

        self.assertEqual(result.model, "gemma-live")
        self.assertEqual(result.content, "반가워요")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage.prompt_tokens, 5)
        self.assertEqual(result.usage.completion_tokens, 3)
        self.assertEqual(result.usage.total_tokens, 8)
        self.assertEqual(len(transport.requests), 1)
        path, payload = transport.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertIs(
            payload["chat_template_kwargs"]["enable_thinking"],
            False,
        )
        self.assertEqual(payload["max_tokens"], 64)

    async def test_transport_timeout_maps_to_stable_provider_error(self):
        provider, _ = self._provider(
            [TransportFailure(TransportFailureKind.TIMEOUT)]
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(_request())

        self.assertEqual(raised.exception.code, ProviderErrorCode.TIMEOUT)
        self.assertIs(raised.exception.retryable, True)
        self.assertIsInstance(raised.exception.__cause__, TransportFailure)

    async def test_http_overload_maps_without_exposing_response_body(self):
        provider, _ = self._provider(
            [JsonResponse(status_code=429, body={"secret": "upstream detail"})]
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(_request())

        self.assertEqual(raised.exception.code, ProviderErrorCode.OVERLOADED)
        serialized = str(raised.exception.to_envelope().to_dict())
        self.assertNotIn("upstream detail", serialized)

    async def test_redirect_response_is_not_accepted_as_generation(self):
        redirect = _valid_response()
        provider, _ = self._provider(
            [JsonResponse(status_code=307, body=redirect.body)]
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(_request())

        self.assertEqual(
            raised.exception.code,
            ProviderErrorCode.INVALID_RESPONSE,
        )
        self.assertIs(raised.exception.retryable, False)

    async def test_malformed_success_response_is_not_accepted(self):
        malformed_responses = (
            JsonResponse(status_code=200, body=[]),
            JsonResponse(status_code=200, body={"choices": []}),
            JsonResponse(
                status_code=200,
                body={"model": "gemma-live", "choices": [42]},
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": None,
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": None}, "finish_reason": "stop"}
                    ],
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": None}
                    ],
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": -1, "completion_tokens": 1},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": True},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": "1", "completion_tokens": 1},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"completion_tokens": 1},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1.5, "completion_tokens": 1},
                },
            ),
        )

        for response in malformed_responses:
            with self.subTest(body=response.body):
                provider, _ = self._provider([response])
                with self.assertRaises(ProviderError) as raised:
                    await provider.generate(_request())
                self.assertEqual(
                    raised.exception.code,
                    ProviderErrorCode.INVALID_RESPONSE,
                )
                self.assertIs(raised.exception.retryable, False)

    async def test_missing_usage_is_rejected_as_invalid_response(self):
        response = JsonResponse(
            status_code=200,
            body={
                "model": "gemma-live",
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
        provider, _ = self._provider([response])

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(_request())

        self.assertEqual(
            raised.exception.code,
            ProviderErrorCode.INVALID_RESPONSE,
        )
        self.assertIs(raised.exception.retryable, False)

    async def test_zero_token_counts_are_accepted_as_valid(self):
        # Over-strict guard for the lower bound of "non-negative integer":
        # an explicit prompt_tokens=0 / completion_tokens=0 must be accepted,
        # while omission of the usage object itself remains invalid.
        response = JsonResponse(
            status_code=200,
            body={
                "model": "gemma-live",
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        )
        provider, _ = self._provider([response])

        result = await provider.generate(_request())

        self.assertEqual(result.usage.prompt_tokens, 0)
        self.assertEqual(result.usage.completion_tokens, 0)
        self.assertEqual(result.usage.total_tokens, 0)


if __name__ == "__main__":
    unittest.main()


def _props(n_ctx):
    return JsonResponse(
        status_code=200,
        body={"default_generation_settings": {"n_ctx": n_ctx}},
    )


def _applied(prompt="<start>안녕<end>"):
    """`/apply-template` 응답 — 채팅 템플릿이 적용된 프롬프트."""
    return JsonResponse(status_code=200, body={"prompt": prompt})


def _tokenized(count):
    """`/tokenize` 응답 — 토큰 배열(가드는 길이만 쓴다)."""
    return JsonResponse(status_code=200, body={"tokens": list(range(count))})


def _guard_probes(input_tokens):
    """가드가 판정에 쓰는 두 왕복. 생성 응답 **앞에** 놓인다."""
    return [_applied(), _tokenized(input_tokens)]


class ContextWindowProbeTest(unittest.TestCase):
    """관측 1b — 창(`n_ctx`)을 `/props`에서 읽어 결과에 싣되, **생성을 붙잡지 않는다.**

    창은 자원 배분 지표의 **분모**다(입력 토큰이 분자). 그런데 창은 서버 기동 설정이라
    repo가 통제하지 못하는 배포가 있으므로(베타는 외부 서버) **상수로 박지 않고 읽는다.**
    """

    def _provider(self, outcomes, get_outcomes):
        transport = FakeJsonTransport(outcomes, get_outcomes=get_outcomes)
        return LlamaCppProvider(
            transport=transport,
            default_model="gemma-default",
            default_thinking=True,
            provider_name="gemma_local",
        ), transport

    async def _generate_then_settle(self, provider):
        """생성한 뒤 이벤트 루프를 한 번 돌려 probe가 끝날 틈을 준다."""
        result = await provider.generate(_request())
        await asyncio.sleep(0)
        return result

    def test_window_is_attached_once_the_probe_completes(self):
        provider, transport = self._provider(
            # 두 번째 생성은 창을 알므로 **가드가 돈다** → 판정 왕복 2회가 앞에 붙는다.
            [_valid_response(), *_guard_probes(10), _valid_response()],
            [_props(16384)],
        )

        async def run():
            await self._generate_then_settle(provider)
            return await provider.generate(_request())

        result = asyncio.run(run())

        self.assertEqual(result.context_window, 16384)
        self.assertEqual(transport.get_requests, ["/props"])

    def test_a_slow_probe_does_not_delay_or_fail_the_generate(self):
        """★ B1(독립 검증 2026-07-29) — **관측이 기능을 깨뜨리지 않는다.**

        종전 구현은 생성이 **이미 성공한 뒤** 반환 경로에서 `await probe`를 했다. `/props`가
        느리면 게이트웨이 응답이 그만큼 늦어지고, 게이트웨이 transport와 앱 상위 deadline이
        **둘 다 120s**라 **성공한 생성이 timeout 실패로 뒤집힌다.** 관측용 부가 정보가 기능을
        깨뜨리는 것이며 SoT §관측 KPI 격리 조항 위반이다.

        여기서는 **끝나지 않는** probe를 준다. 생성은 그대로 성공해야 하고 창만 `None`이어야
        한다. probe를 다시 기다리는 구현으로 되돌리면 이 테스트는 **영원히 끝나지 않는다**.
        """
        never = asyncio.Event()

        class _HangingGet(FakeJsonTransport):
            async def get_json(self, path):
                self.get_requests.append(path)
                await never.wait()          # 절대 풀리지 않는다
                raise AssertionError("unreachable")

        transport = _HangingGet([_valid_response()], get_outcomes=[])
        provider = LlamaCppProvider(
            transport=transport, default_model="gemma-default",
            default_thinking=True, provider_name="gemma_local",
        )

        async def run():
            result = await asyncio.wait_for(provider.generate(_request()), timeout=5)
            never.set()                     # 매달린 probe를 정리한다
            await asyncio.sleep(0)
            return result

        result = asyncio.run(run())

        self.assertEqual(result.content, "반가워요")   # 생성은 성공했다
        self.assertIsNone(result.context_window)       # 창만 "모른다"
        self.assertEqual(transport.get_requests, ["/props"])

    def test_window_is_probed_once_not_per_call(self):
        """창은 기동 설정이라 호출마다 물어볼 이유가 없다.

        매 호출 조회하면 생성 1회에 왕복이 2회가 되고, 그 비용이 **관측 때문에** 생긴다.
        """
        provider, transport = self._provider(
            [_valid_response(),
             *_guard_probes(10), _valid_response(),
             *_guard_probes(10), _valid_response()],
            [_props(8192)],
        )

        async def run():
            await self._generate_then_settle(provider)
            return (await provider.generate(_request()),
                    await provider.generate(_request()))

        second, third = asyncio.run(run())

        self.assertEqual((second.context_window, third.context_window), (8192, 8192))
        # GET은 정확히 한 번. 큐에 하나만 넣었으므로 두 번 물었다면 소진 예외가 났다.
        self.assertEqual(transport.get_requests, ["/props"])

    def test_a_failed_probe_leaves_the_window_unknown_and_is_not_retried(self):
        """실패해도 생성은 성공하고, **재시도하지 않는다**.

        실패를 매 호출 다시 물으면 죽은 서버에 왕복을 계속 쌓는다.
        """
        provider, transport = self._provider(
            [_valid_response(), _valid_response()],
            [TransportFailure(TransportFailureKind.CONNECTION)],
        )

        async def run():
            first = await self._generate_then_settle(provider)
            return first, await provider.generate(_request())

        first, second = asyncio.run(run())

        self.assertIsNone(first.context_window)
        self.assertIsNone(second.context_window)
        self.assertEqual(transport.get_requests, ["/props"])

    def test_a_malformed_props_body_is_unknown_not_a_guess(self):
        """모양이 다른 `/props`는 "모른다"이지 추측이 아니다."""
        provider, _ = self._provider(
            [_valid_response(), _valid_response()],
            [JsonResponse(status_code=200, body={"unexpected": True})],
        )

        async def run():
            await self._generate_then_settle(provider)
            return await provider.generate(_request())

        self.assertIsNone(asyncio.run(run()).context_window)


class ContextWindowGuardTest(unittest.TestCase):
    """K-3 창 가드(오너 2026-07-30) — `입력 + 출력상한 ≤ 창`을 **모델 호출 전에** 판정한다.

    왜 `입력 ≤ 창`으로는 부족한가(§1 실측): 프롬프트 단독 초과는 서버가 400으로 거부하지만
    (왕복 1회를 이미 쓴 뒤다) **`프롬프트 + 출력`이 넘으면 서버는 200을 주고 출력만 조용히
    자른다.** 후자는 에러가 아니라 망가진 결과로 돌아오므로 가드가 없으면 아무도 모른다.

    가드의 입력 수는 **추정이 아니라 서버가 셀 값**이다(`/apply-template` → `/tokenize`).
    그래서 이 가드는 밀도 보정(K-1)과 독립이며, `len/4` 추정 위에 세우면 −55% 과소평가로
    **걸려야 할 때 걸리지 않는다**.
    """

    def _guarded_provider(self, outcomes, *, n_ctx=1000):
        """창이 이미 캐시된 provider(첫 호출로 캐시를 채운 뒤 돌려준다)."""
        transport = FakeJsonTransport(
            [_valid_response(), *outcomes], get_outcomes=[_props(n_ctx)]
        )
        provider = LlamaCppProvider(
            transport=transport, default_model="gemma-default",
            default_thinking=False, provider_name="gemma_local",
        )

        async def warm():
            await provider.generate(_request())
            await asyncio.sleep(0)          # probe가 캐시를 채우도록 한 틱 양보
        asyncio.run(warm())
        return provider, transport

    def test_over_the_window_is_rejected_without_calling_the_model(self):
        # under-strict + 비용: 입력 900 + 출력 상한 64 = 964 > 창 900 → 거부.
        # **생성 응답을 큐에 넣지 않았다** — 모델을 부르면 소진 예외로 터진다.
        provider, transport = self._guarded_provider(_guard_probes(900), n_ctx=900)

        with self.assertRaises(ProviderError) as raised:
            asyncio.run(provider.generate(_request()))

        error = raised.exception
        self.assertIs(error.code, ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED)
        self.assertFalse(error.retryable)   # 같은 요청은 반드시 같은 실패로 끝난다
        # 400 detail이 곧 "경고"다(오너 2026-07-30) — 수치가 본문에 있어야 원인을 안다.
        for number in ("900", "64", "964"):
            self.assertIn(number, str(error))
        # 첫 항목은 캐시를 채운 warm-up 생성이다. 그 뒤로는 판정 왕복 2회뿐이어야 한다.
        self.assertEqual(
            [path for path, _ in transport.requests][1:],
            ["/apply-template", "/tokenize"],
            "가드가 걸렸는데 모델을 불렀다 — 비용을 아끼려고 만든 가드다",
        )

    def test_exactly_at_the_window_is_allowed(self):
        # over-strict 경계: 입력 936 + 출력 64 = 1000 == 창 1000 → 통과해야 한다.
        # `<=`를 `<`로 좁히면 정상 요청이 거부된다.
        provider, _ = self._guarded_provider(
            [*_guard_probes(936), _valid_response()], n_ctx=1000
        )
        self.assertEqual(asyncio.run(provider.generate(_request())).content, "반가워요")

    def test_one_token_over_the_window_is_rejected(self):
        # 같은 경계의 반대편: 937 + 64 = 1001 > 1000 → 거부. 두 셀이 함께 `<=`를 고정한다.
        provider, _ = self._guarded_provider(_guard_probes(937), n_ctx=1000)
        with self.assertRaises(ProviderError):
            asyncio.run(provider.generate(_request()))

    def test_the_guard_counts_the_templated_prompt_not_the_message_text(self):
        """가드는 `/apply-template`의 렌더링 결과를 세고, 같은 `chat_template_kwargs`를 보낸다.

        실측(2026-07-30): `enable_thinking`이 렌더링을 바꿔 같은 messages가 51 vs 49가 된다.
        kwargs를 안 보내면 **다른 프롬프트를 세게 되고**, 메시지 본문만 세면 템플릿 몫이 빠져
        과소평가된다(−16 ~ −80). 과소평가는 가드가 늦게 걸리는 방향이라 특히 나쁘다.
        """
        provider, transport = self._guarded_provider(
            [*_guard_probes(10), _valid_response()], n_ctx=1000
        )
        asyncio.run(provider.generate(_request()))

        paths = [path for path, _ in transport.requests]
        self.assertEqual(paths[1:], ["/apply-template", "/tokenize",
                                     "/v1/chat/completions"])
        applied_payload = transport.requests[1][1]
        completion_payload = transport.requests[3][1]
        self.assertEqual(applied_payload["messages"], completion_payload["messages"])
        self.assertEqual(applied_payload["chat_template_kwargs"],
                         completion_payload["chat_template_kwargs"])
        # BOS를 포함해야 실제 usage.prompt_tokens와 일치한다(빼면 정확히 −1).
        self.assertIs(transport.requests[2][1]["add_special"], True)

    def test_an_unknown_window_passes_through(self):
        """창을 모르면 판정하지 않는다 — 가드가 자기 무지로 생성을 막지 않는다.

        `/props` 실패는 1b 계약대로 재시도하지 않으므로, 그 프로세스에서 가드는 계속 꺼진
        상태로 남는다. **의도된 결과이며 추적 부채로 적혀 있다**(닫으려면 v1.7.60의
        "기다리지 않는다"를 가드 경로에 한해 개정하는 오너 결정이 필요하다).
        """
        transport = FakeJsonTransport(
            [_valid_response(), _valid_response()],
            get_outcomes=[TransportFailure(TransportFailureKind.CONNECTION)],
        )
        provider = LlamaCppProvider(
            transport=transport, default_model="gemma-default",
            default_thinking=False, provider_name="gemma_local",
        )

        async def run():
            await provider.generate(_request())
            await asyncio.sleep(0)
            return await provider.generate(_request())

        # 가드 왕복이 큐를 먹지 않는다 — 판정 자체를 시작하지 않기 때문이다.
        self.assertEqual(asyncio.run(run()).content, "반가워요")
        self.assertEqual([path for path, _ in transport.requests],
                         ["/v1/chat/completions", "/v1/chat/completions"])

    def test_a_guard_probe_failure_passes_through(self):
        """토큰을 셀 수 없으면 통과시킨다(방어가 기능을 깨뜨리지 않는다)."""
        for name, outcomes in (
            ("apply-template 실패", [TransportFailure(TransportFailureKind.CONNECTION),
                                     _valid_response()]),
            ("apply-template 4xx", [JsonResponse(status_code=404, body={}),
                                    _valid_response()]),
            ("tokenize 실패", [_applied(), TransportFailure(TransportFailureKind.TIMEOUT),
                               _valid_response()]),
            ("모양이 다른 응답", [_applied(), JsonResponse(status_code=200, body={"x": 1}),
                                 _valid_response()]),
        ):
            with self.subTest(name=name):
                provider, _ = self._guarded_provider(outcomes, n_ctx=10)
                self.assertEqual(
                    asyncio.run(provider.generate(_request())).content, "반가워요")

    def test_a_request_without_an_output_cap_is_not_judged(self):
        """`max_tokens`가 없으면 `입력+출력` 식을 세울 수 없다 → 판정하지 않는다.

        앱의 모든 호출부는 상한을 명시하므로 이 경로는 게이트웨이를 직접 치는 호출자용이다.
        판정하지 않으므로 가드 왕복도 쓰지 않는다.
        """
        provider, transport = self._guarded_provider([_valid_response()], n_ctx=10)
        request = ChatCompletionRequest(
            messages=(ChatMessage(role="user", content="안녕"),), thinking=False)

        self.assertEqual(asyncio.run(provider.generate(request)).content, "반가워요")
        self.assertEqual([path for path, _ in transport.requests],
                         ["/v1/chat/completions", "/v1/chat/completions"])
