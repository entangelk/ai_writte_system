"""Unit tests for Core SOT MongoDB index setup.

These tests do not require a running MongoDB. They pin the adapter's required
index calls and the stable setup error raised when MongoDB rejects a conflicting
pre-existing index.
"""

import unittest

try:
    from pymongo.errors import OperationFailure

    from services.application.app.core_sot.mongo_repository import (
        MongoCoreSotRepository,
        MongoRepositorySetupError,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    OperationFailure = Exception
    MongoCoreSotRepository = None
    MongoRepositorySetupError = RuntimeError
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
    repo = object.__new__(MongoCoreSotRepository)
    repo._versions = _FakeCollection(fail_on_name=fail_on_name)
    repo._blocks = _FakeCollection(fail_on_name=fail_on_name)
    repo._source_refs = _FakeCollection(fail_on_name=fail_on_name)
    return repo


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class MongoIndexSetupTests(unittest.TestCase):
    def test_ensure_indexes_creates_required_absent_indexes(self):
        """Under-strict guard: every required Core SOT index must be requested."""

        repo = _repo_with_indexes()

        repo.ensure_indexes()

        self.assertEqual(
            repo._versions.calls,
            [
                (
                    [
                        ("project_id", 1),
                        ("draft_id", 1),
                        ("idempotency_key", 1),
                    ],
                    {"unique": True, "name": "uniq_save_request"},
                )
            ],
        )
        self.assertEqual(
            repo._blocks.calls,
            [
                (
                    [("snapshot_id", 1), ("block_index", 1)],
                    {"name": "blocks_by_snapshot"},
                )
            ],
        )
        self.assertEqual(
            repo._source_refs.calls,
            [
                (
                    [("project_id", 1), ("snapshot_id", 1)],
                    {"name": "source_refs_by_snapshot"},
                )
            ],
        )

    def test_conflicting_index_failure_is_stable_setup_error(self):
        """Over-strict guard: a conflicting index must not look like save logic."""

        repo = _repo_with_indexes(fail_on_name="uniq_save_request")

        with self.assertRaises(MongoRepositorySetupError) as raised:
            repo.ensure_indexes()

        self.assertIsInstance(raised.exception.__cause__, OperationFailure)


if __name__ == "__main__":
    unittest.main()
