"""Mongo repository for login failure records (brute-force guard, 2026-08-22).

``_id`` is the username — one row per attempted username, which is the guard's
axis. No TTL index: staleness is a *policy* judgement (the window depends on
``AUTH_LOGIN_LOCKOUT_SECONDS``, which can differ between deployments), so the
service resets stale counters on read and the row set is bounded by the number
of distinct usernames anyone has ever typed at the login form. An index whose
expiry baked in one deployment's window would silently disagree with the
service after an env change — the same class of drift the sessions TTL avoids
by having the service stay authoritative.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import MongoClient

from services.application.app.auth.login_guard import FailureRecord
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def _aware(value: datetime) -> datetime:
    # Same re-labeling as sessions_mongo: BSON dates come back naive and the
    # guard compares against aware now() — a naive/aware mix is a TypeError at
    # the worst possible place (the lock check itself).
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoFailureRecordRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._records = client[db_name]["login_failures"]

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def get(self, username: str) -> FailureRecord | None:
        doc = self._records.find_one({"_id": username})
        if doc is None:
            return None
        locked_until = doc.get("locked_until")
        return FailureRecord(
            failures=doc["failures"],
            last_failure_at=_aware(doc["last_failure_at"]),
            locked_until=_aware(locked_until) if locked_until else None,
        )

    def put(self, username: str, record: FailureRecord) -> None:
        self._records.update_one(
            {"_id": username},
            {"$set": {
                "failures": record.failures,
                "last_failure_at": record.last_failure_at,
                "locked_until": record.locked_until,
            }},
            upsert=True,
        )

    def clear(self, username: str) -> None:
        self._records.delete_one({"_id": username})
