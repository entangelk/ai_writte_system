"""Phase 5.3 accept orchestration: Gate pass → SOT save → pending analysis job."""

from __future__ import annotations

from dataclasses import dataclass

from services.application.app.analysis.models import AnalysisJob
from services.application.app.analysis.service import AnalysisService
from services.application.app.context_search.models import ContextPackage
from services.application.app.core_sot.models import SaveDraftResult
from services.application.app.core_sot.service import Archived, CoreSotService
from services.application.app.writing.context_pointer import pointer_wire
from services.application.app.writing.gate import WritingGateService
from services.application.app.writing.service import CandidateReporter
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateResult, WritingOutputType,
    WritingRequest, WritingTaskType,
)


def analysis_job_key(snapshot_id: str) -> str:
    """Per-snapshot analysis-job idempotency key (D5=A alignment).

    Both accept (which enqueues the pending job) and the explicit "이 원고 분석"
    trigger derive the SAME key from the snapshot, so create_job's
    (project, snapshot, key) tuple resolves to one shared job per snapshot. The
    frontend `analyzeVersion` (client.ts) mirrors this exact literal.
    """
    return f"analyze:{snapshot_id}"


class WritingAcceptError(ValueError):
    pass


class StaleWritingBase(WritingAcceptError):
    pass


class WritingAcceptAnalysisError(RuntimeError):
    def __init__(self, message: str, *, saved: SaveDraftResult) -> None:
        super().__init__(message)
        self.saved = saved


@dataclass(frozen=True, slots=True)
class WritingAcceptResult:
    accepted: bool
    gate: WritingGateResult | None
    saved: SaveDraftResult | None
    analysis_job: AnalysisJob | None
    idempotent_replay: bool = False


class WritingAcceptService:
    def __init__(self, *, core_sot: CoreSotService,
                 analysis: AnalysisService, gate: WritingGateService,
                 reporter: CandidateReporter | None = None) -> None:
        self._core_sot = core_sot
        self._analysis = analysis
        self._gate = gate
        self._reporter = reporter

    async def accept(self, *, draft_id: str, base_version_id: str,
                     idempotency_key: str, request: WritingRequest,
                     candidate: WritingCandidate,
                     package: ContextPackage) -> WritingAcceptResult:
        self._validate(draft_id, base_version_id, idempotency_key,
                       request, candidate, package)
        if self._reporter is not None:
            candidate = await self._reporter.enrich(candidate, package)
        save_key = f"writing-accept:{idempotency_key}"
        draft = self._core_sot.get_draft(
            project_id=request.project_id, draft_id=draft_id)
        project = self._core_sot.get_project(project_id=request.project_id)
        if project.archived or draft.archived:
            raise Archived("project or draft is archived")
        versions = self._core_sot.list_draft_versions(
            project_id=request.project_id, draft_id=draft_id)
        replay = next((v for v in versions if v.idempotency_key == save_key), None)
        if replay is not None:
            saved = self._save_result(request.project_id, draft_id, replay.id)
            try:
                job = self._create_job(request.project_id, saved, candidate)
            except Exception as exc:
                raise WritingAcceptAnalysisError(str(exc), saved=saved) from exc
            return WritingAcceptResult(True, None, saved, job, True)

        base = self._core_sot.get_draft_version(
            project_id=request.project_id, draft_id=draft_id,
            version_id=base_version_id)
        if versions[-1].id != base.draft_version.id:
            raise StaleWritingBase("base draft version is not the latest version")
        gate = await self._gate.evaluate(
            request=request, candidate=candidate, package=package)
        if gate.decision is not WritingGateDecision.PASS:
            return WritingAcceptResult(False, gate, None, None)
        raw_text = _append_patch(base.snapshot.raw_text, candidate.text.strip())
        saved = self._core_sot.save_draft(
            project_id=request.project_id, draft_id=draft_id,
            raw_text=raw_text, idempotency_key=save_key)
        try:
            job = self._create_job(request.project_id, saved, candidate)
        except Exception as exc:
            raise WritingAcceptAnalysisError(str(exc), saved=saved) from exc
        return WritingAcceptResult(True, gate, saved, job, saved.idempotent_replay)

    def _create_job(self, project_id: str, saved: SaveDraftResult,
                    candidate: WritingCandidate) -> AnalysisJob:
        # D5=A alignment (owner, 2026-07-18): the analysis job key is derived from
        # the SNAPSHOT, not the accept idempotency key, so the explicit "이 원고
        # 분석" trigger (which only knows the snapshot) reuses THIS same job
        # instead of minting a new one — realizing D5=A "후속 run이 같은 job을
        # 소비". create_job's idempotency tuple is (project, snapshot, key), so a
        # per-snapshot key gives one job per snapshot: accept-replay (same accept
        # → same snapshot) and the trigger both converge on it. (Amends the D4=A
        # `writing-accept:{key}` analysis-key literal; the save key is unchanged.)
        return self._analysis.create_job(
            project_id=project_id, snapshot_id=saved.snapshot.id,
            idempotency_key=analysis_job_key(saved.snapshot.id),
            writing_candidate_report=_candidate_report_payload(
                candidate)).job

    def _save_result(self, project_id: str, draft_id: str,
                     version_id: str) -> SaveDraftResult:
        detail = self._core_sot.get_draft_version(
            project_id=project_id, draft_id=draft_id, version_id=version_id)
        return SaveDraftResult(detail.draft_version, detail.snapshot,
                               detail.blocks, True)

    @staticmethod
    def _validate(draft_id: str, base_version_id: str, key: str,
                  request: WritingRequest, candidate: WritingCandidate,
                  package: ContextPackage) -> None:
        if not draft_id or not base_version_id or not key:
            raise WritingAcceptError(
                "draft_id, base_version_id, and idempotency_key are required")
        if request.task_type is not WritingTaskType.CONTINUE_SCENE:
            raise WritingAcceptError("only continue_scene is supported")
        if candidate.output_type is not WritingOutputType.DRAFT_PATCH:
            raise WritingAcceptError("only draft_patch is supported")
        if not request.instruction.strip() or not candidate.text.strip():
            raise WritingAcceptError("instruction and candidate text are required")
        if candidate.request_id != request.request_id:
            raise WritingAcceptError("candidate belongs to a different request")
        if candidate.project_id != request.project_id or package.project_id != request.project_id:
            raise WritingAcceptError("writing accept inputs belong to different projects")


def _candidate_report_payload(candidate: WritingCandidate) -> dict[str, object]:
    return {
        "self_reported_constraints": list(candidate.self_reported_constraints),
        "candidate_claims": [{"text": x.text, "type": x.claim_type.value,
            "requires_gate_check": x.requires_gate_check,
            "related_context_pointers": [
                pointer_wire(p) for p in x.related_context_pointers]}
            for x in candidate.candidate_claims],
        "new_memory_hints": [{"type": x.hint_type.value, "text": x.text,
            "confidence": x.confidence,
            "should_analyze_after_save": x.should_analyze_after_save}
            for x in candidate.new_memory_hints],
        "risk_notes": [{"type": x.risk_type.value,
            "severity": x.severity.value, "message": x.message}
            for x in candidate.risk_notes],
    }


def _append_patch(base: str, patch: str) -> str:
    if not base:
        return patch
    if base.endswith("\n"):
        return base + patch
    return base + "\n\n" + patch
