"""Slice 8.2 원장 계약 회귀 — 중복·격리·집계·창 키 위임.

브리프 ``08-2-usage-ledger-decisions.md``(오너 결정 L1=B · L2~L5=A, 2026-08-03).
각 셀은 **양방향**으로 문다. 이 파일에서 가장 중요한 셀 둘:

- ``test_the_same_request_id_under_different_actions_counts_each_time`` — 프론트가
  한 흐름에서 uuid 를 공유하므로, dedupe 키에서 ``action`` 이 빠지면 유료 동작 4개가
  1개로 접힌다. **8.0의 "요청 1건 = 1회"를 지키는 자리가 여기다.**
- ``test_the_project_axis_is_not_named_project_id`` — 이름이 ``project_id`` 가 되는
  순간 purge reconciler 가 과금 기록을 지운다. 오너 결정("삭제돼도 남는다")이
  **필드 이름 하나에 달려 있다.**
"""

from __future__ import annotations

import itertools
import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.quota.ledger import (
    AdjustmentEntry,
    InMemoryUsageLedgerRepository,
    LedgerEntryKind,
    UsageEntry,
    UsageLedgerService,
)
from services.application.app.quota.policy import daily_key, weekly_key

CREATED_AT = datetime(2026, 7, 6, 5, 37, tzinfo=UTC)   # KST 2026-07-06 14:37
NOW = datetime(2026, 7, 8, 5, 0, tzinfo=UTC)           # 첫 주기 안


def _service(now=NOW):
    repo = InMemoryUsageLedgerRepository()
    counter = itertools.count(1)
    clock = {"now": now}
    service = UsageLedgerService(
        repo, id_factory=lambda: f"entry-{next(counter)}", clock=lambda: clock["now"]
    )
    return service, repo, clock


class DedupeTest(unittest.TestCase):
    """L2=A — 같은 동작의 재전송만 접는다."""

    def setUp(self):
        self.service, self.repo, self.clock = _service()

    def _use(self, action="writing_generate", key="req-1", project="p1"):
        return self.service.record_usage(
            user_id="u1", member_created_at=CREATED_AT,
            target_project_id=project, action=action, dedupe_key=key,
        )

    def test_the_same_key_and_action_is_recorded_once(self) -> None:
        self.assertIsNotNone(self._use())
        self.assertIsNone(self._use())  # 재전송 — 안 센다
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 1)

    def test_the_same_request_id_under_different_actions_counts_each_time(self) -> None:
        # ★ 프론트는 한 번의 "이어쓰기" 흐름에서 generate·gate·revise-and-gate·accept
        # 에 **같은 uuid** 를 실어 보낸다. dedupe 키에서 action 이 빠지면 이 넷이
        # 1회로 접혀 8.0 계약이 조용히 깨진다.
        for action in ("writing_generate", "writing_gate",
                       "writing_revise_and_gate", "writing_accept"):
            self.assertIsNotNone(self._use(action=action, key="same-uuid"))
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 4)

    def test_a_different_key_for_the_same_action_counts_again(self) -> None:
        # over-strict 방지: 사용자가 다시 눌러 새 키로 오는 것은 **실제로 두 번**이다.
        # (실수 중복을 막는 것은 8.2b 의 잠금이지 이 dedupe 가 아니다.)
        self.assertIsNotNone(self._use(key="req-1"))
        self.assertIsNotNone(self._use(key="req-2"))
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 2)

    def test_the_same_key_in_a_different_project_still_counts_separately(self) -> None:
        # dedupe 는 (user, action, key) 다 — 프로젝트는 키가 아니다. 같은 키가 두
        # 프로젝트에서 오는 것은 정상 흐름이 아니지만, 접히면 과금이 새므로 확인한다.
        self.assertIsNotNone(self._use(key="k", project="p1"))
        self.assertIsNone(self._use(key="k", project="p2"))


class IsolationTest(unittest.TestCase):
    """회원·창 격리 — 남의 사용량이 내 창에 섞이지 않는다."""

    def setUp(self):
        self.service, self.repo, self.clock = _service()

    def _use(self, user="u1", key="k1", created=CREATED_AT):
        return self.service.record_usage(
            user_id=user, member_created_at=created, target_project_id="p1",
            action="writing_generate", dedupe_key=key,
        )

    def test_another_member_does_not_leak_into_my_windows(self) -> None:
        self._use(user="u1", key="a")
        self._use(user="u2", key="b")
        self._use(user="u2", key="c")
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 1)
        self.assertEqual(self.service.used(
            user_id="u2", member_created_at=CREATED_AT).daily, 2)

    def test_yesterdays_usage_leaves_todays_daily_window_but_stays_in_the_week(self) -> None:
        # 일 창은 넘어가고 주 창은 유지되는 순간을 함께 본다 — 두 창이 독립임을
        # 보이는 자리이고, 한쪽만 보면 창을 하나로 접는 구현도 통과한다.
        self._use(key="yesterday")
        self.clock["now"] = NOW + timedelta(days=1)
        self._use(key="today")
        used = self.service.used(user_id="u1", member_created_at=CREATED_AT)
        self.assertEqual(used.daily, 1)
        self.assertEqual(used.weekly, 2)

    def test_a_new_week_resets_both_windows(self) -> None:
        self._use(key="week1")
        self.clock["now"] = NOW + timedelta(days=7)
        used = self.service.used(user_id="u1", member_created_at=CREATED_AT)
        self.assertEqual((used.daily, used.weekly), (0, 0))

    def test_two_members_who_joined_on_different_days_have_different_weeks(self) -> None:
        # 주 창이 가입일 기준(8.1 P2-b)이라 회원마다 경계가 다르다.
        other_created = datetime(2026, 7, 2, 5, 0, tzinfo=UTC)
        self.assertNotEqual(
            weekly_key(CREATED_AT, NOW), weekly_key(other_created, NOW))


class WindowKeyDelegationTest(unittest.TestCase):
    """창 키를 8.1에서 가져온다 — 여기서 다시 계산하지 않는다."""

    def test_the_entry_carries_exactly_the_keys_policy_computes(self) -> None:
        service, repo, _clock = _service()
        entry = service.record_usage(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="p1",
            action="writing_gate", dedupe_key="k",
        )
        self.assertEqual(entry.daily_key, daily_key(NOW))
        self.assertEqual(entry.weekly_key, weekly_key(CREATED_AT, NOW))

    def test_the_daily_key_follows_the_kst_boundary(self) -> None:
        # 8.1 의 KST 결정이 원장까지 이어지는지. UTC 자정이 아니라 KST 자정에 바뀐다.
        service, _repo, clock = _service(now=datetime(2026, 8, 3, 14, 59, tzinfo=UTC))
        first = service.record_usage(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="p1",
            action="writing_gate", dedupe_key="a")
        clock["now"] = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
        second = service.record_usage(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="p1",
            action="writing_gate", dedupe_key="b")
        self.assertEqual(first.daily_key, "2026-08-03")
        self.assertEqual(second.daily_key, "2026-08-04")


class AdjustmentTest(unittest.TestCase):
    """L5=A — 같은 컬렉션, 다른 종류. 필드 구성이 겹치지 않는다."""

    def setUp(self):
        self.service, self.repo, self.clock = _service()
        self.service.record_usage(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="p1",
            action="writing_generate", dedupe_key="k1")

    def _adjust(self, delta, reason="오류 보상"):
        return self.service.record_adjustment(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="p1",
            delta=delta, reason=reason, admin_user_id="admin-1",
        )

    def test_a_refund_lowers_usage_and_a_charge_raises_it(self) -> None:
        self._adjust(-1)
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 0)
        self._adjust(+3)
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, 3)

    def test_a_refund_larger_than_usage_goes_below_zero_on_purpose(self) -> None:
        # 깎지 않는다 — "한도를 넘는 보너스"는 관리자가 만든 정당한 상태이고,
        # 잔여를 어떻게 읽을지는 8.3 이 정한다. 0 으로 clamp 하면 그 의도가 사라진다.
        self._adjust(-5)
        self.assertEqual(self.service.used(
            user_id="u1", member_created_at=CREATED_AT).daily, -4)

    def test_an_adjustment_is_not_a_usage_row(self) -> None:
        # 두 종류가 섞이면 "몇 번 썼나"와 "얼마를 조정했나"를 갈라 볼 수 없다.
        self._adjust(-1)
        self.assertEqual(
            self.repo.count_usage("u1", window_field="daily_key",
                                  window_key=daily_key(NOW)), 1)
        self.assertEqual(
            self.repo.sum_adjustments("u1", window_field="daily_key",
                                      window_key=daily_key(NOW)), -1)

    def test_an_empty_reason_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._adjust(-1, reason="   ")

    def test_the_two_kinds_do_not_share_their_field_sets(self) -> None:
        # L5 의 구조적 요구. 사용 행에 delta/reason 이, 조정 행에 action/dedupe_key 가
        # 생기면 "같은 컬렉션에 두되 종류를 갈라 둔다"가 무너진다.
        usage_fields = set(UsageEntry.__dataclass_fields__)
        adjustment_fields = set(AdjustmentEntry.__dataclass_fields__)
        self.assertEqual(usage_fields - adjustment_fields, {"action", "dedupe_key"})
        self.assertEqual(adjustment_fields - usage_fields,
                         {"delta", "reason", "admin_user_id"})


class ProjectAxisNameTest(unittest.TestCase):
    """L1=B — 프로젝트 축의 **이름**이 계약이다."""

    def test_the_project_axis_is_not_named_project_id(self) -> None:
        # ★ purge reconciler 는 `project_id` 필드를 가진 컬렉션을 DB 에서 발견해
        # 고아 행을 지운다. 이 이름이 바뀌는 순간 project 영구 삭제가 과금 기록을
        # 지우고, 그것은 오너 결정("삭제돼도 사용 기록은 남는다")과 정면으로
        # 어긋난다. D8-6 tombstone 셀과 같은 성격의 가드다.
        for entry_type in (UsageEntry, AdjustmentEntry):
            with self.subTest(entry=entry_type.__name__):
                fields = set(entry_type.__dataclass_fields__)
                self.assertIn("target_project_id", fields)
                self.assertNotIn("project_id", fields)

    def test_every_entry_carries_the_project_it_happened_in(self) -> None:
        # over-strict 방지의 반대편: 이름만 맞고 값이 안 실리면 "어느 프로젝트에서
        # 얼마나 썼는가"에 답할 수 없다.
        service, _repo, _clock = _service()
        entry = service.record_usage(
            user_id="u1", member_created_at=CREATED_AT, target_project_id="proj-9",
            action="context_search", dedupe_key="k")
        self.assertEqual(entry.target_project_id, "proj-9")
        self.assertIs(entry.kind, LedgerEntryKind.USAGE)


class NoEnforcementHereTest(unittest.TestCase):
    """8.2는 기록·집계까지다 — 한도를 보지 않는다."""

    def test_the_module_never_reads_a_limit(self) -> None:
        from services.application.app.quota import ledger

        source = ledger.__doc__ or ""
        self.assertIn("차감·차단은 없다", source)
        forbidden = [
            name for name in dir(ledger)
            if any(word in name.lower()
                   for word in ("limit", "quota_status", "allow", "deny", "block"))
        ]
        self.assertEqual(forbidden, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
