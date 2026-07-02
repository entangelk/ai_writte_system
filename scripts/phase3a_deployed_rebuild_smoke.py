"""HTTP + optional CLI smoke for deployed Phase 3A source-block rebuild."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.phase3a_rebuild_source_block_index import rebuild_source_block_index
from services.application.app.core_sot.service import CoreSotService

DEFAULT_APPLICATION_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MONGO_DB = "ai_writing_system"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Phase 3A explicit source-block rebuild against an already "
            "running Application HTTP endpoint, and optionally compare it with "
            "the CLI rebuild path against the same MongoDB snapshot."
        )
    )
    parser.add_argument(
        "--application-base-url",
        default=os.environ.get("APPLICATION_BASE_URL", DEFAULT_APPLICATION_BASE_URL),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("PHASE3A_DEPLOYED_SMOKE_TIMEOUT_SECONDS", "60")),
    )
    parser.add_argument("--mongo-uri", default=os.environ.get("CORE_SOT_MONGO_URI"))
    parser.add_argument(
        "--mongo-db",
        default=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_MONGO_DB),
    )
    parser.add_argument(
        "--mongo-transactions",
        default=os.environ.get("CORE_SOT_MONGO_TRANSACTIONS", "true"),
        choices=("true", "false", "1", "0", "yes", "no"),
    )
    return parser.parse_args(argv)


async def run_deployed_smoke(
    client: httpx.AsyncClient,
    *,
    application_base_url: str,
    cli_rebuild_fn=None,
) -> dict[str, Any]:
    raw_text = "민아는 파란 편지를 발견했다.\n\n준호는 지도를 접었다."
    project = await _json(
        client.post("/projects", json={"name": "Phase 3A Rebuild Smoke"})
    )
    draft = await _json(
        client.post(
            f"/projects/{project['id']}/drafts",
            json={"title": "Smoke draft"},
        )
    )
    saved = await _json(
        client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": raw_text, "idempotency_key": "phase3a-smoke-save-1"},
        )
    )
    snapshot_id = saved["snapshot"]["id"]
    http_summary = await _json(
        client.post(
            f"/projects/{project['id']}/snapshots/{snapshot_id}"
            "/index/source-blocks/rebuild"
        )
    )
    cli_summary = None
    if cli_rebuild_fn is not None:
        cli_summary = cli_rebuild_fn(project["id"], snapshot_id)

    return {
        "application_base_url": application_base_url.rstrip("/"),
        "project_id": project["id"],
        "draft_id": draft["id"],
        "snapshot_id": snapshot_id,
        "http_summary": http_summary,
        "cli_summary": cli_summary,
        "summaries_match": (
            _comparable_summary(http_summary) == _comparable_summary(cli_summary)
            if cli_summary is not None
            else None
        ),
    }


async def run_live(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.application_base_url.rstrip("/")
    cli_rebuild_fn = None
    if args.mongo_uri:
        core_sot = _core_sot_from_mongo(args)

        def cli_rebuild(project_id: str, snapshot_id: str) -> dict[str, Any]:
            return rebuild_source_block_index(
                core_sot=core_sot,
                project_id=project_id,
                snapshot_id=snapshot_id,
            )

        cli_rebuild_fn = cli_rebuild

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(args.timeout_seconds),
        trust_env=False,
    ) as client:
        return await run_deployed_smoke(
            client,
            application_base_url=base_url,
            cli_rebuild_fn=cli_rebuild_fn,
        )


def terminal_status(summary: dict[str, Any]) -> bool:
    http_summary = summary["http_summary"]
    http_complete = http_summary["records_attempted"] == http_summary["records_written"]
    cli_summary = summary.get("cli_summary")
    if cli_summary is None:
        return http_complete
    cli_complete = cli_summary["records_attempted"] == cli_summary["records_written"]
    return http_complete and cli_complete and summary["summaries_match"]


def main(
    argv: list[str] | None = None,
    *,
    run_live_fn=run_live,
    stdout=None,
) -> int:
    args = parse_args(argv)
    summary = asyncio.run(run_live_fn(args))
    stream = stdout if stdout is not None else sys.stdout
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=stream)
    return 0 if terminal_status(summary) else 1


def _core_sot_from_mongo(args: argparse.Namespace) -> CoreSotService:
    from services.application.app.core_sot.mongo_repository import (
        MongoCoreSotRepository,
    )

    repository = MongoCoreSotRepository.from_uri(
        args.mongo_uri,
        db_name=args.mongo_db,
        use_transactions=args.mongo_transactions.lower() in {"true", "1", "yes"},
    )
    return CoreSotService(repository)


async def _json(awaitable) -> dict[str, Any]:
    response = await awaitable
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("HTTP response body must be an object")
    return body


def _comparable_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "project_id": summary["project_id"],
        "snapshot_id": summary["snapshot_id"],
        "target": summary["target"],
        "records_attempted": summary["records_attempted"],
        "records_written": summary["records_written"],
        "records_indexed": summary["records_indexed"],
        "records_query_visible": summary["records_query_visible"],
        "records_archived": summary["records_archived"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
