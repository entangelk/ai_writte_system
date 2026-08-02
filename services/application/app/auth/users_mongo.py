"""Mongo repository for users."""

from datetime import UTC

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from services.application.app.auth.models import User
from services.application.app.auth.users import DuplicateUsername
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoUserRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._users = client[db_name]["users"]
        # Unique so the database itself enforces the one-username invariant even
        # under concurrent inserts the service's read-then-write cannot see.
        self._users.create_index(
            [("username", ASCENDING)], name="users_username_unique", unique=True
        )

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def insert(self, user: User) -> None:
        try:
            self._users.insert_one(_doc(user))
        except DuplicateKeyError as exc:
            raise DuplicateUsername("username already exists") from exc

    def get_by_id(self, user_id: str) -> User | None:
        doc = self._users.find_one({"_id": user_id})
        return _entry(doc) if doc else None

    def get_by_username(self, username: str) -> User | None:
        doc = self._users.find_one({"username": username})
        return _entry(doc) if doc else None

    def list_all(self) -> tuple[User, ...]:
        # Sorted server-side: the admin list is the one place where "oldest
        # first" is a contract the caller can see, and ordering in Python would
        # depend on however the driver happened to return the batch.
        docs = self._users.find({}).sort("created_at", ASCENDING)
        return tuple(_entry(doc) for doc in docs)

    def set_password(self, user_id: str, *, password_hash: str) -> User | None:
        doc = self._users.find_one_and_update(
            {"_id": user_id},
            {"$set": {
                "password_hash": password_hash, "must_change_password": False,
            }},
            return_document=ReturnDocument.AFTER,
        )
        return _entry(doc) if doc else None

    def set_active(self, user_id: str, *, is_active: bool) -> User | None:
        doc = self._users.find_one_and_update(
            {"_id": user_id},
            {"$set": {"is_active": is_active}},
            return_document=ReturnDocument.AFTER,
        )
        return _entry(doc) if doc else None


def _doc(value: User) -> dict:
    return {
        "_id": value.id,
        "username": value.username,
        "password_hash": value.password_hash,
        "is_admin": value.is_admin,
        "must_change_password": value.must_change_password,
        "is_active": value.is_active,
        "created_at": value.created_at,
    }


def _entry(doc: dict) -> User:
    return User(
        id=doc["_id"],
        username=doc["username"],
        password_hash=doc["password_hash"],
        is_admin=doc["is_admin"],
        # `.get` on purpose: rows written before C-6 have no such field, and a
        # KeyError here would lock every pre-existing account out of login.
        must_change_password=doc.get("must_change_password", False),
        is_active=doc["is_active"],
        # Same UTC re-labeling as the session repo: pymongo returns BSON dates
        # naive, and the domain treats timestamps as aware. Nothing compares
        # created_at today, so this is consistency rather than a fix — it keeps a
        # future comparison from reintroducing the session bug.
        created_at=(
            doc["created_at"] if doc["created_at"].tzinfo is not None
            else doc["created_at"].replace(tzinfo=UTC)
        ),
    )
