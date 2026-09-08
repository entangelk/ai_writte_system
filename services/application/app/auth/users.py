"""User domain: repository seam, in-memory fake, and the user service.

Ownership (``Project.owner_id``) and authorization enforcement are later slices
(D3/D7). This slice only stores users and verifies credentials.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from services.application.app.auth.models import User
from services.application.app.auth.password import PasswordHasher


class AuthError(RuntimeError):
    pass


class DuplicateUsername(AuthError):
    pass


class InvalidUserInput(AuthError):
    pass


class SignupNotPending(AuthError):
    """Approve/reject targeted a row that is not awaiting approval.

    An active or rejected row is *resolved*, not missing — the caller (an
    administrator) is told so with 409 rather than 404, because "the request
    you are looking at was already handled" is actionable in the admin UI in a
    way "no such user" is not.
    """


class SignupQueueFull(AuthError):
    """The pending-approval queue is at its ceiling (Phase S-3, 2026-09-05).

    Answered as 429, the same face as the per-IP throttle: from the requester's
    side both mean "not now, try later", and neither is a statement about their
    username or password. Distinguishing them in the response would only tell a
    flooder which bound they hit.
    """


class UserNotFound(AuthError):
    pass


class WithdrawalNotRequested(AuthError):
    """Cancel targeted an account that never asked to be deleted.

    409 rather than a silent no-op, following ``SignupNotPending``: "there is
    nothing to cancel" is a different answer from "cancelled", and a screen that
    cannot tell them apart will report success for a request that did nothing.
    """


class LastActiveAdmin(AuthError):
    """Refusing to deactivate the only remaining active admin (D8-5 F2=A).

    The recovery path from an admin lockout is a container ``docker exec`` of
    ``scripts/create_user.py``; one check here is far cheaper than that.
    """


# C-6. Length over composition (no forced symbol/digit classes): composition
# rules push people toward predictable substitutions while shortening what they
# choose. A contract literal — changing it is a deliberate edit, and the
# regression pins it.
MIN_PASSWORD_LENGTH = 12

# Phase S-3 (owner 2026-09-05). The public signup body had **no upper bound** on
# either field, so a multi-megabyte username was a Mongo document and a
# multi-megabyte password was Argon2 input — the same request cost, amplified
# by whatever the caller felt like sending (audit §A.11-(3)). Enforced here and
# not on the pydantic model on purpose: the model would answer 422, while every
# other signup policy refusal is a 400 (`InvalidUserInput`), and a screen that
# has to branch on two shapes of "your input is wrong" gets one of them wrong.
MAX_USERNAME_LENGTH = 64
MAX_PASSWORD_LENGTH = 256

# Phase S-3. The IP throttle bounds one sender; this bounds the *queue*. Pending
# rows grant nothing and carry no TTL, so without a ceiling a distributed caller
# could still bury the approval list an administrator has to read (audit
# §A.11-(2)). A contract literal like MIN_PASSWORD_LENGTH above — 200 is a list
# a person can still scroll, and changing it is a deliberate edit the regression
# pins. Deliberately *not* an env knob: a deployment that quietly raised it
# would make the queue unreadable without any signal that it had.
MAX_PENDING_SIGNUPS = 200

# Signup approval statuses (owner 2026-08-22 — plans/auth-signup-approval-decisions.md).
USER_STATUS_PENDING = "pending"
USER_STATUS_ACTIVE = "active"
USER_STATUS_REJECTED = "rejected"

# Account withdrawal grace period (owner 2026-09-07). A contract literal like
# MIN_PASSWORD_LENGTH above: the member asks to be deleted, and the purge falls
# due this long afterwards, during which cancelling restores the account whole
# (D5=A). **One place** — the policy document points here once withdrawal is
# actually enforced, and a pin cell holds the value until then. Deliberately not
# an env knob: a deployment that shortened it would delete manuscripts earlier
# than the terms promise, with nothing saying it had.
WITHDRAWAL_GRACE_PERIOD = timedelta(days=30)


def purge_due_at(user: User) -> datetime | None:
    """When this account's purge falls due, or None if it is not withdrawing.

    The single place the grace-period arithmetic is done. Doing it a second time
    somewhere else is how the screen and the daemon come to disagree about which
    day the account disappears.
    """
    if user.withdrawal_requested_at is None:
        return None
    return user.withdrawal_requested_at + WITHDRAWAL_GRACE_PERIOD


def is_purge_due(user: User, *, now: datetime) -> bool:
    """Has the grace period elapsed?

    ``>=``, not ``>``: the promise is *thirty days of grace*, so the instant the
    thirtieth day is complete the grace is spent. The boundary cells pin day 29
    (not due), exactly day 30 (due) and day 31 (due), which is what makes the
    two off-by-one corrections — ``>`` here, or a ``+1`` on the period — each
    fail a named cell rather than only one of them.
    """
    due = purge_due_at(user)
    return due is not None and now >= due


class UserRepository(Protocol):
    def insert(self, user: User) -> None:
        """Persist a new user. Raises DuplicateUsername if the username exists."""

    def get_by_id(self, user_id: str) -> User | None: ...
    def get_by_username(self, username: str) -> User | None: ...
    def list_all(self) -> tuple[User, ...]:
        """Every user, oldest first. Admin-only surface (D8-5)."""

    def set_active(self, user_id: str, *, is_active: bool) -> User | None:
        """Flip the active flag and return the stored user, or None if unknown."""

    def set_password(self, user_id: str, *, password_hash: str) -> User | None:
        """Store a new hash and clear ``must_change_password``. C-6."""

    def replace(self, user: User) -> None:
        """Overwrite the stored row for ``user.id`` wholesale (signup re-request)."""

    def list_pending(self) -> tuple[User, ...]:
        """Signup requests awaiting approval, oldest request first."""

    def set_status(self, user_id: str, *, status: str) -> User | None:
        """Flip the signup status and return the stored user, or None."""

    def set_withdrawal_requested_at(
        self, user_id: str, *, at: datetime | None,
        only_if_absent: bool = False,
    ) -> User | None:
        """Stamp (or clear, with None) the withdrawal request time. D5=A.

        ``only_if_absent`` makes the write conditional on the account not
        already withdrawing, so "the first stamp wins" is decided by the store
        rather than by a read the caller did earlier. Returns None when the row
        is missing **or** when the condition failed — the caller re-reads to
        tell those apart.
        """


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._by_username: dict[str, str] = {}

    def insert(self, user: User) -> None:
        if user.username in self._by_username:
            raise DuplicateUsername("username already exists")
        self._by_id[user.id] = user
        self._by_username[user.username] = user.id

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        user_id = self._by_username.get(username)
        return self._by_id.get(user_id) if user_id is not None else None

    def list_all(self) -> tuple[User, ...]:
        return tuple(
            sorted(self._by_id.values(), key=lambda user: (user.created_at, user.id))
        )

    def set_active(self, user_id: str, *, is_active: bool) -> User | None:
        stored = self._by_id.get(user_id)
        if stored is None:
            return None
        updated = replace(stored, is_active=is_active)
        self._by_id[user_id] = updated
        return updated

    def set_password(self, user_id: str, *, password_hash: str) -> User | None:
        stored = self._by_id.get(user_id)
        if stored is None:
            return None
        # The two always move together: a stored hash the account owner chose is
        # exactly what stops it from being someone else's password.
        updated = replace(
            stored, password_hash=password_hash, must_change_password=False
        )
        self._by_id[user_id] = updated
        return updated

    def replace(self, user: User) -> None:
        # Same username by construction (signup re-request), so the by-username
        # index needs no touch — only the stored row itself changes.
        self._by_id[user.id] = user

    def list_pending(self) -> tuple[User, ...]:
        return tuple(
            u for u in sorted(
                self._by_id.values(),
                key=lambda user: (user.created_at, user.id),
            )
            if u.status == USER_STATUS_PENDING
        )

    def set_status(self, user_id: str, *, status: str) -> User | None:
        stored = self._by_id.get(user_id)
        if stored is None:
            return None
        updated = replace(stored, status=status)
        self._by_id[user_id] = updated
        return updated

    def set_withdrawal_requested_at(
        self, user_id: str, *, at: datetime | None,
        only_if_absent: bool = False,
    ) -> User | None:
        stored = self._by_id.get(user_id)
        if stored is None:
            return None
        if only_if_absent and stored.withdrawal_requested_at is not None:
            return None
        updated = replace(stored, withdrawal_requested_at=at)
        self._by_id[user_id] = updated
        return updated


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        *,
        hasher: PasswordHasher,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._hasher = hasher
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "user:" + uuid.uuid4().hex)
        self._dummy_hash: str | None = None

    def create_user(
        self, *, username: str, password: str, is_admin: bool = False,
        must_change_password: bool = False,
    ) -> User:
        """Create an account.

        ``must_change_password`` is the caller's statement that *somebody else*
        chose this password (C-6). It defaults to False because the domain
        cannot know: `POST /admin/users` and the bootstrap script set it, while
        the live-smoke script — which issues a throwaway account for its own use
        and is the only other caller — must not. A guard pins those call sites.
        """
        username = username.strip()
        if not username:
            raise InvalidUserInput("username is required")
        if not password:
            raise InvalidUserInput("password is required")
        user = User(
            id=self._id_factory(),
            username=username,
            password_hash=self._hasher.hash(password),
            is_admin=is_admin,
            is_active=True,
            created_at=self._clock(),
            must_change_password=must_change_password,
        )
        self._repo.insert(user)
        return user

    def request_signup(self, *, username: str, password: str) -> User:
        """Self-service signup request (owner 2026-08-22 — approval required).

        Creates a ``pending`` row. No session is ever issued against it; an
        administrator approves it to ``active`` later (1-d). The password is
        final — unlike C-6 there is nobody else choosing it — so the minimum
        length policy applies *here*, the moment it is chosen.
        """
        username = username.strip()
        if not username:
            raise InvalidUserInput("username is required")
        # S-3: the two upper bounds come *before* the hasher and before the
        # store, because they exist to bound what those two are asked to chew.
        if len(username) > MAX_USERNAME_LENGTH:
            raise InvalidUserInput(
                f"username must be at most {MAX_USERNAME_LENGTH} characters"
            )
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidUserInput(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if len(password) > MAX_PASSWORD_LENGTH:
            raise InvalidUserInput(
                f"password must be at most {MAX_PASSWORD_LENGTH} characters"
            )
        existing = self._repo.get_by_username(username)
        if existing is not None:
            # Re-request is allowed only over a rejected row that is still an
            # enabled account: rejection must not become a permanent username
            # ban. A deactivated row wins over re-request — deactivation is
            # one-way (D6=A) and this path must not resurrect it.
            if existing.status != USER_STATUS_REJECTED or not existing.is_active:
                raise DuplicateUsername("username already exists")
            replacement = User(
                id=existing.id,
                username=username,
                password_hash=self._hasher.hash(password),
                # A signup request can never mint an administrator, and the
                # requester owns the password from the start (no C-6 flow).
                is_admin=False,
                is_active=True,
                created_at=self._clock(),
                must_change_password=False,
                status=USER_STATUS_PENDING,
            )
            self._repo.replace(replacement)
            return replacement
        # S-3 queue ceiling. Only the *new row* path is capped: the re-request
        # branch above needs a rejected username the caller already knows, so it
        # cannot be a flood vector, and refusing it would turn the ceiling into
        # a way to permanently ban whoever was rejected last. Checked before the
        # hasher runs, like every other refusal on this path.
        if len(self._repo.list_pending()) >= MAX_PENDING_SIGNUPS:
            raise SignupQueueFull(
                "too many pending signup requests; try again later"
            )
        user = User(
            id=self._id_factory(),
            username=username,
            password_hash=self._hasher.hash(password),
            is_admin=False,
            is_active=True,
            created_at=self._clock(),
            must_change_password=False,
            status=USER_STATUS_PENDING,
        )
        self._repo.insert(user)
        return user

    def get_by_id(self, user_id: str) -> User | None:
        return self._repo.get_by_id(user_id)

    def list_users(self) -> tuple[User, ...]:
        return self._repo.list_all()

    def deactivate_user(self, user_id: str) -> User:
        """Disable an account. Live sessions die with it.

        No separate revocation step: ``current_user_or_none`` resolves the
        session and then re-reads the user, so a cookie minted before this call
        stops working on its next request. That property is why D2 chose server
        sessions over JWT in the first place.
        """
        stored = self._repo.get_by_id(user_id)
        if stored is None:
            raise UserNotFound("user does not exist")
        if stored.is_active and self._is_last_active_admin(stored):
            # F2=A. Deliberately not "you cannot deactivate yourself": two admins
            # disabling each other would walk past that check into the same
            # lockout, so the invariant is about the *population*, not the caller.
            raise LastActiveAdmin("cannot deactivate the last active admin")
        updated = self._repo.set_active(user_id, is_active=False)
        if updated is None:  # pragma: no cover - deleted between read and write
            raise UserNotFound("user does not exist")
        return updated

    def _is_last_active_admin(self, candidate: User) -> bool:
        if not candidate.is_admin:
            return False
        return not any(
            other.id != candidate.id and other.is_admin and other.is_active
            for other in self._repo.list_all()
        )

    # --- Account withdrawal (owner 2026-09-07 — self request, 30-day grace) ---

    def request_withdrawal(self, user_id: str) -> User:
        """Start the grace period. **Deletes nothing** — the daemon does that.

        Idempotent on purpose, and idempotent *keeping the first stamp*: a
        second request must not re-stamp, or a member clicking twice would
        silently push their own deletion date out by however long they waited,
        and the screen's "N days left" would jump backwards for no visible
        reason.
        """
        stored = self._repo.get_by_id(user_id)
        if stored is None:
            raise UserNotFound("user does not exist")
        if stored.withdrawal_requested_at is not None:
            return stored
        if stored.is_active and self._is_last_active_admin(stored):
            # D6=A, the same population invariant ``deactivate_user`` protects
            # and deliberately the same rule rather than a second one: an admin
            # withdrawing is an admin leaving, and the lockout it would cause is
            # identical. Reused, not re-derived — including the ``is_active``
            # half: an already-disabled admin is not in the active population,
            # so refusing it would be a refusal that protects nothing.
            raise LastActiveAdmin("cannot withdraw the last active admin")
        updated = self._repo.set_withdrawal_requested_at(
            user_id, at=self._clock(), only_if_absent=True
        )
        if updated is not None:
            return updated
        # 조건부 쓰기가 안 걸렸다 — 행이 사라졌거나 **경쟁에서 졌다**. 다시 읽어
        # 가른다: 졌으면 먼저 찍힌 시각을 그대로 돌려주는 것이 멱등의 정의다.
        #
        # ★ 위의 조기 반환만으로는 부족하다(독립 검증 H2, 2026-09-08): 읽기와
        # 쓰기 사이가 열려 있으면 **동시 첫 요청 둘이 모두** 그 반환을 지나고,
        # 무조건 쓰기였다면 나중 시각이 이겨 삭제 예정일이 그만큼 밀린다.
        # 조건을 저장소로 내리면 그 창이 닫힌다.
        #
        # **닫히지 않는 것도 적어 둔다** — 조건이 "없을 때만"이라 *취소를
        # 가로지르는* 지연 요청은 여전히 걸린다(A 가 읽고 멈춘 사이 B 가 찍고
        # 사용자가 취소하면, 깨어난 A 가 다시 찍는다). 그것은 결함이 아니라
        # 순서의 모호함이다 — 저장소가 보기에 늦게 온 요청과 새 요청은 같고,
        # 계정은 그 뒤로도 취소할 수 있다. 막으려면 요청마다 토큰이 필요한데
        # 그 값을 살 만한 피해가 없다.
        stored = self._repo.get_by_id(user_id)
        if stored is None:  # pragma: no cover - deleted between read and write
            raise UserNotFound("user does not exist")
        return stored

    def cancel_withdrawal(self, user_id: str) -> User:
        """Back to a plain active account, with nothing left behind (D5=A).

        Cancelling clears the stamp rather than recording a cancellation, so the
        account that comes back is indistinguishable from one that never asked —
        which is the point: the restrictions of the grace period fall away
        because the *state* is gone, not because a second rule lifts them.
        """
        stored = self._repo.get_by_id(user_id)
        if stored is None:
            raise UserNotFound("user does not exist")
        if stored.withdrawal_requested_at is None:
            raise WithdrawalNotRequested("account is not withdrawing")
        updated = self._repo.set_withdrawal_requested_at(user_id, at=None)
        if updated is None:  # pragma: no cover - deleted between read and write
            raise UserNotFound("user does not exist")
        return updated

    # --- Signup approval (owner 2026-08-22 — requests public, approval admin) --

    def list_pending_signups(self) -> tuple[User, ...]:
        return self._repo.list_pending()

    def approve_signup(self, user_id: str) -> User:
        """pending → active. The member signs in on their *next* attempt —
        approval mints no session, exactly like admin-created accounts."""
        stored = self._repo.get_by_id(user_id)
        if stored is None:
            raise UserNotFound("user does not exist")
        if stored.status != USER_STATUS_PENDING:
            raise SignupNotPending("signup request already resolved")
        return self._repo.set_status(user_id, status=USER_STATUS_ACTIVE)

    def reject_signup(self, user_id: str) -> User:
        """pending → rejected. **Pending rows only**: rejecting an active
        account is not this mechanism — deactivation (D6=A) is, and it kills
        live sessions. Keeping rejection on unresolved rows preserves the
        invariant that no resolved account ever changes status again."""
        stored = self._repo.get_by_id(user_id)
        if stored is None:
            raise UserNotFound("user does not exist")
        if stored.status != USER_STATUS_PENDING:
            raise SignupNotPending("signup request already resolved")
        return self._repo.set_status(user_id, status=USER_STATUS_REJECTED)

    def authenticate(self, *, username: str, password: str) -> User | None:
        user = self._repo.get_by_username(username.strip())
        if user is None or not user.is_active:
            # Username enumeration hardening: returning early here would make a
            # missing/disabled account measurably faster than a wrong password
            # (Argon2 is deliberately slow), which leaks which usernames exist.
            # Burn the same verify cost against a throwaway hash before failing.
            self._hasher.verify(self._enumeration_guard_hash(), password)
            return None
        if not self._hasher.verify(user.password_hash, password):
            return None
        return user

    def change_password(self, *, user_id: str, new_password: str) -> User | None:
        """Set the account's own password and clear the forced-change flag (C-6).

        The policy is applied **here**, not in ``create_user``: an administrator's
        initial password is single-use (the account cannot get a session until it
        is replaced), so the credential whose strength actually matters is this
        one — the durable one the account owner chooses.
        """
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise InvalidUserInput(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        return self._repo.set_password(
            user_id, password_hash=self._hasher.hash(new_password)
        )

    def _enumeration_guard_hash(self) -> str:
        # Built once on first miss (hashing is expensive) over a random secret, so
        # no real password can ever match it.
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))
        return self._dummy_hash
