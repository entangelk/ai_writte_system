"""Mongo repository for administrator access grants."""

from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient

from services.application.app.auth.models import AccessGrant, AccessGrantUse
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
        # C-3: one row per request made under a live grant. Separate collection
        # so the grant row stays a single "who/why" record and the uses grow
        # independently of it.
        self._uses = client[db_name]["access_grant_uses"]
        self._uses.create_index(
            [("project_id", ASCENDING), ("at", DESCENDING)],
            name="access_grant_uses_by_project",
        )
        # No TTL index here either, for the same reason as the grants: this is
        # the record of what an administrator looked at.
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

    def insert_use(self, use: AccessGrantUse) -> None:
        self._uses.insert_one(_use_doc(use))

    def uses_for_project(self, *, project_id: str) -> tuple[AccessGrantUse, ...]:
        return tuple(
            _use_entry(doc)
            for doc in self._uses.find(
                {"project_id": project_id}, sort=[("at", DESCENDING)]
            )
        )

    def purge_project(self, *, project_id: str) -> None:
        self._grants.delete_many({"project_id": project_id})
        self._uses.delete_many({"project_id": project_id})


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


def _use_doc(value: AccessGrantUse) -> dict:
    return {
        "_id": value.id,
        "grant_id": value.grant_id,
        "admin_user_id": value.admin_user_id,
        "project_id": value.project_id,
        "method": value.method,
        "path": value.path,
        "at": value.at,
        "reason": value.reason,
    }


def _use_entry(doc: dict) -> AccessGrantUse:
    return AccessGrantUse(
        id=doc["_id"],
        grant_id=doc["grant_id"],
        admin_user_id=doc["admin_user_id"],
        project_id=doc["project_id"],
        method=doc["method"],
        path=doc["path"],
        at=_aware(doc["at"]),
        reason=doc["reason"],
    )
