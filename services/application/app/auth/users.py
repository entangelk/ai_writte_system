"""User domain: repository seam, in-memory fake, and the user service.

Ownership (``Project.owner_id``) and authorization enforcement are later slices
(D3/D7). This slice only stores users and verifies credentials.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Callable, Protocol

from services.application.app.auth.models import User
from services.application.app.auth.password import PasswordHasher


class AuthError(RuntimeError):
    pass


class DuplicateUsername(AuthError):
    pass


class InvalidUserInput(AuthError):
    pass


class UserNotFound(AuthError):
    pass


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

# Signup approval statuses (owner 2026-08-22 — plans/auth-signup-approval-decisions.md).
USER_STATUS_PENDING = "pending"
USER_STATUS_ACTIVE = "active"
USER_STATUS_REJECTED = "rejected"


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
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidUserInput(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
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
