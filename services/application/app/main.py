"""FastAPI application shell for the Application service."""

from __future__ import annotations

import os
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.application.app.analysis.extractor import AnalysisExtractionError
from services.application.app.analysis.models import AnalysisJobStatus
from services.application.app.analysis.repository import DuplicateAnalysisCandidateRequest
from services.application.app.analysis.runner import AnalysisExtractionRunResult
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
    InvalidCandidateSource,
)
from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
)


class AnalysisJobRunner(Protocol):
    async def run_job(
        self,
        *,
        project_id: str,
        job_id: str,
    ) -> AnalysisExtractionRunResult:
        ...


def _default_core_sot_service() -> CoreSotService:
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


def _default_analysis_service() -> AnalysisService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return AnalysisService(InMemoryAnalysisRepository())

    # Imported lazily so the in-memory path needs no pymongo install.
    from services.application.app.analysis.mongo_repository import (
        MongoAnalysisRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

    use_transactions = os.environ.get(
        "CORE_SOT_MONGO_TRANSACTIONS", "true"
    ).lower() not in {"0", "false", "no"}
    repository = MongoAnalysisRepository.from_uri(
        uri,
        db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
        use_transactions=use_transactions,
    )
    return AnalysisService(repository)


class CreateProjectRequest(BaseModel):
    name: str


class CreateAnalysisJobRequest(BaseModel):
    snapshot_id: str
    idempotency_key: str


class CreateDraftRequest(BaseModel):
    title: str


class RenameProjectRequest(BaseModel):
    name: str


class RenameDraftRequest(BaseModel):
    title: str


class SaveDraftRequest(BaseModel):
    raw_text: str
    idempotency_key: str


def create_app(
    service: CoreSotService | None = None,
    analysis_service: AnalysisService | None = None,
    analysis_runner: AnalysisJobRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Writing System Application")
    core_sot = service or _default_core_sot_service()
    analysis = analysis_service or _default_analysis_service()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def _project_payload(project) -> dict[str, object]:
        return {"id": project.id, "name": project.name, "archived": project.archived}

    def _draft_payload(draft) -> dict[str, object]:
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "title": draft.title,
            "archived": draft.archived,
        }

    def _version_meta_payload(version) -> dict[str, object]:
        # idempotency_key is intentionally omitted: it is an internal save token,
        # not part of the public read surface.
        return {
            "id": version.id,
            "project_id": version.project_id,
            "draft_id": version.draft_id,
            "version_number": version.version_number,
            "snapshot_id": version.snapshot_id,
        }

    def _analysis_job_payload(job) -> dict[str, object]:
        return {
            "id": job.id,
            "project_id": job.project_id,
            "snapshot_id": job.snapshot_id,
            "status": str(job.status),
            "failure_reason": (
                str(job.failure_reason) if job.failure_reason is not None else None
            ),
            "failure_detail": job.failure_detail,
        }

    def _analysis_candidate_payload(candidate) -> dict[str, object]:
        return {
            "id": candidate.id,
            "project_id": candidate.project_id,
            "job_id": candidate.job_id,
            "task_id": candidate.task_id,
            "candidate_type": str(candidate.candidate_type),
            "action": str(candidate.action),
            "status": str(candidate.status),
            "provenance": str(candidate.provenance),
            "confidence": candidate.confidence,
            "source_ref_ids": list(candidate.source_ref_ids),
            "payload": dict(candidate.payload),
        }

    def _analysis_run_payload(
        result: AnalysisExtractionRunResult,
    ) -> dict[str, object]:
        return {
            "job": _analysis_job_payload(result.job),
            "candidates": [
                _analysis_candidate_payload(candidate)
                for candidate in result.candidates
            ],
            "idempotent_replay": result.job_idempotent_replay,
        }

    def _require_project_exists(project_id: str) -> None:
        core_sot.get_project(project_id=project_id)

    @app.post("/projects")
    async def create_project(request: CreateProjectRequest) -> dict[str, object]:
        project = core_sot.create_project(name=request.name)
        return _project_payload(project)

    @app.get("/projects")
    async def list_projects() -> dict[str, object]:
        return {"projects": [_project_payload(p) for p in core_sot.list_projects()]}

    @app.get("/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, object]:
        try:
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _project_payload(project)

    @app.patch("/projects/{project_id}")
    async def rename_project(
        project_id: str, request: RenameProjectRequest
    ) -> dict[str, object]:
        try:
            project = core_sot.rename_project(
                project_id=project_id, name=request.name
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _project_payload(project)

    @app.patch("/projects/{project_id}/drafts/{draft_id}")
    async def rename_draft(
        project_id: str, draft_id: str, request: RenameDraftRequest
    ) -> dict[str, object]:
        try:
            draft = core_sot.rename_draft(
                project_id=project_id, draft_id=draft_id, title=request.title
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.delete("/projects/{project_id}")
    async def archive_project(project_id: str) -> dict[str, object]:
        # MVP: delete is archive (soft delete); SOT data is preserved (§115).
        # Re-archiving is idempotent.
        try:
            project = core_sot.archive_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _project_payload(project)

    @app.delete("/projects/{project_id}/drafts/{draft_id}")
    async def archive_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.archive_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.get("/projects/{project_id}/drafts")
    async def list_drafts(project_id: str) -> dict[str, object]:
        try:
            drafts = core_sot.list_drafts(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"drafts": [_draft_payload(d) for d in drafts]}

    @app.get("/projects/{project_id}/drafts/{draft_id}")
    async def get_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.get_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.get("/projects/{project_id}/drafts/{draft_id}/versions")
    async def list_draft_versions(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            versions = core_sot.list_draft_versions(
                project_id=project_id, draft_id=draft_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"versions": [_version_meta_payload(v) for v in versions]}

    @app.get("/projects/{project_id}/drafts/{draft_id}/versions/{version_id}")
    async def get_draft_version(
        project_id: str, draft_id: str, version_id: str
    ) -> dict[str, object]:
        try:
            detail = core_sot.get_draft_version(
                project_id=project_id, draft_id=draft_id, version_id=version_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "draft_version": _version_meta_payload(detail.draft_version),
            "snapshot": {
                "id": detail.snapshot.id,
                "project_id": detail.snapshot.project_id,
                "draft_id": detail.snapshot.draft_id,
                "version_id": detail.snapshot.version_id,
                "raw_text": detail.snapshot.raw_text,
                "content_hash": detail.snapshot.content_hash,
            },
            "blocks": [
                {
                    "id": block.id,
                    "project_id": block.project_id,
                    "snapshot_id": block.snapshot_id,
                    "block_index": block.block_index,
                    "kind": block.kind,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                    "text": block.text,
                }
                for block in detail.blocks
            ],
        }

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
        return _draft_payload(draft)

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

    @app.post("/projects/{project_id}/analysis/jobs")
    async def create_analysis_job(
        project_id: str, request: CreateAnalysisJobRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            result = analysis.create_job(
                project_id=project_id,
                snapshot_id=request.snapshot_id,
                idempotency_key=request.idempotency_key,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "job": _analysis_job_payload(result.job),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}")
    async def get_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _analysis_job_payload(job)

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}/candidates")
    async def list_analysis_candidates(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidates = analysis.list_candidates(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "candidates": [
                _analysis_candidate_payload(candidate) for candidate in candidates
            ]
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/run")
    async def run_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            if job.status is not AnalysisJobStatus.PENDING:
                candidates = analysis.list_candidates(
                    project_id=project_id, job_id=job_id
                )
                return _analysis_run_payload(
                    AnalysisExtractionRunResult(
                        job=job,
                        candidates=candidates,
                        job_idempotent_replay=True,
                        candidate_idempotent_replays=tuple(True for _ in candidates),
                    )
                )
            if analysis_runner is None:
                raise HTTPException(
                    status_code=503,
                    detail="analysis runner is not configured",
                )
            result = await analysis_runner.run_job(
                project_id=project_id,
                job_id=job_id,
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateAnalysisCandidateRequest as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (
            AnalysisExtractionError,
            InvalidCandidateSource,
            InvalidAnalysisCandidate,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _analysis_run_payload(result)

    return app


app = create_app()
