"""Login failure guard — the brute-force defense for ``/auth/login``.

Signup approval (owner 2026-08-22) opened a public account-request surface,
and the security review the same day measured that login had **no** online
brute-force defense at all — Argon2's slowness bounds the rate but nothing
bounded the attempts. This module is that bound (plans/
auth-signup-approval-decisions.md P-6).

Axis choice: **username**, not IP. The nginx path (5520) and the direct path
(8520) would disagree about what a client IP even is, so an IP axis is deferred
until an X-Forwarded-For trust policy exists. The known trade-off — anyone can
lock *someone else's* username out for the window by failing on purpose — is
accepted because the window is short; making it an owner decision would be
re-litigating what the owner already chose ("함께 담기", 2026-08-22).

The guard answers **before** Argon2 runs, so a locked-out attempt is cheap on
purpose. That leaks "this username is locked right now" by timing — which is
fine: the lock is a state the *attacker's own failures* created, so the only
party that learns anything new is the legitimate owner, who is told the same
thing by waiting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

DEFAULT_MAX_FAILURES = 5
DEFAULT_LOCKOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class FailureRecord:
    failures: int
    last_failure_at: datetime
    locked_until: datetime | None


class FailureRecordRepository(Protocol):
    def get(self, username: str) -> FailureRecord | None: ...
    def put(self, username: str, record: FailureRecord) -> None: ...
    def clear(self, username: str) -> None: ...


class InMemoryFailureRecordRepository:
    def __init__(self) -> None:
        self._records: dict[str, FailureRecord] = {}

    def get(self, username: str) -> FailureRecord | None:
        return self._records.get(username)

    def put(self, username: str, record: FailureRecord) -> None:
        self._records[username] = record

    def clear(self, username: str) -> None:
        self._records.pop(username, None)


class LoginFailureGuard:
    """Per-username failure counting with a short lockout.

    Policy: N failures (default 5) *within the lockout window* lock the
    username for one window (default 300s). After the lockout expires the
    counter starts from zero — the lock is a speed bump, not an escalation
    ladder. A record whose last failure is older than the window is stale and
    resets on read, so slow one-a-day probing never accumulates toward a lock.
    """

    def __init__(
        self,
        repository: FailureRecordRepository,
        *,
        max_failures: int = DEFAULT_MAX_FAILURES,
        lockout: timedelta = timedelta(seconds=DEFAULT_LOCKOUT_SECONDS),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._max_failures = max_failures
        self._lockout = lockout
        self._clock = clock or (lambda: datetime.now(UTC))

    def is_locked(self, username: str, *, now: datetime | None = None) -> bool:
        now = now or self._clock()
        record = self._stale_reset(username, now)
        if record is None or record.locked_until is None:
            return False
        return record.locked_until > now

    def register_failure(self, username: str) -> None:
        now = self._clock()
        record = self._stale_reset(username, now)
        if record is not None and record.locked_until is not None \
                and record.locked_until > now:
            # Already locked: touch nothing. Writing a fresh failure-count row
            # here would *clear* locked_until and unlock the account — the
            # single-worker deployment cannot reach this (the route checks
            # is_locked first and the handler is synchronous), but Mongo is the
            # store precisely because multi-instance is the stated expansion
            # (P-6), and there two requests race past the early check into this
            # method. Found by independent verification H-1 (2026-08-22).
            # Deliberately no extension either: the lock is a speed bump, not
            # an escalation ladder.
            return
        failures = (record.failures if record else 0) + 1
        if failures >= self._max_failures:
            # The counter resets *at* lock time, so when the lockout expires
            # the account starts clean — one lock never rolls into the next.
            self._repo.put(username, FailureRecord(
                failures=0, last_failure_at=now, locked_until=now + self._lockout,
            ))
        else:
            self._repo.put(username, FailureRecord(
                failures=failures, last_failure_at=now, locked_until=None,
            ))

    def register_success(self, username: str) -> None:
        # Called only after credentials verify — including the 403 (status) and
        # 409 (forced password change) paths, since reaching those already
        # proves the caller holds the right password and is not the attacker
        # this guard exists to slow down.
        self._repo.clear(username)

    def _stale_reset(
        self, username: str, now: datetime
    ) -> FailureRecord | None:
        record = self._repo.get(username)
        if record is None:
            return None
        if record.locked_until is not None and record.locked_until > now:
            return record
        if record.last_failure_at + self._lockout < now:
            # Stale counter: the window between the last failure and now
            # already exceeded the lockout, so the count carries no signal.
            self._repo.clear(username)
            return None
        return record
