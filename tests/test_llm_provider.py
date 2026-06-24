import unittest

from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    FakeProviderExhausted,
    GenerationResult,
    LLMProvider,
    TokenUsage,
)


def _request(content: str) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=(ChatMessage(role="user", content=content),),
    )


def _result(content: str) -> GenerationResult:
    return GenerationResult(
        model="fake-gemma",
        content=content,
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=2, completion_tokens=1),
    )


class FakeLLMProviderTests(unittest.IsolatedAsyncioTestCase):
    """The fake must model both normal provider behavior and explicit failure."""

    def test_fake_satisfies_provider_protocol(self):
        provider = FakeLLMProvider([_result("ok")])

        self.assertIsInstance(provider, LLMProvider)

    async def test_results_are_fifo_and_requests_are_recorded(self):
        provider = FakeLLMProvider([_result("first"), _result("second")])
        first_request = _request("one")
        second_request = _request("two")

        first = await provider.generate(first_request)
        second = await provider.generate(second_request)

        self.assertEqual(first.content, "first")
        self.assertEqual(second.content, "second")
        self.assertEqual(provider.requests, [first_request, second_request])

    async def test_queued_error_is_raised_without_consuming_next_result(self):
        provider = FakeLLMProvider(
            [TimeoutError("provider timed out"), _result("recovered")]
        )

        with self.assertRaisesRegex(TimeoutError, "provider timed out"):
            await provider.generate(_request("first attempt"))

        recovered = await provider.generate(_request("retry"))
        self.assertEqual(recovered.content, "recovered")
        self.assertEqual(len(provider.requests), 2)

    async def test_exhaustion_fails_instead_of_fabricating_a_response(self):
        provider = FakeLLMProvider([])

        with self.assertRaisesRegex(FakeProviderExhausted, "no queued outcome"):
            await provider.generate(_request("unexpected call"))

        self.assertEqual(len(provider.requests), 1)


if __name__ == "__main__":
    unittest.main()
