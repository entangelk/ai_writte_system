"""Live MongoDB integration tests for the Phase 2B.1 memory adapter."""

import os
import unittest
import uuid

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    from services.application.app.memory.mongo_repository import MongoMemoryRepository

    _PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    MongoMemoryRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.models import MemoryStatus, PromotionMode
from services.application.app.memory.service import MemoryService

_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


def _probe_mongo() -> bool:
    if not _PYMONGO_AVAILABLE:
        return False
    try:
        client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        client.admin.command("ping")
    except (ConnectionFailure, PyMongoError):
        return False
    client.close()
    return True


_MONGO_AVAILABLE = _probe_mongo()


def _candidate(*, candidate_id="candidate-1", confidence=0.8):
    return AnalysisCandidate(
        id=candidate_id,
        project_id="project-1",
        job_id="analysis-job-1",
        task_id="analysis-task-1",
        candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=confidence,
        source_ref_ids=("source-ref-1",),
        payload={"name": "민아", "observation": "민아가 편지를 발견했다."},
    )


@unittest.skipUnless(_MONGO_AVAILABLE, "requires a reachable MongoDB")
class MongoMemoryRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"memory_test_{uuid.uuid4().hex}"
        self.repo = MongoMemoryRepository(self._client, db_name=self._db_name)

    def tearDown(self) -> None:
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_promoted_memory_round_trips_through_fresh_service(self):
        service = MemoryService(self.repo, auto_promotion_threshold=0.5)
        candidate = _candidate(confidence=0.8)

        result = service.auto_promote_candidate(
            project_id="project-1", candidate=candidate
        )
        self.assertIsNotNone(result)

        reread = MemoryService(self.repo)
        fetched = reread.get_memory(
            project_id="project-1", memory_id=result.memory.id
        )
        self.assertEqual(fetched.status, MemoryStatus.CANONICAL)
        self.assertEqual(fetched.version, 1)
        self.assertEqual(fetched.promotion_mode, PromotionMode.AUTO_THRESHOLD)
        self.assertEqual(fetched.applied_threshold, 0.5)
        self.assertEqual(fetched.source_candidate_id, candidate.id)
        self.assertEqual(dict(fetched.payload), dict(candidate.payload))
        self.assertEqual(
            reread.list_memories(project_id="project-1"), (result.memory,)
        )

    def test_repeated_promotion_replays_via_find_without_second_write(self):
        # A fresh service shares no in-process state; idempotency is served by
        # the Mongo find_memory_by_candidate lookup, not a second insert.
        candidate = _candidate()
        first = MemoryService(self.repo).promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )
        replay = MemoryService(self.repo).promote_candidate(
            project_id="project-1", candidate=candidate, mode=PromotionMode.MANUAL
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.memory.id, first.memory.id)
        self.assertEqual(
            len(MemoryService(self.repo).list_memories(project_id="project-1")), 1
        )

    def test_versioned_update_round_trips_supersedes_and_status(self):
        # Phase 2B.4: a versioned update inserts a new canonical version and
        # supersedes the prior entry. A fresh service must read back the new
        # version's supersedes link and the prior entry's superseded status.
        prior_cand = _candidate(candidate_id="candidate-prior", confidence=0.5)
        prior = MemoryService(self.repo).promote_candidate(
            project_id="project-1", candidate=prior_cand, mode=PromotionMode.MANUAL
        ).memory

        update_cand = AnalysisCandidate(
            id="candidate-update",
            project_id="project-1",
            job_id="analysis-job-2",
            task_id="analysis-task-2",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            status=AnalysisCandidateStatus.NEEDS_REVIEW,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9,
            source_ref_ids=("source-ref-2",),
            payload={"name": "민아", "observation": "민아가 진실을 알았다."},
        )
        result = MemoryService(self.repo).record_updated_version(
            project_id="project-1",
            candidate=update_cand,
            target_memory_id=prior.id,
        )

        reread = MemoryService(self.repo)
        new_entry = reread.get_memory(
            project_id="project-1", memory_id=result.memory.id
        )
        self.assertEqual(new_entry.version, 2)
        self.assertEqual(new_entry.status, MemoryStatus.CANONICAL)
        self.assertEqual(new_entry.supersedes, prior.id)
        self.assertEqual(
            new_entry.source_ref_ids, ("source-ref-1", "source-ref-2")
        )
        old_entry = reread.get_memory(project_id="project-1", memory_id=prior.id)
        self.assertEqual(old_entry.status, MemoryStatus.SUPERSEDED)
        self.assertIsNone(old_entry.supersedes)

    def test_unique_index_rejects_second_promotion_of_same_candidate(self):
        # Directly exercise the race guard: a second insert for the same
        # (project_id, source_candidate_id) must surface DuplicatePromotionRequest
        # regardless of a differing memory id.
        from services.application.app.memory.models import MemoryEntry
        from services.application.app.memory.repository import (
            DuplicatePromotionRequest,
        )

        base = MemoryEntry(
            id="memory-a",
            project_id="project-1",
            memory_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            status=MemoryStatus.CANONICAL,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.8,
            source_ref_ids=("source-ref-1",),
            payload={"name": "민아", "observation": "x"},
            version=1,
            analysis_job_id="analysis-job-1",
            source_candidate_id="candidate-1",
            promotion_mode=PromotionMode.MANUAL,
            applied_threshold=None,
        )
        self.repo.put_memory(base)
        from dataclasses import replace

        with self.assertRaises(DuplicatePromotionRequest):
            self.repo.put_memory(replace(base, id="memory-b"))

    def test_purge_removes_all_project_memory_leaving_others(self):
        # D8-6b: project 의 memory 전부 파기(직접 project_id 스코프). 인접 project 유지.
        from services.application.app.memory.models import (
            MemoryEntry,
            MemoryStatus,
            PromotionMode,
        )
        from services.application.app.analysis.models import (
            AnalysisCandidateType,
            AnalysisProvenance,
        )

        def _entry(memory_id, project_id, candidate_id):
            return MemoryEntry(
                id=memory_id,
                project_id=project_id,
                memory_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                status=MemoryStatus.CANONICAL,
                provenance=AnalysisProvenance.SOURCE_OBSERVED,
                confidence=0.8,
                source_ref_ids=("source-ref-1",),
                payload={"name": "x", "observation": "y"},
                version=1,
                analysis_job_id="analysis-job-1",
                source_candidate_id=candidate_id,
                promotion_mode=PromotionMode.MANUAL,
                applied_threshold=None,
            )

        self.repo.put_memory(_entry("memory-1", "project-1", "candidate-1"))
        self.repo.put_memory(_entry("memory-2", "project-2", "candidate-2"))

        self.repo.purge_project("project-1")

        self.assertEqual(self.repo.list_memories_for_project("project-1"), ())
        self.assertEqual(len(self.repo.list_memories_for_project("project-2")), 1)


if __name__ == "__main__":
    unittest.main()
