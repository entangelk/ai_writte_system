"""Deterministic fake round-trip for the llm-call-audit Mongo adapter.

Mirrors ``test_writing_loop_audit_mongo.py`` (the standing precedent a new
``*_mongo.py`` must follow): a fake collection exercised in the standard suite
catches a ``_doc``↔``_call`` field drift without a live Mongo. Append-only
insert, newest-first project-scoped list ordering, and a stable index name are
pinned.
"""

import unittest
from datetime import UTC, datetime

from services.application.app.observability.llm_call_audit import StoredLlmCall
from services.application.app.observability.llm_call_audit_mongo import (
    MongoLlmCallAuditRepository,
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

    def find(self, query):
        return _Cursor(
            doc for doc in self.docs.values()
            if all(doc.get(key) == value for key, value in query.items())
        )


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "llm_call_audits"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _call(call_id, *, project="p", minute=0, call_site="writing_gate",
          decision="pass", score=1.0, outcome="success", error_type=None):
    return StoredLlmCall(
        id=call_id, project_id=project, call_site=call_site,
        correlation_id="req-1", model="claude-fake", outcome=outcome,
        decision=decision, gate_quality_score=score,
        total_tokens=222, latency_ms=900, error_type=error_type,
        created_at=datetime(2026, 7, 24, 0, minute, tzinfo=UTC),
    )


class MongoLlmCallAuditRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoLlmCallAuditRepository(
            _Client(self.collection), db_name="test"
        )

    def test_installs_both_read_indexes_with_stable_names(self):
        # D8-5c added the second one: the compound index cannot serve the
        # project-less sort ``list_all`` issues, and an unindexed sort is a
        # blocking in-memory sort that fails once the collection is large.
        self.assertEqual(self.collection.indexes, [
            ([("project_id", 1), ("created_at", -1)],
             {"name": "llm_call_audits_by_project_created"}),
            ([("created_at", -1)], {"name": "llm_call_audits_by_created"}),
        ])

    def test_add_and_list_round_trip_newest_first(self):
        earlier = _call("llmc:a", minute=1)
        later = _call("llmc:z", minute=5)
        other = _call("llmc:other", project="other", minute=9)
        errored = _call("llmc:e", minute=3, call_site="query_planner",
                        decision=None, score=None, outcome="provider_error",
                        error_type="upstream_unavailable")
        for call in (earlier, later, other, errored):
            self.repo.add(call)

        # Field-for-field round trip (catches _doc↔_call drift).
        [only_other] = self.repo.list_for_project("other")
        self.assertEqual(only_other, other)
        by_id = {c.id: c for c in self.repo.list_for_project("p")}
        self.assertEqual(by_id["llmc:e"], errored)
        # Project-scoped, created_at desc.
        self.assertEqual(
            tuple(c.id for c in self.repo.list_for_project("p")),
            ("llmc:z", "llmc:e", "llmc:a"),
        )

    def test_list_all_spans_projects_and_stays_newest_first(self):
        # D8-5c. The project-scoped read above is what keeps a caller inside one
        # project, so the global read is asserted to cross exactly that line —
        # and to round-trip fields the same way, since it is the admin KPI's
        # only source.
        earlier = _call("llmc:a", minute=1)
        later = _call("llmc:z", minute=5)
        other = _call("llmc:other", project="other", minute=9)
        for call in (earlier, later, other):
            self.repo.add(call)

        listed = self.repo.list_all()

        self.assertEqual(tuple(c.id for c in listed),
                         ("llmc:other", "llmc:z", "llmc:a"))
        self.assertEqual(listed[0], other)

    def test_add_is_append_only_insert(self):
        self.repo.add(_call("llmc:a"))
        with self.assertRaises(AssertionError):
            self.repo.add(_call("llmc:a"))

    def test_legacy_doc_without_metric_fields_reads_zero(self):
        # Under-strict: a doc missing the numeric aggregates defaults them to 0
        # rather than raising. Present-field direction stays pinned by the
        # field-for-field round trip above.
        self.repo.add(_call("llmc:legacy"))
        legacy = self.collection.docs["llmc:legacy"]
        legacy.pop("total_tokens")
        legacy.pop("latency_ms")

        [restored] = self.repo.list_for_project("p")

        self.assertEqual(restored.total_tokens, 0)
        self.assertEqual(restored.latency_ms, 0)


if __name__ == "__main__":
    unittest.main()
