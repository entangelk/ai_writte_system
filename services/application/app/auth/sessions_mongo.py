"""Mongo repository for sessions."""

from pymongo import ASCENDING, MongoClient

from services.application.app.auth.models import Session
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoSessionRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._sessions = client[db_name]["sessions"]
        # user_id index backs admin force-logout (delete_for_user, D6).
        self._sessions.create_index(
            [("user_id", ASCENDING)], name="sessions_by_user"
        )
        # TTL index: Mongo reaps expired sessions on its own. The service still
        # gates on expires_at because TTL reaping is eventually-consistent.
        self._sessions.create_index(
            [("expires_at", ASCENDING)], name="sessions_ttl", expireAfterSeconds=0
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def insert(self, session: Session) -> None:
        self._sessions.insert_one(_doc(session))

    def get(self, token_hash: str) -> Session | None:
        doc = self._sessions.find_one({"_id": token_hash})
        return _entry(doc) if doc else None

    def delete(self, token_hash: str) -> None:
        self._sessions.delete_one({"_id": token_hash})

    def delete_for_user(self, user_id: str) -> None:
        self._sessions.delete_many({"user_id": user_id})


def _doc(value: Session) -> dict:
    return {
        "_id": value.token_hash,
        "user_id": value.user_id,
        "created_at": value.created_at,
        "expires_at": value.expires_at,
    }


def _entry(doc: dict) -> Session:
    return Session(
        token_hash=doc["_id"],
        user_id=doc["user_id"],
        created_at=doc["created_at"],
        expires_at=doc["expires_at"],
    )
