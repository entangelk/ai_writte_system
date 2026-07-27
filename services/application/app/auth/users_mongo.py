"""Mongo repository for users."""

from pymongo import ASCENDING, MongoClient
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


def _doc(value: User) -> dict:
    return {
        "_id": value.id,
        "username": value.username,
        "password_hash": value.password_hash,
        "is_admin": value.is_admin,
        "is_active": value.is_active,
        "created_at": value.created_at,
    }


def _entry(doc: dict) -> User:
    return User(
        id=doc["_id"],
        username=doc["username"],
        password_hash=doc["password_hash"],
        is_admin=doc["is_admin"],
        is_active=doc["is_active"],
        created_at=doc["created_at"],
    )
