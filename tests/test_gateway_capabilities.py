"""게이트웨이가 창·토큰 계수를 노출하고, 앱이 그것을 캐시해서 쓴다 (R-a 배선).

이 배선의 값은 **앱이 `LLAMA_CTX_SIZE`를 복제하지 않는다**는 데 있다. 그래서 여기서 잠그는
것은 "값이 오간다"만이 아니라 **모를 때 조용히 지어내지 않는다**는 쪽이다.
"""

import unittest

import httpx
from fastapi.testclient import TestClient

from services.application.app.writing.model_capabilities import ModelCapabilities
from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.main import create_app
from services.llm_gateway.app.transport import FakeJsonTransport, JsonResponse


def _props(n_ctx: int) -> JsonResponse:
    return JsonResponse(
        status_code=200, body={"default_generation_settings": {"n_ctx": n_ctx}},
    )


class GatewayCapabilitiesTest(unittest.TestCase):
    def test_it_reports_the_window_the_provider_probed(self):
        provider = LlamaCppProvider(
            transport=FakeJsonTransport([], get_outcomes=[_props(16384)]),
            default_model="m", default_thinking=False, provider_name="p",
        )
        with TestClient(create_app(provider, llama_base_url="http://llama")) as client:
            body = client.get("/v1/capabilities").json()
        self.assertEqual(body, {"context_window": 16384})

    def test_an_unreachable_upstream_reports_null_not_a_guess(self):
        provider = LlamaCppProvider(
            transport=FakeJsonTransport([], get_outcomes=[]),  # 조회가 실패한다
            default_model="m", default_thinking=False, provider_name="p",
        )
        with TestClient(create_app(provider, llama_base_url="http://llama")) as client:
            body = client.get("/v1/capabilities").json()
        self.assertIsNone(body["context_window"])

    def test_a_provider_that_cannot_count_reports_null_tokens(self):
        class _Bare:
            async def generate(self, request): raise AssertionError("not called")

        with TestClient(create_app(_Bare(), llama_base_url="http://llama")) as client:
            body = client.post("/v1/tokenize", json={"text": "가나다"}).json()
        self.assertEqual(body, {"tokens": None})

    def test_it_counts_text_with_the_server_tokenizer(self):
        provider = LlamaCppProvider(
            transport=FakeJsonTransport(
                [JsonResponse(status_code=200, body={"tokens": [1, 2, 3, 4]})]),
            default_model="m", default_thinking=False, provider_name="p",
        )
        with TestClient(create_app(provider, llama_base_url="http://llama")) as client:
            body = client.post("/v1/tokenize", json={"text": "가나다"}).json()
        self.assertEqual(body, {"tokens": 4})


class ModelCapabilitiesClientTest(unittest.IsolatedAsyncioTestCase):
    def _client(self, handler) -> ModelCapabilities:
        return ModelCapabilities(
            base_url="http://gateway", transport=httpx.MockTransport(handler),
        )

    async def test_it_asks_the_gateway_once_and_caches(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={"context_window": 16384})

        capabilities = self._client(handler)
        self.assertEqual(await capabilities.context_window(), 16384)
        self.assertEqual(await capabilities.context_window(), 16384)
        self.assertEqual(calls, ["/v1/capabilities"])

    async def test_a_null_window_is_not_cached_as_a_number(self):
        capabilities = self._client(
            lambda request: httpx.Response(200, json={"context_window": None}))
        self.assertIsNone(await capabilities.context_window())

    async def test_a_gateway_failure_is_unknown_not_an_exception(self):
        """조회 실패가 요청 경로로 새면 예산 최적화가 **생성을 막는다**."""
        def handler(request):
            raise httpx.ConnectError("gateway down")

        self.assertIsNone(await self._client(handler).context_window())

    async def test_an_error_status_is_unknown(self):
        capabilities = self._client(lambda request: httpx.Response(503, text="nope"))
        self.assertIsNone(await capabilities.context_window())

    async def test_token_counts_are_cached_per_text(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={"tokens": 465})

        capabilities = self._client(handler)
        self.assertEqual(await capabilities.count_tokens("report template"), 465)
        self.assertEqual(await capabilities.count_tokens("report template"), 465)
        self.assertEqual(len(calls), 1)

    async def test_a_null_token_count_is_unknown(self):
        capabilities = self._client(
            lambda request: httpx.Response(200, json={"tokens": None}))
        self.assertIsNone(await capabilities.count_tokens("x"))


if __name__ == "__main__":
    unittest.main()
