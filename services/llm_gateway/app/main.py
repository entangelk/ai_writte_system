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
from .fallback import FallbackProvider, SlidingWindowRateLimiter, parse_env_list
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


class TokenizeRequest(BaseModel):
    text: str


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


def _chat_endpoint(raw: str) -> tuple[str, str]:
    """`LLAMA_BASE_URL` → (base_url, chat_path). **붙여넣은 벤더 주소가 그대로 동작해야 한다.**

    임베딩 어댑터의 `_strip_version_suffix` 와 같은 관례다(문서가 인쇄하는 주소를 그대로
    붙여넣어도 404 가 아니어야 한다 — 안 그러면 실패는 원인에서 먼 자리에서 나온다):

    - `…/chat/completions` 으로 끝나면 → 전체 엔드포인트로 보고 그 결론을 유지한다.
    - `/v1beta/openai` 로 끝나면(구글 Gemini API 의 OpenAI 호환 루트 — **접미 `/v1` 이
      없다**) → `/chat/completions` 를 붙인다.
    - 그 외(llama.cpp·OpenAI·OpenRouter) → 접미 `/v1` 하나를 벗기고 `/v1/chat/completions`
      를 붙인다 — 벤더 문서가 `…/v1` 까지 인쇄하든 안 하든 같은 자리에 닿는다.
    """
    trimmed = raw.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed[: -len("/chat/completions")], "/chat/completions"
    if trimmed.endswith("/v1beta/openai"):
        return trimmed, "/chat/completions"
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed, "/v1/chat/completions"


def _build_provider() -> tuple[LLMProvider, list[HttpxJsonTransport], str]:
    """env → provider·transport 들. 키 폴백(오너 2026-08-22)의 조립 지점.

    - `LLAMA_API_KEYS`(쉼표 리스트, 1개여도 된다): 키마다 transport가 하나씩.
      없으면 인증 헤더 없음 — 로컬 llama.cpp 의 오늘 경로다.
    - `LLAMA_MODELS`(쉼표 리스트): `models[0]` 기본, 나머지 폴백. 없으면
      `LLAMA_DEFAULT_MODEL` 하나.
    - 키 ≤1 且 모델 ≤1이면 **래퍼 없이 오늘과 동일한 단일 provider** — 로컬 구성은
      창(窓) 계수기도 라운드로빈도 없는 대가 없는 세계에 그대로 둔다.
    """
    base_url, chat_path = _chat_endpoint(
        os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL)
    )
    # `llamacpp`(기본) — llama.cpp 전용 확장(chat_template_kwargs·/props·/tokenize)을
    # 쓴다. `openai` — OpenAI 호환 서버(구글 Gemini API 등). 모르는 필드를 400 으로
    # 거부하는 쪽이므로 확장을 뺀다(구글 실측 2026-08-22). **형식은 주소로 추론하지
    # 않는다** — 임베딩 축(EMBEDDING_API_FORMAT)과 같은 결: 추론하면 주소를 고치는
    # 순간 조용히 형식이 바뀌고 실패는 원인에서 먼 자리에서 나온다.
    wire_format = os.environ.get("LLAMA_API_FORMAT", "llamacpp").strip().lower()
    if wire_format not in ("llamacpp", "openai"):
        raise ValueError(
            "LLAMA_API_FORMAT must be 'llamacpp' or 'openai', "
            f"got {wire_format!r}"
        )
    llama_extras = wire_format == "llamacpp"
    timeout_seconds = _env_float("LLAMA_TIMEOUT_SECONDS", 120.0)
    trust_env = _env_bool("LLAMA_TRUST_ENV", False)
    default_model = os.environ.get("LLAMA_DEFAULT_MODEL", "gemma-local")
    default_thinking = _env_bool("LLAMA_DEFAULT_THINKING", False)
    provider_name = os.environ.get("LLAMA_PROVIDER_NAME", DEFAULT_PROVIDER_NAME)

    keys: list[str | None] = parse_env_list(os.environ.get("LLAMA_API_KEYS"))
    if not keys:
        keys = [None]
    models = parse_env_list(os.environ.get("LLAMA_MODELS")) or [default_model]
    rpm = _env_float("LLAMA_KEY_RPM", 30.0)
    if rpm < 1:
        # 빈 값은 compose 콜론 표기가 기본 30으로 메우지만, 명시적으로 0을 적은 것은
        # 설정 실수다 — 조용히 모든 키를 막는 것보다 기동에서 거부하는 것이 낫다.
        raise ValueError("LLAMA_KEY_RPM must be at least 1")

    def _transport_for(key: str | None) -> HttpxJsonTransport:
        return HttpxJsonTransport(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            trust_env=trust_env,
            headers={"Authorization": f"Bearer {key}"} if key else None,
        )

    if len(keys) <= 1 and len(models) <= 1:
        transport = _transport_for(keys[0])
        provider = LlamaCppProvider(
            transport=transport,
            default_model=models[0],
            default_thinking=default_thinking,
            provider_name=provider_name,
            chat_path=chat_path,
            llama_extras=llama_extras,
        )
        return provider, [transport], base_url

    transports = [_transport_for(key) for key in keys]
    provider = FallbackProvider(
        providers=[
            LlamaCppProvider(
                transport=transport,
                default_model=models[0],
                default_thinking=default_thinking,
                provider_name=provider_name,
                chat_path=chat_path,
                llama_extras=llama_extras,
            )
            for transport in transports
        ],
        models=models,
        limiter=SlidingWindowRateLimiter(
            slots=len(transports), limit=int(rpm)
        ),
        # 체인 전체가 시도당 타임아웃과 같은 예산을 공유 — N 조합이 지연을 배가하지 않는다.
        total_timeout_seconds=timeout_seconds,
    )
    return provider, transports, base_url


def _status_for_error(error: ProviderError) -> int:
    if error.code is ProviderErrorCode.TIMEOUT:
        return 504
    if error.code is ProviderErrorCode.OVERLOADED:
        return 429
    if error.code is ProviderErrorCode.UNAVAILABLE:
        return 503
    if error.code is ProviderErrorCode.REQUEST_REJECTED:
        return 400
    # 창 가드가 거부한 요청은 **요청 자체가 못 쓰는 요청**이므로 4xx다(K-3, 오너 2026-07-30).
    # 재시도가 같은 실패로 끝나는 점도 `REQUEST_REJECTED`와 같다 — 다른 것은 거부한 주체다.
    if error.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
        return 400
    # 키가 거부된 것(401/403)은 **우리 쪽 자격증명 실패**다. 게이트웨이의 클라이언트(앱)는
    # 게이트웨이에 자격증명이 없으므로 401을 돌려주면 "너의 인증을 고쳐라"라는 거짓 메시지가
    # 된다 — 실패한 자격증명은 게이트웨이→상류 방향이므로 502가 정직하다(오너 2026-08-22).
    if error.code is ProviderErrorCode.KEY_REJECTED:
        return 502
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
    owned_transports: list[HttpxJsonTransport] = []
    configured_base_url = llama_base_url

    if provider is None:
        provider, owned_transports, configured_base_url = _build_provider()
    elif configured_base_url is None:
        configured_base_url = os.environ.get(
            "LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            for transport in owned_transports:
                await transport.aclose()

    app = FastAPI(title="에-라잇 LLM Gateway", lifespan=lifespan)

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

    # R-a (오너 2026-07-31): 앱이 **창을 몰라서** report 예산을 상수로 박을 수밖에 없던 것을
    # 없앤다. 창과 토크나이저는 provider만 아는 사실이므로 게이트웨이가 답한다 — 앱이
    # `LLAMA_CTX_SIZE`를 자기 env로 복제하면 머신마다 두 값이 갈린다(이 프로젝트가 반복해
    # 데인 실패 방식). **모르면 `null`이고 앱은 그때 자기 추정으로 떨어진다.**
    @app.get("/v1/capabilities")
    async def capabilities() -> dict[str, object]:
        window = None
        probe = getattr(provider, "context_window", None)
        if callable(probe):
            window = await probe()
        return {"context_window": window}

    @app.post("/v1/tokenize")
    async def tokenize(payload: TokenizeRequest) -> dict[str, object]:
        counter = getattr(provider, "count_tokens", None)
        if not callable(counter):
            return {"tokens": None}
        return {"tokens": await counter(payload.text)}

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
