"""Measure approved B2b Writing loop workloads through the deployed HTTP API.

The endpoint's opt-in audit is deliberately enabled for each run: its immutable
summary is the only public surface that exposes aggregate provider tokens and
the loop's monotonic wall clock. The POST latency is measured separately so the
report does not confuse API overhead with the loop's internal clock.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, TextIO

import httpx

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.writing.revise_gate import WritingLoopPolicy


class AsyncHttpClient(Protocol):
    async def post(self, url: str, *, json: dict[str, Any]) -> httpx.Response: ...
    async def get(self, url: str) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class WritingLoopBenchmarkCase:
    """An immutable inline candidate/finding fixture plus its required trace."""

    name: str
    instruction: str
    candidate_text: str
    finding: dict[str, str]
    expected_loop_status: str
    expected_stages: tuple[str, ...]

    def request_body(
        self, *, request_id: str, current_position: dict[str, str] | None = None
    ) -> dict[str, Any]:
        body = {
            "request_id": request_id,
            "instruction": self.instruction,
            "candidate_text": self.candidate_text,
            "finding": self.finding,
            "task_type": "continue_scene",
            "max_tokens": 4096,
            "persist_audit": True,
        }
        if current_position is not None:
            body["current_position"] = current_position
        return body

    def fixture_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "instruction": self.instruction,
            "candidate_text": self.candidate_text,
            "finding": self.finding,
            "expected_loop_status": self.expected_loop_status,
            "expected_stages": list(self.expected_stages),
        }


_FINDING = {
    "type": "continuity",
    "severity": "warning",
    "message": "직전 장면의 위치 연속성이 맞지 않습니다.",
    "evidence": "민아는 역 플랫폼에 서 있었다.",
    "recommended_decision": "revise",
}

_CONTEXT_SEED_TEXT = (
    "민아는 역 플랫폼에 서 있었다. 비는 이미 그쳤고, "
    "그녀는 파란 편지를 주머니에 넣었다."
)

# The prompts request a particular Gate route, but the real model remains the
# authority. A trace mismatch is a recorded failure, never silently measured as
# the requested workload. This is intentional: B2b calibrates actual branches.
BENCHMARK_CASES: tuple[WritingLoopBenchmarkCase, ...] = (
    WritingLoopBenchmarkCase(
        name="terminal_pass",
        instruction=(
            "아래 후보의 연속성만 고친 뒤 Writing Gate는 pass로 종료하세요. "
            "추가 검색이나 추가 수정은 요청하지 마세요."
        ),
        candidate_text=(
            "민아는 역 플랫폼에 서 있었다. 비는 이미 그쳤고, "
            "그녀는 파란 편지를 주머니에 넣었다."
        ),
        finding=_FINDING,
        expected_loop_status="pass",
        expected_stages=("revise", "report", "gate"),
    ),
    WritingLoopBenchmarkCase(
        name="retrieve_more_then_pass",
        instruction=(
            "첫 Writing Gate는 사건 근거가 부족하다고 판단해 retrieve_more를 "
            "한 번 요청하고, 검색 결과 뒤 두 번째 Gate는 pass로 종료하세요."
        ),
        candidate_text=(
            "민아는 역 플랫폼에 서 있었다. 비는 이미 그쳤고, "
            "그녀는 파란 편지를 주머니에 넣었다."
        ),
        finding=_FINDING,
        expected_loop_status="pass",
        expected_stages=(
            "revise", "report", "gate", "retrieve_plan", "context_search",
            "merge", "gate",
        ),
    ),
    WritingLoopBenchmarkCase(
        name="max_structural_path",
        instruction=(
            "첫 Writing Gate는 continuity revise를 한 번 요청하고, 두 번째 Gate는 "
            "retrieve_more를 한 번 요청한 뒤, 세 번째 Gate는 pass로 종료하세요. "
            "각 revise finding의 evidence는 현재 후보 본문에서 정확히 한 번 나타나는 "
            "문장으로 반환하세요."
        ),
        candidate_text=(
            "민아는 역 플랫폼에 서 있었다. 비는 이미 그쳤고, "
            "그녀는 파란 편지를 주머니에 넣었다."
        ),
        finding=_FINDING,
        expected_loop_status="pass",
        expected_stages=(
            "revise", "report", "gate", "revise", "report", "gate",
            "retrieve_plan", "context_search", "merge", "gate",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class WritingLoopBenchmarkRun:
    case: str
    iteration: int
    success: bool
    http_latency_ms: float
    total_tokens: int = 0
    loop_wall_clock_ms: int = 0
    loop_status: str | None = None
    stage_trace: tuple[str, ...] = ()
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "iteration": self.iteration,
            "success": self.success,
            "http_latency_ms": round(self.http_latency_ms, 3),
            "total_tokens": self.total_tokens,
            "loop_wall_clock_ms": self.loop_wall_clock_ms,
            "loop_status": self.loop_status,
            "stage_trace": list(self.stage_trace),
            "http_status": self.http_status,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


async def run_benchmark(
    client: AsyncHttpClient,
    *,
    base_url: str,
    project_id: str,
    cases: Iterable[WritingLoopBenchmarkCase] = BENCHMARK_CASES,
    repeats: int,
    warmups: int,
    current_position: dict[str, str] | None = None,
    now: Callable[[], float] = perf_counter,
) -> list[WritingLoopBenchmarkRun]:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    if warmups < 0:
        raise ValueError("warmups must be >= 0")

    root = base_url.rstrip("/")
    runs: list[WritingLoopBenchmarkRun] = []
    for case in cases:
        for warmup in range(1, warmups + 1):
            run = await _run_case(
                client, root=root, project_id=project_id, case=case,
                iteration=0, request_id=f"b2b-{case.name}-warmup-{warmup}",
                current_position=current_position, now=now,
            )
            if not run.success:
                runs.append(run)
        for iteration in range(1, repeats + 1):
            runs.append(await _run_case(
                client, root=root, project_id=project_id, case=case,
                iteration=iteration, request_id=f"b2b-{case.name}-{iteration}",
                current_position=current_position, now=now,
            ))
    return runs


async def _run_case(
    client: AsyncHttpClient,
    *,
    root: str,
    project_id: str,
    case: WritingLoopBenchmarkCase,
    iteration: int,
    request_id: str,
    current_position: dict[str, str] | None,
    now: Callable[[], float],
) -> WritingLoopBenchmarkRun:
    started = now()
    try:
        response = await client.post(
            f"{root}/projects/{project_id}/writing/revise-and-gate",
            json=case.request_body(
                request_id=request_id, current_position=current_position
            ),
        )
    except httpx.HTTPError as exc:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, (now() - started) * 1000,
            error_code="http_transport_error", error_message=str(exc),
        )
    elapsed_ms = (now() - started) * 1000
    if response.status_code != 200:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms,
            http_status=response.status_code,
            error_code=f"http_{response.status_code}", error_message=response.text,
        )
    try:
        payload = response.json()
        loop = payload["loop"]
        trace = tuple(stage["stage"] for stage in payload["stages"])
        audit_id = payload["audit_id"]
    except (KeyError, TypeError, ValueError) as exc:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, http_status=200,
            error_code="invalid_loop_envelope", error_message=str(exc),
        )
    if not audit_id:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, loop_status=loop.get("status"),
            stage_trace=trace, http_status=200, error_code="audit_missing",
            error_message=str(payload.get("audit_error") or "persisted audit id missing"),
        )
    try:
        audit_response = await client.get(
            f"{root}/projects/{project_id}/writing/loop-audits/{audit_id}"
        )
    except httpx.HTTPError as exc:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, loop_status=loop.get("status"),
            stage_trace=trace, http_status=200, error_code="audit_transport_error",
            error_message=str(exc),
        )
    if audit_response.status_code != 200:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, loop_status=loop.get("status"),
            stage_trace=trace, http_status=200,
            error_code=f"audit_http_{audit_response.status_code}",
            error_message=audit_response.text,
        )
    try:
        audit = audit_response.json()
        total_tokens = audit["total_tokens"]
        wall_clock_ms = audit["wall_clock_ms"]
    except (KeyError, TypeError, ValueError) as exc:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, loop_status=loop.get("status"),
            stage_trace=trace, http_status=200,
            error_code="invalid_audit_envelope", error_message=str(exc),
        )
    if loop.get("status") != case.expected_loop_status or trace != case.expected_stages:
        return WritingLoopBenchmarkRun(
            case.name, iteration, False, elapsed_ms, total_tokens=total_tokens,
            loop_wall_clock_ms=wall_clock_ms, loop_status=loop.get("status"),
            stage_trace=trace, http_status=200, error_code="unexpected_loop_trace",
            error_message=(
                f"expected status={case.expected_loop_status}, stages="
                f"{list(case.expected_stages)}"
            ),
        )
    return WritingLoopBenchmarkRun(
        case.name, iteration, True, elapsed_ms, total_tokens=total_tokens,
        loop_wall_clock_ms=wall_clock_ms, loop_status=loop.get("status"),
        stage_trace=trace, http_status=200,
    )


async def seed_benchmark_context(
    client: AsyncHttpClient, *, base_url: str, project_id: str
) -> dict[str, str]:
    """Create the real current-scene pointer required by Writing context search.

    Setup is outside measured POST latency. The benchmark project is dedicated
    because this seed and each opt-in audit are durable records.
    """
    root = base_url.rstrip("/")
    draft_response = await client.post(
        f"{root}/projects/{project_id}/drafts",
        json={"title": "B2b benchmark context"},
    )
    if draft_response.status_code != 200:
        raise RuntimeError(
            f"benchmark context draft failed: HTTP {draft_response.status_code}: "
            f"{draft_response.text}"
        )
    try:
        draft_id = draft_response.json()["id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("benchmark context draft response is invalid") from exc

    version_response = await client.post(
        f"{root}/projects/{project_id}/drafts/{draft_id}/versions",
        json={
            "raw_text": _CONTEXT_SEED_TEXT,
            "idempotency_key": "b2b-writing-loop-context-v1",
        },
    )
    if version_response.status_code != 200:
        raise RuntimeError(
            f"benchmark context version failed: HTTP {version_response.status_code}: "
            f"{version_response.text}"
        )
    try:
        version_id = version_response.json()["draft_version"]["id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("benchmark context version response is invalid") from exc
    return {"draft_id": draft_id, "version_id": version_id}


def summarize_runs(runs: Iterable[WritingLoopBenchmarkRun]) -> dict[str, Any]:
    grouped: dict[str, list[WritingLoopBenchmarkRun]] = {}
    for run in runs:
        grouped.setdefault(run.case, []).append(run)
    summary: dict[str, Any] = {}
    for case, case_runs in sorted(grouped.items()):
        successes = [run for run in case_runs if run.success]
        failures = [run for run in case_runs if not run.success]
        summary[case] = {
            "runs": len(case_runs),
            "successes": len(successes),
            "failures": len(failures),
            "http_latency_ms_p50": _percentile(
                sorted(run.http_latency_ms for run in successes), 50
            ),
            "http_latency_ms_p95": _percentile(
                sorted(run.http_latency_ms for run in successes), 95
            ),
            "loop_wall_clock_ms_p95": _percentile(
                sorted(run.loop_wall_clock_ms for run in successes), 95
            ),
            "max_total_tokens": max(
                (run.total_tokens for run in successes), default=None
            ),
            "error_codes": sorted({
                run.error_code for run in failures if run.error_code is not None
            }),
        }
    return summary


def build_report(
    *, base_url: str, project_id: str, model: str, quant: str,
    compose_revision: str, repeats: int, warmups: int,
    cases: Iterable[WritingLoopBenchmarkCase],
    runs: Iterable[WritingLoopBenchmarkRun],
    context_position: dict[str, str] | None = None,
) -> dict[str, Any]:
    case_list = list(cases)
    fixture = [case.fixture_dict() for case in case_list]
    run_list = list(runs)
    return {
        "metadata": {
            "created_at": datetime.now(UTC).isoformat(),
            "application_base_url": base_url,
            "project_id": project_id,
            "model": model,
            "quant": quant,
            "compose_revision": compose_revision,
            "repeats": repeats,
            "warmups": warmups,
            "context_position": context_position,
            "fixture_sha256": hashlib.sha256(
                json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
        "fixtures": fixture,
        "summary": summarize_runs(run_list),
        "runs": [run.to_dict() for run in run_list],
    }


# --- Option A: analytical worst-case ceiling composition -------------------
# (docs/plans/05-writing-loop-ceiling-composition-decisions.md)
# The Writing Gate is an independent evaluator and cannot be prose-steered into
# retrieve_more (confirmed live: 0/12), so the real model never walks the max
# structural path. But the aggregate budget is a SUM of per-stage provider usage
# (revise_gate.py metered channel) and the structural caps bound stage counts —
# so the worst-case ceiling is composed from per-stage costs measured in
# isolation, without making the model walk the whole loop.
#
# metered() accumulates provider usage for revise, report, gate and
# retrieve_plan into the aggregate token budget. context_search runs outside
# metered() (revise_gate.py) so it adds wall-clock but NOT aggregate tokens;
# merge is in-process (negligible).
_TOKEN_STAGES = ("revise", "report", "gate", "retrieve_plan")
_WALL_CLOCK_STAGES = ("revise", "report", "gate", "retrieve_plan", "context_search")


def worst_case_stage_counts(policy: WritingLoopPolicy) -> dict[str, int]:
    """Worst-case per-stage invocation counts under the policy's structural caps.

    Mirrors the revise_gate loop: report follows every revise; a gate runs once
    initially, once per additional revise round, and once per retrieval round,
    all capped by max_gate_evaluations. Re-derives from the policy so a changed
    cap (env-tunable) automatically re-composes the ceiling.
    """
    revises = policy.max_revision_rounds
    retrievals = policy.max_retrieval_rounds
    gates = min(policy.max_gate_evaluations, 1 + (revises - 1) + retrievals)
    return {
        "revise": revises,
        "report": revises,
        "gate": gates,
        "retrieve_plan": retrievals,
        "context_search": retrievals,
    }


def compose_worst_case_ceiling(
    *,
    stage_tokens: Mapping[str, int],
    stage_ms: Mapping[str, int],
    policy: WritingLoopPolicy,
) -> dict[str, Any]:
    """Compose the raw worst-case aggregate ceiling from per-stage costs.

    stage_tokens/stage_ms map a stage name to its conservatively-measured (max
    observed, repair included) single-invocation cost. Only token-contributing
    stages count toward max_total_tokens; context_search adds wall-clock only.
    Returns the RAW worst case — the owner adds a B4 safety margin before
    promoting it to a production default.
    """
    counts = worst_case_stage_counts(policy)
    max_total_tokens = sum(
        counts[stage] * int(stage_tokens.get(stage, 0)) for stage in _TOKEN_STAGES
    )
    max_wall_clock_ms = sum(
        counts[stage] * int(stage_ms.get(stage, 0)) for stage in _WALL_CLOCK_STAGES
    )
    return {
        "max_total_tokens": max_total_tokens,
        "max_wall_clock_ms": max_wall_clock_ms,
        "stage_counts": counts,
    }


def _percentile(values: list[float | int], percentile: int) -> float | int | None:
    if not values:
        return None
    index = min(len(values) - 1, int(round((percentile / 100) * (len(values) - 1))))
    value = values[index]
    return round(value, 3) if isinstance(value, float) else value


async def _run_live(args: argparse.Namespace) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=args.application_base_url,
                                 timeout=args.timeout) as client:
        current_position = await seed_benchmark_context(
            client, base_url=args.application_base_url, project_id=args.project_id
        )
        runs = await run_benchmark(
            client, base_url=args.application_base_url, project_id=args.project_id,
            repeats=args.repeats, warmups=args.warmups,
            current_position=current_position,
        )
    return build_report(
        base_url=args.application_base_url, project_id=args.project_id,
        model=args.model, quant=args.quant, compose_revision=args.compose_revision,
        repeats=args.repeats, warmups=args.warmups, cases=BENCHMARK_CASES,
        runs=runs, context_position=current_position,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-url", required=True)
    parser.add_argument("--project-id", required=True)
    # The application does not expose model/quant or compose provenance. Require
    # the operator to record them rather than guessing from local environment.
    parser.add_argument("--model", required=True)
    parser.add_argument("--quant", required=True)
    parser.add_argument("--compose-revision", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser


def main(argv: list[str] | None = None, *,
         run_live: Callable[[argparse.Namespace], Any] = _run_live,
         stdout: TextIO | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    report = asyncio.run(run_live(args))
    print(json.dumps(report, ensure_ascii=False, indent=2), file=stdout)


if __name__ == "__main__":
    main()
