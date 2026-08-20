"""HTTP-only smoke for the deployed Phase 6 Context Gate finding lifecycle.

Runs against an already-running Application service and closes the one live gap
left by the 2026-07-17 Review Inbox dogfood: triggering a durable Context Gate
*rejection* so a gate finding is persisted, then exercising the review surface
that consumes it (list -> detail -> resolve / dismiss).

Deterministic reject recipe (no LLM cooperation needed beyond producing a
``current_scene`` plan step):

1. Create project -> draft -> version whose snapshot is plain paragraphs, so the
   current scene (paragraph run after the last heading/scene marker) is always
   non-empty.
2. Archive the draft. Archive keeps reads open, so ``current_scene`` still serves
   the paragraph blocks, but the Context Gate re-derives validity from the SOT
   and finds ``draft.archived`` -> a ``stale_item`` finding -> ``reject``. (This
   is the reachable reject; ``budget_exceeded`` is not — ``_apply_budget`` trims
   over-budget items *before* the gate sums the included ones, so the included
   total can never exceed the budget.)
3. POST /context-search persists the rejection (``persist_rejection`` records
   only when ``decision == "reject"``). A second search with a *different*
   idempotency key mints a second, distinct finding id.
4. The first finding is resolved, the second dismissed — the two lifecycle
   actions the dogfood could not reach live.

Prints a JSON summary; exit 0 only when a finding was persisted and both the
resolve and dismiss transitions returned HTTP 200 with the expected status.

The context-search planner is the real terminal-JSON LLM planner, so the
Application must be wired to a gateway (``LLM_GATEWAY_BASE_URL``); the search is
retried a few times to absorb planner variance (a plan that omits the
current_scene step yields 0 items -> pass, not reject).
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

from scripts.script_auth import add_login_arguments, authenticate_client


DEFAULT_APPLICATION_BASE_URL = "http://127.0.0.1:8000"

# A single plain paragraph, no heading/scene marker: the current scene is the
# whole run (one paragraph block), so each search yields exactly one item and
# thus exactly one stale_item finding per idempotency key. Two keys -> two
# distinct findings: one to resolve, one to dismiss.
RAW_TEXT = "경식은 낡은 등대 아래에 오래 서서 편지를 다시 접었다."


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Trigger a durable Context Gate rejection against a running "
            "Application service and exercise the gate-finding resolve/dismiss "
            "lifecycle."
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
            os.environ.get("PHASE6_GATE_FINDING_SMOKE_TIMEOUT_SECONDS", "600")
        ),
    )
    parser.add_argument(
        "--search-attempts",
        type=int,
        default=int(os.environ.get("PHASE6_GATE_FINDING_SMOKE_ATTEMPTS", "5")),
        help="Max /context-search attempts per idempotency key (planner variance).",
    )
    add_login_arguments(parser)
    return parser.parse_args(argv)


async def _search_until_reject(
    client: httpx.AsyncClient,
    *,
    project_id: str,
    draft_id: str,
    version_id: str,
    idempotency_key: str,
    attempts: int,
) -> tuple[dict[str, Any], int]:
    """POST /context-search, retrying until the gate rejects (or attempts run out).

    The persisted finding id is derived from (project, idempotency_key, ordinal,
    check), so retries with the same key converge on the same finding — a
    retry after a transient pass does not mint duplicates.
    """
    last: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        response = await client.post(
            f"/projects/{project_id}/context-search",
            json={
                "idempotency_key": idempotency_key,
                "query": "경식이 등대 아래에서 편지를 읽는 장면을 이어 쓴다",
                "needs": ["current_scene"],
                "current_position": {
                    "draft_id": draft_id,
                    "version_id": version_id,
                },
                "max_tokens": 6000,
            },
        )
        body = _safe_json(response)
        last = {"attempt": attempt, "http_status": response.status_code,
                "body": body}
        if response.status_code == 200 and isinstance(body, dict):
            decision = body.get("gate", {}).get("decision")
            if decision == "reject":
                return last, attempt
    return last, attempts


async def run_gate_finding_smoke(
    client: httpx.AsyncClient,
    *,
    application_base_url: str,
    attempts: int,
) -> dict[str, Any]:
    project = await _json(
        client.post("/projects", json={"name": "Phase 6 Gate Finding Smoke"})
    )
    draft = await _json(
        client.post(
            f"/projects/{project['id']}/drafts",
            json={"title": "Gate finding smoke draft"},
        )
    )
    saved = await _json(
        client.post(
            f"/projects/{project['id']}/drafts/{draft['id']}/versions",
            json={"raw_text": RAW_TEXT, "idempotency_key": "gate-finding-smoke-v1"},
        )
    )
    version_id = saved["draft_version"]["id"]
    snapshot_id = saved["snapshot"]["id"]

    # Archive the draft: reads stay open (current_scene still serves), but the
    # Context Gate re-derives draft.archived -> stale_item -> reject.
    archive_response = await client.delete(
        f"/projects/{project['id']}/drafts/{draft['id']}"
    )
    archive_body = _safe_json(archive_response)

    summary: dict[str, Any] = {
        "application_base_url": application_base_url.rstrip("/"),
        "project_id": project["id"],
        "draft_id": draft["id"],
        "version_id": version_id,
        "snapshot_id": snapshot_id,
        "archive_http_status": archive_response.status_code,
        "draft_archived": (
            archive_body.get("archived")
            if isinstance(archive_body, dict) else None
        ),
    }

    # First rejection -> the finding we will RESOLVE.
    resolve_search, resolve_attempts = await _search_until_reject(
        client, project_id=project["id"], draft_id=draft["id"],
        version_id=version_id, idempotency_key="gate-finding-smoke-resolve",
        attempts=attempts,
    )
    # Second rejection (distinct idempotency key -> distinct finding id) ->
    # the finding we will DISMISS.
    dismiss_search, dismiss_attempts = await _search_until_reject(
        client, project_id=project["id"], draft_id=draft["id"],
        version_id=version_id, idempotency_key="gate-finding-smoke-dismiss",
        attempts=attempts,
    )
    summary["resolve_search"] = {
        "attempts_used": resolve_attempts,
        "gate_decision": _gate_decision(resolve_search),
        "checks": _finding_checks(resolve_search),
    }
    summary["dismiss_search"] = {
        "attempts_used": dismiss_attempts,
        "gate_decision": _gate_decision(dismiss_search),
        "checks": _finding_checks(dismiss_search),
    }

    # Inbox surface consumed by the frontend: gate_findings with affordances.
    inbox = _safe_json(
        await client.get(f"/projects/{project['id']}/analysis/review-inbox")
    )
    open_findings = (
        inbox.get("gate_findings", []) if isinstance(inbox, dict) else []
    )
    summary["inbox_open_findings"] = len(open_findings)
    summary["inbox_finding_affordances"] = [
        {
            "id": finding.get("id"),
            "check": finding.get("check"),
            "status": finding.get("status"),
            "actions": {
                action.get("action"): action.get("eligible")
                for action in finding.get("actions", [])
            },
        }
        for finding in open_findings
    ]

    finding_ids = [f.get("id") for f in open_findings if f.get("id")]
    if len(finding_ids) >= 2:
        resolve_id, dismiss_id = finding_ids[0], finding_ids[1]

        # Detail read (the review UI opens a finding before acting).
        detail = _safe_json(
            await client.get(
                f"/projects/{project['id']}/analysis/gate-findings/{resolve_id}"
            )
        )
        summary["detail_check"] = (
            detail.get("check") if isinstance(detail, dict) else None
        )

        resolve_response = await client.post(
            f"/projects/{project['id']}/analysis/gate-findings/{resolve_id}/resolve"
        )
        resolve_body = _safe_json(resolve_response)
        summary["resolve"] = {
            "finding_id": resolve_id,
            "http_status": resolve_response.status_code,
            "status": _transition_status(resolve_body),
            "idempotent_replay": _replay(resolve_body),
        }

        dismiss_response = await client.post(
            f"/projects/{project['id']}/analysis/gate-findings/{dismiss_id}/dismiss"
        )
        dismiss_body = _safe_json(dismiss_response)
        summary["dismiss"] = {
            "finding_id": dismiss_id,
            "http_status": dismiss_response.status_code,
            "status": _transition_status(dismiss_body),
            "idempotent_replay": _replay(dismiss_body),
        }

        # After both transitions the open inbox must be empty (server truth,
        # no optimistic patch — the same re-read the frontend performs).
        inbox_after = _safe_json(
            await client.get(f"/projects/{project['id']}/analysis/review-inbox")
        )
        summary["inbox_open_findings_after"] = (
            len(inbox_after.get("gate_findings", []))
            if isinstance(inbox_after, dict) else None
        )

    return summary


def _gate_decision(search: dict[str, Any]) -> Any:
    body = search.get("body")
    if isinstance(body, dict):
        return body.get("gate", {}).get("decision")
    return None


def _finding_checks(search: dict[str, Any]) -> list[str]:
    body = search.get("body")
    if not isinstance(body, dict):
        return []
    return [
        check
        for f in body.get("gate", {}).get("findings", [])
        if isinstance(f, dict) and isinstance(check := f.get("check"), str)
    ]


def _transition_status(body: Any) -> Any:
    if isinstance(body, dict):
        return body.get("finding", {}).get("status")
    return None


def _replay(body: Any) -> Any:
    if isinstance(body, dict):
        return body.get("idempotent_replay")
    return None


async def run_live(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.application_base_url.rstrip("/")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(args.timeout_seconds),
        trust_env=False,
    ) as client:
        await authenticate_client(client, username=args.username)
        return await run_gate_finding_smoke(
            client,
            application_base_url=base_url,
            attempts=args.search_attempts,
        )


def smoke_succeeded(summary: dict[str, Any]) -> bool:
    before = summary.get("inbox_open_findings", 0)
    return (
        summary.get("draft_archived") is True
        and summary.get("resolve_search", {}).get("gate_decision") == "reject"
        and summary.get("dismiss_search", {}).get("gate_decision") == "reject"
        and before >= 2
        and summary.get("resolve", {}).get("http_status") == 200
        and summary.get("resolve", {}).get("status") == "resolved"
        and summary.get("dismiss", {}).get("http_status") == 200
        and summary.get("dismiss", {}).get("status") == "dismissed"
        # Exactly the two acted-on findings leave the open list (server truth).
        and summary.get("inbox_open_findings_after") == before - 2
    )


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
    return 0 if smoke_succeeded(summary) else 1


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
