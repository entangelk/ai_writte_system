"""B.4 real vector backend wiring regression.

Locks how create_app selects the vector backend from env: the embedding provider
(fake vs RemoteEmbeddingProvider with the 1024-dim guard) and the vector index
(in-memory fake vs Chroma), and the rebuild summary `backend` literal that
follows. Chroma is exercised through a patched connect_chroma_collection that
returns an in-memory fake collection, so no chromadb/live server is needed.
See docs/plans/04-real-vector-backend-decisions.md (B.4).
"""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.chroma import ChromaVectorIndexAdapter
from services.application.app.indexing.embedding import RemoteEmbeddingProvider
from services.application.app.indexing.service import DeterministicFakeEmbeddingProvider
from services.application.app.main import (
    _build_chroma_vector_index,
    _build_embedding_provider,
    create_app,
)
from tests.test_chroma_adapter import FakeChromaCollection


RAW_TEXT = (
    "# 1장\n\n"
    "아린은 항구에 도착했다.\n\n"
    "낡은 단검에는 검은 태양 문양이 새겨져 있었다.\n\n"
    "---\n\n"
    "밤이 되자 노스워치의 등불이 켜졌다."
)


def _post(app, path):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(path)

    return asyncio.run(send())


def _seed_snapshot():
    core = CoreSotService(InMemoryCoreSotRepository())
    project = core.create_project(name="Novel")
    draft = core.create_draft(project_id=project.id, title="Episode 1")
    saved = core.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=RAW_TEXT,
        idempotency_key="save-1",
    )
    return core, project.id, saved.snapshot.id


def _rebuild_path(project_id, snapshot_id):
    return (
        f"/projects/{project_id}/snapshots/{snapshot_id}"
        "/index/source-blocks/rebuild"
    )


class BuildProvidersTest(unittest.TestCase):
    def test_embedding_provider_defaults_to_fake(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_SERVICE_URL", None)
            self.assertIsInstance(
                _build_embedding_provider(), DeterministicFakeEmbeddingProvider
            )

    def test_embedding_provider_is_remote_with_1024_guard_when_configured(self):
        with patch.dict(
            os.environ, {"EMBEDDING_SERVICE_URL": "http://embedding:8002"}
        ):
            provider = _build_embedding_provider()
        self.assertIsInstance(provider, RemoteEmbeddingProvider)
        # The B.1 dimension guard is armed at 1024 (B.2 verification follow-up).
        self.assertEqual(provider._expected_dimensions, 1024)

    def test_chroma_index_is_none_without_host(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHROMA_HOST", None)
            self.assertIsNone(_build_chroma_vector_index())

    def test_chroma_index_built_from_env_host_and_port(self):
        fake = FakeChromaCollection()
        with patch.dict(
            os.environ, {"CHROMA_HOST": "chroma", "CHROMA_PORT": "8000"}
        ), patch(
            "services.application.app.main.connect_chroma_collection",
            return_value=fake,
        ) as connect:
            adapter = _build_chroma_vector_index()
        self.assertIsInstance(adapter, ChromaVectorIndexAdapter)
        connect.assert_called_once()
        self.assertEqual(connect.call_args.kwargs["host"], "chroma")
        self.assertEqual(connect.call_args.kwargs["port"], 8000)


class WiringBackendTest(unittest.TestCase):
    def test_default_backend_is_in_memory_fake(self):
        core, project_id, snapshot_id = _seed_snapshot()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHROMA_HOST", None)
            app = create_app(service=core)
        resp = _post(app, _rebuild_path(project_id, snapshot_id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["backend"], "in_memory_fake")

    def test_chroma_env_uses_chroma_backend_and_writes_to_collection(self):
        core, project_id, snapshot_id = _seed_snapshot()
        fake = FakeChromaCollection()
        with patch.dict(
            os.environ, {"CHROMA_HOST": "chroma", "CHROMA_PORT": "8000"}
        ), patch(
            "services.application.app.main.connect_chroma_collection",
            return_value=fake,
        ):
            app = create_app(service=core)
            resp = _post(app, _rebuild_path(project_id, snapshot_id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["backend"], "chroma")
        # Records went into the (patched) Chroma collection, not a fake in-memory
        # adapter.
        self.assertGreater(body["records_written"], 0)
        self.assertGreaterEqual(fake.upsert_calls, 1)

    def test_injected_vector_index_keeps_fake_backend_even_with_chroma_env(self):
        # A test-injected vector_index must not be overridden by CHROMA_HOST, and
        # its backend label stays in_memory_fake.
        from services.application.app.indexing.service import (
            InMemoryVectorIndexAdapter,
        )

        core, project_id, snapshot_id = _seed_snapshot()
        with patch.dict(os.environ, {"CHROMA_HOST": "chroma"}), patch(
            "services.application.app.main.connect_chroma_collection"
        ) as connect:
            app = create_app(
                service=core, vector_index=InMemoryVectorIndexAdapter()
            )
            resp = _post(app, _rebuild_path(project_id, snapshot_id))
        self.assertEqual(resp.json()["backend"], "in_memory_fake")
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
