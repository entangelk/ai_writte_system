"""Writing HTTP response contract models (Phase 5 C0, SoT v1.7.1, D3=A).

Frontend Writing 작업공간(C slice)이 소비하는 generate/gate/revise-and-gate/accept
응답을 OpenAPI에서 실제 타입으로 노출하기 위한 Pydantic 모델. 브리프
``docs/plans/frontend-writing-workspace-decisions.md`` D3=A / ``ARCH-1`` 첫 단계에
따라 Writing HTTP 모델만 별도 모듈로 분리한다(``main.py`` 전 도메인 router 일괄
분리는 하지 않는다).

두 가지 계약 표면이 있다:

* **성공 경로**는 평범한 dict를 반환하므로 route의 ``response_model=``이 적용된다.
  FastAPI는 모델이 선언하지 않은 필드를 **조용히 삭제**하므로(오류·경고 0),
  각 모델은 payload와 **정확히 같은 너비**여야 한다. 완전한 key 집합은 착수 전
  ``Writing*EnvelopeKeyTest``(exact-key 안전망)로 먼저 잠갔다.
* **partial-failure 경로**는 ``JSONResponse``로 직접 반환돼 runtime response
  validation을 **우회**한다. 따라서 아래 partial 모델은 ``responses={}``의
  OpenAPI 문서화 전용이며, 실제 payload는 exact-key 회귀가 유일한 runtime lock이다.

payload 빌더(``main.py`` ``_writing_*_payload``)는 손대지 않는다(D2=A와 동형): 모델은
그 dict를 검증·직렬화만 한다.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel

from services.application.app.writing.models import (
    CandidateClaimType,
    MemoryHintType,
    RiskNoteType,
    RiskSeverity,
    WritingGateDecision,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingOutputType,
    WritingTaskType,
)
from services.application.app.writing.revise_gate import (
    WritingLoopStageName,
    WritingLoopStageStatus,
    WritingLoopStatus,
)


# --- Reusable component models --------------------------------------------

class ContextPointerPayload(BaseModel):
    # Stable pointer projection (writing/context_pointer.pointer_wire); project_id
    # excluded (D1=A). Origin-specific fields may be "" (P-i invariant).
    collection: str
    document_id: str
    version_id: str
    content_hash: str


class CandidateClaimPayload(BaseModel):
    text: str
    # Public wire uses `type`, never the internal dataclass name `claim_type`.
    type: CandidateClaimType
    requires_gate_check: bool
    related_context_pointers: list[ContextPointerPayload]


class MemoryHintPayload(BaseModel):
    type: MemoryHintType
    text: str
    confidence: float
    should_analyze_after_save: bool


class RiskNotePayload(BaseModel):
    type: RiskNoteType
    severity: RiskSeverity
    message: str


class WritingCandidatePayload(BaseModel):
    request_id: str
    project_id: str
    task_type: WritingTaskType
    output_type: WritingOutputType
    text: str
    # Always the literal "candidate" (WRITING_CANDIDATE_STATUS); a plain str
    # rather than an enum because it is a fixed status marker, not a taxonomy.
    status: str
    self_reported_constraints: list[str]
    candidate_claims: list[CandidateClaimPayload]
    new_memory_hints: list[MemoryHintPayload]
    risk_notes: list[RiskNotePayload]
    candidate_id: str | None
    generated_by_model: str


class WritingGateFindingPayload(BaseModel):
    type: WritingGateFindingType
    severity: WritingGateSeverity
    message: str
    evidence: str
    recommended_decision: WritingGateDecision


class WritingGatePayload(BaseModel):
    request_id: str
    project_id: str
    decision: WritingGateDecision
    findings: list[WritingGateFindingPayload]
    checked_constraints: list[str]
    evaluated_by_model: str


class WritingLoopPayload(BaseModel):
    status: WritingLoopStatus
    revision_rounds: int
    retrieval_rounds: int
    gate_evaluations: int


class WritingStagePayload(BaseModel):
    stage: WritingLoopStageName
    ordinal: int
    status: WritingLoopStageStatus


class WritingStageError(BaseModel):
    # The typed error carried by a partial loop envelope's *_error discriminator
    # and by audit_error. `type` is a stage-specific error_type string
    # (e.g. "provider_timeout", "invalid_gate_result", "audit_persist_error").
    type: str
    detail: str


class AcceptedSavePayload(BaseModel):
    draft_version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


class AnalysisJobPayload(BaseModel):
    id: str
    project_id: str
    snapshot_id: str
    status: str
    failure_reason: str | None
    failure_detail: str | None


class ErrorDetailResponse(BaseModel):
    # FastAPI's generic HTTPException shape. A partial-capable status can carry
    # EITHER a partial envelope OR this generic detail, expressed as a Union in
    # ``responses={}`` so the frontend types both arms.
    detail: str


# --- Success response models ----------------------------------------------
#
# generate → WritingCandidatePayload, gate → WritingGatePayload (reused directly).

class WritingReviseGateResponse(BaseModel):
    candidate: WritingCandidatePayload
    gate: WritingGatePayload | None
    loop: WritingLoopPayload
    stages: list[WritingStagePayload]
    audit_id: str | None
    audit_error: WritingStageError | None


class WritingAcceptResponse(BaseModel):
    accepted: bool
    gate: WritingGatePayload | None
    saved: AcceptedSavePayload | None
    analysis_job: AnalysisJobPayload | None
    idempotent_replay: bool


# --- Partial-failure envelope models (responses={} documentation only) -----
#
# These are returned via JSONResponse and bypass response_model validation, so
# they are documentation-only; the exact-key regressions are their runtime lock.

class WritingReviseGatePartial(BaseModel):
    # Every partial carries the common loop surface plus EXACTLY ONE *_error
    # discriminator (the runtime payload omits the other three keys entirely).
    # Modelling all four as optional expresses the union for OpenAPI so the
    # frontend can branch on whichever discriminator is present.
    candidate: WritingCandidatePayload
    gate: WritingGatePayload | None
    loop: WritingLoopPayload
    stages: list[WritingStagePayload]
    audit_id: str | None
    audit_error: WritingStageError | None
    report_error: WritingStageError | None = None
    revision_error: WritingStageError | None = None
    retrieval_error: WritingStageError | None = None
    gate_error: WritingStageError | None = None


class WritingAcceptAnalysisPartial(BaseModel):
    # 502 after the version is already saved: accepted=true + saved present, but
    # the pending Analysis job could not be created. Distinct from a plain error.
    accepted: bool
    saved: AcceptedSavePayload
    analysis_job: AnalysisJobPayload | None
    analysis_error: str


# --- responses={} maps (OpenAPI docs for the non-200 statuses) -------------
#
# A partial-capable status documents the Union of its partial envelope and the
# generic detail; a status that is always a plain error documents only detail.

_REVISE_GATE_PARTIAL = {"model": Union[WritingReviseGatePartial, ErrorDetailResponse]}
_DETAIL_ONLY = {"model": ErrorDetailResponse}

REVISE_AND_GATE_RESPONSES: dict[int | str, dict] = {
    400: _REVISE_GATE_PARTIAL,
    404: _DETAIL_ONLY,
    502: _REVISE_GATE_PARTIAL,
    503: _REVISE_GATE_PARTIAL,
    504: _REVISE_GATE_PARTIAL,
}

ACCEPT_RESPONSES: dict[int | str, dict] = {
    400: _DETAIL_ONLY,
    404: _DETAIL_ONLY,
    409: _DETAIL_ONLY,
    502: {"model": Union[WritingAcceptAnalysisPartial, ErrorDetailResponse]},
    503: _DETAIL_ONLY,
    504: _DETAIL_ONLY,
}
