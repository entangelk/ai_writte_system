"""B.1 RemoteEmbeddingProvider seam regression.

Locks the sync httpx client contract against a MockTransport (no live embedding
service): the request shape, a valid vector, optional dimension validation, and
the error mapping for transport/status/body failures. The provider satisfies the
sync EmbeddingProvider Protocol used by indexing and context search.
See docs/plans/04-real-vector-backend-decisions.md (B.1).
"""

import unittest

import httpx

from services.application.app.indexing.embedding import (
    EmbeddingProviderError,
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
