"""Run a small reproducible benchmark through the LLM provider contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.errors import ProviderError
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider

DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    name: str
    prompt: str
    max_tokens: int
    temperature: float
    thinking: bool = False

    def to_request(self, *, model: str) -> ChatCompletionRequest:
        return ChatCompletionRequest(
            messages=(ChatMessage(role="user", content=self.prompt),),
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            thinking=self.thinking,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    case: str
    iteration: int
    success: bool
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_per_second: float | None = None
    finish_reason: str | None = None
    output_chars: int = 0
    error_code: str | None = None
    error_retryable: bool | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "iteration": self.iteration,
            "success": self.success,
            "latency_ms": round(self.latency_ms, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "tokens_per_second": (
                round(self.tokens_per_second, 3)
                if self.tokens_per_second is not None
                else None
            ),
            "finish_reason": self.finish_reason,
            "output_chars": self.output_chars,
            "error_code": self.error_code,
            "error_retryable": self.error_retryable,
            "error_message": self.error_message,
        }


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        name="short_smoke",
        prompt="다음 문장을 그대로 답하세요: 연결 확인 완료",
        max_tokens=32,
        temperature=0.0,
    ),
    BenchmarkCase(
        name="json_extraction",
        prompt=(
            "다음 원문에서 인물과 사건을 JSON object로만 요약하세요. "
            '스키마: {"character": string, "event": string}.\n\n'
            "민아는 오래된 역에서 파란 편지를 발견했고, "
            "그 편지에는 사라진 동생의 이름이 적혀 있었다."
        ),
        max_tokens=192,
        temperature=0.0,
    ),
    BenchmarkCase(
        name="continue_scene",
        prompt=(
            "다음 장면을 한국어 소설 문체로 2문단 이어 쓰세요.\n\n"
            "비가 그친 골목 끝에서 민아는 파란 문 앞에 멈춰 섰다."
        ),
        max_tokens=384,
        temperature=0.7,
    ),
)


async def run_benchmark(
    provider: LLMProvider,
    *,
    model: str,
    cases: Iterable[BenchmarkCase] = BENCHMARK_CASES,
    repeats: int,
    warmups: int,
    now: Callable[[], float] = perf_counter,
) -> list[BenchmarkRun]:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    if warmups < 0:
        raise ValueError("warmups must be >= 0")

    runs: list[BenchmarkRun] = []
    for case in cases:
        request = case.to_request(model=model)
        for _ in range(warmups):
            started = now()
            try:
                await provider.generate(request)
            except ProviderError as exc:
                elapsed_ms = (now() - started) * 1000
                runs.append(
                    BenchmarkRun(
                        case=case.name,
                        iteration=0,
                        success=False,
                        latency_ms=elapsed_ms,
                        error_code=exc.code.value,
                        error_retryable=exc.retryable,
                        error_message=str(exc),
                    )
                )
        for iteration in range(1, repeats + 1):
            started = now()
            try:
                result = await provider.generate(request)
            except ProviderError as exc:
                elapsed_ms = (now() - started) * 1000
                runs.append(
                    BenchmarkRun(
                        case=case.name,
                        iteration=iteration,
                        success=False,
                        latency_ms=elapsed_ms,
                        error_code=exc.code.value,
                        error_retryable=exc.retryable,
                        error_message=str(exc),
                    )
                )
                continue

            elapsed_ms = (now() - started) * 1000
            elapsed_seconds = max(elapsed_ms / 1000, 1e-9)
            runs.append(
                BenchmarkRun(
                    case=case.name,
                    iteration=iteration,
                    success=True,
                    latency_ms=elapsed_ms,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    total_tokens=result.usage.total_tokens,
                    tokens_per_second=(
                        result.usage.completion_tokens / elapsed_seconds
                    ),
                    finish_reason=result.finish_reason,
                    output_chars=len(result.content),
                )
            )
    return runs


def summarize_runs(runs: Iterable[BenchmarkRun]) -> dict[str, Any]:
    grouped: dict[str, list[BenchmarkRun]] = {}
    for run in runs:
        grouped.setdefault(run.case, []).append(run)

    summaries: dict[str, Any] = {}
    for case, case_runs in sorted(grouped.items()):
        successes = [run for run in case_runs if run.success]
        failures = [run for run in case_runs if not run.success]
        latencies = sorted(run.latency_ms for run in successes)
        total_tokens = [run.total_tokens for run in successes]
        tokens_per_second = [
            run.tokens_per_second
            for run in successes
            if run.tokens_per_second is not None
        ]
        summaries[case] = {
            "runs": len(case_runs),
            "successes": len(successes),
            "failures": len(failures),
            "latency_ms_p50": _percentile(latencies, 50),
            "latency_ms_p95": _percentile(latencies, 95),
            "max_total_tokens": max(total_tokens) if total_tokens else None,
            "avg_output_tokens_per_second": (
                round(sum(tokens_per_second) / len(tokens_per_second), 3)
                if tokens_per_second
                else None
            ),
            "error_codes": sorted(
                {
                    run.error_code
                    for run in failures
                    if run.error_code is not None
                }
            ),
        }
    return summaries


def build_report(
    *,
    base_url: str,
    model: str,
    repeats: int,
    warmups: int,
    runs: Iterable[BenchmarkRun],
) -> dict[str, Any]:
    run_list = list(runs)
    return {
        "metadata": {
            "created_at": datetime.now(UTC).isoformat(),
            "base_url": base_url,
            "model": model,
            "repeats": repeats,
            "warmups": warmups,
        },
        "summary": summarize_runs(run_list),
        "runs": [run.to_dict() for run in run_list],
    }


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    index = min(
        len(values) - 1,
        int(round((percentile / 100) * (len(values) - 1))),
    )
    return round(values[index], 3)


async def _run_live(args: argparse.Namespace) -> dict[str, Any]:
    async with HttpxJsonTransport(
        base_url=args.base_url,
        timeout_seconds=args.timeout,
    ) as transport:
        provider = LlamaCppProvider(
            transport=transport,
            default_model=args.model,
            default_thinking=False,
            provider_name="gemma_local",
        )
        runs = await run_benchmark(
            provider,
            model=args.model,
            repeats=args.repeats,
            warmups=args.warmups,
        )
    return build_report(
        base_url=args.base_url,
        model=args.model,
        repeats=args.repeats,
        warmups=args.warmups,
        runs=runs,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    run_live: Callable[[argparse.Namespace], Any] = _run_live,
    stdout: TextIO | None = None,
) -> None:
    args = build_arg_parser().parse_args(argv)
    report = asyncio.run(run_live(args))
    print(json.dumps(report, ensure_ascii=False, indent=2), file=stdout)


if __name__ == "__main__":
    main()
