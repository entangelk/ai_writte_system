"""B1·B2 probe — Slice 4 리터럴 ① 미잠급 조항의 행동 실측(2026-09-04 검증).

SoT v1.8.27 리터럴 ①: "terminal(confirmed·rejected·superseded) **전 종류**는
skip한다"·"승격 여부(``is_candidate_promoted``)는 **보지 않는다**(승격된
needs_review 후보도 거절되며 canonical은 append-only라 그대로 남는다)".
10셀 어디도 이 두 조항을 잠그지 않는다(검증자 변이 VM-A — skip 열거에서
superseded만 빼도 10 passed; B2는 전 suite에 상응 셀 부재). 이 probe는 행동이
계약대로임을 실측한다 — 빈 것은 잠금뿐이다(Slice 1 B1~B3·Slice 3 B1과 같은 모양).
폐쇄 셀의 본체로도 쓸 수 있다.

실행: python3 docs/verifications/2026-09-04/repro_slice4_member_literals.py
기대 출력: PROBE-OK: superseded 멤버는 skip되고 … / PROBE-OK: 승격 멤버도 거절되며 …
"""
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx

from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
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
from services.application.app.memory.models import PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)
from tests.auth_support import authenticate

CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


class _Client:
    def __init__(self, app):
        authenticate(app)
        self._app = app

    def post(self, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(path, **kwargs)

        return asyncio.run(send())


def _build():
    """tests/test_identity_group_reject.py _build 와 같은 조립 + memory 참조."""
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    groups = CandidateIdentityGroupService(
        InMemoryCandidateIdentityGroupRepository(),
        clock=lambda: datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
    )
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory,
        index_sync_outbox=IndexSyncOutboxService(InMemoryIndexSyncRepository()),
        review_queue_service=ReviewQueueService(InMemoryReviewQueueRepository()),
        identity_group_service=groups,
    )
    client = _Client(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, groups, project_id


def _seed(analysis, *, project_id, logical_key):
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


def _reject(client, project_id, group_id):
    return client.post(
        f"/projects/{project_id}/analysis/review-inbox/groups/{group_id}/reject"
    )


def probe_b1() -> None:
    client, analysis, _memory, groups, project_id = _build()
    a = _seed(analysis, project_id=project_id, logical_key="a")
    b = _seed(analysis, project_id=project_id, logical_key="b")
    group = groups.create_group(project_id, CHARACTER)
    for candidate in (a, b):
        groups.add_member(
            project_id=project_id, group_id=group.group_id,
            candidate_id=candidate.id, candidate_type=CHARACTER,
        )
    # edit는 원본 b를 superseded로 만든다(승격 후보는 신규 id — 그룹 밖).
    analysis.edit_candidate(
        project_id=project_id, candidate_id=b.id,
        payload={"name": "Ariel", "observation": "edited"},
    )
    assert analysis.get_candidate(
        project_id=project_id, candidate_id=b.id
    ).status.value == "superseded"

    response = _reject(client, project_id, group.group_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"] == [a.id], body
    assert body["skipped"] == [b.id], body
    print("PROBE-OK: superseded 멤버는 skip되고 나머지만 거절된다 "
          f"(rejected={[a.id]}, skipped={[b.id]})")


def probe_b2() -> None:
    client, analysis, memory, groups, project_id = _build()
    a = _seed(analysis, project_id=project_id, logical_key="a")
    b = _seed(analysis, project_id=project_id, logical_key="b")
    group = groups.create_group(project_id, CHARACTER)
    for candidate in (a, b):
        groups.add_member(
            project_id=project_id, group_id=group.group_id,
            candidate_id=candidate.id, candidate_type=CHARACTER,
        )
    # auto-promote와 같은 면 — 승격은 상태를 바꾸지 않는다(memory/service.py:
    # "a promoted candidate still carries needs_review status").
    memory.promote_candidate(
        project_id=project_id, candidate=a, mode=PromotionMode.AUTO_THRESHOLD,
    )
    assert memory.is_candidate_promoted(project_id, a.id)
    assert analysis.get_candidate(
        project_id=project_id, candidate_id=a.id
    ).status.value == "needs_review"

    response = _reject(client, project_id, group.group_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"] == sorted([a.id, b.id]), body
    assert body["skipped"] == [], body
    assert memory.is_candidate_promoted(project_id, a.id)
    print("PROBE-OK: 승격 멤버도 거절되며 canonical은 그대로 남는다 "
          f"(rejected={body['rejected']}, promoted={a.id} 잔존)")


def main() -> int:
    probe_b1()
    probe_b2()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
