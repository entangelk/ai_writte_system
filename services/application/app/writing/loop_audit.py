"""Durable audit trail for the Writing bounded revise/retrieve loop.

Phase 5.9 L9 B (brief ``05-writing-persisted-loop-audit-decisions.md``):
every ``/writing/revise-and-gate`` termination (normal or partial failure)
leaves one **append-only, immutable** record. Records are never collapsed
by retry (P3=A: a fresh id per run) and never auto-deleted (P5=A: retention
is a named operational follow-up, not part of this slice) so old runs stay
available as verification reference. Records are bodyless except the final
candidate text: intermediate stages carry only hashes/fingerprints/pointers
(P1=B). No token/latency fields — those wait on B2 usage plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol
from uuid import uuid4

from services.application.app.writing.audit_hash import (
    finding_fingerprint,
    hash_text,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateFinding,
    WritingGateResult,
)
from services.application.app.writing.revise_gate import (
    WritingLoopStage,
    WritingLoopSummary,
)


@dataclass(frozen=True, slots=True)
class StoredLoopStage:
    stage: str
    ordinal: int
    status: str
    candidate_hash: str | None
    finding_fingerprint: str | None
    pointer_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredWritingLoopRun:
    id: str
    project_id: str
    request_id: str
    loop_status: str
    revision_rounds: int
    retrieval_rounds: int
    gate_evaluations: int
    error_type: str | None
    trigger_finding_fingerprint: str
    initial_candidate_hash: str
    final_candidate_hash: str
    final_candidate_text: str
    final_gate_decision: str | None
    final_gate_finding_fingerprints: tuple[str, ...]
    stages: tuple[StoredLoopStage, ...]
    created_at: datetime


class WritingLoopAuditRepository(Protocol):
    def add(self, run: StoredWritingLoopRun) -> None: ...
    def get(self, run_id: str) -> StoredWritingLoopRun | None: ...
    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredWritingLoopRun, ...]: ...


class InMemoryWritingLoopAuditRepository:
    def __init__(self) -> None:
        self.entries: dict[str, StoredWritingLoopRun] = {}

    def add(self, run: StoredWritingLoopRun) -> None:
        self.entries[run.id] = run

    def get(self, run_id: str) -> StoredWritingLoopRun | None:
        return self.entries.get(run_id)

    def list_for_project(
        self, project_id: str
    ) -> tuple[StoredWritingLoopRun, ...]:
        return tuple(sorted(
            (run for run in self.entries.values()
             if run.project_id == project_id),
            key=lambda run: (run.created_at, run.id),
            reverse=True,
        ))


class WritingLoopAuditError(RuntimeError):
    pass


class WritingLoopAuditNotFound(WritingLoopAuditError):
    pass


class WritingLoopAuditService:
    def __init__(
        self, repository: WritingLoopAuditRepository, *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: "wla:" + uuid4().hex)

    def record(
        self, *, project_id: str, request_id: str,
        trigger_finding: WritingGateFinding, initial_candidate_text: str,
        summary: WritingLoopSummary, stages: tuple[WritingLoopStage, ...],
        final_candidate: WritingCandidate, gate: WritingGateResult | None,
        error_type: str | None,
    ) -> StoredWritingLoopRun:
        run = StoredWritingLoopRun(
            id=self._id_factory(),
            project_id=project_id,
            request_id=request_id,
            loop_status=summary.status.value,
            revision_rounds=summary.revision_rounds,
            retrieval_rounds=summary.retrieval_rounds,
            gate_evaluations=summary.gate_evaluations,
            error_type=error_type,
            trigger_finding_fingerprint=finding_fingerprint(trigger_finding),
            initial_candidate_hash=hash_text(initial_candidate_text),
            final_candidate_hash=hash_text(final_candidate.text),
            final_candidate_text=final_candidate.text,
            final_gate_decision=(
                None if gate is None else gate.decision.value
            ),
            final_gate_finding_fingerprints=(
                () if gate is None
                else tuple(finding_fingerprint(f) for f in gate.findings)
            ),
            stages=tuple(_stored_stage(stage) for stage in stages),
            created_at=self._clock(),
        )
        self._repo.add(run)
        return run

    def list_runs(self, project_id: str) -> tuple[StoredWritingLoopRun, ...]:
        return self._repo.list_for_project(project_id)

    def get(
        self, *, project_id: str, run_id: str
    ) -> StoredWritingLoopRun:
        run = self._repo.get(run_id)
        if run is None or run.project_id != project_id:
            raise WritingLoopAuditNotFound("writing loop audit run not found")
        return run


def _stored_stage(stage: WritingLoopStage) -> StoredLoopStage:
    return StoredLoopStage(
        stage=stage.stage.value,
        ordinal=stage.ordinal,
        status=stage.status.value,
        candidate_hash=stage.candidate_hash,
        finding_fingerprint=stage.finding_fingerprint,
        pointer_ids=tuple(stage.pointer_ids),
    )
