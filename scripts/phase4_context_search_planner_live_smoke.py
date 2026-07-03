"""Live smoke for the Phase 4 Slice 4.2 terminal-JSON SearchPlan planner.

Builds a ContextSearchRequest, seeds the versioned prompt template, and runs
``TerminalJsonSearchPlanner.build_plan`` against the real Gateway -> llama.cpp
wiring. Prints the produced SearchPlan (or the llm_error) as JSON.

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

from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.context_search.models import (
    ContextBudget,
    ContextNeed,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.context_search.planner import (
    TerminalJsonSearchPlanner,
    seed_context_search_plan_template,
)
from services.application.app.context_search.service import ContextSearchFailed
from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.main import create_app as create_gateway_app


DEFAULT_LLAMA_BASE_URL = "http://192.168.1.29:9080"
DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 4 terminal-JSON SearchPlan planner through the real "
            "Gateway provider and print the produced plan."
        )
    )
    parser.add_argument(
        "--llama-base-url",
        default=os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LLAMA_DEFAULT_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("PHASE4_SMOKE_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("CONTEXT_SEARCH_PLAN_MAX_TOKENS", "1024")),
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    llama_transport = HttpxJsonTransport(
        base_url=args.llama_base_url,
        timeout_seconds=args.timeout_seconds,
        trust_env=False,
    )
    request = ContextSearchRequest(
        project_id="phase4-smoke-project",
        purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CURRENT_SCENE, ContextNeed.SOURCE_QUOTE),
        query="아린이 항구에서 낡은 단검을 발견하는 장면을 이어 쓴다",
        current_position=CurrentPosition(draft_id="draft-1", version_id="v-1"),
        context_budget=ContextBudget(max_tokens=1536),
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
                provider_name="phase4_live_smoke",
            ),
            llama_base_url=args.llama_base_url,
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_context_search_plan_template(prompt_templates)
        planner = TerminalJsonSearchPlanner(
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
            plan = await planner.build_plan(request)
        except ContextSearchFailed as exc:
            summary["status"] = "failed"
            summary["error_type"] = exc.error_type.value
            summary["detail"] = exc.detail
        else:
            summary["status"] = "succeeded"
            summary["plan"] = {
                "plan_id": plan.plan_id,
                "project_id": plan.project_id,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "need": step.need.value,
                        "tools": [tool.value for tool in step.tools],
                        "query": step.query,
                    }
                    for step in plan.steps
                ],
            }
    finally:
        await llama_transport.aclose()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("status") in {"succeeded", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
