"""Slice 8.2b 잠금 계약 회귀 — 진행 중 보호 · 최소 창 · 축 · 강제 재차지 · fencing.

브리프 ``08-2b-duplicate-request-lock-decisions.md``(오너 결정 G1=C · G2~G6=A,
2026-08-03). 각 셀은 **양방향**으로 문다. 이 파일에서 가장 중요한 셀 셋:

- ``test_an_expired_lock_is_reclaimed_even_though_the_document_is_still_there`` —
  판정이 **문서 존재 여부가 아니라 ``expires_at`` 비교**임을 단정한다. 존재로
  판정하면 Mongo TTL 주기(~60초) 때문에 5초가 최대 1분이 되는데, **fake 에는 TTL
  주기가 없어 운영에서만 보인다**(브리프 §1.3).
- ``test_the_earlier_request_cannot_release_the_new_owners_lock`` — G4(강제 재차지)를
  고른 순간 필수가 된 fencing. 먼저 시작한 요청이 완료되며 남의 잠금을 풀면 새 주인의
  보호가 사라진다(브리프 §0.4).
- ``test_the_lease_is_longer_than_the_minimum_window`` — 최소 창(제품 정책)과
  lease(기술 한계)는 **다른 상수**이며 합치면 둘 다 틀린다(브리프 §0.2).
"""

from __future__ import annotations

import itertools
import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.quota.lock import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MINIMUM_WINDOW_SECONDS,
    InMemoryRequestLockRepository,
    LockBlocked,
    LockGranted,
    RequestLock,
    RequestLockService,
    cooldown_until,
    lock_key,
)

NOW = datetime(2026, 8, 3, 5, 0, tzinfo=UTC)

USER = "user-1"
ACTION = "writing_generate"
PROJECT = "proj-1"

#: 셀이 읽기 쉽도록 픽스처가 쓰는 값을 못박는다. 모듈 기본값과 같은지는
#: `ConstantsTest` 가 따로 단정한다 — 기본값이 바뀌어도 이 파일의 산수는 안 흔들린다.
WINDOW = 5
LEASE = 180


def _service(now=NOW, *, minimum_window_seconds=WINDOW, lease_seconds=LEASE):
    repo = InMemoryRequestLockRepository()
    holders = itertools.count(1)
    clock = {"now": now}
    service = RequestLockService(
        repo,
        holder_factory=lambda: f"holder-{next(holders)}",
        clock=lambda: clock["now"],
        minimum_window_seconds=minimum_window_seconds,
        lease_seconds=lease_seconds,
    )
    return service, repo, clock


class _LockTestCase(unittest.TestCase):
    def setUp(self):
        self.service, self.repo, self.clock = _service()

    def claim(self, *, user=USER, action=ACTION, project=PROJECT):
        return self.service.claim(
            user_id=user, action=action, target_project_id=project)

    def force_claim(self, *, user=USER, action=ACTION, project=PROJECT):
        return self.service.force_claim(
            user_id=user, action=action, target_project_id=project)

    def release(self, holder, *, user=USER, action=ACTION, project=PROJECT):
        return self.service.release(
            user_id=user, action=action, target_project_id=project, holder=holder)

    def advance(self, seconds):
        self.clock["now"] = self.clock["now"] + timedelta(seconds=seconds)


class ExclusionTest(_LockTestCase):
    """이 슬라이스의 존재 이유 — 같은 요청은 하나만 통과한다."""

    def test_only_one_of_two_requests_at_the_same_instant_wins(self) -> None:
        # 같은 시각에 들어온 두 요청(= 연타). 시계를 움직이지 않는 것이 핵심이다.
        first = self.claim()
        second = self.claim()
        self.assertIsInstance(first, LockGranted)
        self.assertIsInstance(second, LockBlocked)

    def test_a_granted_claim_returns_a_holder_token(self) -> None:
        # over-strict 방지 + G4/fencing 의 전제. 토큰이 없으면 해제 소유권을 못 가린다.
        granted = self.claim()
        self.assertTrue(granted.holder)

    def test_two_grants_never_share_a_token(self) -> None:
        first = self.claim()
        self.advance(LEASE + 1)
        second = self.claim()
        self.assertNotEqual(first.holder, second.holder)

    def test_an_expired_lock_is_reclaimed_even_though_the_document_is_still_there(
        self,
    ) -> None:
        # ★ 판정은 `expires_at` 비교다. fake 는 TTL 을 흉내 내지 않으므로 문서는
        # 그대로 남아 있는데, 그래도 차지에 성공해야 한다. 존재 여부로 판정하는
        # 구현은 여기서 막힌다(운영에서는 5초가 최대 1분이 되는 그 결함).
        granted = self.claim()
        self.advance(LEASE + 1)
        key = lock_key(USER, ACTION, PROJECT)
        self.assertIsNotNone(self.repo.peek(key))  # 문서는 아직 있다
        again = self.claim()
        self.assertIsInstance(again, LockGranted)
        self.assertNotEqual(again.holder, granted.holder)

    def test_the_fake_never_expires_documents_on_its_own(self) -> None:
        # 위 셀의 가드의 가드 — fake 가 TTL 을 흉내 내기 시작하면 위 셀은 아무것도
        # 증명하지 못한다(그때는 문서가 사라져서 통과하기 때문이다).
        self.claim()
        self.advance(LEASE * 10)
        self.assertIsNotNone(self.repo.peek(lock_key(USER, ACTION, PROJECT)))


class WindowTest(_LockTestCase):
    """G1=C — 진행 중과 최소 창은 **두 구간**이고 둘 다 막는다."""

    def test_a_request_still_running_blocks_the_next_one(self) -> None:
        self.claim()
        self.advance(10)  # 최소 창(5초)은 지났지만 생성은 아직 진행 중이다
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)

    def test_the_cooldown_still_blocks_just_before_the_minimum_window_ends(self) -> None:
        granted = self.claim()
        self.advance(1)
        self.assertTrue(self.release(granted.holder))
        self.advance(3.9)  # 차지 시각 + 4.9초
        self.assertIsInstance(self.claim(), LockBlocked)

    def test_a_new_claim_succeeds_right_after_the_minimum_window_ends(self) -> None:
        # over-strict 방지 짝: 경계 직후에는 반드시 통과해야 한다. 냉각이 lease 만큼
        # 이어지는 구현(해제가 만료를 안 당기는 구현)은 여기서 막힌다.
        granted = self.claim()
        self.advance(1)
        self.assertTrue(self.release(granted.holder))
        self.advance(4)  # 차지 시각 + 5초 정각
        self.assertIsInstance(self.claim(), LockGranted)

    def test_releasing_after_the_minimum_window_has_passed_unlocks_immediately(
        self,
    ) -> None:
        # 오래 걸린 요청(23초)에는 냉각이 남지 않는다 — 최소 창은 차지 시각 기준이지
        # 완료 시각 기준이 아니다. 완료 기준으로 잡으면 여기서 5초를 더 기다린다.
        granted = self.claim()
        self.advance(23)
        self.assertTrue(self.release(granted.holder))
        self.assertIsInstance(self.claim(), LockGranted)

    def test_the_cooldown_is_measured_from_the_claim_not_the_release(self) -> None:
        self.assertEqual(
            cooldown_until(NOW, NOW + timedelta(seconds=1), timedelta(seconds=5)),
            NOW + timedelta(seconds=5),
        )
        self.assertEqual(
            cooldown_until(NOW, NOW + timedelta(seconds=23), timedelta(seconds=5)),
            NOW + timedelta(seconds=23),
        )


class BlockedReasonTest(_LockTestCase):
    """G5=A — 실패는 **남은 시간과 진행 중 여부**를 돌려준다."""

    def test_being_blocked_while_the_request_runs_says_in_flight(self) -> None:
        self.claim()
        self.advance(10)
        blocked = self.claim()
        self.assertTrue(blocked.in_flight)

    def test_being_blocked_during_the_cooldown_does_not_say_in_flight(self) -> None:
        # ★ 이유는 저장 필드 `released_at` 에서 **파생**된다 — G5 를 위해 필드를
        # 늘리지 않는다는 §0.1 의 주장이 여기서 확인된다.
        granted = self.claim()
        self.advance(1)
        self.release(granted.holder)
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)
        self.assertFalse(blocked.in_flight)

    def test_the_remaining_seconds_shrink_as_time_passes(self) -> None:
        self.claim()
        self.advance(1)
        first = self.claim().retry_after_seconds
        self.advance(60)
        second = self.claim().retry_after_seconds
        self.assertEqual(first, LEASE - 1)
        self.assertEqual(second, LEASE - 61)

    def test_the_cooldown_reports_the_seconds_left_in_the_minimum_window(self) -> None:
        granted = self.claim()
        self.advance(1)
        self.release(granted.holder)
        self.advance(1)
        self.assertEqual(self.claim().retry_after_seconds, 3)

    def test_a_blocked_claim_never_reports_zero_seconds(self) -> None:
        # 0 을 돌려주면 8.3 이 "지금 다시 하세요"라고 말하면서 막는 화면을 만든다.
        granted = self.claim()
        self.advance(1)
        self.release(granted.holder)
        self.advance(3.5)
        self.assertEqual(self.claim().retry_after_seconds, 1)


class KeyAxisTest(_LockTestCase):
    """G2=A — 축은 `(user_id, action, target_project_id)` 셋 다다."""

    def test_the_normal_chain_is_not_blocked(self) -> None:
        # generate 직후 gate 가 자동으로 뒤따른다. action 이 축에서 빠지면 제품의
        # 정상 흐름이 자기 자신을 막는다.
        self.assertIsInstance(self.claim(action="writing_generate"), LockGranted)
        self.assertIsInstance(self.claim(action="writing_gate"), LockGranted)

    def test_another_project_is_not_blocked(self) -> None:
        self.assertIsInstance(self.claim(project="proj-1"), LockGranted)
        self.assertIsInstance(self.claim(project="proj-2"), LockGranted)

    def test_another_member_is_not_blocked(self) -> None:
        self.assertIsInstance(self.claim(user="user-1"), LockGranted)
        self.assertIsInstance(self.claim(user="user-2"), LockGranted)

    def test_the_same_triple_is_blocked(self) -> None:
        # over-strict 방지의 반대편 — 축을 넓히면(예: 요청 본문까지) 실수 중복이 샌다.
        self.assertIsInstance(self.claim(), LockGranted)
        self.assertIsInstance(self.claim(), LockBlocked)

    def test_the_key_carries_the_three_axes_in_order(self) -> None:
        self.assertEqual(lock_key("u", "a", "p"), "u:a:p")


class ForceClaimTest(_LockTestCase):
    """G4=A — 확인된 요청은 살아 있는 잠금을 덮어쓴다(크래시 복구 경로이기도 하다)."""

    def test_a_confirmed_request_takes_the_lock_from_the_current_holder(self) -> None:
        first = self.claim()
        forced = self.force_claim()
        self.assertNotEqual(forced.holder, first.holder)

    def test_a_click_right_after_a_forced_claim_is_blocked_again(self) -> None:
        # ★ 확인이 잠금을 **끄는** 것이 아니라 **옮기는** 것이다. 확인 뒤 잠금이
        # 사라지는 구현은 세 번째 클릭을 그대로 통과시킨다.
        self.claim()
        self.force_claim()
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)
        self.assertTrue(blocked.in_flight)

    def test_a_forced_claim_on_a_free_key_just_claims_it(self) -> None:
        self.assertIsInstance(self.force_claim(), LockGranted)

    def test_a_crashed_request_is_unblocked_by_confirming(self) -> None:
        # 크래시하면 해제가 안 불린다 — lease 만료까지 최대 2분을 기다리는 대신
        # 사용자가 확인으로 즉시 뚫는다(브리프 §1.6).
        self.claim()
        self.advance(30)
        self.assertIsInstance(self.claim(), LockBlocked)
        self.assertIsInstance(self.force_claim(), LockGranted)


class FencingTest(_LockTestCase):
    """§0.4 — 해제는 **자기 토큰일 때만** 동작한다."""

    def test_the_earlier_request_cannot_release_the_new_owners_lock(self) -> None:
        # ★ A 가 23초짜리 생성 중 → 사용자가 확인 → B 가 강제 재차지 → **A 가
        # 완료되며 해제를 부른다**. 소유권 검사가 없으면 B 의 보호가 사라진다.
        first = self.claim()
        self.advance(5)
        self.force_claim()
        self.advance(18)
        self.assertFalse(self.release(first.holder))
        blocked = self.claim()
        self.assertIsInstance(blocked, LockBlocked)
        self.assertTrue(blocked.in_flight)  # B 는 아직 진행 중이다

    def test_the_owner_releases_normally(self) -> None:
        # over-strict 짝: 소유권 검사가 정상 해제까지 막으면 냉각이 lease 내내 이어진다.
        granted = self.claim()
        self.advance(23)
        self.assertTrue(self.release(granted.holder))
        self.assertIsInstance(self.claim(), LockGranted)

    def test_the_new_owner_releases_its_own_lock(self) -> None:
        self.claim()
        forced = self.force_claim()
        self.advance(23)
        self.assertTrue(self.release(forced.holder))

    def test_releasing_a_key_that_was_never_claimed_is_a_no_op(self) -> None:
        self.assertFalse(self.release("holder-nobody"))

    def test_a_stale_release_does_not_shorten_the_new_owners_lease(self) -> None:
        # 소유권 검사가 "실패를 돌려주되 쓰기는 한다"로 반쯤 구현되는 것을 막는다.
        first = self.claim()
        self.force_claim()
        self.advance(1)
        before = self.claim().retry_after_seconds
        self.release(first.holder)
        self.assertEqual(self.claim().retry_after_seconds, before)


class ConstantsTest(unittest.TestCase):
    """§0.2 — 두 상수는 다른 것이고, 합치면 둘 다 틀린다."""

    def test_the_lease_is_longer_than_the_minimum_window(self) -> None:
        self.assertGreater(DEFAULT_LEASE_SECONDS, DEFAULT_MINIMUM_WINDOW_SECONDS)

    def test_the_fixture_uses_the_shipped_defaults(self) -> None:
        # 위 셀들의 산수가 배포 기본값과 같은 것을 재는지 확인한다.
        self.assertEqual((WINDOW, LEASE),
                         (DEFAULT_MINIMUM_WINDOW_SECONDS, DEFAULT_LEASE_SECONDS))

    def test_the_lease_outlives_the_longest_synchronous_request(self) -> None:
        # lease 는 기술 한계다 — gateway timeout(120초)보다 길지 않으면 아직 살아 있는
        # 요청의 잠금이 풀려 중복이 샌다(브리프 §0.3 의 알려진 한계가 상시화된다).
        self.assertGreater(DEFAULT_LEASE_SECONDS, 120)

    def test_the_minimum_window_is_the_number_the_owner_gave(self) -> None:
        self.assertEqual(DEFAULT_MINIMUM_WINDOW_SECONDS, 5)

    def test_a_lease_shorter_than_the_minimum_window_is_refused(self) -> None:
        # 두 값을 한 상수로 합치려는 리팩터링이 여기서 막힌다.
        with self.assertRaises(ValueError):
            _service(minimum_window_seconds=10, lease_seconds=10)

    def test_the_two_values_are_configurable_apart(self) -> None:
        service, _repo, clock = _service(minimum_window_seconds=2, lease_seconds=30)
        granted = service.claim(
            user_id=USER, action=ACTION, target_project_id=PROJECT)
        clock["now"] = NOW + timedelta(seconds=1)
        service.release(user_id=USER, action=ACTION, target_project_id=PROJECT,
                        holder=granted.holder)
        clock["now"] = NOW + timedelta(seconds=2)
        self.assertIsInstance(
            service.claim(user_id=USER, action=ACTION, target_project_id=PROJECT),
            LockGranted,
        )

    def test_the_environment_can_override_both(self) -> None:
        import os

        from services.application.app.quota import lock

        os.environ["QUOTA_LOCK_MINIMUM_WINDOW_SECONDS"] = "9"
        os.environ["QUOTA_LOCK_LEASE_SECONDS"] = "300"
        try:
            self.assertEqual(lock.configured_minimum_window_seconds(), 9)
            self.assertEqual(lock.configured_lease_seconds(), 300)
        finally:
            del os.environ["QUOTA_LOCK_MINIMUM_WINDOW_SECONDS"]
            del os.environ["QUOTA_LOCK_LEASE_SECONDS"]
        self.assertEqual(
            lock.configured_minimum_window_seconds(), DEFAULT_MINIMUM_WINDOW_SECONDS)


class StoredShapeTest(_LockTestCase):
    """§0.1 — 저장되는 것은 다섯 필드뿐이고 상태 둘은 `released_at` 으로 갈린다."""

    def test_the_lock_carries_exactly_the_agreed_fields(self) -> None:
        self.assertEqual(
            set(RequestLock.__dataclass_fields__),
            {"key", "holder", "claimed_at", "expires_at", "released_at"},
        )

    def test_a_claim_marks_the_lock_as_in_flight(self) -> None:
        self.claim()
        lock = self.repo.peek(lock_key(USER, ACTION, PROJECT))
        self.assertIsNone(lock.released_at)
        self.assertEqual(lock.expires_at, NOW + timedelta(seconds=LEASE))

    def test_reclaiming_an_expired_lock_clears_the_previous_release(self) -> None:
        # `released_at` 이 안 지워지면 새 요청이 "냉각 중"으로 보고돼 8.3 이 "방금
        # 요청했습니다"라고 말한다 — 실제로는 지금 생성 중인데.
        granted = self.claim()
        self.advance(1)
        self.release(granted.holder)
        self.advance(10)
        self.claim()
        self.advance(1)
        self.assertTrue(self.claim().in_flight)


class NoEnforcementHereTest(unittest.TestCase):
    """이 슬라이스는 저장 의미론까지다 — HTTP·차감은 8.3이다."""

    def test_the_module_does_not_know_about_status_codes_or_quotas(self) -> None:
        from pathlib import Path

        from services.application.app.quota import lock

        source = Path(lock.__file__).read_text(encoding="utf-8")
        body = source.split('"""', 2)[-1]  # 모듈 docstring 은 8.3을 설명해도 된다
        for forbidden in ("429", "HTTPException", "daily_limit", "record_usage"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
