import unittest

from services.application.app.analysis.compare import CompareAction
from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
    ReviewQueueStatus,
    derive_review_queue_id,
)

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


def _service():
    return ReviewQueueService(InMemoryReviewQueueRepository())


def _enqueue(service, *, project_id="project-1", job_id="job-1", candidate_id="cand-1",
             action=CompareAction.CONFLICT, matched_memory_id="mem-1",
             rationale="duplicate canonical"):
    return service.enqueue(
        project_id=project_id,
        job_id=job_id,
        candidate_id=candidate_id,
        candidate_type=CHARACTER,
        action=action,
        matched_memory_id=matched_memory_id,
        rationale=rationale,
    )


class ReviewQueueEnqueueTest(unittest.TestCase):
    def test_enqueue_persists_open_entry_with_fields(self):
        service = _service()
        entry = _enqueue(service)
        self.assertEqual(entry.status, ReviewQueueStatus.OPEN)
        self.assertEqual(entry.action, CompareAction.CONFLICT)
        self.assertEqual(entry.candidate_id, "cand-1")
        self.assertEqual(entry.matched_memory_id, "mem-1")
        self.assertEqual(entry.rationale, "duplicate canonical")
        [listed] = service.list_open("project-1")
        self.assertEqual(listed, entry)

    def test_id_is_deterministic_from_project_job_candidate_action(self):
        entry = _enqueue(_service())
        self.assertEqual(
            entry.id,
            derive_review_queue_id(
                project_id="project-1",
                job_id="job-1",
                candidate_id="cand-1",
                action=CompareAction.CONFLICT,
            ),
        )


class ReviewQueueIdempotencyTest(unittest.TestCase):
    def test_reenqueue_same_conflict_upserts_not_duplicates(self):
        # D3: apply is idempotent — re-applying the same job's conflict must not
        # grow the queue. Re-fails if the id stops being deterministic.
        service = _service()
        first = _enqueue(service, rationale="v1")
        second = _enqueue(service, rationale="v2")
        self.assertEqual(first.id, second.id)
        entries = service.list_open("project-1")
        self.assertEqual(len(entries), 1)
        # latest write wins on upsert
        self.assertEqual(entries[0].rationale, "v2")

    def test_distinct_candidates_are_separate_entries(self):
        # Over-strict guard: different candidates must NOT collapse into one
        # entry (would silently drop conflicts).
        service = _service()
        _enqueue(service, candidate_id="cand-1")
        _enqueue(service, candidate_id="cand-2")
        self.assertEqual(len(service.list_open("project-1")), 2)


class ReviewQueueScopeTest(unittest.TestCase):
    def test_list_open_is_project_scoped(self):
        service = _service()
        _enqueue(service, project_id="project-1", candidate_id="a")
        _enqueue(service, project_id="project-2", candidate_id="b")
        self.assertEqual(len(service.list_open("project-1")), 1)
        self.assertEqual(len(service.list_open("project-2")), 1)
        self.assertEqual(len(service.list_open("project-3")), 0)


class ReviewQueueTransitionTest(unittest.TestCase):
    """Phase 6 (v1.6.61): open→resolved/dismissed candidate transitions."""

    def test_resolve_for_candidate_closes_open_entries(self):
        # under-strict: a resolved entry leaves the open list.
        service = _service()
        _enqueue(service, candidate_id="cand-1")
        [closed] = service.resolve_for_candidate(
            project_id="project-1", candidate_id="cand-1"
        )
        self.assertEqual(closed.status, ReviewQueueStatus.RESOLVED)
        self.assertEqual(service.list_open("project-1"), ())

    def test_dismiss_for_candidate_closes_open_entries(self):
        service = _service()
        _enqueue(service, candidate_id="cand-1")
        [closed] = service.dismiss_for_candidate(
            project_id="project-1", candidate_id="cand-1"
        )
        self.assertEqual(closed.status, ReviewQueueStatus.DISMISSED)
        self.assertEqual(service.list_open("project-1"), ())

    def test_transition_is_candidate_scoped(self):
        # over-strict: resolving one candidate must not touch another's entry.
        service = _service()
        _enqueue(service, candidate_id="cand-1")
        _enqueue(service, candidate_id="cand-2")
        service.resolve_for_candidate(project_id="project-1", candidate_id="cand-1")
        open_ids = {e.candidate_id for e in service.list_open("project-1")}
        self.assertEqual(open_ids, {"cand-2"})

    def test_transition_is_idempotent_noop_when_no_open_entries(self):
        # D4: a replay (nothing open) transitions nothing and does not error.
        service = _service()
        _enqueue(service, candidate_id="cand-1")
        service.resolve_for_candidate(project_id="project-1", candidate_id="cand-1")
        replay = service.resolve_for_candidate(
            project_id="project-1", candidate_id="cand-1"
        )
        self.assertEqual(replay, ())


if __name__ == "__main__":
    unittest.main()
