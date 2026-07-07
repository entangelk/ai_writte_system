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
from services.application.app.analysis.models import (
    AnalysisCandidateStatus,
    AnalysisJobStatus,
)
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
from services.application.app.analysis.apply import (
    MemoryApplyError,
    MemoryApplyService,
    MissingMatchedMemory,
)
from services.application.app.analysis.compare import (
    ActionProposal,
    AnalysisCompareService,
    CompareAction,
    CompareJudgeNotConfigured,
    InvalidJudgeResult,
)
from services.application.app.analysis.compare_judge import (
    TerminalJsonCompareJudge,
    seed_analysis_compare_template,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.llm_gateway.app.errors import ProviderError
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryError,
    MemoryNotFound,
    MemoryReindexOutbox,
    MemoryService,
)
from services.application.app.context_search.models import (
    AnalysisContextRequest,
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
from services.application.app.context_search.prior_memory import (
    AnalysisContextService,
    DeterministicPriorMemoryBackend,
    evaluate_analysis_context_gate,
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
    CHROMA_VECTOR_BACKEND,
    DeterministicFakeEmbeddingProvider,
    EmbeddingProvider,
    FAKE_VECTOR_BACKEND,
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
    InMemoryVectorIndexAdapter,
    SourceBlockIndexingService,
    rebuild_source_block_index_summary,
)
from services.application.app.indexing.chroma import (
    DEFAULT_COLLECTION_NAME,
    ChromaVectorIndexAdapter,
    connect_chroma_collection,
)
from services.application.app.indexing.embedding import RemoteEmbeddingProvider


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


def _default_memory_service(
    reindex_outbox: MemoryReindexOutbox | None = None,
) -> MemoryService:
    # Conservative default: auto-promotion is off unless a threshold is set,
    # so no canonical memory is minted from a guessed value (SoT v1.6.39 D2=B).
    threshold_raw = os.environ.get("MEMORY_AUTO_PROMOTION_THRESHOLD")
    auto_threshold = float(threshold_raw) if threshold_raw else None

    # Phase 2B.5 (D3=B): every canonical mint (promote/auto-promote/apply
    # versioned upsert) enqueues a reindex through the service, so the index-sync
    # worker keeps the memory_vectors collection current.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return MemoryService(
            InMemoryMemoryRepository(),
            auto_promotion_threshold=auto_threshold,
            reindex_outbox=reindex_outbox,
        )

    # Imported lazily so the in-memory path needs no pymongo install.
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    from services.application.app.memory.mongo_repository import (
        MongoMemoryRepository,
    )

    repository = MongoMemoryRepository.from_uri(
        uri,
        db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
    )
    return MemoryService(
        repository,
        auto_promotion_threshold=auto_threshold,
        reindex_outbox=reindex_outbox,
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


def _default_compare_service(memory: MemoryService) -> AnalysisCompareService:
    # Phase 2B.3.2: wire the real terminal-JSON compare judge when a Gateway is
    # configured; otherwise no judge (matched pairs → 503, deterministic
    # no-match/duplicate proposals still serve). Mirrors the analysis runner /
    # context search planner env gating.
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return AnalysisCompareService(memory_service=memory)
    prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_analysis_compare_template(prompt_templates)
    provider = GatewayGenerateProvider(
        base_url=base_url,
        timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
        trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
    )
    judge = TerminalJsonCompareJudge(
        provider,
        prompt_templates=prompt_templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("ANALYSIS_COMPARE_MAX_TOKENS", "512")),
    )
    return AnalysisCompareService(memory_service=memory, judge=judge)


def _default_context_search_service(
    core_sot: CoreSotService,
    *,
    vector_index: InMemoryVectorIndexAdapter | ChromaVectorIndexAdapter,
    embeddings: EmbeddingProvider,
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
    # The vector adapter and embeddings are the process-shared instances the
    # rebuild endpoint also writes into, so a rebuild followed by a context
    # search yields real vector hits. Depending on env (B.4) these are either the
    # persistent Chroma backend with real embeddings or the in-memory fake with
    # deterministic fake embeddings. Mongo-direct needs (current/recent scenes)
    # serve from the Core SOT. See docs/plans/04-shared-vector-index-decisions.md
    # and docs/plans/04-real-vector-backend-decisions.md.
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


def _build_embedding_provider():
    # Real embedding service (B.2) when configured, else the deterministic fake.
    # expected_dimensions activates the B.1 dimension guard in deployment so a
    # misconfigured model dimension fails fast (B.2 verification follow-up).
    base_url = os.environ.get("EMBEDDING_SERVICE_URL")
    if not base_url:
        return DeterministicFakeEmbeddingProvider()
    return RemoteEmbeddingProvider(
        base_url=base_url,
        timeout_seconds=_env_float("EMBEDDING_TIMEOUT_SECONDS", 30.0),
        trust_env=_env_bool("EMBEDDING_TRUST_ENV", False),
        expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
    )


def _build_chroma_vector_index():
    # Real persistent Chroma (B.3) when CHROMA_HOST is set, else None so the
    # caller falls back to the in-memory fake. chromadb is imported lazily inside
    # connect_chroma_collection, so unconfigured environments/tests never need it.
    host = os.environ.get("CHROMA_HOST")
    if not host:
        return None
    return ChromaVectorIndexAdapter(
        connect_chroma_collection(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            collection_name=os.environ.get(
                "CHROMA_COLLECTION", DEFAULT_COLLECTION_NAME
            ),
        )
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


class ApplyProposalBody(BaseModel):
    candidate_id: str
    action: str
    matched_memory_id: str | None = None


class ApplyMemoryRequest(BaseModel):
    proposals: list[ApplyProposalBody]


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
    memory_service: MemoryService | None = None,
    index_sync_outbox: IndexSyncOutboxService | None = None,
    context_search_service: ContextSearchService | None = None,
    compare_service: AnalysisCompareService | None = None,
    vector_index: InMemoryVectorIndexAdapter | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Writing System Application")
    core_sot = service or _default_core_sot_service()
    analysis = analysis_service or _default_analysis_service(core_sot)
    sync_outbox = index_sync_outbox or _default_index_sync_outbox_service()
    # Phase 2B.5 (D3=B): the default memory service enqueues a MEMORY_UPSERTED
    # reindex on every canonical mint (manual promote / auto-promote / apply
    # versioned upsert) through the shared index-sync outbox; the index-sync
    # worker drains it into the memory_vectors collection. An injected
    # memory_service (tests) keeps its own wiring.
    memory = memory_service or _default_memory_service(reindex_outbox=sync_outbox)
    # Phase 2B.2: prior-memory search/packaging over the canonical memory store.
    # Deterministic backend now; a semantic backend plugs into the same seam
    # (docs/plans/02b-2-analysis-context-package-decisions.md, D2=A).
    analysis_context = AnalysisContextService(
        backend=DeterministicPriorMemoryBackend(memory)
    )
    # Phase 2B.3: candidate↔canonical compare. The real terminal-JSON Gateway
    # judge is a follow-up increment (2B.3.2); until injected, matched pairs
    # return 503 while no-match (create) and duplicate-canonical (conflict)
    # proposals are served deterministically.
    compare = compare_service or _default_compare_service(memory)
    # Phase 2B.4: apply safe compare actions to the canonical store. Deterministic
    # writes only (no LLM); reindex enqueue is owned by MemoryService (2B.5 D3=B
    # choke point), so apply needs no index hook
    # (docs/plans/02b-4-memory-versioned-upsert-decisions.md, D1=A).
    apply_service = MemoryApplyService(memory_service=memory)
    runner = analysis_runner
    if runner is None:
        runner = _default_analysis_runner(core_sot=core_sot, analysis=analysis)
    # A single shared vector index is owned here so the rebuild endpoint writes
    # into the same instance the default context search reads from. It is created
    # regardless of the planner env (rebuild works without LLM_GATEWAY_BASE_URL).
    # When CHROMA_HOST is set it is the real persistent Chroma backend (B.4),
    # else the in-memory fake (non-durable, lost on restart). An injected
    # vector_index (tests) always uses the fake in-memory backend label.
    # See docs/plans/04-shared-vector-index-decisions.md and
    # docs/plans/04-real-vector-backend-decisions.md.
    if vector_index is not None:
        shared_vector_index = vector_index
        shared_embeddings = DeterministicFakeEmbeddingProvider()
        shared_backend = FAKE_VECTOR_BACKEND
    else:
        shared_embeddings = _build_embedding_provider()
        chroma_index = _build_chroma_vector_index()
        if chroma_index is not None:
            shared_vector_index = chroma_index
            shared_backend = CHROMA_VECTOR_BACKEND
        else:
            shared_vector_index = InMemoryVectorIndexAdapter()
            shared_backend = FAKE_VECTOR_BACKEND
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

    def _memory_payload(entry) -> dict[str, object]:
        return {
            "id": entry.id,
            "project_id": entry.project_id,
            "memory_type": str(entry.memory_type),
            "status": str(entry.status),
            "provenance": str(entry.provenance),
            "confidence": entry.confidence,
            "source_ref_ids": list(entry.source_ref_ids),
            "payload": dict(entry.payload),
            "version": entry.version,
            "analysis_job_id": entry.analysis_job_id,
            "source_candidate_id": entry.source_candidate_id,
            "promotion_mode": str(entry.promotion_mode),
            "applied_threshold": entry.applied_threshold,
            "scope": _scope_payload(entry.scope),
            "supersedes": entry.supersedes,
        }

    def _scope_payload(scope) -> dict[str, object] | None:
        if scope is None:
            return None
        return {"scope_type": scope.scope_type, "scope_id": scope.scope_id}

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
        return summary.to_dict(backend=shared_backend)

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

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/promote"
    )
    async def promote_candidate(
        project_id: str, candidate_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidate = analysis.get_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
            result = memory.promote_candidate(
                project_id=project_id,
                candidate=candidate,
                mode=PromotionMode.MANUAL,
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "memory": _memory_payload(result.memory),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/auto-promote")
    async def auto_promote_job(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # ``promoted`` reports only memories newly created by this call. A
        # candidate already promoted (a re-run of the gate) replays idempotently
        # and is excluded, so the count stays consistent with the idempotency
        # semantics instead of growing on every re-call.
        promoted = []
        for candidate in candidates:
            if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
                continue
            result = memory.auto_promote_candidate(
                project_id=project_id, candidate=candidate
            )
            if result is not None and not result.idempotent_replay:
                promoted.append(_memory_payload(result.memory))
        return {
            "auto_promotion_threshold": memory.auto_promotion_threshold,
            "promoted": promoted,
        }

    @app.get("/projects/{project_id}/memory")
    async def list_memory(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "memory": [
                _memory_payload(entry)
                for entry in memory.list_memories(project_id=project_id)
            ]
        }

    @app.get("/projects/{project_id}/memory/{memory_id}")
    async def get_memory(project_id: str, memory_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            entry = memory.get_memory(project_id=project_id, memory_id=memory_id)
        except (MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _memory_payload(entry)

    def _prior_memory_item_payload(item) -> dict[str, object]:
        return {
            "memory_id": item.memory_id,
            "memory_type": item.memory_type.value,
            "value": dict(item.value),
            "status": item.status.value,
            "version": item.version,
            "source_ref_ids": list(item.source_ref_ids),
            "match_reason": item.match_reason,
            "scope": _scope_payload(item.scope),
        }

    def _analysis_context_payload(package, gate) -> dict[str, object]:
        return {
            "package": {
                "project_id": package.project_id,
                "purpose": package.purpose.value,
                "status": package.status,
                "degraded": package.degraded,
                "token_estimate_total": package.token_estimate_total,
                "prior_memories": [
                    _prior_memory_item_payload(item)
                    for item in package.prior_memories
                ],
            },
            "gate": {
                "decision": gate.decision,
                "findings": [
                    {"check": finding.check, "detail": finding.detail}
                    for finding in gate.findings
                ],
            },
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/context")
    async def analysis_context_endpoint(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        # Job-aware entry surface (D4=B): derive the coarse candidate group
        # (the memory_types this job produced) and search prior canonical
        # memories of those types, excluding this job's own memories (F4).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        memory_types = tuple(
            dict.fromkeys(candidate.candidate_type for candidate in candidates)
        )
        # needs is fixed to (PRIOR_MEMORY,) here, so the service request is
        # always valid — no InvalidAnalysisContextRequest→400 branch to add
        # (the request validation is a service-level contract, locked at that
        # layer). Only job/project 404 is reachable from this endpoint.
        request = AnalysisContextRequest(
            project_id=project_id,
            needs=(ContextNeed.PRIOR_MEMORY,),
            memory_types=memory_types,
            exclude_job_id=job.id,
        )
        package = analysis_context.build_prior_memory_package(request)
        gate = evaluate_analysis_context_gate(package=package, request=request)
        return _analysis_context_payload(package, gate)

    def _action_proposal_payload(proposal) -> dict[str, object]:
        return {
            "candidate_id": proposal.candidate_id,
            "candidate_type": proposal.candidate_type.value,
            "action": proposal.action.value,
            "matched_memory_id": proposal.matched_memory_id,
            "rationale": proposal.rationale,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/compare")
    async def analysis_compare_endpoint(
        project_id: str, job_id: str
    ) -> dict[str, object]:
        # Phase 2B.3 (D7): compare a job's candidates against canonical memory
        # and return one action proposal per candidate (proposal only — no
        # memory write, D4=A).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            proposals = await compare.compare_job(
                project_id=project_id, job_id=job.id, candidates=candidates
            )
        except CompareJudgeNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except InvalidJudgeResult as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ProviderError as exc:
            # A Gateway/provider failure during the matched-pair judge turn
            # (timeout/unavailable/5xx) is an LLM error → 502, applying the
            # v1.6.34 error taxonomy to this endpoint. Without this the
            # ProviderError raised by GatewayGenerateProvider propagates as an
            # unhandled 500.
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "job_id": job.id,
            "proposals": [_action_proposal_payload(p) for p in proposals],
        }

    def _applied_proposal_payload(applied) -> dict[str, object]:
        return {
            "candidate_id": applied.candidate_id,
            "action": applied.action.value,
            "outcome": applied.outcome.value,
            "memory_id": applied.memory_id,
            "superseded_memory_id": applied.superseded_memory_id,
            "version": applied.version,
            "idempotent_replay": applied.idempotent_replay,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/apply")
    async def analysis_apply_endpoint(
        project_id: str, job_id: str, request: ApplyMemoryRequest
    ) -> dict[str, object]:
        # Phase 2B.4 (D1=A/D6=A): apply reviewed compare proposals to the
        # canonical memory store. Deterministic writes only — the proposals
        # carry the already-decided action labels (no LLM here). Safe actions
        # (create/update/add_evidence/no_change) are applied; conflict is
        # review-only (D7).
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
            candidates = analysis.list_candidates(
                project_id=project_id, job_id=job_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        proposals: list[ActionProposal] = []
        by_id = {candidate.id: candidate for candidate in candidates}
        for body in request.proposals:
            candidate = by_id.get(body.candidate_id)
            if candidate is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"candidate {body.candidate_id} is not part of this job",
                )
            try:
                action = CompareAction(body.action)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"unknown action {body.action!r}"
                ) from exc
            proposals.append(
                ActionProposal(
                    candidate_id=body.candidate_id,
                    candidate_type=candidate.candidate_type,
                    action=action,
                    matched_memory_id=body.matched_memory_id,
                    rationale="",
                )
            )

        try:
            applied = apply_service.apply_proposals(
                project_id=project_id,
                proposals=tuple(proposals),
                candidates=candidates,
            )
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (MissingMatchedMemory, MemoryError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MemoryApplyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "job_id": job.id,
            "applied": [_applied_proposal_payload(a) for a in applied],
        }

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
    # /context-search serves Writing only; analysis_context has its own
    # job-scoped endpoint. Keep the two purposes on separate surfaces.
    if purpose is not ContextSearchPurpose.WRITING_CONTEXT:
        raise ValueError(f"unsupported purpose: {body.purpose}")
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
