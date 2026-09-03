"""미승인 후보 정체성 그룹 Slice 1 — shortlist와 판정 서비스.

계획: ``docs/plans/pending-candidate-identity-grouping-implementation-phases.md``
Slice 1. runner·HTTP 배선은 이 Slice 밖이다. 잠그는 계약:

1. shortlist는 같은 project/type의 ``needs_review`` 후보만 — character는 정규화
   이름 신호, event/open-question은 주입 retriever(없으면 no-op).
2. 같은 job의 후보도 비교 대상이나 같은 candidate id는 제외한다.
3. judge 미구성은 판정이 필요한 pair가 있을 때만 명시 오류 — shortlist가 비면
   오류 없이 no-op다.
4. ``same``만 group member로 연결하고 ``uncertain``은 relation만 남긴다.
5. 같은 pair 재실행은 멱등 — judge 재호출 없이 저장 판정을 재사용한다.
6. A=B·B=C·A≠C 추이성 모순이 group ``contradicted``로 남는다(도착 순서 무관).
7. ``same``이 서로 다른 두 group을 잇면 하나로 합친다 — 오래된 group이 살아남고
   흡수된 group은 ``closed`` 껍데기가 되며 이후 후보 소속 판정에서 제외된다.

양방향:
- under — 정규화·격리·재사용·그룹 연결·모순 표시·병합을 무력화하면 각 셀이
  재실패한다.
- over — 예: 재사용을 "모든 pair 재판정"으로 바꾸는 순간 멱등 셀이, 소속 판정이
  ``closed`` 껍데기를 다시 보는 순간 병합 셀이 실패한다.
"""

import asyncio
import unittest
from datetime import UTC, datetime

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    IdentityGroupStatus,
    IdentityRelationVerdict,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.analysis.identity_judging import (
    CandidateIdentityJudgingService,
    CandidateNotNeedsReviewError,
    CandidateNotFoundForIdentityJudging,
    IdentityJudgeNotConfigured,
    IdentityJudgement,
    InvalidIdentityJudgement,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.analysis.service import InMemoryAnalysisRepository

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _FixedClock:
    """시각을 한 칸씩 전진 — added_at/created_at 보존을 잰다."""

    def __init__(self) -> None:
        self._ticks = iter(range(0, 300, 10))
        self.now = datetime(2026, 9, 3, 9, next(self._ticks), tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self) -> None:
        self.now = datetime(2026, 9, 3, 9, next(self._ticks), tzinfo=UTC)


class _ScriptedJudge:
    """정렬 pair → 판정 표. 호출 pair를 기록해 재호출 멱등을 잰다."""

    def __init__(self, table, *, async_mode: bool = False) -> None:
        # table: {(작은 id, 큰 id): IdentityJudgement}
        self._table = dict(table)
        self._async = async_mode
        self.calls: list[tuple[str, str]] = []

    def judge(self, *, left, right):
        key = tuple(sorted((left.id, right.id)))
        self.calls.append(key)
        result = self._table[key]

        async def _deferred():
            return result

        return _deferred() if self._async else result


class _ScriptedRetriever:
    """focal id → pool 중 shortlist로 돌려줄 id 목록. 받은 pool도 기록한다."""

    def __init__(self, selection: dict[str, tuple[str, ...]]) -> None:
        self._selection = dict(selection)
        self.pools: dict[str, tuple[str, ...]] = {}

    def shortlist(self, *, project_id, candidate, pool):
        self.pools[candidate.id] = tuple(c.id for c in pool)
        wanted = self._selection.get(candidate.id, ())
        by_id = {c.id: c for c in pool}
        return tuple(by_id[i] for i in wanted if i in by_id)


def _candidate(
    *,
    candidate_id: str,
    project_id: str = "p1",
    job_id: str = "job-1",
    candidate_type: AnalysisCandidateType = CHARACTER,
    payload: dict | None = None,
    status: AnalysisCandidateStatus = AnalysisCandidateStatus.NEEDS_REVIEW,
) -> AnalysisCandidate:
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave"}
    return AnalysisCandidate(
        id=candidate_id,
        project_id=project_id,
        job_id=job_id,
        task_id="task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    )


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


class IdentityJudgingTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _FixedClock()
        self.groups = CandidateIdentityGroupService(
            InMemoryCandidateIdentityGroupRepository(), clock=self.clock
        )
        self.repo = InMemoryAnalysisRepository()

    def _service(
        self, judge=None, retriever=None
    ) -> CandidateIdentityJudgingService:
        return CandidateIdentityJudgingService(
            group_service=self.groups,
            candidate_repository=self.repo,
            judge=judge,
            shortlist_retriever=retriever,
        )

    def _judge_candidate(self, service, *, candidate_id, project_id="p1"):
        return asyncio.run(
            service.judge_candidate(
                project_id=project_id, candidate_id=candidate_id
            )
        )

    def _store(self, *candidates: AnalysisCandidate) -> None:
        for candidate in candidates:
            self.repo.put_candidate(candidate, logical_key=candidate.id)


class ShortlistTest(IdentityJudgingTestBase):
    def test_character_shortlist_uses_normalized_name(self) -> None:
        focal = _candidate(candidate_id="cand-a", payload={"name": "Ariel", "observation": "x"})
        same_name = _candidate(candidate_id="cand-b", payload={"name": "  ariel ", "observation": "y"})
        other_name = _candidate(candidate_id="cand-c", payload={"name": "에리엘", "observation": "z"})
        self._store(focal, same_name, other_name)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.UNCERTAIN, "표기만 다름")}
        )

        result = self._judge_candidate(
            self._service(judge=judge), candidate_id="cand-a"
        )

        self.assertEqual(result.shortlisted_candidate_ids, ("cand-b",))
        self.assertEqual(judge.calls, [_pair("cand-a", "cand-b")])

    def test_shortlist_is_isolated_by_project(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        stranger = _candidate(candidate_id="cand-b", project_id="p2")
        self._store(focal, stranger)
        judge = _ScriptedJudge({})

        result = self._judge_candidate(self._service(judge=judge), candidate_id="cand-a")

        self.assertEqual(result.shortlisted_candidate_ids, ())
        self.assertEqual(judge.calls, [])

    def test_shortlist_is_isolated_by_candidate_type(self) -> None:
        character = _candidate(candidate_id="cand-a")
        event_focal = _candidate(
            candidate_id="cand-b",
            candidate_type=EVENT,
            payload={"event": "폭풍의 밤"},
        )
        event_other = _candidate(
            candidate_id="cand-c",
            candidate_type=EVENT,
            payload={"event": "폭풍이 지나갔다"},
        )
        self._store(character, event_focal, event_other)
        retriever = _ScriptedRetriever({"cand-b": ("cand-c",)})
        judge = _ScriptedJudge(
            {_pair("cand-b", "cand-c"): IdentityJudgement(IdentityRelationVerdict.UNCERTAIN, "사건 비교")}
        )

        self._judge_candidate(
            self._service(judge=judge, retriever=retriever), candidate_id="cand-b"
        )

        # retriever가 받은 pool에는 같은 type의 needs_review 후보만 있다.
        self.assertEqual(retriever.pools["cand-b"], ("cand-c",))

    def test_same_job_candidates_are_eligible_but_self_is_excluded(self) -> None:
        focal = _candidate(candidate_id="cand-a", job_id="job-1")
        sibling = _candidate(candidate_id="cand-b", job_id="job-1")
        self._store(focal, sibling)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.UNCERTAIN, "같은 job")}
        )

        result = self._judge_candidate(
            self._service(judge=judge), candidate_id="cand-a"
        )

        self.assertEqual(result.shortlisted_candidate_ids, ("cand-b",))
        self.assertEqual(judge.calls, [_pair("cand-a", "cand-b")])

    def test_empty_shortlist_is_noop_without_judge(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        other = _candidate(candidate_id="cand-b", payload={"name": "유나", "observation": "다른 사람"})
        self._store(focal, other)

        result = self._judge_candidate(self._service(), candidate_id="cand-a")

        self.assertEqual(result.shortlisted_candidate_ids, ())
        self.assertIsNone(result.group_id)
        self.assertEqual(self.groups.list_groups("p1"), ())
        self.assertEqual(self.groups.list_relations("p1"), ())


class JudgementApplicationTest(IdentityJudgingTestBase):
    def test_missing_judge_is_an_explicit_error_only_when_pairs_exist(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        twin = _candidate(candidate_id="cand-b", payload={"name": " ariel ", "observation": "다른 관찰"})
        self._store(focal, twin)

        with self.assertRaises(IdentityJudgeNotConfigured):
            self._judge_candidate(self._service(), candidate_id="cand-a")

    def test_same_verdict_connects_group_members(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        twin = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 관찰"})
        self._store(focal, twin)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.SAME, "같은 인물 'Ariel'")}
        )

        result = self._judge_candidate(
            self._service(judge=judge), candidate_id="cand-a"
        )

        (group,) = self.groups.list_groups("p1")
        self.assertEqual(group.status, IdentityGroupStatus.OPEN)
        self.assertEqual(
            tuple(m.candidate_id for m in self.groups.list_members("p1", group.group_id)),
            ("cand-a", "cand-b"),
        )
        self.assertEqual(result.group_id, group.group_id)
        (relation,) = self.groups.list_relations("p1")
        self.assertEqual(relation.verdict, IdentityRelationVerdict.SAME)
        self.assertEqual(relation.group_id, group.group_id)

    def test_different_and_uncertain_leave_relation_only(self) -> None:
        a = _candidate(candidate_id="cand-a")
        b = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 인물"})
        c = _candidate(candidate_id="cand-c", payload={"name": "ARIEL", "observation": "애매함"})
        self._store(a, b, c)
        judge = _ScriptedJudge(
            {
                _pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.DIFFERENT, "다른 인물"),
                _pair("cand-a", "cand-c"): IdentityJudgement(IdentityRelationVerdict.UNCERTAIN, "근거 부족"),
            }
        )

        result = self._judge_candidate(
            self._service(judge=judge), candidate_id="cand-a"
        )

        self.assertEqual(self.groups.list_groups("p1"), ())
        self.assertIsNone(result.group_id)
        by_pair = {
            (r.left_candidate_id, r.right_candidate_id): r
            for r in self.groups.list_relations("p1")
        }
        different = by_pair[("cand-a", "cand-b")]
        uncertain = by_pair[("cand-a", "cand-c")]
        self.assertEqual(different.verdict, IdentityRelationVerdict.DIFFERENT)
        self.assertIsNone(different.group_id)
        self.assertEqual(uncertain.verdict, IdentityRelationVerdict.UNCERTAIN)
        self.assertIsNone(uncertain.group_id)

    def test_invalid_judgement_is_rejected(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        twin = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 관찰"})
        self._store(focal, twin)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement("maybe", "허위 verdict")}  # type: ignore[arg-type]
        )

        with self.assertRaises(InvalidIdentityJudgement):
            self._judge_candidate(self._service(judge=judge), candidate_id="cand-a")
        # 거부된 판정은 relation으로 남지 않는다.
        self.assertEqual(self.groups.list_relations("p1"), ())

    def test_judge_exception_propagates(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        twin = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 관찰"})
        self._store(focal, twin)
        judge = _ScriptedJudge({})
        judge.judge = lambda **_: (_ for _ in ()).throw(RuntimeError("provider boom"))

        with self.assertRaises(RuntimeError):
            self._judge_candidate(self._service(judge=judge), candidate_id="cand-a")

    def test_awaitable_judge_result_is_awaited(self) -> None:
        focal = _candidate(candidate_id="cand-a")
        twin = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 관찰"})
        self._store(focal, twin)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.SAME, "비동기 판정")},
            async_mode=True,
        )

        result = self._judge_candidate(
            self._service(judge=judge), candidate_id="cand-a"
        )

        self.assertIsNotNone(result.group_id)
        self.assertEqual(judge.calls, [_pair("cand-a", "cand-b")])

    def test_focal_must_exist_and_be_needs_review(self) -> None:
        with self.assertRaises(CandidateNotFoundForIdentityJudging):
            self._judge_candidate(self._service(), candidate_id="cand-none")

        stored_elsewhere = _candidate(candidate_id="cand-x", project_id="p2")
        self._store(stored_elsewhere)
        with self.assertRaises(CandidateNotFoundForIdentityJudging):
            self._judge_candidate(self._service(), candidate_id="cand-x")

        rejected = _candidate(candidate_id="cand-r", status=AnalysisCandidateStatus.REJECTED)
        self._store(rejected)
        with self.assertRaises(CandidateNotNeedsReviewError):
            self._judge_candidate(self._service(), candidate_id="cand-r")


class IdempotencyTest(IdentityJudgingTestBase):
    def test_rerun_reuses_stored_relation_without_rejudging(self) -> None:
        a = _candidate(candidate_id="cand-a")
        b = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 관찰"})
        self._store(a, b)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.SAME, "같은 인물")}
        )
        service = self._service(judge=judge)

        first = self._judge_candidate(service, candidate_id="cand-a")
        self.assertEqual(first.judged_pair_ids, (_pair("cand-a", "cand-b"),))
        (relation_before,) = self.groups.list_relations("p1")
        (group,) = self.groups.list_groups("p1")
        members_before = self.groups.list_members("p1", group.group_id)

        self.clock.advance()
        second = self._judge_candidate(service, candidate_id="cand-a")

        # judge는 한 번만 불렸고, 두 번째 실행은 저장 판정을 재사용했다.
        self.assertEqual(judge.calls, [_pair("cand-a", "cand-b")])
        self.assertEqual(second.judged_pair_ids, ())
        self.assertEqual(second.reused_pair_ids, (_pair("cand-a", "cand-b"),))
        self.assertEqual(len(self.groups.list_relations("p1")), 1)
        (relation_after,) = self.groups.list_relations("p1")
        self.assertEqual(relation_after, relation_before)  # created_at 포함 불변
        self.assertEqual(len(self.groups.list_groups("p1")), 1)  # 그룹 추가 생성 없음
        (group_after,) = self.groups.list_groups("p1")
        self.assertEqual(group_after.revision, group.revision)  # 상태 변경 없음
        self.assertEqual(
            self.groups.list_members("p1", group_after.group_id), members_before
        )  # added_at 불변


class TransitivityContradictionTest(IdentityJudgingTestBase):
    def _same_name(self, *ids: str) -> tuple[AnalysisCandidate, ...]:
        return tuple(
            _candidate(candidate_id=i, payload={"name": "Ariel", "observation": i})
            for i in ids
        )

    def test_different_after_same_marks_group_contradicted(self) -> None:
        # 계획 순서: A=B, B=C (same) 뒤에 A≠C (different)가 도착한다.
        a, b = self._same_name("cand-a", "cand-b")
        self._store(a, b)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.SAME, "A=B")}
        )
        service = self._service(judge=judge)
        self._judge_candidate(service, candidate_id="cand-a")

        c = _candidate(candidate_id="cand-c", payload={"name": "Ariel", "observation": "셋째"})
        self._store(c)
        judge._table[_pair("cand-b", "cand-c")] = IdentityJudgement(
            IdentityRelationVerdict.SAME, "B=C"
        )
        self._judge_candidate(service, candidate_id="cand-b")
        (group,) = self.groups.list_groups("p1")
        self.assertEqual(group.status, IdentityGroupStatus.OPEN)

        judge._table[_pair("cand-a", "cand-c")] = IdentityJudgement(
            IdentityRelationVerdict.DIFFERENT, "A≠C"
        )
        self._judge_candidate(service, candidate_id="cand-c")

        (group,) = self.groups.list_groups("p1")
        self.assertEqual(group.status, IdentityGroupStatus.CONTRADICTED)
        # 모순 표시는 정확히 한 번의 상태 전환이다(재실행·재표시 멱등).
        self.assertEqual(group.revision, 1)
        # relation은 전부 보존된다 — 모순이라고 지우지 않는다.
        verdicts = {
            (r.left_candidate_id, r.right_candidate_id): r.verdict
            for r in self.groups.list_relations("p1")
        }
        self.assertEqual(
            verdicts,
            {
                ("cand-a", "cand-b"): IdentityRelationVerdict.SAME,
                ("cand-b", "cand-c"): IdentityRelationVerdict.SAME,
                ("cand-a", "cand-c"): IdentityRelationVerdict.DIFFERENT,
            },
        )

    def test_same_closing_a_different_triangle_also_contradicts(self) -> None:
        # 도착 역순: A≠C가 먼저 기록되고 B=C same이 삼각형을 닫는다.
        a, b, c = self._same_name("cand-a", "cand-b", "cand-c")
        self._store(a, b, c)
        judge = _ScriptedJudge(
            {
                _pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.SAME, "A=B"),
                _pair("cand-a", "cand-c"): IdentityJudgement(IdentityRelationVerdict.DIFFERENT, "A≠C"),
            }
        )
        service = self._service(judge=judge)
        self._judge_candidate(service, candidate_id="cand-a")
        # 아직 B=C가 없어 성분이 a-b뿐 — 모순 아니다.
        (group,) = self.groups.list_groups("p1")
        self.assertEqual(group.status, IdentityGroupStatus.OPEN)

        judge._table[_pair("cand-b", "cand-c")] = IdentityJudgement(
            IdentityRelationVerdict.SAME, "B=C"
        )
        self._judge_candidate(service, candidate_id="cand-b")

        (group,) = self.groups.list_groups("p1")
        self.assertEqual(group.status, IdentityGroupStatus.CONTRADICTED)
        self.assertEqual(
            tuple(
                m.candidate_id for m in self.groups.list_members("p1", group.group_id)
            ),
            ("cand-a", "cand-b", "cand-c"),
        )

    def test_plain_different_pair_never_contradicts(self) -> None:
        # over-strict 방향 — same 성분이 없는 different는 그냥 relation이다.
        a = _candidate(candidate_id="cand-a")
        b = _candidate(candidate_id="cand-b", payload={"name": "ariel", "observation": "다른 인물"})
        self._store(a, b)
        judge = _ScriptedJudge(
            {_pair("cand-a", "cand-b"): IdentityJudgement(IdentityRelationVerdict.DIFFERENT, "다른 인물")}
        )

        self._judge_candidate(self._service(judge=judge), candidate_id="cand-a")

        self.assertEqual(self.groups.list_groups("p1"), ())


class GroupMergeTest(IdentityJudgingTestBase):
    def _event(self, candidate_id: str, text: str) -> AnalysisCandidate:
        return _candidate(
            candidate_id=candidate_id,
            candidate_type=EVENT,
            payload={"event": text},
        )

    def test_same_across_two_groups_merges_into_the_older_group(self) -> None:
        e1 = self._event("cand-e1", "폭풍의 밤")
        e2 = self._event("cand-e2", "폭풍의 밤 지나고")
        e3 = self._event("cand-e3", "새로운 조우")
        e4 = self._event("cand-e4", "조우의 여운")
        self._store(e1, e2, e3, e4)
        retriever = _ScriptedRetriever(
            {"cand-e1": ("cand-e2",), "cand-e3": ("cand-e4",)}
        )
        judge = _ScriptedJudge(
            {
                _pair("cand-e1", "cand-e2"): IdentityJudgement(IdentityRelationVerdict.SAME, "같은 사건"),
                _pair("cand-e3", "cand-e4"): IdentityJudgement(IdentityRelationVerdict.SAME, "같은 사건"),
            }
        )
        service = self._service(judge=judge, retriever=retriever)
        self._judge_candidate(service, candidate_id="cand-e1")
        self._judge_candidate(service, candidate_id="cand-e3")
        group1, group2 = sorted(
            self.groups.list_groups("p1"), key=lambda g: g.created_at
        )
        self.assertEqual(group1.status, IdentityGroupStatus.OPEN)
        self.assertEqual(group2.status, IdentityGroupStatus.OPEN)
        self.assertNotEqual(group1.group_id, group2.group_id)

        # 같은 사건 판정이 두 그룹을 잇는다 — 오래된 그룹이 살아남는다.
        retriever._selection["cand-e1"] = ("cand-e3",)
        judge._table[_pair("cand-e1", "cand-e3")] = IdentityJudgement(
            IdentityRelationVerdict.SAME, "두 사건은 같은 사건"
        )
        result = self._judge_candidate(service, candidate_id="cand-e1")

        self.assertEqual(result.group_id, group1.group_id)
        self.assertEqual(group1.status, IdentityGroupStatus.OPEN)
        self.assertEqual(
            tuple(
                m.candidate_id
                for m in self.groups.list_members("p1", group1.group_id)
            ),
            ("cand-e1", "cand-e2", "cand-e3", "cand-e4"),
        )
        refreshed2 = [
            g for g in self.groups.list_groups("p1") if g.group_id == group2.group_id
        ][0]
        self.assertEqual(refreshed2.status, IdentityGroupStatus.CLOSED)

        # 흡수된 closed 껍데기는 이후 소속 판정에서 보이지 않는다 — 같은
        # 그룹에 이미 있으므로 새 그룹은 생기지 않는다.
        retriever._selection["cand-e4"] = ("cand-e2",)
        judge._table[_pair("cand-e2", "cand-e4")] = IdentityJudgement(
            IdentityRelationVerdict.SAME, "여전히 같은 사건"
        )
        after = self._judge_candidate(service, candidate_id="cand-e4")
        self.assertEqual(after.group_id, group1.group_id)
        open_groups = [
            g
            for g in self.groups.list_groups("p1")
            if g.status is IdentityGroupStatus.OPEN
        ]
        self.assertEqual(len(open_groups), 1)


if __name__ == "__main__":
    unittest.main()
