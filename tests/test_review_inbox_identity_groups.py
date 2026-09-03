"""Review Inbox 읽기면의 identity group 메타데이터(정체성 그룹 Slice 3).

계약(`pending-candidate-identity-grouping-implementation-phases.md` Slice 3):
- 기존 개별 item 필드는 그대로다. group metadata는 **additive**다.
- **읽기면의 정본은 open 그룹과 member 행**이다 — relation 행의 ``group_id``는
  기록 시점 값이라 병합으로 흡수된(``closed``) 그룹을 가리킬 수 있으므로
  표시 전용이며 소속 판단에 쓰지 않는다.
- 목록 렌더에 필요한 최소값: ``group_id``·``group_size``·``group_status``·
  ``group_member_ids``·``identity_rationale_summary``.

양방향 회귀:
- under-strict: 그룹 메타데이터가 빠지거나 closed 그룹이 새어 들면 재실패.
- over-strict: 검토함을 떠난(stale) 멤버까지 roster에 싣거나 가시 멤버가
  하나뿐인 그룹을 강제로 묶으면 재실패 — 읽기면은 목록 렌더 기준으로 정리한다.
"""

import asyncio
import unittest
from datetime import UTC, datetime

import httpx

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    IdentityGroupStatus,
    IdentityRelationVerdict,
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
    """시각을 한 칸씩 전진 — relation created_at 순서를 잰다."""

    def __init__(self) -> None:
        self._ticks = iter(range(0, 300, 10))
        self.now = datetime(2026, 9, 4, 9, next(self._ticks), tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self) -> None:
        self.now = datetime(2026, 9, 4, 9, next(self._ticks), tzinfo=UTC)


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
    return client, analysis, groups, clock, project_id


def _seed_candidate(analysis, *, project_id, logical_key, payload):
    job = analysis.create_job(
        project_id=project_id, snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=CHARACTER
    )
    candidate = analysis.record_candidate(
        project_id=project_id, task_id=task.id, logical_key=logical_key,
        candidate_type=CHARACTER, action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED, confidence=0.5,
        source_ref_ids=("source-ref-1",), payload=payload,
    ).candidate
    return candidate


def _open_group(groups, project_id, *candidates):
    group = groups.create_group(project_id, CHARACTER)
    for candidate in candidates:
        groups.add_member(
            project_id=project_id, group_id=group.group_id,
            candidate_id=candidate.id, candidate_type=CHARACTER,
        )
    return group


def _same_relation(groups, project_id, left, right, rationale):
    groups.record_relation(
        project_id, CHARACTER, left.id, right.id,
        verdict=IdentityRelationVerdict.SAME, rationale=rationale,
        source="identity_judge",
    )


def _items(client, project_id):
    response = client.get(f"/projects/{project_id}/analysis/review-inbox")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _by_id(items):
    return {item["candidate_id"]: item for item in items}


class GroupMetadataTest(unittest.TestCase):
    def test_grouped_items_carry_group_metadata(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b)
        _same_relation(groups, project_id, a, b, "same normalized name")

        items = _by_id(_items(client, project_id))

        expected = {
            "group_id": group.group_id,
            "group_size": 2,
            "group_status": "open",
            "group_member_ids": sorted([a.id, b.id]),
            "identity_rationale_summary": "same normalized name",
        }
        self.assertEqual(items[a.id]["identity_group"], expected)
        self.assertEqual(items[b.id]["identity_group"], expected)

    def test_ungrouped_item_has_null_identity_group(self):
        client, analysis, _groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})

        [item] = _items(client, project_id)

        self.assertIsNone(item["identity_group"])
        self.assertEqual(item["candidate_id"], a.id)
        self.assertEqual(item["status"], "needs_review")

    def test_mixed_list_keeps_candidate_fields_and_affordances(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Eric", "observation": "curious"})
        _open_group(groups, project_id, a, b)
        _same_relation(groups, project_id, a, b, "same normalized name")

        items = _by_id(_items(client, project_id))

        # grouped/ungrouped가 같은 목록에 섞여도 기존 개별 후보 소비자 면은
        # 그대로다 — 필드·affordance 전부.
        for candidate in (a, b, c):
            item = items[candidate.id]
            self.assertEqual(item["job_id"], candidate.job_id)
            self.assertEqual(item["candidate_type"], "character_observation")
            self.assertEqual(item["payload"], dict(candidate.payload))
            self.assertEqual(item["conflict_count"], 0)
            self.assertEqual(
                item["actions"],
                [
                    {"action": "confirm", "eligible": True, "reason": None},
                    {"action": "reject", "eligible": True, "reason": None},
                    {"action": "edit", "eligible": True, "reason": None},
                ],
            )
        self.assertIsNotNone(items[a.id]["identity_group"])
        self.assertIsNotNone(items[b.id]["identity_group"])
        self.assertIsNone(items[c.id]["identity_group"])

    def test_closed_group_membership_does_not_group_the_item(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        absorbed = _open_group(groups, project_id, a, b)
        # 병합으로 흡수된 껍데기 — member 행은 남지만 읽기면의 정본이 아니다.
        groups.set_group_status(
            project_id, absorbed.group_id, IdentityGroupStatus.CLOSED
        )

        items = _by_id(_items(client, project_id))

        self.assertIsNone(items[a.id]["identity_group"])
        self.assertIsNone(items[b.id]["identity_group"])

    def test_contradicted_group_is_surfaced_with_its_status(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b)
        groups.set_group_status(
            project_id, group.group_id, IdentityGroupStatus.CONTRADICTED
        )

        items = _by_id(_items(client, project_id))

        # contradicted도 여전히 묶는다 — closed가 아니므로. 상태값이 그대로
        # 흘러가는 것까지가 계약이다(UI 경고 라벨의 재료).
        self.assertEqual(
            items[a.id]["identity_group"]["group_status"], "contradicted"
        )
        self.assertEqual(
            items[b.id]["identity_group"]["group_id"], group.group_id
        )

    def test_members_outside_the_inbox_are_excluded_from_the_roster(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b, c)
        confirmed = client.post(
            f"/projects/{project_id}/analysis/candidates/{b.id}/confirm"
        )
        self.assertEqual(confirmed.status_code, 200)

        items = _by_id(_items(client, project_id))

        # b는 검토함을 떠났다(stale member). roster는 목록 렌더 기준으로 정리한다.
        expected = {
            "group_id": group.group_id,
            "group_size": 2,
            "group_status": "open",
            "group_member_ids": sorted([a.id, c.id]),
            "identity_rationale_summary": None,
        }
        self.assertEqual(items[a.id]["identity_group"], expected)
        self.assertNotIn(b.id, items)

    def test_group_with_fewer_than_two_visible_members_renders_ungrouped(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b)
        _same_relation(groups, project_id, a, b, "same normalized name")
        rejected = client.post(
            f"/projects/{project_id}/analysis/candidates/{b.id}/reject"
        )
        self.assertEqual(rejected.status_code, 200)

        items = _by_id(_items(client, project_id))

        # 가시 멤버가 하나뿐인 그룹은 목록에서 묶을 것이 없다 — 저장 멤버십은
        # 그대로 두되(Slice 4·5가 수명을 확정한다) 읽기면은 ungrouped로 말한다.
        self.assertIsNone(items[a.id]["identity_group"])

    def test_group_roster_is_isolated_by_project(self):
        client, analysis, groups, _clock, project_id = _build()
        other_id = client.post(
            "/projects", json={"name": "Other"}
        ).json()["id"]
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        x = _seed_candidate(analysis, project_id=other_id,
                            logical_key="x", payload={"name": "Ariel", "observation": "brave"})
        y = _seed_candidate(analysis, project_id=other_id,
                            logical_key="y", payload={"name": "Ariel", "observation": "brave"})
        mine = _open_group(groups, project_id, a, b)
        theirs = _open_group(groups, other_id, x, y)
        _same_relation(groups, project_id, a, b, "mine")
        _same_relation(groups, other_id, x, y, "theirs")

        my_items = _by_id(_items(client, project_id))
        their_items = _by_id(_items(client, other_id))

        self.assertEqual(my_items[a.id]["identity_group"]["group_id"],
                         mine.group_id)
        self.assertEqual(their_items[x.id]["identity_group"]["group_id"],
                         theirs.group_id)
        self.assertNotEqual(mine.group_id, theirs.group_id)

    def test_detail_payload_carries_the_same_identity_group(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b)
        _same_relation(groups, project_id, a, b, "same normalized name")

        listed = _by_id(_items(client, project_id))
        detail = client.get(
            f"/projects/{project_id}/analysis/review-inbox/{a.id}"
        ).json()

        self.assertEqual(detail["identity_group"],
                         listed[a.id]["identity_group"])
        # detail 경계는 개별 후보 기준으로 유지된다.
        self.assertIn("source_refs", detail)

    def test_rationale_summary_picks_the_latest_same_relation(self):
        client, analysis, groups, clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b, c)
        _same_relation(groups, project_id, a, b, "older pair")
        clock.advance()
        _same_relation(groups, project_id, a, c, "newer pair")
        clock.advance()
        groups.record_relation(  # 판정이 뒤집힌 pair — same이 아닌 근거는 안 싣는다
            project_id, CHARACTER, b.id, c.id,
            verdict=IdentityRelationVerdict.DIFFERENT,
            rationale="flipped later", source="identity_judge",
        )

        items = _by_id(_items(client, project_id))

        self.assertEqual(
            items[a.id]["identity_group"]["identity_rationale_summary"],
            "newer pair",
        )
        self.assertEqual(
            items[c.id]["identity_group"]["identity_rationale_summary"],
            "newer pair",
        )
        self.assertEqual(
            items[b.id]["identity_group"]["identity_rationale_summary"],
            "older pair",
        )

    def test_rationale_summary_is_truncated_to_200_chars(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b)
        long_rationale = "r" * 250
        _same_relation(groups, project_id, a, b, long_rationale)

        items = _by_id(_items(client, project_id))

        # 200자 — 활동 로그 "짧은 값"·장면 메모 미리보기와 같은 값. 목록에
        # 싣는 텍스트 조각에 두 번째 숫자를 만들지 않는다.
        self.assertEqual(
            items[a.id]["identity_group"]["identity_rationale_summary"],
            "r" * 200,
        )

    def test_rationale_ignores_relation_group_id_pointing_elsewhere(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        live = _open_group(groups, project_id, a, b)
        ghost = groups.create_group(project_id, CHARACTER)
        # relation.group_id는 기록 시점 값 — 흡수된(여기선 없는) 그룹을 가리켜도
        # 소속·근거 선택의 정본이 될 수 없다(표시 전용).
        groups.record_relation(
            project_id, CHARACTER, a.id, b.id,
            verdict=IdentityRelationVerdict.SAME,
            rationale="pair membership decides", source="identity_judge",
            group_id=ghost.group_id,
        )

        items = _by_id(_items(client, project_id))

        self.assertEqual(items[a.id]["identity_group"]["group_id"],
                         live.group_id)
        self.assertEqual(
            items[a.id]["identity_group"]["identity_rationale_summary"],
            "pair membership decides",
        )

    def test_group_without_same_relation_has_null_rationale_summary(self):
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b)

        items = _by_id(_items(client, project_id))

        # member 행만 있고 same relation이 없으면(예: 판정이 뒤집힌 뒤)
        # 근거 요약은 없다 — 없는 사실을 지어내지 않는다.
        self.assertEqual(
            items[a.id]["identity_group"],
            {
                "group_id": group.group_id,
                "group_size": 2,
                "group_status": "open",
                "group_member_ids": sorted([a.id, b.id]),
                "identity_rationale_summary": None,
            },
        )

    def test_rationale_ignores_relations_to_members_outside_the_roster(self):
        # 검증 B1 폐쇄(2026-09-04) — VM1이 13 passed로 입증한 무셀 축. 리터럴 ③의
        # should-NOT: same relation의 상대가 검토함을 떠났으면 그 pair의 근거는
        # 싣지 않는다. 그룹은 가시 멤버가 남는 한 살아 있다(여기선 {a, c} ≥ 2).
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b, c)
        _same_relation(groups, project_id, a, b, "judged while b was visible")
        rejected = client.post(
            f"/projects/{project_id}/analysis/candidates/{b.id}/reject"
        )
        self.assertEqual(rejected.status_code, 200)

        items = _by_id(_items(client, project_id))

        self.assertEqual(items[a.id]["identity_group"]["group_member_ids"],
                         sorted([a.id, c.id]))
        self.assertIsNone(
            items[a.id]["identity_group"]["identity_rationale_summary"]
        )

    def test_rationale_tie_breaks_by_the_larger_pair_id(self):
        # 하드닝 H1 — created_at 동률(BSON ms 해상도라 실운영 가능)의 방향 잠금.
        # 동률이면 큰 pair id가 이긴다(focal 고정 → 더 큰 id의 상대편 relation).
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Ariel", "observation": "brave"})
        _open_group(groups, project_id, a, b, c)
        # 클록을 전진하지 않는다 — 두 relation의 created_at이 정확히 같다.
        _same_relation(groups, project_id, a, b, f"rationale via {b.id}")
        _same_relation(groups, project_id, a, c, f"rationale via {c.id}")

        items = _by_id(_items(client, project_id))

        winner = b if b.id > c.id else c
        self.assertEqual(
            items[a.id]["identity_group"]["identity_rationale_summary"],
            f"rationale via {winner.id}",
        )
        # focal이 아닌 쪽(b·c)은 각자 a와의 relation 하나뿐 — 동률의 영향이 없다.
        self.assertEqual(
            items[b.id]["identity_group"]["identity_rationale_summary"],
            f"rationale via {b.id}",
        )

    def test_edited_member_leaves_the_group_roster(self):
        # 하드닝 H2 — 검토함 이탈의 세 번째 원인 edit(원본 superseded)도
        # confirm(셀 위)·reject(셀 위)와 같은 분기로 roster에서 사라진다.
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        c = _seed_candidate(analysis, project_id=project_id,
                            logical_key="c", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b, c)
        _same_relation(groups, project_id, a, b, "judged while b was visible")
        edited = client.post(
            f"/projects/{project_id}/analysis/candidates/{b.id}/edit",
            json={"payload": {"name": "Ariel", "observation": "revised"}},
        )
        self.assertEqual(edited.status_code, 200)

        items = _by_id(_items(client, project_id))

        # edit의 승격은 새 후보 id로 나가므로 roster에 끼지 않고, 원본 b는
        # superseded로 검토함을 떠난다. a-b relation의 상대도 이탈 → 근거 null.
        self.assertNotIn(b.id, items)
        self.assertEqual(
            items[a.id]["identity_group"],
            {
                "group_id": group.group_id,
                "group_size": 2,
                "group_status": "open",
                "group_member_ids": sorted([a.id, c.id]),
                "identity_rationale_summary": None,
            },
        )

    def test_rationale_ignores_relations_of_another_candidate_type(self):
        # 하드닝 H3 — relation의 candidate_type이 그룹의 type과 다르면 근거가
        # 될 수 없다. 판정 경로는 같은 type pool만 짝짓지만 저장 면은 이 행을
        # 거부하지 않으므로(서비스 오용으로만 생성 가능), 읽기면의 방어를 잠근다.
        client, analysis, groups, _clock, project_id = _build()
        a = _seed_candidate(analysis, project_id=project_id,
                            logical_key="a", payload={"name": "Ariel", "observation": "brave"})
        b = _seed_candidate(analysis, project_id=project_id,
                            logical_key="b", payload={"name": "Ariel", "observation": "brave"})
        group = _open_group(groups, project_id, a, b)
        groups.record_relation(
            project_id, AnalysisCandidateType.EVENT_OBSERVATION, a.id, b.id,
            verdict=IdentityRelationVerdict.SAME,
            rationale="cross-type row references character ids",
            source="identity_judge",
        )

        items = _by_id(_items(client, project_id))

        # 그룹 자체는 member 행으로 살아 있고 — 근거만 오염되지 않는다.
        self.assertEqual(
            items[a.id]["identity_group"],
            {
                "group_id": group.group_id,
                "group_size": 2,
                "group_status": "open",
                "group_member_ids": sorted([a.id, b.id]),
                "identity_rationale_summary": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
