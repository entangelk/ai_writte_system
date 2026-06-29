"""MongoDB adapter implementing the Phase 2A analysis repository contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import (
    BulkWriteError,
    DuplicateKeyError,
    OperationFailure,
    PyMongoError,
)

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisJob,
    AnalysisJobFailureReason,
    AnalysisJobStatus,
    AnalysisProvenance,
    AnalysisTask,
    immutable_payload,
)
from services.application.app.analysis.repository import (
    DuplicateAnalysisCandidateRequest,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

_DUPLICATE_KEY_CODE = 11000


def _is_duplicate_key_error(exc: PyMongoError) -> bool:
    """Return True only when ``exc`` is a duplicate-key write failure.

    ``insert_many`` surfaces a duplicate unique index hit as a ``BulkWriteError``
    whose ``writeErrors`` carry code ``11000``. Any other ``BulkWriteError``
    (e.g. document validation, write concern) must keep its original type so an
    infrastructure failure is never mislabelled as a duplicate request.
    """

    if isinstance(exc, DuplicateKeyError):
        return True
    if isinstance(exc, BulkWriteError):
        write_errors = (exc.details or {}).get("writeErrors", [])
        return bool(write_errors) and all(
            error.get("code") == _DUPLICATE_KEY_CODE for error in write_errors
        )
    return False


class MongoAnalysisRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required analysis indexes."""


class MongoAnalysisRepository:
    """``AnalysisRepository`` backed by MongoDB collections.

    Transaction mode is the normal runtime path. The non-transaction fallback is
    single-writer only, matching the Core SOT local/test fallback constraint.
    """

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> None:
        self._client = client
        self._db = client[db_name]
        self._use_transactions = use_transactions
        self._jobs = self._db["analysis_jobs"]
        self._tasks = self._db["analysis_tasks"]
        self._candidates = self._db["analysis_candidates"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> "MongoAnalysisRepository":
        return cls(
            MongoClient(uri),
            db_name=db_name,
            use_transactions=use_transactions,
        )

    def ensure_indexes(self) -> None:
        try:
            self._jobs.create_index(
                [
                    ("project_id", ASCENDING),
                    ("snapshot_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
                name="uniq_analysis_job_request",
            )
            self._tasks.create_index(
                [
                    ("project_id", ASCENDING),
                    ("job_id", ASCENDING),
                    ("candidate_type", ASCENDING),
                ],
                unique=True,
                name="uniq_analysis_task_request",
            )
            self._candidates.create_index(
                [
                    ("project_id", ASCENDING),
                    ("task_id", ASCENDING),
                    ("logical_key", ASCENDING),
                ],
                unique=True,
                name="uniq_analysis_candidate_request",
            )
            self._candidates.create_index(
                [("project_id", ASCENDING), ("job_id", ASCENDING)],
                name="analysis_candidates_by_job",
            )
        except OperationFailure as exc:
            raise MongoAnalysisRepositorySetupError(
                "failed to create required Analysis MongoDB indexes"
            ) from exc

    def next_job_id(self) -> str:
        return str(ObjectId())

    def next_task_id(self) -> str:
        return str(ObjectId())

    def next_candidate_id(self) -> str:
        return str(ObjectId())

    def get_job(self, job_id: str) -> AnalysisJob | None:
        doc = self._jobs.find_one({"_id": job_id})
        return _to_job(doc) if doc else None

    def find_job_request(
        self, project_id: str, snapshot_id: str, idempotency_key: str
    ) -> str | None:
        doc = self._jobs.find_one(
            {
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "idempotency_key": idempotency_key,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def put_job(self, job: AnalysisJob) -> None:
        self._jobs.insert_one(_job_doc(job))

    def update_job(self, job: AnalysisJob) -> None:
        self._jobs.replace_one({"_id": job.id}, _job_doc(job))

    def get_task(self, task_id: str) -> AnalysisTask | None:
        doc = self._tasks.find_one({"_id": task_id})
        return _to_task(doc) if doc else None

    def find_task_request(
        self, project_id: str, job_id: str, candidate_type: AnalysisCandidateType
    ) -> str | None:
        doc = self._tasks.find_one(
            {
                "project_id": project_id,
                "job_id": job_id,
                "candidate_type": str(candidate_type),
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def put_task(self, task: AnalysisTask) -> None:
        self._tasks.insert_one(_task_doc(task))

    def get_candidate(self, candidate_id: str) -> AnalysisCandidate | None:
        doc = self._candidates.find_one({"_id": candidate_id})
        return _to_candidate(doc) if doc else None

    def find_candidate_request(
        self, project_id: str, task_id: str, logical_key: str
    ) -> str | None:
        doc = self._candidates.find_one(
            {
                "project_id": project_id,
                "task_id": task_id,
                "logical_key": logical_key,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def put_candidate(
        self, candidate: AnalysisCandidate, *, logical_key: str
    ) -> None:
        self.put_candidates(((candidate, logical_key),))

    def put_candidates(
        self, candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None:
        if not candidates:
            return
        if self._use_transactions:
            self._put_candidates_transactional(candidates)
        else:
            self._put_candidates_fallback(candidates)

    def list_candidates_for_job(
        self, project_id: str, job_id: str
    ) -> tuple[AnalysisCandidate, ...]:
        cursor = self._candidates.find(
            {"project_id": project_id, "job_id": job_id}
        ).sort("_id", ASCENDING)
        return tuple(_to_candidate(doc) for doc in cursor)

    def _put_candidates_transactional(
        self, candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None:
        docs = [_candidate_doc(candidate, logical_key) for candidate, logical_key in candidates]
        with self._client.start_session() as session:
            try:
                with session.start_transaction():
                    self._candidates.insert_many(docs, session=session)
            except (BulkWriteError, DuplicateKeyError) as exc:
                if _is_duplicate_key_error(exc):
                    raise DuplicateAnalysisCandidateRequest(
                        "analysis candidate request already exists"
                    ) from exc
                raise

    def _put_candidates_fallback(
        self, candidates: Sequence[tuple[AnalysisCandidate, str]]
    ) -> None:
        docs = [_candidate_doc(candidate, logical_key) for candidate, logical_key in candidates]
        inserted_ids = [doc["_id"] for doc in docs]
        try:
            self._candidates.insert_many(docs)
        except PyMongoError as exc:
            self._candidates.delete_many({"_id": {"$in": inserted_ids}})
            if _is_duplicate_key_error(exc):
                raise DuplicateAnalysisCandidateRequest(
                    "analysis candidate request already exists"
                ) from exc
            raise


def _job_doc(job: AnalysisJob) -> dict[str, Any]:
    return {
        "_id": job.id,
        "project_id": job.project_id,
        "snapshot_id": job.snapshot_id,
        "idempotency_key": job.idempotency_key,
        "status": str(job.status),
        "failure_reason": (
            str(job.failure_reason) if job.failure_reason is not None else None
        ),
        "failure_detail": job.failure_detail,
    }


def _to_job(doc: dict[str, Any]) -> AnalysisJob:
    failure_reason = doc.get("failure_reason")
    return AnalysisJob(
        id=doc["_id"],
        project_id=doc["project_id"],
        snapshot_id=doc["snapshot_id"],
        idempotency_key=doc["idempotency_key"],
        status=AnalysisJobStatus(doc.get("status", AnalysisJobStatus.PENDING)),
        failure_reason=(
            AnalysisJobFailureReason(failure_reason)
            if failure_reason is not None
            else None
        ),
        failure_detail=doc.get("failure_detail"),
    )


def _task_doc(task: AnalysisTask) -> dict[str, Any]:
    return {
        "_id": task.id,
        "project_id": task.project_id,
        "job_id": task.job_id,
        "candidate_type": str(task.candidate_type),
    }


def _to_task(doc: dict[str, Any]) -> AnalysisTask:
    return AnalysisTask(
        id=doc["_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
    )


def _candidate_doc(candidate: AnalysisCandidate, logical_key: str) -> dict[str, Any]:
    return {
        "_id": candidate.id,
        "project_id": candidate.project_id,
        "job_id": candidate.job_id,
        "task_id": candidate.task_id,
        "logical_key": logical_key,
        "candidate_type": str(candidate.candidate_type),
        "action": str(candidate.action),
        "status": str(candidate.status),
        "provenance": str(candidate.provenance),
        "confidence": candidate.confidence,
        "source_ref_ids": list(candidate.source_ref_ids),
        "payload": dict(candidate.payload),
    }


def _to_candidate(doc: dict[str, Any]) -> AnalysisCandidate:
    return AnalysisCandidate(
        id=doc["_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        task_id=doc["task_id"],
        candidate_type=AnalysisCandidateType(doc["candidate_type"]),
        action=AnalysisCandidateAction(doc["action"]),
        status=AnalysisCandidateStatus(doc["status"]),
        provenance=AnalysisProvenance(doc["provenance"]),
        confidence=doc["confidence"],
        source_ref_ids=tuple(doc["source_ref_ids"]),
        payload=immutable_payload(doc["payload"]),
    )
