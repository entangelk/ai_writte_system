"""Unit tests for Analysis MongoDB index setup."""

import unittest

try:
    from pymongo.errors import OperationFailure

    from services.application.app.analysis.mongo_repository import (
        MongoAnalysisRepository,
        MongoAnalysisRepositorySetupError,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    OperationFailure = Exception
    MongoAnalysisRepository = None
    MongoAnalysisRepositorySetupError = RuntimeError
    _PYMONGO_AVAILABLE = False


class _FakeCollection:
    def __init__(self, *, fail_on_name: str | None = None) -> None:
        self.fail_on_name = fail_on_name
        self.calls = []

    def create_index(self, keys, **kwargs):
        self.calls.append((list(keys), dict(kwargs)))
        if kwargs.get("name") == self.fail_on_name:
            raise OperationFailure("conflicting index spec")
        return kwargs.get("name")


def _repo_with_indexes(*, fail_on_name: str | None = None):
    repo = object.__new__(MongoAnalysisRepository)
    repo._jobs = _FakeCollection(fail_on_name=fail_on_name)
    repo._tasks = _FakeCollection(fail_on_name=fail_on_name)
    repo._candidates = _FakeCollection(fail_on_name=fail_on_name)
    return repo


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class MongoAnalysisIndexSetupTests(unittest.TestCase):
    def test_ensure_indexes_creates_required_absent_indexes(self):
        """Under-strict guard: every analysis idempotency index is requested."""

        repo = _repo_with_indexes()

        repo.ensure_indexes()

        self.assertEqual(
            repo._jobs.calls,
            [
                (
                    [
                        ("project_id", 1),
                        ("snapshot_id", 1),
                        ("idempotency_key", 1),
                    ],
                    {"unique": True, "name": "uniq_analysis_job_request"},
                )
            ],
        )
        self.assertEqual(
            repo._tasks.calls,
            [
                (
                    [
                        ("project_id", 1),
                        ("job_id", 1),
                        ("candidate_type", 1),
                    ],
                    {"unique": True, "name": "uniq_analysis_task_request"},
                )
            ],
        )
        self.assertEqual(
            repo._candidates.calls,
            [
                (
                    [
                        ("project_id", 1),
                        ("task_id", 1),
                        ("logical_key", 1),
                    ],
                    {"unique": True, "name": "uniq_analysis_candidate_request"},
                ),
                (
                    [("project_id", 1), ("job_id", 1)],
                    {"name": "analysis_candidates_by_job"},
                ),
            ],
        )

    def test_conflicting_index_failure_is_stable_setup_error(self):
        """Over-strict guard: setup failures must not look like write failures."""

        repo = _repo_with_indexes(fail_on_name="uniq_analysis_candidate_request")

        with self.assertRaises(MongoAnalysisRepositorySetupError) as raised:
            repo.ensure_indexes()

        self.assertIsInstance(raised.exception.__cause__, OperationFailure)


if __name__ == "__main__":
    unittest.main()
