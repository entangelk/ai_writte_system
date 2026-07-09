"""Unit tests for the candidate backfill script (b-2 / b-6 한계#1 fix).

Logic (needs_review filtering via list_needs_review_candidates, project
isolation, summary counts) against an in-memory analysis repo and the fake
vector / lexical backends; no Mongo/Chroma/ES. `from_uri` is patched because it
eagerly ensures Mongo indexes.
"""

from io import StringIO
import json
import unittest
from unittest import mock

from scripts import phase2b5_reindex_candidate
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import InMemoryAnalysisRepository

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
_REPO_PATH = (
    "services.application.app.analysis.mongo_repository."
    "MongoAnalysisRepository.from_uri"
)


def _candidate(
    candidate_id,
    *,
    project_id="project-1",
    status=AnalysisCandidateStatus.NEEDS_REVIEW,
):
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id="job-1",
        task_id="task-1",
        candidate_type=CHARACTER,
        action=AnalysisCandidateAction.CREATE,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload={"name": "Ariel", "observation": "brave"},
    )


def _seeded_repo():
    repo = InMemoryAnalysisRepository()
    repo.put_candidate(_candidate("c1"), logical_key="lk-1")
    # A different project's needs_review candidate must not leak into
    # project-1's backfill.
    repo.put_candidate(
        _candidate("c2", project_id="project-2"), logical_key="lk-2"
    )
    return repo


class RunReindexTest(unittest.TestCase):
    def test_reindexes_only_project_needs_review(self):
        # Under-strict guard: list_needs_review_candidates already pins
        # needs_review, so a non-needs_review status (Phase 6, not yet) would be
        # excluded — count stays at project-1's single needs_review candidate.
        # Over-strict guard: dropping the lexical leg (or the vector leg) would
        # drop the matching *_records_written to 0. Project isolation: c2
        # (project-2) must not leak into project-1's backfill.
        args = phase2b5_reindex_candidate.parse_args(
            ["--project-id", "project-1", "--mongo-uri", "mongodb://x", "--mongo-db", "db"]
        )
        with mock.patch.dict(
            phase2b5_reindex_candidate.os.environ, {}, clear=True
        ), mock.patch(_REPO_PATH, return_value=_seeded_repo()):
            summary = phase2b5_reindex_candidate.run_reindex(args)
        self.assertEqual(summary["project_id"], "project-1")
        self.assertEqual(summary["vector_backend"], "in_memory_fake")
        self.assertEqual(summary["lexical_backend"], "in_memory_fake")
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["vector_records_written"], 1)
        self.assertEqual(summary["lexical_records_written"], 1)

    def test_requires_mongo_uri(self):
        args = phase2b5_reindex_candidate.parse_args(
            ["--project-id", "p", "--mongo-uri", ""]
        )
        with self.assertRaises(ValueError):
            phase2b5_reindex_candidate.run_reindex(args)


class MainTest(unittest.TestCase):
    def test_main_prints_summary(self):
        def fake_run(args):
            self.assertEqual(args.project_id, "p1")
            return {
                "project_id": "p1",
                "vector_backend": "chroma",
                "lexical_backend": "elasticsearch",
                "candidate_count": 3,
                "vector_records_written": 3,
                "lexical_records_written": 3,
            }

        stdout = StringIO()
        code = phase2b5_reindex_candidate.main(
            ["--project-id", "p1", "--mongo-uri", "mongodb://x"],
            run_reindex_fn=fake_run,
            stdout=stdout,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["vector_records_written"], 3)

    def test_main_reports_usage_error(self):
        stderr = StringIO()
        code = phase2b5_reindex_candidate.main(
            ["--project-id", "p1"],
            run_reindex_fn=lambda args: (_ for _ in ()).throw(
                ValueError("boom")
            ),
            stderr=stderr,
        )
        self.assertEqual(code, 2)
        self.assertIn("boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
