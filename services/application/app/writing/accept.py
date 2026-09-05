"""Phase 5.3 accept orchestration: Gate pass → SOT save → pending analysis job.

W3 (W0 contract §3) adds an explicit Writing ``intent``:

* ``append_current`` keeps the original three-surface append and its legacy
  save-key-only replay (WI-17): no receipt is written.
* ``start_next_unit`` opens the next ordered unit through Core SOT's six-surface
  atomic write (positions, Draft, version, snapshot, block, receipt) and replays
  via the durable accept receipt.

Both intents converge on the same snapshot-scoped Analysis job (§3.2) and the
same partial-success contract when that job cannot be created.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.application.app.analysis.models import AnalysisJob
from services.application.app.analysis.service import AnalysisService
from services.application.app.context_search.models import ContextPackage
from services.application.app.core_sot.models import (
    Draft, SaveDraftResult,
)
from services.application.app.core_sot.repository import (
    DuplicateWritingAcceptReceipt,
)
from services.application.app.core_sot.service import (
    Archived,
    CoreSotService,
    DraftOrderIntegrityError,
    NotFound,
)
from services.application.app.env import draft_raw_text_max_chars
from services.application.app.writing.context_pointer import pointer_wire
from services.application.app.writing.gate import WritingGateService
from services.application.app.writing.service import CandidateReporter
from services.application.app.writing.models import (
    WritingCandidate, WritingGateDecision, WritingGateResult, WritingIntent,
    WritingOutputType, WritingRequest, WritingTaskType,
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
    def __init__(self, message: str, *, saved: SaveDraftResult,
                 intent: WritingIntent, target_draft: Draft) -> None:
        super().__init__(message)
        self.saved = saved
        self.intent = intent
        self.target_draft = target_draft


@dataclass(frozen=True, slots=True)
class WritingAcceptResult:
    accepted: bool
    gate: WritingGateResult | None
    saved: SaveDraftResult | None
    analysis_job: AnalysisJob | None
    intent: WritingIntent = WritingIntent.APPEND_CURRENT
    # The Draft the save targeted (append: the current draft; start: the new
    # Scene). Carries chapter_id/position for the response `saved` envelope. None
    # only when nothing was saved (Gate non-pass).
    target_draft: Draft | None = None
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
        # D5-2(오너 2026-08-27, "전 경로 4000자"): 유닛 본문 상한을 **provider 호출
        # 앞에** 시행한다 — 상한을 넘을 몸은 enrich·gate 어느 쪽에도 돈을 쓸 수 없다.
        # append_current 는 합성 결과(base + "\n\n" + patch)를, start_next_unit 은
        # 씨앗 본문(candidate)을 잰다. ★ 이 검사는 replay 조회보다도 앞이다(2026-08-27
        # 검증 보강 1 — `_validate` 가 이미 replay 앞에 있는 것과 같은 부류의 설계 선택):
        # 같은 멱등키의 재시도가 상한 이전에 성공 저장했더라도, env 상한이 그 사이 내려가
        # 있으면 수렴(200)이 아니라 400을 낸다. 발화 조건이 env 변경뿐이라 셀로 의도를
        # 핀했다(test_draft_raw_text_limit — replay-after-lowering).
        self._enforce_raw_text_limit(
            request=request, draft_id=draft_id,
            base_version_id=base_version_id, candidate_text=candidate.text)
        draft = self._core_sot.get_draft(
            project_id=request.project_id, draft_id=draft_id)
        chapters = self._core_sot.list_chapters(project_id=request.project_id)
        chapter = next(
            (item for item in chapters if item.id == draft.chapter_id), None
        )
        if (
            chapter is None
            or draft.position is None
            or draft.unit_kind is not None
        ):
            raise DraftOrderIntegrityError(
                "scene hierarchy migration is required"
            )
        project = self._core_sot.get_project(project_id=request.project_id)
        if project.archived or chapter.archived or draft.archived:
            raise Archived("project, chapter, or draft is archived")
        save_key = f"writing-accept:{idempotency_key}"
        intent = request.intent

        # Replay lookup precedes stale-base and Gate (§3.3, WI-19) — and, since
        # S-1 (감사 §A.1 말미), the provider call too: the same idempotency_key
        # used to re-run reporter.enrich before converging on the stored unit,
        # so every replay burned a real report call for nothing. The un-enriched
        # candidate on this path is harmless — _create_job is idempotent per
        # snapshot and the original accept already minted that job, so the
        # report payload built here is discarded, not stored.
        replay = self._replay(request.project_id, draft_id, save_key, intent)
        if replay is not None:
            saved, target = replay
            return self._finalize(request.project_id, saved, candidate,
                                  intent, target, gate=None, replay=True)
        if self._reporter is not None:
            candidate = await self._reporter.enrich(candidate, package)

        base = self._core_sot.get_draft_version(
            project_id=request.project_id, draft_id=draft_id,
            version_id=base_version_id)
        versions = self._core_sot.list_draft_versions(
            project_id=request.project_id, draft_id=draft_id)
        if versions[-1].id != base.draft_version.id:
            raise StaleWritingBase("base draft version is not the latest version")
        gate = await self._gate.evaluate(
            request=request, candidate=candidate, package=package)
        if gate.decision is not WritingGateDecision.PASS:
            return WritingAcceptResult(False, gate, None, None, intent, None)

        text = candidate.text.strip()
        if intent is WritingIntent.START_NEXT_UNIT:
            try:
                result = self._core_sot.start_next_unit(
                    project_id=request.project_id, current_draft_id=draft_id,
                    raw_text=text, title=request.next_unit.title,
                    goal_intent=intent.value, idempotency_key=save_key)
            except DuplicateWritingAcceptReceipt:
                # Concurrent same-key race: converge on the committed unit.
                # The duplicate says another transaction *wrote* the receipt,
                # not that this one can *read* it yet — before that commit is
                # visible the replay lookup still comes back empty. Fail closed
                # on the caller's own error so a retry can converge; unpacking
                # None here raised TypeError instead.
                replay = self._replay(
                    request.project_id, draft_id, save_key, intent)
                if replay is None:
                    raise
                saved, target = replay
                return self._finalize(request.project_id, saved, candidate,
                                      intent, target, gate=None, replay=True)
            saved = SaveDraftResult(result.draft_version, result.snapshot,
                                    result.blocks, idempotent_replay=False)
            target = result.draft
        else:
            raw_text = _append_patch(base.snapshot.raw_text, text)
            saved = self._core_sot.save_draft(
                project_id=request.project_id, draft_id=draft_id,
                raw_text=raw_text, idempotency_key=save_key)
            target = draft
        return self._finalize(request.project_id, saved, candidate, intent,
                              target, gate=gate, replay=saved.idempotent_replay)

    def _enforce_raw_text_limit(self, *, request: WritingRequest,
                                draft_id: str, base_version_id: str,
                                candidate_text: str) -> None:
        """유닛 본문 상한(app/env.py draft_raw_text_max_chars)을 provider 호출 앞에 잰다.

        base 읽기가 실패해도 여기서 죽이지 않는다 — replay/404/409 순서(§3.3)는
        아래 원래 흐름이 소유한다. 이 조회는 산술을 위한 조용한 읽기일 뿐이다.
        측정은 strip 후다 — 이 경로가 저장하는 패치/씨앗이 strip 된 것이고, 저장 축
        (SaveDraftRequest)이 strip 전 원문을 재는 것과 대칭이다(각 축은 자기가 저장하는
        것을 잰다 — 2026-08-27 검증 보강 3).
        """
        limit = draft_raw_text_max_chars()
        text = candidate_text.strip()
        if request.intent is WritingIntent.START_NEXT_UNIT:
            if len(text) > limit:
                raise WritingAcceptError(
                    f"candidate text must contain at most {limit} characters")
            return
        try:
            base = self._core_sot.get_draft_version(
                project_id=request.project_id, draft_id=draft_id,
                version_id=base_version_id)
        except NotFound:
            return
        if len(_append_patch(base.snapshot.raw_text, text)) > limit:
            raise WritingAcceptError(
                f"accepted text would exceed the {limit}-character unit limit")

    def _replay(self, project_id: str, draft_id: str, save_key: str,
                intent: WritingIntent) -> tuple[SaveDraftResult, Draft] | None:
        """Return (saved, target_draft) for a same-key replay, else None.

        start_next uses the durable receipt (whose target may be a different
        draft); append reads through the legacy version idempotency key so
        pre-receipt append records still replay (WI-17).
        """
        if intent is WritingIntent.START_NEXT_UNIT:
            receipt = self._core_sot.get_writing_accept_receipt(
                project_id=project_id, idempotency_key=save_key)
            if receipt is None:
                return None
            saved = self._save_result(
                project_id, receipt.draft_id, receipt.draft_version_id)
            target = self._core_sot.get_draft(
                project_id=project_id, draft_id=receipt.draft_id)
            return saved, target
        versions = self._core_sot.list_draft_versions(
            project_id=project_id, draft_id=draft_id)
        version = next(
            (v for v in versions if v.idempotency_key == save_key), None)
        if version is None:
            return None
        saved = self._save_result(project_id, draft_id, version.id)
        target = self._core_sot.get_draft(
            project_id=project_id, draft_id=draft_id)
        return saved, target

    def _finalize(self, project_id: str, saved: SaveDraftResult,
                  candidate: WritingCandidate, intent: WritingIntent,
                  target: Draft, *, gate: WritingGateResult | None,
                  replay: bool) -> WritingAcceptResult:
        try:
            job = self._create_job(project_id, saved, candidate)
        except Exception as exc:
            raise WritingAcceptAnalysisError(
                str(exc), saved=saved, intent=intent,
                target_draft=target) from exc
        return WritingAcceptResult(True, gate, saved, job, intent, target, replay)

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
        # Intent/next_unit binding, before any provider or write (§3.1).
        if candidate.intent != request.intent:
            raise WritingAcceptError("candidate intent does not match request")
        if candidate.next_unit != request.next_unit:
            raise WritingAcceptError("candidate next_unit does not match request")
        if request.intent is WritingIntent.APPEND_CURRENT:
            if request.next_unit is not None:
                raise WritingAcceptError(
                    "append_current must not carry next_unit")
        else:
            next_unit = request.next_unit
            if next_unit is None:
                raise WritingAcceptError(
                    "start_next_unit requires next_unit")
            if not next_unit.title.strip():
                raise WritingAcceptError("next_unit.title must not be blank")
            if next_unit.goal is not None and not next_unit.goal.strip():
                raise WritingAcceptError(
                    "next_unit.goal must be a nonblank string or null")


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
