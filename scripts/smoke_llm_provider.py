"""Run one text completion through the real HTTP transport and provider."""

from __future__ import annotations

import argparse
import asyncio
import json

from services.llm_gateway.app.client import LlamaCppProvider
from services.llm_gateway.app.httpx_transport import HttpxJsonTransport
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage


async def run_smoke(base_url: str, model: str, timeout_seconds: float) -> None:
    async with HttpxJsonTransport(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    ) as transport:
        provider = LlamaCppProvider(
            transport=transport,
            default_model=model,
            default_thinking=False,
            provider_name="gemma_local",
        )
        result = await provider.generate(
            ChatCompletionRequest(
                messages=(
                    ChatMessage(
                        role="user",
                        content="다음 문장을 그대로 답하세요: 연결 확인 완료",
                    ),
                ),
                thinking=False,
                temperature=0,
                max_tokens=32,
            )
        )

    print(
        json.dumps(
            {
                "model": result.model,
                "content": result.content,
                "finish_reason": result.finish_reason,
                "usage": {
                    "prompt_tokens": result.usage.prompt_tokens,
                    "completion_tokens": result.usage.completion_tokens,
                    "total_tokens": result.usage.total_tokens,
                },
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--model",
        default="google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    asyncio.run(run_smoke(args.base_url, args.model, args.timeout))


if __name__ == "__main__":
    main()
