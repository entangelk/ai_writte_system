"""Application-side LLM Gateway provider adapter tests."""

import unittest

import httpx

from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.main import create_app as create_gateway_app
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    GenerationResult,
    TokenUsage,
)


class GatewayGenerateProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_calls_gateway_generate_and_parses_result(self):
        gateway_provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="gemma",
                    content='{"candidates":[]}',
                    finish_reason="stop",
                    usage=TokenUsage(prompt_tokens=3, completion_tokens=4),
                )
            ]
        )
        provider = GatewayGenerateProvider(
            base_url="http://gateway",
            transport=httpx.ASGITransport(app=create_gateway_app(gateway_provider)),
        )

        result = await provider.generate(
            ChatCompletionRequest(
                messages=(ChatMessage(role="user", content="안녕"),),
                max_tokens=32,
                thinking=False,
            )
        )

        self.assertEqual(result.model, "gemma")
        self.assertEqual(result.content, '{"candidates":[]}')
        self.assertEqual(result.usage.total_tokens, 7)
        self.assertEqual(gateway_provider.requests[0].max_tokens, 32)
        self.assertIs(gateway_provider.requests[0].thinking, False)

    async def test_non_null_context_window_survives_gateway_and_app_boundaries(self):
        """관측 1b — 창이 **두 경계를 모두** 통과해야 한다(독립 검증 B3).

        경로는 provider → 게이트웨이 봉투 → 앱 파서다. 어느 한쪽이 항상 `None`을 실어도
        `None`만 쓰는 테스트는 전부 green이므로, **비어 있지 않은 값**으로 관통시키는
        셀이 따로 있어야 한다. 이 값이 조용히 `None`으로 퇴행하면 헤드룸을 계산할 분모가
        사라지고 지표가 통째로 죽는다.
        """
        gateway_provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="gemma",
                    content='{"candidates":[]}',
                    finish_reason="stop",
                    usage=TokenUsage(prompt_tokens=3, completion_tokens=4),
                    context_window=16384,
                )
            ]
        )
        provider = GatewayGenerateProvider(
            base_url="http://gateway",
            transport=httpx.ASGITransport(app=create_gateway_app(gateway_provider)),
        )

        result = await provider.generate(
            ChatCompletionRequest(
                messages=(ChatMessage(role="user", content="안녕"),),
            )
        )

        self.assertEqual(result.context_window, 16384)

    async def test_gateway_error_envelope_is_preserved(self):
        gateway_provider = FakeLLMProvider(
            [
                ProviderError(
                    code=ProviderErrorCode.TIMEOUT,
                    message="provider_timeout",
                    retryable=True,
                    provider="gemma_local",
                )
            ]
        )
        provider = GatewayGenerateProvider(
            base_url="http://gateway",
            transport=httpx.ASGITransport(app=create_gateway_app(gateway_provider)),
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(
                ChatCompletionRequest(
                    messages=(ChatMessage(role="user", content="안녕"),)
                )
            )

        self.assertEqual(raised.exception.code, ProviderErrorCode.TIMEOUT)
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.provider, "gemma_local")

    async def test_malformed_gateway_success_is_invalid_response(self):
        async def handler(_request):
            return httpx.Response(200, content=b"not-json")

        provider = GatewayGenerateProvider(
            base_url="http://gateway",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ProviderError) as raised:
            await provider.generate(
                ChatCompletionRequest(
                    messages=(ChatMessage(role="user", content="안녕"),)
                )
            )

        self.assertEqual(raised.exception.code, ProviderErrorCode.INVALID_RESPONSE)
        self.assertFalse(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
