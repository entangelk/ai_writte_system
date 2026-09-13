"""재시도 쿨다운의 naive datetime 경계 — 두 어댑터가 **같은** 결함을 공유했다.

2026-09-13 실측: 실패한 잡의 retry 가 배포에서 **500** 이었다.
``TypeError: can't subtract offset-naive and offset-aware datetimes``.

pymongo 는 client 가 ``tz_aware`` 가 아니면 BSON 날짜를 naive 로 돌려준다. 두
어댑터가 그 값을 ``failed_at`` 에 그대로 실었고, `retry_policy.cooldown_remaining`
이 aware ``now`` 와 빼면서 죽었다. 두 자리와 소비처는 **같은 커밋 `63b6c0d`**
(2026-09-05, S-1 D2 재시도 쿨다운 슬라이스)가 심었다 — 한 슬라이스의 한 오해가
두 곳에 복제된 모양이라 셀도 한 파일에서 쌍으로 잡는다.

- `analysis/mongo_repository.py::_to_job` → `POST …/analysis/jobs/{id}/retry`
- `writing/generation_job_mongo.py::_entry` → `POST …/writing/generation-jobs/{id}/retry`

**기존 셀이 왜 못 봤는가**: `test_analysis_job_state.py`·`test_writing_generation_job.py`
는 in-memory 저장소로 돈다. 그 저장소는 넣은 값을 그대로 돌려주므로 **aware 를
넣으면 aware 가 나온다** — 드라이버가 실제로 하는 일(naive 로 되돌리기)을 재현하지
않는다. 그래서 전수는 초록인데 배포는 깨져 있었다(같은 병의 선례:
`test_auth_sessions_mongo.py::NaiveBsonDatetimeTest`, 2026-07-27).

**양방향**:
- under-strict — 어댑터의 `_aware()` 를 걷으면 각 클래스의 앞 두 셀이 다시 실패한다.
- over-strict — 라벨 붙이기(`replace(tzinfo=UTC)`)를 **변환**(`astimezone(UTC)`)으로
  바꾸면 세 번째 셀이 실패한다. BSON 은 이미 UTC 라 naive 를 로컬 시각으로 해석하는
  변환은 값을 오프셋만큼 민다 — 쿨다운이 조용히 9시간 지난 것이 되어 **냉각 중
  재시도가 통과**한다. 그 방향이 UTC 머신에서는 무해하므로 이 클래스는 프로세스
  시간대를 KST 로 고정하고 잰다(오너 머신·배포가 KST다).
"""

import os
import time
import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.analysis.models import (
    AnalysisJobFailureReason,
    AnalysisJobStatus,
)
from services.application.app.analysis.mongo_repository import _to_job
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.retry_policy import RetryCooldownActive
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobFailureReason,
    WritingGenerationJobService,
    WritingGenerationJobStatus,
)
from services.application.app.writing.generation_job_mongo import _entry

#: 실패 시각. BSON 에는 UTC 로 적히고 드라이버는 tzinfo 를 떼고 돌려준다.
_FAILED_AT = datetime(2026, 9, 13, 3, 0, tzinfo=UTC)
_NAIVE_FAILED_AT = _FAILED_AT.replace(tzinfo=None)


class _LocalTimeZoneIsNotUtc:
    """`replace` 와 `astimezone` 을 가르려면 로컬 시간대가 UTC 가 아니어야 한다.

    UTC 머신에서는 두 처방의 결과가 같아서 과잉 교정을 잴 수 없다 — 잴 수 없는
    가드는 가드가 아니므로 여기서 시간대를 고정한다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Seoul"
        time.tzset()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._saved_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = cls._saved_tz
        time.tzset()


def _analysis_job_doc() -> dict:
    """드라이버가 실제로 돌려주는 모양 — ``failed_at`` 이 naive 다."""

    return {
        "_id": "job-1",
        "project_id": "project-1",
        "snapshot_id": "snap-1",
        "idempotency_key": "key-1",
        "status": AnalysisJobStatus.FAILED.value,
        "failure_reason": AnalysisJobFailureReason.PROVIDER_ERROR.value,
        "failure_detail": "provider timed out",
        "retry_count": 0,
        "failed_at": _NAIVE_FAILED_AT,
    }


def _generation_job_doc() -> dict:
    return {
        "_id": "wgj:1",
        "project_id": "project-1",
        "draft_id": "draft-1",
        "request_id": "wr-1",
        "task_type": "continue_scene",
        "instruction": "이어서",
        "draft_excerpt": "앞 문단",
        "output_length": "medium",
        "max_output_tokens": 2048,
        "max_tokens": 4096,
        "version_id": "v1",
        "created_at": _FAILED_AT - timedelta(minutes=5),
        "user_id": "user-1",
        "status": WritingGenerationJobStatus.FAILED.value,
        "failure_reason": WritingGenerationJobFailureReason.PROVIDER_TIMEOUT.value,
        "failure_detail": "timed out",
        "retry_count": 0,
        "failed_at": _NAIVE_FAILED_AT,
    }


class AnalysisRetryReadsNaiveFailedAtTest(
    _LocalTimeZoneIsNotUtc, unittest.TestCase
):
    def test_failed_at_reads_back_utc_aware(self) -> None:
        """under-strict: 경계 정규화를 걷으면 tzinfo 가 다시 None 이다."""

        job = _to_job(_analysis_job_doc())
        self.assertIsNotNone(job.failed_at.tzinfo)
        self.assertEqual(job.failed_at.utcoffset(), timedelta(0))

    def test_retry_survives_a_naive_failed_at(self) -> None:
        """실제 500 경로: 어댑터가 읽은 잡을 그대로 retry 에 넘긴다.

        고침 전에는 `cooldown_remaining` 의 뺄셈에서 TypeError 였다(배포 500).
        """

        repo = InMemoryAnalysisRepository()
        repo.put_job(_to_job(_analysis_job_doc()))
        service = AnalysisService(
            repo, clock=lambda: _FAILED_AT + timedelta(seconds=61)
        )

        retried = service.retry_failed_job(
            project_id="project-1", job_id="job-1"
        )

        self.assertEqual(retried.status, AnalysisJobStatus.PENDING)
        self.assertEqual(retried.retry_count, 1)

    def test_relabelling_does_not_shift_the_instant(self) -> None:
        """over-strict: `astimezone` 으로 바꾸면 냉각 중 재시도가 통과한다.

        BSON 은 이미 UTC 다. naive 를 로컬(KST) 로 해석하는 변환은 값을 9시간
        과거로 밀고, 그러면 실패 10초 뒤의 재시도가 429 대신 통과한다 — 쿨다운
        자체가 무력해진다.
        """

        job = _to_job(_analysis_job_doc())
        self.assertEqual(job.failed_at, _FAILED_AT)
        self.assertEqual(job.failed_at.replace(tzinfo=None), _NAIVE_FAILED_AT)

        repo = InMemoryAnalysisRepository()
        repo.put_job(job)
        service = AnalysisService(
            repo, clock=lambda: _FAILED_AT + timedelta(seconds=10)
        )
        with self.assertRaises(RetryCooldownActive) as ctx:
            service.retry_failed_job(project_id="project-1", job_id="job-1")
        self.assertEqual(ctx.exception.retry_after_seconds, 50)


class GenerationJobRetryReadsNaiveFailedAtTest(
    _LocalTimeZoneIsNotUtc, unittest.TestCase
):
    def test_failed_at_reads_back_utc_aware(self) -> None:
        """under-strict — analysis 쪽과 같은 단정. 쌍둥이라서 같이 잠근다."""

        job = _entry(_generation_job_doc())
        self.assertIsNotNone(job.failed_at.tzinfo)
        self.assertEqual(job.failed_at.utcoffset(), timedelta(0))

    def test_retry_survives_a_naive_failed_at(self) -> None:
        """`POST …/writing/generation-jobs/{id}/retry` 가 죽던 자리다."""

        repo = InMemoryWritingGenerationJobRepository()
        job = _entry(_generation_job_doc())
        repo.add(job)
        service = WritingGenerationJobService(
            repo, clock=lambda: _FAILED_AT + timedelta(seconds=61)
        )

        retried = service.mark_pending_for_retry(job)

        self.assertEqual(retried.status, WritingGenerationJobStatus.PENDING)
        self.assertEqual(retried.retry_count, 1)
        self.assertIsNone(retried.failure_reason)

    def test_relabelling_does_not_shift_the_instant(self) -> None:
        """over-strict — 변환은 쿨다운을 무르게 한다(analysis 와 같은 방향)."""

        job = _entry(_generation_job_doc())
        self.assertEqual(job.failed_at, _FAILED_AT)
        self.assertEqual(job.failed_at.replace(tzinfo=None), _NAIVE_FAILED_AT)

        service = WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository(),
            clock=lambda: _FAILED_AT + timedelta(seconds=10),
        )
        with self.assertRaises(RetryCooldownActive) as ctx:
            service.mark_pending_for_retry(job)
        self.assertEqual(ctx.exception.retry_after_seconds, 50)


if __name__ == "__main__":
    unittest.main()
