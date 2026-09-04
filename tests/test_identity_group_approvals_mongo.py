"""정체성 그룹 승인 진행 저장(Slice 5) — Mongo 어댑터 round-trip.

선례(``test_identity_groups_mongo.py``)를 따르는 fake-collection round-trip이
표준 suite에서 ``_doc``↔모델 필드 드리프트를 잡고, test-mongo(rs-test)가 있으면
실 Mongo round-trip이 같은 계약을 잰다.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    from services.application.app.analysis.identity_group_approvals_mongo import (
        MongoCandidateIdentityGroupApprovalRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover - test shell without pymongo
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    MongoCandidateIdentityGroupApprovalRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.analysis.identity_group_approvals import (
    CandidateIdentityGroupApproval,
    CandidateIdentityGroupApprovalService,
    GroupApprovalStep,
    GroupApprovalStepStatus,
)

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


class _Collection:
    def __init__(self):
        self.docs: list[dict] = []
        self.indexes: list[tuple[list, dict]] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def _matches(self, doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    def replace_one(self, query, doc, upsert=False):
        assert upsert, "adapter must upsert (idempotent writes)"
        for i, existing in enumerate(self.docs):
            if self._matches(existing, query):
                self.docs[i] = dict(doc)
                return
        self.docs.append(dict(doc))

    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def delete_many(self, query):
        kept = [doc for doc in self.docs if not self._matches(doc, query)]
        removed = len(self.docs) - len(kept)
        self.docs = kept
        return removed


class _Database:
    def __init__(self, collections: dict[str, _Collection]):
        self._collections = collections

    def __getitem__(self, name):
        return self._collections[name]


class _Client:
    def __init__(self, collections):
        self.database = _Database(collections)

    def __getitem__(self, _name):
        return self.database


def _approval(group_id="cig:a", project="p1"):
    return CandidateIdentityGroupApproval(
        group_id=group_id, project_id=project, expected_revision=2,
        canonical_memory_id="mem:1",
        steps=(
            GroupApprovalStep(
                candidate_id="cand:a", status=GroupApprovalStepStatus.APPLIED,
                action="create", memory_id="mem:1", version=1, error=None,
            ),
            GroupApprovalStep(
                candidate_id="cand:b", status=GroupApprovalStepStatus.FAILED,
                action=None, memory_id=None, version=None,
                error="ProviderError",
            ),
            GroupApprovalStep(
                candidate_id="cand:c", status=GroupApprovalStepStatus.CONFLICT,
                action="conflict", memory_id="mem:1", version=1, error=None,
            ),
        ),
        created_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 9, 4, 10, 5, tzinfo=UTC),
    )


class MongoCandidateIdentityGroupApprovalRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.approvals = _Collection()
        self.repo = MongoCandidateIdentityGroupApprovalRepository(
            _Client({"candidate_identity_group_approvals": self.approvals}),
            db_name="test",
        )

    def test_installs_index_on_project_axis(self):
        self.assertEqual(
            self.approvals.indexes,
            [(
                [("project_id", 1)],
                {"name": "candidate_identity_group_approvals_by_project"},
            )],
        )

    def test_round_trip_field_for_field(self):
        approval = _approval()
        self.repo.save(approval)

        self.assertEqual(self.repo.get("p1", "cig:a"), approval)
        self.assertIsNone(self.repo.get("p2", "cig:a"))
        self.assertIsNone(self.repo.get("p1", "cig:other"))

    def test_save_is_an_idempotent_upsert_per_group(self):
        self.repo.save(_approval())
        self.repo.save(_approval())

        self.assertEqual(len(self.approvals.docs), 1)

    def test_purge_project_removes_only_that_project(self):
        self.repo.save(_approval())
        self.repo.save(_approval("cig:b", project="p2"))

        self.repo.purge_project("p1")

        self.assertEqual(len(self.approvals.docs), 1)
        self.assertIsNone(self.repo.get("p1", "cig:a"))
        self.assertIsNotNone(self.repo.get("p2", "cig:b"))


# --- 실 Mongo round-trip (test-mongo 있을 때만) ------------------------------

_MONGO_AVAILABLE = False
try:
    if _PYMONGO_AVAILABLE:
        _probe = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        _probe.admin.command("ping")
        _probe.close()
        _MONGO_AVAILABLE = True
except (ConnectionFailure, PyMongoError):  # pragma: no cover
    pass


@unittest.skipUnless(_MONGO_AVAILABLE, "test-mongo (rs-test) not reachable")
class MongoCandidateIdentityGroupApprovalLiveRoundTripTest(unittest.TestCase):
    """같은 service 계약을 실 Mongo에서 잰다 — naive datetime 읽기 경계(_aware)."""

    def setUp(self):
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"identity_group_approvals_test_{uuid.uuid4().hex}"
        self.repo = MongoCandidateIdentityGroupApprovalRepository(
            self._client, db_name=self._db_name
        )
        self.service = CandidateIdentityGroupApprovalService(self.repo)

    def tearDown(self):
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_round_trip_isolation_and_purge(self):
        stored = self.service.save(_approval())
        self.service.save(_approval("cig:b", project="p2"))

        self.assertEqual(self.service.get("p1", "cig:a"), stored)
        self.assertIsNone(self.service.get("p2", "cig:a"))

        self.service.purge_project("p1")

        self.assertIsNone(self.service.get("p1", "cig:a"))
        self.assertIsNotNone(self.service.get("p2", "cig:b"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
