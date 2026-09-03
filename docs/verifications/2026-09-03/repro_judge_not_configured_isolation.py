"""B1 probe — 러너 레벨 judge 미구성 격리의 행동 확인(Slice 2 검증).

`CandidateIdentityJudgingService`를 judge=None으로 주입(손조립 모양)하고
같은 이름 옛 후보로 판정 짝을 만든다. 계약 리터럴 ③("judge 미구성 어느 것이
와도 job은 succeeded·후보는 needs_review 잔류")의 행동을 잰다 — 셀이 없어서
probe로 대체 실측한 것(검증 기록 §Findings 5).

실행: python3 docs/verifications/2026-09-03/repro_judge_not_configured_isolation.py
기대 출력: PROBE-OK: judge=None → IdentityJudgeNotConfigured isolated, job SUCCEEDED
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.analysis.identity_judging import (
    CandidateIdentityJudgingService,
)
from services.application.app.analysis.models import AnalysisJobStatus
from services.application.app.analysis.runner import AnalysisExtractionRunner
from tests.test_identity_judging import _candidate
from tests.test_identity_judge_runner_wiring import RunnerWiringTestBase


class _StaticExtractor:
    def __init__(self, *drafts):
        self._drafts = drafts

    async def extract(self, _snapshot):
        return self._drafts


async def main() -> int:
    base = RunnerWiringTestBase()
    saved = base._saved_source()
    analysis_service, repo, source_adapter = base._analysis(saved["core_sot"])
    repo.put_candidate(
        _candidate(
            candidate_id="old-1",
            project_id=saved["project_id"],
            job_id="old-job",
            payload={"name": "민아", "observation": "옛 관찰"},
        ),
        logical_key="lk-old-1",
    )
    groups = CandidateIdentityGroupService(InMemoryCandidateIdentityGroupRepository())
    judging = CandidateIdentityJudgingService(
        group_service=groups, candidate_repository=repo, judge=None
    )
    runner = AnalysisExtractionRunner(
        analysis_service=analysis_service,
        snapshot_loader=source_adapter,
        extractor=_StaticExtractor(
            base._draft("c1", "민아", saved["anchors"]["min-a"])
        ),
        identity_judging=judging,
    )
    result = await runner.run(
        project_id=saved["project_id"],
        snapshot_id=saved["snapshot_id"],
        idempotency_key="probe-misconfig",
    )
    assert result.job.status is AnalysisJobStatus.SUCCEEDED, result.job.status
    assert groups.list_relations(saved["project_id"]) == ()
    print("PROBE-OK: judge=None → IdentityJudgeNotConfigured isolated, job SUCCEEDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
