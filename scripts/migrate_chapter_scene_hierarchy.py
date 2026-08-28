"""Run the SoT v1.8.9 flat-unit → Chapter/Scene migration."""

from __future__ import annotations

import json
import os

from pymongo import MongoClient

from services.application.app.core_sot.chapter_scene_migration import (
    ChapterSceneHierarchyMigration,
)
from services.application.app.core_sot.mongo_repository import (
    DEFAULT_DB_NAME,
    MongoCoreSotRepository,
)


def main() -> int:
    uri = os.environ.get("CORE_SOT_MONGO_URI", "mongodb://localhost:27520")
    db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    use_transactions = os.environ.get(
        "CORE_SOT_MONGO_TRANSACTIONS", "true"
    ).lower() not in {"0", "false", "no"}
    client = MongoClient(uri)
    try:
        repository = MongoCoreSotRepository(
            client, db_name=db_name, use_transactions=use_transactions
        )
        result = ChapterSceneHierarchyMigration(repository).run()
        print(json.dumps({
            "migrated_projects": result.migrated_projects,
            "unchanged_projects": result.unchanged_projects,
        }))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
