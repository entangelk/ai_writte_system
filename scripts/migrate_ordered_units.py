"""Run the W3 ordered-unit metadata migration before application deployment."""

from __future__ import annotations

import json
import os

from pymongo import MongoClient

from services.application.app.core_sot.mongo_repository import (
    DEFAULT_DB_NAME,
    MongoCoreSotRepository,
)
from services.application.app.core_sot.ordered_unit_migration import (
    OrderedUnitMigrationService,
)


def main() -> int:
    uri = os.environ.get("CORE_SOT_MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    use_transactions = os.environ.get(
        "CORE_SOT_MONGO_TRANSACTIONS", "true"
    ).lower() not in {"0", "false", "no"}
    client = MongoClient(uri)
    try:
        repository = MongoCoreSotRepository(
            client, db_name=db_name, use_transactions=use_transactions
        )
        report = OrderedUnitMigrationService(repository).run()
        print(
            json.dumps(
                {
                    "migrated_project_ids": report.migrated_project_ids,
                    "unchanged_project_ids": report.unchanged_project_ids,
                    "failures": [
                        {
                            "project_id": failure.project_id,
                            "detail": failure.detail,
                        }
                        for failure in report.failures
                    ],
                    "position_index_installed": report.position_index_installed,
                }
            )
        )
        return 0 if report.succeeded else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
