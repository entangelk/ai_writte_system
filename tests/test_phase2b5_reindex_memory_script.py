"""Unit tests for the Phase 2B.5 memory backfill script.

Logic (canonical filtering, summary counts) against an in-memory memory repo and
the fake vector backend; no Mongo/Chroma. `from_uri` is patched because it eagerly
ensures Mongo indexes.
"""

from io import StringIO
import json
import unittest
from unittest import mock

from scripts import phase2b5_reindex_memory
from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import InMemoryMemoryRepository


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
_REPO_PATH = (
    "services.application.app.memory.mongo_repository."
    "MongoMemoryRepository.from_uri"
)


def _entry(memory_id, *, status, candidate_id, project_id="project-1"):
    return MemoryEntry(
        id=memory_id,
        project_id=project_id,
        memory_type=CHARACTER,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("s1",),
        payload={"name": "Ariel", "observation": "brave"},
        version=1,
        analysis_job_id="j",
        source_candidate_id=candidate_id,
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def _seeded_repo():
    repo = InMemoryMemoryRepository()
    repo.put_memory(_entry("m1", status=MemoryStatus.CANONICAL, candidate_id="c1"))
    repo.put_memory(
        _entry("m2", status=MemoryStatus.SUPERSEDED, candidate_id="c2")
    )
    # A different project's canonical must not leak into project-1's backfill.
    repo.put_memory(
        _entry(
            "m3",
            status=MemoryStatus.CANONICAL,
            candidate_id="c3",
            project_id="project-2",
        )
    )
    return repo


class RunReindexTest(unittest.TestCase):
    def test_reindexes_only_project_canonical(self):
        args = phase2b5_reindex_memory.parse_args(
            ["--project-id", "project-1", "--mongo-uri", "mongodb://x", "--mongo-db", "db"]
        )
        with mock.patch.dict(
            phase2b5_reindex_memory.os.environ, {}, clear=True
        ), mock.patch(_REPO_PATH, return_value=_seeded_repo()):
            summary = phase2b5_reindex_memory.run_reindex(args)
        self.assertEqual(summary["project_id"], "project-1")
        self.assertEqual(summary["memory_backend"], "in_memory_fake")
        self.assertEqual(summary["canonical_count"], 1)
        self.assertEqual(summary["records_written"], 1)

    def test_requires_mongo_uri(self):
        args = phase2b5_reindex_memory.parse_args(["--project-id", "p", "--mongo-uri", ""])
        with self.assertRaises(ValueError):
            phase2b5_reindex_memory.run_reindex(args)


class MainTest(unittest.TestCase):
    def test_main_prints_summary(self):
        def fake_run(args):
            self.assertEqual(args.project_id, "p1")
            return {
                "project_id": "p1",
                "memory_backend": "chroma",
                "canonical_count": 3,
                "records_written": 3,
            }

        stdout = StringIO()
        code = phase2b5_reindex_memory.main(
            ["--project-id", "p1", "--mongo-uri", "mongodb://x"],
            run_reindex_fn=fake_run,
            stdout=stdout,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["records_written"], 3)

    def test_main_reports_usage_error(self):
        stderr = StringIO()
        code = phase2b5_reindex_memory.main(
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
