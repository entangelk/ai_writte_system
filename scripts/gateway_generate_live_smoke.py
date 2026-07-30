"""Live smoke for the deployed LLM Gateway container's HTTP surface.

Most LLM live smokes wrap the gateway in-process (ASGITransport) and reach
llama.cpp directly, so the gateway *container* (its network transport, request
validation, and llama proxying over real HTTP) is only exercised indirectly by
the Phase 4 deployed e2e smoke. This smoke closes that gap: it POSTs directly to
the running gateway container's `POST /v1/generate` and asserts the contract
response shape (`text`, `finish_reason`, `usage.*_tokens`), verifying the
containerized gateway -> llama path in isolation. Also checks GET /health.

Since K-3 (SoT v1.7.62) it also exercises the **context window guard** against the
real model server, which is the part fake transports cannot prove: that
`/apply-template` + `/tokenize` answer in the shape the guard counts, and that a
request whose `input + output cap` exceeds the window is rejected **before** the
model is called. The two guard cases are **self-calibrating** — the window and the
prompt size come from the warm-up response, so the boundary is computed from this
server rather than hardcoded (a hardcoded number silently stops testing the
boundary the moment the deployment's window changes).

Config: GATEWAY_BASE_URL (default http://gateway:8001 for in-network runs, or
http://localhost:8521 from the host). Exit 0 pass, 1 an assertion failed, 2 a
connection/config error. Prints a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

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


# K-3 가드 확인용 프롬프트. **한 단어 답**을 요구하는 이유가 있다: 경계 통과 케이스는
# `max_tokens`를 창 전체로 주므로, 모델이 길게 답하면 스모크가 몇 분씩 걸린다.
_GUARD_PROMPT = "다음 질문에 한 단어로만 답하세요. 바다의 색은?"


def _guard_case(client, args, *, max_tokens: int) -> tuple[int, dict, float]:
    started = time.monotonic()
    response = client.post(
        "/v1/generate",
        json={
            "messages": [{"role": "user", "content": _GUARD_PROMPT}],
            "model": args.model,
            "max_tokens": max_tokens,
        },
    )
    elapsed_ms = 1000 * (time.monotonic() - started)
    return response.status_code, response.json(), elapsed_ms


def _check_window_guard(client, args) -> dict:
    """창 가드를 **이 서버의 창 크기로** 검증한다(K-3).

    창과 프롬프트 크기를 응답에서 읽어 경계를 계산하므로, 배포의 창이 8192든 16384든
    같은 스모크가 그 배포의 경계를 본다. 창을 아직 모르면(첫 호출 경합·`/props` 실패)
    가드는 설계상 판정하지 않으므로 그 사실을 그대로 보고하고 넘어간다.
    """
    status, body, _ = _guard_case(client, args, max_tokens=32)
    assert status == 200, f"guard warm-up status {status}: {str(body)[:200]}"
    window = body.get("context_window")
    prompt_tokens = (body.get("usage") or {}).get("prompt_tokens")
    if window is None or not isinstance(prompt_tokens, int):
        return {
            "exercised": False,
            "why": "gateway does not know the window yet (first-call probe or "
                   "/props failure) — the guard does not judge such calls by design",
        }

    # 경계 바로 위: 합이 창을 1 넘는다 → 모델을 부르기 전에 거부돼야 한다.
    over_status, over_body, over_ms = _guard_case(
        client, args, max_tokens=window - prompt_tokens + 1)
    assert over_status == 400, (
        f"over-window request was not rejected: status {over_status}")
    detail = over_body.get("detail") or {}
    assert detail.get("code") == "provider_context_window_exceeded", (
        f"unexpected rejection code: {detail.get('code')}")
    assert detail.get("retryable") is False, "the rejection must not be retryable"
    # 모델을 부르지 않았다는 것의 관측 가능한 증거: 판정만 하고 돌아오므로 생성 지연이
    # 있을 수 없다. 넉넉한 상한으로 잡아 LAN 변동에 흔들리지 않게 한다.
    assert over_ms < 2000, f"rejection took {over_ms:.0f}ms — was the model called?"

    # 경계 바로 아래: 합이 정확히 창이면 통과해야 한다(`<=`). 이 절반이 없으면 가드를
    # 과잉으로 좁히는 변경이 스모크를 통과한다.
    edge_status, edge_body, edge_ms = _guard_case(
        client, args, max_tokens=window - prompt_tokens)
    assert edge_status == 200, (
        f"a request whose input+output equals the window was rejected: "
        f"{edge_status} {str(edge_body)[:200]}")

    return {
        "exercised": True,
        "context_window": window,
        "prompt_tokens": prompt_tokens,
        "rejected_at_max_tokens": window - prompt_tokens + 1,
        "rejection_ms": round(over_ms),
        "rejection_message": detail.get("message"),
        "allowed_at_max_tokens": window - prompt_tokens,
        "allowed_ms": round(edge_ms),
    }


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
        guard = _check_window_guard(client, args)

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
        # K-3 창 가드(SoT v1.7.62). `exercised: false`는 실패가 아니라 "창을 몰라서
        # 판정 대상이 아니었다"는 의도된 상태다.
        "context_window_guard": guard,
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
