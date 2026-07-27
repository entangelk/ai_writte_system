"""Password hashing.

Argon2id per docs/plans/multi-user-auth-cms-decisions.md D2 (owner: "보안에
맞춰서"). We do not implement the hash ourselves — that is a security anti-pattern;
argon2-cffi provides the vetted primitive. The service depends on the
``PasswordHasher`` protocol so tests can inject a trivial fake and keep the suite
fast (Argon2 is deliberately slow), while the real primitive is exercised
directly in test_auth_password.py.
"""

from __future__ import annotations

from typing import Protocol

from argon2 import PasswordHasher as _Argon2Hasher
from argon2 import Type
from argon2.exceptions import Argon2Error, InvalidHashError


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, stored_hash: str, password: str) -> bool: ...


class Argon2PasswordHasher:
    def __init__(self) -> None:
        # Argon2id (Type.ID) is the OWASP-recommended default: resistant to both
        # GPU and side-channel attacks. argon2-cffi's defaults are sane; we pin
        # the type explicitly so a library default change cannot silently switch
        # variants.
        self._hasher = _Argon2Hasher(type=Type.ID)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(stored_hash, password)
        except (Argon2Error, InvalidHashError):
            # Mismatch, malformed stored hash, or any verification failure is a
            # non-match, not an exception the caller should branch on.
            return False
