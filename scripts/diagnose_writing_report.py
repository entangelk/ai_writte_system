"""Phase 5.10 operator-only one-shot Writing candidate report live diagnostic.

Mirror of ``diagnose_writing_gate.py`` for the report stage. After the v1.6.83
gate fence fix removed ``invalid_gate_result`` 502s, the B2b re-measurement
still shows ``invalid_candidate_report`` 502s ("report field must be an
array"). The bodyless audit exposes neither the raw report text nor which
field/clause failed, and the report has a 1-call repair whose raw output is
also lost. This CLI reproduces the production report provider request (same
prompt template, model, ``thinking=False``, ``max_tokens``) and prints the
first and repair raw responses plus the exact strict-parse error to stdout.

Writes nothing to Mongo/audit/file. Run inside the application container::

    docker compose run --rm --no-deps -e APPLICATION_PASSWORD='...' application \\
        python scripts/diagnose_writing_report.py --project-id <benchmark-project> \\
        --username <account>

``--username`` is needed whenever the idempotent seed runs (D8-3a: the seed's
writes need a session); ``--current-position`` skips both.

Reuses the shared seed/search-request/finding helpers from
``diagnose_writing_gate.py`` (same benchmark context, same ContextSearchRequest
shape) so the report sees the same pipeline the gate does.
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

from services.application.app.writing.models import (
    WritingCandidate,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.report_live_diag import (
    RawCaptureProvider,
    format_report_diagnosis,
    run_report_diagnosis,
)
from scripts.diagnose_writing_gate import (  # shared with the gate diagnostic
    _DEFAULT_CANDIDATE_TEXT, _DEFAULT_FINDING, _DEFAULT_INSTRUCTION,
    _PositionAction, _env_bool, _env_float, _finding_from_dict,
    build_search_request, seed_context,
)
from scripts.script_auth import add_login_arguments, authenticate_client


@dataclass(frozen=True, slots=True)
class ReportDiagServices:
    reviser: object
    reporter: object
    context_search: object
    capture: RawCaptureProvider
    model: str | None
    max_tokens: int


def build_services(*, gateway_provider=None) -> ReportDiagServices:
    """Wire production collaborators; the REPORT provider is wrapped for capture.

    The report is built through ``_build_report_service(capture)`` (which
    already accepts a provider) so its prompt template and
    ``LLM_GATEWAY_MODEL`` / ``WRITING_REPORT_MAX_TOKENS`` config are the
    production contract by construction. Only the report routes through the
    capture wrapper; revise uses a plain gateway provider.
    """
    from services.application.app.main import (
        _build_chroma_vector_index, _build_embedding_provider,
        _build_report_service, _build_revise_service,
        _default_analysis_service, _default_context_search_service,
        _default_core_sot_service, _default_index_sync_outbox_service,
        _default_memory_service,
    )
    from services.application.app.indexing.service import (
        InMemoryVectorIndexAdapter,
    )

    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "LLM_GATEWAY_BASE_URL is not set; the diagnostic needs the same "
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

    capture = RawCaptureProvider(gateway_provider or _gateway())
    reporter = _build_report_service(capture)
    reviser = _build_revise_service(_gateway())

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

    return ReportDiagServices(
        reviser=reviser, reporter=reporter, context_search=context_search,
        capture=capture,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_REPORT_MAX_TOKENS", "1024")),
    )


async def _run(args: argparse.Namespace) -> str:
    services = build_services()
    finding = _finding_from_dict(
        json.loads(args.finding_json) if args.finding_json else _DEFAULT_FINDING
    )
    candidate_text = args.candidate_text or _DEFAULT_CANDIDATE_TEXT
    instruction = args.instruction or _DEFAULT_INSTRUCTION

    if args.current_position is not None:
        draft_id, version_id = args.current_position
        from services.application.app.context_search.models import CurrentPosition
        position = CurrentPosition(draft_id=draft_id, version_id=version_id)
    else:
        async with httpx.AsyncClient(
            base_url=args.application_base_url, timeout=args.timeout,
        ) as client:
            await authenticate_client(client, username=args.username)
            seeded = await seed_context(
                client, base_url=args.application_base_url, project_id=args.project_id,
            )
        from services.application.app.context_search.models import CurrentPosition
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
    diagnosis = await run_report_diagnosis(
        context_search=services.context_search,
        search_request=search_request,
        reviser=services.reviser,
        reporter=services.reporter,
        capture=services.capture,
        request=request, candidate=candidate, finding=finding,
    )
    return format_report_diagnosis(
        diagnosis, request_id=args.request_id, project_id=args.project_id,
        model=services.model, max_tokens=services.max_tokens,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator-only one-shot Writing candidate report live diagnostics.",
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--request-id", default="report-diag")
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
    parser.add_argument("--timeout", type=float, default=600.0)
    add_login_arguments(parser)
    return parser


def main(argv: list[str] | None = None, *,
         run: Callable[[argparse.Namespace], Any] = _run,
         stdout: TextIO | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    text = asyncio.run(run(args))
    print(text, file=stdout)


if __name__ == "__main__":
    main()
