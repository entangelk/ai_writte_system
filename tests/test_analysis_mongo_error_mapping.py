"""Unit tests for Analysis MongoDB write-error classification.

These lock the boundary between a duplicate-key write failure (which must be
surfaced as ``DuplicateAnalysisCandidateRequest``) and any other
``BulkWriteError`` (which must keep its original type so an infrastructure
failure is never mislabelled as a duplicate request).
"""

import contextlib
import unittest

try:
    from pymongo.errors import BulkWriteError

    from services.application.app.analysis.mongo_repository import (
        DuplicateAnalysisCandidateRequest,
        MongoAnalysisRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:
    BulkWriteError = Exception
    DuplicateAnalysisCandidateRequest = RuntimeError
    MongoAnalysisRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)

_DUPLICATE_CODE = 11000
_VALIDATION_CODE = 121


def _bulk_write_error(code: int) -> "BulkWriteError":
    return BulkWriteError(
        {
            "writeErrors": [{"index": 0, "code": code, "errmsg": "boom"}],
            "writeConcernErrors": [],
            "nInserted": 0,
            "nUpserted": 0,
            "nMatched": 0,
            "nModified": 0,
            "nRemoved": 0,
            "upserted": [],
        }
    )


class _FakeCandidates:
    def __init__(self, *, error: Exception) -> None:
        self._error = error
        self.inserted_ids: list[str] = []
        self.delete_calls: list[dict] = []

    def insert_many(self, docs, session=None):
        self.inserted_ids.extend(doc["_id"] for doc in docs)
        raise self._error

    def delete_many(self, flt, session=None):
        self.delete_calls.append(flt)


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def start_transaction(self):
        return contextlib.nullcontext()


class _FakeClient:
    def start_session(self):
        return _FakeSession()


def _candidate() -> AnalysisCandidate:
    return AnalysisCandidate(
        id="candidate-1",
        project_id="project-1",
        job_id="job-1",
        task_id="task-1",
        candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.8,
        source_ref_ids=("source-ref-1",),
        payload={"event": "민아가 편지를 발견했다."},
    )


def _repo(*, use_transactions: bool, error: Exception) -> "MongoAnalysisRepository":
    repo = object.__new__(MongoAnalysisRepository)
    repo._use_transactions = use_transactions
    repo._client = _FakeClient()
    repo._candidates = _FakeCandidates(error=error)
    return repo


@unittest.skipUnless(_PYMONGO_AVAILABLE, "pymongo is not installed")
class AnalysisWriteErrorMappingTests(unittest.TestCase):
    def test_transactional_duplicate_key_maps_to_duplicate_request(self):
        """Under-strict guard: a duplicate-key bulk error is a duplicate request."""

        repo = _repo(use_transactions=True, error=_bulk_write_error(_DUPLICATE_CODE))

        with self.assertRaises(DuplicateAnalysisCandidateRequest):
            repo.put_candidate(_candidate(), logical_key="event:letter")

    def test_transactional_non_duplicate_bulk_error_is_reraised(self):
        """Over-strict guard: a non-duplicate bulk error keeps its original type."""

        original = _bulk_write_error(_VALIDATION_CODE)
        repo = _repo(use_transactions=True, error=original)

        with self.assertRaises(BulkWriteError) as raised:
            repo.put_candidate(_candidate(), logical_key="event:letter")
        self.assertIs(raised.exception, original)

    def test_fallback_duplicate_key_maps_and_cleans_up(self):
        """Under-strict guard: fallback duplicate maps and removes this attempt."""

        repo = _repo(use_transactions=False, error=_bulk_write_error(_DUPLICATE_CODE))

        with self.assertRaises(DuplicateAnalysisCandidateRequest):
            repo.put_candidate(_candidate(), logical_key="event:letter")
        self.assertEqual(
            repo._candidates.delete_calls,
            [{"_id": {"$in": ["candidate-1"]}}],
        )

    def test_fallback_non_duplicate_bulk_error_is_reraised_after_cleanup(self):
        """Over-strict guard: fallback infra error re-raises but still cleans up."""

        original = _bulk_write_error(_VALIDATION_CODE)
        repo = _repo(use_transactions=False, error=original)

        with self.assertRaises(BulkWriteError) as raised:
            repo.put_candidate(_candidate(), logical_key="event:letter")
        self.assertIs(raised.exception, original)
        self.assertEqual(
            repo._candidates.delete_calls,
            [{"_id": {"$in": ["candidate-1"]}}],
        )


if __name__ == "__main__":
    unittest.main()
