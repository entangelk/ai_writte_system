"""LoginFailureGuard — the /auth/login brute-force bound (2026-08-22).

Domain cells against the in-memory repository. The lockout math is policy, so
both directions are pinned: under-strict (a guard that never locks) fails the
first cells; over-strict (a guard that locks too early, never resets, or counts
across windows) fails the later ones.
"""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.login_guard import (
    InMemoryFailureRecordRepository,
    LoginFailureGuard,
)

_T0 = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
_WINDOW = timedelta(seconds=300)


def _guard():
    clock = {"now": _T0}
    guard = LoginFailureGuard(
        InMemoryFailureRecordRepository(),
        max_failures=5,
        lockout=_WINDOW,
        clock=lambda: clock["now"],
    )
    return guard, clock


class LoginFailureGuardTest(unittest.TestCase):
    def test_failures_below_the_threshold_never_lock(self) -> None:
        guard, _ = _guard()
        for _ in range(4):
            guard.register_failure("alice")
        self.assertFalse(guard.is_locked("alice"))

    def test_the_fifth_failure_locks(self) -> None:
        guard, _ = _guard()
        for _ in range(5):
            guard.register_failure("alice")
        self.assertTrue(guard.is_locked("alice"))

    def test_the_lock_expires_after_one_window(self) -> None:
        guard, clock = _guard()
        for _ in range(5):
            guard.register_failure("alice")
        clock["now"] = _T0 + _WINDOW + timedelta(seconds=1)
        self.assertFalse(guard.is_locked("alice"))

    def test_the_counter_starts_clean_after_expiry(self) -> None:
        # Over-strict guard: if the counter survived its own lockout, the very
        # next failure (not the fifth) would re-lock — an escalation ladder the
        # policy explicitly is not.
        guard, clock = _guard()
        for _ in range(5):
            guard.register_failure("alice")
        clock["now"] = _T0 + _WINDOW + timedelta(seconds=1)
        guard.register_failure("alice")  # first failure of a fresh cycle
        self.assertFalse(guard.is_locked("alice"))

    def test_a_stale_counter_resets_on_read(self) -> None:
        # Four failures, then a gap longer than the window: the count carries
        # no signal anymore, so it must not accumulate toward a lock.
        guard, clock = _guard()
        for _ in range(4):
            guard.register_failure("alice")
        clock["now"] = _T0 + _WINDOW + timedelta(seconds=1)
        for _ in range(4):
            guard.register_failure("alice")
        self.assertFalse(guard.is_locked("alice"))

    def test_success_clears_the_counter(self) -> None:
        guard, _ = _guard()
        for _ in range(4):
            guard.register_failure("alice")
        guard.register_success("alice")
        for _ in range(4):
            guard.register_failure("alice")
        self.assertFalse(guard.is_locked("alice"))

    def test_locks_are_per_username(self) -> None:
        guard, _ = _guard()
        for _ in range(5):
            guard.register_failure("alice")
        self.assertTrue(guard.is_locked("alice"))
        self.assertFalse(guard.is_locked("bob"))

    def test_unknown_usernames_register_failures_too(self) -> None:
        # The guard counts *attempts*, not accounts: probing random usernames
        # must lock the probed name just the same.
        guard, _ = _guard()
        for _ in range(5):
            guard.register_failure("ghost")
        self.assertTrue(guard.is_locked("ghost"))

    def test_a_failure_during_a_lock_neither_clears_nor_extends_it(self) -> None:
        # 검증 H-1(2026-08-22)의 재결함 방지. 단일 워커 배포에선 라우트의 조기
        # is_locked 검사가 이 상태를 만들지 못하지만, P-6 이 Mongo 저장을 택한
        # 근거가 다중 인스턴스 확장이고 거기서 두 요청이 조기 검사를 통과해
        # 경쟁한다. 그때 이 메서드가 카운터 행을 새로 쓰면 locked_until 이
        # 지워져 **잠금이 스스로 해제**된다.
        #
        # under-strict: 잠금 중 실패가 잠금을 지우면 첫 단정이 실패한다.
        # over-strict: 잠금을 연장하면(에스컬레이션) 둘째 단정이 실패한다 —
        # 잠금은 속도 방지턱이지 사다리가 아니다.
        guard, clock = _guard()
        for _ in range(5):
            guard.register_failure("alice")
        locked_until_before = guard._repo.get("alice").locked_until

        clock["now"] = _T0 + timedelta(seconds=30)  # well inside the lockout
        guard.register_failure("alice")

        self.assertTrue(guard.is_locked("alice"))
        self.assertEqual(
            guard._repo.get("alice").locked_until, locked_until_before,
            "잠금 중 실패는 잠금 만료 시각을 바꾸지 않는다(연장도 해제도 아님)",
        )


if __name__ == "__main__":
    unittest.main()
