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
                # K-3 창 가드(오너 2026-07-30). `provider_request_rejected`와 별개 literal인
                # 이유는 거부 주체가 다르기 때문이다 — 우리가 부르기 전에 막았으므로 왕복
                # 비용이 0이고, 그 구분이 곧 가드가 일했는지의 신호다.
                "provider_context_window_exceeded",
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


class ProviderErrorStatusMappingTests(unittest.TestCase):
    """앱이 ProviderError를 어느 상태코드로 내는가 — 세 분기 전부.

    이 매핑은 종전에 `504 if TIMEOUT else 502` 형태로 **9개 endpoint에 복제**돼 있었고,
    K-3 창 가드가 세 번째 분기를 더하면서 한 함수(`_provider_error_status`)로 모았다.
    여기서 분기를 전수로 잠그고, endpoint 배선은 각 endpoint의 상태코드 셀이 본다
    (헬퍼만 잠그면 배선이 빠져도 green이다 — 그래서 두 겹이다).
    """

    def _status(self, code):
        from services.application.app.main import _provider_error_status
        return _provider_error_status(ProviderError(
            code=code, message=code.value, retryable=False, provider="llm_gateway"))

    def test_every_code_maps_to_its_documented_status(self):
        cases = {
            ProviderErrorCode.TIMEOUT: 504,               # 상류가 제때 답하지 않았다
            ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED: 400,  # 요청이 너무 크다(K-3)
            ProviderErrorCode.UNAVAILABLE: 502,
            ProviderErrorCode.OVERLOADED: 502,
            ProviderErrorCode.INVALID_RESPONSE: 502,
            ProviderErrorCode.REQUEST_REJECTED: 502,
        }
        # 새 code를 더하고 이 표를 안 고치면 여기서 걸린다 — 기본값 502로 조용히 묻히지 않는다.
        self.assertEqual(set(cases), set(ProviderErrorCode))
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(self._status(code), expected)
