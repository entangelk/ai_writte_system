"""UserService with a fake hasher and the in-memory repository."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from services.application.app.auth.models import User
from services.application.app.auth.users import (
    DuplicateUsername, InMemoryUserRepository, InvalidUserInput,
    LastActiveAdmin, UserNotFound, UserService,
)

_FIXED_TIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _FakeHasher:
    """Deterministic stand-in so service tests never pay Argon2's cost. The real
    primitive is covered in test_auth_password.py.

    Records verify() calls: the timing-side enumeration guard is only observable
    as "was a verify performed at all", so a fake that forgets its calls cannot
    lock it (that gap was the verification's B-1)."""

    def __init__(self) -> None:
        self.verify_calls: list[tuple[str, str]] = []

    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        self.verify_calls.append((stored_hash, password))
        return stored_hash == "H:" + password


def _seq_ids():
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"user:{counter['n']}"

    return factory


def _service(
    repo: InMemoryUserRepository | None = None,
    hasher: _FakeHasher | None = None,
) -> UserService:
    return UserService(
        repo or InMemoryUserRepository(),
        hasher=hasher or _FakeHasher(),
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


class EnumerationHardeningTest(unittest.TestCase):
    """`UserService.authenticate` runs a dummy verify for unknown/disabled
    accounts so they cost the same as a wrong password.

    Without it, Argon2's deliberate slowness makes a missing username measurably
    faster than a wrong password, which leaks which usernames exist. The failure
    is invisible to assertIsNone-style tests (all three cases return None either
    way), so it has to be locked on "was a verify actually performed".
    """

    def _run(self, *, username, password, seeded_active=True):
        repo = InMemoryUserRepository()
        hasher = _FakeHasher()
        _service(repo, hasher).create_user(username="alice", password="pw123")
        if not seeded_active:
            stored = repo.get_by_username("alice")
            repo._by_id[stored.id] = replace(stored, is_active=False)
        hasher.verify_calls.clear()  # ignore setup work
        result = _service(repo, hasher).authenticate(
            username=username, password=password
        )
        return result, hasher

    def test_unknown_and_disabled_cost_the_same_verify_as_a_wrong_password(self):
        # The property itself: all three failures perform the same amount of
        # hashing work. Deleting the dummy verify makes the unknown/disabled
        # counts drop to 0 and this fails.
        wrong, wrong_hasher = self._run(username="alice", password="WRONG")
        unknown, unknown_hasher = self._run(username="ghost", password="WRONG")
        disabled, disabled_hasher = self._run(
            username="alice", password="pw123", seeded_active=False
        )
        self.assertIsNone(wrong)
        self.assertIsNone(unknown)
        self.assertIsNone(disabled)

        self.assertEqual(len(wrong_hasher.verify_calls), 1)
        self.assertEqual(
            len(unknown_hasher.verify_calls), len(wrong_hasher.verify_calls)
        )
        self.assertEqual(
            len(disabled_hasher.verify_calls), len(wrong_hasher.verify_calls)
        )

    def test_dummy_verify_uses_a_throwaway_hash_not_a_real_users(self):
        # Over-strict guard. Equalizing the cost by verifying against a *real*
        # stored hash would let a lucky password match a disabled account, and
        # for the unknown-user case there is no real hash to use anyway. The
        # guard hash must be a throwaway no password can match.
        _, hasher = self._run(username="ghost", password="pw123")
        (guard_hash, attempted_password), = hasher.verify_calls
        self.assertEqual(attempted_password, "pw123")
        self.assertNotEqual(guard_hash, "H:pw123")

    def test_successful_login_still_verifies_against_the_stored_hash(self):
        # Over-strict guard in the other direction: the guard must not replace
        # the real check. A correct password must verify against what was stored.
        repo = InMemoryUserRepository()
        hasher = _FakeHasher()
        created = _service(repo, hasher).create_user(
            username="alice", password="pw123"
        )
        hasher.verify_calls.clear()
        self.assertIsNotNone(
            _service(repo, hasher).authenticate(username="alice", password="pw123")
        )
        self.assertEqual(hasher.verify_calls, [(created.password_hash, "pw123")])


class ListAndDeactivateTest(unittest.TestCase):
    """D8-5 admin operations at the service layer."""

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.service = _service(self.repo)

    def test_list_users_is_empty_before_anyone_is_created(self) -> None:
        self.assertEqual(self.service.list_users(), ())

    def test_list_users_returns_every_account(self) -> None:
        alice = self.service.create_user(username="alice", password="pw")
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.assertEqual(self.service.list_users(), (alice, root))

    def test_deactivating_flips_the_flag_in_the_store(self) -> None:
        alice = self.service.create_user(username="alice", password="pw")

        updated = self.service.deactivate_user(alice.id)

        self.assertFalse(updated.is_active)
        self.assertFalse(self.repo.get_by_id(alice.id).is_active)

    def test_a_deactivated_user_can_no_longer_authenticate(self) -> None:
        # The reason the flag exists. `authenticate` already refused inactive
        # accounts; this pins that deactivation actually reaches that path.
        alice = self.service.create_user(username="alice", password="pw")
        self.service.deactivate_user(alice.id)

        self.assertIsNone(
            self.service.authenticate(username="alice", password="pw")
        )

    def test_deactivating_an_unknown_user_raises(self) -> None:
        with self.assertRaises(UserNotFound):
            self.service.deactivate_user("user:ghost")

    def test_the_last_active_admin_is_refused(self) -> None:
        # F2=A: the invariant is about the population of active admins, so this
        # fires even though the request names a perfectly valid user.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="alice", password="pw")

        with self.assertRaises(LastActiveAdmin):
            self.service.deactivate_user(root.id)

        self.assertTrue(self.repo.get_by_id(root.id).is_active)

    def test_a_second_active_admin_makes_the_first_removable(self) -> None:
        # Over-strict: admins are not undeletable, they are merely not
        # extinguishable. A rule that always refused would pass the test above.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="root2", password="pw", is_admin=True)

        self.assertFalse(self.service.deactivate_user(root.id).is_active)

    def test_an_inactive_admin_does_not_keep_the_last_one_removable(self) -> None:
        # Counting admins instead of *active* admins would allow the lockout.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        second = self.service.create_user(
            username="root2", password="pw", is_admin=True
        )
        self.service.deactivate_user(second.id)

        with self.assertRaises(LastActiveAdmin):
            self.service.deactivate_user(root.id)

    def test_deactivating_an_already_inactive_admin_is_allowed(self) -> None:
        # Idempotence at the boundary: the guard asks whether *this* account is
        # currently holding the deployment's last admin seat. An already
        # disabled one is not, so repeating the call must not start failing.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="root2", password="pw", is_admin=True)
        self.service.deactivate_user(root.id)

        self.assertFalse(self.service.deactivate_user(root.id).is_active)

    def test_a_non_admin_is_never_blocked_by_the_admin_rule(self) -> None:
        # The only user in the deployment, but not an admin: the rule must not
        # generalize into "the last user cannot be disabled".
        alice = self.service.create_user(username="alice", password="pw")

        self.assertFalse(self.service.deactivate_user(alice.id).is_active)


if __name__ == "__main__":
    unittest.main()
