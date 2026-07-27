"""User domain: repository seam, in-memory fake, and the user service.

Ownership (``Project.owner_id``) and authorization enforcement are later slices
(D3/D7). This slice only stores users and verifies credentials.
"""

from __future__ import annotations

import secrets
import uuid
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


class UserRepository(Protocol):
    def insert(self, user: User) -> None:
        """Persist a new user. Raises DuplicateUsername if the username exists."""

    def get_by_id(self, user_id: str) -> User | None: ...
    def get_by_username(self, username: str) -> User | None: ...


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
        self, *, username: str, password: str, is_admin: bool = False
    ) -> User:
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
        )
        self._repo.insert(user)
        return user

    def get_by_id(self, user_id: str) -> User | None:
        return self._repo.get_by_id(user_id)

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

    def _enumeration_guard_hash(self) -> str:
        # Built once on first miss (hashing is expensive) over a random secret, so
        # no real password can ever match it.
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))
        return self._dummy_hash
