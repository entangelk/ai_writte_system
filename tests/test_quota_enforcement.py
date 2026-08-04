"""Slice 8.3 도메인 회귀 — 입장과 정산 (오너 결정 2026-08-04).

브리프 ``08-3-quota-enforcement-decisions.md`` §"결정 뒤 구현 슬라이스" 1.
HTTP 쪽(상태코드·전수 가드·확인 헤더)은 ``test_quota_enforcement_api.py`` 다.

**양방향으로 문다.** 이 슬라이스에서 특히 중요한 이유가 있다 — 여기서 틀리는
방향은 대칭이 아니다:

- under-strict(한 칸 더 통과) = **회원이 돈 안 내고 GPU 를 쓴다**
- over-strict(한 칸 덜 통과) = **회원이 산 것을 못 쓴다**

그래서 "막는다"를 단정하는 셀마다 "막지 **않는다**"를 단정하는 짝을 둔다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.quota.enforcement import (
    ADMISSION_KEY_PREFIX,
    AdmissionMutex,
    AdmissionUnavailable,
    GenerationJobCharger,
    QuotaEnforcementService,
    QuotaRefusalReason,
    QuotaRefused,
    admission_key,
)
from services.application.app.quota.ledger import (
    InMemoryUsageLedgerRepository,
    UsageLedgerService,
)
from services.application.app.quota.lock import (
    InMemoryRequestLockRepository,
    RequestLockService,
    lock_key,
)
from services.application.app.quota.policy import (
    InMemoryQuotaPolicyRepository,
    QuotaLimits,
    QuotaPolicy,
    QuotaPolicyService,
    QuotaStatus,
)

_NOW = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
_JOINED = datetime(2026, 7, 1, tzinfo=UTC)
_USER = "u-1"
_PROJECT = "p-1"


class _Clock:
    def __init__(self, now: datetime = _NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Ids:
    def __init__(self, prefix: str = "id") -> None:
        self._prefix = prefix
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"{self._prefix}-{self._n}"


class _Jobs:
    """진행 중 async job 계수만 흉내 낸다 (Q1-b=A 의 입장 쪽)."""

    def __init__(self, active: int = 0) -> None:
        self.active = active
        self.asked_for: list[str] = []

    def count_active_for_user(self, *, user_id: str) -> int:
        self.asked_for.append(user_id)
        return self.active


def _build(
    *, clock: _Clock | None = None, limits: QuotaLimits | None = None,
    jobs: _Jobs | None = None, lock_repo=None,
):
    clock = clock or _Clock()
    policy_repo = InMemoryQuotaPolicyRepository()
    policy = QuotaPolicyService(policy_repo, clock=clock)
    if limits is not None:
        # 문서를 직접 넣는다 — ``set_limits`` 는 P6 대로 **불리한 변경을 주 경계로
        # 유예**하므로(한도를 내리는 것은 불리하다) 테스트가 원하는 한도가 지금
        # 유효해지지 않는다. 여기서 재는 것은 8.1 의 유예 규칙이 아니라 시행이다.
        policy_repo.upsert(QuotaPolicy(
            user_id=_USER, limits=limits, pending=None, updated_at=clock()))
    ledger_repo = InMemoryUsageLedgerRepository()
    ledger = UsageLedgerService(ledger_repo, id_factory=_Ids("rul"), clock=clock)
    lock_repo = lock_repo if lock_repo is not None else InMemoryRequestLockRepository()
    locks = RequestLockService(
        lock_repo, clock=clock, holder_factory=_Ids("holder"),
        minimum_window_seconds=5, lease_seconds=180,
    )
    service = QuotaEnforcementService(
        policy=policy,
        ledger=ledger,
        locks=locks,
        mutex=AdmissionMutex(
            lock_repo, clock=clock, holder_factory=_Ids("mutex"),
            sleep=lambda _seconds: None,
        ),
        jobs=jobs,
    )
    return service, ledger_repo, lock_repo, clock


def _admit(service, *, action="writing_gate", dedupe_key="req-1", confirmed=False):
    return service.admit(
        user_id=_USER, member_created_at=_JOINED, action=action,
        target_project_id=_PROJECT, dedupe_key=dedupe_key, confirmed=confirmed,
    )


def _usage_rows(repo: InMemoryUsageLedgerRepository) -> list:
    return list(repo._usage)  # noqa: SLF001 — 테스트가 저장된 사실을 직접 읽는다


class SuccessfulChargeTest(unittest.TestCase):
    """Q1=C — 성공한 요청만, 정확히 한 행."""

    def test_a_successful_request_leaves_exactly_one_usage_row(self):
        service, ledger, _locks, _clock = _build()
        service.settle(_admit(service), charged=True)
        rows = _usage_rows(ledger)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].user_id, _USER)
        self.assertEqual(rows[0].action, "writing_gate")
        self.assertEqual(rows[0].dedupe_key, "req-1")
        # L1=B: 필드 이름이 계약이다 — `project_id` 로 적으면 purge reconciler 가
        # 과금 기록을 지운다.
        self.assertEqual(rows[0].target_project_id, _PROJECT)

    def test_a_failed_request_leaves_no_row(self):
        # Q1=C 의 핵심 셀. 502·504·400·409·503 은 전부 HTTP 층에서 "2xx 가 아니다"
        # 하나로 접히므로, 도메인에서는 charged=False 한 축으로 잠근다(HTTP 쪽
        # 셀이 상태코드별로 그것을 다시 잰다).
        service, ledger, _locks, _clock = _build()
        service.settle(_admit(service), charged=False)
        self.assertEqual(_usage_rows(ledger), [])

    def test_the_lock_is_released_whether_or_not_the_request_was_charged(self):
        for charged in (True, False):
            with self.subTest(charged=charged):
                service, _ledger, locks, _clock = _build()
                charge = _admit(service)
                service.settle(charge, charged=charged)
                lock = locks.peek(lock_key(_USER, "writing_gate", _PROJECT))
                self.assertIsNotNone(lock.released_at)

    def test_the_usage_row_lands_before_the_lock_is_released(self):
        # Q3=E 구현 계약 2. 순서가 뒤집히면 그 사이에 **행도 없고 잠금도 없는 한
        # 칸**이 생겨 초과가 정확히 그 틈으로 샌다. 순서를 바꾸는 뮤테이션이 문다.
        order: list[str] = []

        class _OrderedLedger(InMemoryUsageLedgerRepository):
            def add_usage(self, entry):
                order.append("ledger")
                super().add_usage(entry)

        class _OrderedLocks(InMemoryRequestLockRepository):
            def release(self, key, **kwargs):
                # 입장 뮤텍스도 같은 저장소를 쓰므로(§Q3-a 계약 1) 그 반납은
                # 여기서 보고 싶은 순서가 아니다 — 요청 잠금만 센다.
                if not key.startswith(ADMISSION_KEY_PREFIX):
                    order.append("release")
                return super().release(key, **kwargs)

        clock = _Clock()
        ledger_repo = _OrderedLedger()
        lock_repo = _OrderedLocks()
        service = QuotaEnforcementService(
            policy=QuotaPolicyService(InMemoryQuotaPolicyRepository(), clock=clock),
            ledger=UsageLedgerService(
                ledger_repo, id_factory=_Ids("rul"), clock=clock),
            locks=RequestLockService(
                lock_repo, clock=clock, holder_factory=_Ids("holder"),
                minimum_window_seconds=5, lease_seconds=180),
            mutex=AdmissionMutex(
                lock_repo, clock=clock, holder_factory=_Ids("mutex"),
                sleep=lambda _s: None),
        )
        service.settle(_admit(service), charged=True)
        self.assertEqual(order, ["ledger", "release"])

    def test_a_ledger_failure_after_success_does_not_strand_the_lock(self):
        # Q2 의 남는 한 자리: 응답은 이미 나갔으므로 뒤집지 않는다. 그렇다고
        # 잠금까지 남기면 그 회원은 lease(180초) 동안 같은 동작을 못 한다.
        class _BrokenLedger(InMemoryUsageLedgerRepository):
            def add_usage(self, entry):
                raise RuntimeError("ledger is down")

        clock = _Clock()
        lock_repo = InMemoryRequestLockRepository()
        service = QuotaEnforcementService(
            policy=QuotaPolicyService(InMemoryQuotaPolicyRepository(), clock=clock),
            ledger=UsageLedgerService(
                _BrokenLedger(), id_factory=_Ids("rul"), clock=clock),
            locks=RequestLockService(
                lock_repo, clock=clock, holder_factory=_Ids("holder"),
                minimum_window_seconds=5, lease_seconds=180),
            mutex=AdmissionMutex(
                lock_repo, clock=clock, holder_factory=_Ids("mutex"),
                sleep=lambda _s: None),
        )
        charge = _admit(service)
        with self.assertLogs(
            "services.application.app.quota.enforcement", level="ERROR"
        ):
            service.settle(charge, charged=True)
        self.assertIsNotNone(
            lock_repo.peek(lock_key(_USER, "writing_gate", _PROJECT)).released_at
        )


class LimitBoundaryTest(unittest.TestCase):
    """한도 경계 — 직전·정각·직후."""

    def _fill(self, service, clock, count: int) -> None:
        """한도를 채운다. **시계를 넘긴다** — 8.2b 잠금의 최소 창(5초) 때문에
        같은 동작을 연달아 보내면 시행이 아니라 잠금이 먼저 막는다."""
        for index in range(count):
            service.settle(
                _admit(service, dedupe_key=f"seed-{index}"), charged=True)
            clock.advance(10)

    def test_the_last_allowed_request_passes_and_the_next_one_is_refused(self):
        # 경계 직전(2/3) → 정각을 채우는 요청은 통과 → 그 다음이 거절.
        service, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=3, weekly_limit=100))
        self._fill(service, clock, 2)
        service.settle(
            _admit(service, action="writing_report", dedupe_key="third"),
            charged=True,
        )
        self.assertEqual(len(_usage_rows(ledger)), 3)
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, action="context_search", dedupe_key="fourth")
        self.assertIs(refused.exception.reason, QuotaRefusalReason.EXCEEDED)

    def test_exactly_at_the_limit_is_refused(self):
        service, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=2, weekly_limit=100))
        self._fill(service, clock, 2)
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, dedupe_key="third")
        self.assertIs(refused.exception.reason, QuotaRefusalReason.EXCEEDED)
        self.assertIn("daily", refused.exception.detail)

    def test_below_the_limit_is_not_refused(self):
        # over-strict 짝: 경계를 한 칸 당기는 변경(`>` → `>=` 를 `>` 로, 또는
        # used+1 을 세는 것)이 여기서 물린다.
        service, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=2, weekly_limit=100))
        self._fill(service, clock, 1)
        _admit(service, dedupe_key="second")  # 예외가 나면 실패

    def test_both_windows_are_checked(self):
        # 일은 여유인데 주가 소진이면 막힌다 — 그 역도. 한쪽만 보는 뮤테이션이
        # 어느 방향이든 여기서 물린다.
        service, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=100, weekly_limit=2))
        self._fill(service, clock, 2)
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, dedupe_key="x")
        self.assertIn("weekly", refused.exception.detail)

        service, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=2, weekly_limit=100))
        self._fill(service, clock, 2)
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, dedupe_key="x")
        self.assertIn("daily", refused.exception.detail)

    def test_no_limit_never_refuses_and_zero_always_does(self):
        # P5: 수량과 상태는 다른 축이고, `limit=0`("오늘은 0회")과 정지는 다르다.
        unlimited, ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=None, weekly_limit=None))
        for index in range(5):
            unlimited.settle(
                _admit(unlimited, dedupe_key=f"u-{index}"), charged=True)
            clock.advance(10)
        self.assertEqual(len(_usage_rows(ledger)), 5)

        zero, _ledger, _locks, _clock = _build(
            limits=QuotaLimits(daily_limit=0, weekly_limit=100))
        with self.assertRaises(QuotaRefused) as refused:
            _admit(zero)
        self.assertIs(refused.exception.reason, QuotaRefusalReason.EXCEEDED)

    def test_a_suspended_account_is_refused_with_its_own_reason(self):
        service, _ledger, _locks, _clock = _build(
            limits=QuotaLimits(daily_limit=None, weekly_limit=None,
                               status=QuotaStatus.SUSPENDED))
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service)
        # Q5=B: 초과(시간이 지나면 풀린다)와 정지(관리자만 푼다)는 다른 사건이라
        # 프론트가 다르게 행동해야 한다 — 사유가 접히면 그 구분이 사라진다.
        self.assertIs(refused.exception.reason, QuotaRefusalReason.SUSPENDED)

    def test_an_administrator_refund_gives_room_back(self):
        # 8.2 L5: 조정은 사용량에 더해지는 값이라 음수가 여유가 된다. 시행이
        # 원장 행만 세면(조정을 빼먹으면) 이 셀이 문다.
        service, ledger_repo, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=2, weekly_limit=100))
        for index in range(2):
            service.settle(
                _admit(service, dedupe_key=f"seed-{index}"), charged=True)
            clock.advance(10)
        with self.assertRaises(QuotaRefused):
            _admit(service, dedupe_key="blocked")
        UsageLedgerService(
            ledger_repo, id_factory=_Ids("adj"), clock=_Clock()
        ).record_adjustment(
            user_id=_USER, member_created_at=_JOINED, target_project_id=_PROJECT,
            delta=-2, reason="장애 보상", admin_user_id="admin-1",
        )
        _admit(service, dedupe_key="after-refund")  # 예외가 나면 실패


class InFlightCountsTowardTheLimitTest(unittest.TestCase):
    """Q3=E — 진행 중 요청이 한도를 차지한다."""

    def test_a_live_lock_takes_a_slot_and_giving_it_back_restores_it(self):
        service, _ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=1, weekly_limit=100))
        first = _admit(service, action="writing_gate", dedupe_key="a")
        # 행은 아직 없다(성공차감). 그런데도 한도는 차 있어야 한다 — 그렇지
        # 않으면 91초 동안 같은 회원의 모든 요청이 "아직 여유 있음"을 읽는다.
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, action="writing_report", dedupe_key="b")
        self.assertIs(refused.exception.reason, QuotaRefusalReason.EXCEEDED)
        # 실패로 끝나면(charged=False) 그 칸은 되돌아온다 = 오너가 말한 "리캐싱".
        service.settle(first, charged=False)
        clock.advance(10)
        _admit(service, action="writing_report", dedupe_key="b")

    def test_a_released_lock_in_its_cooldown_does_not_take_a_slot(self):
        # over-strict 짝: 냉각(released_at 이 있고 아직 expires_at 전)까지 세면
        # 회원이 **쓰지도 않은 한 칸**을 5초마다 잃는다. 계수 조건에서
        # `released_at is None` 을 빼는 뮤테이션이 여기서 물린다.
        service, _ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=1, weekly_limit=100))
        charge = _admit(service, action="writing_gate", dedupe_key="a")
        service.settle(charge, charged=False)
        # 아직 냉각 중이다(차지 + 5초 이내).
        clock.advance(1)
        _admit(service, action="writing_report", dedupe_key="b")

    def test_pending_async_jobs_take_slots_too(self):
        # Q1-b=A: 202 에서 잠금이 풀리므로 워커가 도는 91초는 잠금이 안 덮는다.
        # job 계수를 빼면 회원이 async 를 쌓아 한도를 우회한다.
        jobs = _Jobs(active=2)
        service, _ledger, _locks, _clock = _build(
            limits=QuotaLimits(daily_limit=2, weekly_limit=100), jobs=jobs)
        with self.assertRaises(QuotaRefused):
            _admit(service)
        self.assertEqual(jobs.asked_for, [_USER])

    def test_effective_usage_adds_both_axes(self):
        jobs = _Jobs(active=3)
        service, _ledger, _locks, _clock = _build(jobs=jobs)
        _admit(service, action="writing_gate", dedupe_key="a")
        daily, weekly = service.effective_usage(
            user_id=_USER, member_created_at=_JOINED)
        # 잠금 1 + job 3, 원장 0.
        self.assertEqual((daily, weekly), (4, 4))


class AdmissionMutexTest(unittest.TestCase):
    """Q3-a=A — 입장은 직렬화된다."""

    def test_two_concurrent_admissions_cannot_both_read_the_same_free_slot(self):
        # 이 저장소의 fake 는 단일 스레드라 "동시"를 흉내 낸다: 뮤텍스를 쥔 채
        # 두 번째 입장을 시도하면 획득에 실패해야 한다. 실 Mongo 20-way 셀은
        # ``test_quota_enforcement_live_mongo.py`` 에 있다.
        lock_repo = InMemoryRequestLockRepository()
        service, _ledger, _locks, _clock = _build(lock_repo=lock_repo)
        mutex = AdmissionMutex(
            lock_repo, clock=_Clock(), holder_factory=_Ids("other"),
            attempts=2, sleep=lambda _s: None,
        )
        with mutex.hold(_USER):
            with self.assertRaises(AdmissionUnavailable):
                _admit(service)

    def test_the_mutex_is_released_before_the_caller_does_its_work(self):
        # ★ over-strict 핵심 셀: 뮤텍스를 쥔 채 provider 를 부르면 이 설계의
        # 장점이 전부 사라진다(한 회원의 요청이 91초씩 직렬화된다). admit 이
        # 돌아온 시점에 뮤텍스는 이미 풀려 있어야 하고, 그것을 "다른 주인이
        # 곧바로 잡을 수 있다"로 잰다.
        lock_repo = InMemoryRequestLockRepository()
        service, _ledger, _locks, clock = _build(lock_repo=lock_repo)
        _admit(service)
        other = AdmissionMutex(
            lock_repo, clock=clock, holder_factory=_Ids("other"),
            attempts=1, sleep=lambda _s: None,
        )
        with other.hold(_USER):
            pass

    def test_the_mutex_is_released_even_when_admission_refuses(self):
        # §Q3-a 계약 4: 해제는 finally 다. 초과로 거절된 뒤에도 그 회원의 다음
        # 요청이 뮤텍스를 잡을 수 있어야 한다(안 그러면 lease 5초 동안 잠긴다).
        lock_repo = InMemoryRequestLockRepository()
        service, _ledger, _locks, clock = _build(
            limits=QuotaLimits(daily_limit=0, weekly_limit=None),
            lock_repo=lock_repo,
        )
        with self.assertRaises(QuotaRefused):
            _admit(service)
        self.assertIsNotNone(lock_repo.peek(admission_key(_USER)).released_at)

    def test_a_mutex_that_cannot_be_taken_fails_closed(self):
        class _NeverGrants(InMemoryRequestLockRepository):
            def claim(self, lock, *, now):
                return lock.__class__(
                    key=lock.key, holder="someone-else",
                    claimed_at=now, expires_at=now + timedelta(seconds=5),
                )

        service, _ledger, _locks, _clock = _build(lock_repo=_NeverGrants())
        # 초과를 허용하느니 요청을 실패시킨다(Q4=A 와 같은 방향).
        with self.assertRaises(AdmissionUnavailable):
            _admit(service)

    def test_the_mutex_key_space_is_disjoint_from_the_request_lock_space(self):
        # §Q3-a 계약 1. 접두가 겹치면 뮤텍스가 자기 자신을 "진행 중 요청"으로
        # 세어 회원이 한 칸을 상시로 잃는다.
        lock_repo = InMemoryRequestLockRepository()
        service, _ledger, _locks, _clock = _build(lock_repo=lock_repo)
        mutex = AdmissionMutex(
            lock_repo, clock=_Clock(), holder_factory=_Ids("m"),
            sleep=lambda _s: None)
        with mutex.hold(_USER):
            self.assertEqual(
                service.effective_usage(
                    user_id=_USER, member_created_at=_JOINED),
                (0, 0),
            )
        self.assertTrue(admission_key(_USER).startswith(ADMISSION_KEY_PREFIX))


class DuplicateLockTest(unittest.TestCase):
    """8.2b 잠금이 시행 통로에 붙었다 — 그리고 막힌 요청은 과금되지 않는다."""

    def test_the_same_action_twice_is_locked_and_leaves_no_row(self):
        service, ledger, _locks, _clock = _build()
        _admit(service, dedupe_key="a")
        with self.assertRaises(QuotaRefused) as refused:
            _admit(service, dedupe_key="b")
        self.assertIs(refused.exception.reason, QuotaRefusalReason.LOCKED)
        self.assertTrue(refused.exception.in_flight)
        self.assertGreaterEqual(refused.exception.retry_after_seconds, 1)
        # 잠금 실패가 차감을 남기면 최악이다 — 일도 안 하고 돈만 받는다.
        self.assertEqual(_usage_rows(ledger), [])

    def test_a_different_action_in_the_same_project_is_not_locked(self):
        # over-strict 짝(8.2b G2=A): 축에서 action 을 빼면 제품의 정상 연쇄
        # (generate → gate → revise-and-gate → accept)가 서로를 막는다.
        service, _ledger, _locks, _clock = _build()
        _admit(service, action="writing_generate", dedupe_key="a")
        _admit(service, action="writing_gate", dedupe_key="a")

    def test_confirming_takes_the_lock_over_and_the_next_click_is_blocked_again(self):
        # G4=A: 확인은 잠금을 **끄는 것이 아니라 옮긴다**.
        service, ledger, _locks, _clock = _build()
        _admit(service, dedupe_key="a")
        confirmed = _admit(service, dedupe_key="b", confirmed=True)
        self.assertIsNotNone(confirmed.holder)
        with self.assertRaises(QuotaRefused):
            _admit(service, dedupe_key="c")

    def test_a_confirmed_request_spends_another_unit(self):
        # 8.0 B1=A: 의도적인 2안은 사용량 1회를 더 쓴다.
        service, ledger, _locks, _clock = _build()
        first = _admit(service, dedupe_key="a")
        service.settle(first, charged=True)
        second = _admit(service, dedupe_key="b", confirmed=True)
        service.settle(second, charged=True)
        self.assertEqual(len(_usage_rows(ledger)), 2)

    def test_the_same_dedupe_key_is_never_counted_twice(self):
        service, ledger, _locks, clock = _build()
        service.settle(_admit(service, dedupe_key="same"), charged=True)
        clock.advance(10)
        service.settle(_admit(service, dedupe_key="same"), charged=True)
        self.assertEqual(len(_usage_rows(ledger)), 1)

    def test_different_actions_sharing_one_client_key_are_counted_separately(self):
        # 8.2 L2=A: 프론트는 한 흐름에 uuid 하나를 쓴다. 원장 키에서 action 을
        # 빼면 유료 동작 4개가 1개로 접혀 8.0 B1 이 조용히 깨진다.
        service, ledger, _locks, _clock = _build()
        for action in ("writing_generate", "writing_gate", "writing_accept"):
            service.settle(
                _admit(service, action=action, dedupe_key="one-flow"),
                charged=True,
            )
        self.assertEqual(len(_usage_rows(ledger)), 3)


class StorageFailureTest(unittest.TestCase):
    """Q4=A — 전면 fail-closed. 계량 불능은 무료 제공이 아니다."""

    def _service_with(self, *, policy=None, ledger=None, locks=None):
        clock = _Clock()
        lock_repo = locks or InMemoryRequestLockRepository()
        return QuotaEnforcementService(
            policy=QuotaPolicyService(
                policy or InMemoryQuotaPolicyRepository(), clock=clock),
            ledger=UsageLedgerService(
                ledger or InMemoryUsageLedgerRepository(),
                id_factory=_Ids("rul"), clock=clock),
            locks=RequestLockService(
                lock_repo, clock=clock, holder_factory=_Ids("holder"),
                minimum_window_seconds=5, lease_seconds=180),
            mutex=AdmissionMutex(
                lock_repo, clock=clock, holder_factory=_Ids("mutex"),
                sleep=lambda _s: None),
        )

    def test_a_policy_read_failure_stops_the_request(self):
        class _Broken(InMemoryQuotaPolicyRepository):
            def get(self, user_id):
                raise RuntimeError("policy store is down")

        with self.assertRaises(RuntimeError):
            _admit(self._service_with(policy=_Broken()))

    def test_a_ledger_read_failure_stops_the_request(self):
        class _Broken(InMemoryUsageLedgerRepository):
            def count_usage(self, user_id, **kwargs):
                raise RuntimeError("ledger is down")

        with self.assertRaises(RuntimeError):
            _admit(self._service_with(ledger=_Broken()))

    def test_a_lock_claim_failure_stops_the_request(self):
        class _Broken(InMemoryRequestLockRepository):
            def claim(self, lock, *, now):
                if lock.key.startswith(ADMISSION_KEY_PREFIX):
                    return super().claim(lock, now=now)
                raise RuntimeError("lock store is down")

        with self.assertRaises(RuntimeError):
            _admit(self._service_with(locks=_Broken()))


class AsyncGenerationChargeTest(unittest.TestCase):
    """Q1-b=A — 비동기는 워커가 센다."""

    class _Job:
        def __init__(self, user_id="u-1", request_id="wr-1"):
            self.id = "wgj-1"
            self.user_id = user_id
            self.request_id = request_id
            self.project_id = _PROJECT

    class _Users:
        def __init__(self, member=True):
            self._member = member

        def get_by_id(self, user_id):
            if not self._member:
                return None
            return type("M", (), {"created_at": _JOINED})()

    def test_a_successful_generation_leaves_exactly_one_row(self):
        service, ledger, _locks, _clock = _build()
        GenerationJobCharger(
            enforcement=service, users=self._Users()
        ).charge(self._Job())
        rows = _usage_rows(ledger)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, "writing_generate")
        # dedupe_key = request_id: 요청 경로와 **같은 축**이라 재전송·retry 가
        # 몇 번을 돌아도 한 행이다(8.0 B5=A).
        self.assertEqual(rows[0].dedupe_key, "wr-1")

    def test_re_running_the_same_job_does_not_charge_twice(self):
        service, ledger, _locks, _clock = _build()
        charger = GenerationJobCharger(enforcement=service, users=self._Users())
        charger.charge(self._Job())
        charger.charge(self._Job())          # lease 회수 뒤 재실행 · retry
        self.assertEqual(len(_usage_rows(ledger)), 1)

    def test_a_job_without_a_subject_is_not_charged(self):
        service, ledger, _locks, _clock = _build()
        GenerationJobCharger(
            enforcement=service, users=self._Users()
        ).charge(self._Job(user_id=None))
        self.assertEqual(_usage_rows(ledger), [])

    def test_charging_never_raises_into_the_worker(self):
        # 차감 실패로 job 이 RUNNING 에 남으면 lease 만료 뒤 재차지되어 **같은
        # 91초 생성을 다시 돌린다**. 사용량 기록 하나 때문에 치를 대가가 아니다.
        class _BrokenUsers:
            def get_by_id(self, user_id):
                raise RuntimeError("users store is down")

        service, ledger, _locks, _clock = _build()
        with self.assertLogs(
            "services.application.app.quota.enforcement", level="ERROR"
        ):
            GenerationJobCharger(
                enforcement=service, users=_BrokenUsers()
            ).charge(self._Job())
        self.assertEqual(_usage_rows(ledger), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
