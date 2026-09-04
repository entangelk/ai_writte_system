"""정체성 그룹 승인 액션(정체성 그룹 Slice 5).

계약(`pending-candidate-identity-grouping-implementation-phases.md` Slice 5 +
착수 브리프 `pending-candidate-identity-grouping-slice5-approval-orchestration-decisions.md`
D1=A·D2=A·D3=A·D4=A, 오너 2026-09-04):
- ``POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/approve`` 는 owner만
  실행한다(401/403은 전수 행렬이 잠근다 — 이 파일은 도메인 동작만 본다).
- **D1=A** — 요청 body ``{"expected_revision": N}``. revision이 멱등 key를 겸한다:
  같은 revision 재전송은 replay/이어가기, 그룹 현재 revision과의 불일치는 409(detail에
  현재 revision).
- **그룹의 첫 eligible 후보가 canonical이 된다**(승격 = 개별 confirm 경로 그대로).
  나머지는 **그룹 canonical을 강제 대상**으로 compare judge에 넣어
  update/add_evidence/no_change/conflict로 수렴한다 — scope matcher를 다시 돌리지
  않으므로 두 번째 canonical이 만들어지지 않는다(canonical 중복 생성 방지).
- **각 member step은 pending|applied|conflict|failed|skipped 와 결과 memory/version
  id를 저장**한다(신규 approval 상태 저장). 재시도는 applied step을 재실행하지 않는다.
- **D2=A** — applied(update·add_evidence·no_change) 멤버는 confirmed 전이 +
  de-index + 대기열 resolve(개별 confirm과 같은 부수효과). conflict 멤버는
  needs_review 잔류 + 검토 대기열 적재.
- **D3=A** — 그룹·멤버·relation 행은 바꾸지 않는다(거절과 대칭).
- **D4=A** — 판정 실패(ProviderError·parse 거부)는 그 step=failed·패스 종료.
  응답은 200에 step 상태 노출(부분 실패는 사람이 이해 — Slice 6 전제).
- **활동 로그는 그룹 행 1줄**(Slice 4 A안에 묶임) — ``identity_group_approved``·
  ``after``="applied=N, conflict=M, skipped=K", 변경≥1일 때만.

양방향 회귀:
- under-strict: 멤버를 confirmed로 만들지 않거나, 두 번째 canonical을 만들거나,
  applied step을 재실행하거나, 행을 남기지 않으면 재실패.
- over-strict: terminal 멤버를 409로 막거나, conflict 멤버를 confirmed로 만들거나,
  변경이 없는데 행을 남기면 재실패.
"""

import asyncio
import json
import unittest
from datetime import UTC, datetime

import httpx
from pymongo.errors import PyMongoError

from services.application.app.analysis.compare import CompareAction, JudgeResult
from services.application.app.analysis.compare_judge import (
    TerminalJsonCompareJudge,
    seed_analysis_compare_template,
)
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    IdentityGroupStatus,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.analysis.identity_group_approvals import (
    CandidateIdentityGroupApproval,
    CandidateIdentityGroupApprovalService,
    GroupApprovalStep,
    GroupApprovalStepStatus,
    InMemoryCandidateIdentityGroupApprovalRepository,
)
from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
)
from services.application.app.analysis.compare import AnalysisCompareService
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import IndexSyncEvent
from services.application.app.indexing.service import (
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
)
from services.application.app.main import create_app
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallSite,
)
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from tests.auth_support import authenticate
from tests.test_llm_call_sites import _observed

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


class _FixedClock:
    """시각을 한 칸씩 전진 — 멤버 added_at 순서를 잰다(Slice 4 셀과 같은 함정 방어)."""

    def __init__(self) -> None:
        self._ticks = iter(range(0, 300, 10))
        self.now = datetime(2026, 9, 4, 10, next(self._ticks), tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self) -> None:
        self.now = datetime(2026, 9, 4, 10, next(self._ticks), tzinfo=UTC)


class _ScriptedJudge:
    """스크립트 순서대로 판정하고 (candidate_id, memory_id) 호출을 기록한다.

    스크립트 항목이 Exception이면 그대로 던진다(provider/parse 실패 축).
    """

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str]] = []

    async def judge(self, *, candidate, memory):
        self.calls.append((candidate.id, memory.id))
        item = self.results.pop(0) if self.results else JudgeResult(
            CompareAction.NO_CHANGE, "default"
        )
        if isinstance(item, Exception):
            raise item
        return item


def _update(rationale="값이 바뀌었다"):
    return JudgeResult(CompareAction.UPDATE, rationale)


def _add_evidence(rationale="같은 값, 새 출처"):
    return JudgeResult(CompareAction.ADD_EVIDENCE, rationale)


def _no_change(rationale="더할 것이 없다"):
    return JudgeResult(CompareAction.NO_CHANGE, rationale)


def _conflict(rationale="다른 인물일 수 있다"):
    return JudgeResult(CompareAction.CONFLICT, rationale)


def _gateway_down():
    return ProviderError(
        code=ProviderErrorCode.UNAVAILABLE,
        message="gateway is unavailable",
        retryable=True,
        provider="llm_gateway",
    )


class _FlakyApprovalRepository:
    """save가 N번째 호출에 PyMongoError — mid-loop 스토리지 장애 주입(Slice 4 H1 이관)."""

    def __init__(self, inner, *, fail_on: int) -> None:
        self._inner = inner
        self._fail_on = fail_on
        self.saves = 0

    def save(self, approval):
        self.saves += 1
        if self.saves == self._fail_on:
            raise PyMongoError("approval store unreachable")
        self._inner.save(approval)

    def get(self, project_id, group_id):
        return self._inner.get(project_id, group_id)

    def purge_project(self, project_id):
        self._inner.purge_project(project_id)


class TestClient:
    __test__ = False

    def __init__(self, app):
        authenticate(app)
        self._app = app

    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def _request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())


def _build(judge=None, *, audit=None, approval_repository=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    queue = ReviewQueueService(InMemoryReviewQueueRepository())
    index_repo = InMemoryIndexSyncRepository()
    clock = _FixedClock()
    groups = CandidateIdentityGroupService(
        InMemoryCandidateIdentityGroupRepository(), clock=clock
    )
    repository = approval_repository or InMemoryCandidateIdentityGroupApprovalRepository()
    approvals = CandidateIdentityGroupApprovalService(repository)
    compare = AnalysisCompareService(memory_service=memory, judge=judge)
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory,
        index_sync_outbox=IndexSyncOutboxService(index_repo),
        review_queue_service=queue,
        identity_group_service=groups,
        identity_group_approval_service=approvals,
        compare_service=compare,
        llm_call_audit_service=audit,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return {
        "client": client, "analysis": analysis, "memory": memory, "groups": groups,
        "approvals": approvals, "queue": queue, "compare": compare,
        "index_repo": index_repo, "clock": clock, "project_id": project_id,
    }


def _seed_candidate(analysis, *, project_id, logical_key, payload=None):
    job = analysis.create_job(
        project_id=project_id, snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=CHARACTER
    )
    return analysis.record_candidate(
        project_id=project_id, task_id=task.id, logical_key=logical_key,
        candidate_type=CHARACTER, action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=(f"source-{logical_key}",),
        payload=payload or {"name": "Ariel", "observation": "brave"},
    ).candidate


def _open_group(groups, project_id, *candidates):
    group = groups.create_group(project_id, CHARACTER)
    for candidate in candidates:
        groups.add_member(
            project_id=project_id, group_id=group.group_id,
            candidate_id=candidate.id, candidate_type=CHARACTER,
        )
    return group


def _approve(client, project_id, group_id, revision=0):
    return client.post(
        f"/projects/{project_id}/analysis/review-inbox/groups/{group_id}/approve",
        json={"expected_revision": revision},
    )


def _step_by(payload, candidate_id):
    return next(s for s in payload["steps"] if s["candidate_id"] == candidate_id)


def _statuses(client, project_id):
    items = client.get(
        f"/projects/{project_id}/analysis/review-inbox"
    ).json()["items"]
    return {item["candidate_id"]: item["status"] for item in items}


def _activity(client, project_id):
    response = client.get(f"/projects/{project_id}/activity")
    assert response.status_code == 200, response.text
    return response.json()["events"]


def _memories(w):
    return w["memory"].list_memories(project_id=w["project_id"])


class GroupApproveOrchestrationTest(unittest.TestCase):
    def test_first_eligible_member_becomes_the_canonical_seed(self):
        """승격 = 개별 confirm 경로 그대로 — 나머지는 그 canonical로 수렴한다."""
        w = _build(_ScriptedJudge(_no_change()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        canonical = payload["canonical_memory_id"]
        self.assertIsNotNone(canonical)
        seed = _step_by(payload, a.id)
        self.assertEqual(seed["status"], "applied")
        self.assertEqual(seed["action"], "create")
        self.assertEqual(seed["memory_id"], canonical)
        self.assertEqual(seed["version"], 1)
        # seed(a)의 canonical이 실제로 mint됐고 그 멤버는 confirmed다.
        seed_memory = w["memory"].get_memory(
            project_id=w["project_id"], memory_id=canonical)
        self.assertEqual(seed_memory.source_candidate_id, a.id)
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=a.id
            ).status.value, "confirmed"
        )
        self.assertFalse(payload["idempotent_replay"])

    def test_an_update_member_replaces_the_canonical_payload(self):
        w = _build(_ScriptedJudge(_update()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(
            w["analysis"], project_id=w["project_id"], logical_key="b",
            payload={"name": "Ariel", "observation": "braver"},
        )
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        b_step = _step_by(payload, b.id)
        self.assertEqual(b_step["status"], "applied")
        self.assertEqual(b_step["action"], "update")
        self.assertEqual(b_step["version"], 2)
        # 버전 upsert — 새 canonical이 seed의 v1을 supersede하고 payload는 b의 것.
        new_canonical = w["memory"].get_memory(
            project_id=w["project_id"], memory_id=b_step["memory_id"])
        self.assertEqual(new_canonical.payload["observation"], "braver")
        self.assertEqual(
            new_canonical.supersedes, _step_by(payload, a.id)["memory_id"]
        )
        # 응답의 canonical 포인터는 버전 적용 뒤의 최신(v2)이다.
        self.assertEqual(payload["canonical_memory_id"], b_step["memory_id"])
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=b.id
            ).status.value, "confirmed"
        )
        # D2=A: conflict 없는 승인은 검토함을 비운다.
        self.assertEqual(_statuses(w["client"], w["project_id"]), {})

    def test_an_add_evidence_member_preserves_payload_and_unions_sources(self):
        w = _build(_ScriptedJudge(_add_evidence()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        b_step = _step_by(response.json(), b.id)
        self.assertEqual(b_step["action"], "add_evidence")
        new_canonical = w["memory"].get_memory(
            project_id=w["project_id"], memory_id=b_step["memory_id"])
        self.assertEqual(new_canonical.payload["observation"], "brave")  # 보존
        self.assertIn("source-a", tuple(new_canonical.source_ref_ids))
        self.assertIn("source-b", tuple(new_canonical.source_ref_ids))  # 합집합
        self.assertEqual(new_canonical.version, 2)

    def test_a_no_change_member_is_confirmed_without_a_new_memory_write(self):
        w = _build(_ScriptedJudge(_no_change()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        b_step = _step_by(payload, b.id)
        self.assertEqual(b_step["status"], "applied")
        self.assertEqual(b_step["action"], "no_change")
        # memory write는 없다 — 프로젝트 memory는 seed의 v1 하나뿐.
        self.assertEqual(len(_memories(w)), 1)
        self.assertEqual(b_step["memory_id"], payload["canonical_memory_id"])
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=b.id
            ).status.value, "confirmed"
        )

    def test_a_conflict_member_stays_needs_review_and_queues_review(self):
        w = _build(_ScriptedJudge(_conflict()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        b_step = _step_by(payload, b.id)
        self.assertEqual(b_step["status"], "conflict")
        self.assertEqual(b_step["action"], "conflict")
        self.assertEqual(b_step["memory_id"], payload["canonical_memory_id"])
        # 후보는 needs_review 잔류 + 검토 대기열에 OPEN 행(적용 경로와 같은 모양).
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=b.id
            ).status.value, "needs_review"
        )
        open_entries = w["queue"].list_open(w["project_id"])
        self.assertEqual([e.candidate_id for e in open_entries], [b.id])
        self.assertEqual(
            open_entries[0].matched_memory_id, payload["canonical_memory_id"]
        )

    def test_the_judge_target_is_always_the_group_canonical(self):
        """canonical 중복 생성 방지 — 대상은 scope matcher가 아니라 그룹 canonical이다.

        스파이 judge가 받은 memory가 seed canonical 그 하나여야 한다. judge가 그
        canonical을 받지 못하고 스스로 대상을 고른다면(예: create 폴스루) 이 셀과
        감사 상관 셀이 같이 물린다.
        """
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        canonical = response.json()["canonical_memory_id"]
        self.assertEqual(judge.calls, [(b.id, canonical)])
        # 프로젝트 memory는 seed canonical 하나뿐 — 두 번째 canonical이 없다.
        self.assertEqual(len(_memories(w)), 1)

    def test_an_individually_promoted_member_is_adopted_not_duplicated(self):
        """승격된 멤버가 있는 그룹은 그 memory를 canonical로 채택한다.

        잃어버린 approval 문서의 재구성 축이자(저장 실패 창) "개별 승격 뒤 그룹
        승인" 경로의 중복 방지다 — 채택이 없으면 seed가 두 번째 canonical을 mint한다.
        """
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)
        # b가 그룹 밖에서 개별 승격됐다(상태는 needs_review 유지).
        self.assertEqual(w["client"].post(
            f"/projects/{w['project_id']}/analysis/candidates/{b.id}/promote"
        ).status_code, 200)
        promoted = _memories(w)
        self.assertEqual(len(promoted), 1)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        # 채택: canonical은 b가 이미 가진 memory다(새 mint 아님).
        self.assertEqual(payload["canonical_memory_id"], promoted[0].id)
        # a는 그 canonical로 수렴하고, 두 번째 canonical은 생기지 않는다.
        self.assertEqual(judge.calls, [(a.id, promoted[0].id)])
        self.assertEqual(len(_memories(w)), 1)
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=b.id
            ).status.value, "confirmed"
        )

    def test_members_already_terminal_are_skipped(self):
        """terminal 멤버는 rejected로 시드한다 — confirm이 남기는 canonical이 채택
        규칙을 통해 나머지 멤버의 판정 대상을 바꾸는 간섭 없이 skip 축만 잰다."""
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        terminal = _seed_candidate(
            w["analysis"], project_id=w["project_id"], logical_key="c")
        self.assertEqual(w["client"].post(
            f"/projects/{w['project_id']}/analysis/candidates/{terminal.id}/reject"
        ).status_code, 200)
        group = _open_group(w["groups"], w["project_id"], a, b, terminal)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        t_step = _step_by(payload, terminal.id)
        self.assertEqual(t_step["status"], "skipped")
        self.assertIsNone(t_step["action"])
        self.assertIsNone(t_step["memory_id"])
        # terminal 멤버는 판정 대상이 아니다.
        judged = {candidate_id for candidate_id, _ in judge.calls}
        self.assertNotIn(terminal.id, judged)

    def test_a_judge_failure_marks_the_step_failed_and_ends_the_pass(self):
        """D4=A — ProviderError는 그 step=failed·패스 종료, 응답은 200(부분 실패 가시)."""
        judge = _ScriptedJudge(_gateway_down())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        c = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="c")
        group = _open_group(w["groups"], w["project_id"], a, b, c)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(_step_by(payload, a.id)["status"], "applied")
        self.assertEqual(_step_by(payload, b.id)["status"], "failed")
        self.assertEqual(_step_by(payload, b.id)["error"], "ProviderError")
        self.assertEqual(_step_by(payload, c.id)["status"], "pending")
        # 실패 멤버의 상태·memory는 그대로다.
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=b.id
            ).status.value, "needs_review"
        )
        self.assertEqual(len(_memories(w)), 1)

    def test_a_retry_resumes_without_reexecuting_applied_steps(self):
        """중간 실패 뒤 재시도 — applied는 재실행하지 않고 failed/pending을 이어간다."""
        judge = _ScriptedJudge(_gateway_down())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        c = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="c")
        group = _open_group(w["groups"], w["project_id"], a, b, c)
        self.assertEqual(
            _approve(w["client"], w["project_id"], group.group_id).status_code, 200
        )

        # 게이트웨이가 회복됐다 — 같은 revision으로 재호출.
        judge.results = [_no_change(), _no_change()]
        retry = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(retry.status_code, 200, retry.text)
        payload = retry.json()
        self.assertEqual(_step_by(payload, a.id)["status"], "applied")
        self.assertEqual(_step_by(payload, b.id)["status"], "applied")
        self.assertEqual(_step_by(payload, c.id)["status"], "applied")
        # seed(a)는 재실행되지 않았다 — canonical도 a의 memory도 하나뿐.
        self.assertEqual(len(_memories(w)), 1)
        self.assertEqual(payload["canonical_memory_id"], _memories(w)[0].id)
        self.assertFalse(payload["idempotent_replay"])

    def test_a_completed_approval_replay_is_a_full_noop(self):
        """같은 revision 재전송 — 저장된 step을 그대로 돌려주고 아무 것도 다시 하지 않는다."""
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)
        first = _approve(w["client"], w["project_id"], group.group_id)
        self.assertEqual(first.status_code, 200, first.text)

        replay = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["steps"], first.json()["steps"])
        self.assertTrue(replay.json()["idempotent_replay"])
        # judge 재호출 없음(판정 pair는 첫 패스의 1회뿐) · 활동 행도 늘지 않는다.
        self.assertEqual(len(judge.calls), 1)
        self.assertEqual(
            len([e for e in _activity(w["client"], w["project_id"])
                 if e["action"] == "identity_group_approved"]), 1
        )

    def test_a_revision_mismatch_is_409_with_the_current_revision_in_detail(self):
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)
        # 판정이 모순을 올렸다 — revision 0→1.
        w["groups"].set_group_status(
            w["project_id"], group.group_id, IdentityGroupStatus.CONTRADICTED
        )

        response = _approve(w["client"], w["project_id"], group.group_id, revision=0)

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("group is at revision 1", response.json()["detail"])
        # 아무 것도 시작하지 않았다.
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=a.id
            ).status.value, "needs_review"
        )
        self.assertEqual(_memories(w), ())

    def test_judge_not_configured_fails_fast_with_503_and_nothing_started(self):
        """eligible≥2인데 judge가 없으면 compare endpoint 선례대로 503 — 반쪽 상태 금지."""
        w = _build()  # judge=None
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=a.id
            ).status.value, "needs_review"
        )
        self.assertEqual(_memories(w), ())

    def test_a_single_eligible_member_approves_without_a_judge(self):
        """eligible==1이면 판정이 필요 없다 — judge 미구성 503은 남은 멤버가 있을 때뿐.

        terminal 멤버를 rejected로 시드한다 — confirm은 승격을 동반해 canonical을
        남기고, 그러면 채택 규칙이 남은 eligible 멤버를 판정 대상으로 만들어
        judge가 필요해지기 때문이다(그 경우의 503은 셀 12가 잠근다).
        """
        w = _build()  # judge=None
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        rejected = _seed_candidate(
            w["analysis"], project_id=w["project_id"], logical_key="c")
        self.assertEqual(w["client"].post(
            f"/projects/{w['project_id']}/analysis/candidates/{rejected.id}/reject"
        ).status_code, 200)
        group = _open_group(w["groups"], w["project_id"], a, rejected)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(_step_by(payload, a.id)["status"], "applied")
        self.assertEqual(_step_by(payload, rejected.id)["status"], "skipped")

    def test_a_group_with_no_eligible_members_is_a_noop_replay(self):
        w = _build(_ScriptedJudge(_no_change()))
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        for candidate in (a, b):
            self.assertEqual(w["client"].post(
                f"/projects/{w['project_id']}/analysis/candidates/{candidate.id}/confirm"
            ).status_code, 200)
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["idempotent_replay"])
        # 두 멤버 모두 개별 confirm으로 끝났다 — 채택은 가장 이른 멤버의 canonical을
        # 읽기면에 드러낼 뿐, 이 호출의 변경으로 세지 않는다(replay·행 없음).
        self.assertEqual(payload["canonical_memory_id"], _memories(w)[0].id)
        self.assertEqual(
            [s["status"] for s in payload["steps"]], ["skipped", "skipped"]
        )
        self.assertEqual(
            [e for e in _activity(w["client"], w["project_id"])
             if e["action"] == "identity_group_approved"], []
        )

    def test_a_contradicted_group_can_still_be_approved(self):
        """contradicted도 묶는다(읽기면·거절과 같은 순서) — 승인이 모순을 해소한다."""
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)
        w["groups"].set_group_status(
            w["project_id"], group.group_id, IdentityGroupStatus.CONTRADICTED
        )

        response = _approve(w["client"], w["project_id"], group.group_id, revision=1)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [s["status"] for s in response.json()["steps"]],
            ["applied", "applied"],
        )

    def test_closed_group_is_404(self):
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        group = _open_group(w["groups"], w["project_id"], a)
        w["groups"].set_group_status(
            w["project_id"], group.group_id, IdentityGroupStatus.CLOSED
        )

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 404)

    def test_unknown_group_is_404(self):
        w = _build(_ScriptedJudge(_no_change()))

        response = _approve(w["client"], w["project_id"], "cig:does-not-exist")

        self.assertEqual(response.status_code, 404)

    def test_another_projects_group_is_404_for_this_project(self):
        w = _build(_ScriptedJudge(_no_change()))
        other_id = w["client"].post("/projects", json={"name": "Other"}).json()["id"]
        foreign = _seed_candidate(
            w["analysis"], project_id=other_id, logical_key="x")
        foreign_group = _open_group(w["groups"], other_id, foreign)

        response = _approve(w["client"], w["project_id"], foreign_group.group_id)

        self.assertEqual(response.status_code, 404)

    def test_missing_project_is_404(self):
        w = _build(_ScriptedJudge(_no_change()))

        response = _approve(w["client"], "does-not-exist", "cig:any")

        self.assertEqual(response.status_code, 404)

    def test_an_applied_member_leaves_the_index_and_resolves_its_queue(self):
        """D2=A — confirm과 같은 부수효과: de-index enqueue + 열린 conflict resolve."""
        judge = _ScriptedJudge(_update())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        # b에 열린 conflict 대기열 행이 있었다 — 승인(applied)은 그것을 RESOLVED로.
        w["queue"].enqueue(
            project_id=w["project_id"], job_id=b.job_id, candidate_id=b.id,
            candidate_type=CHARACTER,
            action=CompareAction.CONFLICT, matched_memory_id="mem:old",
            rationale="prior conflict",
        )
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(w["queue"].list_open(w["project_id"]), ())
        removed = [
            entry for entry in w["index_repo"].outbox_entries.values()
            if entry.event is IndexSyncEvent.CANDIDATE_REMOVED
        ]
        # 두 멤버 모두 needs_review를 떠났다 — 개별 confirm과 같은 de-index 면.
        self.assertEqual(
            sorted(entry.source.mongo_id for entry in removed),
            sorted([a.id, b.id]),
        )


class GroupApproveActivityLogTest(unittest.TestCase):
    def test_approval_records_one_group_level_activity_row(self):
        """Slice 4 A안에 묶인 모양 — 그룹 행 1줄, after에 세 수, 멤버별 행 없음."""
        judge = _ScriptedJudge(_conflict())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        confirmed = _seed_candidate(
            w["analysis"], project_id=w["project_id"], logical_key="c")
        self.assertEqual(w["client"].post(
            f"/projects/{w['project_id']}/analysis/candidates/{confirmed.id}/confirm"
        ).status_code, 200)
        group = _open_group(w["groups"], w["project_id"], a, b, confirmed)
        _approve(w["client"], w["project_id"], group.group_id)

        events = _activity(w["client"], w["project_id"])
        rows = [e for e in events if e["action"] == "identity_group_approved"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target_type"], "candidate_identity_group")
        self.assertEqual(rows[0]["target_id"], group.group_id)
        self.assertEqual(rows[0]["after"], "applied=1, conflict=1, skipped=1")
        # 멤버별 candidate_confirmed 행은 남기지 않는다 — 같은 사실의 두 번째
        # 정본. (셋업의 개별 confirm 행은 대상이 confirmed 멤버 하나뿐이다.)
        self.assertEqual(
            [e for e in events
             if e["action"] == "candidate_confirmed"
             and e["target_id"] in (a.id, b.id)],
            [],
        )

    def test_a_noop_approval_records_no_activity_row(self):
        judge = _ScriptedJudge(_no_change())
        w = _build(judge)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)
        _approve(w["client"], w["project_id"], group.group_id)
        before = _activity(w["client"], w["project_id"])

        _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(_activity(w["client"], w["project_id"]), before)


class GroupApproveStorageFailureTest(unittest.TestCase):
    """Slice 4 검증 H1 이관 — mid-loop 스토리지 실패→503, 재호출이 이어간다."""

    def test_storage_failure_midway_answers_503_and_the_retry_resumes(self):
        judge = _ScriptedJudge(_no_change())
        flaky = _FlakyApprovalRepository(
            InMemoryCandidateIdentityGroupApprovalRepository(), fail_on=2
        )
        w = _build(judge, approval_repository=flaky)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        failed = _approve(w["client"], w["project_id"], group.group_id)

        # 503(전역 저장소 handler) — seed의 confirm/promote는 이미 durable하다.
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            w["analysis"].get_candidate(
                project_id=w["project_id"], candidate_id=a.id
            ).status.value, "confirmed"
        )
        self.assertEqual(len(_memories(w)), 1)
        # approval 문서는 첫 저장(멤버십 동기)에서만 성공 — canonical 기록 전에 죽었다.
        stored = w["approvals"].get(w["project_id"], group.group_id)
        self.assertIsNotNone(stored)
        self.assertIsNone(stored.canonical_memory_id)

        # 같은 revision 재호출 — seed의 canonical을 채택해 이어간다(재mint 금지).
        retry = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(retry.status_code, 200, retry.text)
        payload = retry.json()
        self.assertEqual(
            [s["status"] for s in payload["steps"]], ["applied", "applied"]
        )
        self.assertEqual(_step_by(payload, a.id)["action"], "create")
        # canonical은 a의 것 하나 — 503 창이 두 번째 canonical을 만들지 않았다.
        self.assertEqual(len(_memories(w)), 1)
        self.assertEqual(payload["canonical_memory_id"], _memories(w)[0].id)


class GroupApproveAuditRowsTest(unittest.TestCase):
    """실 adapter + seam C — 판정 pair당 1행·site·correlation_id=group_id·재분류.

    Slice 5는 compare judge adapter를 재사용한다(신규 site 아님 — 브리프
    "계획·선례가 이미 묶은 것"). approve endpoint가 llm_call_scope를 열어
    correlation_id=group_id로 묶는 모양을 실측한다.
    """

    def _audit(self):
        return LlmCallAuditService(InMemoryLlmCallAuditRepository())

    def _compare_judge(self, *contents):
        templates = PromptTemplateService(InMemoryPromptTemplateRepository())
        seed_analysis_compare_template(templates)
        return TerminalJsonCompareJudge(
            _observed(LlmCallSite.COMPARE_JUDGE, *contents),
            prompt_templates=templates,
        )

    @staticmethod
    def _content(action):
        return json.dumps({"action": action, "rationale": "r"}, ensure_ascii=False)

    def test_each_judged_member_leaves_exactly_one_row_under_the_group(self):
        audit = self._audit()
        judge = self._compare_judge(self._content("no_change"))
        w = _build(judge, audit=audit)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        calls = audit.list_calls(w["project_id"])
        judged = [c for c in calls if c.call_site == "compare_judge"]
        # 판정 pair당 1행 — seed는 judge를 거치지 않으므로 1행뿐.
        self.assertEqual(len(judged), 1)
        self.assertEqual(judged[0].correlation_id, group.group_id)

    def test_a_terminal_parse_rejection_is_reclassified_and_fails_the_step(self):
        audit = self._audit()
        judge = self._compare_judge("not json", "still not json")
        w = _build(judge, audit=audit)
        a = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="a")
        b = _seed_candidate(w["analysis"], project_id=w["project_id"], logical_key="b")
        group = _open_group(w["groups"], w["project_id"], a, b)

        response = _approve(w["client"], w["project_id"], group.group_id)

        # D4=A: parse 거부도 step=failed·200(상태 가시) — 마지막 행은 parse_error.
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(_step_by(payload, b.id)["status"], "failed")
        self.assertEqual(_step_by(payload, b.id)["error"], "InvalidJudgeResult")
        calls = [
            c for c in audit.list_calls(w["project_id"])
            if c.call_site == "compare_judge"
        ]
        self.assertEqual(len(calls), 2)  # 시도 + repair
        # list_calls 는 최신 우선 — 재분류된 행은 맨 앞이다.
        self.assertEqual(calls[0].outcome, "parse_error")


class CandidateIdentityGroupApprovalStoreTest(unittest.TestCase):
    """승인 진행 상태 저장(Slice 5 신규 저장 단위) — Slice 0 저장 계약과 같은 축."""

    def _service(self):
        return CandidateIdentityGroupApprovalService(
            InMemoryCandidateIdentityGroupApprovalRepository()
        )

    def test_save_and_get_round_trip_with_project_isolation(self):
        service = self._service()
        approval = CandidateIdentityGroupApproval(
            group_id="cig:a", project_id="p1", expected_revision=0,
            canonical_memory_id="mem:1",
            steps=(
                GroupApprovalStep(
                    candidate_id="cand:a",
                    status=GroupApprovalStepStatus.APPLIED,
                    action="create", memory_id="mem:1", version=1, error=None,
                ),
            ),
            created_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        )

        stored = service.save(approval)

        self.assertEqual(service.get("p1", "cig:a"), stored)
        self.assertEqual(stored.steps, approval.steps)  # 본체는 호출자 값 그대로
        self.assertIsNone(service.get("p2", "cig:a"))
        self.assertIsNone(service.get("p1", "cig:other"))

    def test_purge_project_removes_only_that_project(self):
        service = self._service()

        def _approval(group_id, project_id):
            return CandidateIdentityGroupApproval(
                group_id=group_id, project_id=project_id, expected_revision=0,
                canonical_memory_id=None, steps=(),
                created_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
            )

        service.save(_approval("cig:a", "p1"))
        kept = service.save(_approval("cig:b", "p2"))

        service.purge_project("p1")

        self.assertIsNone(service.get("p1", "cig:a"))
        self.assertEqual(service.get("p2", "cig:b"), kept)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
