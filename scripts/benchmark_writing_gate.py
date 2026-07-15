"""Run labelled Writing Gate quality fixtures through production Gate wiring.

This is a read-only classifier benchmark: no Core SOT, audit, Mongo, or file
writes.  The checked-in fixture prose is printed only as case ids and labels;
the JSON report contains no raw candidate/context text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.main import _default_writing_gate_service
from services.application.app.writing.gate_quality import (
    run_gate_quality_benchmark,
)
from services.application.app.writing.gate_prompt import (
    WRITING_GATE_PROMPT_VERSION,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score labelled Writing Gate boundaries with production wiring."
    )
    parser.add_argument("--repeats", type=int, default=3)
    return parser.parse_args()


def build_gate_service(*, provider=None):
    gate = _default_writing_gate_service(provider=provider)
    if gate is None:
        raise RuntimeError("LLM_GATEWAY_BASE_URL is required")
    return gate


async def _run(repeats: int) -> dict[str, object]:
    report = await run_gate_quality_benchmark(
        build_gate_service(), repeats=repeats,
    )
    return {
        "prompt_version": WRITING_GATE_PROMPT_VERSION,
        "model": os.environ.get("LLM_GATEWAY_MODEL") or None,
        "max_tokens": int(os.environ.get("WRITING_GATE_MAX_TOKENS", "1024")),
        **report,
    }


def main() -> int:
    args = parse_args()
    report = asyncio.run(_run(args.repeats))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["complete"] and report["matched_count"] == report["attempt_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
