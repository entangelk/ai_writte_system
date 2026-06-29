import unittest

from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import (
    AnalysisError,
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
)


def _service():
    repo = InMemoryAnalysisRepository()
    return AnalysisService(repo), repo


class AnalysisJobAndTaskTest(unittest.TestCase):
    def test_create_job_replays_same_request_without_duplicate(self):
        service, repo = _service()

        first = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        )
        replay = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.job, first.job)
        self.assertEqual(len(repo.jobs), 1)

    def test_distinct_job_request_creates_new_job(self):
        service, repo = _service()

        first = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        )
        second = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-2",
        )

        self.assertNotEqual(second.job.id, first.job.id)
        self.assertEqual(len(repo.jobs), 2)

    def test_missing_job_idempotency_key_is_rejected(self):
        service, _repo = _service()

        with self.assertRaises(AnalysisError):
            service.create_job(
                project_id="project-1",
                snapshot_id="snapshot-1",
                idempotency_key="",
            )

    def test_task_creation_enforces_project_isolation(self):
        service, _repo = _service()
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        with self.assertRaises(AnalysisNotFound):
            service.create_task(
                project_id="project-2",
                job_id=job.id,
                candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            )

    def test_all_phase2a_candidate_types_can_create_tasks(self):
        service, _repo = _service()
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        tasks = [
            service.create_task(
                project_id="project-1",
                job_id=job.id,
                candidate_type=candidate_type,
            )
            for candidate_type in AnalysisCandidateType
        ]

        self.assertEqual(
            [task.candidate_type for task in tasks],
            [
                AnalysisCandidateType.CHARACTER_OBSERVATION,
                AnalysisCandidateType.EVENT_OBSERVATION,
                AnalysisCandidateType.OPEN_QUESTION_OBSERVATION,
            ],
        )

    def test_unknown_candidate_type_is_rejected(self):
        service, _repo = _service()
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job

        with self.assertRaises(InvalidAnalysisCandidate):
            service.create_task(
                project_id="project-1",
                job_id=job.id,
                candidate_type="location_observation",
            )


class AnalysisCandidateTest(unittest.TestCase):
    def test_record_candidate_locks_phase2a_literals_and_needs_review(self):
        service, _repo = _service()
        task = self._task(service)

        result = service.record_candidate(
            project_id="project-1",
            task_id=task.id,
            logical_key="character:min-a",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=1.0,
            source_ref_ids=("source-ref-1",),
            payload={"name": "민아"},
        )

        candidate = result.candidate
        self.assertFalse(result.idempotent_replay)
        self.assertEqual(candidate.candidate_type, task.candidate_type)
        self.assertEqual(candidate.action, AnalysisCandidateAction.CREATE)
        self.assertEqual(candidate.status, AnalysisCandidateStatus.NEEDS_REVIEW)
        self.assertEqual(candidate.provenance, AnalysisProvenance.SOURCE_OBSERVED)
        self.assertEqual(candidate.confidence, 1.0)
        self.assertEqual(candidate.source_ref_ids, ("source-ref-1",))
        self.assertEqual(candidate.payload["name"], "민아")

    def test_same_task_retry_replays_logical_candidate_without_duplicate(self):
        service, repo = _service()
        task = self._task(service)

        first = self._record(
            service,
            task_id=task.id,
            logical_key="character:min-a",
            payload={"name": "민아"},
        )
        replay = self._record(
            service,
            task_id=task.id,
            logical_key="character:min-a",
            payload={"name": "retry body must not replace candidate"},
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.candidate.id, first.candidate.id)
        self.assertEqual(replay.candidate.payload["name"], "민아")
        self.assertEqual(len(repo.candidates), 1)

    def test_same_source_span_can_support_different_logical_candidates(self):
        service, repo = _service()
        task = self._task(service)

        first = self._record(
            service,
            task_id=task.id,
            logical_key="character:min-a",
            source_ref_ids=("source-ref-shared",),
        )
        second = self._record(
            service,
            task_id=task.id,
            logical_key="character:letter-sender",
            source_ref_ids=("source-ref-shared",),
        )

        self.assertNotEqual(second.candidate.id, first.candidate.id)
        self.assertEqual(len(repo.candidates), 2)

    def test_cross_project_candidate_access_is_not_listed(self):
        service, _repo = _service()
        task = self._task(service)
        self._record(service, task_id=task.id, logical_key="character:min-a")

        with self.assertRaises(AnalysisNotFound):
            service.list_candidates(project_id="project-2", job_id=task.job_id)

    def test_candidate_type_must_match_task(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            service.record_candidate(
                project_id="project-1",
                task_id=task.id,
                logical_key="event:letter",
                candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
                action=AnalysisCandidateAction.CREATE,
                provenance=AnalysisProvenance.SOURCE_OBSERVED,
                confidence=0.8,
                source_ref_ids=("source-ref-1",),
                payload={"event": "편지를 발견함"},
            )

    def test_confidence_range_allows_zero_and_one_but_rejects_out_of_range(self):
        service, _repo = _service()
        task = self._task(service)

        zero = self._record(
            service,
            task_id=task.id,
            logical_key="character:low-confidence",
            confidence=0.0,
        )
        one = self._record(
            service,
            task_id=task.id,
            logical_key="character:high-confidence",
            confidence=1.0,
        )

        self.assertEqual(zero.candidate.confidence, 0.0)
        self.assertEqual(one.candidate.confidence, 1.0)
        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:too-low",
                confidence=-0.01,
            )
        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:too-high",
                confidence=1.01,
            )

    def test_confidence_rejects_bool_and_non_number(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:bool-confidence",
                confidence=True,
            )
        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:string-confidence",
                confidence="0.8",
            )

    def test_confidence_rejects_nan(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:nan-confidence",
                confidence=float("nan"),
            )

    def test_source_ref_ids_are_required_but_not_deduped_as_candidate_identity(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(
                service,
                task_id=task.id,
                logical_key="character:no-source",
                source_ref_ids=(),
            )

    def test_action_other_than_create_is_rejected(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            service.record_candidate(
                project_id="project-1",
                task_id=task.id,
                logical_key="character:update",
                candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                action="update",
                provenance=AnalysisProvenance.AI_INFERRED,
                confidence=0.8,
                source_ref_ids=("source-ref-1",),
                payload={"name": "민아"},
            )

    def test_logical_key_must_be_non_empty_string(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(service, task_id=task.id, logical_key="")
        with self.assertRaises(InvalidAnalysisCandidate):
            self._record(service, task_id=task.id, logical_key=123)

    def test_user_declared_provenance_is_rejected_until_writingbrief_exists(self):
        service, _repo = _service()
        task = self._task(service)

        with self.assertRaises(InvalidAnalysisCandidate):
            service.record_candidate(
                project_id="project-1",
                task_id=task.id,
                logical_key="character:user-declared",
                candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                action=AnalysisCandidateAction.CREATE,
                provenance="user_declared",
                confidence=0.8,
                source_ref_ids=("source-ref-1",),
                payload={"name": "민아"},
            )

    def _task(self, service: AnalysisService):
        job = service.create_job(
            project_id="project-1",
            snapshot_id="snapshot-1",
            idempotency_key="analysis-run-1",
        ).job
        return service.create_task(
            project_id="project-1",
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )

    def _record(
        self,
        service: AnalysisService,
        *,
        task_id: str,
        logical_key: str,
        confidence=0.8,
        source_ref_ids=("source-ref-1",),
        payload=None,
    ):
        return service.record_candidate(
            project_id="project-1",
            task_id=task_id,
            logical_key=logical_key,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.AI_INFERRED,
            confidence=confidence,
            source_ref_ids=source_ref_ids,
            payload=payload or {"name": "민아"},
        )
