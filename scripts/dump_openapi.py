"""Dump the Application FastAPI OpenAPI schema to stdout as JSON.

The frontend generates its TypeScript path/request types from this schema
(`frontend/npm run gen:api`), so the 50-endpoint contract is not hand-typed.
Read-only: builds the app with default (in-memory) collaborators and never
serves a request, so no Mongo/Gateway/Chroma connection is made.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.main import create_app  # noqa: E402


def main() -> int:
    schema = create_app().openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
