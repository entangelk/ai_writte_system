"""H1 — deterministic fake round-trip for the loop-audit Mongo adapter.

Mirrors `test_gate_findings_mongo.py` (the "채택된 기본값" precedent the brief
cites): a fake collection exercised in the standard suite, catching a `_doc`↔`_run`
field drift without a live Mongo. Append-only insert (no replace), newest-first
list ordering, project isolation, and stable index name are pinned.
"""

import unittest
from datetime import UTC, datetime

from services.application.app.writing.loop_audit import (
    StoredLoopStage,
    StoredWritingLoopRun,
)
from services.application.app.writing.loop_audit_mongo import (
    MongoWritingLoopAuditRepository,
)


class _Cursor(list):
    def sort(self, keys):
        docs = list(self)
        for key, direction in reversed(keys):
            docs.sort(key=lambda doc: doc[key], reverse=(direction == -1))
        return _Cursor(docs)


class _Collection:
    def __init__(self):
        self.docs = {}
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise AssertionError("append-only: duplicate _id insert")
        self.docs[doc["_id"]] = dict(doc)

    def find_one(self, query):
        return self.docs.get(query["_id"])

    def find(self, query):
        return _Cursor(
            doc for doc in self.docs.values()
            if all(doc.get(key) == value for key, value in query.items())
        )


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "writing_loop_audits"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _run(run_id, *, project="p", minute=0, loop_status="pass",
         error_type=None):
    return StoredWritingLoopRun(
        id=run_id, project_id=project, request_id="r1",
        loop_status=loop_status, revision_rounds=2, retrieval_rounds=1,
        gate_evaluations=2, error_type=error_type,
        trigger_finding_fingerprint="f" * 64,
        initial_candidate_hash="a" * 64, final_candidate_hash="b" * 64,
        final_candidate_text="최종 본문", final_gate_decision="pass",
        final_gate_finding_fingerprints=("c" * 64,),
        stages=(
            StoredLoopStage("revise", 1, "completed", "h1", "fp1", ()),
            StoredLoopStage("gate", 2, "completed", "b" * 64, None,
                            ("d1", "s1")),
        ),
        created_at=datetime(2026, 7, 13, 0, minute, tzinfo=UTC),
        total_tokens=123, wall_clock_ms=456,
    )


class MongoWritingLoopAuditRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoWritingLoopAuditRepository(
            _Client(self.collection), db_name="test"
        )

    def test_installs_project_created_index_with_stable_name(self):
        self.assertEqual(self.collection.indexes, [(
            [("project_id", 1), ("created_at", -1)],
            {"name": "writing_loop_audits_by_project_created"},
        )])

    def test_add_get_and_list_round_trip_newest_first(self):
        earlier = _run("wla:a", minute=1)
        later = _run("wla:z", minute=5)
        other = _run("wla:other", project="other", minute=9)
        failed = _run("wla:f", minute=3, loop_status="failed",
                      error_type="gate_error")
        for run in (earlier, later, other, failed):
            self.repo.add(run)

        # Field-for-field round trip (catches _doc↔_run drift).
        self.assertEqual(self.repo.get("wla:a"), earlier)
        self.assertEqual(self.repo.get("wla:f"), failed)
        self.assertIsNone(self.repo.get("ghost"))
        # Project-scoped, created_at desc.
        self.assertEqual(
            tuple(run.id for run in self.repo.list_for_project("p")),
            ("wla:z", "wla:f", "wla:a"),
        )
        self.assertEqual(
            tuple(run.id for run in self.repo.list_for_project("other")),
            ("wla:other",),
        )

    def test_add_is_append_only_insert(self):
        self.repo.add(_run("wla:a"))
        with self.assertRaises(AssertionError):
            self.repo.add(_run("wla:a"))

    def test_legacy_doc_without_aggregate_fields_reads_zero(self):
        """Under-strict: pre-v1.6.80 docs default both aggregates to zero.

        The present-field direction remains pinned by the field-for-field
        round-trip assertion in ``test_add_get_and_list_round_trip_newest_first``.
        """
        self.repo.add(_run("wla:legacy"))
        legacy = self.collection.docs["wla:legacy"]
        legacy.pop("total_tokens")
        legacy.pop("wall_clock_ms")

        restored = self.repo.get("wla:legacy")

        self.assertEqual(restored.total_tokens, 0)
        self.assertEqual(restored.wall_clock_ms, 0)


if __name__ == "__main__":
    unittest.main()
