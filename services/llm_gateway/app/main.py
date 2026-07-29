"""FastAPI shell for the LLM gateway service."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import Any

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel

from .client import LlamaCppProvider
from .errors import ProviderError, ProviderErrorCode
from .httpx_transport import HttpxJsonTransport
from .payload import ChatCompletionRequest, ChatMessage
from .provider import LLMProvider


DEFAULT_LLAMA_BASE_URL = "http://host.docker.internal:9080"
DEFAULT_PROVIDER_NAME = "gemma_local"


class GenerateMessage(BaseModel):
    role: str
    content: str | None = None


class GenerateRequest(BaseModel):
    messages: list[GenerateMessage]
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    thinking: bool | None = None
    chat_template_kwargs: dict[str, Any] | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _build_provider() -> tuple[LLMProvider, HttpxJsonTransport, str]:
    base_url = os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL)
    transport = HttpxJsonTransport(
        base_url=base_url,
        timeout_seconds=_env_float("LLAMA_TIMEOUT_SECONDS", 120.0),
        trust_env=_env_bool("LLAMA_TRUST_ENV", False),
    )
    provider = LlamaCppProvider(
        transport=transport,
        default_model=os.environ.get("LLAMA_DEFAULT_MODEL", "gemma-local"),
        default_thinking=_env_bool("LLAMA_DEFAULT_THINKING", False),
        provider_name=os.environ.get("LLAMA_PROVIDER_NAME", DEFAULT_PROVIDER_NAME),
    )
    return provider, transport, base_url


def _status_for_error(error: ProviderError) -> int:
    if error.code is ProviderErrorCode.TIMEOUT:
        return 504
    if error.code is ProviderErrorCode.OVERLOADED:
        return 429
    if error.code is ProviderErrorCode.UNAVAILABLE:
        return 503
    if error.code is ProviderErrorCode.REQUEST_REJECTED:
        return 400
    return 502


def _request_from_payload(payload: GenerateRequest) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=tuple(
            ChatMessage(role=message.role, content=message.content)
            for message in payload.messages
        ),
        model=payload.model,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
        thinking=payload.thinking,
        chat_template_kwargs=payload.chat_template_kwargs,
    )


def create_app(
    provider: LLMProvider | None = None,
    *,
    llama_base_url: str | None = None,
) -> FastAPI:
    owned_transport: HttpxJsonTransport | None = None
    configured_base_url = llama_base_url

    if provider is None:
        provider, owned_transport, configured_base_url = _build_provider()
    elif configured_base_url is None:
        configured_base_url = os.environ.get(
            "LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if owned_transport is not None:
                await owned_transport.aclose()

    app = FastAPI(title="AI Writing System LLM Gateway", lifespan=lifespan)

    @app.get("/health")
    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        assert configured_base_url is not None
        try:
            async with httpx.AsyncClient(
                base_url=configured_base_url.rstrip("/"),
                timeout=httpx.Timeout(5.0),
                trust_env=_env_bool("LLAMA_TRUST_ENV", False),
            ) as client:
                response = await client.get("/health")
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="llama upstream is unavailable",
            ) from exc
        if not 200 <= response.status_code < 300:
            raise HTTPException(
                status_code=503,
                detail="llama upstream is not ready",
            )
        return {"status": "ready"}

    @app.post("/v1/generate")
    async def generate(payload: GenerateRequest) -> dict[str, object]:
        try:
            result = await provider.generate(_request_from_payload(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(
                status_code=_status_for_error(exc),
                detail=exc.to_envelope().to_dict()["error"],
            ) from exc

        return {
            "model": result.model,
            "text": result.content,
            "finish_reason": result.finish_reason,
            "usage": {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            },
            # 이 호출이 실제로 쓴 서버 창. `None`은 "모른다"이며 호출자는 그때 헤드룸을
            # 계산하지 않는다(지어낸 분모 위에서 계산하지 않기 위해서다).
            "context_window": result.context_window,
        }

    return app


app = create_app()
