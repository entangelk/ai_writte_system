import unittest

from services.llm_gateway.app.errors import ProviderErrorCode
from services.llm_gateway.app.transport import (
    FakeJsonTransport,
    FakeTransportExhausted,
    TransportFailureKind,
    error_from_http_status,
    error_from_transport_failure,
)


class TransportFailureMappingTests(unittest.TestCase):
    def test_transport_failures_map_to_stable_errors(self):
        cases = (
            (
                TransportFailureKind.TIMEOUT,
                ProviderErrorCode.TIMEOUT,
                True,
            ),
            (
                TransportFailureKind.CONNECTION,
                ProviderErrorCode.UNAVAILABLE,
                True,
            ),
            (
                TransportFailureKind.INVALID_RESPONSE,
                ProviderErrorCode.INVALID_RESPONSE,
                False,
            ),
        )

        for kind, expected_code, expected_retryable in cases:
            with self.subTest(kind=kind):
                error = error_from_transport_failure(
                    kind,
                    provider="gemma_local",
                )
                self.assertEqual(error.code, expected_code)
                self.assertIs(error.retryable, expected_retryable)
                self.assertEqual(error.provider, "gemma_local")


class FakeJsonTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_exhaustion_fails_instead_of_fabricating_a_response(self):
        transport = FakeJsonTransport([])

        with self.assertRaisesRegex(
            FakeTransportExhausted,
            "no queued outcome",
        ):
            await transport.post_json("/v1/chat/completions", {})

        self.assertEqual(
            transport.requests,
            [("/v1/chat/completions", {})],
        )


class HttpStatusMappingTests(unittest.TestCase):
    def test_timeout_statuses_are_retryable(self):
        for status_code in (408, 504):
            with self.subTest(status_code=status_code):
                error = error_from_http_status(status_code)
                self.assertEqual(error.code, ProviderErrorCode.TIMEOUT)
                self.assertIs(error.retryable, True)

    def test_overload_status_is_retryable(self):
        error = error_from_http_status(429)

        self.assertEqual(error.code, ProviderErrorCode.OVERLOADED)
        self.assertIs(error.retryable, True)

    def test_server_errors_are_unavailable_and_retryable(self):
        for status_code in (500, 502, 503, 599):
            with self.subTest(status_code=status_code):
                error = error_from_http_status(status_code)
                self.assertEqual(error.code, ProviderErrorCode.UNAVAILABLE)
                self.assertIs(error.retryable, True)

    def test_other_client_errors_are_rejected_and_not_retryable(self):
        # 401/403은 여서 빠진다 — 그 둘은 요청이 아니라 **키**가 거부된 것이므로 아래
        # 별도 셀로 간다(키 폴백 슬라이스, 오너 2026-08-22). 이 셀이 401/403까지 잡고
        # 있으면 over-strict다: 키 실패를 요청 실패로 뭉개면 폴백이 키를 안 바꾼다.
        for status_code in (400, 404, 422):
            with self.subTest(status_code=status_code):
                error = error_from_http_status(status_code)
                self.assertEqual(
                    error.code,
                    ProviderErrorCode.REQUEST_REJECTED,
                )
                self.assertIs(error.retryable, False)

    def test_auth_failures_are_key_rejected(self):
        # under-strict 방향: 401/403을 REQUEST_REJECTED로 되돌리면 이 셀이 재실패한다 —
        # 키 폴백 계층은 이 코드를 보고 "키를 바꿔라"를 판단한다.
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                error = error_from_http_status(status_code)
                self.assertEqual(error.code, ProviderErrorCode.KEY_REJECTED)
                self.assertIs(error.retryable, False)

    def test_success_and_redirect_statuses_are_not_misclassified_as_errors(self):
        for status_code in (200, 204, 301, 307):
            with self.subTest(status_code=status_code):
                with self.assertRaisesRegex(
                    ValueError,
                    "does not represent a provider error",
                ):
                    error_from_http_status(status_code)

    def test_mapping_does_not_include_upstream_response_body(self):
        error = error_from_http_status(503, provider="gemma_local")
        serialized = str(error.to_envelope().to_dict())

        self.assertEqual(error.provider, "gemma_local")
        self.assertNotIn("upstream", serialized)
        self.assertNotIn("response body", serialized)


if __name__ == "__main__":
    unittest.main()
