import unittest
from dataclasses import replace
from datetime import UTC, datetime

from services.application.app.context_search.gate_findings import (
    GateFindingStatus, StoredGateFinding,
)
from services.application.app.context_search.gate_findings_mongo import (
    MongoGateFindingRepository,
)


class _Cursor(list):
    def sort(self, key, _direction):
        return _Cursor(sorted(self, key=lambda doc: doc[key]))


class _Collection:
    def __init__(self):
        self.docs = {}
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def replace_one(self, query, doc, *, upsert):
        assert upsert
        self.docs[query["_id"]] = dict(doc)

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
        assert name == "gate_findings"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def finding(fid, *, project="p", status=GateFindingStatus.OPEN):
    return StoredGateFinding(
        id=fid, project_id=project, idempotency_key="key", ordinal=0,
        check="stale_item", detail="stale", status=status,
        query="continue", purpose="writing_context", needs=("current_scene",),
        pointer_ids=("snapshot-1",), request_fingerprint="a" * 64,
        result_fingerprint="b" * 64,
        created_at=datetime(2026, 7, 12, tzinfo=UTC),
    )


class MongoGateFindingRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoGateFindingRepository(_Client(self.collection), db_name="test")

    def test_installs_project_status_index_with_stable_name(self):
        self.assertEqual(self.collection.indexes, [(
            [("project_id", 1), ("status", 1)],
            {"name": "gate_findings_by_project_status"},
        )])

    def test_upsert_get_and_open_listing_round_trip(self):
        later_id = finding("gf:z")
        earlier_id = finding("gf:a")
        other_project = finding("gf:other", project="other")
        terminal = replace(finding("gf:closed"), status=GateFindingStatus.RESOLVED,
                           terminal_at=datetime(2026, 7, 13, tzinfo=UTC))
        for entry in (later_id, earlier_id, other_project, terminal):
            self.repo.upsert(entry)

        reread = self.repo.get(earlier_id.id)
        self.assertEqual(reread, earlier_id)
        self.assertEqual(
            tuple(entry.id for entry in self.repo.list_open("p")),
            ("gf:a", "gf:z"),
        )
