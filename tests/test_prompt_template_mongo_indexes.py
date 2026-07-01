"""Unit tests for prompt template MongoDB index setup."""

import unittest

try:
    from pymongo.errors import OperationFailure

    from services.application.app.analysis.prompt_template_mongo_repository import (
        MongoPromptTemplateRepository,
        MongoPromptTemplateRepositorySetupError,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    OperationFailure = Exception
    MongoPromptTemplateRepository = None
    MongoPromptTemplateRepositorySetupError = RuntimeError
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
    repo = object.__new__(MongoPromptTemplateRepository)
    repo._templates = _FakeCollection(fail_on_name=fail_on_name)
    return repo


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class MongoPromptTemplateIndexSetupTests(unittest.TestCase):
    def test_ensure_indexes_creates_required_absent_indexes(self):
        """Under-strict guard: template version uniqueness must be requested."""

        repo = _repo_with_indexes()

        repo.ensure_indexes()

        self.assertEqual(
            repo._templates.calls,
            [
                (
                    [("task_type", 1), ("version", 1)],
                    {"unique": True, "name": "uniq_prompt_template_version"},
                )
            ],
        )

    def test_conflicting_index_failure_is_stable_setup_error(self):
        """Over-strict guard: setup failure is not a template conflict."""

        repo = _repo_with_indexes(fail_on_name="uniq_prompt_template_version")

        with self.assertRaises(MongoPromptTemplateRepositorySetupError) as raised:
            repo.ensure_indexes()

        self.assertIsInstance(raised.exception.__cause__, OperationFailure)


if __name__ == "__main__":
    unittest.main()
