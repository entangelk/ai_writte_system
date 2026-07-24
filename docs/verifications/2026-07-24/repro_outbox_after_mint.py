"""Repro for verification 2026-07-24 / auto-promote-503-partial-envelope (B1).

Question: SoT v1.6.40/v1.7.35 claims the 503 partial envelope `promoted[]`
carries "what this call newly minted so far" and therefore the response does
not disagree with stored state. The shipped regression models a store failure
BEFORE the mint. What if the store write succeeds and the SEPARATE outbox
enqueue (service.py:194 -> _enqueue_reindex -> IndexSyncOutboxService, a Mongo
write) fails afterwards? The memory IS minted then.

Run:  python3 docs/verifications/2026-07-24/repro_outbox_after_mint.py
Expected: status 503, promoted=[c1], STORED=[c1,c2], agrees=False
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


class _FailingOutbox:
    """2nd enqueue fails — models a Mongo write that drops AFTER put_memory
    already succeeded for that candidate."""

    def __init__(self):
        self.calls = 0

    def enqueue_memory_upserted(self, *, project_id, memory_id, version):
        self.calls += 1
        if self.calls == 2:
            raise AutoReconnect("outbox write lost mid-call")


def main():
    analysis = AnalysisService(InMemoryAnalysisRepository())
    outbox = _FailingOutbox()
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
            project_id=project_id, snapshot_id="snapshot-1", idempotency_key="run-multi"
        ).job
        task = analysis.create_task(
            project_id=project_id,
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        cands = []
        for key, name in (("k1", "Ariel"), ("k2", "Boram")):
            cands.append(
                analysis.record_candidate(
                    project_id=project_id,
                    task_id=task.id,
                    logical_key=key,
                    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
                    action=AnalysisCandidateAction.CREATE,
                    provenance=AnalysisProvenance.SOURCE_OBSERVED,
                    confidence=0.95,
                    source_ref_ids=("source-ref-1",),
                    payload={"name": name, "observation": "brave"},
                ).candidate
            )
        resp = client.post(f"/projects/{project_id}/analysis/jobs/{job.id}/auto-promote")
        print("status:", resp.status_code)
        body = resp.json()
        print("promoted source_candidate_ids:",
              [m["source_candidate_id"] for m in body.get("promoted", [])])
        print("promotion_error:", body.get("promotion_error", "<none>"))
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        stored_ids = sorted(m["source_candidate_id"] for m in stored)
        print("STORED source_candidate_ids:", stored_ids)
        promoted_ids = sorted(m["source_candidate_id"] for m in body.get("promoted", []))
        agrees = promoted_ids == stored_ids
        print("response.promoted == stored state?:", agrees)
        print("=> SoT claim HOLDS" if agrees
              else "=> SoT claim VIOLATED: a minted memory is stored but absent from promoted[]")


if __name__ == "__main__":
    main()
