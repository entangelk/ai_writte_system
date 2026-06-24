import unittest

from services.llm_gateway.app.errors import (
    ProviderError,
    ProviderErrorCode,
)
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import FakeLLMProvider


class ProviderErrorContractTests(unittest.TestCase):
    """Pin stable literals and both retryable/non-retryable envelopes."""

    def test_error_code_literals_are_stable(self):
        self.assertEqual(
            {code.value for code in ProviderErrorCode},
            {
                "provider_unavailable",
                "provider_timeout",
                "provider_overloaded",
                "provider_invalid_response",
                "provider_request_rejected",
            },
        )

    def test_retryable_error_envelope(self):
        error = ProviderError(
            code=ProviderErrorCode.TIMEOUT,
            message="generation timed out",
            retryable=True,
            provider="gemma_local",
        )

        self.assertEqual(
            error.to_envelope().to_dict(),
            {
                "error": {
                    "code": "provider_timeout",
                    "message": "generation timed out",
                    "retryable": True,
                    "provider": "gemma_local",
                }
            },
        )

    def test_non_retryable_error_envelope(self):
        error = ProviderError(
            code=ProviderErrorCode.INVALID_RESPONSE,
            message="provider returned an invalid response",
            retryable=False,
        )

        self.assertEqual(
            error.to_envelope().to_dict(),
            {
                "error": {
                    "code": "provider_invalid_response",
                    "message": "provider returned an invalid response",
                    "retryable": False,
                }
            },
        )

    def test_underlying_exception_is_not_exposed_by_envelope(self):
        cause = TimeoutError("secret upstream address and transport detail")
        error = ProviderError(
            code=ProviderErrorCode.TIMEOUT,
            message="generation timed out",
            retryable=True,
        )
        error.__cause__ = cause

        serialized = str(error.to_envelope().to_dict())
        self.assertNotIn("secret upstream", serialized)
        self.assertNotIn("transport detail", serialized)

    def test_public_error_message_must_not_be_empty(self):
        with self.assertRaisesRegex(ValueError, "message must not be empty"):
            ProviderError(
                code=ProviderErrorCode.INVALID_RESPONSE,
                message="",
                retryable=False,
            )


class ProviderErrorFakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_raises_the_stable_provider_error_unchanged(self):
        error = ProviderError(
            code=ProviderErrorCode.UNAVAILABLE,
            message="provider unavailable",
            retryable=True,
        )
        provider = FakeLLMProvider([error])
        request = ChatCompletionRequest(
            messages=(ChatMessage(role="user", content="hello"),),
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(request)

        self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
