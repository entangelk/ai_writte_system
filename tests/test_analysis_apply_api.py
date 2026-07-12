import asyncio
import unittest

import httpx

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
from services.application.app.indexing.models import IndexSyncEvent
from services.application.app.indexing.service import (
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
)
from services.application.app.main import create_app
from services.application.app.memory.models import MemoryStatus, PromotionMode
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION


class TestClient:
    __test__ = False

    def __init__(self, app):
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


def _seed_candidate(
    analysis, *, project_id, logical_key, payload,
    source_ref_ids=("source-ref-1",),
):
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
        source_ref_ids=source_ref_ids, payload=payload,
    ).candidate
    return job, candidate


def _build():
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = MemoryService(InMemoryMemoryRepository())
    sync_outbox = IndexSyncOutboxService(InMemoryIndexSyncRepository())
    app = create_app(
        service=core_sot, analysis_service=analysis, memory_service=memory,
        index_sync_outbox=sync_outbox,
        review_queue_service=ReviewQueueService(InMemoryReviewQueueRepository()),
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, memory, project_id


class AnalysisApplyApiTest(unittest.TestCase):
    def test_create_proposal_mints_canonical(self):
        client, analysis, memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "create"}]},
        )

        self.assertEqual(response.status_code, 200)
        applied = response.json()["applied"][0]
        self.assertEqual(applied["outcome"], "created")
        self.assertEqual(applied["version"], 1)
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 1)

    def test_update_proposal_versions_prior_and_supersedes(self):
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "now cautious"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": current.id,
                        "action": "update",
                        "matched_memory_id": prior_mem.id,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        applied = response.json()["applied"][0]
        self.assertEqual(applied["outcome"], "versioned")
        self.assertEqual(applied["version"], 2)
        self.assertEqual(applied["superseded_memory_id"], prior_mem.id)
        # prior preserved as superseded, new version canonical
        old = memory.get_memory(project_id=project_id, memory_id=prior_mem.id)
        self.assertEqual(old.status, MemoryStatus.SUPERSEDED)
        new = memory.get_memory(project_id=project_id, memory_id=applied["memory_id"])
        self.assertEqual(new.status, MemoryStatus.CANONICAL)
        self.assertEqual(new.supersedes, prior_mem.id)

    def test_reapply_is_idempotent(self):
        # D5: re-posting the same apply body replays, no duplicate version.
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "changed"},
        )
        body = {
            "proposals": [
                {
                    "candidate_id": current.id,
                    "action": "update",
                    "matched_memory_id": prior_mem.id,
                }
            ]
        }
        url = f"/projects/{project_id}/analysis/jobs/{job.id}/apply"

        first = client.post(url, json=body).json()["applied"][0]
        second = client.post(url, json=body).json()["applied"][0]

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["memory_id"], second["memory_id"])
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 2)

    def test_no_change_and_conflict_write_nothing(self):
        client, analysis, memory, project_id = _build()
        _pj, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_mem = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="cur",
            payload={"name": "Ariel", "observation": "same"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": current.id,
                        "action": "no_change",
                        "matched_memory_id": prior_mem.id,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["applied"][0]["outcome"], "no_change")
        # only the prior canonical entry remains
        self.assertEqual(len(memory.list_memories(project_id=project_id)), 1)

    def test_unknown_action_returns_400(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "merge"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_candidate_not_in_job_returns_400(self):
        client, analysis, _memory, project_id = _build()
        job, _candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": "ghost", "action": "create"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_missing_matched_memory_returns_404(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {
                        "candidate_id": candidate.id,
                        "action": "update",
                        "matched_memory_id": "no-such-memory",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_update_without_matched_memory_returns_400(self):
        # O3: update with matched_memory_id omitted (None) → MissingMatchedMemory
        # → 400 at the HTTP boundary (distinct from a non-existent id → 404).
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "update"}]},
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_project_and_job_return_404(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        body = {"proposals": [{"candidate_id": candidate.id, "action": "create"}]}
        missing_project = client.post(
            f"/projects/missing/analysis/jobs/{job.id}/apply", json=body
        )
        self.assertEqual(missing_project.status_code, 404)
        missing_job = client.post(
            f"/projects/{project_id}/analysis/jobs/nope/apply", json=body
        )
        self.assertEqual(missing_job.status_code, 404)


class ApplyReindexEnqueueWiringTest(unittest.TestCase):
    """Phase 2B.5 (D3=B): the default create_app wires the memory service to the
    index-sync outbox, so an apply through the HTTP endpoint enqueues a
    MEMORY_UPSERTED reindex (end-to-end, not just the service unit)."""

    def test_apply_create_enqueues_memory_upserted(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        analysis = AnalysisService(InMemoryAnalysisRepository())
        sync_repo = InMemoryIndexSyncRepository()
        # No memory_service injected → create_app builds the default one wired to
        # this outbox.
        app = create_app(
            service=core_sot,
            analysis_service=analysis,
            index_sync_outbox=IndexSyncOutboxService(sync_repo),
        )
        client = TestClient(app)
        project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{"candidate_id": candidate.id, "action": "create"}]},
        )

        self.assertEqual(response.status_code, 200)
        memory_id = response.json()["applied"][0]["memory_id"]
        entries = tuple(sync_repo.outbox_entries.values())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event, IndexSyncEvent.MEMORY_UPSERTED)
        self.assertEqual(entries[0].source.mongo_id, memory_id)


class ReviewQueueApiTest(unittest.TestCase):
    """2B.4 follow-up: applying a conflict persists it to the review queue, and
    the GET list endpoint (D2) surfaces the open entry end-to-end."""

    def _apply_conflict(self, client, project_id, job, candidate):
        return client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={
                "proposals": [
                    {"candidate_id": candidate.id, "action": "conflict"}
                ]
            },
        )

    def test_conflict_apply_surfaces_in_review_queue(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )

        applied = self._apply_conflict(client, project_id, job, candidate)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(
            applied.json()["applied"][0]["outcome"], "skipped_review"
        )

        listed = client.get(f"/projects/{project_id}/analysis/review-queue")
        self.assertEqual(listed.status_code, 200)
        entries = listed.json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["candidate_id"], candidate.id)
        self.assertEqual(entries[0]["job_id"], job.id)
        self.assertEqual(entries[0]["action"], "conflict")
        self.assertEqual(entries[0]["status"], "open")

    def test_reapplying_conflict_does_not_duplicate(self):
        client, analysis, _memory, project_id = _build()
        job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="c1",
            payload={"name": "Ariel", "observation": "brave"},
        )
        self._apply_conflict(client, project_id, job, candidate)
        self._apply_conflict(client, project_id, job, candidate)
        listed = client.get(f"/projects/{project_id}/analysis/review-queue")
        self.assertEqual(len(listed.json()["entries"]), 1)

    def test_empty_queue_returns_empty_list(self):
        client, _analysis, _memory, project_id = _build()
        listed = client.get(f"/projects/{project_id}/analysis/review-queue")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["entries"], [])

    def test_missing_project_returns_404(self):
        client, _analysis, _memory, _project_id = _build()
        listed = client.get("/projects/missing/analysis/review-queue")
        self.assertEqual(listed.status_code, 404)


class CharacterReconciliationApiTest(unittest.TestCase):
    def _open_conflict(
        self, client, analysis, memory, project_id,
        current_source_ref_ids=("source-ref-1",),
    ):
        _prior_job, prior = _seed_candidate(
            analysis, project_id=project_id, logical_key="prior-reconcile",
            payload={"name": "Ariel", "observation": "brave"},
        )
        prior_memory = memory.promote_candidate(
            project_id=project_id, candidate=prior, mode=PromotionMode.MANUAL
        ).memory
        job, current = _seed_candidate(
            analysis, project_id=project_id, logical_key="current-reconcile",
            payload={"name": "Song", "observation": "brave"},
            source_ref_ids=current_source_ref_ids,
        )
        applied = client.post(
            f"/projects/{project_id}/analysis/jobs/{job.id}/apply",
            json={"proposals": [{
                "candidate_id": current.id,
                "action": "conflict",
                "matched_memory_id": prior_memory.id,
            }]},
        )
        self.assertEqual(applied.status_code, 200)
        entry = client.get(
            f"/projects/{project_id}/analysis/review-queue"
        ).json()["entries"][0]
        return entry, prior_memory, current

    def test_merge_response_envelope_and_same_action_replay(self):
        client, analysis, memory, project_id = _build()
        entry, prior, _current = self._open_conflict(
            client, analysis, memory, project_id
        )
        url = (
            f"/projects/{project_id}/analysis/review-queue/"
            f"{entry['id']}/reconcile"
        )

        first = client.post(url, json={"action": "merge"})
        replay = client.post(url, json={"action": "merge"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            set(first.json()),
            {"entry_id", "action", "memory_id", "superseded_memory_id",
             "idempotent_replay"},
        )
        self.assertEqual(first.json()["action"], "merge")
        self.assertEqual(first.json()["superseded_memory_id"], prior.id)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(replay.json()["memory_id"], first.json()["memory_id"])

    def test_different_and_invalid_actions_return_409(self):
        client, analysis, memory, project_id = _build()
        entry, _prior, _current = self._open_conflict(
            client, analysis, memory, project_id
        )
        url = (
            f"/projects/{project_id}/analysis/review-queue/"
            f"{entry['id']}/reconcile"
        )
        self.assertEqual(client.post(url, json={"action": "split"}).status_code, 200)
        self.assertEqual(client.post(url, json={"action": "merge"}).status_code, 409)

        client2, _analysis2, _memory2, project2 = _build()
        invalid = client2.post(
            f"/projects/{project2}/analysis/review-queue/anything/reconcile",
            json={"action": "invalid"},
        )
        self.assertEqual(invalid.status_code, 409)

    def test_missing_project_and_entry_return_404(self):
        client, _analysis, _memory, project_id = _build()
        body = {"action": "merge"}
        self.assertEqual(
            client.post(
                f"/projects/{project_id}/analysis/review-queue/missing/reconcile",
                json=body,
            ).status_code,
            404,
        )
        self.assertEqual(
            client.post(
                "/projects/missing/analysis/review-queue/missing/reconcile",
                json=body,
            ).status_code,
            404,
        )

    def test_merge_to_superseded_target_returns_409(self):
        client, analysis, memory, project_id = _build()
        entry, prior, _current = self._open_conflict(
            client, analysis, memory, project_id
        )
        _job, updater = _seed_candidate(
            analysis, project_id=project_id, logical_key="supersede-target",
            payload={"name": "Ariel", "observation": "changed"},
        )
        memory.record_updated_version(
            project_id=project_id, candidate=updater,
            target_memory_id=prior.id,
        )

        response = client.post(
            f"/projects/{project_id}/analysis/review-queue/{entry['id']}/reconcile",
            json={"action": "merge"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("non-canonical", response.json()["detail"])


class ReviewInboxApiTest(unittest.TestCase):
    def _open_conflict(
        self, client, analysis, memory, project_id,
        current_source_ref_ids=("source-ref-1",),
    ):
        return CharacterReconciliationApiTest._open_conflict(
            self, client, analysis, memory, project_id,
            current_source_ref_ids=current_source_ref_ids,
        )

    def test_list_unifies_candidate_with_open_conflict(self):
        client, analysis, memory, project_id = _build()
        entry, _prior, current = self._open_conflict(
            client, analysis, memory, project_id
        )

        response = client.get(f"/projects/{project_id}/analysis/review-inbox")

        self.assertEqual(response.status_code, 200)
        [item] = response.json()["items"]
        self.assertEqual(item["candidate_id"], current.id)
        self.assertEqual(item["status"], "needs_review")
        self.assertEqual(item["conflict_count"], 1)
        self.assertNotIn("payload", item)
        self.assertTrue(entry["id"])

    def test_detail_returns_payload_source_status_memory_and_field_diff(self):
        client, analysis, memory, project_id = _build()
        _entry, prior, current = self._open_conflict(
            client, analysis, memory, project_id
        )

        response = client.get(
            f"/projects/{project_id}/analysis/review-inbox/{current.id}"
        )

        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["payload"]["name"], "Song")
        self.assertEqual(
            detail["source_refs"],
            [{"source_ref_id": "source-ref-1", "status": "missing"}],
        )
        [conflict] = detail["conflicts"]
        self.assertEqual(conflict["matched_memory"]["id"], prior.id)
        self.assertEqual(
            conflict["diff"],
            [{"field": "name", "before": "Ariel", "after": "Song"}],
        )

    def test_detail_resolves_source_ref_pointer_from_core_sot(self):
        client, analysis, memory, project_id = _build()
        draft = client.post(
            f"/projects/{project_id}/drafts", json={"title": "Episode 1"}
        ).json()
        raw_text = "Ariel found the blue letter."
        saved = client.post(
            f"/projects/{project_id}/drafts/{draft['id']}/versions",
            json={"raw_text": raw_text, "idempotency_key": "review-source"},
        ).json()
        quote = "blue letter"
        start = raw_text.index(quote)
        source_ref = client.post(
            f"/projects/{project_id}/snapshots/{saved['snapshot']['id']}/source-refs",
            json={"start_offset": start, "end_offset": start + len(quote)},
        ).json()
        _entry, _prior, current = self._open_conflict(
            client, analysis, memory, project_id,
            current_source_ref_ids=(source_ref["id"],),
        )

        detail = client.get(
            f"/projects/{project_id}/analysis/review-inbox/{current.id}"
        ).json()

        self.assertEqual(detail["source_refs"], [{
            "source_ref_id": source_ref["id"],
            "status": "resolved",
            "snapshot_id": saved["snapshot"]["id"],
            "block_id": source_ref["block_id"],
            "start_offset": start,
            "end_offset": start + len(quote),
            "quote": quote,
            "content_hash": saved["snapshot"]["content_hash"],
        }])

    def test_directly_promoted_needs_review_candidate_is_suppressed(self):
        client, analysis, memory, project_id = _build()
        _job, candidate = _seed_candidate(
            analysis, project_id=project_id, logical_key="legacy-promoted",
            payload={"name": "Ariel", "observation": "brave"},
        )
        memory.promote_candidate(
            project_id=project_id, candidate=candidate, mode=PromotionMode.MANUAL
        )
        self.assertEqual(candidate.status.value, "needs_review")

        listed = client.get(f"/projects/{project_id}/analysis/review-inbox")
        detail = client.get(
            f"/projects/{project_id}/analysis/review-inbox/{candidate.id}"
        )

        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(detail.status_code, 404)

    def test_confirmed_candidate_leaves_inbox(self):
        client, analysis, memory, project_id = _build()
        entry, _prior, current = self._open_conflict(
            client, analysis, memory, project_id
        )
        reconciled = client.post(
            f"/projects/{project_id}/analysis/review-queue/{entry['id']}/reconcile",
            json={"action": "split"},
        )
        self.assertEqual(reconciled.status_code, 200)

        listed = client.get(f"/projects/{project_id}/analysis/review-inbox")
        detail = client.get(
            f"/projects/{project_id}/analysis/review-inbox/{current.id}"
        )
        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(detail.status_code, 404)

    def test_missing_project_and_cross_project_candidate_return_404(self):
        client, analysis, memory, project_id = _build()
        _entry, _prior, current = self._open_conflict(
            client, analysis, memory, project_id
        )
        other_project = client.post("/projects", json={"name": "Other"}).json()["id"]

        self.assertEqual(
            client.get("/projects/missing/analysis/review-inbox").status_code,
            404,
        )
        self.assertEqual(
            client.get(
                f"/projects/{other_project}/analysis/review-inbox/{current.id}"
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
