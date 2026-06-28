"""FastAPI application shell for the Application service."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
)


def _default_service() -> CoreSotService:
    """Build the service from environment configuration.

    Uses MongoDB when ``CORE_SOT_MONGO_URI`` is set (transaction-backed by
    default, the approved Docker runtime), otherwise the in-memory skeleton for
    local/test runs without infrastructure.
    """

    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return CoreSotService(InMemoryCoreSotRepository())

    # Imported lazily so the in-memory path needs no pymongo install.
    from services.application.app.core_sot.mongo_repository import (
        DEFAULT_DB_NAME,
        MongoCoreSotRepository,
    )

    use_transactions = os.environ.get(
        "CORE_SOT_MONGO_TRANSACTIONS", "true"
    ).lower() not in {"0", "false", "no"}
    repository = MongoCoreSotRepository.from_uri(
        uri,
        db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
        use_transactions=use_transactions,
    )
    return CoreSotService(repository)


class CreateProjectRequest(BaseModel):
    name: str


class CreateDraftRequest(BaseModel):
    title: str


class SaveDraftRequest(BaseModel):
    raw_text: str
    idempotency_key: str


def create_app(service: CoreSotService | None = None) -> FastAPI:
    app = FastAPI(title="AI Writing System Application")
    core_sot = service or _default_service()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/projects")
    async def create_project(request: CreateProjectRequest) -> dict[str, object]:
        project = core_sot.create_project(name=request.name)
        return {"id": project.id, "name": project.name, "archived": project.archived}

    @app.post("/projects/{project_id}/drafts")
    async def create_draft(
        project_id: str, request: CreateDraftRequest
    ) -> dict[str, object]:
        try:
            draft = core_sot.create_draft(project_id=project_id, title=request.title)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "title": draft.title,
            "archived": draft.archived,
        }

    @app.post("/projects/{project_id}/drafts/{draft_id}/versions")
    async def save_draft(
        project_id: str, draft_id: str, request: SaveDraftRequest
    ) -> dict[str, object]:
        try:
            result = core_sot.save_draft(
                project_id=project_id,
                draft_id=draft_id,
                raw_text=request.raw_text,
                idempotency_key=request.idempotency_key,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CoreSotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "draft_version": {
                "id": result.draft_version.id,
                "version_number": result.draft_version.version_number,
                "snapshot_id": result.draft_version.snapshot_id,
            },
            "snapshot": {
                "id": result.snapshot.id,
                "content_hash": result.snapshot.content_hash,
            },
            "blocks": [
                {
                    "id": block.id,
                    "kind": block.kind,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                }
                for block in result.blocks
            ],
            "idempotent_replay": result.idempotent_replay,
        }

    return app


app = create_app()
