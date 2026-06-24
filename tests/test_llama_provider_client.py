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

    def _provider(self, outcomes):
        transport = FakeJsonTransport(outcomes)
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
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": -1, "completion_tokens": 1},
                },
            ),
            JsonResponse(
                status_code=200,
                body={
                    "model": "gemma-live",
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
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

    async def test_missing_usage_is_valid_and_defaults_to_zero(self):
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

        result = await provider.generate(_request())

        self.assertEqual(result.usage.total_tokens, 0)

    async def test_zero_token_counts_are_accepted_as_valid(self):
        # Over-strict guard for the lower bound of "non-negative integer":
        # an explicit prompt_tokens=0 / completion_tokens=0 must be accepted,
        # not only tolerated through the usage-omission default path.
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
