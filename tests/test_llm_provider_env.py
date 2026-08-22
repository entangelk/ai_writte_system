"""_build_provider env 조립 — 키 폴백 구성 행렬 (오너 2026-08-22).

★ 총괄 over-strict 가드: **무설정 세계는 오늘과 동일하다** — 래퍼도 인증 헤더도
없는 단일 provider. 1키는 헤더만, N키 또는 N모델부터 래퍼가 붙는다.
"""

import os
import unittest
from unittest.mock import patch

from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.fallback import FallbackProvider
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.main import _build_provider, _chat_endpoint, create_app
from services.llm_gateway.app.provider import FakeLLMProvider


_VARS = (
    "LLAMA_BASE_URL",
    "LLAMA_API_KEYS",
    "LLAMA_MODELS",
    "LLAMA_DEFAULT_MODEL",
    "LLAMA_KEY_RPM",
    "LLAMA_TIMEOUT_SECONDS",
    "LLAMA_TRUST_ENV",
    "LLAMA_DEFAULT_THINKING",
    "LLAMA_PROVIDER_NAME",
)


class BuildProviderEnvTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in _VARS}
        for name in _VARS:
            os.environ.pop(name, None)
        os.environ["LLAMA_TIMEOUT_SECONDS"] = "5.0"

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _build(self):
        provider, transports, base_url = _build_provider()
        self.addAsyncCleanup(self._aclose_all, transports)
        return provider, transports, base_url

    @staticmethod
    async def _aclose_all(transports):
        for transport in transports:
            await transport.aclose()

    async def test_no_keys_no_models_builds_today_s_provider(self):
        # over-strict 총괄: env 를 하나도 안 준 로컬 llama 구성은 래퍼·헤더·창 계수기
        # 모두 없는 오늘의 provider 그 자체여야 한다.
        provider, transports, _ = self._build()

        self.assertIsInstance(provider, LlamaCppProvider)
        self.assertNotIsInstance(provider, FallbackProvider)
        self.assertEqual(len(transports), 1)
        self.assertIsNone(transports[0]._client.headers.get("Authorization"))

    async def test_one_key_adds_the_bearer_header_without_the_wrapper(self):
        # 1키 × 1모델 — 헤더가 이 변수를 설정하는 이유 전부다. 폴백 조합이 없으니
        # 래퍼까지 얹는 것은 과설계다.
        os.environ["LLAMA_API_KEYS"] = "k1"

        provider, transports, _ = self._build()

        self.assertIsInstance(provider, LlamaCppProvider)
        self.assertEqual(len(transports), 1)
        self.assertEqual(
            transports[0]._client.headers.get("Authorization"),
            "Bearer k1",
        )

    async def test_key_list_builds_one_transport_per_key_and_the_wrapper(self):
        # 쉼표 분리·공백 제거·빈 항목·중복 제거가 조립 지점에서 함께 걸린다:
        # " a , b ,,a " → a, b 두 키(중복 a는 슬롯 doubling 방지로 뺀다).
        os.environ["LLAMA_API_KEYS"] = " a , b ,,a "

        provider, transports, _ = self._build()

        self.assertIsInstance(provider, FallbackProvider)
        self.assertEqual(len(transports), 2)
        self.assertEqual(
            transports[0]._client.headers.get("Authorization"),
            "Bearer a",
        )
        self.assertEqual(
            transports[1]._client.headers.get("Authorization"),
            "Bearer b",
        )

    async def test_model_list_alone_builds_the_wrapper(self):
        # 키 없이 모델만 여럿 — 폴백은 모델 축만. 키 없음 = 인증 없는 슬롯 하나.
        os.environ["LLAMA_MODELS"] = "m1,m2"

        provider, transports, _ = self._build()

        self.assertIsInstance(provider, FallbackProvider)
        self.assertEqual(len(transports), 1)
        self.assertIsNone(transports[0]._client.headers.get("Authorization"))
        self.assertEqual(provider._models, ["m1", "m2"])

    async def test_models_fall_back_to_the_default_model_when_unset(self):
        os.environ["LLAMA_API_KEYS"] = "k1,k2"

        provider, _, _ = self._build()

        self.assertEqual(provider._models, ["gemma-local"])

    async def test_non_positive_rpm_fails_fast(self):
        # 0을 명시한 것은 설정 실수 — 모든 키를 조용히 막는 대신 기동에서 거부한다.
        os.environ["LLAMA_API_KEYS"] = "k1,k2"
        os.environ["LLAMA_KEY_RPM"] = "0"

        with self.assertRaisesRegex(ValueError, "LLAMA_KEY_RPM"):
            _build_provider()

    async def test_the_google_root_builds_the_google_shaped_endpoint(self):
        # 구글 Gemini API 의 OpenAI 호환 루트는 접미 /v1 이 없다 — 정규화가 경로를
        # 맞춰 주지 않으면 붙여넣은 주소는 404 로만 응답한다(live smoke 선행 조건).
        os.environ["LLAMA_BASE_URL"] = (
            "https://generativelanguage.googleapis.com/v1beta/openai"
        )
        os.environ["LLAMA_API_KEYS"] = "AIza-test"

        provider, transports, _ = self._build()

        self.assertIsInstance(provider, LlamaCppProvider)
        self.assertEqual(
            str(transports[0]._client.base_url).rstrip("/"),
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(provider._chat_path, "/chat/completions")

    async def test_the_lifespan_closes_every_owned_transport(self):
        # under-strict: lifespan 안에서는 열려 있고, over-strict: 나갈 때 전부 닫힌다.
        # 첫 transport만 닫는 종전 형태로 되돌아가면 나머지가 Unclosed client 가 된다.
        transports = [
            HttpxJsonTransport(base_url="http://llama.test:9080")
            for _ in range(3)
        ]
        with patch(
            "services.llm_gateway.app.main._build_provider",
            return_value=(
                FakeLLMProvider([]),
                transports,
                "http://llama.test:9080",
            ),
        ):
            app = create_app()

        async with app.router.lifespan_context(app):
            self.assertFalse(
                any(t._client.is_closed for t in transports)
            )

        self.assertTrue(all(t._client.is_closed for t in transports))


class ChatEndpointNormalizationTests(unittest.TestCase):
    """붙여넣은 벤더 주소가 그대로 동작해야 한다(임베딩 `_strip_version_suffix` 관례).

    under-strict: 구글 루트에 /v1 을 얹으면 재실패한다(404). over-strict: 경로 안의
    `v1` 을 접미로 오인해 벗기면 재실패한다.
    """

    def test_pasted_addresses_reach_the_right_endpoint(self):
        cases = {
            # 구글 Gemini API — 문서가 인쇄하는 OpenAI 호환 루트(접미 /v1 이 없다)
            "https://generativelanguage.googleapis.com/v1beta/openai": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/chat/completions",
            ),
            # 같은 주소의 끝 슬래시·전체 엔드포인트 통째로 붙여넣기
            "https://generativelanguage.googleapis.com/v1beta/openai/": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/chat/completions",
            ),
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/chat/completions",
            ),
            # OpenAI — 문서가 …/v1 까지 인쇄한다
            "https://api.openai.com/v1": (
                "https://api.openai.com",
                "/v1/chat/completions",
            ),
            # OpenRouter — …/api/v1 까지 인쇄한다
            "https://openrouter.ai/api/v1": (
                "https://openrouter.ai/api",
                "/v1/chat/completions",
            ),
            # llama.cpp — 오늘의 기본(호스트 루트)
            "http://host.docker.internal:9080": (
                "http://host.docker.internal:9080",
                "/v1/chat/completions",
            ),
            # over-strict: 경로 안의 v1 은 접미가 아니다(임베딩 브리프와 같은 결)
            "https://proxy.example.com/v1/llm": (
                "https://proxy.example.com/v1/llm",
                "/v1/chat/completions",
            ),
        }
        for pasted, (base, path) in cases.items():
            with self.subTest(pasted=pasted):
                self.assertEqual(_chat_endpoint(pasted), (base, path))


if __name__ == "__main__":
    unittest.main()
