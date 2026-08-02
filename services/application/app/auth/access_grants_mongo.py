"""Mongo repository for administrator access grants."""

from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient

from services.application.app.auth.models import AccessGrant
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def _aware(value: datetime) -> datetime:
    """Same boundary re-labeling as ``sessions_mongo._aware``.

    pymongo returns BSON dates without tzinfo unless the client is tz_aware, and
    the grant domain compares ``expires_at`` against an aware ``now(UTC)``.
    Comparing naive to aware raises TypeError — the failure mode that once made
    every session read a 500 against real Mongo while the in-memory fake stayed
    green, so it is re-attached here rather than trusted to client settings.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoAccessGrantRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._grants = client[db_name]["access_grants"]
        # Backs ``latest_for``: newest first within one (admin, project) pair.
        self._grants.create_index(
            [
                ("admin_user_id", ASCENDING),
                ("project_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="access_grants_by_admin_project",
        )
        # ★ There is deliberately **no TTL index here**, unlike ``sessions``.
        # The row is the issuance audit record (C-3), so reaping it would delete
        # the evidence of an access that happened. Expiry is a judgement made in
        # ``AccessGrantService.active``; the store keeps everything.

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def insert(self, grant: AccessGrant) -> None:
        self._grants.insert_one(_doc(grant))

    def latest_for(
        self, *, admin_user_id: str, project_id: str
    ) -> AccessGrant | None:
        doc = self._grants.find_one(
            {"admin_user_id": admin_user_id, "project_id": project_id},
            sort=[("created_at", DESCENDING)],
        )
        return _entry(doc) if doc else None

    def purge_project(self, *, project_id: str) -> None:
        self._grants.delete_many({"project_id": project_id})


def _doc(value: AccessGrant) -> dict:
    return {
        "_id": value.id,
        "admin_user_id": value.admin_user_id,
        "project_id": value.project_id,
        "reason": value.reason,
        "created_at": value.created_at,
        "expires_at": value.expires_at,
    }


def _entry(doc: dict) -> AccessGrant:
    return AccessGrant(
        id=doc["_id"],
        admin_user_id=doc["admin_user_id"],
        project_id=doc["project_id"],
        reason=doc["reason"],
        created_at=_aware(doc["created_at"]),
        expires_at=_aware(doc["expires_at"]),
    )
