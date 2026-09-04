"""정체성 그룹 거절 액션(정체성 그룹 Slice 4).

계약(`pending-candidate-identity-grouping-implementation-phases.md` Slice 4 +
착수 브리프 `pending-candidate-identity-grouping-slice4-activity-log-decisions.md`):
- ``POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/reject`` 는 owner만
  실행한다(401/403은 전수 행렬이 잠근다 — 이 파일은 도메인 동작만 본다).
- **멤버 판정은 후보 상태 기계만 본다** — 저장 멤버십에서 needs_review만 거절하고
  나머지(terminal 전 종류)는 skip한다. 멱등은 상태에서 유도한다(요청 body 없음,
  개별 reject와 대칭).
- **closed 그룹은 404** — 읽기면의 정본(Slice 3, open 그룹과 member 행)과 같은
  이유다. ``contradicted``는 여전히 묶으므로 거절된다.
- **활동 로그는 그룹 행 1줄**(오너 2026-09-04, 브리프 A안) — 신규 리터럴
  ``identity_group_rejected``·target ``candidate_identity_group``·
  ``after``="rejected=N, skipped=M", **변경≥1일 때만**(일괄 승격 선례와 같은 모양).

양방향 회귀:
- under-strict: 멤버를 거절하지 않거나, terminal 멤버를 다시 건드리거나, 행을
  남기지 않으면 재실패.
- over-strict: terminal 멤버를 409로 막거나, 그룹 상태(closed) 외에 거절을 막거나,
  변경이 없는데 행을 남기면 재실패.
"""

import asyncio
import unittest
from datetime import UTC, datetime

import httpx

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    IdentityGroupStatus,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.service import (
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
)
from services.application.app.main import create_app
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)
from tests.auth_support import authenticate

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


class _FixedClock:
    """시각을 한 칸씩 전진 — 멤버 added_at 순서를 잰다.

    서비스 클록은 ms 로 절단되므로 클록 없이는 같은 밀리초 추가가 전부
    동률이 되고 ``(added_at, candidate_id)`` 정렬이 아이디 정렬로 붕괴한다.
    멤버 추가 순서 ≠ 아이디 순서를 만들려면 added_at 이 실제로 갈라져야 한다.
    """

    def __init__(self) -> None:
        self._ticks = iter(range(0, 300, 10))
        self.now = datetime(2026, 9, 4, 10, next(self._ticks), tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self) -> None:
        self.now = datetime(2026, 9, 4, 10, next(self._ticks), tzinfo=UTC)


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


def _build():
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    clock = _FixedClock()
    groups = CandidateIdentityGroupService(
        InMemoryCandidateIdentityGroupRepository(), clock=clock
    )
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory,
        index_sync_outbox=IndexSyncOutboxService(InMemoryIndexSyncRepository()),
        review_queue_service=ReviewQueueService(InMemoryReviewQueueRepository()),
        identity_group_service=groups,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, groups, clock, project_id


def _seed_candidate(analysis, *, project_id, logical_key):
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
        source_ref_ids=("source-ref-1",),
        payload={"name": "Ariel", "observation": "brave"},
    ).candidate


def _open_group(groups, project_id, *candidates):
    group = groups.create_group(project_id, CHARACTER)
    for candidate in candidates:
        groups.add_member(
            project_id=project_id, group_id=group.group_id,
            candidate_id=candidate.id, candidate_type=CHARACTER,
        )
    return group


def _reject(client, project_id, group_id):
    return client.post(
        f"/projects/{project_id}/analysis/review-inbox/groups/{group_id}/reject"
    )


def _statuses(client, project_id):
    items = client.get(
        f"/projects/{project_id}/analysis/review-inbox"
    ).json()["items"]
    return {item["candidate_id"]: item["status"] for item in items}


def _activity(client, project_id):
    response = client.get(f"/projects/{project_id}/activity")
    assert response.status_code == 200, response.text
    return response.json()["events"]


class GroupRejectTest(unittest.TestCase):
    def test_rejecting_a_group_rejects_every_needs_review_member(self):
        client, analysis, _memory, groups, clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        c = _seed_candidate(analysis, project_id=project_id, logical_key="c")
        # 멤버 추가 순서는 아이디 순서와 반대고 added_at 은 클록 전진으로 실제로
        # 갈라진다 — 응답이 멤버십 순회(added_at) 순서가 아니라 아이디 정렬을
        # 따르는 것(어댑터와 무관한 결정성)을 잠근다. 클록 없이는 같은 밀리초
        # 동률이 아이디 tie-break 로 붕괴해 sorted() 제거가 관측되지 않는다.
        group = groups.create_group(project_id, CHARACTER)
        for candidate in (c, b, a):
            groups.add_member(
                project_id=project_id, group_id=group.group_id,
                candidate_id=candidate.id, candidate_type=CHARACTER,
            )
            clock.advance()

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "group_id": group.group_id,
            "rejected": sorted([a.id, b.id, c.id]),
            "skipped": [],
            "idempotent_replay": False,
        })
        # 후보 상태가 실제로 바뀌었고 검토함은 비었다.
        self.assertEqual(
            analysis.get_candidate(
                project_id=project_id, candidate_id=a.id
            ).status.value, "rejected"
        )
        self.assertEqual(_statuses(client, project_id), {})

    def test_members_already_terminal_are_skipped_and_the_rest_rejected(self):
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        confirmed = _seed_candidate(
            analysis, project_id=project_id, logical_key="c")
        rejected = _seed_candidate(
            analysis, project_id=project_id, logical_key="d")
        self.assertEqual(client.post(
            f"/projects/{project_id}/analysis/candidates/{confirmed.id}/confirm"
        ).status_code, 200)
        self.assertEqual(client.post(
            f"/projects/{project_id}/analysis/candidates/{rejected.id}/reject"
        ).status_code, 200)
        group = _open_group(groups, project_id, a, b, confirmed, rejected)

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "group_id": group.group_id,
            "rejected": sorted([a.id, b.id]),
            "skipped": sorted([confirmed.id, rejected.id]),
            "idempotent_replay": False,
        })
        # skipped 멤버는 다시 건드리지 않는다 — confirmed는 그대로다.
        self.assertEqual(
            analysis.get_candidate(
                project_id=project_id, candidate_id=confirmed.id
            ).status.value, "confirmed"
        )

    def test_superseded_members_are_skipped_like_other_terminal_states(self):
        """검증 B1 폐쇄(2026-09-04) — 리터럴 ① "terminal 전 종류"의 세 번째 값.

        셀 2가 confirmed·rejected만 시드해서 검증자 변이 VM-A(skip을 두 값
        열거로 좁히는 과잉 교정)가 10 passed로 통과했다. 그 좁힘 아래에서는
        superseded 멤버가 개별 reject 경로의 `InvalidCandidateStateTransition`
        을 그룹 라우터 catch 밖으로 흘려 배치를 mid-flight로 죽린다(검증 실측)
        — 이 셀이 그 방향을 문다. edit가 원본을 superseded로 남기는 상태는
        Slice 3 H2 셀이 읽기면에서 이미 시드하는 도달 가능 상태다.
        probe `repro_slice4_member_literals.py` P1의 본체.
        """
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        # edit는 원본 b를 superseded로 만든다(승격 후보는 신규 id — 그룹 밖).
        self.assertEqual(client.post(
            f"/projects/{project_id}/analysis/candidates/{b.id}/edit",
            json={"payload": {"name": "Ariel", "observation": "edited"}},
        ).status_code, 200)
        self.assertEqual(
            analysis.get_candidate(
                project_id=project_id, candidate_id=b.id
            ).status.value, "superseded"
        )
        group = _open_group(groups, project_id, a, b)

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "group_id": group.group_id,
            "rejected": [a.id],
            "skipped": [b.id],
            "idempotent_replay": False,
        })

    def test_promoted_members_are_still_rejected_and_canonical_survives(self):
        """검증 B2 폐쇄(2026-09-04) — 리터럴 ① "승격 여부는 보지 않는다".

        승격은 상태를 바꾸지 않는다(`memory/service.py` — "a promoted candidate
        still carries `needs_review` status")— 승격된 needs_review 멤버도
        그룹 거절의 대상이고, canonical은 append-only라 거절 뒤에 남는다.
        현재 방어가 구조적일 뿐(서비스가 memory를 주입받지 않는다)이어서
        memory를 주입해 승격 멤버를 skip하는 날 아무 셀도 물지 않는 상태였다(검증).
        probe `repro_slice4_member_literals.py` P2의 본체.
        """
        client, analysis, memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        # 개별 promote 경로 — 승격 후에도 상태는 needs_review다.
        self.assertEqual(client.post(
            f"/projects/{project_id}/analysis/candidates/{a.id}/promote"
        ).status_code, 200)
        self.assertTrue(memory.is_candidate_promoted(project_id, a.id))
        self.assertEqual(
            analysis.get_candidate(
                project_id=project_id, candidate_id=a.id
            ).status.value, "needs_review"
        )
        group = _open_group(groups, project_id, a, b)

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "group_id": group.group_id,
            "rejected": sorted([a.id, b.id]),
            "skipped": [],
            "idempotent_replay": False,
        })
        # canonical은 append-only — 거절이 승격을 되돌리지 않는다.
        self.assertTrue(memory.is_candidate_promoted(project_id, a.id))

    def test_re_invoking_a_completed_reject_is_a_full_noop(self):
        """같은 key 재전송과 "다른 key로 이미 끝난 그룹 재호출"이 같은 관측이다.

        멱등이 상태에서 유도되므로(요청 key 없음 — 착수 결정) 두 방향은 서버에서
        구분되지 않는다. 잠그는 것은 과잉 방향이다: 완료된 그룹을 다시 눌러도
        아무 후보를 다시 건드리지 않고 행도 남기지 않는다.
        """
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        group = _open_group(groups, project_id, a, b)
        self.assertEqual(
            _reject(client, project_id, group.group_id).status_code, 200)

        replay = _reject(client, project_id, group.group_id)

        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), {
            "group_id": group.group_id,
            "rejected": [],
            "skipped": sorted([a.id, b.id]),
            "idempotent_replay": True,
        })
        self.assertEqual(len(_activity(client, project_id)), 2)

    def test_unknown_group_is_404(self):
        client, _analysis, _memory, _groups, _clock, project_id = _build()

        response = _reject(client, project_id, "cig:does-not-exist")

        self.assertEqual(response.status_code, 404)

    def test_another_projects_group_is_404_for_this_project(self):
        client, analysis, _memory, groups, _clock, project_id = _build()
        other_id = client.post(
            "/projects", json={"name": "Other"}
        ).json()["id"]
        foreign = _seed_candidate(analysis, project_id=other_id, logical_key="x")
        foreign_group = _open_group(groups, other_id, foreign)

        response = _reject(client, project_id, foreign_group.group_id)

        self.assertEqual(response.status_code, 404)

    def test_closed_group_is_404(self):
        """병합으로 흡수된 closed 껍데기는 검토 대상이 아니다(읽기면과 같은 정본)."""
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        group = _open_group(groups, project_id, a, b)
        groups.set_group_status(
            project_id, group.group_id, IdentityGroupStatus.CLOSED
        )

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 404)
        # 그룹은 거절되지 않았다.
        self.assertEqual(
            analysis.get_candidate(
                project_id=project_id, candidate_id=a.id
            ).status.value, "needs_review"
        )

    def test_missing_project_is_404(self):
        client, _analysis, _memory, _groups, _clock, _project_id = _build()

        response = _reject(client, "does-not-exist", "cig:any")

        self.assertEqual(response.status_code, 404)

    def test_a_contradicted_group_can_still_be_rejected(self):
        """contradicted도 읽기면이 묶는다(Slice 3) — 거절도 그룹 전체에 적용된다."""
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        group = _open_group(groups, project_id, a, b)
        groups.set_group_status(
            project_id, group.group_id, IdentityGroupStatus.CONTRADICTED
        )

        response = _reject(client, project_id, group.group_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["rejected"], sorted([a.id, b.id])
        )

    def test_rejection_records_one_group_level_activity_row(self):
        """브리프 A안 — 그룹 행 1줄, after에 두 수를 싣는다(멤버별 행이 아니다)."""
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        confirmed = _seed_candidate(
            analysis, project_id=project_id, logical_key="c")
        self.assertEqual(client.post(
            f"/projects/{project_id}/analysis/candidates/{confirmed.id}/confirm"
        ).status_code, 200)
        group = _open_group(groups, project_id, a, b, confirmed)
        _reject(client, project_id, group.group_id)

        events = _activity(client, project_id)
        rows = [e for e in events if e["action"] == "identity_group_rejected"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target_type"], "candidate_identity_group")
        self.assertEqual(rows[0]["target_id"], group.group_id)
        self.assertEqual(rows[0]["after"], "rejected=2, skipped=1")
        # 멤버별 candidate_rejected 행은 남기지 않는다 — 같은 사실의 두 번째 정본.
        self.assertEqual(
            [e for e in events if e["action"] == "candidate_rejected"], []
        )

    def test_a_noop_rejection_records_no_activity_row(self):
        """변경이 없으면 행을 남기지 않는다(일괄 승격의 `if promoted:` 선례).

        RED 단계에서 이 셀은 우연 통과했다(검증 H2, 2026-09-04) — 라우트가
        없으면 첫 거절도 404라 before==after가 성립한다. 구현 세션의 RED 기록
        "5 failed" 산술과 정확히 일치하는 사실이고, 이 셀의 효력은 라우트가
        있는 지금부터다(셀 3이 먼저 거절을 완료하는 순서 의존은 이미 문서화).
        """
        client, analysis, _memory, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id, logical_key="a")
        b = _seed_candidate(analysis, project_id=project_id, logical_key="b")
        group = _open_group(groups, project_id, a, b)
        _reject(client, project_id, group.group_id)
        before = _activity(client, project_id)

        _reject(client, project_id, group.group_id)

        self.assertEqual(_activity(client, project_id), before)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
