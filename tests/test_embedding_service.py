"""B.2 embedding service regression.

Two surfaces:
- Producer app self-regression (ASGITransport, injected stub model): /embed
  returns {embedding, dimensions}, /health, readiness, empty-text rejection, and
  the not-loaded 503 path.
- Producer<->consumer round-trip: the service's build_embed_response output is
  consumed by the B.1 RemoteEmbeddingProvider unchanged, so the wire contract
  ({"text"} -> {"embedding": [...]}) cannot drift between B.2 and B.1.
See docs/plans/04-real-vector-backend-decisions.md (B.2).
"""

import hashlib
import json
import unittest

import httpx

from services.application.app.indexing.embedding import RemoteEmbeddingProvider
from services.embedding.app.main import build_embed_response, create_app


class StubEmbeddingModel:
    """Deterministic no-dependency stand-in for the sentence-transformers model."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(self._dimensions)]


class EmbeddingServiceAppTest(unittest.IsolatedAsyncioTestCase):
    async def _client(self, app):
        return httpx.AsyncClient(
            base_url="http://embedding",
            transport=httpx.ASGITransport(app=app),
        )

    async def test_embed_returns_vector_and_dimensions(self):
        model = StubEmbeddingModel(dimensions=8)
        async with await self._client(create_app(model=model)) as client:
            resp = await client.post("/embed", json={"text": "아린은 항구에 도착했다"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["dimensions"], 8)
        self.assertEqual(len(body["embedding"]), 8)
        self.assertEqual(body["embedding"], model.embed("아린은 항구에 도착했다"))

    async def test_health_and_readiness_when_model_present(self):
        async with await self._client(create_app(model=StubEmbeddingModel())) as client:
            live = await client.get("/health/live")
            ready = await client.get("/health/ready")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)

    async def test_empty_text_is_rejected(self):
        async with await self._client(create_app(model=StubEmbeddingModel())) as client:
            resp = await client.post("/embed", json={"text": ""})
        self.assertEqual(resp.status_code, 422)

    async def test_not_loaded_model_returns_503(self):
        # create_app() without an injected model and without lifespan (ASGITransport
        # does not run lifespan) leaves the model unset: /embed and readiness 503.
        async with await self._client(create_app()) as client:
            embed = await client.post("/embed", json={"text": "x"})
            ready = await client.get("/health/ready")
            live = await client.get("/health/live")
        self.assertEqual(embed.status_code, 503)
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(live.status_code, 200)


class EmbeddingWireContractRoundTripTest(unittest.TestCase):
    """Locks the producer (build_embed_response) against the consumer (B.1
    RemoteEmbeddingProvider): the B.2 response shape is exactly what B.1 parses,
    so the two sides of the wire contract cannot drift."""

    def test_service_response_is_consumable_by_remote_provider(self):
        model = StubEmbeddingModel(dimensions=8)

        def handler(request):
            text = json.loads(request.read())["text"]
            return httpx.Response(200, json=build_embed_response(model, text))

        provider = RemoteEmbeddingProvider(
            base_url="http://embedding",
            transport=httpx.MockTransport(handler),
            expected_dimensions=8,
        )
        vector = provider.embed("아린은 편지를 다시 읽었다")

        self.assertEqual(vector, tuple(model.embed("아린은 편지를 다시 읽었다")))
        self.assertTrue(all(isinstance(v, float) for v in vector))


if __name__ == "__main__":
    unittest.main()
