"""Deterministic fake round-trip + atomic claim for the generation job adapter.

Every new ``*_mongo.py`` carries a fake-collection round-trip in the standard
suite (precedent: ``test_writing_scratch_mongo.py`` / ``test_gate_findings_mongo
.py``) so a ``_doc``↔``_entry`` drift surfaces here, not only in durable mode.
This store adds the load-bearing ``claim_next`` (``find_one_and_update`` with a
lease), so the claim's atomicity contract is pinned against a fake too: oldest
PENDING first, lease-expired RUNNING reclaimable, fresh RUNNING skipped.
"""

import unittest
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from services.application.app.writing.generation_job import (
    WritingGenerationJob,
    WritingGenerationJobFailureReason,
    WritingGenerationJobStatus,
)
from services.application.app.writing.generation_job_mongo import (
    MongoWritingGenerationJobRepository,
)

_NOW = datetime(2026, 7, 21, tzinfo=UTC)


class _Cursor(list):
    def sort(self, keys):
        docs = list(self)
        for key, direction in reversed(keys):
            docs.sort(key=lambda doc: doc[key], reverse=(direction == -1))
        return _Cursor(docs)


def _matches(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in value):
                return False
        elif isinstance(value, dict) and "$lte" in value:
            dv = doc.get(key)
            if dv is None or dv > value["$lte"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class _Collection:
    def __init__(self):
        self.docs = {}
        self.unique_keys = []  # list of tuple-of-field-names

    def create_index(self, keys, *, name=None, unique=False):
        if unique:
            self.unique_keys.append(tuple(k for k, _ in keys))

    def _unique_violation(self, doc, *, ignore_id=None):
        for fields in self.unique_keys:
            signature = tuple(doc.get(f) for f in fields)
            for other in self.docs.values():
                if other["_id"] == doc["_id"] or other["_id"] == ignore_id:
                    continue
                if tuple(other.get(f) for f in fields) == signature:
                    return True
        return False

    def insert_one(self, doc):
        if doc["_id"] in self.docs or self._unique_violation(doc):
            raise DuplicateKeyError("duplicate")
        self.docs[doc["_id"]] = dict(doc)

    def replace_one(self, query, doc):
        [victim] = [d["_id"] for d in self.docs.values() if _matches(d, query)]
        self.docs[victim] = dict(doc)

    def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query):
        return _Cursor(dict(d) for d in self.docs.values() if _matches(d, query))

    def find_one_and_update(self, query, update, *, sort, return_document):
        matches = [d for d in self.docs.values() if _matches(d, query)]
        for key, direction in reversed(sort):
            matches.sort(key=lambda d: d[key], reverse=(direction == -1))
        if not matches:
            return None
        target = matches[0]
        target.update(update["$set"])
        return dict(target)


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "writing_generation_jobs"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _job(job_id, *, project="p", draft="d", request="wr1", minute=0,
         status=WritingGenerationJobStatus.PENDING, claimed_at=None,
         failure_reason=None, failure_detail=None, result_scratch_id=None):
    return WritingGenerationJob(
        id=job_id, project_id=project, draft_id=draft, request_id=request,
        task_type="continue_scene", instruction="이어서", draft_excerpt="앞",
        query=None, output_length="medium", max_output_tokens=2048,
        max_tokens=4096, version_id="v1",
        created_at=_NOW + timedelta(minutes=minute),
        status=status, claimed_at=claimed_at, failure_reason=failure_reason,
        failure_detail=failure_detail, result_scratch_id=result_scratch_id,
    )


class MongoWritingGenerationJobRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.collection = _Collection()
        self.repo = MongoWritingGenerationJobRepository(
            _Client(self.collection), db_name="test")

    def test_round_trip_preserves_all_fields_including_failure_enum(self):
        # Field-for-field round trip catches _doc↔_entry drift, including the
        # StrEnum status/failure_reason and the nullable claimed_at/result.
        failed = _job(
            "wgj:f", status=WritingGenerationJobStatus.FAILED,
            claimed_at=_NOW + timedelta(seconds=5),
            failure_reason=WritingGenerationJobFailureReason.PROVIDER_TIMEOUT,
            failure_detail="timed out")
        pending = _job("wgj:p", request="wr2", minute=1)
        self.repo.add(failed)
        self.repo.add(pending)
        self.assertEqual(self.repo.get("wgj:f"), failed)
        self.assertEqual(self.repo.get("wgj:p"), pending)

    def test_get_unknown_id_is_none(self):
        self.assertIsNone(self.repo.get("nope"))

    def test_duplicate_request_is_swallowed_not_raised(self):
        # The unique (project_id, request_id) index backstops enqueue dedup; a
        # second insert of the same request must not blow up or double-store.
        self.repo.add(_job("wgj:a", request="wr1"))
        self.repo.add(_job("wgj:b", request="wr1"))  # same (project, request)
        self.assertEqual(self.repo.get("wgj:b"), None)
        self.assertEqual(self.repo.find_request("p", "wr1"), "wgj:a")

    def test_find_request_returns_none_when_absent(self):
        self.assertIsNone(self.repo.find_request("p", "missing"))

    def test_claim_moves_oldest_pending_to_running(self):
        self.repo.add(_job("wgj:new", minute=5))
        self.repo.add(_job("wgj:old", request="wr2", minute=1))

        claimed = self.repo.claim_next(now=_NOW + timedelta(minutes=10),
                                       claim_timeout_seconds=600)

        self.assertEqual(claimed.id, "wgj:old")  # oldest created_at first
        self.assertEqual(claimed.status, WritingGenerationJobStatus.RUNNING)
        self.assertEqual(claimed.claimed_at, _NOW + timedelta(minutes=10))
        # persisted, not just returned
        self.assertEqual(self.repo.get("wgj:old").status,
                         WritingGenerationJobStatus.RUNNING)

    def test_claim_returns_none_when_nothing_claimable(self):
        self.repo.add(_job("wgj:done",
                           status=WritingGenerationJobStatus.SUCCEEDED))
        self.assertIsNone(self.repo.claim_next(
            now=_NOW + timedelta(minutes=10), claim_timeout_seconds=600))

    def test_claim_skips_fresh_running_but_reclaims_stale(self):
        claimed_at = _NOW
        self.repo.add(_job("wgj:run", status=WritingGenerationJobStatus.RUNNING,
                           claimed_at=claimed_at))
        # within lease → skipped
        self.assertIsNone(self.repo.claim_next(
            now=claimed_at + timedelta(seconds=300), claim_timeout_seconds=600))
        # past lease → reclaimed (stays RUNNING, re-stamped)
        reclaimed = self.repo.claim_next(
            now=claimed_at + timedelta(seconds=601), claim_timeout_seconds=600)
        self.assertEqual(reclaimed.id, "wgj:run")
        self.assertEqual(reclaimed.claimed_at, claimed_at + timedelta(seconds=601))

    def test_update_persists_terminal_state(self):
        from dataclasses import replace
        self.repo.add(_job("wgj:a"))
        done = replace(self.repo.get("wgj:a"),
                       status=WritingGenerationJobStatus.SUCCEEDED,
                       result_scratch_id="wds:9")
        self.repo.update(done)
        self.assertEqual(self.repo.get("wgj:a"), done)

    def test_list_for_draft_newest_first_isolated(self):
        self.repo.add(_job("wgj:1", draft="d1", request="wr1", minute=1))
        self.repo.add(_job("wgj:2", draft="d1", request="wr2", minute=2))
        self.repo.add(_job("wgj:3", draft="d2", request="wr3", minute=3))
        self.assertEqual(
            [j.id for j in self.repo.list_for_draft("p", "d1")],
            ["wgj:2", "wgj:1"])
        self.assertEqual(
            [j.id for j in self.repo.list_for_draft("p", "d2")],
            ["wgj:3"])


if __name__ == "__main__":
    unittest.main()
