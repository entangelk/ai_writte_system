"""SessionService with the in-memory repository and injected clock/token."""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.sessions import (
    InMemorySessionRepository, SessionService, hash_token,
)

_T0 = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _service(repo=None, *, clock=None, tokens=("tok-1", "tok-2", "tok-3")):
    it = iter(tokens)
    return SessionService(
        repo or InMemorySessionRepository(),
        ttl=timedelta(hours=1),
        clock=clock or _Clock(_T0),
        token_factory=lambda: next(it),
    )


class SessionServiceTest(unittest.TestCase):
    def test_stores_only_the_hash_not_the_raw_token(self) -> None:
        repo = InMemorySessionRepository()
        raw, session = _service(repo).create_session(user_id="user:1")
        self.assertEqual(raw, "tok-1")
        self.assertEqual(session.token_hash, hash_token("tok-1"))
        self.assertNotEqual(session.token_hash, raw)
        # What is persisted is keyed by the hash, and the raw token is not in it.
        self.assertIsNotNone(repo.get(hash_token("tok-1")))
        self.assertIsNone(repo.get("tok-1"))

    def test_resolve_valid_then_expired_two_directional(self) -> None:
        repo = InMemorySessionRepository()
        clock = _Clock(_T0)
        service = _service(repo, clock=clock)
        raw, _ = service.create_session(user_id="user:1")
        # under-strict: a live session must resolve to its user.
        resolved = service.resolve(raw)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.user_id, "user:1")
        # over-strict: once past expires_at the same token must stop resolving,
        # even though the store still holds the row.
        clock.now = _T0 + timedelta(hours=1, seconds=1)
        self.assertIsNone(service.resolve(raw))
        self.assertIsNotNone(repo.get(hash_token(raw)))  # row still present

    def test_resolve_boundary_exactly_at_expiry_is_expired(self) -> None:
        repo = InMemorySessionRepository()
        clock = _Clock(_T0)
        service = _service(repo, clock=clock)
        raw, session = service.create_session(user_id="user:1")
        clock.now = session.expires_at  # expires_at <= now → expired
        self.assertIsNone(service.resolve(raw))

    def test_resolve_unknown_token_returns_none(self) -> None:
        self.assertIsNone(_service().resolve("never-issued"))

    def test_revoke_makes_session_unresolvable(self) -> None:
        repo = InMemorySessionRepository()
        service = _service(repo)
        raw, _ = service.create_session(user_id="user:1")
        service.revoke(raw)
        self.assertIsNone(service.resolve(raw))

    def test_revoke_all_for_user_only_targets_that_user(self) -> None:
        repo = InMemorySessionRepository()
        service = _service(repo, tokens=("a", "b", "c"))
        raw_a, _ = service.create_session(user_id="user:1")
        raw_b, _ = service.create_session(user_id="user:1")
        raw_c, _ = service.create_session(user_id="user:2")
        service.revoke_all_for_user("user:1")
        self.assertIsNone(service.resolve(raw_a))
        self.assertIsNone(service.resolve(raw_b))
        self.assertIsNotNone(service.resolve(raw_c))


class DefaultTokenEntropyTest(unittest.TestCase):
    """The default token factory is the one place session security depends on
    randomness: D2 keeps only the hash server-side, so an attacker's only route
    back to a live session is guessing the raw token. Every other test injects a
    fixed token_factory, which would leave a low-entropy default unnoticed."""

    def test_default_tokens_are_unique_and_full_length(self) -> None:
        service = SessionService(InMemorySessionRepository())
        tokens = [service.create_session(user_id="u")[0] for _ in range(50)]
        self.assertEqual(len(set(tokens)), 50)
        for token in tokens:
            # secrets.token_urlsafe(32) = 32 random bytes -> 43 base64url chars.
            # Shortening the default (or swapping in a counter) fails here.
            self.assertGreaterEqual(len(token), 43)


if __name__ == "__main__":
    unittest.main()
