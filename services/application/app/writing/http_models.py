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

from services.application.app.core_sot.models import UnitKind
from services.application.app.writing.models import (
    CandidateClaimType,
    MemoryHintType,
    RiskNoteType,
    RiskSeverity,
    WritingGateDecision,
    WritingGateFindingType,
    WritingGateSeverity,
    WritingIntent,
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
    # W3 (§3.3): both intents expose the target Draft's kind/position. For
    # append the target is the current draft; for start_next_unit it is the new
    # unit created at current position + 1.
    draft_id: str
    draft_version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str
    unit_kind: UnitKind
    position: int


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
    intent: WritingIntent
    gate: WritingGatePayload | None
    saved: AcceptedSavePayload | None
    analysis_job: AnalysisJobPayload | None
    idempotent_replay: bool


class WritingGenerationJobPayload(BaseModel):
    # Async generation job status (async-pad D3=B/D4=A/D5=A, v1.7.27 = 증분 2c).
    # This is the GET .../writing/generation-jobs/{job_id} success body, AND the
    # nested ``job`` inside the 202 generate-accepted envelope. ``status`` is a
    # plain str (the StrEnum's value, "pending|running|succeeded|failed") matching
    # the AnalysisJobPayload precedent; failure_reason likewise. Exact-width — a
    # too-narrow model would silently drop fields from the public status surface.
    job_id: str
    request_id: str
    project_id: str
    draft_id: str
    version_id: str
    task_type: str
    output_length: str
    status: str
    created_at: str
    result_scratch_id: str | None = None
    failure_reason: str | None = None
    failure_detail: str | None = None


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
    # 502 after the unit is already saved: accepted=true + intent + saved
    # present, but the pending Analysis job could not be created. Distinct from a
    # plain error. Applies to both intents (§3.3, WI-13/WI-20).
    accepted: bool
    intent: WritingIntent
    saved: AcceptedSavePayload
    analysis_job: AnalysisJobPayload | None
    analysis_error: str


class WritingGenerationJobAcceptedPayload(BaseModel):
    # 202 Accepted body returned by POST .../writing/generate for an async preset
    # (medium/long). Mirrors the Analysis create_job envelope shape
    # (``{"job": ..., "idempotent_replay": bool}``). Returned via JSONResponse so it
    # bypasses response_model validation; this model is responses={} documentation
    # only, and the exact-key regression is its runtime lock (same pattern as the
    # partial envelopes above).
    job: WritingGenerationJobPayload
    idempotent_replay: bool


# --- responses={} maps (OpenAPI docs for the non-200 statuses) -------------
#
# A partial-capable status documents the Union of its partial envelope and the
# generic detail; a status that is always a plain error documents only detail.

_REVISE_GATE_PARTIAL = {"model": Union[WritingReviseGatePartial, ErrorDetailResponse]}
_DETAIL_ONLY = {"model": ErrorDetailResponse}

# D8-3a: both endpoints below are protected operations (main._REQUIRE_AUTH), so
# 401 is realistic for them exactly as it is for the operations declared through
# main._protected. It is always a plain error — the request never reaches the
# handler, so no partial work can have been persisted.
REVISE_AND_GATE_RESPONSES: dict[int | str, dict] = {
    400: _REVISE_GATE_PARTIAL,
    401: _DETAIL_ONLY,
    404: _DETAIL_ONLY,
    502: _REVISE_GATE_PARTIAL,
    503: _REVISE_GATE_PARTIAL,
    504: _REVISE_GATE_PARTIAL,
}

# accept is the only endpoint whose 503 carries BOTH faces the SoT distinguishes
# (v1.7.29): a collaborator missing from the deployment, and — since H3 S5 closed
# the start_next_unit 500 leak — stored draft metadata predating the W3
# ordered-unit invariant. Neither is fixable by resending the request, but the
# operator actions differ, so the declaration names both instead of making the
# reader infer which one they hit from a log.
_ACCEPT_503 = {
    "model": ErrorDetailResponse,
    "description": "Server-side action required before this request can succeed: "
                   "either a collaborator is not configured in this deployment, "
                   "or stored draft metadata predates the ordered-unit invariant "
                   "(run scripts/migrate_ordered_units.py). Retrying the request "
                   "alone cannot succeed. The canonical store may also be "
                   "unreachable or failing; in that case recover it and retry the "
                   "same request unchanged.",
}

ACCEPT_RESPONSES: dict[int | str, dict] = {
    400: _DETAIL_ONLY,
    401: _DETAIL_ONLY,
    404: _DETAIL_ONLY,
    409: _DETAIL_ONLY,
    502: {"model": Union[WritingAcceptAnalysisPartial, ErrorDetailResponse]},
    503: _ACCEPT_503,
    504: _DETAIL_ONLY,
}

# Async generate (async-pad D5=A, v1.7.27 = 증분 2c): medium/long presets are
# enqueued for background worker execution and the endpoint returns 202 Accepted
# with the job reference instead of blocking on a candidate. 200 stays the
# synchronous short-preset candidate (response_model=WritingCandidatePayload); 202
# is the divergent success arm, documented here via the established responses={}
# mechanism (same shape as REVISE_AND_GATE_RESPONSES / ACCEPT_RESPONSES).
GENERATE_ASYNC_RESPONSES: dict[int | str, dict] = {
    202: {
        "model": WritingGenerationJobAcceptedPayload,
        "description": "Async preset accepted — the generation job was enqueued "
                       "for background execution; poll GET .../generation-jobs/{job_id}.",
    },
}
