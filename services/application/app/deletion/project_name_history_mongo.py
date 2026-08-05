"""Mongo repository for project names that outlive their project (Slice 8.2c).

``_id`` is the project id on purpose: the document then carries **no**
``project_id`` field, and ``scripts/purge_reconciler.py`` — which discovers
sweep targets by that field — cannot mistake this collection for orphaned
project data. No TTL; the retention policy is a separate owner decision.
"""

from datetime import UTC, datetime

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.deletion.project_name_history import (
    ProjectNameSnapshot,
)


def _aware(value: datetime) -> datetime:
    # pymongo returns BSON dates naive unless the client is tz_aware; comparing
    # those with aware datetimes raises TypeError in deployment while every
    # fake-collection test stays green (HANDOFF trap).
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoProjectNameHistoryRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._names = client[db_name]["project_name_history"]

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def put(self, snapshot: ProjectNameSnapshot) -> None:
        self._names.replace_one(
            {"_id": snapshot.project_id}, _doc(snapshot), upsert=True
        )

    def get(self, project_id: str) -> ProjectNameSnapshot | None:
        doc = self._names.find_one({"_id": project_id})
        return None if doc is None else _entry(doc)


def _doc(snapshot: ProjectNameSnapshot) -> dict:
    # Exactly three keys. Adding ``project_id`` here would hand the collection to
    # the purge reconciler; a regression fixes this key set.
    return {
        "_id": snapshot.project_id,
        "name": snapshot.name,
        "purged_at": snapshot.purged_at,
    }


def _entry(doc: dict) -> ProjectNameSnapshot:
    return ProjectNameSnapshot(
        project_id=doc["_id"],
        name=doc["name"],
        purged_at=_aware(doc["purged_at"]),
    )
