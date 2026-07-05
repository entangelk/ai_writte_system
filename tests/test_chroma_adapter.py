"""B.3 ChromaVectorIndexAdapter regression.

Two surfaces:
- Pure logic with an in-memory FakeChromaCollection (no chromadb): record<->chroma
  round-trip, project scoping, archived exclusion, id ordering, cosine ranking,
  limit, empty-upsert short-circuit. Runs in both environments.
- Skip-aware live Chroma (import chromadb + CHROMA_TEST_URL): upsert/query/list
  and restart-survival (a fresh client sees the same data).
See docs/plans/04-real-vector-backend-decisions.md (B.3).
"""

import os
import unittest
from typing import Any

from services.application.app.indexing.chroma import (
    ChromaVectorIndexAdapter,
    connect_chroma_collection,
    record_from_chroma,
    record_to_chroma,
)
from services.application.app.indexing.models import (
    IndexPointer,
    IndexRecordKind,
    SourceBlockIndexRecord,
)
from services.application.app.indexing.service import _cosine_similarity


def _record(
    record_id: str,
    *,
    project_id: str = "project-1",
    vector: tuple[float, ...] = (1.0, 0.0),
    snapshot_id: str = "snapshot-1",
    block_index: int = 0,
    project_archived: bool = False,
    draft_archived: bool = False,
) -> SourceBlockIndexRecord:
    return SourceBlockIndexRecord(
        id=record_id,
        kind=IndexRecordKind.SOURCE_BLOCK,
        pointer=IndexPointer(
            project_id=project_id,
            collection="project_memory_vectors",
            document_id="draft-1",
            version_id="version-1",
            content_hash="hash-" + record_id,
        ),
        snapshot_id=snapshot_id,
        draft_id="draft-1",
        block_id="block-" + record_id,
        block_index=block_index,
        text="본문 " + record_id,
        vector=vector,
        project_archived=project_archived,
        draft_archived=draft_archived,
    )


class FakeChromaCollection:
    """In-memory stand-in for a Chroma collection supporting the subset of the
    API the adapter uses: upsert, get, query, with equality / $and where and
    cosine ranking."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.upsert_calls = 0

    def upsert(self, *, ids, embeddings, metadatas) -> None:
        self.upsert_calls += 1
        for record_id, embedding, metadata in zip(ids, embeddings, metadatas):
            self._store[record_id] = (list(embedding), dict(metadata))

    @staticmethod
    def _match(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
        if not where:
            return True
        if "$and" in where:
            return all(
                FakeChromaCollection._match(metadata, cond) for cond in where["$and"]
            )
        return all(metadata.get(key) == value for key, value in where.items())

    def get(self, *, where, include):
        ids, embeddings, metadatas = [], [], []
        for record_id, (embedding, metadata) in self._store.items():
            if self._match(metadata, where):
                ids.append(record_id)
                embeddings.append(embedding)
                metadatas.append(metadata)
        result: dict[str, Any] = {"ids": ids}
        if "embeddings" in include:
            result["embeddings"] = embeddings
        if "metadatas" in include:
            result["metadatas"] = metadatas
        return result

    def query(self, *, query_embeddings, n_results, where, include):
        query_vector = tuple(query_embeddings[0])
        matched = [
            (record_id, embedding, metadata)
            for record_id, (embedding, metadata) in self._store.items()
            if self._match(metadata, where)
        ]
        matched.sort(
            key=lambda item: (
                -_cosine_similarity(query_vector, tuple(item[1])),
                item[0],
            )
        )
        top = matched[:n_results]
        result: dict[str, Any] = {"ids": [[item[0] for item in top]]}
        if "embeddings" in include:
            result["embeddings"] = [[item[1] for item in top]]
        if "metadatas" in include:
            result["metadatas"] = [[item[2] for item in top]]
        return result


class ChromaSerializationTest(unittest.TestCase):
    def test_record_chroma_roundtrip_preserves_all_fields(self):
        record = _record("r1", vector=(0.1, 0.2, 0.3), block_index=4)
        record_id, embedding, metadata = record_to_chroma(record)
        self.assertEqual(record_id, "r1")
        self.assertEqual(embedding, [0.1, 0.2, 0.3])
        rebuilt = record_from_chroma(record_id, embedding, metadata)
        self.assertEqual(rebuilt, record)

    def test_roundtrip_coerces_embedding_to_float_tuple(self):
        record = _record("r1", vector=(1.0, 0.0))
        _id, _embedding, metadata = record_to_chroma(record)
        # Chroma may hand back ints/other numeric types; reconstruction normalizes.
        rebuilt = record_from_chroma("r1", [1, 0], metadata)
        self.assertEqual(rebuilt.vector, (1.0, 0.0))
        self.assertTrue(all(isinstance(v, float) for v in rebuilt.vector))


class ChromaAdapterLogicTest(unittest.TestCase):
    def setUp(self):
        self.collection = FakeChromaCollection()
        self.adapter = ChromaVectorIndexAdapter(self.collection)

    def test_upsert_empty_short_circuits(self):
        self.assertEqual(self.adapter.upsert_records(()), 0)
        self.assertEqual(self.collection.upsert_calls, 0)

    def test_list_records_excludes_archived_and_sorts_by_id(self):
        self.adapter.upsert_records(
            (
                _record("b"),
                _record("a"),
                _record("z", project_archived=True),
                _record("y", draft_archived=True),
            )
        )
        active = self.adapter.list_records(project_id="project-1")
        self.assertEqual([r.id for r in active], ["a", "b"])
        allrec = self.adapter.list_records(
            project_id="project-1", include_archived=True
        )
        self.assertEqual([r.id for r in allrec], ["a", "b", "y", "z"])

    def test_list_records_is_project_scoped(self):
        self.adapter.upsert_records(
            (_record("a", project_id="p1"), _record("b", project_id="p2"))
        )
        self.assertEqual(
            [r.id for r in self.adapter.list_records(project_id="p1")], ["a"]
        )

    def test_query_similar_ranks_by_cosine_excludes_archived_and_limits(self):
        self.adapter.upsert_records(
            (
                _record("near", vector=(1.0, 0.0)),
                _record("far", vector=(0.0, 1.0)),
                _record("archived_near", vector=(1.0, 0.0), project_archived=True),
            )
        )
        hits = self.adapter.query_similar(
            project_id="project-1", vector=(1.0, 0.05), limit=2
        )
        ids = [r.id for r in hits]
        # near ranks first; archived excluded even though its vector is closest.
        self.assertEqual(ids[0], "near")
        self.assertNotIn("archived_near", ids)
        self.assertTrue(all(isinstance(r, SourceBlockIndexRecord) for r in hits))

    def test_query_similar_respects_limit(self):
        self.adapter.upsert_records(
            tuple(_record(f"r{i}", vector=(1.0, float(i))) for i in range(5))
        )
        self.assertEqual(
            len(self.adapter.query_similar(
                project_id="project-1", vector=(1.0, 0.0), limit=3
            )),
            3,
        )

    def test_query_similar_rejects_nonpositive_limit(self):
        with self.assertRaises(ValueError):
            self.adapter.query_similar(project_id="project-1", vector=(1.0,), limit=0)


_CHROMA_URL = os.environ.get("CHROMA_TEST_URL")


def _chroma_host_port():
    # CHROMA_TEST_URL like "localhost:8000".
    host, _, port = (_CHROMA_URL or "").partition(":")
    return host, int(port or "8000")


try:  # pragma: no cover - availability probe
    import chromadb as _chromadb  # noqa: F401

    _CHROMADB_INSTALLED = True
except Exception:  # pragma: no cover
    _CHROMADB_INSTALLED = False


@unittest.skipUnless(
    _CHROMA_URL and _CHROMADB_INSTALLED,
    "set CHROMA_TEST_URL and install chromadb for the live Chroma test",
)
class ChromaAdapterLiveTest(unittest.TestCase):
    def setUp(self):
        import chromadb

        host, port = _chroma_host_port()
        self._client = chromadb.HttpClient(host=host, port=port)
        self._name = "b3_live_test"
        self._client.get_or_create_collection(
            name=self._name, metadata={"hnsw:space": "cosine"}
        )

    def tearDown(self):
        try:
            self._client.delete_collection(name=self._name)
        except Exception:
            pass

    def _adapter(self):
        host, port = _chroma_host_port()
        return ChromaVectorIndexAdapter(
            connect_chroma_collection(host=host, port=port, collection_name=self._name)
        )

    def test_upsert_query_list_and_restart_survival(self):
        adapter = self._adapter()
        adapter.upsert_records(
            (
                _record("near", vector=(1.0, 0.0)),
                _record("far", vector=(0.0, 1.0)),
            )
        )
        hits = adapter.query_similar(
            project_id="project-1", vector=(1.0, 0.05), limit=1
        )
        self.assertEqual([r.id for r in hits], ["near"])

        # A fresh client/collection handle (simulating a process restart) sees
        # the persisted records.
        fresh = self._adapter()
        listed = fresh.list_records(project_id="project-1")
        self.assertEqual({r.id for r in listed}, {"near", "far"})
        # Reconstructed records preserve pointer/hash for the SOT re-read.
        near = next(r for r in listed if r.id == "near")
        self.assertEqual(near.pointer.content_hash, "hash-near")


if __name__ == "__main__":
    unittest.main()
