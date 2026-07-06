"""FastAPI embedding service (Phase 4 real vector backend, B.2).

Exposes POST /embed producing the exact wire contract the Application-side
`RemoteEmbeddingProvider` (B.1) consumes: {"text": str} -> {"embedding":
[float, ...], "dimensions": int}. The real model (dragonkue/BGE-m3-ko, a
1024-dim sentence-transformers bi-encoder) is loaded from env at startup; tests
inject a stub model so the app is exercised without the model or torch.
See docs/plans/04-real-vector-backend-decisions.md (B.2).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class EmbeddingModel(Protocol):
    def embed(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddingModel:
    """Real model backend. sentence-transformers/torch are imported lazily so
    unit tests (which inject a stub) never require the heavy dependency."""

    def __init__(self, model_name: str, *, normalize: bool = True) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._normalize = normalize

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=self._normalize)
        return [float(value) for value in vector]


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1)


def build_embed_response(model: EmbeddingModel, text: str) -> dict[str, object]:
    """Single source of truth for the /embed response shape, shared by the
    route and the B.1<->B.2 round-trip regression so producer and consumer of
    the wire contract cannot drift."""
    vector = model.embed(text)
    return {"embedding": vector, "dimensions": len(vector)}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no"}


def _build_model_from_env() -> EmbeddingModel:
    model_name = os.environ.get("EMBEDDING_MODEL_NAME", "dragonkue/BGE-m3-ko")
    return SentenceTransformerEmbeddingModel(
        model_name,
        normalize=_env_bool("EMBEDDING_NORMALIZE", True),
    )


def create_app(model: EmbeddingModel | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # In the container the real model is loaded once at startup; an injected
        # model (tests) is left as-is.
        if app.state.model is None:
            app.state.model = _build_model_from_env()
        yield

    app = FastAPI(title="AI Writing System Embedding Service", lifespan=lifespan)
    app.state.model = model

    @app.get("/health")
    @app.get("/health/live")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        if app.state.model is None:
            raise HTTPException(status_code=503, detail="model is not loaded")
        return {"status": "ok"}

    @app.post("/embed")
    async def embed(request: EmbedRequest) -> dict[str, object]:
        model = app.state.model
        if model is None:
            raise HTTPException(status_code=503, detail="model is not loaded")
        return build_embed_response(model, request.text)

    return app


app = create_app()
