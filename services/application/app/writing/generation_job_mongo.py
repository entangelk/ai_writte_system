"""Mongo repository for the async generation job store.

Backs ``writing_generation_jobs`` (async-pad D4=A). Core-SOT-external, like the
scratch store. The claim is the load-bearing primitive: ``find_one_and_update``
moves a PENDING (or lease-expired RUNNING) job to RUNNING atomically, so
concurrent/replica workers never double-run a generation — the same guarantee
the index-sync outbox gives (``indexing/mongo_repository.py``).

Enqueue idempotency is a service-level ``find_request`` check backed by a unique
``(project_id, request_id)`` index; ``add`` swallows the duplicate so a rare
double-POST of the same request cannot insert twice. (Single-user MVP: enqueue
is not a concurrency hotspot — the worker claim is; see the module docstring in
``generation_job.py``.)
"""

from datetime import datetime, timedelta

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.writing.generation_job import (
    WritingGenerationJob,
    WritingGenerationJobFailureReason,
    WritingGenerationJobStatus,
)


class MongoWritingGenerationJobRepository:
    def __init__(
        self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME
    ) -> None:
        self._jobs = client[db_name]["writing_generation_jobs"]
        self._jobs.create_index(
            [("project_id", ASCENDING), ("request_id", ASCENDING)],
            name="writing_generation_jobs_request_unique",
            unique=True,
        )
        self._jobs.create_index(
            [("status", ASCENDING), ("created_at", ASCENDING)],
            name="writing_generation_jobs_claim",
        )
        self._jobs.create_index(
            [("project_id", ASCENDING), ("draft_id", ASCENDING),
             ("created_at", DESCENDING)],
            name="writing_generation_jobs_by_draft_created",
        )
        # Phase 8 Slice 8.3 (Q1-b=A): 입장 판정이 매 유료 요청마다 이 회원의 대기·
        # 실행 중 job 을 센다. 입장은 뮤텍스 임계 구역 안이라 **빨라야 한다** —
        # 인덱스 없이 컬렉션을 훑으면 그 구간이 길어지고, 길어진 임계 구역이 곧
        # 같은 회원의 다음 요청 지연이다.
        self._jobs.create_index(
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="writing_generation_jobs_by_user_status",
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def add(self, job: WritingGenerationJob) -> None:
        try:
            self._jobs.insert_one(_doc(job))
        except DuplicateKeyError:
            # A concurrent enqueue of the same (project_id, request_id) already
            # persisted the job; the service's find_request check owns dedup.
            return

    def get(self, job_id: str) -> WritingGenerationJob | None:
        doc = self._jobs.find_one({"_id": job_id})
        return _entry(doc) if doc else None

    def find_request(self, project_id: str, request_id: str) -> str | None:
        doc = self._jobs.find_one(
            {"project_id": project_id, "request_id": request_id},
            projection={"_id": 1},
        )
        return doc["_id"] if doc else None

    def update(self, job: WritingGenerationJob) -> None:
        self._jobs.replace_one({"_id": job.id}, _doc(job))

    def claim_next(
        self, *, now: datetime, claim_timeout_seconds: int
    ) -> WritingGenerationJob | None:
        stale_before = now - timedelta(seconds=claim_timeout_seconds)
        doc = self._jobs.find_one_and_update(
            {
                "$or": [
                    {"status": WritingGenerationJobStatus.PENDING.value},
                    {
                        "status": WritingGenerationJobStatus.RUNNING.value,
                        "claimed_at": {"$lte": stale_before},
                    },
                ]
            },
            {
                "$set": {
                    "status": WritingGenerationJobStatus.RUNNING.value,
                    "claimed_at": now,
                }
            },
            sort=[("created_at", ASCENDING), ("_id", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        return _entry(doc) if doc else None

    def list_for_draft(
        self, project_id: str, draft_id: str
    ) -> tuple[WritingGenerationJob, ...]:
        return tuple(_entry(doc) for doc in self._jobs.find(
            {"project_id": project_id, "draft_id": draft_id},
        ).sort([("created_at", DESCENDING), ("_id", DESCENDING)]))

    def count_active_for_user(self, user_id: str) -> int:
        return self._jobs.count_documents({
            "user_id": user_id,
            "status": {"$in": [
                WritingGenerationJobStatus.PENDING.value,
                WritingGenerationJobStatus.RUNNING.value,
            ]},
        })

    def purge_project(self, project_id: str) -> None:
        # D8-6b-2: project 의 generation job 전부 파기(직접 project_id 스코프).
        self._jobs.delete_many({"project_id": project_id})

    def purge_draft(self, project_id: str, draft_id: str) -> None:
        self._jobs.delete_many({"project_id": project_id, "draft_id": draft_id})


def _doc(job: WritingGenerationJob) -> dict:
    return {
        "_id": job.id,
        "project_id": job.project_id,
        "draft_id": job.draft_id,
        "request_id": job.request_id,
        "task_type": job.task_type,
        "instruction": job.instruction,
        "draft_excerpt": job.draft_excerpt,
        "query": job.query,
        "output_length": job.output_length,
        "max_output_tokens": job.max_output_tokens,
        "max_tokens": job.max_tokens,
        "version_id": job.version_id,
        "created_at": job.created_at,
        # 8.3 Q1-b=A: 워커가 성공 시 원장에 쓰려면 주체를 알아야 한다.
        "user_id": job.user_id,
        "status": job.status.value,
        "claimed_at": job.claimed_at,
        "failure_reason": (
            job.failure_reason.value if job.failure_reason is not None else None
        ),
        "failure_detail": job.failure_detail,
        "result_scratch_id": job.result_scratch_id,
    }


def _entry(doc: dict) -> WritingGenerationJob:
    failure_reason = doc.get("failure_reason")
    return WritingGenerationJob(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        request_id=doc["request_id"],
        task_type=doc["task_type"],
        instruction=doc["instruction"],
        draft_excerpt=doc["draft_excerpt"],
        query=doc.get("query"),
        output_length=doc["output_length"],
        max_output_tokens=doc["max_output_tokens"],
        max_tokens=doc["max_tokens"],
        version_id=doc["version_id"],
        created_at=doc["created_at"],
        # 8.3 이전에 만들어진 행에는 이 필드가 없다 — 그런 job 은 과금되지 않는다.
        user_id=doc.get("user_id"),
        status=WritingGenerationJobStatus(doc["status"]),
        claimed_at=doc.get("claimed_at"),
        failure_reason=(
            WritingGenerationJobFailureReason(failure_reason)
            if failure_reason is not None else None
        ),
        failure_detail=doc.get("failure_detail"),
        result_scratch_id=doc.get("result_scratch_id"),
    )
