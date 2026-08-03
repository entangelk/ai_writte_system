"""Slice 8.1 저장 계약 회귀 — 창 경계·한도 표현·정책 변경 발효.

브리프 ``08-1-request-quota-policy-decisions.md``(오너 결정 2026-08-03).
각 셀은 **양방향**으로 물도록 썼다: 원래 결함을 되살리면 실패하고(under-strict),
과잉 교정으로 정상 경로를 깨도 실패한다(over-strict). 특히 경계는 **직전과 직후를
함께** 단정한다 — 한쪽만 보면 `<` 를 `<=` 로 바꾸는 종류의 실수가 통과한다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from services.application.app.quota.policy import (
    DEFAULT_DAILY_LIMIT,
    DEFAULT_WEEKLY_LIMIT,
    InMemoryQuotaPolicyRepository,
    QuotaLimits,
    QuotaPolicyService,
    QuotaStatus,
    daily_key,
    default_limits,
    effective_limits,
    next_week_boundary,
    split_change,
    weekly_cycle_bounds,
    weekly_key,
)

# 가입 시각: KST 2026-07-06(월) 14:37 = UTC 05:37.
CREATED_AT = datetime(2026, 7, 6, 5, 37, tzinfo=UTC)


class DailyWindowTest(unittest.TestCase):
    """P2 + P2-a — 일 창은 **KST 자정**에 바뀐다."""

    def test_the_day_turns_over_at_kst_midnight_not_utc_midnight(self) -> None:
        # KST 자정 = UTC 15:00. 직전/직후를 함께 본다: 한쪽만 보면 UTC 기준 구현도
        # 통과할 수 있다(UTC 자정에도 날짜는 바뀌므로).
        just_before = datetime(2026, 8, 3, 14, 59, 59, tzinfo=UTC)
        just_after = datetime(2026, 8, 3, 15, 0, 0, tzinfo=UTC)
        self.assertEqual(daily_key(just_before), "2026-08-03")
        self.assertEqual(daily_key(just_after), "2026-08-04")

    def test_utc_midnight_is_the_middle_of_a_korean_day(self) -> None:
        # over-strict 방향: 누군가 경계를 UTC 자정으로 되돌리면 여기서 갈라진다.
        # UTC 로 날짜가 바뀌는 순간에도 한국은 같은 날(오전 9시)이다.
        before_utc_midnight = datetime(2026, 8, 3, 23, 59, tzinfo=UTC)
        after_utc_midnight = datetime(2026, 8, 4, 0, 1, tzinfo=UTC)
        self.assertEqual(daily_key(before_utc_midnight), "2026-08-04")
        self.assertEqual(daily_key(after_utc_midnight), "2026-08-04")


class WeeklyWindowTest(unittest.TestCase):
    """P2-b — 주 창은 **가입일로부터 7일** 주기이고 회원마다 다르다."""

    def test_the_cycle_is_anchored_to_the_signup_date_at_kst_midnight(self) -> None:
        # 기준은 가입 *시각*(14:37)이 아니라 가입 *일*의 KST 자정이다. 시각 기준이면
        # 주 경계가 오후에 걸려 일 창과 어긋난다.
        start, end = weekly_cycle_bounds(CREATED_AT, CREATED_AT)
        self.assertEqual(start, datetime(2026, 7, 5, 15, 0, tzinfo=UTC))  # KST 7/6 00:00
        self.assertEqual(end - start, timedelta(days=7))

    def test_the_week_turns_over_exactly_seven_days_later(self) -> None:
        start, end = weekly_cycle_bounds(CREATED_AT, CREATED_AT)
        just_before = end - timedelta(seconds=1)
        self.assertEqual(weekly_key(CREATED_AT, just_before), "2026-07-06")
        self.assertEqual(weekly_key(CREATED_AT, end), "2026-07-13")

    def test_two_members_who_joined_on_different_days_have_different_weeks(self) -> None:
        # 달력 주였다면 같은 키가 나왔을 순간이다. 회원별 주기라는 결정이 여기서 보인다.
        other = datetime(2026, 7, 9, 5, 0, tzinfo=UTC)
        now = datetime(2026, 7, 20, 5, 0, tzinfo=UTC)
        self.assertNotEqual(weekly_key(CREATED_AT, now), weekly_key(other, now))

    def test_a_moment_between_signup_and_the_first_midnight_is_the_first_cycle(self) -> None:
        # 가입 시각은 그 날 KST 자정보다 뒤이므로 elapsed 가 음수가 될 수 없지만,
        # 시계 오차나 소급 생성으로 그런 값이 들어와도 첫 주기로 접는다.
        before_anchor = CREATED_AT - timedelta(days=1)
        start, _end = weekly_cycle_bounds(CREATED_AT, before_anchor)
        self.assertEqual(start, datetime(2026, 7, 5, 15, 0, tzinfo=UTC))


class DefaultLimitsTest(unittest.TestCase):
    """P4 + P7 — 행이 없으면 기본, 기본은 env 로 조정 가능."""

    def test_a_member_without_a_row_gets_the_default(self) -> None:
        self.assertEqual(effective_limits(None, datetime.now(UTC)), default_limits())
        self.assertEqual(default_limits().daily_limit, DEFAULT_DAILY_LIMIT)
        self.assertEqual(default_limits().weekly_limit, DEFAULT_WEEKLY_LIMIT)

    def test_the_weekly_default_is_smaller_than_seven_daily_windows(self) -> None:
        # 이 부등식이 깨지면 주 한도는 영원히 도달 불가라 존재 이유가 사라진다.
        # 저장 계약이 임의 조합을 금지하지는 않지만(브리프 P2), **기본값**은 두 창이
        # 모두 의미를 갖는 조합이어야 한다.
        self.assertLess(DEFAULT_WEEKLY_LIMIT, DEFAULT_DAILY_LIMIT * 7)

    def test_env_overrides_the_default_and_empty_means_unlimited(self) -> None:
        with mock.patch.dict("os.environ", {"QUOTA_DEFAULT_DAILY_LIMIT": "5"}):
            self.assertEqual(default_limits().daily_limit, 5)
        with mock.patch.dict("os.environ", {"QUOTA_DEFAULT_WEEKLY_LIMIT": ""}):
            self.assertIsNone(default_limits().weekly_limit)
        # over-strict: env 가 없을 때 None 으로 떨어지면 안 된다(무제한 오배포).
        self.assertEqual(default_limits().daily_limit, DEFAULT_DAILY_LIMIT)


class LimitRepresentationTest(unittest.TestCase):
    """P5 — 무제한·정지·0회가 서로 다른 상태다."""

    def test_zero_is_not_the_same_as_suspended(self) -> None:
        zero = QuotaLimits(daily_limit=0, weekly_limit=0)
        suspended = QuotaLimits(daily_limit=10, weekly_limit=10,
                                status=QuotaStatus.SUSPENDED)
        self.assertNotEqual(zero, suspended)
        self.assertIs(zero.status, QuotaStatus.ACTIVE)

    def test_unlimited_is_none_and_can_apply_to_one_window_only(self) -> None:
        mixed = QuotaLimits(daily_limit=None, weekly_limit=30)
        self.assertIsNone(mixed.daily_limit)
        self.assertEqual(mixed.weekly_limit, 30)

    def test_unlimited_outranks_every_number(self) -> None:
        # P6 판정의 토대: 10 → None 은 상향, None → 10 은 하향이다.
        _immediate, deferred = split_change(
            QuotaLimits(10, 10), QuotaLimits(None, 10))
        self.assertFalse(deferred)
        _immediate, deferred = split_change(
            QuotaLimits(None, 10), QuotaLimits(10, 10))
        self.assertTrue(deferred)


class PolicyChangeEffectTest(unittest.TestCase):
    """P6 — 유리한 변경은 즉시, 불리한 변경은 주 경계에. 판정은 필드별."""

    def setUp(self) -> None:
        self.now = datetime(2026, 7, 8, 5, 0, tzinfo=UTC)  # 첫 주기 안
        self.repo = InMemoryQuotaPolicyRepository()
        self.service = QuotaPolicyService(self.repo, clock=lambda: self.now)

    def _set(self, target: QuotaLimits):
        return self.service.set_limits(
            user_id="u1", created_at=CREATED_AT, target=target)

    def test_raising_a_limit_takes_effect_immediately(self) -> None:
        policy = self._set(QuotaLimits(daily_limit=50, weekly_limit=200))
        self.assertEqual(policy.limits.daily_limit, 50)
        self.assertIsNone(policy.pending)
        self.assertEqual(self.service.limits_for("u1").daily_limit, 50)

    def test_lowering_a_limit_waits_for_the_end_of_the_current_week(self) -> None:
        policy = self._set(QuotaLimits(daily_limit=1, weekly_limit=1))
        # 지금은 옛 값 그대로다.
        self.assertEqual(policy.limits.daily_limit, DEFAULT_DAILY_LIMIT)
        self.assertIsNotNone(policy.pending)
        self.assertEqual(
            policy.pending.effective_at, next_week_boundary(CREATED_AT, self.now))
        # 경계 직전/직후를 함께 본다.
        just_before = policy.pending.effective_at - timedelta(seconds=1)
        self.assertEqual(
            effective_limits(policy, just_before).daily_limit, DEFAULT_DAILY_LIMIT)
        self.assertEqual(
            effective_limits(policy, policy.pending.effective_at).daily_limit, 1)

    def test_a_mixed_change_splits_per_field(self) -> None:
        # 일은 올리고 주는 내린다 — 덩어리로 판정하면 한쪽이 다른 쪽을 끌고 간다.
        policy = self._set(QuotaLimits(daily_limit=50, weekly_limit=1))
        self.assertEqual(policy.limits.daily_limit, 50)               # 즉시
        self.assertEqual(policy.limits.weekly_limit, DEFAULT_WEEKLY_LIMIT)  # 유예
        self.assertEqual(policy.pending.limits.weekly_limit, 1)
        self.assertEqual(policy.pending.limits.daily_limit, 50)

    def test_suspending_waits_but_lifting_a_suspension_is_immediate(self) -> None:
        # 오너 결정(2026-08-03): 정지가 최대 1주 늦는 것을 받아들인다 — 사용감이 먼저.
        # 즉시 차단이 필요하면 계정 비활성화가 세션까지 끊는다(별도 수단).
        suspend = self._set(QuotaLimits(status=QuotaStatus.SUSPENDED))
        self.assertIs(suspend.limits.status, QuotaStatus.ACTIVE)
        self.assertIs(suspend.pending.limits.status, QuotaStatus.SUSPENDED)

        self.now = suspend.pending.effective_at
        self.service.clear_pending("u1")
        lift = self._set(QuotaLimits(status=QuotaStatus.ACTIVE))
        self.assertIs(lift.limits.status, QuotaStatus.ACTIVE)
        self.assertIsNone(lift.pending)

    def test_a_second_change_replaces_the_pending_one(self) -> None:
        first = self._set(QuotaLimits(daily_limit=1, weekly_limit=1))
        self.assertEqual(first.pending.limits.daily_limit, 1)
        second = self._set(QuotaLimits(daily_limit=3, weekly_limit=3))
        self.assertEqual(second.pending.limits.daily_limit, 3)

    def test_settling_a_fired_pending_change_is_a_no_op_for_the_reader(self) -> None:
        # clear_pending 은 선택적 정리다 — 굳히기 전과 후의 '유효 한도'가 같아야 한다.
        policy = self._set(QuotaLimits(daily_limit=2, weekly_limit=2))
        self.now = policy.pending.effective_at
        before = self.service.limits_for("u1")
        settled = self.service.clear_pending("u1")
        self.assertEqual(before, settled.limits)
        self.assertIsNone(settled.pending)
        self.assertEqual(self.service.limits_for("u1"), before)

    def test_settling_before_the_boundary_changes_nothing(self) -> None:
        # over-strict: 발효 전에 굳혀 버리면 하향이 즉시 적용된 것과 같아진다.
        policy = self._set(QuotaLimits(daily_limit=2, weekly_limit=2))
        self.now = policy.pending.effective_at - timedelta(seconds=1)
        kept = self.service.clear_pending("u1")
        self.assertIsNotNone(kept.pending)
        self.assertEqual(kept.limits.daily_limit, DEFAULT_DAILY_LIMIT)


class NoEnforcementHereTest(unittest.TestCase):
    """8.1은 저장 계약까지다 — 차감·차단은 8.3."""

    def test_the_module_exposes_no_counter_or_consumption_api(self) -> None:
        from services.application.app.quota import policy

        forbidden = [
            name for name in dir(policy)
            if any(word in name.lower()
                   for word in ("consume", "charge", "deduct", "counter", "usage"))
        ]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
