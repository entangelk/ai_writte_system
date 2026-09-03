"""미승인 후보 정체성 그룹 Slice 2 — 분석 runner 배선.

계획: ``docs/plans/pending-candidate-identity-grouping-implementation-phases.md``
Slice 2. 분석 candidate가 저장된 뒤 Slice 1 서비스를 호출해 identity
relation/group을 생성한다. Review Inbox 응답·액션은 바꾸지 않는다. 잠그는 계약:

1. **성공 경로에서만 판정** — 후보 저장 실패·job 실패에는 group 판정을 시도하지
   않는다. 판정은 job이 종결(success)에 도달한 뒤에 돈다.
2. **focal은 이번 job에 기록된 후보뿐** — pool의 옛 후보는 비교 대상이 되어도
   스스로 판정을 다니지는 않는다.
3. **후보 0개 / no shortlist는 no-op** — judge를 부르지 않고 relation도 남기지
   않는다(event/open-question은 retriever 미주입 no-op, Slice 1 B1의 runner 면).
4. **판정 실패 격리** — judge ProviderError·terminal parse rejection(
   ``InvalidIdentityJudgement``)은 job을 실패로 바꾸지 않고 후보는
   ``needs_review``로 남는다. 첫 실패가 판정 단계를 끝낸다(죽은 게이트웨이에
   남은 pair만큼 timeout을 태우지 않는다).
5. **LLM audit 행 수** — 판정 pair당 1행(``identity_judge`` site,
   ``correlation_id``=job_id — run endpoint의 scope를 탄다), repair 재시도는
   둘째 행, terminal 거부는 마지막 행의 ``parse_error`` 재분류(D4). provider
   실패 행은 자기 taxonomy를 유지한다.

양방향:
- under — 배선을 끊거나(1·3·5 격), 격리를 없애 판정 실패가 job 실패로 새면
  (4) 각 셀이 재실패한다.
- over — 저장된 relation을 재판정하면 행 수 셀이, 옛 후보를 focal로 삼으면
  focal 셀이, job 종결 *전*으로 판정을 옮기면 저장 실패 셀이 실패한다.
"""

import json
import unittest

from services.application.app.analysis.extractor import AnalysisCandidateDraft
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    IdentityRelationVerdict,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.analysis.identity_judge import (
    TerminalJsonIdentityJudge,
    seed_analysis_identity_judge_template,
)
from services.application.app.analysis.identity_judging import (
    CandidateIdentityJudgingService,
    IdentityJudgement,
    InvalidIdentityJudgement,
)
from services.application.app.analysis.models import (
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisJobStatus,
    AnalysisProvenance,
    CandidateSourceAnchor,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.analysis.runner import AnalysisExtractionRunner
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
    InvalidCandidateSource,
)
from services.application.app.analysis.source import CoreSotSourceAdapter
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
)
from services.application.app.observability.llm_call_scope import llm_call_scope
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode

from tests.test_identity_judging import _candidate
from tests.test_llm_call_sites import _observed


class _StaticExtractor:
    def __init__(self, drafts):
        self._drafts = drafts

    async def extract(self, _snapshot):
        return self._drafts


class _AlwaysSameJudge:
    """어느 pair든 ``same``으로 답하고 호출 pair를 기록한다."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def judge(self, *, left, right):
        self.calls.append(tuple(sorted((left.id, right.id))))
        return IdentityJudgement(IdentityRelationVerdict.SAME, "같은 인물")


class _RaisingJudge:
    """호출 pair를 기록하고 항상 같은 예외를 던진다(격리 축)."""

    def __init__(self, error):
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def judge(self, *, left, right):
        self.calls.append(tuple(sorted((left.id, right.id))))
        raise self.error


class RunnerWiringTestBase(unittest.IsolatedAsyncioTestCase):
    def _analysis(self, core_sot):
        repo = InMemoryAnalysisRepository()
        source_adapter = CoreSotSourceAdapter(core_sot)
        return (
            AnalysisService(repo, source_ref_resolver=source_adapter),
            repo,
            source_adapter,
        )

    def _saved_source(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        project = core_sot.create_project(name="Novel")
        draft = core_sot.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "민아는 파란 편지를 발견했다.\n\n수아가 그것을 보았다."
        saved = core_sot.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        min_a = self._source_ref(core_sot, project.id, saved.snapshot.id, raw_text, "민아")
        su_a = self._source_ref(core_sot, project.id, saved.snapshot.id, raw_text, "수아")
        return {
            "core_sot": core_sot,
            "project_id": project.id,
            "snapshot_id": saved.snapshot.id,
            "anchors": {
                "min-a": self._anchor(min_a),
                "su-a": self._anchor(su_a),
            },
        }

    @staticmethod
    def _source_ref(core_sot, project_id, snapshot_id, raw_text, quote):
        start = raw_text.index(quote)
        return core_sot.create_source_ref(
            project_id=project_id,
            snapshot_id=snapshot_id,
            start_offset=start,
            end_offset=start + len(quote),
        )

    @staticmethod
    def _anchor(source_ref):
        return {
            "source_ref_id": source_ref.id,
            "start_offset": source_ref.start_offset,
            "end_offset": source_ref.end_offset,
            "quote": source_ref.quote,
            "content_hash": source_ref.content_hash,
        }

    def _wiring(self, judge, drafts=None, *, with_judging=True):
        """drafts는 ``saved``를 받아 draft 묶음을 돌려주는 callable(앵커용)."""
        saved = self._saved_source()
        analysis_service, repo, source_adapter = self._analysis(saved["core_sot"])
        resolved = drafts(saved) if callable(drafts) else (drafts or ())
        groups = CandidateIdentityGroupService(
            InMemoryCandidateIdentityGroupRepository()
        )
        judging = None
        if with_judging:
            judging = CandidateIdentityJudgingService(
                group_service=groups,
                candidate_repository=repo,
                judge=judge,
            )
        runner = AnalysisExtractionRunner(
            analysis_service=analysis_service,
            snapshot_loader=source_adapter,
            extractor=_StaticExtractor(resolved),
            identity_judging=judging,
        )
        return {
            "saved": saved,
            "analysis": analysis_service,
            "repo": repo,
            "groups": groups,
            "runner": runner,
        }

    def _draft(self, logical_key, name, anchor):
        return AnalysisCandidateDraft(
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9,
            source_anchors=(CandidateSourceAnchor(**anchor),),
            payload={"name": name, "observation": f"{name}에 대한 관찰"},
            logical_key=logical_key,
        )

    def _event_draft(self, logical_key, anchor):
        return AnalysisCandidateDraft(
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9,
            source_anchors=(CandidateSourceAnchor(**anchor),),
            payload={"event": "민아가 편지를 발견했다."},
            logical_key=logical_key,
        )

    def _same_name_drafts(self, saved):
        return (
            self._draft("c1", "민아", saved["anchors"]["min-a"]),
            self._draft("c2", "민아", saved["anchors"]["su-a"]),
        )

    @staticmethod
    def _pair(a: str, b: str) -> tuple[str, str]:
        return tuple(sorted((a, b)))

    async def _run(self, wiring, *, key):
        saved = wiring["saved"]
        return await wiring["runner"].run(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key=key,
        )


class SuccessPathWiringTest(RunnerWiringTestBase):
    async def test_success_path_judges_recorded_candidates_after_save(self):
        # judge가 pool을 저장소에서 읽으므로, 판정 pair가 보였다는 것 자체가
        # "후보 저장 뒤"에 호출됐다는 증명이다(저장 전이면 pool이 비어 무호출).
        judge = _AlwaysSameJudge()
        wiring = self._wiring(judge, self._same_name_drafts)

        result = await self._run(wiring, key="identity-run-1")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        candidate_ids = sorted(c.id for c in result.candidates)
        self.assertEqual(judge.calls, [self._pair(*candidate_ids)])
        for candidate in result.candidates:
            self.assertIs(candidate.status, AnalysisCandidateStatus.NEEDS_REVIEW)
        relations = wiring["groups"].list_relations(wiring["saved"]["project_id"])
        self.assertEqual(len(relations), 1)
        self.assertIs(relations[0].verdict, IdentityRelationVerdict.SAME)
        self.assertEqual(relations[0].source, "identity_judge")
        groups = wiring["groups"].list_groups(wiring["saved"]["project_id"])
        self.assertEqual(len(groups), 1)
        members = wiring["groups"].list_members(
            wiring["saved"]["project_id"], groups[0].group_id
        )
        self.assertEqual(sorted(m.candidate_id for m in members), candidate_ids)

    async def test_only_this_jobs_candidates_are_focal(self):
        # 옛 후보(old-1·old-2)는 pool에 들어가 new와 비교되지만, 둘 사이의
        # pair은 어느 쪽도 focal이 아니므로 판정되지 않는다. focal을 "저장소의
        # needs_review 전체"로 넓히는 과잉은 이 셀이 잡는다(calls가 3이 된다).
        judge = _AlwaysSameJudge()
        wiring = self._wiring(
            judge,
            lambda saved: (self._draft("c1", "민아", saved["anchors"]["min-a"]),),
        )
        saved = wiring["saved"]
        for old_id in ("old-1", "old-2"):
            wiring["repo"].put_candidate(
                _candidate(
                    candidate_id=old_id,
                    project_id=saved["project_id"],
                    job_id="old-job",
                    payload={"name": "민아", "observation": "옛 관찰"},
                ),
                logical_key=f"lk-{old_id}",
            )

        result = await self._run(wiring, key="identity-run-focal")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        new_id = result.candidates[0].id
        self.assertEqual(judge.calls, [
            self._pair(new_id, "old-1"),
            self._pair(new_id, "old-2"),
        ])
        relation_pairs = {
            self._pair(r.left_candidate_id, r.right_candidate_id)
            for r in wiring["groups"].list_relations(saved["project_id"])
        }
        self.assertNotIn(self._pair("old-1", "old-2"), relation_pairs)

    async def test_zero_candidates_is_noop(self):
        judge = _AlwaysSameJudge()
        wiring = self._wiring(judge)

        result = await self._run(wiring, key="identity-run-empty")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(judge.calls, [])
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )
        self.assertEqual(
            wiring["groups"].list_groups(wiring["saved"]["project_id"]), ()
        )

    async def test_no_shortlist_is_noop(self):
        # character 이름 불일치 2건 + retriever 미주입 event 2건 — 어느 축도
        # shortlist가 비면 judge를 부르지 않는다(Slice 1 B1의 runner 면).
        judge = _AlwaysSameJudge()
        wiring = self._wiring(
            judge,
            lambda saved: (
                self._draft("c1", "민아", saved["anchors"]["min-a"]),
                self._draft("c2", "수아", saved["anchors"]["su-a"]),
                self._event_draft("e1", saved["anchors"]["min-a"]),
                self._event_draft("e2", saved["anchors"]["su-a"]),
            ),
        )

        result = await self._run(wiring, key="identity-run-noshortlist")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(judge.calls, [])
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )

    async def test_missing_judging_wiring_is_noop(self):
        # judging 미주입(게이트웨이 없는 조립)은 판정 단계 자체가 없다.
        wiring = self._wiring(
            None,
            lambda saved: (self._draft("c1", "민아", saved["anchors"]["min-a"]),),
            with_judging=False,
        )

        result = await self._run(wiring, key="identity-run-unwired")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )


class IsolationTest(RunnerWiringTestBase):
    async def test_provider_error_does_not_fail_the_job(self):
        judge = _RaisingJudge(ProviderError(
            code=ProviderErrorCode.UNAVAILABLE,
            message="gateway is unavailable",
            retryable=True,
            provider="llm_gateway",
        ))
        wiring = self._wiring(judge, self._same_name_drafts)

        result = await self._run(wiring, key="identity-run-perr")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(len(judge.calls), 1)  # 첫 실패가 판정 단계를 끝낸다
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )
        for candidate in result.candidates:
            self.assertIs(candidate.status, AnalysisCandidateStatus.NEEDS_REVIEW)

    async def test_parse_error_does_not_fail_the_job(self):
        # scope 밖(run 직접 구동)에서도 격리는 성립 — current_scope()가 None인
        # 경로까지 함께 잰다.
        judge = _RaisingJudge(InvalidIdentityJudgement(
            "identity judge produced an invalid result: test"
        ))
        wiring = self._wiring(judge, self._same_name_drafts)

        result = await self._run(wiring, key="identity-run-parse")

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        self.assertEqual(len(judge.calls), 1)
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )
        for candidate in result.candidates:
            self.assertIs(candidate.status, AnalysisCandidateStatus.NEEDS_REVIEW)

    async def test_candidate_save_failure_skips_judging(self):
        # 유령 앵커 → preflight 실패 → job 실패. 판정은 시도조차 되지 않는다.
        # (판정을 job 종결 전으로 옮기는 변이도 이 셀이 잡는다 — 저장이
        # 무너진 뒤 판정이 돌면 judge.calls가 늘어난다.)
        judge = _RaisingJudge(InvalidIdentityJudgement("unreachable"))
        wiring = self._wiring(
            judge,
            lambda saved: (
                self._draft(
                    "c1", "민아",
                    dict(saved["anchors"]["min-a"], source_ref_id="ghost-ref"),
                ),
            ),
        )
        saved = wiring["saved"]
        job = wiring["analysis"].create_job(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key="identity-run-savefail",
        ).job

        with self.assertRaises(InvalidCandidateSource):
            await wiring["runner"].run_job(
                project_id=saved["project_id"], job_id=job.id
            )

        failed = wiring["analysis"].get_job(
            project_id=saved["project_id"], job_id=job.id
        )
        self.assertIs(failed.status, AnalysisJobStatus.FAILED)
        self.assertEqual(judge.calls, [])


def _identity_judge(*contents):
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    seed_analysis_identity_judge_template(templates)
    return TerminalJsonIdentityJudge(
        _observed(LlmCallSite.IDENTITY_JUDGE, *contents),
        prompt_templates=templates,
    )


def _same_content() -> str:
    return json.dumps(
        {"verdict": "same", "rationale": "같은 인물"}, ensure_ascii=False
    )


class AuditRowsTest(RunnerWiringTestBase):
    """실 adapter + seam C — 행 수·site·correlation_id·재분류를 잰다.

    run endpoint가 ``llm_call_scope(correlation_id=job_id)``로 runner를 감싸는
    모양을 그대로 재현한다(create_job → run_job). extractor는 provider를 쓰지
    않는 stand-in이라 판정 행만 남아 셈이 명료하다.
    """

    def _audit(self):
        return LlmCallAuditService(InMemoryLlmCallAuditRepository())

    async def _run_scoped(self, wiring, audit, *, key):
        saved = wiring["saved"]
        job = wiring["analysis"].create_job(
            project_id=saved["project_id"],
            snapshot_id=saved["snapshot_id"],
            idempotency_key=key,
        ).job
        with llm_call_scope(audit, project_id=saved["project_id"],
                            correlation_id=job.id):
            result = await wiring["runner"].run_job(
                project_id=saved["project_id"], job_id=job.id
            )
        return job, result

    async def test_each_judged_pair_leaves_exactly_one_record(self):
        # 같은 이름 3건 → 판정 pair 3(c1-c2·c1-c3·c2-c3). 재사용이 무너져
        # 저장된 relation을 재판정하면 3보다 커지고(과잉), pair당 1행이
        # 무너지면 집계 자체가 틀리다(과소).
        audit = self._audit()
        wiring = self._wiring(
            _identity_judge(_same_content(), _same_content(), _same_content()),
            lambda saved: self._same_name_drafts(saved) + (
                self._draft("c3", "민아", saved["anchors"]["min-a"]),
            ),
        )

        job, result = await self._run_scoped(
            wiring, audit, key="identity-audit-3pairs"
        )

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        calls = audit.list_calls(wiring["saved"]["project_id"])
        self.assertEqual(len(calls), 3)
        self.assertEqual({c.call_site for c in calls},
                         {LlmCallSite.IDENTITY_JUDGE.value})
        self.assertEqual({c.correlation_id for c in calls}, {job.id})
        self.assertEqual({c.outcome for c in calls},
                         {LlmCallOutcome.SUCCESS.value})

    async def test_repaired_verdict_leaves_two_rows_both_successful(self):
        audit = self._audit()
        wiring = self._wiring(
            _identity_judge("not json", _same_content()),
            self._same_name_drafts,
        )

        job, result = await self._run_scoped(
            wiring, audit, key="identity-audit-repair"
        )

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        calls = audit.list_calls(wiring["saved"]["project_id"])
        self.assertEqual(len(calls), 2)
        self.assertEqual({c.outcome for c in calls},
                         {LlmCallOutcome.SUCCESS.value})
        self.assertEqual({c.correlation_id for c in calls}, {job.id})

    async def test_terminal_rejection_is_reclassified_and_isolated(self):
        # 두 번 다 비-JSON → InvalidIdentityJudgement. 격리(4)와 D4 재분류가
        # 한 경로에서 만난다: job은 SUCCEEDED, 행은 [success, parse_error].
        audit = self._audit()
        wiring = self._wiring(
            _identity_judge("not json", "still not json"),
            self._same_name_drafts,
        )

        job, result = await self._run_scoped(
            wiring, audit, key="identity-audit-parse"
        )

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        calls = audit.list_calls(wiring["saved"]["project_id"])
        # list_calls는 newest-first — 재분류된 "마지막 호출"(repair)이 첫 행,
        # repair로 회수된 첫 시도는 success로 남는다(D4).
        self.assertEqual(
            [c.outcome for c in calls],
            [LlmCallOutcome.PARSE_ERROR.value, LlmCallOutcome.SUCCESS.value],
        )
        self.assertEqual(calls[0].error_type, "InvalidIdentityJudgement")

    async def test_provider_failure_row_keeps_its_taxonomy(self):
        audit = self._audit()
        wiring = self._wiring(
            _identity_judge(ProviderError(
                code=ProviderErrorCode.TIMEOUT,
                message="down",
                retryable=True,
            )),
            self._same_name_drafts,
        )

        job, result = await self._run_scoped(
            wiring, audit, key="identity-audit-perr"
        )

        self.assertIs(result.job.status, AnalysisJobStatus.SUCCEEDED)
        calls = audit.list_calls(wiring["saved"]["project_id"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].outcome, LlmCallOutcome.PROVIDER_ERROR.value)
        self.assertEqual(calls[0].error_type, "provider_timeout")
        self.assertEqual(
            wiring["groups"].list_relations(wiring["saved"]["project_id"]), ()
        )


if __name__ == "__main__":
    unittest.main()
