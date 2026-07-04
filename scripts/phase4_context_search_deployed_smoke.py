"""HTTP-only smoke for the deployed Phase 4 context search endpoint.

Runs against an already-running Application service: creates a project/draft/
version, then calls POST /projects/{id}/context-search so the request goes
application HTTP -> gateway container -> llama -> planner and back through the
Mongo-direct retrieval. Prints a JSON summary; exit 0 only on HTTP 200.

The deployed vector index is the non-persistent fake, so vector needs return
no hits and Mongo-direct needs (current scene) serve from the Core SOT.
"""

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


DEFAULT_APPLICATION_BASE_URL = "http://127.0.0.1:8000"

RAW_TEXT = (
    "# 1장\n\n"
    "아린은 항구에 도착했다.\n\n"
    "낡은 단검에는 검은 태양 문양이 새겨져 있었다.\n\n"
    "---\n\n"
    "밤이 되자 노스워치의 등불이 켜졌다.\n\n"
    "아린은 편지를 다시 읽었다."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 4 context search endpoint through an already "
            "running Application service over HTTP: save a snapshot, then call "
            "POST /context-search and read back the package + gate decision."
        )
    )
    parser.add_argument(
        "--application-base-url",
        default=os.environ.get("APPLICATION_BASE_URL", DEFAULT_APPLICATION_BASE_URL),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(
            os.environ.get(
                "PHASE4_CONTEXT_SEARCH_DEPLOYED_SMOKE_TIMEOUT_SECONDS", "600"
            )
        ),
    )
    return parser.parse_args(argv)


async def run_deployed_context_search_smoke(
    client: httpx.AsyncClient,
    *,
    application_base_url: str,
) -> dict[str, Any]:
    project = await _json(
        client.post("/projects", json={"name": "Phase 4 Deployed Smoke"})
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
            json={"raw_text": RAW_TEXT, "idempotency_key": "ctx-deployed-smoke-1"},
        )
    )
    version_id = saved["draft_version"]["id"]
    search_response = await client.post(
        f"/projects/{project['id']}/context-search",
        json={
            "query": "아린이 항구에서 낡은 단검을 발견하는 장면을 이어 쓴다",
            "needs": ["current_scene", "source_quote"],
            "current_position": {"draft_id": draft["id"], "version_id": version_id},
            "max_tokens": 6000,
        },
    )

    body = _safe_json(search_response)
    summary: dict[str, Any] = {
        "application_base_url": application_base_url.rstrip("/"),
        "project_id": project["id"],
        "draft_id": draft["id"],
        "version_id": version_id,
        "search_http_status": search_response.status_code,
        "response": body,
    }
    if search_response.status_code == 200 and isinstance(body, dict):
        package = body.get("package", {})
        gate = body.get("gate", {})
        summary["gate_decision"] = gate.get("decision")
        summary["degraded"] = package.get("degraded")
        summary["macro_count"] = len(package.get("macro_items", []))
        summary["micro_count"] = len(package.get("micro_evidence", []))
        summary["plan_steps"] = [
            {"need": step.get("need"), "tools": step.get("tools")}
            for step in package.get("trace", {}).get("plan", {}).get("steps", [])
        ]
    return summary


async def run_live(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.application_base_url.rstrip("/")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(args.timeout_seconds),
        trust_env=False,
    ) as client:
        return await run_deployed_context_search_smoke(
            client,
            application_base_url=base_url,
        )


def search_succeeded(summary: dict[str, Any]) -> bool:
    return summary["search_http_status"] == 200


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
    return 0 if search_succeeded(summary) else 1


async def _json(awaitable) -> dict[str, Any]:
    response = await awaitable
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("HTTP response body must be an object")
    return body


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


if __name__ == "__main__":
    raise SystemExit(main())
