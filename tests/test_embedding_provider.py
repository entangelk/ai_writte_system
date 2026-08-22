"""B.1 RemoteEmbeddingProvider seam regression.

Locks the sync httpx client contract against a MockTransport (no live embedding
service): the request shape, a valid vector, optional dimension validation, and
the error mapping for transport/status/body failures. The provider satisfies the
sync EmbeddingProvider Protocol used by indexing and context search.
See docs/plans/04-real-vector-backend-decisions.md (B.1).

`OpenAIEmbeddingProvider` (embedding-adapter slice, decision 1=A) is locked in
the same file and against the same harness: the two providers speak different
wires but sit behind one `embed(text) -> vector` seam, and keeping their
regressions side by side is what makes a divergence visible.
"""

import json
import unittest

import httpx

from services.application.app.indexing.embedding import (
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    RemoteEmbeddingProvider,
)


def _provider(handler, **kwargs):
    return RemoteEmbeddingProvider(
        base_url="http://embedding",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


class RemoteEmbeddingProviderTest(unittest.TestCase):
    def test_posts_text_and_returns_float_vector(self):
        seen = {}

        def handler(request):
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3, 4]})

        vector = _provider(handler).embed("아린은 항구에 도착했다")

        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["path"], "/embed")
        self.assertIn("아린은 항구에 도착했다", seen["body"])
        # Ints are coerced to float; the tuple is the public shape.
        self.assertEqual(vector, (0.1, 0.2, 0.3, 4.0))
        self.assertTrue(all(isinstance(v, float) for v in vector))

    def test_expected_dimensions_pass_and_mismatch(self):
        def handler(_request):
            return httpx.Response(200, json={"embedding": [0.0, 1.0, 2.0]})

        # Matching dimension passes.
        self.assertEqual(
            len(_provider(handler, expected_dimensions=3).embed("x")), 3
        )
        # A mismatch is rejected rather than silently accepted (misconfig guard).
        with self.assertRaises(EmbeddingProviderError):
            _provider(handler, expected_dimensions=1024).embed("x")

    def test_timeout_maps_to_embedding_error(self):
        def handler(_request):
            raise httpx.TimeoutException("slow")

        with self.assertRaises(EmbeddingProviderError):
            _provider(handler).embed("x")

    def test_request_error_maps_to_embedding_error(self):
        def handler(_request):
            raise httpx.ConnectError("refused")

        with self.assertRaises(EmbeddingProviderError):
            _provider(handler).embed("x")

    def test_non_200_status_maps_to_embedding_error(self):
        def handler(_request):
            return httpx.Response(503, json={"detail": "loading model"})

        with self.assertRaises(EmbeddingProviderError):
            _provider(handler).embed("x")

    def test_non_json_body_maps_to_embedding_error(self):
        def handler(_request):
            return httpx.Response(200, text="not json")

        with self.assertRaises(EmbeddingProviderError):
            _provider(handler).embed("x")

    def test_missing_or_empty_embedding_array_rejected(self):
        for body in ({"embedding": []}, {"embedding": "x"}, {"nope": 1}, [1, 2]):
            with self.subTest(body=body):
                def handler(_request, body=body):
                    return httpx.Response(200, json=body)

                with self.assertRaises(EmbeddingProviderError):
                    _provider(handler).embed("x")

    def test_non_numeric_or_bool_values_rejected(self):
        for body in (
            {"embedding": [0.1, "x", 0.3]},
            {"embedding": [0.1, True, 0.3]},
            {"embedding": [0.1, None]},
        ):
            with self.subTest(body=body):
                def handler(_request, body=body):
                    return httpx.Response(200, json=body)

                with self.assertRaises(EmbeddingProviderError):
                    _provider(handler).embed("x")


if __name__ == "__main__":
    unittest.main()


def _openai(handler, **kwargs):
    kwargs.setdefault("model", "text-embedding-3-small")
    kwargs.setdefault("base_url", "https://api.example.com")
    return OpenAIEmbeddingProvider(
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _openai_body(vector):
    return {"data": [{"embedding": list(vector), "index": 0}],
            "usage": {"prompt_tokens": 4, "total_tokens": 4}}


class OpenAIEmbeddingProviderTest(unittest.TestCase):
    """네 가지가 다르다 — 경로·요청 키·응답 구조·인증. 넷을 각각 잠근다."""

    def test_posts_the_openai_shape_and_returns_a_float_vector(self):
        seen = {}

        def handler(request):
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.read().decode())
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=_openai_body([0.1, 0.2, 0.3, 4]))

        vector = _openai(handler, api_key="sk-test").embed("아린은 항구에 도착했다")

        self.assertEqual(seen["method"], "POST")
        # 경로는 provider 가 소유한다 — base 는 호스트 루트다(게이트웨이와 같은 관례).
        self.assertEqual(seen["path"], "/v1/embeddings")
        # 요청 키는 'text' 가 아니라 'input' 이고, 모델을 요청마다 보낸다.
        self.assertEqual(seen["body"],
                         {"input": "아린은 항구에 도착했다",
                          "model": "text-embedding-3-small"})
        self.assertEqual(seen["auth"], "Bearer sk-test")
        # 응답은 data[0].embedding 에 있다.
        self.assertEqual(vector, (0.1, 0.2, 0.3, 4.0))
        self.assertTrue(all(isinstance(v, float) for v in vector))

    def test_expected_dimensions_travel_in_the_request_too(self):
        # 구글 gemini-embedding-2 실측(2026-08-22): dimensions 를 안 보내면 벤더 기본
        # (3072)로 나온다. 가드가 기대하는 값을 요청에도 실어 고정한다.
        # under-strict: 전송을 빼면 응답 차원이 벤더 기본값을 따라간다.
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.read().decode())
            return httpx.Response(200, json=_openai_body([0.0] * 1536))

        _openai(handler, expected_dimensions=1536).embed("x")

        self.assertEqual(seen["body"]["dimensions"], 1536)

    def test_without_expected_dimensions_the_field_stays_absent(self):
        # over-strict: 기대 차원이 없으면(가드 off) 파라미터를 안 보낸다 — 이 필드가
        # 없는 벤더가 400 으로 거부하는 일을 만들지 않는다.
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.read().decode())
            return httpx.Response(200, json=_openai_body([0.0]))

        _openai(handler).embed("x")

        self.assertNotIn("dimensions", seen["body"])

    def test_a_custom_embeddings_path_is_posted_as_given(self):
        # 구글의 OpenAI 호환 루트에는 접미 /v1 이 없다(/v1beta/openai + /embeddings).
        # 조립이 계산해 준 경로를 provider 가 그대로 써야 한다(2026-08-22 실측).
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            return httpx.Response(200, json=_openai_body([0.0]))

        _openai(
            handler,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            embeddings_path="/embeddings",
        ).embed("x")

        self.assertEqual(seen["path"], "/v1beta/openai/embeddings")

    def test_no_api_key_sends_no_authorization_header(self):
        # OpenAI 호환 로컬 서버는 키를 안 받는 경우가 있다. 빈 문자열을 Bearer 로
        # 보내면 그런 서버가 오히려 거부한다.
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=_openai_body([1.0]))

        _openai(handler).embed("x")
        self.assertIsNone(seen["auth"])

    def test_the_dimension_guard_is_the_same_one(self):
        """결정 3=A 의 전 기제가 이 가드다 — 두 provider 에서 갈리면 안 된다."""

        def handler(_request):
            return httpx.Response(200, json=_openai_body([0.0, 1.0, 2.0]))

        self.assertEqual(len(_openai(handler, expected_dimensions=3).embed("x")), 3)
        with self.assertRaises(EmbeddingProviderError):
            _openai(handler, expected_dimensions=1024).embed("x")

    def test_transport_and_status_failures_map_to_embedding_error(self):
        def timeout(_request):
            raise httpx.ConnectTimeout("slow")

        def refused(_request):
            raise httpx.ConnectError("refused")

        def unauthorized(_request):
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        for name, handler in (("timeout", timeout), ("refused", refused),
                              ("401", unauthorized)):
            with self.subTest(failure=name):
                with self.assertRaises(EmbeddingProviderError):
                    _openai(handler).embed("x")

    def test_the_error_message_carries_the_status_and_not_the_body(self):
        # 본문에는 벤더 메시지와 함께 우리가 보낸 텍스트가 되돌아올 수 있다.
        def handler(_request):
            return httpx.Response(
                429, json={"error": {"message": "rate limited: 아린은 항구에"}})

        with self.assertRaises(EmbeddingProviderError) as raised:
            _openai(handler).embed("아린은 항구에")
        self.assertIn("429", str(raised.exception))
        self.assertNotIn("아린은 항구에", str(raised.exception))

    def test_malformed_bodies_are_rejected_rather_than_coerced(self):
        cases = {
            "not json": httpx.Response(200, content=b"nope"),
            "not an object": httpx.Response(200, json=[1, 2, 3]),
            "no data": httpx.Response(200, json={"usage": {}}),
            "empty data": httpx.Response(200, json={"data": []}),
            "data holds scalars": httpx.Response(200, json={"data": ["x"]}),
            "no embedding": httpx.Response(200, json={"data": [{"index": 0}]}),
            "empty embedding": httpx.Response(200, json=_openai_body([])),
            "string values": httpx.Response(200, json=_openai_body(["0.1"])),
            # bool 은 int 의 하위형이라 걸러내지 않으면 0.0/1.0 으로 조용히 들어온다.
            "bool values": httpx.Response(200, json=_openai_body([True, False])),
        }
        for name, response in cases.items():
            with self.subTest(body=name):
                with self.assertRaises(EmbeddingProviderError):
                    _openai(lambda _r, _resp=response: _resp).embed("x")
