"""Phase 5.10 Option A (M-i) operator-only per-stage cost measurement CLI.

Measures each Writing loop stage (revise, report, gate, retrieve_plan,
context_search) in isolation against the real gateway using the production
service seams, then composes the loop's worst-case aggregate ceiling from those
per-stage costs (``compose_worst_case_ceiling``). This is the measurement
mechanism the owner picked (M-i) for the B2b ceiling — the Writing Gate is an
independent evaluator and cannot be prose-steered into the max structural path,
so the ceiling is composed analytically rather than measured loop-level.

Writes nothing to Mongo/audit/file (the measurement core is read-only). Like the
gate/report diagnostics it may idempotently seed the benchmark context draft
unless ``--current-position`` is given. Output is numeric JSON (tokens/ms) — no
candidate/context prose — so it is safe to persist as a benchmark artifact.

Run inside the application container, which carries the full env contract::

    docker compose run --rm --no-deps application \\
        python scripts/measure_writing_stages.py --project-id <benchmark-project> \\
        --repeats 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

import httpx

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.context_search.models import CurrentPosition
from services.application.app.writing.models import (
    WritingCandidate,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.per_stage_measure import (
    measurement_to_dict,
    run_per_stage_measurement,
)
from services.application.app.writing.revise_gate import WritingLoopPolicy
from scripts.benchmark_writing_loop import compose_worst_case_ceiling
from scripts.diagnose_writing_gate import (  # shared with the gate diagnostic
    _DEFAULT_CANDIDATE_TEXT, _DEFAULT_FINDING, _DEFAULT_INSTRUCTION,
    _PositionAction, _env_bool, _env_float, _finding_from_dict,
    build_search_request, seed_context,
)


@dataclass(frozen=True, slots=True)
class MeasureServices:
    reviser: object
    reporter: object
    gate: object
    retrieval_planner: object
    context_search: object
    model: str | None


def build_services() -> MeasureServices:
    """Wire the production collaborators reusing ``main``'s factories.

    Every stage uses the real gateway provider (no capture wrapper — this script
    records provider usage/latency, not raw text) so per-stage costs reflect the
    production prompt template / model / max_tokens config by construction.
    """
    from services.application.app.main import (
        _build_chroma_vector_index, _build_embedding_provider,
        _build_report_service, _build_revise_service,
        _build_writing_retrieval_planner, _default_analysis_service,
        _default_context_search_service, _default_core_sot_service,
        _default_index_sync_outbox_service, _default_memory_service,
        _default_writing_gate_service,
    )
    from services.application.app.indexing.service import (
        InMemoryVectorIndexAdapter,
    )

    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "LLM_GATEWAY_BASE_URL is not set; the measurement needs the same "
            "gateway the application uses."
        )
    from services.application.app.analysis.gateway_provider import (
        GatewayGenerateProvider,
    )

    def _gateway():
        return GatewayGenerateProvider(
            base_url=base_url,
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
        )

    reviser = _build_revise_service(_gateway())
    reporter = _build_report_service(_gateway())
    gate = _default_writing_gate_service(provider=_gateway())
    if gate is None:  # pragma: no cover — base_url guard above makes this unreachable
        raise RuntimeError("writing gate service is not configured")
    retrieval_planner = _build_writing_retrieval_planner(_gateway())

    core_sot = _default_core_sot_service()
    sync_outbox = _default_index_sync_outbox_service()
    memory = _default_memory_service(reindex_outbox=sync_outbox)
    analysis = _default_analysis_service(core_sot, reindex_outbox=sync_outbox)
    embeddings = _build_embedding_provider()
    vector_index = _build_chroma_vector_index() or InMemoryVectorIndexAdapter()
    context_search = _default_context_search_service(
        core_sot, vector_index=vector_index, embeddings=embeddings,
        memory=memory, analysis=analysis,
    )
    if context_search is None:
        raise RuntimeError("context search service is not configured")

    return MeasureServices(
        reviser=reviser, reporter=reporter, gate=gate,
        retrieval_planner=retrieval_planner, context_search=context_search,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
    )


def _policy_from_env() -> WritingLoopPolicy:
    """Same structural caps ``main`` builds for the production loop, so the
    composed ceiling matches the loop the numbers will bound. Token/wall-clock
    caps do not affect worst-case stage counts, so they are left at defaults.
    """
    return WritingLoopPolicy(
        max_revision_rounds=int(
            os.environ.get("WRITING_LOOP_MAX_REVISION_ROUNDS", "2")),
        max_retrieval_rounds=int(
            os.environ.get("WRITING_LOOP_MAX_RETRIEVAL_ROUNDS", "1")),
        max_gate_evaluations=int(
            os.environ.get("WRITING_LOOP_MAX_GATE_EVALUATIONS", "3")),
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    services = build_services()
    finding = _finding_from_dict(
        json.loads(args.finding_json) if args.finding_json else _DEFAULT_FINDING
    )
    candidate_text = args.candidate_text or _DEFAULT_CANDIDATE_TEXT
    instruction = args.instruction or _DEFAULT_INSTRUCTION

    if args.current_position is not None:
        draft_id, version_id = args.current_position
        position = CurrentPosition(draft_id=draft_id, version_id=version_id)
    else:
        async with httpx.AsyncClient(
            base_url=args.application_base_url, timeout=args.timeout,
        ) as client:
            seeded = await seed_context(
                client, base_url=args.application_base_url,
                project_id=args.project_id,
            )
        position = CurrentPosition(
            draft_id=seeded["draft_id"], version_id=seeded["version_id"],
        )

    search_request = build_search_request(
        project_id=args.project_id, instruction=instruction, query=args.query,
        position=position, max_tokens=args.max_tokens,
    )
    request = WritingRequest(
        request_id=args.request_id, project_id=args.project_id,
        task_type=WritingTaskType.CONTINUE_SCENE, instruction=instruction,
    )
    candidate = WritingCandidate(
        request_id=args.request_id, project_id=args.project_id,
        task_type=WritingTaskType.CONTINUE_SCENE,
        output_type=WritingOutputType.DRAFT_PATCH, text=candidate_text,
    )
    measurement = await run_per_stage_measurement(
        context_search=services.context_search, search_request=search_request,
        reviser=services.reviser, reporter=services.reporter, gate=services.gate,
        retrieval_planner=services.retrieval_planner, request=request,
        candidate=candidate, finding=finding, current_position=position,
        repeats=args.repeats,
    )
    policy = _policy_from_env()
    ceiling = compose_ceiling(measurement, policy)
    return {
        "project_id": args.project_id,
        "model": services.model,
        "repeats": args.repeats,
        "policy": {
            "max_revision_rounds": policy.max_revision_rounds,
            "max_retrieval_rounds": policy.max_retrieval_rounds,
            "max_gate_evaluations": policy.max_gate_evaluations,
        },
        "measurement": measurement_to_dict(measurement),
        "ceiling": ceiling,
    }


def compose_ceiling(measurement, policy: WritingLoopPolicy) -> dict[str, Any]:
    """Compose the ceiling, but fail closed when the measurement is incomplete.

    ``compose_worst_case_ceiling`` treats a missing stage as a 0 contribution
    (``stage_tokens.get(stage, 0)``), so a faulted/incomplete stage would
    silently UNDER-bound the ceiling — a footgun for an operator who reads only
    ``ceiling.max_total_tokens`` to set the production default (verification H6).
    When any stage is incomplete (fault, or no successful sample) the numeric
    ceiling is nulled and ``complete=false`` is surfaced, so the under-bound
    number is never mistaken for the real worst case. ``stage_counts`` is kept
    for debugging either way.
    """
    ceiling = compose_worst_case_ceiling(
        stage_tokens=measurement.stage_tokens, stage_ms=measurement.stage_ms,
        policy=policy,
    )
    complete = not measurement.incomplete_stages and measurement.error is None
    ceiling["complete"] = complete
    ceiling["incomplete_stages"] = list(measurement.incomplete_stages)
    if not complete:
        ceiling["max_total_tokens"] = None
        ceiling["max_wall_clock_ms"] = None
    return ceiling


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator-only per-stage Writing loop cost measurement (M-i).",
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--request-id", default="stage-measure")
    parser.add_argument("--instruction", default=None)
    parser.add_argument("--candidate-text", default=None)
    parser.add_argument("--finding-json", default=None)
    parser.add_argument("--query", default=None)
    parser.add_argument(
        "--current-position", nargs=2, metavar=("DRAFT_ID", "VERSION_ID"),
        action=_PositionAction, default=None,
        help="reuse an existing draft/version and skip the idempotent context seed",
    )
    parser.add_argument("--application-base-url", default="http://application:8000")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument(
        "--repeats", type=int, default=3,
        help="measurement passes per stage; the conservative MAX per stage is used",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser


def main(argv: list[str] | None = None, *,
         run: Callable[[argparse.Namespace], Any] = _run,
         stdout: TextIO | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    report = asyncio.run(run(args))
    print(json.dumps(report, ensure_ascii=False, indent=2), file=stdout)


if __name__ == "__main__":
    main()
