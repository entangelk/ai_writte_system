"""미승인 후보 정체성 그룹 Slice 0 — 저장 모델과 수명 (in-memory).

계획: ``docs/plans/pending-candidate-identity-grouping-implementation-phases.md``
Slice 0. HTTP·runner 배선·LLM judge는 이 Slice 밖이다. 잠그는 계약:

1. 세 저장 단위(group·member·relation)의 round-trip.
2. project/type 격리 — 다른 프로젝트·타입은 서로에게 보이지 않는다.
3. member 중복 추가는 멱등 — 같은 (project, type, group, candidate)는 한 행이고
   재추가가 ``added_at``을 바꾸지 않는다.
4. relation pair 정규화 — ``(A,B)``와 ``(B,A)``는 같은 행이다(재기록 멱등).
5. group status ``open|contradicted|closed`` round-trip. ``contradicted``는 상태를
   저장할 자리만 만든다 — 자동 분할·자동 병합은 이 Slice 밖이다.
6. ``purge_project``는 그룹·멤버·관계를 모두 지운다(고아 없음, 인접 project 무변).

relation의 ``candidate_type`` 필드는 오너 결정(2026-09-02)이다 — 계획의 "모든
unique/index 축에 project_id와 candidate_type 포함" 문장을 relation에도 그대로
적용한다.

양방향:
- under — 정규화·멱등·격리·상태 저장·파기를 무력화하면 각 셀이 재실패한다.
- over — 예: pair 정규화가 서로 다른 pair까지 접는 순간 type 격리 셀·구성원이 다른
  relation 셀이 실패한다.
"""

import unittest
from datetime import UTC, datetime

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroup,
    CandidateIdentityGroupMember,
    CandidateIdentityGroupNotFoundError,
    CandidateIdentityGroupService,
    CandidateIdentityGroupTypeError,
    CandidateIdentityRelation,
    IdentityGroupMemberStatus,
    IdentityGroupStatus,
    IdentityRelationVerdict,
    InMemoryCandidateIdentityGroupRepository,
)

_CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
_EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _FixedClock:
    """시각을 한 칸씩 전진 — created_at/updated_at/added_at의 보존을 잰다."""

    def __init__(self) -> None:
        self._ticks = iter(range(0, 100, 10))
        self.now = datetime(2026, 9, 2, 12, next(self._ticks), tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self) -> None:
        self.now = datetime(2026, 9, 2, 12, next(self._ticks), tzinfo=UTC)


class CandidateIdentityGroupServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _FixedClock()
        self.service = CandidateIdentityGroupService(
            InMemoryCandidateIdentityGroupRepository(), clock=self.clock
        )

    # --- ① round-trip ----------------------------------------------------

    def test_create_group_round_trip(self) -> None:
        group = self.service.create_group(
            project_id="p1", candidate_type=_CHARACTER
        )

        self.assertTrue(group.group_id.startswith("cig:"))
        self.assertEqual(group.project_id, "p1")
        self.assertEqual(group.candidate_type, _CHARACTER)
        self.assertEqual(group.status, IdentityGroupStatus.OPEN)
        self.assertEqual(group.revision, 0)
        self.assertEqual(group.created_at, group.updated_at)
        # Field-for-field equality, not just selected attributes.
        self.assertEqual(self.service.get_group("p1", group.group_id), group)

    def test_member_round_trip(self) -> None:
        group = self.service.create_group(
            project_id="p1", candidate_type=_CHARACTER
        )

        member = self.service.add_member(
            project_id="p1", group_id=group.group_id,
            candidate_id="cand:a", candidate_type=_CHARACTER,
        )

        self.assertEqual(
            member,
            CandidateIdentityGroupMember(
                group_id=group.group_id, candidate_id="cand:a",
                project_id="p1", candidate_type=_CHARACTER,
                member_status=IdentityGroupMemberStatus.ACTIVE,
                added_at=self.clock.now,
            ),
        )
        self.assertEqual(
            self.service.list_members("p1", group.group_id), (member,)
        )

    def test_relation_round_trip(self) -> None:
        relation = self.service.record_relation(
            project_id="p1", candidate_type=_CHARACTER,
            left_candidate_id="cand:b", right_candidate_id="cand:a",
            verdict=IdentityRelationVerdict.SAME,
            rationale="같은 인물 '유나' 관찰", source="identity_judge",
            group_id="cig:x",
        )

        self.assertEqual(
            relation,
            CandidateIdentityRelation(
                project_id="p1", candidate_type=_CHARACTER,
                left_candidate_id="cand:a", right_candidate_id="cand:b",
                verdict=IdentityRelationVerdict.SAME,
                rationale="같은 인물 '유나' 관찰", source="identity_judge",
                group_id="cig:x", created_at=self.clock.now,
            ),
        )
        self.assertEqual(
            self.service.get_relation(
                "p1", _CHARACTER, "cand:a", "cand:b"
            ),
            relation,
        )

    # --- ② project/type 격리 ----------------------------------------------

    def test_get_group_is_project_scoped(self) -> None:
        group = self.service.create_group(
            project_id="p1", candidate_type=_CHARACTER
        )

        # 같은 group_id라도 다른 project에서는 NotFound — 존재 노출도 없다.
        with self.assertRaises(CandidateIdentityGroupNotFoundError):
            self.service.get_group("p2", group.group_id)

    def test_relations_are_type_and_project_scoped(self) -> None:
        relation = self.service.record_relation(
            project_id="p1", candidate_type=_CHARACTER,
            left_candidate_id="cand:a", right_candidate_id="cand:b",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge",
        )

        # 같은 pair라도 type이 다르면 별개 relation — 오너 결정(2026-09-02)으로
        # relation unique 축에 candidate_type이 들어간다.
        self.assertIsNone(
            self.service.get_relation("p1", _EVENT, "cand:a", "cand:b")
        )
        self.assertIsNone(
            self.service.get_relation("p2", _CHARACTER, "cand:a", "cand:b")
        )
        self.assertEqual(self.service.list_relations("p2"), ())
        self.assertEqual(self.service.list_relations("p1"), (relation,))

    def test_members_do_not_leak_across_groups(self) -> None:
        group1 = self.service.create_group("p1", _CHARACTER)
        group2 = self.service.create_group("p1", _CHARACTER)

        self.service.add_member(
            "p1", group1.group_id, "cand:a", _CHARACTER
        )

        self.assertEqual(
            self.service.list_members("p1", group2.group_id), ()
        )

    # --- ③ member 멱등 ----------------------------------------------------

    def test_add_member_is_idempotent(self) -> None:
        group = self.service.create_group("p1", _CHARACTER)
        first = self.service.add_member(
            "p1", group.group_id, "cand:a", _CHARACTER
        )

        self.clock.advance()
        again = self.service.add_member(
            "p1", group.group_id, "cand:a", _CHARACTER
        )

        # 재추가는 added_at을 바꾸지 않고 같은 행을 돌려준다.
        self.assertEqual(again, first)
        members = self.service.list_members("p1", group.group_id)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].added_at, first.added_at)

    def test_add_member_rejects_missing_group_and_type_mismatch(self) -> None:
        group = self.service.create_group("p1", _CHARACTER)

        with self.assertRaises(CandidateIdentityGroupNotFoundError):
            self.service.add_member(
                "p1", "cig:ghost", "cand:a", _CHARACTER
            )
        # 그룹의 type과 다른 후보는 그룹에 들어올 수 없다(격리 축).
        with self.assertRaises(CandidateIdentityGroupTypeError):
            self.service.add_member(
                "p1", group.group_id, "cand:a", _EVENT
            )

    # --- ④ relation pair 정규화 -------------------------------------------

    def test_relation_pair_is_normalized_across_directions(self) -> None:
        forward = self.service.record_relation(
            "p1", _CHARACTER, "cand:a", "cand:b",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge",
        )
        self.assertEqual(
            (forward.left_candidate_id, forward.right_candidate_id),
            ("cand:a", "cand:b"),
        )

        # 반대 방향으로 같은 pair를 재기록 — 새 행이 아니라 같은 행이다.
        self.clock.advance()
        backward = self.service.record_relation(
            "p1", _CHARACTER, "cand:b", "cand:a",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge",
        )

        self.assertEqual(backward.created_at, forward.created_at)
        self.assertEqual(len(self.service.list_relations("p1")), 1)
        # 조회도 방향 무관.
        self.assertEqual(
            self.service.get_relation("p1", _CHARACTER, "cand:b", "cand:a"),
            forward,
        )

    def test_relation_re_record_same_pair_updates_verdict_in_place(self) -> None:
        first = self.service.record_relation(
            "p1", _CHARACTER, "cand:a", "cand:b",
            verdict=IdentityRelationVerdict.UNCERTAIN,
            rationale="첫 판정", source="identity_judge",
        )

        second = self.service.record_relation(
            "p1", _CHARACTER, "cand:a", "cand:b",
            verdict=IdentityRelationVerdict.DIFFERENT,
            rationale="재판정", source="identity_judge",
        )

        # 저장 층은 upsert(마지막 판정 승리) — 판정 재사용 정책은 Slice 1 것이다.
        self.assertEqual(
            self.service.get_relation("p1", _CHARACTER, "cand:a", "cand:b"),
            second,
        )
        self.assertNotEqual(second.verdict, first.verdict)
        self.assertEqual(len(self.service.list_relations("p1")), 1)

    def test_relation_rejects_self_pair(self) -> None:
        with self.assertRaises(ValueError):
            self.service.record_relation(
                "p1", _CHARACTER, "cand:a", "cand:a",
                verdict=IdentityRelationVerdict.SAME,
                rationale="r", source="identity_judge",
            )

    # --- ⑤ contradicted 상태 round-trip ------------------------------------

    def test_group_status_round_trip_including_contradicted(self) -> None:
        group = self.service.create_group("p1", _CHARACTER)

        self.clock.advance()
        contradicted = self.service.set_group_status(
            "p1", group.group_id, IdentityGroupStatus.CONTRADICTED
        )

        self.assertEqual(contradicted.status, IdentityGroupStatus.CONTRADICTED)
        self.assertEqual(contradicted.revision, 1)
        self.assertGreater(contradicted.updated_at, group.created_at)
        self.assertEqual(
            self.service.get_group("p1", group.group_id).status,
            IdentityGroupStatus.CONTRADICTED,
        )

        self.clock.advance()
        closed = self.service.set_group_status(
            "p1", group.group_id, IdentityGroupStatus.CLOSED
        )
        self.assertEqual(closed.status, IdentityGroupStatus.CLOSED)
        self.assertEqual(closed.revision, 2)

    def test_set_group_status_is_project_scoped(self) -> None:
        group = self.service.create_group("p1", _CHARACTER)

        with self.assertRaises(CandidateIdentityGroupNotFoundError):
            self.service.set_group_status(
                "p2", group.group_id, IdentityGroupStatus.CONTRADICTED
            )
        self.assertEqual(
            self.service.get_group("p1", group.group_id).status,
            IdentityGroupStatus.OPEN,
        )

    # --- ⑥ project purge 정리 ----------------------------------------------

    def test_purge_project_clears_groups_members_and_relations(self) -> None:
        group_p1 = self.service.create_group("p1", _CHARACTER)
        self.service.add_member("p1", group_p1.group_id, "cand:a", _CHARACTER)
        self.service.record_relation(
            "p1", _CHARACTER, "cand:a", "cand:b",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge",
            group_id=group_p1.group_id,
        )
        group_p2 = self.service.create_group("p2", _CHARACTER)
        self.service.add_member("p2", group_p2.group_id, "cand:z", _CHARACTER)

        self.service.purge_project(project_id="p1")

        with self.assertRaises(CandidateIdentityGroupNotFoundError):
            self.service.get_group("p1", group_p1.group_id)
        self.assertIsNone(
            self.service.get_relation("p1", _CHARACTER, "cand:a", "cand:b")
        )
        self.assertEqual(self.service.list_relations("p1"), ())
        # 인접 project는 무변 — 과잉 파기 방향.
        self.assertEqual(
            self.service.get_group("p2", group_p2.group_id), group_p2
        )
        self.assertEqual(
            len(self.service.list_members("p2", group_p2.group_id)), 1
        )
        self.assertEqual(len(self.service.list_relations("p2")), 0)


if __name__ == "__main__":
    unittest.main()
