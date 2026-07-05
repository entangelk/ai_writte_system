"""FastAPI application shell for the Application service."""

from __future__ import annotations

import os
from typing import Protocol

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from services.application.app.analysis.extractor import (
    AnalysisExtractionError,
    VersionedPromptAnalysisExtractionAdapter,
)
from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.application.app.analysis.models import AnalysisJobStatus
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.repository import DuplicateAnalysisCandidateRequest
from services.application.app.analysis.runner import (
    AnalysisExtractionRunner,
    AnalysisExtractionRunResult,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidAnalysisCandidate,
    InvalidCandidateSource,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.application.app.context_search.models import (
    ContextNeed,
    ContextSearchPurpose,
    ContextSearchRequest,
    ContextBudget,
    CurrentPosition,
)
from services.application.app.context_search.planner import (
    TerminalJsonSearchPlanner,
    seed_context_search_plan_template,
)
from services.application.app.context_search.service import (
    ContextSearchBudgetExceeded,
    ContextSearchFailed,
    ContextSearchService,
    InvalidContextSearchRequest,
    evaluate_context_gate,
)
from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    CoreSotService,
    InMemoryCoreSotRepository,
    NotFound,
    UnsupportedExportFormat,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    FAKE_VECTOR_BACKEND,
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
    rebuild_source_block_index_summary,
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


def _default_analysis_service(core_sot: CoreSotService) -> AnalysisService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return AnalysisService(
            InMemoryAnalysisRepository(),
            source_ref_resolver=CoreSotSourceAdapter(core_sot),
        )

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
    return AnalysisService(
        repository,
        source_ref_resolver=CoreSotSourceAdapter(core_sot),
    )


def _default_prompt_template_service() -> PromptTemplateService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v1()
        return service

    from services.application.app.analysis.prompt_template_mongo_repository import (
        MongoPromptTemplateRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

    repository = MongoPromptTemplateRepository.from_uri(
        uri,
        db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
    )
    service = PromptTemplateService(repository)
    service.seed_analysis_extract_v1()
    return service


def _default_index_sync_outbox_service() -> IndexSyncOutboxService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return IndexSyncOutboxService(InMemoryIndexSyncRepository())

    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.indexing.mongo_repository import (
        MongoIndexSyncRepository,
    )

    repository = MongoIndexSyncRepository.from_uri(
        uri,
        db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
    )
    return IndexSyncOutboxService(repository)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no"}


def _default_analysis_runner(
    *,
    core_sot: CoreSotService,
    analysis: AnalysisService,
) -> AnalysisExtractionRunner | None:
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    prompt_templates = _default_prompt_template_service()
    provider = GatewayGenerateProvider(
        base_url=base_url,
        timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
        trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
    )
    return AnalysisExtractionRunner(
        analysis_service=analysis,
        snapshot_loader=CoreSotSourceAdapter(core_sot),
        extractor=VersionedPromptAnalysisExtractionAdapter(
            provider,
            prompt_templates=prompt_templates,
            source_ref_catalog=core_sot,
            model=os.environ.get("LLM_GATEWAY_MODEL") or None,
            max_tokens=int(os.environ.get("ANALYSIS_EXTRACT_MAX_TOKENS", "2048")),
        ),
    )


def _default_context_search_service(
    core_sot: CoreSotService,
    *,
    vector_index: InMemoryVectorIndexAdapter,
    embeddings: DeterministicFakeEmbeddingProvider,
) -> ContextSearchService | None:
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_context_search_plan_template(prompt_templates)
    provider = GatewayGenerateProvider(
        base_url=base_url,
        timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
        trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
    )
    planner = TerminalJsonSearchPlanner(
        provider,
        prompt_templates=prompt_templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("CONTEXT_SEARCH_PLAN_MAX_TOKENS", "1024")),
    )
    # The vector adapter is the process-shared in-process fake (real Chroma is a
    # later slice). It is the same instance the rebuild endpoint writes into, so
    # a rebuild followed by a context search in the same process yields real
    # vector hits; the index is non-durable and lost on restart. Mongo-direct
    # needs (current/recent scenes) serve from the Core SOT.
    # See docs/plans/04-shared-vector-index-decisions.md.
    indexing = SourceBlockIndexingService(
        core_sot=core_sot,
        embeddings=embeddings,
        vector_index=vector_index,
    )
    return ContextSearchService(
        core_sot=core_sot,
        indexing_service=indexing,
        vector_search=vector_index,
        embeddings=embeddings,
        planner=planner,
    )


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


class CreateSourceRefRequest(BaseModel):
    start_offset: int
    end_offset: int


class ContextPositionBody(BaseModel):
    draft_id: str
    version_id: str


class ContextSearchHttpRequest(BaseModel):
    query: str
    needs: list[str]
    purpose: str = ContextSearchPurpose.WRITING_CONTEXT.value
    current_position: ContextPositionBody | None = None
    max_tokens: int = 4096


def create_app(
    service: CoreSotService | None = None,
    analysis_service: AnalysisService | None = None,
    analysis_runner: AnalysisJobRunner | None = None,
    index_sync_outbox: IndexSyncOutboxService | None = None,
    context_search_service: ContextSearchService | None = None,
    vector_index: InMemoryVectorIndexAdapter | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Writing System Application")
    core_sot = service or _default_core_sot_service()
    analysis = analysis_service or _default_analysis_service(core_sot)
    sync_outbox = index_sync_outbox or _default_index_sync_outbox_service()
    runner = analysis_runner
    if runner is None:
        runner = _default_analysis_runner(core_sot=core_sot, analysis=analysis)
    # A single process-shared in-process vector index is owned here so the
    # rebuild endpoint writes into the same instance the default context search
    # reads from. It is created regardless of the planner env (rebuild works
    # without LLM_GATEWAY_BASE_URL); it is non-durable and lost on restart.
    # See docs/plans/04-shared-vector-index-decisions.md.
    shared_vector_index = vector_index if vector_index is not None else InMemoryVectorIndexAdapter()
    shared_embeddings = DeterministicFakeEmbeddingProvider()
    context_search = context_search_service
    if context_search is None:
        context_search = _default_context_search_service(
            core_sot,
            vector_index=shared_vector_index,
            embeddings=shared_embeddings,
        )

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

    def _source_ref_payload(source_ref) -> dict[str, object]:
        return {
            "id": source_ref.id,
            "project_id": source_ref.project_id,
            "snapshot_id": source_ref.snapshot_id,
            "block_id": source_ref.block_id,
            "start_offset": source_ref.start_offset,
            "end_offset": source_ref.end_offset,
            "quote": source_ref.quote,
            "content_hash": source_ref.content_hash,
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

    def _rebuild_source_block_index_payload(
        *, project_id: str, snapshot_id: str
    ) -> dict[str, object]:
        summary = rebuild_source_block_index_summary(
            core_sot=core_sot,
            project_id=project_id,
            snapshot_id=snapshot_id,
            vector_index=shared_vector_index,
            embeddings=shared_embeddings,
        )
        return summary.to_dict(backend=FAKE_VECTOR_BACKEND)

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
        sync_outbox.enqueue_project_archived(project_id=project_id)
        return _project_payload(project)

    @app.delete("/projects/{project_id}/drafts/{draft_id}")
    async def archive_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.archive_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        sync_outbox.enqueue_draft_archived(
            project_id=project_id,
            draft_id=draft_id,
        )
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

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export"
    )
    async def export_draft_version(
        project_id: str,
        draft_id: str,
        version_id: str,
        format: str = Query("txt"),
    ) -> dict[str, object]:
        try:
            export = core_sot.export_draft_version(
                project_id=project_id,
                draft_id=draft_id,
                version_id=version_id,
                fmt=format,
            )
        except UnsupportedExportFormat as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "format": export.format,
            "filename": export.filename,
            "content_type": export.content_type,
            "body": export.body,
            "project_id": export.project_id,
            "draft_id": export.draft_id,
            "version_id": export.version_id,
            "version_number": export.version_number,
            "snapshot_id": export.snapshot_id,
            "content_hash": export.content_hash,
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

    @app.post("/projects/{project_id}/snapshots/{snapshot_id}/source-refs")
    async def create_source_ref(
        project_id: str,
        snapshot_id: str,
        request: CreateSourceRefRequest,
    ) -> dict[str, object]:
        try:
            source_ref = core_sot.create_source_ref(
                project_id=project_id,
                snapshot_id=snapshot_id,
                start_offset=request.start_offset,
                end_offset=request.end_offset,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CoreSotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _source_ref_payload(source_ref)

    @app.get("/projects/{project_id}/snapshots/{snapshot_id}/source-refs")
    async def list_source_refs(
        project_id: str,
        snapshot_id: str,
    ) -> dict[str, object]:
        try:
            source_refs = core_sot.list_source_refs(
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"source_refs": [_source_ref_payload(ref) for ref in source_refs]}

    @app.get("/projects/{project_id}/source-refs/{source_ref_id}")
    async def get_source_ref(
        project_id: str,
        source_ref_id: str,
    ) -> dict[str, object]:
        try:
            source_ref = core_sot.get_source_ref(
                project_id=project_id,
                source_ref_id=source_ref_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _source_ref_payload(source_ref)

    @app.post("/projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild")
    async def rebuild_source_block_index(
        project_id: str,
        snapshot_id: str,
    ) -> dict[str, object]:
        try:
            return _rebuild_source_block_index_payload(
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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
            if runner is None:
                raise HTTPException(
                    status_code=503,
                    detail="analysis runner is not configured",
                )
            result = await runner.run_job(
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

    def _context_item_payload(item) -> dict[str, object]:
        return {
            "need": item.need.value,
            "status": item.status.value,
            "text": item.text,
            "pointer": {
                "project_id": item.pointer.project_id,
                "collection": item.pointer.collection,
                "document_id": item.pointer.document_id,
                "version_id": item.pointer.version_id,
                "content_hash": item.pointer.content_hash,
            },
            "snapshot_id": item.snapshot_id,
            "sot_reloaded": item.sot_reloaded,
            "token_estimate": item.token_estimate,
            "source_ref_ids": list(item.source_ref_ids),
        }

    def _context_trace_payload(trace) -> dict[str, object]:
        return {
            "plan": {
                "plan_id": trace.plan.plan_id,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "need": step.need.value,
                        "tools": [tool.value for tool in step.tools],
                        "query": step.query,
                    }
                    for step in trace.plan.steps
                ],
            },
            "steps": [
                {
                    "step_id": step.step_id,
                    "need": step.need.value,
                    "tool": step.tool.value,
                    "hits_considered": step.hits_considered,
                    "items_produced": step.items_produced,
                    "excluded": [
                        {"record_id": hit.record_id, "reason": hit.reason}
                        for hit in step.excluded
                    ],
                    "failure": (
                        None
                        if step.failure is None
                        else {
                            "error_type": step.failure.error_type.value,
                            "detail": step.failure.detail,
                        }
                    ),
                }
                for step in trace.steps
            ],
            "budget_excluded": [
                {"record_id": hit.record_id, "reason": hit.reason}
                for hit in trace.budget_excluded
            ],
        }

    def _context_package_payload(package, gate) -> dict[str, object]:
        return {
            "package": {
                "project_id": package.project_id,
                "purpose": package.purpose.value,
                "status": package.status,
                "degraded": package.degraded,
                "token_estimate_total": package.token_estimate_total,
                "macro_items": [
                    _context_item_payload(item) for item in package.macro_items
                ],
                "micro_evidence": [
                    _context_item_payload(item) for item in package.micro_evidence
                ],
                "constraints": list(package.constraints),
                "do_not_use": list(package.do_not_use),
                "trace": _context_trace_payload(package.trace),
            },
            "gate": {
                "decision": gate.decision,
                "findings": [
                    {"check": finding.check, "detail": finding.detail}
                    for finding in gate.findings
                ],
            },
        }

    @app.post("/projects/{project_id}/context-search")
    async def context_search_endpoint(
        project_id: str, body: ContextSearchHttpRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            request = _build_context_search_request(project_id, body)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if context_search is None:
            raise HTTPException(
                status_code=503,
                detail="context search service is not configured",
            )
        try:
            package = await context_search.build_context_package(request)
            gate = evaluate_context_gate(
                package=package, request=request, core_sot=core_sot
            )
        except InvalidContextSearchRequest as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ContextSearchBudgetExceeded as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except ContextSearchFailed as exc:
            raise HTTPException(
                status_code=502,
                detail=f"{exc.error_type.value}: {exc.detail}",
            ) from exc
        return _context_package_payload(package, gate)

    return app


def _build_context_search_request(
    project_id: str, body: ContextSearchHttpRequest
) -> ContextSearchRequest:
    try:
        purpose = ContextSearchPurpose(body.purpose)
    except ValueError as exc:
        raise ValueError(f"unsupported purpose: {body.purpose}") from exc
    needs: list[ContextNeed] = []
    for raw_need in body.needs:
        try:
            needs.append(ContextNeed(raw_need))
        except ValueError as exc:
            raise ValueError(f"unsupported need: {raw_need}") from exc
    position = (
        CurrentPosition(
            draft_id=body.current_position.draft_id,
            version_id=body.current_position.version_id,
        )
        if body.current_position is not None
        else None
    )
    return ContextSearchRequest(
        project_id=project_id,
        purpose=purpose,
        needs=tuple(needs),
        query=body.query,
        current_position=position,
        context_budget=ContextBudget(max_tokens=body.max_tokens),
    )


app = create_app()
