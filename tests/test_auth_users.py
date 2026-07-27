"""UserService with a fake hasher and the in-memory repository."""

import unittest
from datetime import UTC, datetime

from services.application.app.auth.models import User
from services.application.app.auth.users import (
    DuplicateUsername, InMemoryUserRepository, InvalidUserInput, UserService,
)

_FIXED_TIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _FakeHasher:
    """Deterministic stand-in so service tests never pay Argon2's cost. The real
    primitive is covered in test_auth_password.py."""

    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


def _seq_ids():
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"user:{counter['n']}"

    return factory


def _service(repo: InMemoryUserRepository | None = None) -> UserService:
    return UserService(
        repo or InMemoryUserRepository(),
        hasher=_FakeHasher(),
        clock=lambda: _FIXED_TIME,
        id_factory=_seq_ids(),
    )


class CreateUserTest(unittest.TestCase):
    def test_stores_hashed_password_not_plaintext(self) -> None:
        service = _service()
        user = service.create_user(username="alice", password="pw123")
        self.assertEqual(user.username, "alice")
        # Delegated to the hasher (fake = "H:"+pw), not stored raw. The real
        # not-plaintext property is proven in test_auth_password.py.
        self.assertEqual(user.password_hash, "H:pw123")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_admin)
        self.assertEqual(user.id, "user:1")
        self.assertEqual(user.created_at, _FIXED_TIME)

    def test_is_admin_flag_is_honored(self) -> None:
        user = _service().create_user(
            username="root", password="pw", is_admin=True
        )
        self.assertTrue(user.is_admin)

    def test_username_is_stripped(self) -> None:
        user = _service().create_user(username="  bob  ", password="pw")
        self.assertEqual(user.username, "bob")

    def test_duplicate_username_rejected(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw")
        with self.assertRaises(DuplicateUsername):
            _service(repo).create_user(username="alice", password="other")

    def test_empty_username_rejected(self) -> None:
        for bad in ("", "   "):
            with self.assertRaises(InvalidUserInput):
                _service().create_user(username=bad, password="pw")

    def test_empty_password_rejected(self) -> None:
        with self.assertRaises(InvalidUserInput):
            _service().create_user(username="alice", password="")


class AuthenticateTest(unittest.TestCase):
    def test_correct_credentials_return_user(self) -> None:
        repo = InMemoryUserRepository()
        created = _service(repo).create_user(username="alice", password="pw123")
        got = _service(repo).authenticate(username="alice", password="pw123")
        self.assertEqual(got, created)

    def test_wrong_password_returns_none(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw123")
        self.assertIsNone(
            _service(repo).authenticate(username="alice", password="nope")
        )

    def test_unknown_username_returns_none(self) -> None:
        self.assertIsNone(
            _service().authenticate(username="ghost", password="pw")
        )

    def test_inactive_user_cannot_authenticate(self) -> None:
        repo = InMemoryUserRepository()
        repo.insert(
            User(
                id="user:x", username="alice", password_hash="H:pw123",
                is_admin=False, is_active=False, created_at=_FIXED_TIME,
            )
        )
        # Right password, but disabled account (admin-disable, D6) must not log in.
        self.assertIsNone(
            _service(repo).authenticate(username="alice", password="pw123")
        )

    def test_username_stripped_on_authenticate(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw123")
        self.assertIsNotNone(
            _service(repo).authenticate(username="  alice ", password="pw123")
        )


if __name__ == "__main__":
    unittest.main()
