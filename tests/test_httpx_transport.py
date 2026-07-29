import json
import unittest
from unittest.mock import patch

import httpx

from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.transport import (
    TransportFailure,
    TransportFailureKind,
)


class HttpxJsonTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_environment_proxy_policy_defaults_off_and_allows_opt_in(self):
        for configured, expected in ((None, False), (True, True)):
            with self.subTest(configured=configured):
                kwargs = {"base_url": "http://llama.test:9080"}
                if configured is not None:
                    kwargs["trust_env"] = configured

                with patch(
                    "services.llm_gateway.app.httpx_transport.httpx.AsyncClient"
                ) as client_factory:
                    HttpxJsonTransport(**kwargs)

                self.assertIs(
                    client_factory.call_args.kwargs["trust_env"],
                    expected,
                )

    async def test_success_posts_json_and_decodes_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(json.loads(request.content), {"hello": "world"})
            return httpx.Response(200, json={"ok": True})

        async with HttpxJsonTransport(
            base_url="http://llama.test:9080",
            transport=httpx.MockTransport(handler),
        ) as transport:
            response = await transport.post_json(
                "/v1/chat/completions",
                {"hello": "world"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, {"ok": True})

    async def test_get_json_issues_a_real_http_get(self):
        """관측 1b — `/props` 조회는 **GET**이어야 한다(독립 검증 B2).

        POST로 퇴행해도 fake transport를 쓰는 상위 테스트는 전부 green이다. 실 HTTP
        메서드를 단정하는 곳은 여기뿐이며, llama.cpp `/props`는 GET만 받는다.
        """
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/props")
            self.assertEqual(request.content, b"")   # GET은 본문을 싣지 않는다
            return httpx.Response(
                200, json={"default_generation_settings": {"n_ctx": 16384}}
            )

        async with HttpxJsonTransport(
            base_url="http://llama.test:9080",
            transport=httpx.MockTransport(handler),
        ) as transport:
            response = await transport.get_json("/props")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.body, {"default_generation_settings": {"n_ctx": 16384}}
        )

    async def test_timeout_and_connection_errors_are_classified(self):
        cases = (
            (
                lambda request: httpx.ReadTimeout(
                    "timed out",
                    request=request,
                ),
                TransportFailureKind.TIMEOUT,
            ),
            (
                lambda request: httpx.ConnectError(
                    "connection failed",
                    request=request,
                ),
                TransportFailureKind.CONNECTION,
            ),
        )

        for error_factory, expected_kind in cases:
            with self.subTest(expected_kind=expected_kind):
                def handler(request: httpx.Request) -> httpx.Response:
                    raise error_factory(request)

                async with HttpxJsonTransport(
                    base_url="http://llama.test:9080",
                    transport=httpx.MockTransport(handler),
                ) as transport:
                    with self.assertRaises(TransportFailure) as raised:
                        await transport.post_json("/health", {})

                self.assertEqual(raised.exception.kind, expected_kind)
                self.assertIsInstance(
                    raised.exception.__cause__,
                    httpx.RequestError,
                )

    async def test_non_json_success_is_invalid_response(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-json")

        async with HttpxJsonTransport(
            base_url="http://llama.test:9080",
            transport=httpx.MockTransport(handler),
        ) as transport:
            with self.assertRaises(TransportFailure) as raised:
                await transport.post_json("/v1/chat/completions", {})

        self.assertEqual(
            raised.exception.kind,
            TransportFailureKind.INVALID_RESPONSE,
        )

    async def test_non_json_http_error_keeps_status_for_provider_mapping(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="private upstream detail")

        async with HttpxJsonTransport(
            base_url="http://llama.test:9080",
            transport=httpx.MockTransport(handler),
        ) as transport:
            provider = LlamaCppProvider(
                transport=transport,
                default_model="gemma-test",
                default_thinking=False,
                provider_name="gemma_local",
            )
            request = ChatCompletionRequest(
                messages=(ChatMessage(role="user", content="hello"),),
            )

            with self.assertRaises(ProviderError) as raised:
                await provider.generate(request)

        self.assertEqual(raised.exception.code, ProviderErrorCode.UNAVAILABLE)
        self.assertNotIn(
            "private upstream detail",
            str(raised.exception.to_envelope().to_dict()),
        )

    async def test_context_manager_closes_the_httpx_client(self):
        # Under-strict guard: the client is open while in use.
        # Over-strict guard: exiting the context must close it.
        transport = HttpxJsonTransport(base_url="http://llama.test:9080")
        client = transport._client
        self.assertFalse(client.is_closed)

        async with transport:
            self.assertFalse(client.is_closed)

        self.assertTrue(client.is_closed)


if __name__ == "__main__":
    unittest.main()
