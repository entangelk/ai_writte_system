"""Phase 2B.5 increment 2: ChromaMemoryVectorIndexAdapter regression.

Pure logic against an in-memory fake collection (no chromadb): memory record
<->chroma round-trip, upsert, project-scoped delete-by-memory_id, list ordering,
empty-upsert short-circuit. The adapter is the real-backend implementation of the
same `MemoryVectorIndexAdapter` seam the in-memory fake implements, so these lock
its serialization/where-clause logic without a Chroma dependency.
"""

import unittest
from typing import Any

from services.application.app.indexing.chroma import (
    ChromaMemoryVectorIndexAdapter,
    memory_record_from_chroma,
    memory_record_to_chroma,
)
from services.application.app.indexing.models import (
    IndexRecordKind,
    MemoryIndexRecord,
)


def _record(
    memory_id: str,
    *,
    project_id: str = "project-1",
    memory_type: str = "character_observation",
    version: int = 1,
    status: str = "canonical",
    text: str = "Ariel\nbrave",
    vector: tuple[float, ...] = (0.1, 0.2, 0.3),
) -> MemoryIndexRecord:
    return MemoryIndexRecord(
        id=memory_id,
        kind=IndexRecordKind.MEMORY,
        project_id=project_id,
        memory_id=memory_id,
        memory_type=memory_type,
        version=version,
        status=status,
        text=text,
        vector=vector,
    )


class FakeChromaCollection:
    def __init__(self) -> None:
        self._store: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.upsert_calls = 0
        self.delete_calls = 0

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

    def delete(self, *, where) -> None:
        self.delete_calls += 1
        to_remove = [
            record_id
            for record_id, (_embedding, metadata) in self._store.items()
            if self._match(metadata, where)
        ]
        for record_id in to_remove:
            del self._store[record_id]

    def stored_ids(self) -> set[str]:
        return set(self._store)


class MemoryRecordSerializationTest(unittest.TestCase):
    def test_round_trip_preserves_fields(self):
        record = _record("m1", vector=(1, 0.5, 0.25))
        record_id, embedding, metadata = memory_record_to_chroma(record)
        self.assertEqual(record_id, "m1")
        rebuilt = memory_record_from_chroma(record_id, embedding, metadata)
        self.assertEqual(rebuilt, record)

    def test_chroma_id_is_memory_id(self):
        record_id, _emb, meta = memory_record_to_chroma(_record("mv-42"))
        self.assertEqual(record_id, "mv-42")
        self.assertEqual(meta["memory_id"], "mv-42")


class ChromaMemoryAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = FakeChromaCollection()
        self.adapter = ChromaMemoryVectorIndexAdapter(self.collection)

    def test_upsert_and_list(self):
        self.adapter.upsert_memory_records((_record("m1"), _record("m2")))
        records = self.adapter.list_memory_records(project_id="project-1")
        self.assertEqual([r.memory_id for r in records], ["m1", "m2"])
        self.assertEqual(records[0].kind, IndexRecordKind.MEMORY)

    def test_empty_upsert_short_circuits(self):
        self.assertEqual(self.adapter.upsert_memory_records(()), 0)
        self.assertEqual(self.collection.upsert_calls, 0)

    def test_list_is_project_scoped(self):
        self.adapter.upsert_memory_records(
            (_record("m1"), _record("m2", project_id="project-2"))
        )
        records = self.adapter.list_memory_records(project_id="project-1")
        self.assertEqual([r.memory_id for r in records], ["m1"])

    def test_delete_removes_only_target_in_project(self):
        self.adapter.upsert_memory_records((_record("m1"), _record("m2")))
        self.adapter.delete_memory_record(project_id="project-1", memory_id="m1")
        self.assertEqual(self.collection.stored_ids(), {"m2"})

    def test_delete_is_project_scoped(self):
        # over-strict guard: a record with the same memory_id in another project
        # must survive a project-1 delete (the where clause is $and-scoped).
        self.adapter.upsert_memory_records(
            (
                _record("m1", project_id="project-1"),
                _record("p2-dup", project_id="project-2"),
            )
        )
        # Force the project-2 record to carry the same memory_id "m1".
        embedding, metadata = self.collection._store["p2-dup"]
        metadata["memory_id"] = "m1"
        self.adapter.delete_memory_record(project_id="project-1", memory_id="m1")
        self.assertNotIn("m1", self.collection.stored_ids())
        self.assertIn("p2-dup", self.collection.stored_ids())


if __name__ == "__main__":
    unittest.main()
