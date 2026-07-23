"""Live smoke for the deployed LLM Gateway container's HTTP surface.

Most LLM live smokes wrap the gateway in-process (ASGITransport) and reach
llama.cpp directly, so the gateway *container* (its network transport, request
validation, and llama proxying over real HTTP) is only exercised indirectly by
the Phase 4 deployed e2e smoke. This smoke closes that gap: it POSTs directly to
the running gateway container's `POST /v1/generate` and asserts the contract
response shape (`text`, `finish_reason`, `usage.*_tokens`), verifying the
containerized gateway -> llama path in isolation. Also checks GET /health.

Config: GATEWAY_BASE_URL (default http://gateway:8001 for in-network runs, or
http://localhost:8521 from the host). Exit 0 pass, 1 an assertion failed, 2 a
connection/config error. Prints a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

DEFAULT_GATEWAY_BASE_URL = "http://gateway:8001"
DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway-base-url",
        default=os.environ.get("GATEWAY_BASE_URL", DEFAULT_GATEWAY_BASE_URL),
    )
    parser.add_argument(
        "--model", default=os.environ.get("LLAMA_DEFAULT_MODEL", DEFAULT_MODEL)
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("GATEWAY_SMOKE_TIMEOUT_SECONDS", "180")),
    )
    return parser.parse_args(argv)


def run_smoke(args: argparse.Namespace) -> dict:
    base_url = args.gateway_base_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=args.timeout_seconds) as client:
        health = client.get("/health")
        assert health.status_code == 200, f"/health status {health.status_code}"

        response = client.post(
            "/v1/generate",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "다음 문장을 그대로 답하세요: 연결 확인 완료",
                    }
                ],
                "model": args.model,
                "max_tokens": 64,
            },
        )
        assert response.status_code == 200, (
            f"/v1/generate status {response.status_code}: {response.text[:200]}"
        )
        body = response.json()

    # Contract shape (services/llm_gateway/app/main.py generate()).
    assert isinstance(body.get("text"), str) and body["text"], "missing text"
    assert "finish_reason" in body, "missing finish_reason"
    usage = body.get("usage") or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert isinstance(usage.get(key), int), f"usage.{key} not an int"

    return {
        "ok": True,
        "gateway_base_url": base_url,
        "model": body.get("model"),
        "finish_reason": body.get("finish_reason"),
        "usage": usage,
        "text_preview": body["text"][:80],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_smoke(args)
    except AssertionError as exc:
        print(json.dumps({"ok": False, "assertion": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:  # connection/config
        print(json.dumps({"ok": False, "error": repr(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
