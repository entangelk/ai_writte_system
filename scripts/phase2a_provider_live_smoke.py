"""Live smoke for Phase 2A Application -> Gateway -> llama.cpp wiring."""

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

from services.application.app.analysis.extractor import (
    VersionedPromptAnalysisExtractionAdapter,
)
from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.runner import AnalysisExtractionRunner
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import create_app as create_application_app
from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.main import create_app as create_gateway_app
from services.llm_gateway.app.payload import ChatCompletionRequest
from services.llm_gateway.app.provider import GenerationResult, LLMProvider


DEFAULT_LLAMA_BASE_URL = "http://192.168.1.29:9080"
DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an in-memory Core SOT snapshot/source_ref catalog, then run "
            "the Phase 2A analysis endpoint through the real Gateway provider."
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
        default=float(os.environ.get("PHASE2A_SMOKE_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("ANALYSIS_EXTRACT_MAX_TOKENS", "2048")),
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    llama_transport = HttpxJsonTransport(
        base_url=args.llama_base_url,
        timeout_seconds=args.timeout_seconds,
        trust_env=False,
    )
    try:
        gateway_app = create_gateway_app(
            provider=LlamaCppProvider(
                transport=llama_transport,
                default_model=args.model,
                default_thinking=False,
                provider_name="phase2a_live_smoke",
            ),
            llama_base_url=args.llama_base_url,
        )
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(
            InMemoryAnalysisRepository(),
            source_ref_resolver=CoreSotSourceAdapter(core_sot),
        )
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        prompt_templates.seed_analysis_extract_v1()
        prompt_templates.seed_analysis_extract_v2()
        prompt_templates.seed_analysis_extract_v3()
        gateway_provider = _RecordingProvider(
            GatewayGenerateProvider(
                base_url="http://gateway-smoke",
                timeout_seconds=args.timeout_seconds + 5,
                trust_env=False,
                transport=httpx.ASGITransport(app=gateway_app),
            )
        )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis,
            snapshot_loader=CoreSotSourceAdapter(core_sot),
            extractor=VersionedPromptAnalysisExtractionAdapter(
                gateway_provider,
                prompt_templates=prompt_templates,
                source_ref_catalog=core_sot,
                model=args.model,
                max_tokens=args.max_tokens,
            ),
        )
        app = create_application_app(core_sot, analysis, runner)
        summary = await _run_smoke(
            app=app,
            args=args,
            provider=gateway_provider,
        )
    finally:
        await llama_transport.aclose()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    job_status = summary["final_job"]["status"]
    if job_status in {"succeeded", "failed"}:
        return 0
    return 1


async def _run_smoke(
    *,
    app,
    args: argparse.Namespace,
    provider: "_RecordingProvider",
) -> dict[str, Any]:
    raw_text = (
        "민아는 파란 편지를 발견했다.\n\n"
        "준호는 민아에게 오래된 지도에 대해 말했다."
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://application-smoke",
        timeout=httpx.Timeout(args.timeout_seconds + 10),
    ) as client:
        project = (
            await client.post("/projects", json={"name": "Phase 2A Live Smoke"})
        ).json()
        draft = (
            await client.post(
                f"/projects/{project['id']}/drafts",
                json={"title": "Smoke draft"},
            )
        ).json()
        saved = (
            await client.post(
                f"/projects/{project['id']}/drafts/{draft['id']}/versions",
                json={"raw_text": raw_text, "idempotency_key": "smoke-save-1"},
            )
        ).json()
        snapshot_id = saved["snapshot"]["id"]
        source_refs = []
        for quote in ("민아", "파란 편지", "준호"):
            source_refs.append(
                (
                    await client.post(
                        f"/projects/{project['id']}/snapshots/{snapshot_id}"
                        "/source-refs",
                        json=_source_ref_request(raw_text, quote),
                    )
                ).json()
            )
        job_response = await client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": snapshot_id, "idempotency_key": "smoke-job-1"},
        )
        job = job_response.json()["job"]
        run_response = await client.post(
            f"/projects/{project['id']}/analysis/jobs/{job['id']}/run"
        )
        final_job_response = await client.get(
            f"/projects/{project['id']}/analysis/jobs/{job['id']}"
        )
        candidates_response = await client.get(
            f"/projects/{project['id']}/analysis/jobs/{job['id']}/candidates"
        )

    return {
        "llama_base_url": args.llama_base_url,
        "model": args.model,
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
        "final_job": final_job_response.json(),
        "candidates": candidates_response.json()["candidates"],
        "provider_result": provider.to_summary(),
        "provider_results": provider.to_summaries(),
    }


def _source_ref_request(raw_text: str, quote: str) -> dict[str, int]:
    start = raw_text.index(quote)
    return {"start_offset": start, "end_offset": start + len(quote)}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


class _RecordingProvider:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self.result: GenerationResult | None = None
        self.results: list[GenerationResult] = []
        self.error: str | None = None

    async def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        try:
            self.result = await self._provider.generate(request)
            self.results.append(self.result)
        except Exception as exc:
            self.error = str(exc)
            raise
        return self.result

    def to_summary(self) -> dict[str, object] | None:
        if self.result is None:
            if self.error is None:
                return None
            return {"error": self.error}
        return {
            "model": self.result.model,
            "finish_reason": self.result.finish_reason,
            "prompt_tokens": self.result.usage.prompt_tokens,
            "completion_tokens": self.result.usage.completion_tokens,
            "content": self.result.content,
        }

    def to_summaries(self) -> list[dict[str, object]]:
        return [
            {
                "model": result.model,
                "finish_reason": result.finish_reason,
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "content": result.content,
            }
            for result in self.results
        ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
