"""FastAPI application shell for the Application service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.application.app.auth.login_guard import LoginFailureGuard

import os
import uuid
from datetime import timedelta

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from services.application.app.auth.access_grants import (
    AccessGrantService,
    InMemoryAccessGrantRepository,
)
from services.application.app.auth.admin_audit import (
    AdminAuditService,
    InMemoryAdminAuditRepository,
)
from services.application.app.deletion.project_name_history import (
    InMemoryProjectNameHistoryRepository,
    ProjectNameHistoryService,
)
from services.application.app.activity.log import (
    ActivityLogService,
    InMemoryActivityLogRepository,
)
from services.application.app.auth.sessions import (
    DEFAULT_SESSION_TTL,
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import (
    InMemoryUserRepository,
    UserService,
)
from services.application.app.auth.password import Argon2PasswordHasher
from services.application.app.analysis.extractor import (
    VersionedPromptAnalysisExtractionAdapter,
)
from services.application.app.analysis.gateway_provider import GatewayGenerateProvider
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.runner import (
    AnalysisExtractionRunner,
    AnalysisExtractionRunResult,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.candidate_review import (
    CandidateReviewService,
)
from services.application.app.analysis.apply import (
    MemoryApplyService,
)
from services.application.app.analysis.compare import (
    AnalysisCompareService,
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
)
from services.application.app.analysis.review_inbox import (
    ReviewInboxService,
)
from services.application.app.writing.revise import (
    WritingRevisionService,
    seed_writing_revise_template,
)
from services.application.app.writing.revise_gate import (
    WritingLoopPolicy,
    WritingReviseGateService,
)
from services.application.app.writing.retrieval import (
    TerminalJsonWritingRetrievalPlanner,
    seed_writing_retrieval_template,
)
from services.application.app.writing.gate import (
    WritingGateService,
    seed_writing_gate_template,
)
from services.application.app.writing.accept import (
    WritingAcceptService,
)
from services.application.app.writing.model_capabilities import ModelCapabilities
from services.application.app.writing.report import (
    WritingCandidateReportService,
    seed_report_template,
)
from services.application.app.writing.service import (
    WritingService,
    seed_writing_template,
)
from services.application.app.writing.loop_audit import (
    InMemoryWritingLoopAuditRepository,
    WritingLoopAuditService,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallSite,
)
from services.application.app.observability.llm_call_scope import (
    ObservedProvider,
    ProviderCallTally,
    provider_call_tally,
)
from services.application.app.quota.enforcement import (
    AdmissionMutex,
    GenerationJobCharger,
    QuotaCharge,
    QuotaEnforcementService,
)
from services.application.app.quota.ledger import (
    InMemoryUsageLedgerRepository,
    UsageLedgerService,
)
from services.application.app.quota.lock import (
    InMemoryRequestLockRepository,
    RequestLockService,
)
from services.application.app.quota.policy import (
    InMemoryQuotaPolicyRepository,
    QuotaPolicyService,
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
from services.application.app.writing.generation_worker import (
    GenerationCollaborators,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.llm_gateway.app.provider import LLMProvider
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryReindexEnqueueFailed,
    MemoryReindexOutbox,
    MemoryService,
)
from services.application.app.context_search.gate_findings import (
    GateFindingService,
    InMemoryGateFindingRepository,
)
from services.application.app.context_search.planner import (
    TerminalJsonSearchPlanner,
    seed_context_search_plan_template,
)
from services.application.app.context_search.prior_memory import (
    AnalysisContextService,
    DeterministicPriorMemoryBackend,
)
from services.application.app.context_search.service import (
    ContextSearchService,
    HybridCanonicalMemoryRetriever,
    HybridCandidateMemoryRetriever,
    LexicalCanonicalMemoryRetriever,
    LexicalCandidateMemoryRetriever,
    MongoDirectCanonicalMemoryRetriever,
    MongoDirectCandidateMemoryRetriever,
    VectorCanonicalMemoryRetriever,
    VectorCandidateMemoryRetriever,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
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
)
from services.application.app.indexing.chroma import (
    DEFAULT_COLLECTION_NAME,
    ChromaCandidateVectorIndexAdapter,
    ChromaMemoryVectorIndexAdapter,
    ChromaVectorIndexAdapter,
    connect_chroma_collection,
)
from services.application.app.indexing.embedding import (
    build_embedding_provider_from_env,
)
from services.application.app.context_search.rerank import (
    RerankingRetriever,
    build_rerank_provider_from_env,
)
from services.application.app.indexing.memory_index import (
    MEMORY_VECTOR_COLLECTION,
    derive_memory_index_text,
)
from services.application.app.indexing.memory_lexical_index import (
    MEMORY_LEXICAL_INDEX,
    connect_elasticsearch_memory_index,
)
from services.application.app.indexing.candidate_index import (
    CANDIDATE_VECTOR_COLLECTION,
    candidate_index_text,
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


def _default_login_failure_guard() -> "LoginFailureGuard":
    # Brute-force defense for /auth/login (signup approval slice 1-c, owner
    # 2026-08-22). Malformed/negative values refuse to start rather than
    # silently falling back — same posture as AUTH_SESSION_TTL_HOURS above: a
    # guard that quietly became "no guard" is worse than no guard.
    from services.application.app.auth.login_guard import (
        DEFAULT_LOCKOUT_SECONDS, DEFAULT_MAX_FAILURES, InMemoryFailureRecordRepository,
        LoginFailureGuard,
    )
    max_failures = DEFAULT_MAX_FAILURES
    raw_max = os.environ.get("AUTH_LOGIN_MAX_FAILURES")
    if raw_max:
        parsed = int(raw_max)
        if parsed <= 0:
            raise ValueError("AUTH_LOGIN_MAX_FAILURES must be > 0")
        max_failures = parsed
    lockout_seconds = DEFAULT_LOCKOUT_SECONDS
    raw_lockout = os.environ.get("AUTH_LOGIN_LOCKOUT_SECONDS")
    if raw_lockout:
        parsed = int(raw_lockout)
        if parsed <= 0:
            raise ValueError("AUTH_LOGIN_LOCKOUT_SECONDS must be > 0")
        lockout_seconds = parsed
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if uri:
        from services.application.app.auth.login_guard_mongo import (
            MongoFailureRecordRepository,
        )
        from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
        repository = MongoFailureRecordRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        )
    else:
        repository = InMemoryFailureRecordRepository()
    return LoginFailureGuard(
        repository,
        max_failures=max_failures,
        lockout=timedelta(seconds=lockout_seconds),
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


def _default_admin_audit_service() -> AdminAuditService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return AdminAuditService(InMemoryAdminAuditRepository())
    from services.application.app.auth.admin_audit_mongo import (
        MongoAdminAuditRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return AdminAuditService(
        MongoAdminAuditRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        )
    )


def _default_activity_log_service() -> ActivityLogService:
    """Phase 9 (A1=A·A6=A): `activity_events`. Mongo 가 있으면 durable, 없으면 in-memory.

    ★ A4=A 격리 때문에 이 조립이 in-memory 로 떨어져도 **아무 소리도 안 난다** —
    요청은 200 이고 로그만 사라진다. 그래서 실 Mongo 조립 가드가 함께 간다
    (`tests/test_activity_log.py::DefaultAssemblyLiveMongoTest`, 8.2c HARDEN-1 선례).
    """
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return ActivityLogService(InMemoryActivityLogRepository())
    from services.application.app.activity.log_mongo import (
        MongoActivityLogRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return ActivityLogService(
        MongoActivityLogRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        )
    )


def _default_project_name_history_service() -> ProjectNameHistoryService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        return ProjectNameHistoryService(InMemoryProjectNameHistoryRepository())
    from services.application.app.deletion.project_name_history_mongo import (
        MongoProjectNameHistoryRepository,
    )
    from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
    return ProjectNameHistoryService(
        MongoProjectNameHistoryRepository.from_uri(
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


def _default_quota_enforcement_service(
    jobs: WritingGenerationJobService | None = None,
) -> QuotaEnforcementService:
    """정책·원장·잠금을 한 저장소 위에서 조립한다 (Slice 8.3).

    셋 다 in-memory 기본이 있어 인프라 없이도 시행이 **켜진 채로** 돈다 — 무제한이
    되는 기본값은 두지 않는다(그 상태가 곧 무료 제공이다). Mongo URI 가 있으면 세
    어댑터가 함께 올라간다: 셋 중 하나만 durable 하면 재기동마다 사용량이 반쯤
    사라지므로 갈라 놓지 않는다.

    입장 뮤텍스는 잠금과 **같은 컬렉션**을 쓴다(§Q3-a 계약 1) — 키 공간만 다르다.
    """
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        policy_repo = InMemoryQuotaPolicyRepository()
        ledger_repo = InMemoryUsageLedgerRepository()
        lock_repo = InMemoryRequestLockRepository()
    else:
        from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
        from services.application.app.quota.ledger_mongo import (
            MongoUsageLedgerRepository,
        )
        from services.application.app.quota.lock_mongo import (
            MongoRequestLockRepository,
        )
        from services.application.app.quota.policy_mongo import (
            MongoQuotaPolicyRepository,
        )
        db_name = os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        policy_repo = MongoQuotaPolicyRepository.from_uri(uri, db_name=db_name)
        ledger_repo = MongoUsageLedgerRepository.from_uri(uri, db_name=db_name)
        lock_repo = MongoRequestLockRepository.from_uri(uri, db_name=db_name)
    return QuotaEnforcementService(
        policy=QuotaPolicyService(policy_repo),
        ledger=UsageLedgerService(
            ledger_repo, id_factory=lambda: "rul:" + uuid.uuid4().hex
        ),
        locks=RequestLockService(lock_repo),
        mutex=AdmissionMutex(lock_repo),
        jobs=jobs,
    )


def _default_prompt_template_service() -> PromptTemplateService:
    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v1()
        service.seed_analysis_extract_v2()
        service.seed_analysis_extract_v3()
        service.seed_analysis_extract_v4()
        service.seed_analysis_extract_v5()
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
    service.seed_analysis_extract_v5()
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
            # Owner 2026-08-23 (extractor slice): 2048 could truncate mid-fence —
            # gemma-4-31b-it wraps JSON in a ```json fence and a long candidate
            # list lost the closing fence to the ceiling, which parsing then
            # rejected (work_log 2026-08-23 session 5/6). Headroom first; the
            # open-fence guard in writing/json_extract.py is the second half.
            max_tokens=int(os.environ.get("ANALYSIS_EXTRACT_MAX_TOKENS", "8192")),
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


def _rerank_wrapped(inner, *, text_of):
    """Wrap a retriever with neural reranking, or return it untouched.

    Both assembly sites go through here so the "did someone forget to wrap it"
    failure has a single place to be guarded — `ObservedProvider` produced
    exactly that bug once (green suite, instrumentation silently gone in
    deployment) and the prescription was an assembly guard. Here the same
    omission would silently return search to its pre-reranking quality.
    """

    provider = build_rerank_provider_from_env()
    if provider is None:
        return inner
    return RerankingRetriever(inner=inner, provider=provider, text_of=text_of)


def _build_canonical_memory_retriever(memory: MemoryService):
    # ⑤ §5 B canonical retrieval backend, chosen by env (D3/E6): vector over the
    # shared memory_vectors collection, lexical over the Elasticsearch memory
    # index, both fused by RRF when configured, else the deterministic Mongo-direct
    # listing. The item/Gate authority re-derivation is identical for every
    # backend — only the retrieval layer changes.
    vector = _build_vector_canonical_retriever(memory)
    lexical = _build_lexical_canonical_retriever(memory)
    if vector is not None and lexical is not None:
        inner = HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
    elif vector is not None:
        inner = vector
    elif lexical is not None:
        inner = lexical
    else:
        inner = MongoDirectCanonicalMemoryRetriever(memory)
    # Neural reranking wraps the chosen backend rather than living inside it, so
    # vector-only and lexical-only configurations get it too (decision 3=A). No
    # address configured means no wrapper at all — turning it off ends here.
    return _rerank_wrapped(
        inner,
        text_of=lambda memory_entry: derive_memory_index_text(
            memory_entry.memory_type, memory_entry.payload
        ),
    )


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
        inner = HybridCandidateMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
    elif vector is not None:
        inner = vector
    elif lexical is not None:
        inner = lexical
    else:
        inner = MongoDirectCandidateMemoryRetriever(analysis)
    # Same wrapper, same seam — the two retrieval families differ only in the
    # item type, which is why the text projection is the injected part.
    return _rerank_wrapped(inner, text_of=candidate_index_text)


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
    # The dimension guard, timeouts and the fake fallback all live in the single
    # assembly helper now (embedding-adapter slice, decision 4=A).
    return build_embedding_provider_from_env()


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











































_QUOTA_TALLY_STATE = "quota_tally"













class QuotaSettledRoute(APIRoute):
    """응답을 실제로 보고 정산하는 seam. **정책은 여기 없다**(위 주석 참조).

    - 차감 조건은 Q1-a=A 하나다: ``2xx`` **그리고** provider 를 불렀다.
    - ``202`` 는 뺀다(Q1-b=A) — 접수는 성공이 아니고 그 차감은 **워커**가 한다.
      202 는 provider 를 부르지도 않으므로 조건이 두 겹으로 막지만, 규칙 자체를
      적어 두는 편이 나중에 202 를 내는 다른 경로가 생겨도 안전하다.
    - 예외로 끝난 요청은 차감 없이 잠금만 푼다. 해제는 ``finally`` 라 어떤 경로로
      끝나도 잠금이 남지 않는다.
    """

    def get_route_handler(self):
        original = super().get_route_handler()

        async def settled(request: Request) -> Response:
            tally = ProviderCallTally()
            setattr(request.state, _QUOTA_TALLY_STATE, tally)
            status_code: int | None = None
            with provider_call_tally(tally):
                try:
                    response = await original(request)
                    status_code = response.status_code
                    return response
                finally:
                    charge: QuotaCharge | None = getattr(
                        request.state, _QUOTA_STATE, None
                    )
                    if charge is not None:
                        request.app.state.quota.settle(
                            charge,
                            charged=_is_charged(status_code, tally.provider_calls),
                        )

        return settled


def _is_charged(status_code: int | None, provider_calls: int) -> bool:
    if status_code is None or not 200 <= status_code < 300:
        return False
    if status_code == 202:
        return False
    return provider_calls > 0












































































# The save surface is deliberately narrower than the read surface above and
# reuses the same key names (draft_version/snapshot/blocks) with fewer fields.
# Sharing one model across both breaks in whichever direction it is shared:
# the wide read model on this narrow payload fails validation (missing fields),
# and the narrow model on the read payload silently drops fields. Hence the
# separate declarations.















































































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
    jobs = _default_writing_generation_job_service()
    return GenerationCollaborators(
        context_search=context_search,
        writing=writing,
        scratch=_default_writing_scratch_service(),
        jobs=jobs,
        needs=_WRITING_CONTINUE_SCENE_NEEDS,
        # Same factory create_app uses, so the worker's records land in the same
        # store the KPI aggregation reads (증분 C, D3).
        llm_call_audit=_default_llm_call_audit_service(),
        # R-a: 워커도 같은 유도를 쓴다. 워커에서 빠뜨리면 **제품의 주 경로만** 종전 예산으로
        # 남는다(생성은 HTTP가 아니라 이 워커가 돌린다).
        capabilities=_default_model_capabilities(),
        report_output_cap=_report_output_cap(),
        # 8.3 Q1-b=A: 비동기 생성의 차감 주체는 워커다. 같은 factory 를 쓰므로 요청
        # 경로와 **같은 원장**에 쓰고, 회원 조회는 주 창 키(가입일 기준)를 계산하기
        # 위한 것이다. 여기서 빠뜨리면 medium/long 이 통째로 무료가 된다.
        quota=GenerationJobCharger(
            enforcement=_default_quota_enforcement_service(jobs),
            users=_default_user_service(),
        ),
    )


# 라우터 분해(R1, 2026-08-05): register 함수를 create_app 이 호출한다.
#
# **이 import 의 위치는 이제 자유롭다**(2026-08-06 공유 prelude 추출). 종전에는
# ``def create_app`` 바로 앞이어야 했다 — router 가 ``from ..main import`` 로 공유
# 심볼을 되가져와서 ``main ↔ routers`` 순환이 있었고, 그 순환은 **필요한 심볼이 전부
# 이 줄 위에 정의돼 있다**는 순서에만 기대어 풀렸다. 그래서 ``routers`` 를 먼저
# import 하는 모든 경로가 죽었다(``python -m`` 포함, H-3-A).
#
# 지금은 공유 심볼이 ``app/api/`` 와 ``app/env.py`` 에 있고 router 도 거기서 가져오므로
# **순환 자체가 없다**. 상대 경로를 유지하는 이유는 순환이 아니라 **모듈 동일성**이다 —
# 절대 경로면 짧은 이름(``PYTHONPATH=services/application`` + ``import app.main``)으로
# 들어온 로드에서 ``app.main`` 과 ``services.application.app.main`` 이 서로 다른 객체가
# 되고, 다른 테스트의 ``patch("services.application.app.main....")`` 가 엉뚱한 사본을
# 건드린다. 회귀: ``tests/test_app_import_paths.py``.
from .routers.admin import register_admin
from .routers.analysis import register_analysis
from .routers.auth import register_auth
from .routers.context_search import register_context_search
from .routers.drafts import register_drafts
from .routers.health import register_health
from .routers.memory import register_memory
from .routers.observability import register_observability
from .routers.projects import register_projects
from .routers.source_refs import register_source_refs
from .routers.writing import register_writing

# ── HTTP 계약 계층(2026-08-06 공유 prelude 추출) ─────────────────────────
# 요청/응답 모델·에러 선언·dependency 는 여기서 산다. `routers/*` 도 **main 이 아니라**
# 이 모듈들을 본다 — 그래서 `main ↔ routers` 순환이 없고, 어떤 로드 순서에서도 뜬다.
# 되돌리면(= 정의를 main.py 로 되가져오면) 순환이 복구된다: tests/test_app_import_paths.py.
from .env import (
    _env_bool,
    _env_int,
    draft_raw_text_max_chars,
)
from .api.models import (
    _WRITING_CONTINUE_SCENE_NEEDS,
    _project_brief_style_example_limits,
    _writing_output_length_tokens,
)
from .api.errors import (
    _STORAGE_ERRORS,
)
from .api.dependencies import (
    _QUOTA_STATE,
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
    login_failure_guard: "LoginFailureGuard | None" = None,
    access_grant_service: AccessGrantService | None = None,
    admin_audit_service: AdminAuditService | None = None,
    project_name_history_service: ProjectNameHistoryService | None = None,
    quota_enforcement_service: QuotaEnforcementService | None = None,
    activity_log_service: ActivityLogService | None = None,
    include_product: bool = True,
    include_admin: bool = True,
) -> FastAPI:
    """Assemble the application. ``include_*`` pick which **surface** is served.

    Slice 2 (A1=ⓑ, 2026-08-09): the admin surface moved to its own address —
    a fourth compose service running the same image with a different command,
    reachable only through nginx ``/api/admin/``. That means two deployed apps
    (`create_product_app` / `create_admin_app`), while tests, `scripts/
    dump_openapi.py` (= the frontend's generated TS contract) and the
    boundary-matrix guards keep needing the **union** — the browser sees one
    origin, so one schema has to describe all 76 operations.

    The three factories are one function on purpose. H-2 (verification
    2026-08-05) asked for a guard against "the app tests exercise drifts from
    the app that ships"; a shared body makes the drift **structurally**
    impossible rather than merely watched — the only difference between the
    three is which ``register_*`` calls run. Service assembly above is
    unconditional for the same reason: an admin-only assembly path would be a
    second wiring nobody exercises (the shape this repo was already burned by
    with ``ObservedProvider`` — fake green, missing only in deployment).
    ``tests/test_admin_surface_separation.py`` states the union property.

    ``/health`` is registered on **both** surfaces: it is infrastructure, not
    product, and the admin container needs a compose healthcheck of its own.
    """
    # Fail startup loudly for invalid environment-adjustable public bounds.
    _project_brief_style_example_limits()
    _writing_output_length_tokens()
    draft_raw_text_max_chars()
    # Owner 2026-08-23 (security audit finding ③ / verification H-3): the
    # interactive docs are NOT a public surface. With FastAPI defaults they
    # were reachable unauthenticated both directly (8520 /docs·/redoc·
    # /openapi.json) and through nginx (/api/docs·…) — which advertises every
    # route, guard and error shape to anyone on the network. Nothing legit
    # consumes them over HTTP: the frontend contract comes from
    # ``scripts/dump_openapi.py`` (an import, ``create_app().openapi()``), and
    # the test suites call ``.openapi()`` the same way. Disabling here covers
    # product, admin and union app at once — the three factories are one body.
    app = FastAPI(
        title="에-라잇 Application",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Slice 8.3: every route is built by the settling wrapper. It is a no-op for
    # the 66 free operations (no receipt on ``request.state`` → nothing to do);
    # applying it globally rather than per-route is deliberate, because "which
    # routes settle" must not become a second, hand-kept list beside the
    # enforcement dependency — the dependency stays the single classification.
    # Must be set before the first decorator runs: FastAPI freezes the class per
    # route at registration time.
    app.router.route_class = QuotaSettledRoute

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

    register_health(app)

    # 공통 auth/admin 서비스 — register_auth·register_admin 이 쓴다(라우터 분해).
    users = user_service or _default_user_service()
    sessions = session_service or _default_session_service()
    access_grants = access_grant_service or _default_access_grant_service()
    admin_audit = admin_audit_service or _default_admin_audit_service()
    # Slice 8.2c: written only by purge, and it outlives the project graph.
    project_name_history = (
        project_name_history_service or _default_project_name_history_service()
    )
    # Phase 9 (I1): the opposite direction — a project *child*, purged with it.
    activity = activity_log_service or _default_activity_log_service()
    # The module-level dependency reads them from here: it must be one function
    # object across all apps so the exhaustive guard has a single identity to
    # look for (see require_authenticated_user).
    app.state.users = users
    app.state.sessions = sessions
    app.state.core_sot = core_sot
    # require_project_owner reads this to honour a live grant (D8-5e, F1=C).
    app.state.access_grants = access_grants
    app.state.admin_audit = admin_audit
    # Slice 8.3 (Q7=A): ``enforce_quota`` and the settling route read enforcement
    # from here for the same reason the auth dependency does — one module-level
    # function object across all apps, so the exhaustive guard has one identity
    # to look for. The generation job store is handed over so admission counts a
    # member's pending/running async jobs (Q1-b=A).
    app.state.quota = (
        quota_enforcement_service
        or _default_quota_enforcement_service(writing_generation_jobs)
    )

    # ``/auth`` is product-side: the browser logs in through the product origin
    # (nginx sends only ``/api/admin/`` to the admin service), and the session
    # it mints lives in Mongo, which both apps read. That is why the admin
    # service needs no auth route of its own and no shared secret.
    #
    # ★ The registration **order** below is the union app's route order, which
    # the OpenAPI document (and therefore the frontend's generated types) is
    # built from. Skipping a surface must not reorder the others — that is why
    # these are ``if`` guards in place rather than a reshuffled call list.
    if include_product:
        register_auth(app, users=users, sessions=sessions,
                      core_sot=core_sot, activity=activity,
                      login_guard=login_failure_guard or _default_login_failure_guard())

    if include_admin:
        register_admin(
            app,
            users=users, core_sot=core_sot,
            quota=app.state.quota, access_grants=access_grants,
            admin_audit=admin_audit, llm_call_audit=llm_call_audit,
            writing_loop_audit=writing_loop_audit, memory=memory,
            analysis=analysis, review_queue=review_queue,
            gate_findings=gate_findings,
            writing_generation_jobs=writing_generation_jobs,
            writing_scratch=writing_scratch, sync_outbox=sync_outbox,
            project_name_history=project_name_history, activity=activity,
        )

    if not include_product:
        return app

    register_memory(app, core_sot=core_sot, memory=memory)

    register_observability(
        app,
        core_sot=core_sot, llm_call_audit=llm_call_audit,
        writing_loop_audit=writing_loop_audit,
    )

    register_context_search(
        app,
        core_sot=core_sot, memory=memory, analysis=analysis,
        context_search=context_search, gate_findings=gate_findings,
        llm_call_audit=llm_call_audit,
    )

    register_projects(
        app,
        core_sot=core_sot, access_grants=access_grants, sync_outbox=sync_outbox,
        activity=activity,
    )

    register_drafts(
        app, core_sot=core_sot, sync_outbox=sync_outbox, activity=activity,
        writing_generation_jobs=writing_generation_jobs,
        writing_scratch=writing_scratch,
    )

    register_source_refs(
        app,
        core_sot=core_sot, shared_vector_index=shared_vector_index,
        shared_embeddings=shared_embeddings, shared_backend=shared_backend,
        activity=activity,
    )


    register_analysis(
        app,
        core_sot=core_sot,
        analysis=analysis,
        memory=memory,
        runner=runner,
        analysis_context=analysis_context,
        compare=compare,
        apply_service=apply_service,
        review_queue=review_queue,
        character_reconciliation=character_reconciliation,
        review_inbox=review_inbox,
        gate_findings=gate_findings,
        llm_call_audit=llm_call_audit,
        candidate_review=candidate_review,
        activity=activity,
    )

    register_writing(
        app,
        core_sot=core_sot,
        writing=writing,
        writing_gate=writing_gate,
        writing_report=writing_report,
        writing_revision=writing_revision,
        writing_revise_gate=writing_revise_gate,
        writing_accept=writing_accept,
        writing_generation_jobs=writing_generation_jobs,
        writing_scratch=writing_scratch,
        writing_loop_audit=writing_loop_audit,
        context_search=context_search,
        llm_call_audit=llm_call_audit,
        model_capabilities=model_capabilities,
        report_output_cap=report_output_cap,
        activity=activity,
    )

    return app


def create_product_app(**kwargs) -> FastAPI:
    """The product surface — every operation but ``/admin/*`` (A1=ⓑ).

    This is what the ``application`` container serves, and the reason the split
    exists: the product port is published to the LAN on purpose (D8-7 G1=C), so
    the admin operations must not be *on* it. A LAN client hitting
    ``application:8520/admin/users`` now gets 404 from the router, before any
    guard runs — ``require_admin_user`` stays as the second layer, not the only
    one.
    """
    return create_app(include_admin=False, **kwargs)


def create_admin_app(**kwargs) -> FastAPI:
    """The admin surface — ``/admin/*`` plus the health probe (A1=ⓑ).

    Served by the ``admin`` compose service, which publishes no host port and is
    reachable only through nginx ``location /api/admin/``. Sessions are shared
    for free because they live in Mongo (no process secret to carry over), so
    the browser keeps using the cookie it got from the product origin.
    """
    return create_app(include_product=False, **kwargs)


# ``uvicorn services.application.app.main:app`` — the image's default CMD, i.e.
# the ``application`` service. It is the **product** app: the deployment default
# has to be the surface that is safe to publish, or a container started without
# a command override would put /admin back on the LAN port.
app = create_product_app()
