"""Auth domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    id: str
    username: str
    password_hash: str
    is_admin: bool
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Session:
    # token_hash = sha256 of the raw cookie token. Only the hash is stored, so a
    # database leak does not hand over live session tokens; the raw token exists
    # only in the client cookie.
    token_hash: str
    user_id: str
    created_at: datetime
    expires_at: datetime
