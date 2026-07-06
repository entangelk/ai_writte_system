"""Phase 2B.2: prior-memory search and the Analysis comparison package (§8 ⑧).

This slice is "search + packaging", not judgment (D1=A): it collects the coarse
candidate group — canonical memories of the requested ``memory_type``(s) in the
same project — and packages them for Analysis compare (2B.3) to judge. Identity
matching and scope-key precision are 2B.3.

The search backend is injected (D2=A + seam): the first slice is a deterministic
key lookup, but a later LLM/semantic query generator plugs into the same
``PriorMemoryBackend`` interface without touching the packaging or Gate layers.
"""

from __future__ import annotations

from typing import Protocol

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.context_search.models import (
    AnalysisContextRequest,
    ContextNeed,
    ContextPackage,
    ContextSearchPurpose,
    GATE_PASS,
    GATE_REJECT,
    GateDecision,
    GateFinding,
    PriorMemoryItem,
)
from services.application.app.context_search.service import estimate_tokens
from services.application.app.memory.models import MemoryEntry, MemoryStatus
from services.application.app.memory.service import MemoryService


class AnalysisContextError(Exception):
    pass


class InvalidAnalysisContextRequest(AnalysisContextError):
    pass


class PriorMemoryBackend(Protocol):
    """Injection seam for prior-memory retrieval (D2=A semantic seam).

    A deterministic key lookup implements it now; a later semantic backend
    implements the same method so the packaging layer never changes.
    """

    def search_prior_memories(
        self,
        *,
        project_id: str,
        memory_types: tuple[AnalysisCandidateType, ...],
        exclude_job_id: str | None,
    ) -> tuple[MemoryEntry, ...]: ...


class DeterministicPriorMemoryBackend:
    """Coarse deterministic lookup over the canonical memory store.

    Returns canonical memories in ``project_id`` whose ``memory_type`` is in
    ``memory_types`` (empty ``memory_types`` → empty result, never all), minus
    any memory whose ``analysis_job_id`` equals ``exclude_job_id`` (F4).
    """

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    def search_prior_memories(
        self,
        *,
        project_id: str,
        memory_types: tuple[AnalysisCandidateType, ...],
        exclude_job_id: str | None,
    ) -> tuple[MemoryEntry, ...]:
        wanted = set(memory_types)
        if not wanted:
            return ()
        results = [
            entry
            # The canonical-only filter is a contract lock ("prior canonical
            # memories"). Phase 2B.4 introduced MemoryStatus.SUPERSEDED, so the
            # non-canonical-excluded direction is now regression-tested by
            # test_superseded_memories_excluded_from_prior_memory (2B.2 O1).
            for entry in self._memory.list_memories(project_id=project_id)
            if entry.status is MemoryStatus.CANONICAL
            and entry.memory_type in wanted
            and not (
                exclude_job_id is not None
                and entry.analysis_job_id == exclude_job_id
            )
        ]
        return tuple(results)


class AnalysisContextService:
    def __init__(self, *, backend: PriorMemoryBackend) -> None:
        self._backend = backend

    def build_prior_memory_package(
        self, request: AnalysisContextRequest
    ) -> ContextPackage:
        self._validate_request(request)
        entries = self._backend.search_prior_memories(
            project_id=request.project_id,
            memory_types=request.memory_types,
            exclude_job_id=request.exclude_job_id,
        )
        items = tuple(_prior_memory_item(entry) for entry in entries)
        return ContextPackage(
            project_id=request.project_id,
            purpose=ContextSearchPurpose.ANALYSIS_CONTEXT,
            macro_items=(),
            micro_evidence=(),
            constraints=(),
            do_not_use=(),
            token_estimate_total=sum(_value_tokens(item) for item in items),
            degraded=False,
            trace=None,
            prior_memories=items,
        )

    def _validate_request(self, request: AnalysisContextRequest) -> None:
        if not request.needs:
            raise InvalidAnalysisContextRequest("needs must not be empty")
        for need in request.needs:
            if need is not ContextNeed.PRIOR_MEMORY:
                raise InvalidAnalysisContextRequest(
                    f"analysis_context only serves prior_memory, not {need.value}"
                )


def _prior_memory_item(entry: MemoryEntry) -> PriorMemoryItem:
    return PriorMemoryItem(
        memory_id=entry.id,
        memory_type=entry.memory_type,
        value=entry.payload,
        status=entry.status,
        version=entry.version,
        source_ref_ids=entry.source_ref_ids,
        # First-slice retrieval reason is the deterministic coarse match: the
        # memory shares the requested candidate group (memory_type). Semantic
        # match reasons arrive with the semantic backend (D2 seam).
        match_reason=f"memory_type matches {entry.memory_type.value}",
        scope=entry.scope,
    )


def _value_tokens(item: PriorMemoryItem) -> int:
    text = " ".join(str(value) for value in item.value.values())
    return estimate_tokens(text)


def evaluate_analysis_context_gate(
    *, package: ContextPackage, request: AnalysisContextRequest
) -> GateDecision:
    """Purpose-branched Gate for analysis_context (D5=A).

    The Writing Gate's candidate-prohibition is not applicable here: this
    package carries only canonical memories, so candidate leakage has no target.
    The one analysis_context invariant is that no Writing item (macro/micro)
    smuggles into the package that Analysis compare consumes. Cross-project
    isolation is guaranteed upstream by the project-scoped lookup contract (F5),
    so it is not re-checked here — PriorMemoryItem intentionally carries no
    project_id (D3 five fields). A non-canonical check is omitted because
    MemoryStatus is CANONICAL-only today (no impossible-scenario guard).
    """
    findings: list[GateFinding] = []
    if package.macro_items or package.micro_evidence:
        findings.append(
            GateFinding(
                check="writing_item_in_analysis_package",
                detail="analysis_context package must carry only prior_memories",
            )
        )
    if findings:
        return GateDecision(decision=GATE_REJECT, findings=tuple(findings))
    return GateDecision(decision=GATE_PASS, findings=())
