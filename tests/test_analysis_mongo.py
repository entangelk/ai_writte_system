"""Live MongoDB integration tests for the Phase 2A analysis adapter."""

import os
import unittest
import uuid

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError

    from services.application.app.analysis.mongo_repository import (
        DuplicateAnalysisCandidateRequest,
        MongoAnalysisRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    ConnectionFailure = OperationFailure = PyMongoError = Exception
    DuplicateAnalysisCandidateRequest = RuntimeError
    MongoAnalysisRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    AnalysisProvenance,
)
from services.application.app.analysis.service import AnalysisService

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


def _probe_mongo() -> tuple[bool, bool]:
    """Return ``(available, transactions_supported)`` for the test deployment."""

    if not _PYMONGO_AVAILABLE:
        return False, False
    try:
        client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        client.admin.command("ping")
    except (ConnectionFailure, PyMongoError):
        return False, False

    txn_supported = False
    probe_db = f"analysis_probe_{uuid.uuid4().hex}"
    try:
        with client.start_session() as session:
            with session.start_transaction():
                client[probe_db]["probe"].insert_one({"_id": "x"}, session=session)
        txn_supported = True
    except OperationFailure:
        txn_supported = False
    finally:
        try:
            client.drop_database(probe_db)
        except PyMongoError:
            client.close()
            return False, False
        client.close()
    return True, txn_supported


_MONGO_AVAILABLE, _TXN_SUPPORTED = _probe_mongo()


class _MongoAnalysisContractMixin:
    use_transactions = False

    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"analysis_test_{uuid.uuid4().hex}"
        self.repo = MongoAnalysisRepository(
            self._client,
            db_name=self._db_name,
            use_transactions=self.use_transactions,
        )
        self.service = AnalysisService(self.repo)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_analysis_state_round_trips_through_fresh_service(self):
        job = self.service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        task = self.service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )

        result = self.service.record_candidate(
            project_id="project-1",
            task_id=task.id,
            logical_key="character:min-a",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.8,
            source_ref_ids=("source-ref-1",),
            payload={"name": "민아", "observation": "민아가 편지를 발견했다."},
        )

        reread = AnalysisService(self.repo)
        self.assertEqual(
            reread.list_candidates(project_id="project-1", job_id=job.id),
            (result.candidate,),
        )
        self.assertEqual(self.repo.get_job(job.id), job)
        self.assertEqual(self.repo.get_task(task.id), task)
        self.assertEqual(self.repo.get_candidate(result.candidate.id), result.candidate)

    def test_idempotent_replay_returns_same_job_task_and_candidate(self):
        job = self.service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        replay_job = self.service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        )
        task = self.service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        )
        replay_task = self.service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        )
        first = self.service.record_candidate(
            project_id="project-1",
            task_id=task.id,
            logical_key="event:letter",
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.8,
            source_ref_ids=("source-ref-1",),
            payload={"event": "민아가 편지를 발견했다."},
        )
        replay = self.service.record_candidate(
            project_id="project-1",
            task_id=task.id,
            logical_key="event:letter",
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.8,
            source_ref_ids=("source-ref-1",),
            payload={"event": "retry body must not duplicate"},
        )

        self.assertTrue(replay_job.idempotent_replay)
        self.assertEqual(replay_job.job.id, job.id)
        self.assertEqual(replay_task.id, task.id)
        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.candidate.id, first.candidate.id)
        self.assertEqual(
            len(self.repo.list_candidates_for_job("project-1", job.id)),
            1,
        )

    def test_job_state_round_trips_and_terminal_replay(self):
        job = self.service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        self.assertEqual(job.status, AnalysisJobStatus.PENDING)

        self.service.mark_job_running(project_id="project-1", job_id=job.id)
        self.service.mark_job_failed(
            project_id="project-1",
            job_id=job.id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail="gateway timeout",
        )

        # Fresh repository read-back: the persisted job reconstructs its terminal
        # status and failure fields (update_job + _job_doc/_to_job round-trip).
        persisted = MongoAnalysisRepository(
            self._client,
            db_name=self._db_name,
            use_transactions=self.use_transactions,
        ).get_job(job.id)
        self.assertEqual(persisted.status, AnalysisJobStatus.FAILED)
        self.assertEqual(
            persisted.failure_reason, AnalysisJobFailureReason.PROVIDER_ERROR
        )
        self.assertEqual(persisted.failure_detail, "gateway timeout")

        # Terminal job is returned as an idempotent replay, never re-run.
        replay = AnalysisService(self.repo).create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        )
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.job.id, job.id)
        self.assertEqual(replay.job.status, AnalysisJobStatus.FAILED)
        self.assertEqual(
            replay.job.failure_reason, AnalysisJobFailureReason.PROVIDER_ERROR
        )

    def test_candidate_batch_duplicate_rolls_back_partial_write(self):
        job = self.service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        task = self.service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        )
        committed = _candidate(
            candidate_id="committed-candidate",
            job_id=job.id,
            task_id=task.id,
            payload={"event": "committed"},
        )
        self.repo.put_candidate(committed, logical_key="event:committed")

        should_rollback = _candidate(
            candidate_id="should-rollback",
            job_id=job.id,
            task_id=task.id,
            payload={"event": "should rollback"},
        )
        duplicate = _candidate(
            candidate_id="duplicate-candidate",
            job_id=job.id,
            task_id=task.id,
            payload={"event": "duplicate"},
        )

        with self.assertRaises(DuplicateAnalysisCandidateRequest):
            self.repo.put_candidates(
                (
                    (should_rollback, "event:new"),
                    (duplicate, "event:committed"),
                )
            )

        self.assertIsNone(self.repo.get_candidate("should-rollback"))
        self.assertEqual(self.repo.get_candidate("committed-candidate"), committed)
        self.assertEqual(
            self.repo.list_candidates_for_job("project-1", job.id),
            (committed,),
        )


@unittest.skipUnless(_MONGO_AVAILABLE, "no MongoDB reachable for integration tests")
class FallbackMongoAnalysisTest(_MongoAnalysisContractMixin, unittest.TestCase):
    use_transactions = False


@unittest.skipUnless(
    _MONGO_AVAILABLE and _TXN_SUPPORTED,
    "MongoDB deployment does not support transactions (needs a replica set)",
)
class TransactionMongoAnalysisTest(_MongoAnalysisContractMixin, unittest.TestCase):
    use_transactions = True


def _candidate(
    *, candidate_id: str, job_id: str, task_id: str, payload: dict
) -> AnalysisCandidate:
    return AnalysisCandidate(
        id=candidate_id,
        project_id="project-1",
        job_id=job_id,
        task_id=task_id,
        candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.8,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    )


if __name__ == "__main__":
    unittest.main()
