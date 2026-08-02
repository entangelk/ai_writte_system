"""FastAPI application shell for the Application service."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Annotated, Protocol, Union

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from services.application.app.auth.cookies import SESSION_COOKIE_NAME, cookie_kwargs
from services.application.app.auth.access_grants import (
    AccessGrantService,
    InMemoryAccessGrantRepository,
)
from services.application.app.auth.sessions import (
    DEFAULT_SESSION_TTL,
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import (
    DuplicateUsername,
    InMemoryUserRepository,
    InvalidUserInput,
    LastActiveAdmin,
    UserNotFound,
    UserService,
)
from services.application.app.auth.password import Argon2PasswordHasher
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
    InvalidCandidateStateTransition,
    InvalidJobStateTransition,
)
from services.application.app.analysis.candidate_review import (
    CandidateReviewService,
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
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
)
from services.application.app.analysis.reconciliation import (
    CharacterReconciliationService,
    ReconciliationAction,
)
from services.application.app.analysis.review_inbox import (
    ReviewInboxNotFound,
    ReviewInboxService,
    candidate_affordances,
    conflict_affordances,
    gate_finding_affordances,
)
from services.application.app.writing.models import (
    NextUnit,
    OutputLength,
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingIntent,
    WritingOutputType,
    WritingRequest,
    WritingTaskType,
)
from services.application.app.writing.revise import (
    InvalidWritingRevision,
    WritingRevisionError,
    WritingRevisionService,
    seed_writing_revise_template,
)
from services.application.app.writing.revise_gate import (
    WritingLoopPolicy,
    WritingLoopRevisionFailure,
    WritingRetrievalConfigurationError,
    WritingRetrievalFailure,
    WritingReviseGateFailure,
    WritingReviseReportFailure,
    WritingReviseGateService,
)
from services.application.app.writing.retrieval import (
    InvalidWritingRetrievalPlan,
    TerminalJsonWritingRetrievalPlanner,
    WritingRetrievalPlannerError,
    seed_writing_retrieval_template,
)
from services.application.app.writing.gate import (
    InvalidWritingGateResult,
    WritingGateError,
    WritingGateService,
    seed_writing_gate_template,
)
from services.application.app.writing.accept import (
    StaleWritingBase,
    WritingAcceptAnalysisError,
    WritingAcceptError,
    WritingAcceptService,
)
from services.application.app.writing.context_pointer import pointer_wire
from services.application.app.writing.model_capabilities import ModelCapabilities
from services.application.app.writing.report import (
    InvalidCandidateReport, WritingCandidateReportService, seed_report_template,
)
from services.application.app.writing.report import TEMPLATE as REPORT_SYSTEM_TEMPLATE
from services.application.app.writing.report_budget import (
    candidate_tokens_from_text, derive_context_budget,
)
from services.application.app.writing.service import (
    WritingError,
    WritingService,
    seed_writing_template,
)
from services.application.app.writing.loop_audit import (
    InMemoryWritingLoopAuditRepository,
    WritingLoopAuditNotFound,
    WritingLoopAuditService,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallSite,
    gate_quality_score,
)
from services.application.app.observability.kpi import (
    aggregate_global_kpi,
    aggregate_kpi,
)
from services.application.app.observability.llm_call_scope import (
    ObservedProvider,
    llm_call_scope,
    reclassify_planner_parse_error,
)
from services.application.app.writing.scratch import (
    MAX_SCRATCH_PER_DRAFT,
    InMemoryWritingScratchRepository,
    WritingScratchService,
)
from services.application.app.writing.generation_job import (
    DEFAULT_CLAIM_TIMEOUT_SECONDS,
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobService,
)
from services.application.app.writing.generation_job import (
    # Distinct class from analysis.service.InvalidJobStateTransition (imported
    # above) — the generation job service raises its own, so the retry endpoint
    # must catch this one to map it to 409.
    InvalidJobStateTransition as InvalidGenerationJobStateTransition,
)
from services.application.app.writing.generation_worker import (
    GenerationCollaborators,
)
from services.application.app.writing.http_models import (
    ACCEPT_RESPONSES,
    ErrorDetailResponse,
    GENERATE_ASYNC_RESPONSES,
    REVISE_AND_GATE_RESPONSES,
    WritingAcceptResponse,
    WritingCandidatePayload,
    WritingContextBudgetPayload,
    WritingGenerationJobPayload,
    WritingGatePayload,
    WritingReviseGateResponse,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import LLMProvider
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryError,
    MemoryNotFound,
    MemoryReindexEnqueueFailed,
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
from services.application.app.context_search.gate_findings import (
    GateFindingError,
    GateFindingNotFound,
    GateFindingService,
    GateFindingStatus,
    InMemoryGateFindingRepository,
    InvalidGateFindingTransition,
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
    HybridCanonicalMemoryRetriever,
    HybridCandidateMemoryRetriever,
    LexicalCanonicalMemoryRetriever,
    LexicalCandidateMemoryRetriever,
    MongoDirectCanonicalMemoryRetriever,
    MongoDirectCandidateMemoryRetriever,
    VectorCanonicalMemoryRetriever,
    VectorCandidateMemoryRetriever,
    evaluate_context_gate,
)
from services.application.app.core_sot.models import BlockKind, UnitKind
from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    CoreSotService,
    DraftOrderIntegrityError,
    InMemoryCoreSotRepository,
    InvalidDraftOrder,
    NotFound,
    StaleProjectBriefBase,
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
    ChromaCandidateVectorIndexAdapter,
    ChromaMemoryVectorIndexAdapter,
    ChromaVectorIndexAdapter,
    connect_chroma_collection,
)
from services.application.app.indexing.embedding import (
    EmbeddingProviderError, RemoteEmbeddingProvider,
)
from services.application.app.indexing.memory_index import MEMORY_VECTOR_COLLECTION
from services.application.app.indexing.memory_lexical_index import (
    MEMORY_LEXICAL_INDEX,
    connect_elasticsearch_memory_index,
)
from services.application.app.indexing.candidate_index import (
    CANDIDATE_VECTOR_COLLECTION,
)
from services.application.app.indexing.candidate_lexical_index import (
    CANDIDATE_LEXICAL_INDEX,
    connect_elasticsearch_candidate_index,
)
from services.application.app.analysis.semantic_matcher import (
    EmbeddingCharacterIdentityVerifier,
    EmbeddingSemanticMatcher,
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


def _default_analysis_service(
    core_sot: CoreSotService,
    *,
    reindex_outbox: "IndexSyncOutboxService | None" = None,
) -> AnalysisService:
    # b-2 (G2): recording a needs_review candidate enqueues a CANDIDATE_UPSERTED
    # index sync through the shared outbox; the worker drains it into the
    # candidate index. An injected analysis_service (tests) keeps its own wiring.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return AnalysisService(
            InMemoryAnalysisRepository(),
            source_ref_resolver=CoreSotSourceAdapter(core_sot),
            reindex_outbox=reindex_outbox,
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
        reindex_outbox=reindex_outbox,
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


def _default_review_queue_service() -> ReviewQueueService:
    # 2B.4 follow-up: durable review queue for review-only (conflict) proposals.
    # Mongo-backed when configured, else the non-durable in-memory repo.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return ReviewQueueService(InMemoryReviewQueueRepository())

    from services.application.app.analysis.review_queue_mongo_repository import (
        MongoReviewQueueRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME

    return ReviewQueueService(
        MongoReviewQueueRepository.from_uri(
            uri,
            db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME),
        )
    )


def _default_gate_finding_service() -> GateFindingService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return GateFindingService(InMemoryGateFindingRepository())
    from services.application.app.context_search.gate_findings_mongo import (
        MongoGateFindingRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return GateFindingService(MongoGateFindingRepository.from_uri(
        uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    ))


def _default_user_service() -> UserService:
    # Multi-user D1=A: auth lives inside the application, so it shares the
    # canonical store's connection settings rather than inventing its own.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    hasher = Argon2PasswordHasher()
    if not uri:
        return UserService(InMemoryUserRepository(), hasher=hasher)
    from services.application.app.auth.users_mongo import MongoUserRepository
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return UserService(
        MongoUserRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        hasher=hasher,
    )


def _default_session_service() -> SessionService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    ttl = DEFAULT_SESSION_TTL
    hours = os.environ.get("AUTH_SESSION_TTL_HOURS")
    if hours:
        # Refuse to start on a malformed/negative TTL rather than silently
        # falling back — a session that never expires is a security defect.
        parsed = float(hours)
        if parsed <= 0:
            raise ValueError("AUTH_SESSION_TTL_HOURS must be > 0")
        ttl = timedelta(hours=parsed)
    if not uri:
        return SessionService(InMemorySessionRepository(), ttl=ttl)
    from services.application.app.auth.sessions_mongo import MongoSessionRepository
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return SessionService(
        MongoSessionRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        ttl=ttl,
    )


def _default_access_grant_service() -> AccessGrantService:
    # The TTL is a contract literal (C-1 = 1 hour), not an env knob: a grant that
    # outlives the support task is exactly the risk F1=C was chosen to bound, and
    # a per-deployment override would make the audit trail mean different things
    # on different machines.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return AccessGrantService(InMemoryAccessGrantRepository())
    from services.application.app.auth.access_grants_mongo import (
        MongoAccessGrantRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return AccessGrantService(
        MongoAccessGrantRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        )
    )


def _default_writing_loop_audit_service() -> WritingLoopAuditService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return WritingLoopAuditService(InMemoryWritingLoopAuditRepository())
    from services.application.app.writing.loop_audit_mongo import (
        MongoWritingLoopAuditRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return WritingLoopAuditService(MongoWritingLoopAuditRepository.from_uri(
        uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    ))


def _default_llm_call_audit_service() -> LlmCallAuditService:
    # Observability KPI phase (SoT §"LLM 파이프라인 관측(KPI)"). Always available
    # (in-memory default) for the same reason the loop audit is: a call site that
    # only records when infra happens to be configured produces a KPI that
    # silently undercounts. A Mongo URI upgrades it to the durable adapter.
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return LlmCallAuditService(InMemoryLlmCallAuditRepository())
    from services.application.app.observability.llm_call_audit_mongo import (
        MongoLlmCallAuditRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return LlmCallAuditService(MongoLlmCallAuditRepository.from_uri(
        uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
    ))


def _default_writing_scratch_service() -> WritingScratchService:
    # Unaccepted-candidate recovery store (brief D2=A). In-memory default keeps
    # the safety net working with no infra; a Mongo URI upgrades it to durable
    # ``writing_drafts_scratch`` (Core-SOT-external). The per-draft history cap
    # is env-tunable (default 20) because the useful depth differs per writer and
    # the value is still provisional pending SoT ratification.
    max_per_draft = _env_int(
        "WRITING_SCRATCH_MAX_PER_DRAFT", MAX_SCRATCH_PER_DRAFT
    )
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return WritingScratchService(
            InMemoryWritingScratchRepository(), max_per_draft=max_per_draft
        )
    from services.application.app.writing.scratch_mongo import (
        MongoWritingScratchRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return WritingScratchService(
        MongoWritingScratchRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        max_per_draft=max_per_draft,
    )


def _default_writing_generation_job_service() -> WritingGenerationJobService:
    # Async generation job store (async-pad D4=A). In-memory default; a Mongo URI
    # upgrades it to the durable ``writing_generation_jobs`` with the atomic
    # find_one_and_update claim. The claim lease is env-tunable (default 600s) so
    # a long generate fits comfortably under it.
    claim_timeout = _env_int(
        "WRITING_GENERATION_CLAIM_TIMEOUT_SECONDS", DEFAULT_CLAIM_TIMEOUT_SECONDS
    )
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return WritingGenerationJobService(
            InMemoryWritingGenerationJobRepository(),
            claim_timeout_seconds=claim_timeout,
        )
    from services.application.app.writing.generation_job_mongo import (
        MongoWritingGenerationJobRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return WritingGenerationJobService(
        MongoWritingGenerationJobRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        claim_timeout_seconds=claim_timeout,
    )


def _default_prompt_template_service() -> PromptTemplateService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v1()
        service.seed_analysis_extract_v2()
        service.seed_analysis_extract_v3()
        service.seed_analysis_extract_v4()
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
    service.seed_analysis_extract_v2()
    service.seed_analysis_extract_v3()
    service.seed_analysis_extract_v4()
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


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


# The self-report's OUTPUT budget. It must exceed the longest prose preset
# (WRITING_OUTPUT_LENGTH_LONG, 4096): the report is a structured JSON summary OF
# that prose, so a cap at or below the prose length truncates the JSON mid-string
# and the parser fails with `invalid_report` — observed live on 2026-07-22 at the
# old 1024 default, where every failure cut off in the same ~2200-char window
# regardless of prose length.
#
# The ceiling is the llama.cpp per-slot context (LLAMA_CTX_SIZE, 8192), which the
# prompt and the completion share. 6144 leaves 2048 tokens of prompt headroom, so
# the cap stays a real limit instead of being silently clamped by the server.
# Raising it further only pays off together with a larger context window.
WRITING_REPORT_DEFAULT_MAX_TOKENS = 6144


def _env_opt_int(name: str) -> int | None:
    # Unset or empty means "no limit" (None) for the aggregate loop budget.
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


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
    provider = ObservedProvider(
        GatewayGenerateProvider(
            base_url=base_url,
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
        ),
        call_site=LlmCallSite.ANALYSIS_EXTRACTOR,
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
    judge = None
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if base_url:
        prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_analysis_compare_template(prompt_templates)
        # Observability seam C (증분 C): one record per judge turn, so a job
        # that judges N matched pairs leaves N rows — plus a second row when a
        # non-JSON verdict triggers the repair retry.
        provider = ObservedProvider(
            GatewayGenerateProvider(
                base_url=base_url,
                timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
                trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
            ),
            call_site=LlmCallSite.COMPARE_JUDGE,
        )
        judge = TerminalJsonCompareJudge(
            provider,
            prompt_templates=prompt_templates,
            model=os.environ.get("LLM_GATEWAY_MODEL") or None,
            max_tokens=int(os.environ.get("ANALYSIS_COMPARE_MAX_TOKENS", "512")),
        )
    return AnalysisCompareService(
        memory_service=memory,
        judge=judge,
        semantic_matcher=_build_semantic_matcher(memory),
        alias_matcher=_build_character_alias_matcher(memory),
        homonym_verifier=_build_character_homonym_verifier(),
    )


# Fixed retrieval needs for a continue_scene generation (Phase 5.1). Mongo-served
# needs (current/recent scene) require a current_position; when absent they yield
# empty sections and generation proceeds with whatever context was retrieved.
_WRITING_CONTINUE_SCENE_NEEDS = (
    ContextNeed.CURRENT_SCENE,
    ContextNeed.RECENT_SCENES,
    ContextNeed.CANONICAL_MEMORY,
)


def _default_writing_service() -> WritingService | None:
    # Phase 5.1: wire the Writing generation service when a Gateway is configured;
    # otherwise the endpoint reports 503 (mirrors the analysis runner / compare
    # judge / context search planner env gating).
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_template(prompt_templates)
    provider = GatewayGenerateProvider(
        base_url=base_url,
        timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
        trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
    )
    # The reporter shares this gateway provider but is a *different* call site
    # (owner decision 2026-07-26, D2): it wraps the raw provider with its own
    # ``writing_report`` label, so a generate that also self-reports leaves two
    # rows that can be told apart. Passing the generation-wrapped provider here
    # instead would label both rows ``writing_generation``.
    reporter = _build_report_service(provider)
    return WritingService(
        ObservedProvider(provider, call_site=LlmCallSite.WRITING_GENERATION),
        prompt_templates=prompt_templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_GENERATE_MAX_TOKENS", "1024")),
        reporter=reporter,
    )


def _default_model_capabilities() -> ModelCapabilities | None:
    """게이트웨이가 아는 모델 사실(창·토큰 계수)의 앱쪽 창구. 게이트웨이가 없으면 None.

    **report 서비스와 같은 env(`LLM_GATEWAY_BASE_URL`)에 걸려 있는 것이 의도다** — 게이트웨이가
    없으면 report 호출 자체가 없으므로 예산을 줄일 이유도 없다(R-a).
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    return ModelCapabilities(
        base_url=base_url,
        timeout_seconds=_env_float("LLM_GATEWAY_CAPABILITIES_TIMEOUT_SECONDS", 10.0),
        trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
    )


def _report_output_cap() -> int:
    """report 호출의 출력 상한. `_build_report_service`와 **같은 env를 같은 기본값으로** 읽는다."""
    return _env_int("WRITING_REPORT_MAX_TOKENS", WRITING_REPORT_DEFAULT_MAX_TOKENS)


def _build_report_service(provider) -> WritingCandidateReportService:
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_report_template(templates)
    return WritingCandidateReportService(
        ObservedProvider(provider, call_site=LlmCallSite.WRITING_REPORT),
        prompt_templates=templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=_env_int("WRITING_REPORT_MAX_TOKENS", WRITING_REPORT_DEFAULT_MAX_TOKENS))


def _build_revise_service(provider) -> WritingRevisionService:
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_revise_template(templates)
    return WritingRevisionService(
        ObservedProvider(provider, call_site=LlmCallSite.WRITING_REVISION),
        prompt_templates=templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_REVISE_MAX_TOKENS", "512")),
    )


def _build_writing_retrieval_planner(provider):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_retrieval_template(templates)
    return TerminalJsonWritingRetrievalPlanner(
        # A separate site from the context-search planner (owner decision
        # 2026-07-26, D1): same "what should I retrieve next" job, but a
        # different prompt, token cap and failure surface, and it runs inside
        # the revise loop where the other never does.
        ObservedProvider(
            provider, call_site=LlmCallSite.WRITING_RETRIEVAL_PLANNER
        ),
        prompt_templates=templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_RETRIEVAL_PLAN_MAX_TOKENS", "512")),
    )


def _default_writing_gate_service(
    *, provider: LLMProvider | None = None,
) -> WritingGateService | None:
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_writing_gate_template(prompt_templates)
    # ``provider`` lets an operator-only diagnostic reuse this exact config
    # (prompt template + LLM_GATEWAY_MODEL / WRITING_GATE_MAX_TOKENS env
    # contract) with a raw-capturing wrapper, mirroring _build_revise_service /
    # _build_report_service which already accept a provider. Default builds the
    # real gateway provider (unchanged behaviour).
    gate_provider = ObservedProvider(
        provider or GatewayGenerateProvider(
            base_url=base_url,
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
        ),
        call_site=LlmCallSite.WRITING_GATE,
    )
    return WritingGateService(
        gate_provider, prompt_templates=prompt_templates,
        model=os.environ.get("LLM_GATEWAY_MODEL") or None,
        max_tokens=int(os.environ.get("WRITING_GATE_MAX_TOKENS", "1024")),
    )


def _build_semantic_matcher(memory: MemoryService):
    # Phase 2B.6 (D4=A): off by default. The threshold env is the on-switch; a
    # guessed value must not silently merge canon, so absent it, event/
    # open_question stay always-create. See
    # docs/plans/02b-6-semantic-identity-resolution-decisions.md.
    return _build_memory_semantic_matcher(
        memory, threshold_env="ANALYSIS_SEMANTIC_MATCH_THRESHOLD"
    )


def _build_character_alias_matcher(memory: MemoryService):
    # Phase 2B.7 (D4/D5): off by default, on its own threshold env (character's
    # name signal warrants a threshold distinct from event/open_question). When
    # set, a character candidate with no same-name canonical is checked against
    # semantically-near canonical characters; a hit → conflict (review), never
    # an automatic merge (D1=A/D2=A). See
    # docs/plans/02b-7-character-alias-homonym-decisions.md.
    return _build_memory_semantic_matcher(
        memory, threshold_env="ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD"
    )


def _build_character_homonym_verifier():
    threshold_raw = os.environ.get("ANALYSIS_CHARACTER_HOMONYM_MATCH_THRESHOLD")
    if not threshold_raw:
        return None
    if not os.environ.get("EMBEDDING_SERVICE_URL"):
        raise RuntimeError(
            "ANALYSIS_CHARACTER_HOMONYM_MATCH_THRESHOLD requires "
            "EMBEDDING_SERVICE_URL"
        )
    return EmbeddingCharacterIdentityVerifier(
        embeddings=_build_embedding_provider(),
        similarity_floor=float(threshold_raw),
    )


def _build_memory_semantic_matcher(memory: MemoryService, *, threshold_env: str):
    # Shared builder for the compare semantic seams (2B.6 event/open_question and
    # 2B.7 character alias). Semantic matching needs the real shared
    # memory_vectors collection — the in-memory fake in this process is separate
    # from the worker's, so without CHROMA_HOST there is nothing to query.
    threshold_raw = os.environ.get(threshold_env)
    host = os.environ.get("CHROMA_HOST")
    if not threshold_raw or not host:
        return None
    # Fail fast on a misconfiguration: enabling semantic matching without a real
    # embedding service would query the 1024-dim memory_vectors collection with
    # the fake embedding's dimensions. Surface it clearly at wiring time instead
    # of a cryptic dimension mismatch on the first candidate (verification obs #1).
    if not os.environ.get("EMBEDDING_SERVICE_URL"):
        raise RuntimeError(
            f"{threshold_env} + CHROMA_HOST enable semantic memory matching, "
            "which requires EMBEDDING_SERVICE_URL — the fake embedding does not "
            "match the memory_vectors collection dimensions."
        )
    vector_search = ChromaMemoryVectorIndexAdapter(
        connect_chroma_collection(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            collection_name=os.environ.get(
                "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
            ),
        )
    )
    return EmbeddingSemanticMatcher(
        embeddings=_build_embedding_provider(),
        vector_search=vector_search,
        memory_service=memory,
        similarity_threshold=float(threshold_raw),
        limit=int(os.environ.get("ANALYSIS_SEMANTIC_MATCH_LIMIT", "5")),
    )


def _default_context_search_service(
    core_sot: CoreSotService,
    *,
    vector_index: InMemoryVectorIndexAdapter | ChromaVectorIndexAdapter,
    embeddings: EmbeddingProvider,
    memory: MemoryService,
    analysis: AnalysisService,
) -> ContextSearchService | None:
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    prompt_templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_context_search_plan_template(prompt_templates)
    provider = ObservedProvider(
        GatewayGenerateProvider(
            base_url=base_url,
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
        ),
        call_site=LlmCallSite.QUERY_PLANNER,
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
        # Writing canonical inclusion (⑤ §5 B, D2 follow-up): relevance-ranked
        # vector retrieval over memory_vectors when the shared collection exists,
        # else Mongo-direct. The item/Gate authority re-derivation is unchanged.
        canonical_memory_retriever=_build_canonical_memory_retriever(memory),
        # Writing candidate inclusion (⑤ §5 B follow-up): vector/lexical/hybrid
        # over the candidate index when configured, else Mongo-direct. Labeled
        # candidate at the Gate; the authority re-derivation is unchanged (b-2).
        candidate_memory_retriever=_build_candidate_memory_retriever(analysis),
        # canonical↔candidate dedup ((e), v1.6.60): suppress a candidate that has
        # been promoted (its canonical copy already grounds the knowledge). The
        # MemoryService satisfies the resolver seam structurally.
        promoted_candidate_resolver=memory,
    )


def _build_canonical_memory_retriever(memory: MemoryService):
    # ⑤ §5 B canonical retrieval backend, chosen by env (D3/E6): vector over the
    # shared memory_vectors collection, lexical over the Elasticsearch memory
    # index, both fused by RRF when configured, else the deterministic Mongo-direct
    # listing. The item/Gate authority re-derivation is identical for every
    # backend — only the retrieval layer changes.
    vector = _build_vector_canonical_retriever(memory)
    lexical = _build_lexical_canonical_retriever(memory)
    if vector is not None and lexical is not None:
        return HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
    if vector is not None:
        return vector
    if lexical is not None:
        return lexical
    return MongoDirectCanonicalMemoryRetriever(memory)


def _build_vector_canonical_retriever(memory: MemoryService):
    # Like _build_semantic_matcher, the in-memory fake in this process is separate
    # from the worker's, so without CHROMA_HOST there is nothing to query; and the
    # real 1024-dim collection needs a real embedding service (the fake embedding's
    # dimensions do not match). With either absent, no vector backend.
    host = os.environ.get("CHROMA_HOST")
    if not host or not os.environ.get("EMBEDDING_SERVICE_URL"):
        return None
    vector_index = ChromaMemoryVectorIndexAdapter(
        connect_chroma_collection(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            collection_name=os.environ.get(
                "CHROMA_MEMORY_COLLECTION", MEMORY_VECTOR_COLLECTION
            ),
        )
    )
    return VectorCanonicalMemoryRetriever(
        memory_service=memory,
        embeddings=_build_embedding_provider(),
        vector_index=vector_index,
    )


def _build_lexical_canonical_retriever(memory: MemoryService):
    # §8 lexical leg: the Elasticsearch memory index when ELASTICSEARCH_URL is set.
    # The real ES client is imported lazily inside connect_elasticsearch_memory_index,
    # so unconfigured environments never need the package.
    url = os.environ.get("ELASTICSEARCH_URL")
    if not url:
        return None
    lexical_index = connect_elasticsearch_memory_index(
        url=url,
        index_name=os.environ.get(
            "ELASTICSEARCH_MEMORY_INDEX", MEMORY_LEXICAL_INDEX
        ),
    )
    return LexicalCanonicalMemoryRetriever(
        memory_service=memory, lexical_index=lexical_index
    )


def _build_candidate_memory_retriever(analysis: AnalysisService):
    # b-2: candidate retrieval backend, chosen by the same env switches as the
    # canonical path — vector over candidate_vectors, lexical over the ES candidate
    # index, both fused by RRF when configured, else the deterministic Mongo-direct
    # listing. The item/Gate authority re-derivation is identical for every backend.
    vector = _build_vector_candidate_retriever(analysis)
    lexical = _build_lexical_candidate_retriever(analysis)
    if vector is not None and lexical is not None:
        return HybridCandidateMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
    if vector is not None:
        return vector
    if lexical is not None:
        return lexical
    return MongoDirectCandidateMemoryRetriever(analysis)


def _build_vector_candidate_retriever(analysis: AnalysisService):
    # Symmetric to _build_vector_canonical_retriever: needs a real Chroma
    # collection and a real embedding service (fake dims do not match), else None.
    host = os.environ.get("CHROMA_HOST")
    if not host or not os.environ.get("EMBEDDING_SERVICE_URL"):
        return None
    vector_index = ChromaCandidateVectorIndexAdapter(
        connect_chroma_collection(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            collection_name=os.environ.get(
                "CHROMA_CANDIDATE_COLLECTION", CANDIDATE_VECTOR_COLLECTION
            ),
        )
    )
    return VectorCandidateMemoryRetriever(
        analysis_service=analysis,
        embeddings=_build_embedding_provider(),
        vector_index=vector_index,
    )


def _build_lexical_candidate_retriever(analysis: AnalysisService):
    # b-2 lexical leg: the Elasticsearch candidate index when ELASTICSEARCH_URL is
    # set. The real ES client is imported lazily inside connect_..., so
    # unconfigured environments never need the package.
    url = os.environ.get("ELASTICSEARCH_URL")
    if not url:
        return None
    lexical_index = connect_elasticsearch_candidate_index(
        url=url,
        index_name=os.environ.get(
            "ELASTICSEARCH_CANDIDATE_INDEX", CANDIDATE_LEXICAL_INDEX
        ),
    )
    return LexicalCandidateMemoryRetriever(
        analysis_service=analysis, lexical_index=lexical_index
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


# Product shell spine response models (SoT v1.6.95, D1=A/D2=A).
#
# These are declared as `response_model=` on the spine endpoints so OpenAPI emits
# a real response schema and the frontend generates its types instead of hand-
# declaring them. The endpoints keep returning hand-built dicts (D2=A): FastAPI
# validates the dict against the model, so no payload helper changes.
#
# WARNING: response_model silently DROPS any field a model does not declare. Keep
# each model exactly as wide as its payload; `SpineEnvelopeKeyTest` pins the full
# key set of every envelope below and bites if a model narrows one.


# HTTP error contract declarations (SoT v1.7.29 "HTTP 에러 응답 계약", H3 S2).
#
# Every error body in this app is the uniform ``{"detail": <string>}``
# (``ErrorDetailResponse``), so declaring a status documents *which* failures an
# endpoint can return — it never changes runtime behaviour. The status codes
# below are the realistic set each endpoint actually raises, not the full app
# vocabulary.
#
# 422 is deliberately absent everywhere: FastAPI documents request-schema
# validation automatically and its body shape (``{"detail": [ ... ]}``) differs.
_ERROR = {"model": ErrorDetailResponse}

# The only 503 in the CRUD family is the data-integrity face: stored drafts that
# predate the W3 ordered-unit invariant. The fix is the one-shot migration, not a
# corrected request, so the description says so rather than leaving the reader to
# infer it from a log (the exact gap H3 exists to close).
_MIGRATION_503 = {
    "model": ErrorDetailResponse,
    "description": "Stored draft metadata predates the ordered-unit invariant "
                   "(or is corrupt). Run scripts/migrate_ordered_units.py; "
                   "retrying the request alone cannot succeed.",
}

# SoT v1.7.35 D2=A: the third face of 503 — the canonical store is configured
# but *failing*. Unlike the other two faces the remedy is not a one-shot human
# action but storage recovery, after which retrying the same request is the
# correct recovery (promotion is idempotent, so a retry promotes only what is
# left).
#
# Resolved lazily and exactly once, because main.py must import without pymongo:
# the in-memory path needs no driver install (see _default_core_sot_service). A
# missing driver yields an empty tuple, and `except ()` matches nothing — which
# is the correct behaviour, since a deployment with no Mongo has no Mongo failure
# to classify.
#
# Deliberately ONE named seam rather than a clause per call site: it covers both
# the memory repository and the reindex outbox (each writes Mongo directly), and
# the deferred repository-level exception taxonomy replaces this single point
# instead of every endpoint (brief "Follow-up considerations").
def _resolve_storage_error_types() -> tuple[type[BaseException], ...]:
    try:
        from pymongo.errors import PyMongoError
    except ModuleNotFoundError:
        return ()
    return (PyMongoError,)


_STORAGE_ERRORS = _resolve_storage_error_types()


class AutoPromotePartialResponse(BaseModel):
    # SoT v1.7.35 D1=B: 503 raised *after* some candidates were already promoted.
    # Canonical mints are append-only and are not rolled back, so hiding them
    # behind a bare error body would make the response disagree with the stored
    # state. Same shape as the success envelope plus the failure reason; the
    # partial-envelope precedent is WritingAcceptAnalysisPartial (accept 502).
    #
    # Returned via JSONResponse, so this model is responses={} documentation only
    # and the exact-key regression is its runtime lock (same pattern as the
    # writing partials). ``promoted`` stays untyped item-wise because the success
    # arm of this endpoint is an untyped dict today — a narrower model here would
    # document a wire shape the endpoint does not actually promise.
    auto_promotion_threshold: float | None
    promoted: list[dict[str, object]]
    promotion_error: str


_AUTO_PROMOTE_503 = {
    "model": Union[AutoPromotePartialResponse, ErrorDetailResponse],
    "description": "The canonical store failed mid-promotion. Every memory this "
                   "call minted is returned in `promoted` — including one whose "
                   "mint succeeded but whose reindex enqueue then failed — and "
                   "none of them are rolled back, so `promoted` always matches "
                   "what is stored. `promotion_error` names the stage that "
                   "failed. Recover the store and retry the same request: "
                   "promotion is idempotent, so the retry promotes only what is "
                   "left — and a reindex enqueue lost after its mint is repaired "
                   "by that same retry, because a replayed promotion re-enqueues.",
}

# SoT v1.7.38: the storage face of 503 is reachable from *every* endpoint that
# touches Mongo — which is every endpoint except /health — because a global
# handler (see create_app) maps a driver failure to 503 instead of letting it
# leak as an opaque 500. Declaring it everywhere is what keeps OpenAPI the
# mechanical truth (D3=A): a status the runtime can return must appear here.
#
# Endpoints whose 503 already carried another face keep that wording and gain
# this sentence, because one status code gets one declaration and the reader
# needs to know both remedies apply.
_STORAGE_503_NOTE = (
    " The canonical store may also be unreachable or failing; in that case "
    "recover it and retry the same request unchanged."
)

_STORAGE_503 = {
    "model": ErrorDetailResponse,
    "description": "The canonical store is unreachable or failing. Recover it "
                   "and retry the same request; the request itself needs no "
                   "change.",
}


def _with_storage_note(declaration: dict) -> dict:
    return {**declaration, "description": declaration["description"] + _STORAGE_503_NOTE}


_MIGRATION_503 = _with_storage_note(_MIGRATION_503)

# Auth (multi-user D2=A). 401 first appeared on the login endpoint (bad
# credentials) and the session-reading endpoint (missing/expired/revoked cookie).
# Project-scoped declarations gain 403 through ``_owned`` below.
_ERRORS_401: dict[int | str, dict] = {401: _ERROR, 503: _STORAGE_503}
# Logout is the one non-/health operation that stays reachable without a session:
# it is idempotent by design so a client can always reach a known-logged-out
# state. It therefore keeps a declaration with no 401 — hence its own constant,
# so that adding 401 to the shared storage declaration cannot reach it.
_ERRORS_LOGOUT: dict[int | str, dict] = {503: _STORAGE_503}


# D8-3a: every protected operation can answer 401, so the declaration is added
# once here instead of 61 times at the call sites. H3 (D3=A) makes OpenAPI the
# mechanical truth about what a request can get back, and after this slice a
# sessionless request to any of them gets 401 before the handler runs.
#
# Central, but not a substitute for the guard: the wrapper only makes the
# *declaration* right. An operation that gets the declaration and forgets
# ``dependencies=_REQUIRE_AUTH`` would be documented as protected while staying
# open — which is why the exhaustive guard checks the route, not the spec.
def _protected(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    return {401: _ERROR, **declaration}


def _owned(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    """Declare the 403 face added by the project ownership dependency."""
    return {403: _ERROR, **declaration}


def _admin(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    """Declare the 403 face added by the admin dependency (D8-5).

    Same status as ``_owned`` and deliberately a separate helper: the two 403s
    answer different questions ("not your project" vs "not an admin"), and a
    single shared helper would make the declaration guards unable to say which
    boundary an operation is behind.
    """
    return {403: _ERROR, **declaration}


_ERRORS_STORAGE: dict[int | str, dict] = _protected({503: _STORAGE_503})
_ERRORS_404: dict[int | str, dict] = _protected({404: _ERROR, 503: _STORAGE_503})
_ERRORS_404_502: dict[int | str, dict] = _protected(
    {404: _ERROR, 502: _ERROR, 503: _STORAGE_503}
)
_ERRORS_404_STORAGE: dict[int | str, dict] = _protected(
    {404: _ERROR, 503: _AUTO_PROMOTE_503}
)
_ERRORS_400_404: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 503: _STORAGE_503,
})
_ERRORS_404_409: dict[int | str, dict] = _protected({
    404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
})
_ERRORS_400_404_409: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
})
# D8-5 admin surface. 403 = "not an admin" (see _admin), and it is additive over
# the same 401/503 every protected operation carries.
_ERRORS_ADMIN: dict[int | str, dict] = _admin(_protected({503: _STORAGE_503}))
_ERRORS_ADMIN_400_409: dict[int | str, dict] = _admin(_protected({
    400: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}))
_ERRORS_ADMIN_404_409: dict[int | str, dict] = _admin(_protected({
    404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}))
# D8-6d: project purge. Idempotent — re-purging an already-purged project hits
# core_sot._require_project NotFound → 404 (not 409; there is no conflict).
_ERRORS_ADMIN_404: dict[int | str, dict] = _admin(_protected({
    404: _ERROR, 503: _STORAGE_503,
}))

_ERRORS_404_MIGRATION: dict[int | str, dict] = _protected(
    {404: _ERROR, 503: _MIGRATION_503}
)
_ERRORS_400_404_MIGRATION: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 503: _MIGRATION_503,
})
_ERRORS_404_409_MIGRATION: dict[int | str, dict] = _protected({
    404: _ERROR, 409: _ERROR, 503: _MIGRATION_503,
})

# The analysis track's 503 is the *other* face: a collaborator the endpoint needs
# (the extraction runner, the compare judge) is absent from this deployment. The
# request is fine, so — like the migration face — retrying alone cannot help; the
# operator action is a deployment change. One constant covers both endpoints
# because the runtime ``detail`` already names which collaborator is missing, and
# the semantics are identical.
_CONFIG_503 = _with_storage_note({
    "model": ErrorDetailResponse,
    "description": "A collaborator this endpoint requires is not configured in "
                   "this deployment. Configure it in the deployment environment; "
                   "retrying the request alone cannot succeed.",
})

def _provider_error_status(error: ProviderError) -> int:
    """ProviderError → 이 API의 상태코드. **한 곳에만 둔다.**

    종전에는 이 매핑이 `504 if TIMEOUT else 502` 형태로 **9개 호출부에 복제**돼 있었다.
    K-3 창 가드가 세 번째 분기를 더하면서 복제본 하나만 놓쳐도 같은 사건이 endpoint마다
    다른 상태코드로 나가게 되므로 한 함수로 모았다.

    - `TIMEOUT` → **504**: 상류가 제때 답하지 않았다(v1.6.34 taxonomy).
    - `CONTEXT_WINDOW_EXCEEDED` → **400**: 창 가드가 **모델을 부르기 전에** 거부했다
      (K-3, 오너 2026-07-30). 상류 장애가 아니라 **요청이 너무 큰 것**이므로 4xx이며,
      같은 요청의 재시도는 반드시 같은 실패로 끝난다. `detail`이 입력·출력상한·창 수치를
      실어 나르므로 그 자체가 오너가 말한 "경고"다.
    - 그 밖의 provider 실패 → **502**: 상류는 있는데 실패했다.
    """
    if error.code is ProviderErrorCode.TIMEOUT:
        return 504
    if error.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
        return 400
    return 502


# 400은 K-3 창 가드가 이 endpoint에도 닿기 때문에 있다(오너 2026-07-30) — 요청이 창을
# 넘으면 모델을 부르기 전에 거부되고, 그 얼굴은 상류 장애(502)가 아니라 4xx다.
_ERRORS_404_502_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 502: _ERROR, 503: _CONFIG_503,
})
_ERRORS_400_404_409_502_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 409: _ERROR, 502: _ERROR, 503: _CONFIG_503,
})
# context-search is the only endpoint outside the writing track that can exhaust
# its own budget, so 504 first appears in the declared surface here.
_ERRORS_400_404_502_504_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 502: _ERROR, 503: _CONFIG_503, 504: _ERROR,
})


# --- Authentication enforcement (D8-3a) --------------------------------------
# D7=A: enforcement is a FastAPI *dependency* declared per operation, backed by
# an exhaustive guard — not middleware (path patterns become the policy and new
# routes open silently) and not the service layer (every signature changes).
#
# Module level rather than a create_app closure on purpose. A closure would be a
# different function object per app, so neither ``app.dependency_overrides`` nor
# the exhaustive guard could name it; the guard has to look for exactly one
# identity on every route or it cannot tell a protected route from an open one.
def current_user_or_none(request: Request):
    """Resolve the session cookie to a live, still-active user, or None."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return None
    session = request.app.state.sessions.resolve(raw_token)
    if session is None:
        return None
    user = request.app.state.users.get_by_id(session.user_id)
    # A user disabled or deleted after the session was minted must not keep
    # working just because the cookie is still within its TTL.
    if user is None or not user.is_active:
        return None
    return user


def require_authenticated_user(request: Request):
    """Fail closed: no live session means the operation does not run at all."""
    user = current_user_or_none(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


# C-2 read-only. HEAD rides along with GET because Starlette answers it from the
# same route; both are side-effect free by HTTP contract.
_GRANTED_METHODS = frozenset({"GET", "HEAD"})


def require_project_owner(
    request: Request,
    project_id: str,
    current=Depends(require_authenticated_user),
):
    """Allow the owning user, or an administrator holding a live access grant.

    Missing projects retain their 404 face.

    D8-5e (F1=C, owner 2026-08-02): the grant is the *only* way past ownership,
    and it is narrower than ownership in two ways that are both enforced here:

    * **read-only (C-2)** — a grant admits GET/HEAD and nothing else. Anything
      that could write is refused even while the grant is live, so an
      administrator can never edit someone else's manuscript. The test is the
      HTTP method rather than a hand-kept list of "read operations": a list
      would silently misclassify the next endpoint someone adds, and failing
      closed on an unlisted method is the safe direction.
    * **still an administrator** — the grant is checked *together with*
      ``is_admin``, not instead of it. A grant issued to someone who has since
      lost the role stops working immediately rather than outliving it.

    ``owner_id is None`` keeps denying everyone (E1=A) — a grant does not adopt
    an unowned project.
    """
    try:
        project = request.app.state.core_sot.get_project(project_id=project_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if project.owner_id is not None and project.owner_id == current.id:
        return project
    if (
        # E1=A first, on this branch too. Omitting it here (while the owner
        # branch had it) was the 2026-08-02 verification Blocking: an unowned
        # project opened to any admin holding a grant, contradicting the three
        # places the SoT says otherwise — including the docstring above.
        project.owner_id is not None
        and current.is_admin
        and request.method in _GRANTED_METHODS
        and request.app.state.access_grants.active(
            admin_user_id=current.id, project_id=project_id
        )
        is not None
    ):
        return project
    raise HTTPException(status_code=403, detail="forbidden")


def require_admin_user(current=Depends(require_authenticated_user)):
    """Allow only administrators (D8-5, D6=A).

    403 rather than 401: the session is live and re-logging in changes nothing,
    which is the same distinction the ownership boundary draws. It is also *not*
    404 — hiding the admin surface would mean the frontend could not tell "no
    such endpoint" from "not for you".
    """
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="forbidden")
    return current


# One shared list so every protected operation declares the *same* dependency
# object. ``dependencies=`` copies it per route, so sharing is safe.
_REQUIRE_AUTH = [Depends(require_authenticated_user)]
_REQUIRE_PROJECT_OWNER = [
    Depends(require_authenticated_user),
    Depends(require_project_owner),
]
# D8-5: the admin surface is a third tier, layered the same way — the outer list
# names the authentication dependency so the exhaustive guard can see it on the
# route, and the inner dependency re-declares it so the check cannot run against
# an unauthenticated request even if the outer layer is ever dropped.
_REQUIRE_ADMIN = [
    Depends(require_authenticated_user),
    Depends(require_admin_user),
]


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPayload(BaseModel):
    # Deliberately no password_hash: the wire model is the reason a hash cannot
    # leak by someone later returning the domain object directly.
    id: str
    username: str
    is_admin: bool


class LoginResponse(BaseModel):
    user: UserPayload


class LogoutResponse(BaseModel):
    ok: bool


class AdminUserPayload(BaseModel):
    # Same no-password_hash reason as UserPayload, and one field more: the admin
    # list is the only surface where whether an account is disabled is the point.
    id: str
    username: str
    is_admin: bool
    is_active: bool


class AdminUserListResponse(BaseModel):
    users: list[AdminUserPayload]


class CreateUserRequest(BaseModel):
    # The admin supplies the initial password, exactly as scripts/create_user.py
    # does. Generating and delivering a temporary one needs a channel this
    # deployment does not have.
    username: str
    password: str
    is_admin: bool = False


class ProjectPayload(BaseModel):
    id: str
    name: str
    archived: bool


class ProjectListResponse(BaseModel):
    projects: list[ProjectPayload]


NonBlankBriefString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"\S")
]


class AccessGrantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # C-5: required, and non-blank. "왜 봤는가" is the whole value of the audit
    # record, and a blank string would satisfy a plain `str` while recording
    # nothing. The service re-checks so non-HTTP callers cannot skip it.
    reason: NonBlankBriefString


class AccessGrantPayload(BaseModel):
    id: str
    project_id: str
    admin_user_id: str
    reason: str
    created_at: datetime
    expires_at: datetime


class AccessGrantCreateResponse(BaseModel):
    grant: AccessGrantPayload

PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS = 3
PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS = 1000


def _project_brief_style_example_limits() -> tuple[int, int]:
    max_items = _env_int(
        "PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS",
        PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS,
    )
    max_chars = _env_int(
        "PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS",
        PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS,
    )
    for name, value in (
        ("PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS", max_items),
        ("PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS", max_chars),
    ):
        if value < 1:
            raise ValueError(f"{name} must be at least 1")
    return max_items, max_chars


def _writing_output_length_tokens() -> dict[OutputLength, int]:
    # 문체/분량 슬라이스 증분 2 (D3=A). The SERVER owns the preset→output-token
    # mapping; the confirmed defaults are 1024/2048/4096 and each is env-adjustable
    # with fail-loud validation (mirrors `_project_brief_style_example_limits`,
    # increment 1's sibling precedent). `short` defaults to the existing
    # WRITING_GENERATE_MAX_TOKENS so operators who already tuned it keep that value.
    presets = {
        OutputLength.SHORT: _env_int(
            "WRITING_OUTPUT_LENGTH_SHORT",
            _env_int("WRITING_GENERATE_MAX_TOKENS", 1024),
        ),
        OutputLength.MEDIUM: _env_int("WRITING_OUTPUT_LENGTH_MEDIUM", 2048),
        OutputLength.LONG: _env_int("WRITING_OUTPUT_LENGTH_LONG", 4096),
    }
    for length, value in presets.items():
        if value < 1:
            raise ValueError(
                f"WRITING_OUTPUT_LENGTH_{length.name} must be at least 1"
            )
    return presets


class ProjectBriefVersionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonBlankBriefString
    project_id: NonBlankBriefString
    version_number: Annotated[int, Field(ge=1)]
    premise: NonBlankBriefString | None
    genre: NonBlankBriefString | None
    tone: NonBlankBriefString | None
    pov: NonBlankBriefString | None
    constraints: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_rules: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    preferred_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    forbidden_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_examples: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )

class ProjectBriefGetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: ProjectBriefVersionPayload | None


class ProjectBriefPutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: ProjectBriefVersionPayload
    idempotent_replay: bool


class ProjectBriefVersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versions: list[ProjectBriefVersionPayload]


class DraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    title: str
    archived: bool
    unit_kind: UnitKind
    position: int = Field(ge=1)


class DraftListResponse(BaseModel):
    drafts: list[DraftPayload]


class DraftVersionMetaPayload(BaseModel):
    # idempotency_key is intentionally absent: an internal save token, not part
    # of the public read surface (mirrors _version_meta_payload).
    id: str
    project_id: str
    draft_id: str
    version_number: int
    snapshot_id: str


class DraftVersionListResponse(BaseModel):
    versions: list[DraftVersionMetaPayload]


class SnapshotDetailPayload(BaseModel):
    id: str
    project_id: str
    draft_id: str
    version_id: str
    raw_text: str
    content_hash: str


class SourceBlockDetailPayload(BaseModel):
    id: str
    project_id: str
    snapshot_id: str
    block_index: int
    kind: BlockKind
    start_offset: int
    end_offset: int
    text: str


class DraftVersionDetailResponse(BaseModel):
    draft_version: DraftVersionMetaPayload
    snapshot: SnapshotDetailPayload
    blocks: list[SourceBlockDetailPayload]


# The save surface is deliberately narrower than the read surface above and
# reuses the same key names (draft_version/snapshot/blocks) with fewer fields.
# Sharing one model across both breaks in whichever direction it is shared:
# the wide read model on this narrow payload fails validation (missing fields),
# and the narrow model on the read payload silently drops fields. Hence the
# separate declarations.


class SavedDraftVersionPayload(BaseModel):
    id: str
    version_number: int
    snapshot_id: str


class SavedSnapshotPayload(BaseModel):
    id: str
    content_hash: str


class SavedSourceBlockPayload(BaseModel):
    id: str
    kind: BlockKind
    start_offset: int
    end_offset: int


class SaveDraftResponse(BaseModel):
    draft_version: SavedDraftVersionPayload
    snapshot: SavedSnapshotPayload
    blocks: list[SavedSourceBlockPayload]
    idempotent_replay: bool


class DraftVersionExportResponse(BaseModel):
    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    draft_id: str
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


class ProjectExportUnitModel(BaseModel):
    draft_id: str
    title: str
    unit_kind: str | None
    position: int | None
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


class ProjectExportManifest(BaseModel):
    project_id: str
    format: str
    include_archived: bool
    units: list[ProjectExportUnitModel]


class ProjectExportResponse(BaseModel):
    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    include_archived: bool
    manifest: ProjectExportManifest | None


# Project/draft naming constraint (SoT v1.6.95, D3=A). Validation lives at the
# HTTP boundary: every client reaches Core SOT through it, so rejecting here
# closes the blank-name hole without changing the Core SOT contract. Whitespace
# is stripped BEFORE min_length runs, so "  x  " is stored as "x" and a
# whitespace-only name is a 422 rather than a blank name in the canonical store.
NonBlankName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateProjectRequest(BaseModel):
    name: NonBlankName


class PutProjectBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version_id: NonBlankBriefString | None
    idempotency_key: NonBlankBriefString
    premise: NonBlankBriefString | None
    genre: NonBlankBriefString | None
    tone: NonBlankBriefString | None
    pov: NonBlankBriefString | None
    constraints: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_rules: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    preferred_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    forbidden_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_examples: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )

    @field_validator(
        "constraints", "style_rules", "preferred_patterns",
        "forbidden_patterns", "style_examples",
    )
    @classmethod
    def reject_normalized_duplicates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("brief arrays must not contain duplicates")
        return value

    @field_validator("style_examples")
    @classmethod
    def enforce_style_example_limits(cls, value: list[str]) -> list[str]:
        max_items, max_chars = _project_brief_style_example_limits()
        if len(value) > max_items:
            raise ValueError(f"style_examples must contain at most {max_items} items")
        if any(len(example) > max_chars for example in value):
            raise ValueError(
                f"style_examples entries must contain at most {max_chars} characters"
            )
        return value


class CreateAnalysisJobRequest(BaseModel):
    snapshot_id: str
    idempotency_key: str


class CreateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankName
    unit_kind: UnitKind = UnitKind.OTHER


class DraftOrderPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Keep the structural constraint discoverable in OpenAPI, but route runtime
    # duplicate detection through CoreSotService so every incomplete/full-set
    # permutation violation has the W0 §2.2 exact 409 outcome (not Pydantic 422).
    ordered_draft_ids: list[NonBlankName] = Field(
        json_schema_extra={"uniqueItems": True}
    )


class DraftOrderPutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drafts: list[DraftPayload]


class RenameProjectRequest(BaseModel):
    name: NonBlankName


class RenameDraftRequest(BaseModel):
    title: NonBlankName


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


class ReconcileCharacterRequest(BaseModel):
    action: str


class EditCandidateRequest(BaseModel):
    payload: dict[str, object]


# 입력 ContextPackage 예산의 기본값(오너 지시 ④, 2026-07-28). 4096은 **동기 생성 시절 응답
# 속도** 때문에 고른 값이었고, 생성이 백그라운드 job + 푸시로 바뀌면서(v1.7.27) 그 제약이
# 사라졌다는 것이 오너의 근거다.
#
# **K-1(a)와 같이 올려야 하는 이유**: 회계가 `len/4`에서 `len/1.7`로 정직해지면서 같은 숫자가
# 뜻하는 실제 분량이 **절반**이 됐다(4096 회계 ≈ 실제 8,900 tok → ≈ 3,830 tok). 8192로 올리면
# 실효 분량이 종전과 비슷해지고(≈ 7,660 tok) 숫자는 정직해진다 — 즉 이 값은 확장이라기보다
# **회계 수정의 짝**이다.
#
# **★ 창 여유 — 이 값이 report 경로에 안전하다는 뜻은 아니다**(독립 검증 H1이 잡은 정정,
# 2026-07-30). 예산을 꽉 채운 프로젝트의 report 호출은 항목만이 아니라 **후보 산문까지** 싣는다.
# **2026-07-31 실측**(`scripts/report_budget_measure.py`, 베타 창 16384, 후보 = `long` 상한):
#
#   컨텍스트 8,358 + system 465 + 후보 산문 4,159 + 래퍼 94 + 출력 상한 6,144 = **19,220 > 16,384**
#
# 즉 창 16384에서 **2,836 넘는다**(종전 외삽치 −1,914보다 나쁘다 — 실제 렌더링이 외삽값보다
# 컸다). 후보 산문을 빼고 보면 "들어간다"로 오독하게 되는데, report는 그 산문을 대상으로 하는
# 호출이라 항상 함께 실린다. 통과하는 최대 예산은 실측 **5120**(여유 +386)이었다.
#
# **그래서 이 초과는 조용히 잘리지 않고 K-3 가드가 400으로 거부한다**(실측 delta 0: 가드가
# 보고한 input 13,076이 위 계산과 같다). 근본 해결은 **R-a**(report 전용 예산)이고, 형태와
# 숫자는 오너 결정 대기다(브리프 §2-5 — 상수 · 창에서 유도 · 출력 프리셋별의 세 갈래).
# 창 8192 배포에서는 더 일찍 걸리므로 알파는 `LLAMA_CTX_SIZE=16384`가 전제다(HANDOFF 함정).
# **이 경계는 예산을 꽉 채우는 프로젝트에서만 만난다** — 베타 프로브(회계 2,876)로는 닿지
# 않아 `--seed`가 그 재현 데이터를 만든다.
#
# 여섯 개 요청 모델이 같은 기본값을 쓴다. 리터럴을 복제하면 하나만 놓쳐도 endpoint마다 다른
# 예산이 되므로 상수로 둔다.
DEFAULT_CONTEXT_BUDGET_TOKENS = 8192

class ContextSearchHttpRequest(BaseModel):
    idempotency_key: str
    query: str
    needs: list[str]
    purpose: str = ContextSearchPurpose.WRITING_CONTEXT.value
    current_position: ContextPositionBody | None = None
    max_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS


class WritingGenerateRequest(BaseModel):
    request_id: str
    instruction: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    # Retrieval query for the internal context search; defaults to the instruction.
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31): 생성이 끝나면 같은 패키지로 self-report가 돌고 그쪽이 창을
    # 구속하므로, 이 값은 **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window (R-a); never increased. "
            "Distinct from output_length (output tokens)."
        ),
    )
    # 증분 2 (D3=A): output-length preset (short|medium|long). The server maps it
    # to output tokens (1024/2048/4096 by default). Distinct from ``max_tokens``,
    # which is the input ContextPackage budget. Legacy clients omit it → short.
    # `long` (4096) is single-generate only; it is not a knob on revise-and-gate.
    output_length: str = OutputLength.SHORT.value


class WritingGateRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    max_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS


class WritingReportRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31): 후보 산문을 곧바로 싣는 report 다리가 창을 구속하므로 이 값은
    # **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window alongside the candidate "
            "prose and report output (R-a); never increased."
        ),
    )


class WritingReviseFindingRequest(BaseModel):
    type: str
    severity: str
    message: str
    evidence: str
    recommended_decision: str


class WritingReviseRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    finding: WritingReviseFindingRequest
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31, v1.7.66): 루프의 report 다리(출력 상한 6144 + 후보 산문)가 창을
    # 구속하므로 이 값은 **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    # 진입 시 1회 유도하며 그 값이 패키지 예산과 merge 상한을 함께 묶는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it once at loop entry to fit the model's context window "
            "alongside the candidate prose and report output (R-a); never increased. "
            "The derived value also bounds package growth from retrieve_more merges."
        ),
    )
    # Phase 5.9 L9 B (P2=B opt-in, 2026-07-13): persist this loop's audit only
    # when requested. None → env default (WRITING_LOOP_AUDIT_DEFAULT, off).
    persist_audit: bool | None = None


class NextUnitBody(BaseModel):
    # W3 start_next_unit target (§3.1). unit_kind is validated at the endpoint
    # by converting to UnitKind. `goal` is a required-but-nullable key (W0 catalog
    # `nextUnitSpec`): the value is optional (null allowed), the key is not.
    # extra="forbid" matches the catalog's additionalProperties:false.
    model_config = ConfigDict(extra="forbid")
    title: str
    unit_kind: str
    goal: str | None


class ObservabilityKpiSitePayload(BaseModel):
    call_site: str
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    # The row count the token total was built from — ``provider_error`` rows are
    # excluded because their 0 means "unknown" (SoT v1.7.42).
    tokens_counted_from: int
    avg_latency_ms: int
    # Workflows this site served, and how many took more than one call. Not
    # named "repairs": a second row is a retry at a repair-shaped site but a
    # designed extra round inside the writing loop.
    correlations: int
    multi_call_correlations: int
    # K-3 창 헤드룸 경고(오너 2026-07-30): `창 − 입력 − 출력상한`이 창의 10% 미만인 호출 수와
    # **그 판정이 가능했던 행 수**(분모). 저장된 플래그가 아니라 원천 세 값에서 읽기 시점에
    # 파생한다(v1.7.59: 헤드룸은 저장하지 않는다). 분모가 함께 있어야 "빠듯한 호출이 없었다"와
    # "창을 아는 호출이 없었다"를 구분할 수 있다.
    thin_headroom_calls: int
    headroom_considered: int


class ObservabilityKpiTotalsPayload(BaseModel):
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    tokens_counted_from: int
    thin_headroom_calls: int
    headroom_considered: int


class ObservabilityKpiGatePayload(BaseModel):
    scored_calls: int
    # Null, not 0.0, when nothing carried a score (SoT v1.7.47 known gap: loop
    # gate calls have none).
    avg_quality_score: float | None


class ObservabilityKpiLoopPayload(BaseModel):
    runs_considered: int
    non_convergence_rate: float | None


class ObservabilityKpiResponse(BaseModel):
    project_id: str
    totals: ObservabilityKpiTotalsPayload
    # A list, not a map keyed by call_site: the literals grow (5→8 in 증분 C,
    # more with Phase 7) and keying by them would change the generated frontend
    # type on every new site (owner decision 2026-07-26, D2=A).
    sites: list[ObservabilityKpiSitePayload]
    gate: ObservabilityKpiGatePayload
    loop: ObservabilityKpiLoopPayload


class AdminObservabilityKpiResponse(BaseModel):
    # D8-5c. Same four sections as the per-project read-out, and deliberately a
    # separate model: the two differ in exactly one field, and merging them would
    # force ``project_id`` to be nullable on a payload where it is always present.
    #
    # ``projects_considered`` replaces it — how many projects contributed a
    # record. It is the project axis this fold would otherwise lose, reported the
    # way every other counter-intuitive number here is (with its denominator),
    # and it names no project: which projects exist is the admin projects slice.
    projects_considered: int
    totals: ObservabilityKpiTotalsPayload
    sites: list[ObservabilityKpiSitePayload]
    gate: ObservabilityKpiGatePayload
    loop: ObservabilityKpiLoopPayload


class WritingAcceptRequest(BaseModel):
    request_id: str
    draft_id: str
    base_version_id: str
    idempotency_key: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    output_type: str = WritingOutputType.DRAFT_PATCH.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31, v1.7.66): accept도 report 다리(reporter.enrich)를 지나므로 이 값은
    # **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다(후보 산문 추정 기반).
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window alongside the candidate "
            "prose and report output (R-a); never increased."
        ),
    )
    # W3 Writing intent (§3.1). Legacy clients omit both → append_current/null.
    intent: str = WritingIntent.APPEND_CURRENT.value
    next_unit: NextUnitBody | None = None


def build_async_generation_collaborators() -> GenerationCollaborators | None:
    """Assemble the env-configured collaborators the async generation worker
    (async-pad 증분 2b) drives, reusing the same factories create_app wires from.
    Returns ``None`` when the gateway is unconfigured (nothing to run).

    Kept next to create_app (not in the worker script) so all gateway/env wiring
    lives in one place; the worker imports just this one seam.
    """
    writing = _default_writing_service()
    if writing is None:
        return None
    core_sot = _default_core_sot_service()
    memory = _default_memory_service()
    analysis = _default_analysis_service(core_sot)
    # Same shared vector index / embeddings selection as create_app's non-inject
    # path: real Chroma when configured, else the in-memory fake.
    shared_embeddings = _build_embedding_provider()
    chroma_index = _build_chroma_vector_index()
    shared_vector_index = (
        chroma_index if chroma_index is not None else InMemoryVectorIndexAdapter()
    )
    context_search = _default_context_search_service(
        core_sot,
        vector_index=shared_vector_index,
        embeddings=shared_embeddings,
        memory=memory,
        analysis=analysis,
    )
    if context_search is None:
        return None
    return GenerationCollaborators(
        context_search=context_search,
        writing=writing,
        scratch=_default_writing_scratch_service(),
        jobs=_default_writing_generation_job_service(),
        needs=_WRITING_CONTINUE_SCENE_NEEDS,
        # Same factory create_app uses, so the worker's records land in the same
        # store the KPI aggregation reads (증분 C, D3).
        llm_call_audit=_default_llm_call_audit_service(),
        # R-a: 워커도 같은 유도를 쓴다. 워커에서 빠뜨리면 **제품의 주 경로만** 종전 예산으로
        # 남는다(생성은 HTTP가 아니라 이 워커가 돌린다).
        capabilities=_default_model_capabilities(),
        report_output_cap=_report_output_cap(),
    )


def create_app(
    service: CoreSotService | None = None,
    analysis_service: AnalysisService | None = None,
    analysis_runner: AnalysisJobRunner | None = None,
    memory_service: MemoryService | None = None,
    index_sync_outbox: IndexSyncOutboxService | None = None,
    context_search_service: ContextSearchService | None = None,
    compare_service: AnalysisCompareService | None = None,
    review_queue_service: ReviewQueueService | None = None,
    gate_finding_service: GateFindingService | None = None,
    writing_service: WritingService | None = None,
    writing_gate_service: WritingGateService | None = None,
    writing_report_service: WritingCandidateReportService | None = None,
    writing_revision_service: WritingRevisionService | None = None,
    writing_retrieval_planner: TerminalJsonWritingRetrievalPlanner | None = None,
    writing_loop_policy: WritingLoopPolicy | None = None,
    writing_loop_audit_service: WritingLoopAuditService | None = None,
    llm_call_audit_service: LlmCallAuditService | None = None,
    writing_scratch_service: WritingScratchService | None = None,
    writing_generation_job_service: WritingGenerationJobService | None = None,
    vector_index: InMemoryVectorIndexAdapter | None = None,
    user_service: UserService | None = None,
    session_service: SessionService | None = None,
    access_grant_service: AccessGrantService | None = None,
) -> FastAPI:
    # Fail startup loudly for invalid environment-adjustable public bounds.
    _project_brief_style_example_limits()
    _writing_output_length_tokens()
    app = FastAPI(title="AI Writing System Application")

    # SoT v1.7.38 (owner decision 2026-07-24): the storage face of 503 is closed
    # app-wide here rather than endpoint by endpoint. Every endpoint but /health
    # reaches Mongo, so a driver failure could leak an opaque 500 from any of the
    # 48 that had no 503 clause — H3 spent the whole phase defining exactly that
    # as a bug. One handler is also the only shape that cannot drift: a new
    # endpoint inherits the mapping instead of having to remember a clause.
    #
    # Endpoint-level clauses still win, because Starlette only consults a handler
    # for exceptions that escape the route. That ordering is what keeps
    # auto-promote's 503 *partial envelope* (v1.7.35 D1=B) intact instead of it
    # being flattened into the uniform body here.
    for _storage_error in _STORAGE_ERRORS:
        @app.exception_handler(_storage_error)
        async def _canonical_store_failed(_request, exc):
            return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(MemoryReindexEnqueueFailed)
    async def _reindex_enqueue_failed(_request, exc):
        # Also a storage failure, but deliberately not a pymongo type (it carries
        # the completed mint, see memory/service.py), so the loop above does not
        # cover it. Endpoints that report the mint catch it themselves; this is
        # the fallback for the ones that do not, without which that would be the
        # one storage path still leaking a 500.
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    core_sot = service or _default_core_sot_service()
    sync_outbox = index_sync_outbox or _default_index_sync_outbox_service()
    analysis = analysis_service or _default_analysis_service(
        core_sot, reindex_outbox=sync_outbox
    )
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
    # 2B.4 follow-up: review-only (conflict) proposals persist to a durable
    # review queue (docs/plans/02b-4-review-queue-persistence-decisions.md).
    review_queue = review_queue_service or _default_review_queue_service()
    apply_service = MemoryApplyService(
        memory_service=memory, review_queue=review_queue
    )
    # Phase 6 (v1.6.61): candidate review state transitions. confirm promotes and
    # de-indexes + resolves the conflict queue; reject de-indexes + dismisses. The
    # de-index rides the same shared index-sync outbox
    # (docs/plans/06-candidate-state-transition-decisions.md).
    candidate_review = CandidateReviewService(
        analysis_service=analysis,
        memory_service=memory,
        removal_outbox=sync_outbox,
        review_queue=review_queue,
    )
    character_reconciliation = CharacterReconciliationService(
        analysis_service=analysis, memory_service=memory,
        review_queue=review_queue, removal_outbox=sync_outbox,
    )
    review_inbox = ReviewInboxService(
        analysis_service=analysis, memory_service=memory,
        review_queue=review_queue,
    )
    gate_findings = gate_finding_service or _default_gate_finding_service()
    # Phase 5.9 L9 B: every bounded-loop termination is recorded to a durable,
    # append-only audit trail. Always available (in-memory default) so no loop
    # run goes unaudited (P2=A); a Mongo URI upgrades it to the durable adapter.
    writing_loop_audit = (
        writing_loop_audit_service or _default_writing_loop_audit_service()
    )
    # Observability KPI phase, 증분 4: the per-LLM-call audit trail the KPI
    # aggregation reads. Unlike the loop audit it is not opt-in — a KPI that only
    # counts when someone remembered to ask for it is not a measurement.
    llm_call_audit = llm_call_audit_service or _default_llm_call_audit_service()
    # Unaccepted-candidate recovery store (brief D0=B/D1=B/D2=A). Always
    # available (in-memory default) so generate can always leave a safety net.
    writing_scratch = (
        writing_scratch_service or _default_writing_scratch_service()
    )
    # Async generation job store (async-pad D3=B/D4=A). The generate endpoint
    # enqueues medium/long presets here (v1.7.27, 증분 2c); the worker
    # (scripts/generation_job_worker.py) claims and runs them. Always available
    # (in-memory default); a Mongo URI upgrades it to the durable adapter, which
    # the worker also uses so both sides see the same queue.
    writing_generation_jobs = (
        writing_generation_job_service or _default_writing_generation_job_service()
    )
    writing = writing_service or _default_writing_service()
    writing_gate = writing_gate_service or _default_writing_gate_service()
    # R-a (오너 2026-07-31): 창·토큰 계수는 **앱 수명 동안 한 번씩만** 묻는다. 여기서 만들어야
    # 캐시가 요청 간에 살아남는다 — 요청마다 만들면 매 요청에 왕복이 두 번 붙는다.
    model_capabilities = _default_model_capabilities()
    report_output_cap = _report_output_cap()
    writing_report = writing_report_service
    if writing_report is None and os.environ.get("LLM_GATEWAY_BASE_URL"):
        writing_report = _build_report_service(GatewayGenerateProvider(
            base_url=os.environ["LLM_GATEWAY_BASE_URL"],
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False)))
    writing_revision = writing_revision_service
    if writing_revision is None and os.environ.get("LLM_GATEWAY_BASE_URL"):
        writing_revision = _build_revise_service(GatewayGenerateProvider(
            base_url=os.environ["LLM_GATEWAY_BASE_URL"],
            timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
            trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False)))
    writing_accept = (
        WritingAcceptService(core_sot=core_sot, analysis=analysis,
                             gate=writing_gate, reporter=writing_report)
        if writing_gate is not None else None
    )
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
            memory=memory,
            analysis=analysis,
        )
    retrieval_planner = writing_retrieval_planner
    if retrieval_planner is None and os.environ.get("LLM_GATEWAY_BASE_URL"):
        retrieval_planner = _build_writing_retrieval_planner(
            GatewayGenerateProvider(
                base_url=os.environ["LLM_GATEWAY_BASE_URL"],
                timeout_seconds=_env_float("LLM_GATEWAY_TIMEOUT_SECONDS", 120.0),
                trust_env=_env_bool("LLM_GATEWAY_TRUST_ENV", False),
            )
        )
    writing_revise_gate = (
        WritingReviseGateService(
            reviser=writing_revision,
            reporter=writing_report,
            gate=writing_gate,
            retrieval_planner=retrieval_planner,
            context_search=context_search,
            policy=writing_loop_policy or WritingLoopPolicy(
                max_revision_rounds=_env_int(
                    "WRITING_LOOP_MAX_REVISION_ROUNDS", 2
                ),
                max_retrieval_rounds=_env_int(
                    "WRITING_LOOP_MAX_RETRIEVAL_ROUNDS", 1
                ),
                max_gate_evaluations=_env_int(
                    "WRITING_LOOP_MAX_GATE_EVALUATIONS", 3
                ),
                max_total_tokens=_env_opt_int("WRITING_LOOP_MAX_TOTAL_TOKENS"),
                max_wall_clock_ms=_env_opt_int(
                    "WRITING_LOOP_MAX_WALL_CLOCK_MS"
                ),
            ),
        )
        if (writing_revision is not None and writing_report is not None
            and writing_gate is not None) else None
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- Auth (multi-user D8) ---------------------------------------------
    # D8-3a: authentication is now enforced. Every operation except /health and
    # the three below declares ``dependencies=_REQUIRE_AUTH``, so a sessionless
    # request is 401 before the handler runs.
    #
    # The three exceptions each have a *stated* policy rather than an accident:
    #   /auth/login  — public: it is how a session is obtained.
    #   /auth/logout — public and idempotent: a client must always be able to
    #                  reach a known-logged-out state, including from a cookie
    #                  the server has already forgotten.
    #   /auth/me     — requires a session but answers 401 itself, because it is
    #                  the endpoint the frontend uses to *ask* whether it has one.
    #
    # Ownership (403) is enforced separately on every project-scoped route.
    users = user_service or _default_user_service()
    sessions = session_service or _default_session_service()
    access_grants = access_grant_service or _default_access_grant_service()
    # The module-level dependency reads them from here: it must be one function
    # object across all apps so the exhaustive guard has a single identity to
    # look for (see require_authenticated_user).
    app.state.users = users
    app.state.sessions = sessions
    app.state.core_sot = core_sot
    # require_project_owner reads this to honour a live grant (D8-5e, F1=C).
    app.state.access_grants = access_grants

    def _user_payload(user) -> dict[str, object]:
        return {
            "id": user.id, "username": user.username, "is_admin": user.is_admin
        }

    @app.post("/auth/login", response_model=LoginResponse, responses=_ERRORS_401)
    async def login(request: LoginRequest, response: Response) -> dict[str, object]:
        user = users.authenticate(
            username=request.username, password=request.password
        )
        if user is None:
            # One message for every failure mode (unknown user, wrong password,
            # disabled account). Distinguishing them here would undo the timing
            # hardening in UserService.authenticate.
            raise HTTPException(status_code=401, detail="invalid credentials")
        raw_token, session = sessions.create_session(user_id=user.id)
        max_age = int((session.expires_at - session.created_at).total_seconds())
        response.set_cookie(value=raw_token, **cookie_kwargs(max_age=max_age))
        return {"user": _user_payload(user)}

    @app.post("/auth/logout", response_model=LogoutResponse,
              responses=_ERRORS_LOGOUT)
    async def logout(request: Request, response: Response) -> dict[str, object]:
        # Idempotent by design: logging out without a session is not an error,
        # so a client can always reach a known-logged-out state.
        raw_token = request.cookies.get(SESSION_COOKIE_NAME)
        if raw_token:
            sessions.revoke(raw_token)
        response.delete_cookie(**cookie_kwargs())
        return {"ok": True}

    @app.get("/auth/me", response_model=UserPayload, responses=_ERRORS_401)
    async def read_current_user(request: Request) -> dict[str, object]:
        # Deliberately not `dependencies=_REQUIRE_AUTH`: this is the endpoint the
        # frontend calls to find out whether it has a session, so it must be able
        # to answer "no" as its own 401 rather than through a shared guard.
        user = current_user_or_none(request)
        if user is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        return _user_payload(user)

    # --- Admin (D8-5, D6=A minimal admin) ---------------------------------
    # Users only: the all-projects list and the global KPI are their own slices,
    # and project *content* stays behind the ownership boundary — an admin
    # reaches another user's project only through the audited, expiring grant
    # the owner chose in F1=C, which is a later slice too.
    def _admin_user_payload(user) -> dict[str, object]:
        return {
            "id": user.id, "username": user.username,
            "is_admin": user.is_admin, "is_active": user.is_active,
        }

    @app.get("/admin/users", response_model=AdminUserListResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def list_users() -> dict[str, object]:
        return {"users": [_admin_user_payload(u) for u in users.list_users()]}

    @app.post("/admin/users", response_model=AdminUserPayload,
              responses=_ERRORS_ADMIN_400_409, dependencies=_REQUIRE_ADMIN)
    async def create_user(request: CreateUserRequest) -> dict[str, object]:
        try:
            user = users.create_user(
                username=request.username,
                password=request.password,
                is_admin=request.is_admin,
            )
        except DuplicateUsername as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidUserInput as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _admin_user_payload(user)

    @app.post("/admin/users/{user_id}/deactivate",
              response_model=AdminUserPayload,
              responses=_ERRORS_ADMIN_404_409, dependencies=_REQUIRE_ADMIN)
    async def deactivate_user(user_id: str) -> dict[str, object]:
        try:
            user = users.deactivate_user(user_id)
        except UserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LastActiveAdmin as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _admin_user_payload(user)

    @app.get("/admin/observability/kpi",
             response_model=AdminObservabilityKpiResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def admin_observability_kpi_endpoint() -> dict[str, object]:
        # D8-5c: the deployment-wide read-out. Pure aggregation, like its
        # per-project sibling — no provider call, no scope. No 404: unlike the
        # project route there is nothing to look up, and no 403 for ownership
        # either, because it reads counts rather than any project's content.
        kpi = aggregate_global_kpi(
            calls=llm_call_audit.list_all_calls(),
            loop_runs=writing_loop_audit.list_all_runs(),
        )
        return {
            "projects_considered": kpi.projects_considered,
            "totals": asdict(kpi.totals),
            "sites": [asdict(site) for site in kpi.sites],
            "gate": asdict(kpi.gate),
            "loop": asdict(kpi.loop),
        }

    def _project_payload(project) -> dict[str, object]:
        return {"id": project.id, "name": project.name, "archived": project.archived}

    def _project_brief_payload(brief) -> dict[str, object]:
        return {
            "id": brief.id,
            "project_id": brief.project_id,
            "version_number": brief.version_number,
            "premise": brief.premise,
            "genre": brief.genre,
            "tone": brief.tone,
            "pov": brief.pov,
            "constraints": list(brief.constraints),
            "style_rules": list(brief.style_rules),
            "preferred_patterns": list(brief.preferred_patterns),
            "forbidden_patterns": list(brief.forbidden_patterns),
            "style_examples": list(brief.style_examples),
        }

    def _draft_payload(draft) -> dict[str, object]:
        assert draft.unit_kind is not None
        assert draft.position is not None
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "title": draft.title,
            "archived": draft.archived,
            "unit_kind": draft.unit_kind,
            "position": draft.position,
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

    @app.post("/projects", response_model=ProjectPayload,
              responses=_ERRORS_STORAGE,
              dependencies=_REQUIRE_AUTH)
    async def create_project(
        request: CreateProjectRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # D8-3a: the creator is no longer optional. The same dependency the
        # decorator declares is taken as a parameter here so the owner comes from
        # the value the guard already resolved — re-reading the cookie would be a
        # second, driftable answer to "who is this".
        #
        # `owner_id=None` therefore stops being reachable through this endpoint.
        # It stays deny-by-default in D8-3b anyway (E1=A): rows with no owner can
        # still arrive from a deletion bug or a future migration.
        project = core_sot.create_project(name=request.name, owner_id=current.id)
        return _project_payload(project)

    @app.get("/projects", response_model=ProjectListResponse,
             responses=_ERRORS_STORAGE,
             dependencies=_REQUIRE_AUTH)
    async def list_projects(
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        projects = core_sot.list_projects_for_owner(owner_id=current.id)
        return {"projects": [_project_payload(p) for p in projects]}

    @app.get("/projects/{project_id}", response_model=ProjectPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_project(project_id: str) -> dict[str, object]:
        try:
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _project_payload(project)

    @app.get(
        "/projects/{project_id}/brief", response_model=ProjectBriefGetResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_project_brief(project_id: str) -> dict[str, object]:
        try:
            brief = core_sot.get_project_brief(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "brief": _project_brief_payload(brief) if brief is not None else None
        }

    @app.put(
        "/projects/{project_id}/brief", response_model=ProjectBriefPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_project_brief(
        project_id: str, request: PutProjectBriefRequest
    ) -> dict[str, object]:
        try:
            result = core_sot.put_project_brief(
                project_id=project_id,
                base_version_id=request.base_version_id,
                idempotency_key=request.idempotency_key,
                premise=request.premise,
                genre=request.genre,
                tone=request.tone,
                pov=request.pov,
                constraints=tuple(request.constraints),
                style_rules=tuple(request.style_rules),
                preferred_patterns=tuple(request.preferred_patterns),
                forbidden_patterns=tuple(request.forbidden_patterns),
                style_examples=tuple(request.style_examples),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, StaleProjectBriefBase) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "brief": _project_brief_payload(result.brief),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.get(
        "/projects/{project_id}/brief/versions",
        response_model=ProjectBriefVersionListResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_project_brief_versions(project_id: str) -> dict[str, object]:
        try:
            versions = core_sot.list_project_brief_versions(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"versions": [_project_brief_payload(brief) for brief in versions]}

    @app.get(
        "/projects/{project_id}/brief/versions/{version_id}",
        response_model=ProjectBriefGetResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_project_brief_version(
        project_id: str, version_id: str
    ) -> dict[str, object]:
        try:
            brief = core_sot.get_project_brief_version(
                project_id=project_id, version_id=version_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"brief": _project_brief_payload(brief)}

    @app.patch("/projects/{project_id}", response_model=ProjectPayload,
               responses=_owned(_ERRORS_404_409),
               dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.patch(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
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

    @app.delete("/projects/{project_id}", response_model=ProjectPayload,
                responses=_owned(_ERRORS_404),
                dependencies=_REQUIRE_PROJECT_OWNER)
    async def archive_project(project_id: str) -> dict[str, object]:
        # MVP: delete is archive (soft delete); SOT data is preserved (§115).
        # Re-archiving is idempotent.
        try:
            project = core_sot.archive_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        sync_outbox.enqueue_project_archived(project_id=project_id)
        return _project_payload(project)

    @app.post("/admin/projects/{project_id}/access-grants",
              response_model=AccessGrantCreateResponse, status_code=201,
              responses=_ERRORS_ADMIN_404, dependencies=_REQUIRE_ADMIN)
    async def issue_access_grant(
        project_id: str, request: AccessGrantCreateRequest,
        current=Depends(require_admin_user),
    ) -> dict[str, object]:
        # D8-5e (F1=C, owner 2026-08-02). Ownership refuses administrators too;
        # this is the audited, expiring way past it. It sits in the ADMIN tier
        # for the same reason purge does — the path names a project but the
        # check is "are you an administrator", not "do you own this".
        #
        # 404 before issuing: a grant to a project that does not exist would be
        # an audit record about nothing, and it would let an administrator probe
        # for project ids through a 201.
        try:
            core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        grant = access_grants.issue(
            admin_user_id=current.id,
            project_id=project_id,
            reason=request.reason,
        )
        return {"grant": {
            "id": grant.id,
            "project_id": grant.project_id,
            "admin_user_id": grant.admin_user_id,
            "reason": grant.reason,
            "created_at": grant.created_at,
            "expires_at": grant.expires_at,
        }}

    @app.post("/admin/projects/{project_id}/purge", status_code=204,
              response_model=None, responses=_ERRORS_ADMIN_404,
              dependencies=_REQUIRE_ADMIN)
    async def purge_project(project_id: str) -> None:
        # D8-6d: 영구 파기(불가역). archive(soft)와 달리 18컬렉션을 hard delete 하고
        # indexing outbox 로 worker 가 vector/index 5백엔드를 파기(6c _drain_purge).
        # D5 전체 그래프 파기. 응답은 204(리소스 소멸). core_sot 파기(8컬렉션, mongo
        # 트랜잭션)가 NotFound 면 404.
        #
        # ★ 알려진 한계 — **재시도는 멱등이 아니다**(2026-08-02 정정. v1.7.74 는 이 자리에
        # "클라이언트 재시도(멱등)"라고 적었으나 거짓이었다). core_sot 이 **먼저** 지워지므로,
        # 아래 derived 단계에서 mongo 장애가 나 전역 handler 가 503 을 내면 **수습할 방법이
        # 없다**: 재시도는 core_sot 이 비어 404 로 끝나고 derived 에 도달하지 못한다. 남는
        # derived 는 무해하지 않다 — llm_call_audits 에 프롬프트 본문이, scratch 에 원고
        # 후보가 남는다(D5 부분 삭제 금지 위반). **수습은 `scripts/purge_reconciler.py`**
        # 가 한다(projects 에 없는 project_id 의 잔류를 찾아 파기 + PROJECT_PURGED enqueue).
        # 이 순서를 바꿀지(재시도 가능하게) 는 오너 결정 사안이다 — HANDOFF "Owner Decisions".
        # 한계 자체는 AdminProjectPurgeTest 의
        # test_a_second_purge_is_404_and_never_reaches_the_derived_services 가 잠근다.
        try:
            core_sot.purge_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        memory.purge_project(project_id=project_id)
        analysis.purge_project(project_id=project_id)
        review_queue.purge_project(project_id=project_id)
        gate_findings.purge_project(project_id=project_id)
        writing_generation_jobs.purge_project(project_id=project_id)
        writing_scratch.purge_project(project_id=project_id)
        writing_loop_audit.purge_project(project_id=project_id)
        llm_call_audit.purge_project(project_id=project_id)
        # D8-5e: access grants are project-scoped too (they carry the project id
        # and the reason an admin looked at it). Leaving them behind would be the
        # silent orphan D5 forbids — append-only is a rule about *expiry*, not
        # about surviving the project's destruction.
        access_grants.purge_project(project_id=project_id)
        sync_outbox.enqueue_project_purged(project_id=project_id)
        return None

    @app.delete(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
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

    @app.get("/projects/{project_id}/drafts", response_model=DraftListResponse,
             responses=_owned(_ERRORS_404_MIGRATION),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_drafts(project_id: str) -> dict[str, object]:
        try:
            drafts = core_sot.list_drafts(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Stored drafts predate the W3 ordered-unit invariant (or are corrupt).
            # The fix is the one-shot scripts/migrate_ordered_units.py, not a
            # corrected request, so surface a 503 instead of leaking an opaque 500.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"drafts": [_draft_payload(d) for d in drafts]}

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.get_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions",
        response_model=DraftVersionListResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_draft_versions(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            versions = core_sot.list_draft_versions(
                project_id=project_id, draft_id=draft_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"versions": [_version_meta_payload(v) for v in versions]}

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions/{version_id}",
        response_model=DraftVersionDetailResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
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
        "/projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export",
        response_model=DraftVersionExportResponse,
        responses=_owned(_ERRORS_400_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
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

    @app.get(
        "/projects/{project_id}/export",
        response_model=ProjectExportResponse,
        responses=_owned(_ERRORS_400_404_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def export_project(
        project_id: str,
        format: str = Query("txt"),
        manifest: bool = Query(False),
        include_archived: bool = Query(False),
    ) -> dict[str, object]:
        try:
            export = core_sot.export_project(
                project_id=project_id,
                fmt=format,
                include_archived=include_archived,
            )
        except UnsupportedExportFormat as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Whole-project export reads the ordered unit set; unmigrated legacy
            # data blocks it. Same migration-required 503 as list/create.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        manifest_payload: dict[str, object] | None = None
        if manifest:
            manifest_payload = {
                "project_id": export.project_id,
                "format": export.format,
                "include_archived": export.include_archived,
                "units": [
                    {
                        "draft_id": unit.draft_id,
                        "title": unit.title,
                        "unit_kind": unit.unit_kind,
                        "position": unit.position,
                        "version_id": unit.version_id,
                        "version_number": unit.version_number,
                        "snapshot_id": unit.snapshot_id,
                        "content_hash": unit.content_hash,
                    }
                    for unit in export.units
                ],
            }
        return {
            "format": export.format,
            "filename": export.filename,
            "content_type": export.content_type,
            "body": export.body,
            "project_id": export.project_id,
            "include_archived": export.include_archived,
            "manifest": manifest_payload,
        }

    @app.post("/projects/{project_id}/drafts", response_model=DraftPayload,
              responses=_owned(_ERRORS_404_409_MIGRATION),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def create_draft(
        project_id: str, request: CreateDraftRequest
    ) -> dict[str, object]:
        try:
            draft = core_sot.create_draft(
                project_id=project_id,
                title=request.title,
                unit_kind=request.unit_kind,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Appending a unit reads the existing ordered set; unmigrated legacy
            # data blocks it. Same migration-required 503 as list/export.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.put(
        "/projects/{project_id}/draft-order",
        response_model=DraftOrderPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_draft_order(
        project_id: str, request: DraftOrderPutRequest
    ) -> dict[str, object]:
        try:
            drafts = core_sot.reorder_drafts(
                project_id=project_id,
                ordered_draft_ids=tuple(request.ordered_draft_ids),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, InvalidDraftOrder) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"drafts": [_draft_payload(draft) for draft in drafts]}

    @app.post(
        "/projects/{project_id}/drafts/{draft_id}/versions",
        response_model=SaveDraftResponse,
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
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

    @app.post("/projects/{project_id}/snapshots/{snapshot_id}/source-refs",
              responses=_owned(_ERRORS_400_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.get("/projects/{project_id}/snapshots/{snapshot_id}/source-refs",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.get("/projects/{project_id}/source-refs/{source_ref_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.post(
        "/projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild",
        responses=_owned(_ERRORS_404_502),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
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
        except EmbeddingProviderError as exc:
            # The rebuild embeds every source block, so a configured-but-failing
            # embedding service (timeout / unreachable / malformed response) used
            # to escape as an opaque 500. It is an upstream collaborator failure,
            # not a missing one, so it is 502 rather than 503 — the same call this
            # endpoint's sibling already makes: context search's vector step maps
            # an embedding failure to BACKEND_ERROR, which surfaces as 502
            # (context_search/service.py::_run_vector_step).
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/analysis/jobs", responses=_owned(_ERRORS_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.get_job(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _analysis_job_payload(job)

    @app.get("/projects/{project_id}/analysis/jobs/{job_id}/candidates",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/retry",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def retry_analysis_job(project_id: str, job_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            job = analysis.retry_failed_job(project_id=project_id, job_id=job_id)
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidJobStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _analysis_job_payload(job)

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/run",
              responses=_owned(_ERRORS_400_404_409_502_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
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
            # Observability seam C: the extractor's provider is wrapped, so the
            # repair retry (extractor.py `_repair_once`) lands as its own record
            # instead of hiding behind this one endpoint call. correlation_id is
            # the job — every call made while running it belongs together.
            with llm_call_scope(llm_call_audit, project_id=project_id,
                                correlation_id=job_id):
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
        except ProviderError as exc:
            # A Gateway/provider failure (timeout/unavailable/5xx) re-raised by
            # the runner after it marks the job failed(provider_error) is an LLM
            # error → 502, mirroring the compare endpoint's explicit branch. The
            # generic catch below also maps to 502; this explicit branch keeps
            # the intent legible and refactor-safe. (It must precede the generic
            # ``except Exception`` catch; the 400/404/409 mappings above are for
            # unrelated types, so their order is unaffected.)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except _STORAGE_ERRORS as exc:
            # SoT v1.7.40 D2=A (owner decision 2026-07-24): a canonical store
            # failure — from the project-exists gate, get_job, list_candidates, or
            # a store write inside the runner — is not an upstream/LLM failure, so
            # it is the store face of 503, not the 502 the generic catch below
            # assigns. The 503 declaration already names this face (``_CONFIG_503``
            # is wrapped with ``_with_storage_note``), so the declaration is
            # unchanged; this branch is what makes the runtime match it and closes
            # the precision gap v1.7.39 had to record as a pre-existing exception.
            # It must precede the generic ``except Exception`` so the store failure
            # is not swallowed into 502.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _analysis_run_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/promote",
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
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

    def _candidate_review_payload(result) -> dict[str, object]:
        return {
            "candidate_id": result.candidate_id,
            "status": str(result.status),
            "memory_id": result.memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    def _candidate_edit_payload(result) -> dict[str, object]:
        return {
            "original_candidate_id": result.original_candidate_id,
            "candidate_id": result.candidate_id,
            "status": str(result.status),
            "memory_id": result.memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/confirm",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def confirm_candidate(
        project_id: str, candidate_id: str
    ) -> dict[str, object]:
        # Phase 6 (v1.6.61): approve → confirmed + promotion + de-index + resolve.
        try:
            _require_project_exists(project_id)
            result = candidate_review.confirm(
                project_id=project_id, candidate_id=candidate_id
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _candidate_review_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/reject",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def reject_candidate(
        project_id: str, candidate_id: str
    ) -> dict[str, object]:
        # Phase 6 (v1.6.61): reject → rejected (no promotion) + de-index + dismiss.
        try:
            _require_project_exists(project_id)
            result = candidate_review.reject(
                project_id=project_id, candidate_id=candidate_id
            )
        except (AnalysisNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _candidate_review_payload(result)

    @app.post(
        "/projects/{project_id}/analysis/candidates/{candidate_id}/edit",
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def edit_candidate(
        project_id: str, candidate_id: str, body: EditCandidateRequest
    ) -> dict[str, object]:
        # Phase 6 (v1.6.66): edit → new confirmed candidate version + promotion +
        # de-index of the superseded original + resolve. The edited payload is
        # revalidated against the candidate_type schema (invalid → 400); editing a
        # non-needs_review candidate is a 409.
        try:
            _require_project_exists(project_id)
            result = candidate_review.edit(
                project_id=project_id,
                candidate_id=candidate_id,
                payload=body.payload,
            )
        except (AnalysisNotFound, MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidCandidateStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnalysisCandidate as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _candidate_edit_payload(result)

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/auto-promote",
              responses=_owned(_ERRORS_404_STORAGE),
              dependencies=_REQUIRE_PROJECT_OWNER)
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
            try:
                result = memory.auto_promote_candidate(
                    project_id=project_id, candidate=candidate
                )
            except MemoryNotFound as exc:
                # SoT v1.7.35 D3. Defensive: promote_candidate raises this on a
                # project mismatch, which cannot happen here because `candidates`
                # came from list_candidates(project_id=...). Mapped anyway so the
                # branch cannot leak a 500, and mapped to 404 like the sibling
                # manual promote endpoint. It precedes any write for this
                # candidate, so no mint of this iteration is lost.
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except MemoryReindexEnqueueFailed as exc:
                # SoT v1.7.36. A promotion is two writes — the mint, then the
                # reindex outbox — and only the second failed here, so *this*
                # candidate is durably stored too. Reporting it in ``promoted``
                # is what keeps the envelope's promise that the response agrees
                # with the stored state; dropping it (v1.7.35 did) understated the
                # mints by one and made the SoT claim false in this mode.
                promoted.append(_memory_payload(exc.result.memory))
                return JSONResponse(status_code=503, content={
                    "auto_promotion_threshold": memory.auto_promotion_threshold,
                    "promoted": promoted,
                    "promotion_error": str(exc),
                })
            except _STORAGE_ERRORS as exc:
                # SoT v1.7.35 D1=B/D2=A. The loop writes once per candidate with
                # no transaction spanning them, so a store failure at candidate N
                # leaves N-1 canonical mints already durable. They are append-only
                # and are not rolled back, so returning a bare error body would
                # make the response disagree with the stored state — report what
                # this call minted alongside the failure instead.
                #
                # The message names the stage (brief Follow-up #2): reaching here
                # means the mint itself did not happen, which is what tells an
                # operator that ``promoted`` is complete as reported.
                return JSONResponse(status_code=503, content={
                    "auto_promotion_threshold": memory.auto_promotion_threshold,
                    "promoted": promoted,
                    "promotion_error": (
                        f"canonical store failure — this candidate was not minted "
                        f"by this call: {exc}"
                    ),
                })
            if result is not None and not result.idempotent_replay:
                promoted.append(_memory_payload(result.memory))
        return {
            "auto_promotion_threshold": memory.auto_promotion_threshold,
            "promoted": promoted,
        }

    @app.get("/projects/{project_id}/memory", responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.get("/projects/{project_id}/memory/{memory_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/context",
              responses=_owned(_ERRORS_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/compare",
              responses=_owned(_ERRORS_404_502_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
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
        # Observability seam C (증분 C): one record per judge turn. The scope
        # ties a job's whole compare run together — N matched pairs leave N
        # rows under this one correlation_id, plus a repair row where the first
        # verdict was not JSON. Deterministic proposals (no match / duplicate)
        # call no provider and so leave nothing, without special handling.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=job.id) as scope:
            try:
                proposals = await compare.compare_job(
                    project_id=project_id, job_id=job.id, candidates=candidates
                )
            except CompareJudgeNotConfigured as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except InvalidJudgeResult as exc:
                # The judge answered and repair still failed to parse — the
                # domain's final rejection of that last answer (owner decision
                # 2026-07-26, D4). Recovered first attempts keep ``success``:
                # only the last call is touched, so the repair-frequency signal
                # (two rows under one correlation_id) stays intact.
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ProviderError as exc:
                # A Gateway/provider failure during the matched-pair judge turn
                # (timeout/unavailable/5xx) is an LLM error → 502, applying the
                # v1.6.34 error taxonomy to this endpoint. Without this the
                # ProviderError raised by GatewayGenerateProvider propagates as an
                # unhandled 500. Already recorded by the decorator with its
                # taxonomy intact. 창 가드 거부만 4xx로 갈라진다(K-3).
                raise HTTPException(status_code=_provider_error_status(exc),
                                    detail=str(exc)) from exc
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

    def _review_queue_entry_payload(entry) -> dict[str, object]:
        return {
            "id": entry.id,
            "job_id": entry.job_id,
            "candidate_id": entry.candidate_id,
            "candidate_type": entry.candidate_type.value,
            "action": entry.action.value,
            "matched_memory_id": entry.matched_memory_id,
            "rationale": entry.rationale,
            "status": entry.status.value,
        }

    @app.post("/projects/{project_id}/analysis/jobs/{job_id}/apply",
              responses=_owned(_ERRORS_400_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
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

    @app.get("/projects/{project_id}/analysis/review-queue",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def analysis_review_queue_endpoint(project_id: str) -> dict[str, object]:
        # 2B.4 follow-up: list the project's open review-only (conflict) entries
        # persisted by apply, so an unresolved conflict is observable/reconcilable
        # (docs/plans/02b-4-review-queue-persistence-decisions.md, D2).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        entries = review_queue.list_open(project_id)
        return {
            "project_id": project_id,
            "entries": [_review_queue_entry_payload(e) for e in entries],
        }

    @app.post(
        "/projects/{project_id}/analysis/review-queue/{entry_id}/reconcile",
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def reconcile_character_conflict(
        project_id: str, entry_id: str, request: ReconcileCharacterRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            action = ReconciliationAction(request.action)
            result = character_reconciliation.reconcile(
                project_id=project_id, entry_id=entry_id, action=action
            )
        except (NotFound, AnalysisNotFound, MemoryNotFound, KeyError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (MemoryError, InvalidCandidateStateTransition) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "entry_id": result.entry_id,
            "action": result.action.value,
            "memory_id": result.memory_id,
            "superseded_memory_id": result.superseded_memory_id,
            "idempotent_replay": result.idempotent_replay,
        }

    def _review_source_pointer(project_id: str, source_ref_id: str) -> dict[str, object]:
        try:
            ref = core_sot.get_source_ref(
                project_id=project_id, source_ref_id=source_ref_id
            )
        except NotFound:
            return {"source_ref_id": source_ref_id, "status": "missing"}
        return {
            "source_ref_id": ref.id,
            "status": "resolved",
            "snapshot_id": ref.snapshot_id,
            "block_id": ref.block_id,
            "start_offset": ref.start_offset,
            "end_offset": ref.end_offset,
            "quote": ref.quote,
            "content_hash": ref.content_hash,
        }

    def _affordance_payload(affordance) -> dict[str, object]:
        return {
            "action": affordance.action,
            "eligible": affordance.eligible,
            "reason": affordance.reason,
        }

    def _review_inbox_payload(item, *, include_detail: bool) -> dict[str, object]:
        candidate = item.candidate
        payload: dict[str, object] = {
            "candidate_id": candidate.id,
            "job_id": candidate.job_id,
            "candidate_type": candidate.candidate_type.value,
            "status": candidate.status.value,
            "confidence": candidate.confidence,
            "provenance": candidate.provenance.value,
            "conflict_count": len(item.conflicts),
            # v1.6.67: available review actions per item (list + detail, D3).
            "actions": [
                _affordance_payload(a) for a in candidate_affordances()
            ],
        }
        if include_detail:
            payload.update({
                "payload": dict(candidate.payload),
                "source_refs": [
                    _review_source_pointer(candidate.project_id, source_ref_id)
                    for source_ref_id in candidate.source_ref_ids
                ],
                "conflicts": [
                    {
                        "entry_id": conflict.entry.id,
                        "action": conflict.entry.action.value,
                        "rationale": conflict.entry.rationale,
                        "matched_memory": (
                            _memory_payload(conflict.matched_memory)
                            if conflict.matched_memory is not None else None
                        ),
                        "diff": [
                            {"field": diff.field, "before": diff.before,
                             "after": diff.after}
                            for diff in conflict.diff
                        ],
                        "actions": [
                            _affordance_payload(a)
                            for a in conflict_affordances(conflict)
                        ],
                    }
                    for conflict in item.conflicts
                ],
            })
        return payload

    @app.get("/projects/{project_id}/analysis/review-inbox",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_review_inbox(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "project_id": project_id,
            "items": [
                _review_inbox_payload(item, include_detail=False)
                for item in review_inbox.list_items(project_id=project_id)
            ],
            "gate_findings": [
                _gate_finding_payload(finding)
                for finding in gate_findings.list_open(project_id)
            ],
        }

    @app.get("/projects/{project_id}/analysis/review-inbox/{candidate_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_review_inbox_item(
        project_id: str, candidate_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            item = review_inbox.get_item(
                project_id=project_id, candidate_id=candidate_id
            )
        except (NotFound, ReviewInboxNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _review_inbox_payload(item, include_detail=True)

    def _gate_finding_payload(finding) -> dict[str, object]:
        return {
            "id": finding.id, "origin": "context_gate",
            "status": finding.status.value, "check": finding.check,
            "detail": finding.detail, "query": finding.query,
            "purpose": finding.purpose, "needs": list(finding.needs),
            "pointer_ids": list(finding.pointer_ids),
            "request_fingerprint": finding.request_fingerprint,
            "result_fingerprint": finding.result_fingerprint,
            "created_at": finding.created_at.isoformat(),
            "terminal_at": (
                finding.terminal_at.isoformat()
                if finding.terminal_at is not None else None
            ),
            "actions": [
                _affordance_payload(a)
                for a in gate_finding_affordances(
                    is_open=finding.status is GateFindingStatus.OPEN
                )
            ],
        }

    @app.get("/projects/{project_id}/analysis/gate-findings",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_gate_findings(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"project_id": project_id, "gate_findings": [
            _gate_finding_payload(finding)
            for finding in gate_findings.list_open(project_id)
        ]}

    @app.get("/projects/{project_id}/analysis/gate-findings/{finding_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_gate_finding(project_id: str, finding_id: str):
        try:
            _require_project_exists(project_id)
            finding = gate_findings.get(
                project_id=project_id, finding_id=finding_id
            )
        except (NotFound, GateFindingNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _gate_finding_payload(finding)

    async def _transition_gate_finding(
        project_id: str, finding_id: str, target: GateFindingStatus
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            finding, replay = gate_findings.transition(
                project_id=project_id, finding_id=finding_id, target=target
            )
        except (NotFound, GateFindingNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidGateFindingTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"finding": _gate_finding_payload(finding),
                "idempotent_replay": replay}

    @app.post("/projects/{project_id}/analysis/gate-findings/{finding_id}/resolve",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def resolve_gate_finding(project_id: str, finding_id: str):
        return await _transition_gate_finding(
            project_id, finding_id, GateFindingStatus.RESOLVED
        )

    @app.post("/projects/{project_id}/analysis/gate-findings/{finding_id}/dismiss",
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def dismiss_gate_finding(project_id: str, finding_id: str):
        return await _transition_gate_finding(
            project_id, finding_id, GateFindingStatus.DISMISSED
        )

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
            "review_status": item.review_status,
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
                "project_brief": (
                    _project_brief_payload(package.project_brief)
                    if package.project_brief is not None
                    else None
                ),
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

    @app.post("/projects/{project_id}/context-search",
              responses=_owned(_ERRORS_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
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
        # Observability seam C (증분 C): the query planner's calls (one, or two
        # when the first plan is not JSON). ``idempotency_key`` is this
        # endpoint's workflow tie — it is what the caller retries under.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.idempotency_key) as scope:
            try:
                package = await context_search.build_context_package(request)
                gate = evaluate_context_gate(
                    package=package,
                    request=request,
                    core_sot=core_sot,
                    memory_service=memory,
                    analysis_service=analysis,
                )
                try:
                    gate_findings.persist_rejection(
                        request=request, idempotency_key=body.idempotency_key,
                        package=package, gate=gate,
                    )
                except _STORAGE_ERRORS:
                    # SoT v1.7.40 D2=A (owner decision 2026-07-24): a canonical store
                    # failure while persisting the gate rejection is the store face of
                    # 503, not the upstream 502 the ``GateFindingError`` wrap below
                    # assigns. Re-raise it unwrapped so it escapes both this try and
                    # the outer one (no outer clause matches a pymongo type) to the
                    # global handler → 503, matching run and every other storage path.
                    # Non-pymongo persistence failures still become GateFindingError →
                    # 502 (over-strict guard: an operational persist bug is not a store
                    # outage). Empty ``_STORAGE_ERRORS`` (no driver) catches nothing.
                    raise
                except Exception as exc:
                    raise GateFindingError(str(exc)) from exc
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except GateFindingError as exc:
                raise HTTPException(
                    status_code=502, detail=f"gate finding persistence failed: {exc}"
                ) from exc
        return _context_package_payload(package, gate)

    def _writing_candidate_payload(candidate) -> dict[str, object]:
        return {
            "request_id": candidate.request_id,
            "project_id": candidate.project_id,
            "task_type": candidate.task_type.value,
            "output_type": candidate.output_type.value,
            "text": candidate.text,
            "status": candidate.status,
            "self_reported_constraints": list(candidate.self_reported_constraints),
            "candidate_claims": [
                {"text": x.text, "type": x.claim_type.value,
                 "requires_gate_check": x.requires_gate_check,
                 "related_context_pointers": [
                     pointer_wire(p) for p in x.related_context_pointers]}
                for x in candidate.candidate_claims],
            "new_memory_hints": [
                {"type": x.hint_type.value, "text": x.text,
                 "confidence": x.confidence,
                 "should_analyze_after_save": x.should_analyze_after_save}
                for x in candidate.new_memory_hints],
            "risk_notes": [
                {"type": x.risk_type.value, "severity": x.severity.value,
                 "message": x.message} for x in candidate.risk_notes],
            "candidate_id": candidate.candidate_id,
            "generated_by_model": candidate.generated_by_model,
        }

    def _writing_generation_job_payload(job) -> dict[str, object]:
        # Async generation job status (async-pad D5=A, v1.7.27 = 증분 2c). Used by
        # GET .../writing/generation-jobs/{job_id} (validated through
        # WritingGenerationJobPayload) and nested under ``job`` in the 202 envelope
        # the generate endpoint returns for medium/long presets. The terminal
        # fields (result_scratch_id / failure_reason / failure_detail) are None
        # until the worker reaches a terminal state.
        return {
            "job_id": job.id,
            "request_id": job.request_id,
            "project_id": job.project_id,
            "draft_id": job.draft_id,
            "version_id": job.version_id,
            "task_type": job.task_type,
            "output_length": job.output_length,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "result_scratch_id": job.result_scratch_id,
            "failure_reason": (
                job.failure_reason.value if job.failure_reason is not None else None
            ),
            "failure_detail": job.failure_detail,
        }

    def _writing_gate_payload(result) -> dict[str, object]:
        return {
            "request_id": result.request_id,
            "project_id": result.project_id,
            "decision": result.decision.value,
            "findings": [{
                "type": item.finding_type.value,
                "severity": item.severity.value,
                "message": item.message,
                "evidence": item.evidence,
                "recommended_decision": item.recommended_decision.value,
            } for item in result.findings],
            "checked_constraints": list(result.checked_constraints),
            "evaluated_by_model": result.evaluated_by_model,
        }

    def _writing_loop_payload(loop) -> dict[str, object]:
        return {
            "status": loop.status.value,
            "revision_rounds": loop.revision_rounds,
            "retrieval_rounds": loop.retrieval_rounds,
            "gate_evaluations": loop.gate_evaluations,
        }

    def _writing_stages_payload(stages) -> list[dict[str, object]]:
        return [{
            "stage": item.stage.value,
            "ordinal": item.ordinal,
            "status": item.status.value,
        } for item in stages]

    def _writing_loop_audit_summary_payload(run) -> dict[str, object]:
        return {
            "audit_id": run.id,
            "request_id": run.request_id,
            "loop_status": run.loop_status,
            "error_type": run.error_type,
            "revision_rounds": run.revision_rounds,
            "retrieval_rounds": run.retrieval_rounds,
            "gate_evaluations": run.gate_evaluations,
            # Phase 5.10 ("B2") aggregate metering — bodyless run-level metric,
            # exposed only on the persisted audit (M5=A), never on the ephemeral
            # loop response.
            "total_tokens": run.total_tokens,
            "wall_clock_ms": run.wall_clock_ms,
            "created_at": run.created_at.isoformat(),
        }

    def _writing_loop_audit_payload(run) -> dict[str, object]:
        return {
            **_writing_loop_audit_summary_payload(run),
            "trigger_finding_fingerprint": run.trigger_finding_fingerprint,
            "initial_candidate_hash": run.initial_candidate_hash,
            "final_candidate_hash": run.final_candidate_hash,
            "final_candidate_text": run.final_candidate_text,
            "final_gate_decision": run.final_gate_decision,
            "final_gate_finding_fingerprints": list(
                run.final_gate_finding_fingerprints
            ),
            "stages": [{
                "stage": stage.stage, "ordinal": stage.ordinal,
                "status": stage.status,
                "candidate_hash": stage.candidate_hash,
                "finding_fingerprint": stage.finding_fingerprint,
                "pointer_ids": list(stage.pointer_ids),
            } for stage in run.stages],
        }

    def _accepted_save_payload(saved, target_draft) -> dict[str, object]:
        return {
            "draft_id": saved.draft_version.draft_id,
            "draft_version_id": saved.draft_version.id,
            "version_number": saved.draft_version.version_number,
            "snapshot_id": saved.snapshot.id,
            "content_hash": saved.snapshot.content_hash,
            "unit_kind": target_draft.unit_kind.value,
            "position": target_draft.position,
        }

    @app.post("/projects/{project_id}/writing/generate",
              response_model=WritingCandidatePayload,
              responses=_owned({**GENERATE_ASYNC_RESPONSES,
                                **_ERRORS_400_404_502_504_CONFIG}),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_generate_endpoint(
        project_id: str, body: WritingGenerateRequest
    ) -> dict[str, object]:
        # Phase 5.1: continue_scene generation. The intended flow is
        # context request → ContextPackage → Writing AI (핵심 흐름), so the
        # endpoint builds the package via context search, then generates.
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        # 증분 2 (D3=A): resolve the output-length preset to a token cap. The server
        # owns the mapping; an unknown preset is a 400 (same shape as task_type).
        try:
            output_length = OutputLength(body.output_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_length: {body.output_length}",
            ) from exc
        output_tokens = _writing_output_length_tokens()[output_length]
        # 증분 2c (D5=A): medium/long presets are too slow to block the request, so
        # enqueue a background generation job and return 202 Accepted immediately
        # (the worker claims and runs it, appending the result to scratch). short
        # (1024) stays fully synchronous below. The pad is keyed per-draft, so an
        # async preset without current_position has nowhere to display → 400 (short
        # still allows a positionless request, as today). The endpoint does not
        # touch writing/context_search/scratch here — that is the worker's job, so
        # the sync-only 503 checks below are not consulted for async.
        if output_length in (OutputLength.MEDIUM, OutputLength.LONG):
            if body.current_position is None:
                raise HTTPException(
                    status_code=400,
                    detail="current_position is required for async presets "
                           "(output_length medium/long)",
                )
            result = writing_generation_jobs.enqueue(
                project_id=project_id,
                draft_id=body.current_position.draft_id,
                request_id=body.request_id,
                task_type=task_type.value,
                instruction=body.instruction,
                draft_excerpt=body.draft_excerpt,
                query=body.query,
                output_length=output_length.value,
                max_output_tokens=output_tokens,
                max_tokens=body.max_tokens,
                version_id=body.current_position.version_id,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "job": _writing_generation_job_payload(result.job),
                    "idempotent_replay": result.idempotent_replay,
                },
            )
        if writing is None:
            raise HTTPException(
                status_code=503, detail="writing service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a: 생성은 이 패키지로 끝나지 않는다 — 같은 패키지가 곧바로 self-report에
            # 실리고 그쪽이 더 무겁다(출력 상한 6144 + 후보 산문). 후보는 아직 없지만
            # **상한은 출력 프리셋**이므로 그 값으로 창에 맞춰 줄인다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=output_tokens,
            )),
        )
        # Observability seam C (증분 C): this one request makes up to three
        # provider calls under three different sites — the query planner, the
        # generation itself, and the self-report when a reporter is configured.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                candidate = await writing.generate(
                    request=WritingRequest(
                        request_id=body.request_id,
                        project_id=project_id,
                        task_type=task_type,
                        instruction=body.instruction,
                        draft_excerpt=body.draft_excerpt,
                    ),
                    package=package,
                    max_output_tokens=output_tokens,
                )
            except WritingError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidCandidateReport as exc:
                # The reporter answered and its JSON was rejected — the report
                # call is the last one made, so this marks that row (D4).
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                # 창 가드 거부만 4xx로 갈라진다(K-3, 오너 2026-07-30) — 상류 장애가 아니라
                # 요청이 창을 넘은 것이고, 같은 요청의 재시도는 반드시 같은 실패다.
                # **주의(기존 불일치, 이 슬라이스가 만든 것 아님)**: 이 endpoint는 TIMEOUT도
                # 502로 내는데 gate/revise/report는 504로 낸다. 그 정렬은 별도 판단이라
                # 여기서 바꾸지 않았다(추적 부채).
                if exc.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        # Safety net (brief D0=B): persist the just-generated candidate to the
        # recovery store so a refresh/navigation before accept doesn't lose it.
        # Keyed by the draft being continued; skipped when there's no draft key.
        # Best-effort — a scratch failure must never fail generation.
        if body.current_position is not None:
            try:
                writing_scratch.save(
                    project_id=project_id,
                    draft_id=body.current_position.draft_id,
                    request_id=body.request_id,
                    task_type=candidate.task_type.value,
                    output_type=candidate.output_type.value,
                    instruction=body.instruction,
                    candidate_text=candidate.text,
                    version_id=body.current_position.version_id,
                )
            except Exception:  # noqa: BLE001 — safety net never blocks generate
                pass
        return _writing_candidate_payload(candidate)

    @app.get("/projects/{project_id}/writing/generation-jobs/{job_id}",
             response_model=WritingGenerationJobPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_writing_generation_job(
        project_id: str, job_id: str,
    ) -> dict[str, object]:
        # 증분 2c (D5=A): status read for an async generation job — the pad (증분 3)
        # polls this to learn when a medium/long generation finishes, then re-reads
        # the scratch list to display the result. 404 covers both "no such job" and
        # "job exists but belongs to another project" (project-scoped isolation).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        job = writing_generation_jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise HTTPException(
                status_code=404, detail="generation job not found"
            )
        return _writing_generation_job_payload(job)

    @app.get("/projects/{project_id}/writing/budget",
             response_model=WritingContextBudgetPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_writing_context_budget(project_id: str) -> dict[str, object]:
        # K-4 (프론트 글자수 표시·경고): R-a 유도 예산을 프론트에 노출해 카운터의 경고 기준을
        # 정확히 맞춘다 — 고정 상수(8192)는 R-a 이후 실제 예산(베타 ≈5407)과 어긋나 경고를
        # 거짓으로 만든다. 출력 프리셋마다 derive(후보 상한 = 해당 프리셋 출력 상한).
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        presets = _writing_output_length_tokens()

        async def _derive(upper_bound: int) -> int:
            return await derive_context_budget(
                requested_tokens=DEFAULT_CONTEXT_BUDGET_TOKENS,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=upper_bound,
            )

        return {
            "project_id": project_id,
            "context_budget_tokens": {
                "short": await _derive(presets[OutputLength.SHORT]),
                "medium": await _derive(presets[OutputLength.MEDIUM]),
                "long": await _derive(presets[OutputLength.LONG]),
            },
        }

    @app.post("/projects/{project_id}/writing/generation-jobs/{job_id}/retry",
              response_model=WritingGenerationJobPayload,
              responses=_owned(_ERRORS_404_409),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def retry_writing_generation_job(
        project_id: str, job_id: str,
    ) -> dict[str, object]:
        # Retry slice (async-pad D4=A): reset one FAILED generation job to PENDING
        # so the worker re-claims and re-runs it. Mirrors the Analysis retry
        # endpoint (failed→pending, others 409). No separate run call: the
        # generation worker's claim loop picks up any PENDING job on its own.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        job = writing_generation_jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise HTTPException(
                status_code=404, detail="generation job not found"
            )
        try:
            job = writing_generation_jobs.mark_pending_for_retry(job)
        except InvalidGenerationJobStateTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _writing_generation_job_payload(job)

    @app.post("/projects/{project_id}/writing/gate",
              response_model=WritingGatePayload,
              responses=_owned(_ERRORS_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_gate_endpoint(
        project_id: str, body: WritingGateRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        if writing_gate is None:
            raise HTTPException(
                status_code=503, detail="writing gate service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(draft_id=body.current_position.draft_id,
                            version_id=body.current_position.version_id)
            if body.current_position is not None else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            context_budget=ContextBudget(max_tokens=body.max_tokens),
        )
        request = WritingRequest(
            request_id=body.request_id, project_id=project_id,
            task_type=task_type, instruction=body.instruction,
            draft_excerpt=body.draft_excerpt,
        )
        candidate = WritingCandidate(
            request_id=body.request_id, project_id=project_id,
            task_type=task_type, output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )

        # Observability seam C: the gate's provider is wrapped, so the record —
        # model, tokens, latency, provider failures — comes from the call itself.
        # This scope only has to supply what the provider cannot know: which
        # workflow the call belongs to, and the domain verdicts annotated below.
        # Pre-call rejections (bad task_type, invalid search request, context
        # budget, context-search failure) leave no record without any special
        # handling: no provider call means nothing to record.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            try:
                result = await writing_gate.evaluate(
                    request=request, candidate=candidate, package=package)
            except InvalidWritingGateResult as exc:
                # The provider answered and domain parsing rejected it — a
                # verdict the provider layer cannot reach on its own, so the
                # success it recorded is corrected here before the flush.
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except WritingGateError as exc:
                # Input validation and an unavailable prompt template, both
                # raised before the provider is called — so no record.
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ProviderError as exc:
                # Already recorded by the decorator, with its taxonomy intact.
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
            scope.annotate_last(decision=result.decision.value,
                                gate_quality_score=gate_quality_score(result))
        return _writing_gate_payload(result)

    @app.post("/projects/{project_id}/writing/report",
              responses=_owned(_ERRORS_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_report_endpoint(
        project_id: str, body: WritingReportRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unsupported task_type: {body.task_type}"
            ) from exc
        if not body.request_id.strip():
            raise HTTPException(status_code=400, detail="request_id must not be empty")
        if not body.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction must not be empty")
        if not body.candidate_text.strip():
            raise HTTPException(status_code=400, detail="candidate_text must not be empty")
        if writing_report is None:
            raise HTTPException(
                status_code=503, detail="writing report service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a: 여기서는 후보가 **이미 있으므로** 상한이 아니라 그 산문을 직접 센다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )
        # Observability seam C (증분 C): planner call(s) then the report call.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                enriched = await writing_report.enrich(candidate, package)
            except InvalidContextSearchRequest as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidCandidateReport as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _writing_candidate_payload(enriched)

    @app.post("/projects/{project_id}/writing/revise",
              responses=_owned(_ERRORS_400_404_502_504_CONFIG),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_revise_endpoint(
        project_id: str, body: WritingReviseRequest
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            finding = WritingGateFinding(
                finding_type=WritingGateFindingType(body.finding.type),
                severity=WritingGateSeverity(body.finding.severity),
                message=body.finding.message,
                evidence=body.finding.evidence,
                recommended_decision=WritingGateDecision(
                    body.finding.recommended_decision
                ),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_revision is None:
            raise HTTPException(
                status_code=503, detail="writing revision service is not configured"
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            context_budget=ContextBudget(max_tokens=body.max_tokens),
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )
        # Observability seam C (증분 C): planner call(s) then the revision call.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                # Validate cheap deterministic boundaries before context search so
                # invalid requests never spend a planner round-trip.
                writing_revision.validate_inputs(candidate, finding, body.instruction)
                package = await context_search.build_context_package(search_request)
                revised = await writing_revision.revise(
                    candidate=candidate,
                    finding=finding,
                    instruction=body.instruction,
                    package=package,
                )
            except (WritingRevisionError, InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingRevision as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _writing_candidate_payload(revised)

    @app.post("/projects/{project_id}/writing/revise-and-gate",
              response_model=WritingReviseGateResponse,
              responses=_owned(REVISE_AND_GATE_RESPONSES),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_revise_and_gate_endpoint(
        project_id: str, body: WritingReviseRequest
    ) -> object:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            finding = WritingGateFinding(
                finding_type=WritingGateFindingType(body.finding.type),
                severity=WritingGateSeverity(body.finding.severity),
                message=body.finding.message,
                evidence=body.finding.evidence,
                recommended_decision=WritingGateDecision(
                    body.finding.recommended_decision
                ),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_revise_gate is None:
            raise HTTPException(
                status_code=503,
                detail="writing revise-and-gate service is not configured",
            )
        if context_search is None:
            raise HTTPException(
                status_code=503, detail="context search service is not configured"
            )
        position = (
            CurrentPosition(
                draft_id=body.current_position.draft_id,
                version_id=body.current_position.version_id,
            )
            if body.current_position is not None
            else None
        )
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a(오너 2026-07-31, v1.7.66): 후보가 이미 있고 루프의 report 다리(출력 상한
            # 6144 + 후보 산문)가 창을 구속하므로 report 엔드포인트와 같이 창에서 유도한다.
            # **진입 시 1회**만 유도한다 — 루프는 이 값을 (a) 패키지 예산과 (b) merge 상한의
            # 양쪽에 그대로 쓰므로, merge_context_packages가 패키지를 이 값으로 묶어
            # retrieve_more가 유도값 너머로 패키지를 키우지 못하게 한다. 후보는 revise로
            # partial patch될 뿐 유의하게 자라지 않고, 남는 초과는 K-3 가드가 받는다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        request = WritingRequest(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            instruction=body.instruction,
        )
        candidate = WritingCandidate(
            request_id=body.request_id,
            project_id=project_id,
            task_type=task_type,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=body.candidate_text,
        )

        persist_audit = (
            body.persist_audit if body.persist_audit is not None
            else _env_bool("WRITING_LOOP_AUDIT_DEFAULT", False)
        )

        def _record_loop_audit(*, summary, stages, final_candidate, gate,
                               error_type) -> tuple[str | None, dict | None]:
            # Phase 5.9 L9 B (P2=B opt-in): audit this loop termination only when
            # persist_audit is on. Only outcomes that produced a WritingLoopSummary
            # are loop runs; pre-loop request rejections (400/502/504) are never
            # audited. The persist is isolated from the loop critical path — a write
            # failure returns the loop result with audit_id=null + audit_error, it
            # never breaks the loop outcome (folds the prior H3 question).
            if not persist_audit:
                return None, None
            try:
                run_id = writing_loop_audit.record(
                    project_id=project_id, request_id=body.request_id,
                    trigger_finding=finding,
                    initial_candidate_text=body.candidate_text,
                    summary=summary, stages=stages,
                    final_candidate=final_candidate, gate=gate,
                    error_type=error_type,
                ).id
                return run_id, None
            except Exception as exc:  # noqa: BLE001 — deliberate isolation boundary
                return None, {"type": "audit_persist_error", "detail": str(exc)}

        # Observability seam C (증분 C): the loop's calls all land here —
        # planner, reviser, self-report and gate, once per round. One
        # correlation_id per request is what makes "how many rounds did this
        # request cost" answerable at all.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                writing_revision.validate_inputs(candidate, finding, body.instruction)
                package = await context_search.build_context_package(search_request)
                result = await writing_revise_gate.run(
                    request=request,
                    candidate=candidate,
                    finding=finding,
                    package=package,
                    current_position=position,
                    context_budget=search_request.context_budget,
                )
            except (WritingRevisionError, InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingRevision as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"{exc.error_type.value}: {exc.detail}",
                ) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
            except WritingReviseReportFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidCandidateReport):
                    status, error_type = 502, "invalid_candidate_report"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                else:
                    status, error_type = 502, "report_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "report_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingLoopRevisionFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, WritingRevisionError):
                    status, error_type = 400, "writing_revision_error"
                elif isinstance(cause, InvalidWritingRevision):
                    status, error_type = 502, "invalid_writing_revision"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                else:
                    status, error_type = 502, "revision_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "revision_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingRetrievalFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidWritingRetrievalPlan):
                    status, error_type = 502, "invalid_retrieval_plan"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                elif isinstance(cause, WritingRetrievalConfigurationError):
                    status, error_type = 503, "retrieval_not_configured"
                elif isinstance(cause, WritingRetrievalPlannerError):
                    status, error_type = 503, "retrieval_planner_error"
                elif isinstance(cause, InvalidContextSearchRequest):
                    status, error_type = 400, "invalid_context_request"
                elif isinstance(cause, ContextSearchBudgetExceeded):
                    status, error_type = 504, "context_budget_exceeded"
                elif isinstance(cause, ContextSearchFailed):
                    status, error_type = 502, cause.error_type.value
                    reclassify_planner_parse_error(scope, cause)
                else:
                    status, error_type = 502, "retrieval_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": _writing_gate_payload(exc.gate),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "retrieval_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
            except WritingReviseGateFailure as exc:
                cause = exc.cause
                if isinstance(cause, ProviderError):
                    status = _provider_error_status(cause)
                    error_type = cause.code.value
                elif isinstance(cause, InvalidWritingGateResult):
                    status, error_type = 502, "invalid_gate_result"
                    scope.reclassify_last_as_parse_error(type(cause).__name__)
                elif isinstance(cause, WritingGateError):
                    status, error_type = 400, "writing_gate_error"
                else:
                    status, error_type = 502, "gate_error"
                audit_id, audit_error = _record_loop_audit(
                    summary=exc.loop, stages=exc.stages,
                    final_candidate=exc.candidate, gate=exc.gate,
                    error_type=error_type,
                )
                return JSONResponse(
                    status_code=status,
                    content={
                        "candidate": _writing_candidate_payload(exc.candidate),
                        "gate": (
                            _writing_gate_payload(exc.gate)
                            if exc.gate is not None else None
                        ),
                        "loop": _writing_loop_payload(exc.loop),
                        "stages": _writing_stages_payload(exc.stages),
                        "audit_id": audit_id,
                        "audit_error": audit_error,
                        "gate_error": {
                            "type": error_type,
                            "detail": str(cause),
                        },
                    },
                )
        audit_id, audit_error = _record_loop_audit(
            summary=result.loop, stages=result.stages,
            final_candidate=result.candidate, gate=result.gate,
            error_type=None,
        )
        return {
            "candidate": _writing_candidate_payload(result.candidate),
            "gate": (
                _writing_gate_payload(result.gate)
                if result.gate is not None else None
            ),
            "loop": _writing_loop_payload(result.loop),
            "stages": _writing_stages_payload(result.stages),
            "audit_id": audit_id,
            "audit_error": audit_error,
        }

    @app.get("/projects/{project_id}/writing/loop-audits",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_loop_audits_endpoint(project_id: str) -> dict[str, object]:
        # Phase 5.9 L9 B: durable, append-only loop audit summaries, newest
        # first. Project-scoped; retained for later verification reference.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        runs = writing_loop_audit.list_runs(project_id)
        return {
            "project_id": project_id,
            "items": [_writing_loop_audit_summary_payload(run) for run in runs],
        }

    @app.get("/projects/{project_id}/writing/loop-audits/{audit_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_loop_audit_detail_endpoint(
        project_id: str, audit_id: str
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            run = writing_loop_audit.get(project_id=project_id, run_id=audit_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except WritingLoopAuditNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _writing_loop_audit_payload(run)

    @app.get("/projects/{project_id}/observability/kpi",
             response_model=ObservabilityKpiResponse,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def observability_kpi_endpoint(project_id: str) -> dict[str, object]:
        # 증분 5 (brief D4=A): the read-out over the per-call audit trail. Pure
        # aggregation — nothing is measured here that the pipeline did not
        # already record, so this endpoint calls no provider and opens no scope.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        kpi = aggregate_kpi(
            project_id=project_id,
            calls=llm_call_audit.list_calls(project_id),
            # The loop rollup is opt-in (WRITING_LOOP_AUDIT_DEFAULT, off), so
            # this is empty on a default deployment. That is why the payload
            # reports ``runs_considered`` next to the rate: a null rate over
            # zero runs is "never measured", not "never diverged".
            loop_runs=writing_loop_audit.list_runs(project_id),
        )
        return {
            "project_id": kpi.project_id,
            "totals": asdict(kpi.totals),
            "sites": [asdict(site) for site in kpi.sites],
            "gate": asdict(kpi.gate),
            "loop": asdict(kpi.loop),
        }

    @app.post("/projects/{project_id}/writing/accept",
              response_model=WritingAcceptResponse,
              responses=_owned(ACCEPT_RESPONSES),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_accept_endpoint(
        project_id: str, body: WritingAcceptRequest
    ) -> object:
        try:
            _require_project_exists(project_id)
            task_type = WritingTaskType(body.task_type)
            output_type = WritingOutputType(body.output_type)
            intent = WritingIntent(body.intent)
            next_unit = (
                NextUnit(
                    title=body.next_unit.title,
                    unit_kind=UnitKind(body.next_unit.unit_kind),
                    goal=body.next_unit.goal,
                )
                if body.next_unit is not None else None
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if writing_accept is None:
            raise HTTPException(status_code=503,
                                detail="writing accept service is not configured")
        if context_search is None:
            raise HTTPException(status_code=503,
                                detail="context search service is not configured")
        position = (CurrentPosition(
            draft_id=body.current_position.draft_id,
            version_id=body.current_position.version_id)
            if body.current_position is not None else None)
        search_request = ContextSearchRequest(
            project_id=project_id,
            purpose=ContextSearchPurpose.WRITING_CONTEXT,
            needs=_WRITING_CONTINUE_SCENE_NEEDS,
            query=body.query or body.instruction,
            current_position=position,
            # R-a(오너 2026-07-31, v1.7.66): accept도 report 다리를 지난다
            # (`WritingAcceptService.run` → `reporter.enrich`), 그래서 report 엔드포인트와
            # 같이 창에서 유도한다(후보 산문 추정을 후보 상한으로). 패턴 스윕으로 발견해
            # revise-and-gate 확장과 한 슬라이스로 담았다.
            context_budget=ContextBudget(max_tokens=await derive_context_budget(
                requested_tokens=body.max_tokens,
                capabilities=model_capabilities,
                report_output_cap=report_output_cap,
                report_system_template=REPORT_SYSTEM_TEMPLATE,
                candidate_tokens_upper_bound=candidate_tokens_from_text(
                    body.candidate_text),
            )),
        )
        request = WritingRequest(body.request_id, project_id, task_type,
                                 body.instruction, body.draft_excerpt,
                                 intent=intent, next_unit=next_unit)
        candidate = WritingCandidate(
            body.request_id, project_id, task_type, output_type,
            body.candidate_text, intent=intent, next_unit=next_unit)

        def _clear_scratch_for_saved_accept() -> None:
            # A *saved* accept means the canonical version now exists, so the
            # accepted candidate is no longer "unaccepted" and is retired from
            # scratch. Async-pad D2=A (SoT v1.7.25): remove ONLY the accepted
            # item (matching request_id), not the draft's whole history — other
            # generated candidates stay recoverable/copyable (the pad's reason to
            # exist). Called from BOTH saved outcomes — the clean 200 and the 502
            # partial where the version saved but the analysis job failed. A
            # non-PASS Gate result (accepted=false, nothing saved) must NOT clear:
            # the user still has a bounced draft worth recovering. Key on the same
            # draft generate used (current_position), falling back to the accept
            # target. No matching entry → no-op. Best-effort — never fails accept.
            cleanup_draft_id = (
                body.current_position.draft_id
                if body.current_position is not None else body.draft_id
            )
            try:
                writing_scratch.clear_accepted_item(
                    project_id, cleanup_draft_id, body.request_id)
            except Exception:  # noqa: BLE001 — cleanup never blocks accept
                pass

        # Observability seam C (증분 C): accept runs the planner and then the
        # gate (plus the reporter when the gate asks for a fresh report), so
        # its calls belong to the accept request, not to whatever earlier
        # request produced the candidate.
        with llm_call_scope(llm_call_audit, project_id=project_id,
                            correlation_id=body.request_id) as scope:
            try:
                package = await context_search.build_context_package(search_request)
                result = await writing_accept.accept(
                    draft_id=body.draft_id,
                    base_version_id=body.base_version_id,
                    idempotency_key=body.idempotency_key,
                    request=request, candidate=candidate, package=package)
            except (NotFound,) as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (Archived, StaleWritingBase) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except DraftOrderIntegrityError as exc:
                # H3 S5: closes the 500 leak SoT v1.7.29 recorded as a known defect.
                # intent=start_next_unit reaches core_sot.start_next_unit →
                # _require_ordered_drafts, which raises this on drafts predating the W3
                # ordered-unit invariant. No clause here caught it, so it escaped as an
                # opaque 500. Same mapping and rationale as the CRUD siblings (503, fix
                # is scripts/migrate_ordered_units.py — not a corrected request).
                #
                # Order matters: this must precede the WritingAcceptError clause below.
                # It is not a subclass today, but the 400 group is the broad
                # "bad request" bucket and putting the integrity face after it invites a
                # future re-parent to silently reclassify a server-side data problem as
                # the caller's fault. The over-strict regression pins 503, not 400.
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except (WritingAcceptError, WritingGateError,
                    InvalidContextSearchRequest) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except InvalidWritingGateResult as exc:
                scope.reclassify_last_as_parse_error(type(exc).__name__)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except WritingAcceptAnalysisError as exc:
                # The version WAS saved here (only the analysis job failed), so the
                # canonical draft exists and the scratch history is moot — same
                # rationale as the clean success path below.
                _clear_scratch_for_saved_accept()
                return JSONResponse(status_code=502, content={
                    "accepted": True,
                    "intent": exc.intent.value,
                    "saved": _accepted_save_payload(exc.saved, exc.target_draft),
                    "analysis_job": None,
                    "analysis_error": str(exc),
                })
            except ContextSearchBudgetExceeded as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ContextSearchFailed as exc:
                reclassify_planner_parse_error(scope, exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ProviderError as exc:
                status = _provider_error_status(exc)
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        if result.accepted:
            _clear_scratch_for_saved_accept()
        return {
            "accepted": result.accepted,
            "intent": result.intent.value,
            "gate": (_writing_gate_payload(result.gate)
                     if result.gate is not None else None),
            "saved": (_accepted_save_payload(result.saved, result.target_draft)
                      if result.saved is not None else None),
            "analysis_job": (_analysis_job_payload(result.analysis_job)
                             if result.analysis_job is not None else None),
            "idempotent_replay": result.idempotent_replay,
        }

    def _writing_scratch_payload(entry) -> dict[str, object]:
        return {
            "id": entry.id,
            "draft_id": entry.draft_id,
            "request_id": entry.request_id,
            "task_type": entry.task_type,
            "output_type": entry.output_type,
            "instruction": entry.instruction,
            "candidate_text": entry.candidate_text,
            "intent": entry.intent,
            "version_id": entry.version_id,
            "created_at": entry.created_at.isoformat(),
        }

    @app.get("/projects/{project_id}/writing/scratch", responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_scratch_list_endpoint(
        project_id: str, draft_id: str
    ) -> dict[str, object]:
        # Recovery surface (brief D1=B): unaccepted candidates for a draft,
        # newest first, so the editor can offer to restore an in-progress draft.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        entries = writing_scratch.list_for_draft(project_id, draft_id)
        return {
            "project_id": project_id,
            "draft_id": draft_id,
            "items": [_writing_scratch_payload(e) for e in entries],
        }

    @app.delete("/projects/{project_id}/writing/scratch", responses=_owned(_ERRORS_404),
                dependencies=_REQUIRE_PROJECT_OWNER)
    async def writing_scratch_discard_endpoint(
        project_id: str, draft_id: str
    ) -> dict[str, object]:
        # Explicit "버리기": drop the draft's unaccepted scratch history.
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        deleted = writing_scratch.clear_draft(project_id, draft_id)
        return {
            "project_id": project_id,
            "draft_id": draft_id,
            "deleted": deleted,
        }

    return app


def _build_context_search_request(
    project_id: str, body: ContextSearchHttpRequest
) -> ContextSearchRequest:
    if not body.idempotency_key.strip():
        raise ValueError("idempotency_key is required")
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
