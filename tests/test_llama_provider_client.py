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


class ContextWindowProbeTest(unittest.TestCase):
    """관측 1b — 창(`n_ctx`)을 `/props`에서 한 번 읽어 결과에 싣는다.

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

    def test_window_is_read_from_props_and_attached_to_the_result(self):
        provider, transport = self._provider(
            [_valid_response()], [_props(16384)]
        )

        result = asyncio.run(provider.generate(_request()))

        self.assertEqual(result.context_window, 16384)
        self.assertEqual(transport.get_requests, ["/props"])

    def test_window_is_probed_once_not_per_call(self):
        """창은 기동 설정이라 호출마다 물어볼 이유가 없다.

        매 호출 조회하면 생성 1회에 왕복이 2회가 되고, 그 비용이 **관측 때문에** 생긴다.
        """
        provider, transport = self._provider(
            [_valid_response(), _valid_response()], [_props(8192)]
        )

        async def run():
            first = await provider.generate(_request())
            second = await provider.generate(_request())
            return first, second

        first, second = asyncio.run(run())

        self.assertEqual((first.context_window, second.context_window), (8192, 8192))
        # GET은 정확히 한 번. 큐에 하나만 넣었으므로 두 번 물었다면 소진 예외가 났다.
        self.assertEqual(transport.get_requests, ["/props"])

    def test_a_failed_probe_leaves_the_window_unknown_and_does_not_fail_generate(self):
        """**관측이 기능을 깨뜨리지 않는다.**

        `/props`를 못 읽는 것은 창을 모른다는 뜻이지 생성을 못 한다는 뜻이 아니다.
        여기서 예외를 올리면 관측 부가 정보 하나 때문에 멀쩡한 생성이 죽는다 —
        감사 flush 격리(SoT §관측 KPI)와 같은 원칙이다. 그리고 **재시도하지 않는다**:
        실패를 매 호출 다시 물으면 죽은 서버에 왕복을 계속 쌓는다.
        """
        provider, transport = self._provider(
            [_valid_response(), _valid_response()],
            [TransportFailure(TransportFailureKind.CONNECTION)],
        )

        async def run():
            return (await provider.generate(_request()),
                    await provider.generate(_request()))

        first, second = asyncio.run(run())

        self.assertIsNone(first.context_window)
        self.assertIsNone(second.context_window)
        self.assertEqual(transport.get_requests, ["/props"])

    def test_a_malformed_props_body_is_unknown_not_a_guess(self):
        """모양이 다른 `/props`는 "모른다"이지 추측이 아니다."""
        provider, _ = self._provider(
            [_valid_response()],
            [JsonResponse(status_code=200, body={"unexpected": True})],
        )

        result = asyncio.run(provider.generate(_request()))

        self.assertIsNone(result.context_window)
