"""Phase 5.10 (D1=A) operator-only one-shot Writing Gate live diagnostic CLI.

Reproduces the production Gate provider request (same model, prompt template,
ContextPackage assembly, ``thinking=False``, ``max_tokens``) for a benchmark-
dedicated project/request and prints the raw model response plus the exact
strict-parse error to stdout. It writes nothing to Mongo, the audit trail, or
the API response — the loop's bodyless persisted audit (P1) cannot answer this,
so this is the minimum surface that can (decision brief D1=A).

Run inside the application container, which carries the full env contract
(CORE_SOT_MONGO_URI, LLM_GATEWAY_*, CHROMA_*, EMBEDDING_*, ELASTICSEARCH_URL)
plus ``scripts/`` and the application code::

    docker compose run --rm --no-deps -e APPLICATION_PASSWORD='...' application \\
        python scripts/diagnose_writing_gate.py --project-id <benchmark-project> \\
        --username <account>

``--username`` is needed whenever the idempotent seed runs: D8-3a put the seed's
project/draft/version writes behind a session (without it they 401). Skip it
together with the seed by passing ``--current-position``.

By default this seeds the benchmark context idempotently (the same
``b2b-writing-loop-context-v1`` draft/version ``benchmark_writing_loop.py``
creates) so the operator only supplies the project id. Pass
``--current-position DRAFT_ID VERSION_ID`` to reuse an existing draft and avoid
even that idempotent seed write.
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

from services.application.app.context_search.models import (
    ContextBudget,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.gate_live_diag import (
    RawCaptureProvider,
    format_diagnosis,
    run_gate_diagnosis,
)
from services.application.app.writing.gate_prompt import WRITING_GATE_PROMPT_VERSION
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.llm_gateway.app.provider import LLMProvider
from scripts.script_auth import add_login_arguments, authenticate_client


# Defaults mirror the benchmark_writing_loop.py `terminal_pass` case so an
# operator can diagnose immediately after observing the 502. Keep these in sync
# with that script's _FINDING / BENCHMARK_CASES[0] if they change.
_DEFAULT_INSTRUCTION = (
    "아래 후보의 연속성만 고친 뒤 Writing Gate는 pass로 종료하세요. "
    "추가 검색이나 추가 수정은 요청하지 마세요."
)
_DEFAULT_CANDIDATE_TEXT = (
    "민아는 역 플랫폼에 서 있었다. 비는 이미 그쳤고, "
    "그녀는 파란 편지를 주머니에 넣었다."
)
_DEFAULT_FINDING = {
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
_CONTEXT_SEED_IDEMPOTENCY_KEY = "b2b-writing-loop-context-v1"


@dataclass(frozen=True, slots=True)
class DiagServices:
    reviser: object
    reporter: object
    gate: object
    context_search: object
    capture: RawCaptureProvider
    model: str | None
    max_tokens: int


def build_services(*, gateway_provider: LLMProvider | None = None) -> DiagServices:
    """Wire the production collaborators, reusing ``main``'s factories.

    The Gate is built through ``_default_writing_gate_service(provider=...)`` so
    its prompt template and ``LLM_GATEWAY_MODEL`` / ``WRITING_GATE_MAX_TOKENS``
    config are the production contract by construction (not re-derived). Only the
    Gate routes through the capturing provider; revise/report use the real
    gateway provider so the captured raw output is the Gate's alone.
    """
    # Imported lazily so unit tests can exercise build_search_request /
    # build_services with a controlled environment without importing the whole
    # application at module load.
    from services.application.app.main import (
        _build_chroma_vector_index,
        _build_embedding_provider,
        _build_report_service,
        _build_revise_service,
        _default_analysis_service,
        _default_context_search_service,
        _default_core_sot_service,
        _default_index_sync_outbox_service,
        _default_memory_service,
        _default_writing_gate_service,
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

    def _gateway() -> LLMProvider:
        return GatewayGenerateProvider(
            base_url=base_url,
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
        )

    # The Gate observes its own raw output via the capture wrapper; revise and
    # report use plain gateway providers (their raw output is out of scope here).
    capture = RawCaptureProvider(gateway_provider or _gateway())
    gate = _default_writing_gate_service(provider=capture)
    if gate is None:  # pragma: no cover — base_url guard above makes this unreachable
        raise RuntimeError("writing gate service is not configured")

    reviser = _build_revise_service(_gateway())
    reporter = _build_report_service(_gateway())

    core_sot = _default_core_sot_service()
    sync_outbox = _default_index_sync_outbox_service()
    memory = _default_memory_service(reindex_outbox=sync_outbox)
    analysis = _default_analysis_service(core_sot, reindex_outbox=sync_outbox)
    embeddings = _build_embedding_provider()
    vector_index = _build_chroma_vector_index() or InMemoryVectorIndexAdapter()
    context_search = _default_context_search_service(
        core_sot,
        vector_index=vector_index,
        embeddings=embeddings,
        memory=memory,
        analysis=analysis,
    )
    if context_search is None:
        raise RuntimeError("context search service is not configured")

    return DiagServices(
        reviser=reviser, reporter=reporter, gate=gate,
        context_search=context_search, capture=capture,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_GATE_MAX_TOKENS", "1024")),
    )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no"}


def build_search_request(
    *, project_id: str, instruction: str, query: str | None,
    position: CurrentPosition | None, max_tokens: int,
) -> ContextSearchRequest:
    """Build the same ContextSearchRequest the revise-and-gate endpoint builds.

    Parity is structural: ``needs`` is the endpoint's exact tuple (imported from
    ``main``), purpose is WRITING_CONTEXT, the query falls back to the
    instruction, and the budget mirrors the request body's ``max_tokens``.
    """
    from services.application.app.main import _WRITING_CONTINUE_SCENE_NEEDS

    return ContextSearchRequest(
        project_id=project_id,
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=_WRITING_CONTINUE_SCENE_NEEDS,
        query=query or instruction,
        current_position=position,
        context_budget=ContextBudget(max_tokens=max_tokens),
    )


def _finding_from_dict(value: dict[str, str]) -> WritingGateFinding:
    return WritingGateFinding(
        finding_type=WritingGateFindingType(value["type"]),
        severity=WritingGateSeverity(value["severity"]),
        message=value["message"],
        evidence=value["evidence"],
        recommended_decision=WritingGateDecision(value["recommended_decision"]),
    )


async def seed_context(
    client: httpx.AsyncClient, *, base_url: str, project_id: str,
) -> dict[str, str]:
    """Idempotently create the benchmark current-scene pointer (same as the B2b
    benchmark). Returns the ``current_position`` the Gate context search needs.

    This is the only write the CLI performs and it is shared with
    ``benchmark_writing_loop.py``; pass ``--current-position`` to skip it.
    """
    root = base_url.rstrip("/")
    draft = await client.post(
        f"{root}/projects/{project_id}/drafts", json={"title": "B2b benchmark context"}
    )
    if draft.status_code != 200:
        raise RuntimeError(
            f"context seed draft failed: HTTP {draft.status_code}: {draft.text}"
        )
    draft_id = draft.json()["id"]
    version = await client.post(
        f"{root}/projects/{project_id}/drafts/{draft_id}/versions",
        json={
            "raw_text": _CONTEXT_SEED_TEXT,
            "idempotency_key": _CONTEXT_SEED_IDEMPOTENCY_KEY,
        },
    )
    if version.status_code != 200:
        raise RuntimeError(
            f"context seed version failed: HTTP {version.status_code}: {version.text}"
        )
    version_id = version.json()["draft_version"]["id"]
    return {"draft_id": draft_id, "version_id": version_id}


async def _run(args: argparse.Namespace) -> str:
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
            await authenticate_client(client, username=args.username)
            seeded = await seed_context(
                client, base_url=args.application_base_url, project_id=args.project_id,
            )
        position = CurrentPosition(
            draft_id=seeded["draft_id"], version_id=seeded["version_id"],
        )

    search_request = build_search_request(
        project_id=args.project_id, instruction=instruction, query=args.query,
        position=position, max_tokens=args.max_tokens,
    )
    request = WritingRequest(
        request_id=args.request_id,
        project_id=args.project_id,
        task_type=WritingTaskType.CONTINUE_SCENE,
        instruction=instruction,
    )
    candidate = WritingCandidate(
        request_id=args.request_id,
        project_id=args.project_id,
        task_type=WritingTaskType.CONTINUE_SCENE,
        output_type=WritingOutputType.DRAFT_PATCH,
        text=candidate_text,
    )
    diagnosis = await run_gate_diagnosis(
        context_search=services.context_search,
        search_request=search_request,
        reviser=services.reviser,
        reporter=services.reporter,
        gate=services.gate,
        capture=services.capture,
        request=request,
        candidate=candidate,
        finding=finding,
    )
    return format_diagnosis(
        diagnosis, request_id=args.request_id, project_id=args.project_id,
        model=services.model, max_tokens=services.max_tokens,
        prompt_version=WRITING_GATE_PROMPT_VERSION,
    )


class _PositionAction(argparse.Action):
    """Parse ``--current-position DRAFT_ID VERSION_ID`` as a 2-tuple."""

    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) != 2:
            raise argparse.ArgumentError(self, "expected DRAFT_ID VERSION_ID")
        setattr(namespace, self.dest, (values[0], values[1]))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator-only one-shot Writing Gate live diagnostics (D1=A).",
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--request-id", default="gate-diag")
    parser.add_argument("--instruction", default=None,
                        help="override the default terminal_pass instruction")
    parser.add_argument("--candidate-text", default=None,
                        help="override the default candidate prose")
    parser.add_argument("--finding-json", default=None,
                        help="override the default continuity finding (JSON object)")
    parser.add_argument("--query", default=None,
                        help="context search query (defaults to the instruction)")
    parser.add_argument(
        "--current-position", nargs=2, metavar=("DRAFT_ID", "VERSION_ID"),
        action=_PositionAction, default=None,
        help="reuse an existing draft/version and skip the idempotent context seed",
    )
    parser.add_argument("--application-base-url", default="http://application:8000",
                        help="deployed app URL used only for the idempotent context seed")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="context budget max_tokens (mirrors the loop request body)")
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
