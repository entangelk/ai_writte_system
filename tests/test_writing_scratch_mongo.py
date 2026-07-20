"""B-1 — deterministic fake round-trip for the scratch Mongo adapter.

Closes the blocking finding in `docs/verifications/2026-07-20/writing_scratch_recovery.md`:
`MongoWritingScratchRepository` had no coverage in the standard suite, so a
`_doc`↔`_entry` field drift (a renamed key, a dropped `intent`) would surface
only in durable mode (`CORE_SOT_MONGO_URI` set) — exactly where "잃지 않기" has
to hold. Mirrors `test_writing_loop_audit_mongo.py` / `test_gate_findings_mongo.py`:
a fake collection exercised without a live Mongo.

Unlike the append-only loop audit, this store is **mutable** — the delete paths
(`delete_for_draft` on accept/discard, `delete_ids` on cap trim) are part of the
contract and are pinned here, including the over-strict guard that an empty trim
must not issue a wildcard delete.
"""

import unittest
from datetime import UTC, datetime

from services.application.app.writing.scratch import ScratchCandidate
from services.application.app.writing.scratch_mongo import (
    MongoWritingScratchRepository,
)


class _Cursor(list):
    def sort(self, keys):
        docs = list(self)
        for key, direction in reversed(keys):
            docs.sort(key=lambda doc: doc[key], reverse=(direction == -1))
        return _Cursor(docs)


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


def _matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class _Collection:
    def __init__(self):
        self.docs = {}
        self.indexes = []
        self.delete_queries = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def insert_one(self, doc):
        self.docs[doc["_id"]] = dict(doc)

    def find(self, query):
        return _Cursor(
            doc for doc in self.docs.values() if _matches(doc, query)
        )

    def delete_many(self, query):
        self.delete_queries.append(query)
        victims = [
            doc["_id"] for doc in self.docs.values() if _matches(doc, query)
        ]
        for doc_id in victims:
            del self.docs[doc_id]
        return _DeleteResult(len(victims))


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "writing_drafts_scratch"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _entry(entry_id, *, project="p", draft="d", minute=0, text="초안",
           intent=None):
    return ScratchCandidate(
        id=entry_id, project_id=project, draft_id=draft, request_id="wr1",
        task_type="continue_scene", output_type="draft_patch",
        instruction="이어서 써줘", candidate_text=text,
        created_at=datetime(2026, 7, 20, 0, minute, tzinfo=UTC),
        intent=intent,
    )


class MongoWritingScratchRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoWritingScratchRepository(
            _Client(self.collection), db_name="test"
        )

    def test_installs_draft_created_index_with_stable_name(self):
        self.assertEqual(self.collection.indexes, [(
            [("project_id", 1), ("draft_id", 1), ("created_at", -1)],
            {"name": "writing_drafts_scratch_by_draft_created"},
        )])

    def test_add_and_list_round_trip_newest_first(self):
        earlier = _entry("wds:a", minute=1, text="오래된")
        later = _entry("wds:z", minute=5, text="최신")
        with_intent = _entry("wds:i", minute=3, intent="append_current")
        other_draft = _entry("wds:d2", draft="d2", minute=9)
        other_project = _entry("wds:p2", project="p2", minute=9)
        for entry in (earlier, later, with_intent, other_draft, other_project):
            self.repo.add(entry)

        listed = self.repo.list_for_draft("p", "d")
        # Field-for-field round trip (catches _doc↔_entry drift), newest first.
        self.assertEqual(listed, (later, with_intent, earlier))
        # Keyed by BOTH project and draft — neither neighbour leaks in.
        self.assertEqual(
            tuple(e.id for e in self.repo.list_for_draft("p", "d2")),
            ("wds:d2",),
        )
        self.assertEqual(
            tuple(e.id for e in self.repo.list_for_draft("p2", "d")),
            ("wds:p2",),
        )

    def test_delete_for_draft_removes_only_that_draft(self):
        self.repo.add(_entry("wds:a"))
        self.repo.add(_entry("wds:b", minute=2))
        self.repo.add(_entry("wds:keep", draft="d2"))

        self.assertEqual(self.repo.delete_for_draft("p", "d"), 2)

        self.assertEqual(self.repo.list_for_draft("p", "d"), ())
        self.assertEqual(
            tuple(e.id for e in self.repo.list_for_draft("p", "d2")),
            ("wds:keep",),
        )

    def test_delete_ids_removes_named_entries_only(self):
        self.repo.add(_entry("wds:drop", minute=1))
        self.repo.add(_entry("wds:keep", minute=2))

        self.repo.delete_ids(("wds:drop",))

        self.assertEqual(
            tuple(e.id for e in self.repo.list_for_draft("p", "d")),
            ("wds:keep",),
        )

    def test_empty_delete_ids_is_a_no_op(self):
        # Over-strict: a trim with nothing to drop must not reach Mongo at all.
        # Without the guard the query would be {"_id": {"$in": []}} — harmless
        # today, but the assertion pins that no unfiltered delete is issued.
        self.repo.add(_entry("wds:a"))

        self.repo.delete_ids(())

        self.assertEqual(self.collection.delete_queries, [])
        self.assertEqual(len(self.repo.list_for_draft("p", "d")), 1)

    def test_legacy_doc_without_intent_reads_none(self):
        # Under-strict: a doc written before `intent` existed still loads. The
        # present-field direction stays pinned by the round-trip assertion above.
        self.repo.add(_entry("wds:legacy"))
        self.collection.docs["wds:legacy"].pop("intent")

        restored = self.repo.list_for_draft("p", "d")[0]

        self.assertIsNone(restored.intent)


if __name__ == "__main__":
    unittest.main()
