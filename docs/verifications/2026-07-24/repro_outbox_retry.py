"""Repro for verification 2026-07-24 / auto-promote-503-partial-envelope (B2).

Does the promised "retry recovers what is left" hold when the failure was an
outbox enqueue AFTER a successful mint? promote_candidate short-circuits
already-promoted candidates as idempotent replays BEFORE _enqueue_reindex
(service.py:158-163 vs :194), so a retry hitting a minted-but-enqueue-lost
candidate would skip re-enqueueing it entirely.

Run:  python3 docs/verifications/2026-07-24/repro_outbox_retry.py
Expected: retry 200 promoted=[], outbox enqueued still [memory-1],
         c2 minted-but-never-enqueued-for-reindex
"""
import sys
sys.path.insert(0, ".")

from pymongo.errors import AutoReconnect

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisCandidateAction,
    AnalysisProvenance,
)
from services.application.app.memory.service import (
    MemoryService,
    InMemoryMemoryRepository,
)
from services.application.app.main import create_app
from starlette.testclient import TestClient as _TC


class _Outbox:
    def __init__(self):
        self.calls = 0
        self.enqueued = []

    def enqueue_memory_upserted(self, *, project_id, memory_id, version):
        self.calls += 1
        if self.calls == 2:
            raise AutoReconnect("outbox write lost mid-call")
        self.enqueued.append(memory_id)


def main():
    analysis = AnalysisService(InMemoryAnalysisRepository())
    outbox = _Outbox()
    memory = MemoryService(
        InMemoryMemoryRepository(),
        auto_promotion_threshold=0.9,
        reindex_outbox=outbox,
    )
    app = create_app(
        service=CoreSotService(InMemoryCoreSotRepository()),
        analysis_service=analysis,
        memory_service=memory,
    )
    with _TC(app) as client:
        project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
        job = analysis.create_job(
            project_id=project_id, snapshot_id="snapshot-1", idempotency_key="k"
        ).job
        task = analysis.create_task(
            project_id=project_id,
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        cands = []
        for key, name in (("k1", "A"), ("k2", "B")):
            cands.append(
                analysis.record_candidate(
                    project_id=project_id,
                    task_id=task.id,
                    logical_key=key,
                    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                    action=AnalysisCandidateAction.CREATE,
                    provenance=AnalysisProvenance.SOURCE_OBSERVED,
                    confidence=0.95,
                    source_ref_ids=("s",),
                    payload={"name": name, "observation": "brave"},
                ).candidate
            )
        path = f"/projects/{project_id}/analysis/jobs/{job.id}/auto-promote"

        r1 = client.post(path)
        print("1st call:", r1.status_code, "promoted=",
              [m["source_candidate_id"] for m in r1.json().get("promoted", [])])
        print("  outbox enqueued so far:", outbox.enqueued)
        r2 = client.post(path)
        print("retry   :", r2.status_code, "promoted=",
              [m["source_candidate_id"] for m in r2.json().get("promoted", [])])
        print("  outbox enqueued AFTER retry:", outbox.enqueued)

        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        stored_ids = sorted(m["source_candidate_id"] for m in stored)
        print("STORED:", stored_ids)
        print("memory_ids ever enqueued for reindex:", sorted(outbox.enqueued))
        c2_missing = cands[1].id not in outbox.enqueued and any(
            m["source_candidate_id"] == cands[1].id for m in stored
        )
        print("c2 minted-but-never-enqueued-for-reindex?:", c2_missing)
        print("=> retry recovered the lost reindex?",
              "YES" if cands[1].id in outbox.enqueued
              else "NO — 503 'retry promotes only what is left' is misleading here")


if __name__ == "__main__":
    main()
