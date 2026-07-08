"""Phase 4 Slice 4.1: context search orchestration and Context Gate.

The planner is an injected producer (terminal-JSON LLM planner arrives in
Slice 4.2); this slice locks the SearchPlan/ContextPackage/Gate contracts
against a deterministic fake planner. Index hits are never used directly:
every hit passes the Phase 3A stale guard and is reloaded from the MongoDB
SOT before it can become a ContextItem.
"""

from __future__ import annotations

import inspect
import time
from typing import Awaitable, Callable, Protocol

from services.application.app.core_sot.service import (
    CoreSotService,
    NotFound,
)
from services.application.app.core_sot.models import BlockKind, SourceBlock
from services.application.app.context_search.models import (
    BUDGET_EXCLUDED_REASON,
    ContextBudget,
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchErrorType,
    ContextSearchRequest,
    ContextSearchTrace,
    ExcludedHit,
    GateDecision,
    GateFinding,
    GATE_PASS,
    GATE_REJECT,
    MACRO_NEEDS,
    NEED_ALLOWED_TOOLS,
    SearchPlan,
    SearchStepTrace,
    SearchTool,
    StepFailure,
)
from services.application.app.indexing.models import (
    IndexPointer,
    MemoryIndexRecord,
    SourceBlockIndexRecord,
)
from services.application.app.indexing.memory_index import (
    MemoryVectorIndexAdapter,
    derive_memory_index_text,
)
from services.application.app.indexing.memory_lexical_index import (
    MemoryLexicalIndexAdapter,
)
from services.application.app.indexing.service import (
    EmbeddingProvider,
    MEMORIES_COLLECTION,
    SOURCE_BLOCK_COLLECTION,
    SourceBlockIndexingService,
    _cosine_similarity,
)
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryNotFound, MemoryService
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
)
from services.application.app.analysis.service import (
    AnalysisNotFound,
    AnalysisService,
)
from services.llm_gateway.app.errors import ProviderError


# Candidate store collection (Writing candidate inclusion origin). Matches the
# analysis Mongo repository's candidate collection so the Gate can tell a
# candidate-origin item from a canonical-memory or source-block one.
CANDIDATES_COLLECTION = "analysis_candidates"

DEFAULT_WALL_CLOCK_SECONDS = 60
DEFAULT_VECTOR_HIT_LIMIT = 8
DEFAULT_RECENT_SCENE_BLOCK_LIMIT = 5


class ContextSearchError(Exception):
    pass


class InvalidContextSearchRequest(ContextSearchError):
    pass


class ContextSearchBudgetExceeded(ContextSearchError):
    """Request wall-clock budget ran out; distinct from the error taxonomy."""


class ContextSearchFailed(ContextSearchError):
    def __init__(self, error_type: ContextSearchErrorType, detail: str) -> None:
        super().__init__(f"{error_type.value}: {detail}")
        self.error_type = error_type
        self.detail = detail


class SearchPlanner(Protocol):
    # The planner may be sync (Slice 4.1 fake planners) or async (the Slice 4.2
    # terminal-JSON LLM planner). build_context_package awaits the result when
    # it is awaitable, so either shape plugs into the same seam.
    def build_plan(
        self, request: ContextSearchRequest
    ) -> SearchPlan | Awaitable[SearchPlan]: ...


class VectorSearchAdapter(Protocol):
    def query_similar(
        self, *, project_id: str, vector: tuple[float, ...], limit: int
    ) -> tuple[SourceBlockIndexRecord, ...]: ...


DEFAULT_CANONICAL_MEMORY_LIMIT = 8


class CanonicalMemoryRetriever(Protocol):
    """Writing canonical inclusion retrieval seam (⑤ §5 B, D2).

    Returns the authoritative canonical ``MemoryEntry`` records to surface as
    Writing evidence. The Mongo-direct implementation lists the store; a later
    vector/search-engine layer implements the same method (retrieval finds the
    ids, the memory store stays the authority) without changing item or Gate
    logic. See docs/plans/04-writing-canonical-context-decisions.md (D2=A).
    """

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryEntry, ...]: ...


class MongoDirectCanonicalMemoryRetriever:
    """D2=A: list a project's canonical memories from the store (no ranking).

    The ``query`` is ignored for now — relevance ranking arrives with the vector
    retrieval layer. Only ``CANONICAL`` entries are returned (superseded versions
    are prior history, not current knowledge)."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryEntry, ...]:
        canonical = [
            entry
            for entry in self._memory.list_memories(project_id=project_id)
            if entry.status is MemoryStatus.CANONICAL
        ]
        return tuple(canonical[:limit])


class VectorCanonicalMemoryRetriever:
    """D2 follow-up: relevance-ranked canonical retrieval over ``memory_vectors``.

    Vector similarity finds the ids; the memory store stays the authority
    (D2=A: "벡터에서 찾고 Mongo를 찔러 권위 레코드 재유도"), so every hit is
    reloaded via ``get_memory`` and only ``CANONICAL`` survivors are returned. A
    stale vector (a superseded/deleted memory whose vector lingers before the
    reindex drain catches up) is dropped here, and would be caught again by the
    Gate. The ``.retrieve()`` seam and return type are identical to the
    Mongo-direct retriever, so step/item/Gate logic is unchanged.

    Canonical memories are indexed per ``memory_type``, so each type is queried
    and the hits are merged into one relevance-ranked pool. ``_merge_hits`` is
    the isolated swap point for a future per-type selection strategy (owner D2:
    single pool for the MVP, kept separable)."""

    # The three canonical memory taxonomies (== MemoryEntry.memory_type domain).
    _MEMORY_TYPES: tuple[AnalysisCandidateType, ...] = tuple(AnalysisCandidateType)

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        embeddings: EmbeddingProvider,
        vector_index: MemoryVectorIndexAdapter,
    ) -> None:
        self._memory = memory_service
        self._embeddings = embeddings
        self._vector_index = vector_index

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryEntry, ...]:
        vector = self._embeddings.embed(query)
        hits: list[MemoryIndexRecord] = []
        for memory_type in self._MEMORY_TYPES:
            hits.extend(
                self._vector_index.query_similar(
                    project_id=project_id,
                    memory_type=memory_type.value,
                    vector=vector,
                    limit=limit,
                )
            )
        entries: list[MemoryEntry] = []
        for hit in self._merge_hits(hits, vector):
            try:
                entry = self._memory.get_memory(
                    project_id=project_id, memory_id=hit.memory_id
                )
            except MemoryNotFound:
                # The vector outlived its memory (deleted before the reindex
                # drain); skip it rather than surfacing a phantom.
                continue
            if entry.status is MemoryStatus.CANONICAL:
                entries.append(entry)
            if len(entries) >= limit:
                break
        return tuple(entries)

    def _merge_hits(
        self, hits: list[MemoryIndexRecord], vector: tuple[float, ...]
    ) -> list[MemoryIndexRecord]:
        # MVP (owner D2): merge every type's hits into one pool ranked by cosine
        # similarity, id as a deterministic tie-break (the fake adapter's own
        # ordering convention). Isolated so a later per-type selection strategy
        # can replace it without touching the authority re-derivation above.
        return sorted(
            hits,
            key=lambda hit: (-_cosine_similarity(vector, hit.vector), hit.id),
        )


class LexicalCanonicalMemoryRetriever:
    """§8 lexical leg: BM25/nori keyword retrieval over the Elasticsearch memory
    index (⑤ §5 B, E2). Symmetric to the vector retriever — the lexical index
    finds the ids (ranked by keyword relevance), and the memory store stays the
    authority (contracts.md §1.3: an ES hit is reloaded from Mongo before it can
    ground). Only ``CANONICAL`` survivors are returned; the ``.retrieve()`` seam
    and return type are identical, so step/item/Gate are unchanged."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        lexical_index: MemoryLexicalIndexAdapter,
    ) -> None:
        self._memory = memory_service
        self._lexical = lexical_index

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryEntry, ...]:
        hits = self._lexical.search(
            project_id=project_id, query=query, limit=limit
        )
        entries: list[MemoryEntry] = []
        for hit in hits:
            try:
                entry = self._memory.get_memory(
                    project_id=project_id, memory_id=hit.memory_id
                )
            except MemoryNotFound:
                # The lexical doc outlived its memory (deleted before drain); skip.
                continue
            if entry.status is MemoryStatus.CANONICAL:
                entries.append(entry)
        return tuple(entries)


DEFAULT_RRF_K = 60


class HybridCanonicalMemoryRetriever:
    """E3: Reciprocal Rank Fusion of the vector and lexical canonical retrievers.

    Each sub-retriever returns a ranked, authority-resolved (canonical-only)
    ``MemoryEntry`` list; RRF fuses by rank (``1/(k + rank)``, rank 1-based) keyed
    by memory id, so a memory ranked well by either signal surfaces near the top
    and one ranked well by both is boosted. Authority re-derivation already
    happened inside each sub-retriever, so fusion is a pure rank merge; dedup is
    by ``MemoryEntry.id``. The ``.retrieve()`` seam is unchanged."""

    def __init__(
        self,
        *,
        vector_retriever: CanonicalMemoryRetriever,
        lexical_retriever: CanonicalMemoryRetriever,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._vector = vector_retriever
        self._lexical = lexical_retriever
        self._rrf_k = rrf_k

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[MemoryEntry, ...]:
        ranked_lists = (
            self._vector.retrieve(
                project_id=project_id, query=query, limit=limit
            ),
            self._lexical.retrieve(
                project_id=project_id, query=query, limit=limit
            ),
        )
        scores: dict[str, float] = {}
        entries: dict[str, MemoryEntry] = {}
        for ranked in ranked_lists:
            for rank, entry in enumerate(ranked):
                scores[entry.id] = scores.get(entry.id, 0.0) + 1.0 / (
                    self._rrf_k + rank + 1
                )
                entries.setdefault(entry.id, entry)
        fused = sorted(
            entries.values(), key=lambda entry: (-scores[entry.id], entry.id)
        )
        return tuple(fused[:limit])


DEFAULT_CANDIDATE_MEMORY_LIMIT = 8


class CandidateMemoryRetriever(Protocol):
    """Writing candidate inclusion retrieval seam (⑤ §5 B follow-up, D2).

    Returns ``needs_review`` candidate records to surface as *labeled* Writing
    evidence. Mongo-direct now; a later vector/search-engine layer implements
    the same method (retrieval finds the ids, the analysis store stays the
    authority) without changing item or Gate logic. See docs/plans/
    04-writing-candidate-context-decisions.md (D2=A).
    """

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[AnalysisCandidate, ...]: ...


class MongoDirectCandidateMemoryRetriever:
    """D2=A: list a project's needs_review candidates from the store (no ranking).

    The ``query`` is ignored for now — relevance ranking arrives with the vector
    retrieval layer. Only ``needs_review`` candidates are returned; promoted
    candidates are served by the canonical path instead (D5=A)."""

    def __init__(self, analysis_service: AnalysisService) -> None:
        self._analysis = analysis_service

    def retrieve(
        self, *, project_id: str, query: str, limit: int
    ) -> tuple[AnalysisCandidate, ...]:
        candidates = self._analysis.list_needs_review_candidates(
            project_id=project_id
        )
        return tuple(candidates[:limit])


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


class ContextSearchService:
    def __init__(
        self,
        *,
        core_sot: CoreSotService,
        indexing_service: SourceBlockIndexingService,
        vector_search: VectorSearchAdapter,
        embeddings: EmbeddingProvider,
        planner: SearchPlanner,
        canonical_memory_retriever: CanonicalMemoryRetriever | None = None,
        candidate_memory_retriever: CandidateMemoryRetriever | None = None,
        wall_clock_seconds: float = DEFAULT_WALL_CLOCK_SECONDS,
        vector_hit_limit: int = DEFAULT_VECTOR_HIT_LIMIT,
        recent_scene_block_limit: int = DEFAULT_RECENT_SCENE_BLOCK_LIMIT,
        canonical_memory_limit: int = DEFAULT_CANONICAL_MEMORY_LIMIT,
        candidate_memory_limit: int = DEFAULT_CANDIDATE_MEMORY_LIMIT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if wall_clock_seconds <= 0:
            raise InvalidContextSearchRequest("wall_clock_seconds must be positive")
        self._core_sot = core_sot
        self._indexing = indexing_service
        self._vector_search = vector_search
        self._embeddings = embeddings
        self._planner = planner
        # Writing canonical inclusion (⑤ §5 B). When absent, a canonical_memory
        # step produces no items (the need is simply unserved), so existing
        # Writing requests without it are unchanged.
        self._canonical_memory_retriever = canonical_memory_retriever
        # Writing candidate inclusion (⑤ §5 B follow-up). Same absent-is-unserved
        # contract as canonical, so requests without it are unchanged.
        self._candidate_memory_retriever = candidate_memory_retriever
        self._wall_clock_seconds = wall_clock_seconds
        self._vector_hit_limit = vector_hit_limit
        self._recent_scene_block_limit = recent_scene_block_limit
        self._canonical_memory_limit = canonical_memory_limit
        self._candidate_memory_limit = candidate_memory_limit
        self._clock = clock

    async def build_context_package(
        self, request: ContextSearchRequest
    ) -> ContextPackage:
        self._validate_request(request)
        started = self._clock()
        plan = await self._build_plan(request)
        self._validate_plan(plan, request)

        step_traces: list[SearchStepTrace] = []
        items_in_plan_order: list[ContextItem] = []
        degraded = False
        for step in plan.steps:
            for tool in step.tools:
                self._check_wall_clock(started)
                trace, items = self._execute_step_tool(step, tool, request)
                step_traces.append(trace)
                items_in_plan_order.extend(items)
                if trace.failure is not None:
                    degraded = True

        ranked = self._rank(items_in_plan_order, request)
        included, budget_excluded = self._apply_budget(
            ranked, request.context_budget
        )
        macro = tuple(item for item in included if item.need in MACRO_NEEDS)
        micro = tuple(item for item in included if item.need not in MACRO_NEEDS)
        return ContextPackage(
            project_id=request.project_id,
            purpose=request.purpose,
            macro_items=macro,
            micro_evidence=micro,
            constraints=(),
            do_not_use=(),
            token_estimate_total=sum(item.token_estimate for item in included),
            degraded=degraded,
            trace=ContextSearchTrace(
                plan=plan,
                steps=tuple(step_traces),
                budget_excluded=budget_excluded,
            ),
        )

    def _validate_request(self, request: ContextSearchRequest) -> None:
        if not request.needs:
            raise InvalidContextSearchRequest("needs must not be empty")
        if request.context_budget.max_tokens <= 0:
            raise InvalidContextSearchRequest(
                "context_budget.max_tokens must be positive"
            )
        position_needs = set(request.needs) & set(MACRO_NEEDS)
        if position_needs and request.current_position is None:
            raise InvalidContextSearchRequest(
                "current_position is required for "
                + ", ".join(sorted(need.value for need in position_needs))
            )

    async def _build_plan(self, request: ContextSearchRequest) -> SearchPlan:
        try:
            result = self._planner.build_plan(request)
            if inspect.isawaitable(result):
                result = await result
            return result
        except ContextSearchFailed:
            # The terminal-JSON planner already classifies its own failures
            # (e.g. llm_error); preserve that lineage instead of re-wrapping.
            raise
        except ProviderError as exc:
            # A Gateway/provider failure (timeout/unavailable/5xx) raised by
            # the planner's provider turn is an LLM-tier error → llm_error →
            # 502 at the HTTP boundary. This is the context-search counterpart
            # of the compare endpoint's explicit ``except ProviderError`` (the
            # provider call lives at the service layer here, so the Context
            # SearchFailed lineage is applied here, not at the endpoint). The
            # generic catch below would also reach llm_error; this explicit
            # branch keeps the intent legible and refactor-safe.
            raise ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR,
                f"planner provider error: {exc}",
            ) from exc
        except Exception as exc:
            raise ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR,
                f"planner failed: {exc}",
            ) from exc

    def _validate_plan(
        self, plan: SearchPlan, request: ContextSearchRequest
    ) -> None:
        if plan.project_id != request.project_id:
            raise ContextSearchFailed(
                ContextSearchErrorType.LLM_ERROR,
                "plan project_id does not match request project_id",
            )
        requested = set(request.needs)
        for step in plan.steps:
            if step.need not in requested:
                raise ContextSearchFailed(
                    ContextSearchErrorType.LLM_ERROR,
                    f"plan step {step.step_id} targets unrequested need "
                    f"{step.need.value}",
                )
            if not step.tools:
                raise ContextSearchFailed(
                    ContextSearchErrorType.LLM_ERROR,
                    f"plan step {step.step_id} has no tools",
                )
            allowed = NEED_ALLOWED_TOOLS[step.need]
            for tool in step.tools:
                if tool not in allowed:
                    raise ContextSearchFailed(
                        ContextSearchErrorType.LLM_ERROR,
                        f"tool {tool.value} is not allowed for need "
                        f"{step.need.value}",
                    )

    def _check_wall_clock(self, started: float) -> None:
        if self._clock() - started > self._wall_clock_seconds:
            raise ContextSearchBudgetExceeded(
                f"wall clock budget of {self._wall_clock_seconds}s exceeded"
            )

    def _execute_step_tool(
        self,
        step,
        tool: SearchTool,
        request: ContextSearchRequest,
    ) -> tuple[SearchStepTrace, tuple[ContextItem, ...]]:
        if step.need is ContextNeed.CANONICAL_MEMORY:
            return self._run_canonical_memory_step(step, request)
        if step.need is ContextNeed.CANDIDATE_MEMORY:
            return self._run_candidate_memory_step(step, request)
        if tool is SearchTool.VECTOR:
            return self._run_vector_step(step, request)
        return self._run_mongo_step(step, request)

    def _run_canonical_memory_step(
        self, step, request: ContextSearchRequest
    ) -> tuple[SearchStepTrace, tuple[ContextItem, ...]]:
        if self._canonical_memory_retriever is None:
            # The need is unserved in this deployment; emit an empty (non-failing)
            # step so an unwired canonical_memory request degrades to no memories.
            return (
                SearchStepTrace(
                    step_id=step.step_id,
                    need=step.need,
                    tool=SearchTool.MONGO,
                    hits_considered=0,
                    items_produced=0,
                    excluded=(),
                    failure=None,
                ),
                (),
            )
        try:
            entries = self._canonical_memory_retriever.retrieve(
                project_id=request.project_id,
                query=step.query or request.query,
                limit=self._canonical_memory_limit,
            )
        except Exception as exc:
            return (
                SearchStepTrace(
                    step_id=step.step_id,
                    need=step.need,
                    tool=SearchTool.MONGO,
                    hits_considered=0,
                    items_produced=0,
                    excluded=(),
                    failure=StepFailure(
                        error_type=ContextSearchErrorType.BACKEND_ERROR,
                        detail=f"canonical memory retrieval failed: {exc}",
                    ),
                ),
                (),
            )
        items = tuple(self._item_from_memory(step.need, entry) for entry in entries)
        return (
            SearchStepTrace(
                step_id=step.step_id,
                need=step.need,
                tool=SearchTool.MONGO,
                hits_considered=len(entries),
                items_produced=len(items),
                excluded=(),
                failure=None,
            ),
            items,
        )

    def _item_from_memory(
        self, need: ContextNeed, entry: MemoryEntry
    ) -> ContextItem:
        # The memory store is the authority (there is no source-block snapshot),
        # so the pointer names the memory collection/version and the Gate
        # re-validates against the store, not a SOT snapshot (D3/D4). Text uses
        # the same projection as the vector index (derive_memory_index_text) for
        # a stable rendering. snapshot_id/content_hash/sot_reloaded are required
        # ContextItem fields but inert here: the Gate's origin branch
        # (pointer.collection == MEMORIES_COLLECTION) bypasses the source-block
        # _gate_stale_findings that would otherwise read them.
        text = derive_memory_index_text(entry.memory_type, entry.payload)
        return ContextItem(
            need=need,
            status=ContextItemStatus.CANONICAL,
            text=text,
            pointer=IndexPointer(
                project_id=entry.project_id,
                collection=MEMORIES_COLLECTION,
                document_id=entry.id,
                version_id=str(entry.version),
                content_hash="",
            ),
            snapshot_id="",
            sot_reloaded=True,
            token_estimate=estimate_tokens(text),
            source_ref_ids=entry.source_ref_ids,
        )

    def _run_candidate_memory_step(
        self, step, request: ContextSearchRequest
    ) -> tuple[SearchStepTrace, tuple[ContextItem, ...]]:
        if self._candidate_memory_retriever is None:
            # Unserved in this deployment; emit an empty (non-failing) step so an
            # unwired candidate_memory request degrades to no candidates.
            return (
                SearchStepTrace(
                    step_id=step.step_id,
                    need=step.need,
                    tool=SearchTool.MONGO,
                    hits_considered=0,
                    items_produced=0,
                    excluded=(),
                    failure=None,
                ),
                (),
            )
        try:
            candidates = self._candidate_memory_retriever.retrieve(
                project_id=request.project_id,
                query=step.query or request.query,
                limit=self._candidate_memory_limit,
            )
        except Exception as exc:
            return (
                SearchStepTrace(
                    step_id=step.step_id,
                    need=step.need,
                    tool=SearchTool.MONGO,
                    hits_considered=0,
                    items_produced=0,
                    excluded=(),
                    failure=StepFailure(
                        error_type=ContextSearchErrorType.BACKEND_ERROR,
                        detail=f"candidate memory retrieval failed: {exc}",
                    ),
                ),
                (),
            )
        items = tuple(
            self._item_from_candidate(step.need, candidate)
            for candidate in candidates
        )
        return (
            SearchStepTrace(
                step_id=step.step_id,
                need=step.need,
                tool=SearchTool.MONGO,
                hits_considered=len(candidates),
                items_produced=len(items),
                excluded=(),
                failure=None,
            ),
            items,
        )

    def _item_from_candidate(
        self, need: ContextNeed, candidate: AnalysisCandidate
    ) -> ContextItem:
        # Candidate items are labeled ``candidate`` (never disguised as canonical,
        # Phase 6 §62) and carry review_status so a consumer knows they are
        # unreviewed (D4=B). The authority is the analysis store; the Gate's
        # candidate-origin branch (pointer.collection == CANDIDATES_COLLECTION)
        # re-validates against it. Text reuses derive_memory_index_text (the
        # same projection as memory), so it never leaks the vector index text.
        # snapshot_id/content_hash/sot_reloaded are inert here (same as memory).
        text = derive_memory_index_text(candidate.candidate_type, candidate.payload)
        return ContextItem(
            need=need,
            status=ContextItemStatus.CANDIDATE,
            text=text,
            pointer=IndexPointer(
                project_id=candidate.project_id,
                collection=CANDIDATES_COLLECTION,
                document_id=candidate.id,
                version_id="",
                content_hash="",
            ),
            snapshot_id="",
            sot_reloaded=True,
            token_estimate=estimate_tokens(text),
            source_ref_ids=candidate.source_ref_ids,
            review_status=str(candidate.status),
        )

    def _run_vector_step(
        self, step, request: ContextSearchRequest
    ) -> tuple[SearchStepTrace, tuple[ContextItem, ...]]:
        try:
            vector = self._embeddings.embed(step.query or request.query)
            hits = self._vector_search.query_similar(
                project_id=request.project_id,
                vector=vector,
                limit=self._vector_hit_limit,
            )
        except Exception as exc:
            return (
                SearchStepTrace(
                    step_id=step.step_id,
                    need=step.need,
                    tool=SearchTool.VECTOR,
                    hits_considered=0,
                    items_produced=0,
                    excluded=(),
                    failure=StepFailure(
                        error_type=ContextSearchErrorType.BACKEND_ERROR,
                        detail=f"vector retrieval failed: {exc}",
                    ),
                ),
                (),
            )

        items: list[ContextItem] = []
        excluded: list[ExcludedHit] = []
        for hit in hits:
            try:
                validation = self._indexing.validate_source_block_record(hit)
            except Exception as exc:
                raise ContextSearchFailed(
                    ContextSearchErrorType.SOT_ERROR,
                    f"SOT validation reload failed for record {hit.id}: {exc}",
                ) from exc
            if not validation.usable:
                excluded.append(
                    ExcludedHit(
                        record_id=hit.id,
                        reason=",".join(
                            reason.value for reason in validation.stale_reasons
                        ),
                    )
                )
                continue
            item = self._reload_hit_from_sot(hit, step.need, request)
            if item is None:
                excluded.append(
                    ExcludedHit(record_id=hit.id, reason="snapshot_missing")
                )
                continue
            items.append(item)
        return (
            SearchStepTrace(
                step_id=step.step_id,
                need=step.need,
                tool=SearchTool.VECTOR,
                hits_considered=len(hits),
                items_produced=len(items),
                excluded=tuple(excluded),
                failure=None,
            ),
            tuple(items),
        )

    def _reload_hit_from_sot(
        self,
        hit: SourceBlockIndexRecord,
        need: ContextNeed,
        request: ContextSearchRequest,
    ) -> ContextItem | None:
        try:
            detail = self._core_sot.get_snapshot(
                project_id=request.project_id, snapshot_id=hit.snapshot_id
            )
        except NotFound:
            # Index drift: the snapshot vanished from the SOT, so the hit is
            # excluded as stale rather than failing the whole request.
            return None
        except Exception as exc:
            # Any non-NotFound exception escaping a SOT reload call is an SOT
            # reload failure (backend down included), never a raw escape.
            raise ContextSearchFailed(
                ContextSearchErrorType.SOT_ERROR,
                f"SOT reload failed for record {hit.id}: {exc}",
            ) from exc
        block = next(
            (block for block in detail.blocks if block.id == hit.block_id), None
        )
        if block is None:
            return None
        return self._item_from_block(
            need=need,
            block=block,
            version_id=detail.snapshot.version_id,
            content_hash=detail.snapshot.content_hash,
        )

    def _run_mongo_step(
        self, step, request: ContextSearchRequest
    ) -> tuple[SearchStepTrace, tuple[ContextItem, ...]]:
        position = request.current_position
        assert position is not None  # guaranteed by _validate_request
        try:
            detail = self._core_sot.get_draft_version(
                project_id=request.project_id,
                draft_id=position.draft_id,
                version_id=position.version_id,
            )
        except Exception as exc:
            # Missing position (NotFound) and backend failures both mean the
            # requested position cannot be honestly reloaded: full failure.
            raise ContextSearchFailed(
                ContextSearchErrorType.SOT_ERROR,
                f"SOT position reload failed: {exc}",
            ) from exc
        current, recent = _split_scene_blocks(
            detail.blocks, recent_limit=self._recent_scene_block_limit
        )
        blocks = current if step.need is ContextNeed.CURRENT_SCENE else recent
        items = tuple(
            self._item_from_block(
                need=step.need,
                block=block,
                version_id=detail.snapshot.version_id,
                content_hash=detail.snapshot.content_hash,
            )
            for block in blocks
        )
        return (
            SearchStepTrace(
                step_id=step.step_id,
                need=step.need,
                tool=SearchTool.MONGO,
                hits_considered=len(blocks),
                items_produced=len(items),
                excluded=(),
                failure=None,
            ),
            items,
        )

    def _item_from_block(
        self,
        *,
        need: ContextNeed,
        block: SourceBlock,
        version_id: str,
        content_hash: str,
    ) -> ContextItem:
        return ContextItem(
            need=need,
            status=ContextItemStatus.CANONICAL,
            text=block.text,
            pointer=IndexPointer(
                project_id=block.project_id,
                collection=SOURCE_BLOCK_COLLECTION,
                document_id=block.id,
                version_id=version_id,
                content_hash=content_hash,
            ),
            snapshot_id=block.snapshot_id,
            sot_reloaded=True,
            token_estimate=estimate_tokens(block.text),
        )

    def _rank(
        self,
        items: list[ContextItem],
        request: ContextSearchRequest,
    ) -> tuple[ContextItem, ...]:
        # Stable sort: within one need the arrival order is preserved, which
        # is similarity order for vector steps and positional order for
        # Mongo direct steps (ties inside a step are already deterministic).
        need_priority = {need: index for index, need in enumerate(request.needs)}
        return tuple(sorted(items, key=lambda item: need_priority[item.need]))

    def _apply_budget(
        self,
        ranked: tuple[ContextItem, ...],
        budget: ContextBudget,
    ) -> tuple[tuple[ContextItem, ...], tuple[ExcludedHit, ...]]:
        included: list[ContextItem] = []
        excluded: list[ExcludedHit] = []
        total = 0
        for item in ranked:
            if total + item.token_estimate <= budget.max_tokens:
                included.append(item)
                total += item.token_estimate
            else:
                excluded.append(
                    ExcludedHit(
                        record_id=item.pointer.document_id,
                        reason=BUDGET_EXCLUDED_REASON,
                    )
                )
        return tuple(included), tuple(excluded)


def _split_scene_blocks(
    blocks: tuple[SourceBlock, ...], *, recent_limit: int
) -> tuple[tuple[SourceBlock, ...], tuple[SourceBlock, ...]]:
    """Split snapshot blocks into (current scene, recent preceding blocks).

    The current scene is the paragraph run after the last heading/scene
    marker; scenes are derived from deterministic SOT block kinds, never
    from AI inference.
    """
    boundary = -1
    for index, block in enumerate(blocks):
        if block.kind in (BlockKind.HEADING, BlockKind.SCENE_MARKER):
            boundary = index
    current = tuple(
        block
        for block in blocks[boundary + 1 :]
        if block.kind is BlockKind.PARAGRAPH
    )
    preceding = tuple(
        block
        for block in blocks[: boundary + 1]
        if block.kind is BlockKind.PARAGRAPH
    )
    recent = preceding[-recent_limit:] if recent_limit > 0 else ()
    return current, recent


def evaluate_context_gate(
    *,
    package: ContextPackage,
    request: ContextSearchRequest,
    core_sot: CoreSotService,
    memory_service: MemoryService | None = None,
    analysis_service: AnalysisService | None = None,
) -> GateDecision:
    """Independent Context Gate check; never replaced by loop preflight.

    Re-derives item validity from the authority instead of trusting the
    orchestration flags, by item origin (``pointer.collection``): source-block
    items reload from the SOT snapshot; canonical-memory items (⑤) re-validate
    against the memory store (still ``canonical``); candidate items (⑤ follow-up)
    re-validate against the analysis store (still ``needs_review``). Candidate
    status is allowed ONLY through the candidate origin — a candidate-status item
    on any other origin stays rejected (the Writing safety line is narrowed, not
    lifted; Phase 6 §62).
    """
    findings: list[GateFinding] = []
    items = package.macro_items + package.micro_evidence
    for item in items:
        if item.pointer.project_id != request.project_id:
            findings.append(
                GateFinding(
                    check="cross_project_item",
                    detail=f"item {item.pointer.document_id} belongs to "
                    f"project {item.pointer.project_id}",
                )
            )
            continue
        if not item.sot_reloaded:
            findings.append(
                GateFinding(
                    check="missing_sot_reload",
                    detail=f"item {item.pointer.document_id} was not "
                    "reloaded from SOT",
                )
            )
        is_candidate_origin = item.pointer.collection == CANDIDATES_COLLECTION
        # Candidate status is allowed ONLY through the candidate origin. On any
        # other origin (memory or source-block) a candidate-status item is still
        # prohibited — the Writing safety line is narrowed to the sanctioned
        # candidate path, not lifted (v1.6.48 contract retained, Phase 6 §62).
        if item.status is ContextItemStatus.CANDIDATE and not is_candidate_origin:
            findings.append(
                GateFinding(
                    check="candidate_item_not_allowed",
                    detail=f"item {item.pointer.document_id} carries "
                    "candidate-status memory from a non-candidate origin, "
                    "which is not allowed in Writing context",
                )
            )
        if item.pointer.collection == MEMORIES_COLLECTION:
            findings.extend(
                _gate_memory_findings(item, request, memory_service)
            )
        elif is_candidate_origin:
            findings.extend(
                _gate_candidate_findings(item, request, analysis_service)
            )
        else:
            findings.extend(_gate_stale_findings(item, request, core_sot))
    total = sum(item.token_estimate for item in items)
    if total > request.context_budget.max_tokens:
        findings.append(
            GateFinding(
                check="budget_exceeded",
                detail=f"package estimate {total} exceeds budget "
                f"{request.context_budget.max_tokens}",
            )
        )
    if findings:
        return GateDecision(decision=GATE_REJECT, findings=tuple(findings))
    return GateDecision(decision=GATE_PASS, findings=())


def _gate_memory_findings(
    item: ContextItem,
    request: ContextSearchRequest,
    memory_service: MemoryService | None,
) -> tuple[GateFinding, ...]:
    # Canonical-memory items have no SOT snapshot; the authority is the memory
    # store. Re-validate that the memory still exists, is still canonical (a
    # superseded/deleted version is stale), and belongs to the project (D4).
    if memory_service is None:
        return (
            GateFinding(
                check="memory_gate_unconfigured",
                detail=f"memory item {item.pointer.document_id} cannot be "
                "validated without a memory service",
            ),
        )
    try:
        entry = memory_service.get_memory(
            project_id=request.project_id, memory_id=item.pointer.document_id
        )
    except MemoryNotFound:
        return (
            GateFinding(
                check="stale_item",
                detail=f"memory {item.pointer.document_id} is missing or "
                "belongs to another project",
            ),
        )
    if entry.status is not MemoryStatus.CANONICAL:
        return (
            GateFinding(
                check="stale_item",
                detail=f"memory {item.pointer.document_id} is no longer "
                f"canonical (status {entry.status.value})",
            ),
        )
    return ()


def _gate_candidate_findings(
    item: ContextItem,
    request: ContextSearchRequest,
    analysis_service: AnalysisService | None,
) -> tuple[GateFinding, ...]:
    # Candidate items have no SOT snapshot; the authority is the analysis store.
    # Re-validate that the candidate still exists, is still needs_review (a
    # promoted/removed candidate is stale — it must not linger as unreviewed
    # evidence), and belongs to the project (D3=A). Mirrors _gate_memory_findings.
    if analysis_service is None:
        return (
            GateFinding(
                check="candidate_gate_unconfigured",
                detail=f"candidate item {item.pointer.document_id} cannot be "
                "validated without an analysis service",
            ),
        )
    try:
        candidate = analysis_service.get_candidate(
            project_id=request.project_id,
            candidate_id=item.pointer.document_id,
        )
    except AnalysisNotFound:
        return (
            GateFinding(
                check="stale_item",
                detail=f"candidate {item.pointer.document_id} is missing or "
                "belongs to another project",
            ),
        )
    if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
        return (
            GateFinding(
                check="stale_item",
                detail=f"candidate {item.pointer.document_id} is no longer "
                f"needs_review (status {candidate.status.value})",
            ),
        )
    return ()


def _gate_stale_findings(
    item: ContextItem,
    request: ContextSearchRequest,
    core_sot: CoreSotService,
) -> tuple[GateFinding, ...]:
    try:
        detail = core_sot.get_snapshot(
            project_id=request.project_id, snapshot_id=item.snapshot_id
        )
    except NotFound:
        return (
            GateFinding(
                check="stale_item",
                detail=f"snapshot {item.snapshot_id} is missing for item "
                f"{item.pointer.document_id}",
            ),
        )
    except Exception as exc:
        # The gate must not turn an unverifiable package into a pass or a
        # misattributed reject; SOT backend failure keeps its sot_error
        # lineage here too.
        raise ContextSearchFailed(
            ContextSearchErrorType.SOT_ERROR,
            f"gate SOT reload failed for item {item.pointer.document_id}: {exc}",
        ) from exc
    findings: list[GateFinding] = []
    if detail.snapshot.content_hash != item.pointer.content_hash:
        findings.append(
            GateFinding(
                check="stale_item",
                detail=f"content hash drifted for item "
                f"{item.pointer.document_id}",
            )
        )
    if all(block.id != item.pointer.document_id for block in detail.blocks):
        findings.append(
            GateFinding(
                check="stale_item",
                detail=f"block {item.pointer.document_id} is missing from "
                f"snapshot {item.snapshot_id}",
            )
        )
    try:
        project = core_sot.get_project(project_id=request.project_id)
        draft = core_sot.get_draft(
            project_id=request.project_id, draft_id=detail.snapshot.draft_id
        )
    except Exception as exc:
        raise ContextSearchFailed(
            ContextSearchErrorType.SOT_ERROR,
            f"gate SOT reload failed for item {item.pointer.document_id}: {exc}",
        ) from exc
    if project.archived:
        findings.append(
            GateFinding(
                check="stale_item",
                detail=f"project {request.project_id} is archived",
            )
        )
    if draft.archived:
        findings.append(
            GateFinding(
                check="stale_item",
                detail=f"draft {detail.snapshot.draft_id} is archived",
            )
        )
    return tuple(findings)
