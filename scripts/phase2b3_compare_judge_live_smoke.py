"""Live smoke for the Phase 2B.3.2 terminal-JSON compare judge.

Builds a (candidate, canonical memory) pair about the same character, seeds the
versioned ``analysis_compare_v1`` prompt template, and runs
``TerminalJsonCompareJudge.judge`` against the real Gateway -> llama.cpp wiring.
Prints the produced action label (or the InvalidJudgeResult) as JSON.

Sandbox note: internal Python/httpx cannot open external TCP, so this must run
outside the network sandbox against a reachable llama.cpp-compatible endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.application.app.analysis.compare import InvalidJudgeResult
from services.application.app.analysis.compare_judge import (
    TerminalJsonCompareJudge,
    seed_analysis_compare_template,
)
from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.scope import MemoryScope
from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.main import create_app as create_gateway_app


DEFAULT_LLAMA_BASE_URL = "http://192.168.1.29:9080"
DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 2B.3.2 terminal-JSON compare judge through the real "
            "Gateway provider and print the produced action."
        )
    )
    parser.add_argument(
        "--llama-base-url",
        default=os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL),
    )
    parser.add_argument(
        "--model", default=os.environ.get("LLAMA_DEFAULT_MODEL", DEFAULT_MODEL)
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("PHASE2B3_SMOKE_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("ANALYSIS_COMPARE_MAX_TOKENS", "512")),
    )
    return parser.parse_args()


def _candidate() -> AnalysisCandidate:
    return AnalysisCandidate(
        id="smoke-candidate", project_id="phase2b3-smoke", job_id="job-current",
        task_id="task-1", candidate_type=CHARACTER,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload={"name": "아린", "observation": "이제 단검을 능숙하게 다룬다"},
    )


def _memory() -> MemoryEntry:
    return MemoryEntry(
        id="smoke-memory", project_id="phase2b3-smoke", memory_type=CHARACTER,
        status=MemoryStatus.CANONICAL, provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5, source_ref_ids=("source-ref-0",),
        payload={"name": "아린", "observation": "검을 다룰 줄 모른다"}, version=1,
        analysis_job_id="job-prior", source_candidate_id="cand-0",
        promotion_mode=PromotionMode.MANUAL, applied_threshold=None,
        scope=MemoryScope(scope_type="character", scope_id="아린"),
    )


async def main() -> int:
    args = parse_args()
    llama_transport = HttpxJsonTransport(
        base_url=args.llama_base_url,
        timeout_seconds=args.timeout_seconds,
        trust_env=False,
    )
    summary: dict[str, object] = {
        "llama_base_url": args.llama_base_url,
        "model": args.model,
    }
    try:
        gateway_app = create_gateway_app(
            provider=LlamaCppProvider(
                transport=llama_transport,
                default_model=args.model,
                default_thinking=False,
                provider_name="phase2b3_live_smoke",
            ),
            llama_base_url=args.llama_base_url,
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_analysis_compare_template(prompt_templates)
        judge = TerminalJsonCompareJudge(
            GatewayGenerateProvider(
                base_url="http://gateway-smoke",
                timeout_seconds=args.timeout_seconds + 5,
                trust_env=False,
                transport=httpx.ASGITransport(app=gateway_app),
            ),
            prompt_templates=prompt_templates,
            model=args.model,
            max_tokens=args.max_tokens,
        )
        try:
            result = await judge.judge(candidate=_candidate(), memory=_memory())
        except InvalidJudgeResult as exc:
            summary["status"] = "failed"
            summary["detail"] = str(exc)
        else:
            summary["status"] = "succeeded"
            summary["action"] = result.action.value
            summary["rationale"] = result.rationale
    finally:
        await llama_transport.aclose()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("status") in {"succeeded", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
