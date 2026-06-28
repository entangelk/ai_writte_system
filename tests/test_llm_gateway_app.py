import unittest

import httpx

from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.main import create_app
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    GenerationResult,
    TokenUsage,
)


class LlmGatewayAppTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, provider):
        app = create_app(provider=provider)
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    async def test_live_health_does_not_require_llama_upstream(self):
        provider = FakeLLMProvider([])

        async with self._client(provider) as client:
            response = await client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_generate_calls_provider_and_returns_gateway_envelope(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="gemma-live",
                    content="완료",
                    finish_reason="stop",
                    usage=TokenUsage(prompt_tokens=2, completion_tokens=1),
                )
            ]
        )

        async with self._client(provider) as client:
            response = await client.post(
                "/v1/generate",
                json={
                    "messages": [{"role": "user", "content": "안녕"}],
                    "max_tokens": 16,
                    "thinking": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "model": "gemma-live",
                "text": "완료",
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 1,
                    "total_tokens": 3,
                },
            },
        )
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].messages[0].role, "user")
        self.assertEqual(provider.requests[0].max_tokens, 16)
        self.assertIs(provider.requests[0].thinking, False)

    async def test_empty_messages_are_rejected_before_provider_call(self):
        provider = FakeLLMProvider([])

        async with self._client(provider) as client:
            response = await client.post("/v1/generate", json={"messages": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(provider.requests, [])

    async def test_provider_error_uses_stable_public_envelope(self):
        cases = (
            (ProviderErrorCode.TIMEOUT, 504),
            (ProviderErrorCode.OVERLOADED, 429),
            (ProviderErrorCode.UNAVAILABLE, 503),
            (ProviderErrorCode.REQUEST_REJECTED, 400),
            (ProviderErrorCode.INVALID_RESPONSE, 502),
        )

        for code, expected_status in cases:
            with self.subTest(code=code):
                provider = FakeLLMProvider(
                    [
                        ProviderError(
                            code=code,
                            message=code.value,
                            retryable=True,
                            provider="gemma_local",
                        )
                    ]
                )

                async with self._client(provider) as client:
                    response = await client.post(
                        "/v1/generate",
                        json={"messages": [{"role": "user", "content": "안녕"}]},
                    )

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(
                    response.json()["detail"],
                    {
                        "code": code.value,
                        "message": code.value,
                        "retryable": True,
                        "provider": "gemma_local",
                    },
                )


if __name__ == "__main__":
    unittest.main()
