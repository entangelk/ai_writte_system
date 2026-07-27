"""Server-side sessions (D2=A: server session + HttpOnly cookie).

The raw token lives only in the client cookie; the store keeps its sha256 so a
DB leak cannot resurrect live sessions. Immediate invalidation (logout, admin
force-logout D6) is a delete — the property JWT could not give us (D2 rationale).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from services.application.app.auth.models import Session

DEFAULT_SESSION_TTL = timedelta(days=7)


def hash_token(raw_token: str) -> str:
    # The token is 256 bits of CSPRNG output, so a single sha256 (not a slow
    # password hash) is the right primitive — there is nothing to brute-force.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionRepository(Protocol):
    def insert(self, session: Session) -> None: ...
    def get(self, token_hash: str) -> Session | None: ...
    def delete(self, token_hash: str) -> None: ...
    def delete_for_user(self, user_id: str) -> None: ...


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, Session] = {}

    def insert(self, session: Session) -> None:
        self._by_hash[session.token_hash] = session

    def get(self, token_hash: str) -> Session | None:
        return self._by_hash.get(token_hash)

    def delete(self, token_hash: str) -> None:
        self._by_hash.pop(token_hash, None)

    def delete_for_user(self, user_id: str) -> None:
        for token_hash in [
            h for h, s in self._by_hash.items() if s.user_id == user_id
        ]:
            del self._by_hash[token_hash]


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        *,
        ttl: timedelta = DEFAULT_SESSION_TTL,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def create_session(self, *, user_id: str) -> tuple[str, Session]:
        """Returns (raw_token, session). The raw token goes to the cookie and is
        never stored; only the caller sees it once."""
        raw_token = self._token_factory()
        now = self._clock()
        session = Session(
            token_hash=hash_token(raw_token),
            user_id=user_id,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._repo.insert(session)
        return raw_token, session

    def resolve(self, raw_token: str) -> Session | None:
        session = self._repo.get(hash_token(raw_token))
        if session is None:
            return None
        if session.expires_at <= self._clock():
            # Expired: treat as absent. The store may still hold it (TTL reaping
            # is eventually-consistent), so the service is the authoritative gate.
            return None
        return session

    def revoke(self, raw_token: str) -> None:
        self._repo.delete(hash_token(raw_token))

    def revoke_all_for_user(self, user_id: str) -> None:
        self._repo.delete_for_user(user_id)
