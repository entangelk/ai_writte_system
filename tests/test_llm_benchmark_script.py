import io
import json
import unittest

from scripts.benchmark_llm_provider import (
    BenchmarkCase,
    BenchmarkRun,
    build_report,
    main,
    run_benchmark,
    summarize_runs,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import (
    FakeLLMProvider,
    GenerationResult,
    TokenUsage,
)


class _FakeClock:
    def __init__(self, values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


class BenchmarkScriptTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_benchmark_records_success_metrics(self):
        provider = FakeLLMProvider(
            [
                GenerationResult(
                    model="gemma",
                    content="ok",
                    finish_reason="stop",
                    usage=TokenUsage(prompt_tokens=4, completion_tokens=6),
                )
            ]
        )
        case = BenchmarkCase(
            name="sample",
            prompt="hello",
            max_tokens=32,
            temperature=0.0,
        )

        runs = await run_benchmark(
            provider,
            model="gemma",
            cases=(case,),
            repeats=1,
            warmups=0,
            now=_FakeClock([10.0, 12.0]),
        )

        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertTrue(run.success)
        self.assertEqual(run.latency_ms, 2000.0)
        self.assertEqual(run.total_tokens, 10)
        self.assertEqual(run.tokens_per_second, 3.0)
        self.assertEqual(provider.requests[0].model, "gemma")
        self.assertEqual(provider.requests[0].max_tokens, 32)

    async def test_run_benchmark_records_provider_error_without_retrying(self):
        provider = FakeLLMProvider(
            [
                ProviderError(
                    code=ProviderErrorCode.TIMEOUT,
                    message="timed out",
                    retryable=True,
                    provider="gemma_local",
                )
            ]
        )
        case = BenchmarkCase(
            name="timeout_case",
            prompt="hello",
            max_tokens=32,
            temperature=0.0,
        )

        runs = await run_benchmark(
            provider,
            model="gemma",
            cases=(case,),
            repeats=1,
            warmups=0,
            now=_FakeClock([1.0, 1.25]),
        )

        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertFalse(run.success)
        self.assertEqual(run.latency_ms, 250.0)
        self.assertEqual(run.error_code, "provider_timeout")
        self.assertIs(run.error_retryable, True)

    async def test_warmup_provider_error_is_recorded_without_aborting(self):
        provider = FakeLLMProvider(
            [
                ProviderError(
                    code=ProviderErrorCode.UNAVAILABLE,
                    message="warming failed",
                    retryable=True,
                    provider="gemma_local",
                ),
                GenerationResult(
                    model="gemma",
                    content="after warmup",
                    finish_reason="stop",
                    usage=TokenUsage(prompt_tokens=3, completion_tokens=2),
                ),
            ]
        )
        case = BenchmarkCase(
            name="warmup_case",
            prompt="hello",
            max_tokens=32,
            temperature=0.0,
        )

        runs = await run_benchmark(
            provider,
            model="gemma",
            cases=(case,),
            repeats=1,
            warmups=1,
            now=_FakeClock([1.0, 1.1, 2.0, 2.5]),
        )

        self.assertEqual(len(runs), 2)
        warmup = runs[0]
        self.assertEqual(warmup.iteration, 0)
        self.assertFalse(warmup.success)
        self.assertAlmostEqual(warmup.latency_ms, 100.0)
        self.assertEqual(warmup.error_code, "provider_unavailable")
        measured = runs[1]
        self.assertEqual(measured.iteration, 1)
        self.assertTrue(measured.success)
        self.assertEqual(measured.total_tokens, 5)

    async def test_invalid_repeat_and_warmup_are_rejected(self):
        provider = FakeLLMProvider(())
        case = BenchmarkCase(
            name="sample",
            prompt="hello",
            max_tokens=32,
            temperature=0.0,
        )

        with self.assertRaises(ValueError):
            await run_benchmark(
                provider,
                model="gemma",
                cases=(case,),
                repeats=0,
                warmups=0,
            )
        with self.assertRaises(ValueError):
            await run_benchmark(
                provider,
                model="gemma",
                cases=(case,),
                repeats=1,
                warmups=-1,
            )


class BenchmarkSummaryTests(unittest.TestCase):
    def test_summary_groups_success_and_failure_by_case(self):
        runs = [
            _run("case-a", success=True, latency_ms=100, total_tokens=10, tps=5),
            _run("case-a", success=True, latency_ms=300, total_tokens=12, tps=7),
            _run(
                "case-a",
                success=False,
                latency_ms=50,
                error_code="provider_timeout",
            ),
        ]

        summary = summarize_runs(runs)

        self.assertEqual(summary["case-a"]["runs"], 3)
        self.assertEqual(summary["case-a"]["successes"], 2)
        self.assertEqual(summary["case-a"]["failures"], 1)
        self.assertEqual(summary["case-a"]["latency_ms_p50"], 100)
        self.assertEqual(summary["case-a"]["latency_ms_p95"], 300)
        self.assertEqual(summary["case-a"]["max_total_tokens"], 12)
        self.assertEqual(summary["case-a"]["avg_output_tokens_per_second"], 6.0)
        self.assertEqual(summary["case-a"]["error_codes"], ["provider_timeout"])

    def test_build_report_keeps_raw_runs_and_summary(self):
        runs = [
            BenchmarkRun(
                case="case-a",
                iteration=2,
                success=True,
                latency_ms=100.1234,
                prompt_tokens=4,
                completion_tokens=6,
                total_tokens=10,
                tokens_per_second=5.4321,
                finish_reason="stop",
                output_chars=42,
            )
        ]

        report = build_report(
            base_url="http://llama.test:9080",
            model="gemma",
            repeats=1,
            warmups=0,
            runs=runs,
        )

        self.assertEqual(report["metadata"]["base_url"], "http://llama.test:9080")
        self.assertEqual(report["metadata"]["model"], "gemma")
        self.assertIn("created_at", report["metadata"])
        self.assertEqual(report["summary"]["case-a"]["successes"], 1)
        self.assertEqual(
            report["runs"][0],
            {
                "case": "case-a",
                "iteration": 2,
                "success": True,
                "latency_ms": 100.123,
                "prompt_tokens": 4,
                "completion_tokens": 6,
                "total_tokens": 10,
                "tokens_per_second": 5.432,
                "finish_reason": "stop",
                "output_chars": 42,
                "error_code": None,
                "error_retryable": None,
                "error_message": None,
            },
        )

    def test_main_wires_cli_args_to_live_runner_and_prints_json(self):
        captured = {}

        async def fake_run_live(args):
            captured["args"] = args
            return {
                "metadata": {"base_url": args.base_url},
                "summary": {},
                "runs": [],
            }

        out = io.StringIO()

        main(
            [
                "--base-url",
                "http://llama.test:9080",
                "--model",
                "gemma-test",
                "--repeats",
                "2",
                "--warmups",
                "0",
                "--timeout",
                "5",
            ],
            run_live=fake_run_live,
            stdout=out,
        )

        args = captured["args"]
        self.assertEqual(args.base_url, "http://llama.test:9080")
        self.assertEqual(args.model, "gemma-test")
        self.assertEqual(args.repeats, 2)
        self.assertEqual(args.warmups, 0)
        self.assertEqual(args.timeout, 5.0)
        self.assertEqual(
            json.loads(out.getvalue())["metadata"]["base_url"],
            args.base_url,
        )


def _run(
    case,
    *,
    success,
    latency_ms,
    total_tokens=0,
    tps=None,
    error_code=None,
):
    from scripts.benchmark_llm_provider import BenchmarkRun

    return BenchmarkRun(
        case=case,
        iteration=1,
        success=success,
        latency_ms=latency_ms,
        total_tokens=total_tokens,
        tokens_per_second=tps,
        error_code=error_code,
    )


if __name__ == "__main__":
    unittest.main()
