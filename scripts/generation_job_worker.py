"""Run the async generation worker (async-pad 증분 2b).

Claims ``writing_generation_jobs`` (the long presets the generate endpoint runs
in the background) and executes them through the same context-build + generate
pipeline the sync path uses, appending each result to the scratch store for the
pad. Mirrors ``index_sync_worker.py``: one-shot by default, ``--loop`` runs a
daemon draining until SIGTERM, and the atomic ``claim_next`` (find_one_and_update
+ lease) is what makes concurrent/replica execution safe.

This is a **separate** loop from the index-sync worker (verification H3 of the
brief): the index outbox is idempotent single-shot CDC, generation jobs are
long-lived non-idempotent user requests — different lifecycles, so a separate
service/script rather than a second sink on the outbox.

Unlike the index worker this calls the **LLM gateway** (the worker's first LLM
access), so it requires ``LLM_GATEWAY_BASE_URL``; without it there is nothing to
run and the worker exits non-zero.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.main import build_async_generation_collaborators
from services.application.app.writing.generation_worker import (
    GenerationCollaborators,
    execute_generation_job,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the async generation worker (one-shot by default; "
        "--loop runs a claiming daemon until SIGTERM/SIGINT)."
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run as a long-lived daemon: claim+execute until SIGTERM/SIGINT.",
    )
    parser.add_argument(
        "--interval", type=float,
        default=float(os.environ.get("GENERATION_WORKER_INTERVAL", "5")),
        help="Seconds to idle-sleep between passes when no job is claimable.",
    )
    return parser.parse_args(argv)


def _require_collaborators(
    build_fn: Callable[[], GenerationCollaborators | None],
) -> GenerationCollaborators:
    collaborators = build_fn()
    if collaborators is None:
        raise ValueError(
            "async generation worker requires LLM_GATEWAY_BASE_URL (and a "
            "context search service); nothing to run without a gateway"
        )
    return collaborators


def run_pass(collaborators: GenerationCollaborators) -> dict[str, Any] | None:
    """Claim and execute one job if available. Returns a result summary, or None
    when nothing was claimable."""
    job = collaborators.jobs.claim_next()
    if job is None:
        return None
    done = asyncio.run(execute_generation_job(job, collaborators))
    return {
        "job_id": done.id,
        "status": done.status.value,
        "failure_reason": (
            done.failure_reason.value if done.failure_reason is not None else None
        ),
    }


class _GracefulShutdown:
    """SIGTERM/SIGINT flag so the loop exits at the next job boundary (the
    in-flight job finishes first). The atomic claim is what makes concurrent
    execution safe; this only governs orderly shutdown of one loop."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_args: object) -> None:
        self.requested = True

    def is_requested(self) -> bool:
        return self.requested


def _install_signal_handlers(stop: _GracefulShutdown) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)


def run_loop(
    args: argparse.Namespace,
    *,
    build_fn: Callable[[], GenerationCollaborators | None] =
    build_async_generation_collaborators,
    run_pass_fn: Callable[[GenerationCollaborators], dict[str, Any] | None] =
    run_pass,
    stop: _GracefulShutdown,
    sleep_fn: Callable[[float], None] = time.sleep,
    stdout: TextIO | None = None,
) -> int:
    collaborators = _require_collaborators(build_fn)
    stream = stdout if stdout is not None else sys.stdout

    def emit(event: dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), file=stream)
        stream.flush()

    emit({"event": "loop_started", "interval_seconds": args.interval})
    passes = 0
    while True:
        if stop.is_requested():
            break
        result = run_pass_fn(collaborators)
        passes += 1
        emit({"event": "pass", "pass": passes, "result": result})
        if stop.is_requested():
            break
        if result is None:
            sleep_fn(args.interval)
    emit({"event": "loop_stopped", "passes": passes})
    return 0


def main(
    argv: list[str] | None = None,
    *,
    build_fn: Callable[[], GenerationCollaborators | None] =
    build_async_generation_collaborators,
    run_pass_fn: Callable[[GenerationCollaborators], dict[str, Any] | None] =
    run_pass,
    run_loop_fn=run_loop,
    install_signal_handlers_fn=_install_signal_handlers,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = parse_args(argv)
    err = stderr if stderr is not None else sys.stderr
    stream = stdout if stdout is not None else sys.stdout
    try:
        if args.loop:
            stop = _GracefulShutdown()
            install_signal_handlers_fn(stop)
            return run_loop_fn(
                args, build_fn=build_fn, run_pass_fn=run_pass_fn,
                stop=stop, stdout=stdout)
        collaborators = _require_collaborators(build_fn)
        result = run_pass_fn(collaborators)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    print(json.dumps({"result": result}, ensure_ascii=False, indent=2,
                     sort_keys=True), file=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
