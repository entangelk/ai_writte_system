"""HTTP-only smoke for deployed Phase 2A Application -> Gateway wiring."""

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

from scripts.script_auth import add_login_arguments, authenticate_client


DEFAULT_APPLICATION_BASE_URL = "http://127.0.0.1:8000"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Phase 2A through an already running Application service over "
            "HTTP: save snapshot, create source_ref catalog, create analysis "
            "job, run it, and read back candidates."
        )
    )
    parser.add_argument(
        "--application-base-url",
        default=os.environ.get("APPLICATION_BASE_URL", DEFAULT_APPLICATION_BASE_URL),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("PHASE2A_DEPLOYED_SMOKE_TIMEOUT_SECONDS", "240")),
    )
    add_login_arguments(parser)
    return parser.parse_args(argv)


async def run_deployed_smoke(
    client: httpx.AsyncClient,
    *,
    application_base_url: str,
) -> dict[str, Any]:
    raw_text = (
        "민아는 파란 편지를 발견했다.\n\n"
        "준호는 민아에게 오래된 지도에 대해 말했다."
    )
    project = await _json(
        client.post("/projects", json={"name": "Phase 2A Deployed Smoke"})
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
            json={"raw_text": raw_text, "idempotency_key": "deployed-smoke-save-1"},
        )
    )
    snapshot_id = saved["snapshot"]["id"]
    source_refs = []
    for quote in ("민아", "파란 편지", "준호"):
        source_refs.append(
            await _json(
                client.post(
                    f"/projects/{project['id']}/snapshots/{snapshot_id}/source-refs",
                    json=_source_ref_request(raw_text, quote),
                )
            )
        )
    job_created = await _json(
        client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={
                "snapshot_id": snapshot_id,
                "idempotency_key": "deployed-smoke-job-1",
            },
        )
    )
    job = job_created["job"]
    run_response = await client.post(
        f"/projects/{project['id']}/analysis/jobs/{job['id']}/run"
    )
    final_job_response = await client.get(
        f"/projects/{project['id']}/analysis/jobs/{job['id']}"
    )
    candidates_response = await client.get(
        f"/projects/{project['id']}/analysis/jobs/{job['id']}/candidates"
    )

    final_job = final_job_response.json()
    candidates = candidates_response.json()["candidates"]
    return {
        "application_base_url": application_base_url.rstrip("/"),
        "project_id": project["id"],
        "snapshot_id": snapshot_id,
        "source_refs": [
            {
                "id": ref["id"],
                "quote": ref["quote"],
                "start_offset": ref["start_offset"],
                "end_offset": ref["end_offset"],
            }
            for ref in source_refs
        ],
        "run_http_status": run_response.status_code,
        "run_response": _safe_json(run_response),
        "final_job": final_job,
        "candidates": candidates,
        "candidate_count": len(candidates),
    }


async def run_live(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.application_base_url.rstrip("/")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(args.timeout_seconds),
        trust_env=False,
    ) as client:
        await authenticate_client(client, username=args.username)
        return await run_deployed_smoke(
            client,
            application_base_url=base_url,
        )


def terminal_status(summary: dict[str, Any]) -> bool:
    return summary["final_job"]["status"] in {"succeeded", "failed"}


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


async def _json(awaitable) -> dict[str, Any]:
    response = await awaitable
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("HTTP response body must be an object")
    return body


def _source_ref_request(raw_text: str, quote: str) -> dict[str, int]:
    start = raw_text.index(quote)
    return {"start_offset": start, "end_offset": start + len(quote)}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


if __name__ == "__main__":
    raise SystemExit(main())
