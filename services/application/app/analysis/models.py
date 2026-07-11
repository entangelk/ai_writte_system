"""Phase 2A analysis candidate contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class AnalysisCandidateType(StrEnum):
    CHARACTER_OBSERVATION = "character_observation"
    EVENT_OBSERVATION = "event_observation"
    OPEN_QUESTION_OBSERVATION = "open_question_observation"


class AnalysisProvenance(StrEnum):
    SOURCE_OBSERVED = "source_observed"
    AI_INFERRED = "ai_inferred"


class AnalysisCandidateAction(StrEnum):
    CREATE = "create"


class AnalysisCandidateStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    # Phase 6 review state transition (v1.6.61): a reviewer confirms (approved →
    # promoted to canonical) or rejects a candidate. Both leave needs_review, so
    # the candidate is de-indexed and no longer surfaces as candidate evidence.
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AnalysisJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisJobFailureReason(StrEnum):
    SNAPSHOT_NOT_FOUND = "snapshot_not_found"
    SOURCE_INVALID = "source_invalid"
    SCHEMA_INVALID = "schema_invalid"
    PROVIDER_ERROR = "provider_error"
    DUPLICATE_CONFLICT = "duplicate_conflict"


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    id: str
    project_id: str
    snapshot_id: str
    idempotency_key: str
    status: AnalysisJobStatus = AnalysisJobStatus.PENDING
    failure_reason: AnalysisJobFailureReason | None = None
    failure_detail: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisTask:
    id: str
    project_id: str
    job_id: str
    candidate_type: AnalysisCandidateType


@dataclass(frozen=True, slots=True)
class AnalysisCandidate:
    id: str
    project_id: str
    job_id: str
    task_id: str
    candidate_type: AnalysisCandidateType
    action: AnalysisCandidateAction
    status: AnalysisCandidateStatus
    provenance: AnalysisProvenance
    confidence: float
    source_ref_ids: tuple[str, ...]
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CreateAnalysisJobResult:
    job: AnalysisJob
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class RecordAnalysisCandidateResult:
    candidate: AnalysisCandidate
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class AnalysisCandidateRecordRequest:
    task_id: str
    logical_key: str
    candidate_type: AnalysisCandidateType
    action: AnalysisCandidateAction
    provenance: AnalysisProvenance
    confidence: float
    source_ref_ids: Sequence[str]
    payload: Mapping[str, Any]
    source_anchors: Sequence["CandidateSourceAnchor"] | None = None


@dataclass(frozen=True, slots=True)
class CandidateSourceAnchor:
    source_ref_id: str
    start_offset: int
    end_offset: int
    quote: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class SnapshotText:
    project_id: str
    snapshot_id: str
    raw_text: str
    content_hash: str
    block_ids: tuple[str, ...]


def immutable_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(payload))
