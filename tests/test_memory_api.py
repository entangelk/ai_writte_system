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
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.service import (
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
)
from services.application.app.main import create_app
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryNotFound,
    MemoryService,
)
from tests.auth_support import authenticate

try:  # pymongo is optional for the in-memory path (main._resolve_storage_error_types)
    from pymongo.errors import AutoReconnect as _STORAGE_FAILURE
except ModuleNotFoundError:  # pragma: no cover - the driver is present in CI
    _STORAGE_FAILURE = None


class TestClient:
    def __init__(self, app):
        # D8-3a: this suite is about domain behaviour, not the session
        # boundary, so the client arrives authenticated. The boundary itself
        # is driven un-overridden in tests/test_auth_api.py.
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


def _seed_candidate(
    analysis: AnalysisService,
    *,
    project_id: str,
    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
    logical_key="lk-1",
    confidence=0.5,
    payload=None,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave under pressure"}
    job = analysis.create_job(
        project_id=project_id,
        snapshot_id="snapshot-1",
        idempotency_key=f"run-{logical_key}",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=candidate_type
    )
    return analysis.record_candidate(
        project_id=project_id,
        task_id=task.id,
        logical_key=logical_key,
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=confidence,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    ).candidate


def _build(*, auto_promotion_threshold=None, memory_repository=None, memory=None):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    memory = memory or MemoryService(
        memory_repository or InMemoryMemoryRepository(),
        auto_promotion_threshold=auto_promotion_threshold,
    )
    app = create_app(
        service=core_sot,
        analysis_service=analysis,
        memory_service=memory,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, project_id


class ManualPromotionApiTest(unittest.TestCase):
    def test_promote_candidate_creates_and_reads_canonical_memory(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id, confidence=0.42)

        response = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        memory = body["memory"]
        self.assertEqual(memory["status"], "canonical")
        self.assertEqual(memory["version"], 1)
        self.assertEqual(memory["promotion_mode"], "manual")
        self.assertIsNone(memory["applied_threshold"])
        self.assertEqual(memory["source_candidate_id"], candidate.id)
        self.assertEqual(memory["memory_type"], "character_observation")
        self.assertEqual(memory["confidence"], 0.42)

        fetched = client.get(f"/projects/{project_id}/memory/{memory['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], memory["id"])

        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual([m["id"] for m in listed], [memory["id"]])

    def test_promote_candidate_is_idempotent(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)

        first = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        ).json()
        replay = client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
        ).json()

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["memory"]["id"], first["memory"]["id"])
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(listed), 1)

    def test_promote_missing_candidate_returns_404(self):
        client, _analysis, project_id = _build()
        response = client.post(
            f"/projects/{project_id}/analysis/candidates/nope/promote"
        )
        self.assertEqual(response.status_code, 404)

    def test_promote_on_missing_project_returns_404(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        response = client.post(
            f"/projects/missing/analysis/candidates/{candidate.id}/promote"
        )
        self.assertEqual(response.status_code, 404)


class AutoPromotionApiTest(unittest.TestCase):
    def test_auto_promote_off_by_default_promotes_nothing(self):
        client, analysis, project_id = _build(auto_promotion_threshold=None)
        candidate = _seed_candidate(analysis, project_id=project_id, confidence=1.0)
        job_id = candidate.job_id

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["auto_promotion_threshold"])
        self.assertEqual(body["promoted"], [])
        self.assertEqual(
            client.get(f"/projects/{project_id}/memory").json()["memory"], []
        )

    def test_auto_promote_fires_only_at_or_above_threshold(self):
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        high = _seed_candidate(
            analysis, project_id=project_id, logical_key="high", confidence=0.95
        )

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{high.job_id}/auto-promote"
        )

        body = response.json()
        self.assertEqual(body["auto_promotion_threshold"], 0.9)
        self.assertEqual(len(body["promoted"]), 1)
        promoted = body["promoted"][0]
        self.assertEqual(promoted["promotion_mode"], "auto_threshold")
        self.assertEqual(promoted["applied_threshold"], 0.9)
        self.assertEqual(promoted["source_candidate_id"], high.id)

    def test_auto_promote_recall_reports_only_newly_promoted(self):
        # promoted[] means "newly promoted this call": a second run of the gate
        # over the same job replays idempotently (stored memory stays 1) and
        # must not re-report the already-promoted candidate.
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        high = _seed_candidate(
            analysis, project_id=project_id, logical_key="high", confidence=0.95
        )
        path = f"/projects/{project_id}/analysis/jobs/{high.job_id}/auto-promote"

        first = client.post(path).json()
        second = client.post(path).json()

        self.assertEqual(len(first["promoted"]), 1)
        self.assertEqual(second["promoted"], [])
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(stored), 1)

    def test_auto_promote_leaves_below_threshold_candidate_for_manual(self):
        client, analysis, project_id = _build(auto_promotion_threshold=0.9)
        low = _seed_candidate(
            analysis, project_id=project_id, logical_key="low", confidence=0.5
        )

        auto = client.post(
            f"/projects/{project_id}/analysis/jobs/{low.job_id}/auto-promote"
        ).json()
        self.assertEqual(auto["promoted"], [])

        manual = client.post(
            f"/projects/{project_id}/analysis/candidates/{low.id}/promote"
        )
        self.assertEqual(manual.status_code, 200)
        self.assertEqual(manual.json()["memory"]["promotion_mode"], "manual")

    def test_get_missing_memory_returns_404(self):
        client, _analysis, project_id = _build()
        self.assertEqual(
            client.get(f"/projects/{project_id}/memory/nope").status_code, 404
        )


class AutoPromoteStorageFailureTest(unittest.TestCase):
    """A failing canonical store makes auto-promote a 503 partial, not a 500.

    SoT v1.7.35 (brief ``plans/auto-promote-partial-failure-decisions.md``,
    owner decisions D1=B / D2=A / D3=404). The promotion loop sat outside every
    ``try``, so a store failure at candidate N escaped as an opaque 500 *after*
    N-1 canonical mints had already been written.

    Two contract points are locked here, and they are separate claims:

    * **503, not 502 or 500** (D2=A). The canonical store is not an upstream
      collaborator, so 502 would conflate "the AI/search is misbehaving" with
      "the database is down" — operationally different responses. A contracted
      500 was rejected because H3 spent the whole phase defining 500 as an
      undeclared leak.
    * **The partial envelope keeps the mints** (D1=B). Promotion is append-only
      and is never rolled back, so a bare error body would make the response
      disagree with what is stored. ``promoted`` keeps the same meaning it has on
      the success path: what *this call* newly minted.

    Both directions. Under-strict: dropping the ``except _STORAGE_ERRORS``
    clause brings the 500 back. Over-strict: a healthy run must stay 200, and —
    the guard that matters most — widening the clause to bare ``Exception`` must
    fail, because that would relabel ordinary programming errors as "the store
    is down" and send an operator to check a healthy database.
    """

    THRESHOLD = 0.9

    def _two_candidates_in_one_job(self, analysis, project_id):
        # The loop must promote one candidate before failing on the next, so
        # both have to live in the *same* job (_seed_candidate makes a new job
        # per call) and both have to clear the auto-promotion threshold.
        job = analysis.create_job(
            project_id=project_id,
            snapshot_id="snapshot-1",
            idempotency_key="run-multi",
        ).job
        task = analysis.create_task(
            project_id=project_id,
            job_id=job.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
        )
        candidates = []
        for key, name in (("k1", "Ariel"), ("k2", "Boram")):
            candidates.append(
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
        return job.id, candidates

    def _client_failing_on_the_second_put(self, error):
        # A transient outage: the second write of the run fails, later writes
        # succeed. Modelling recovery (rather than failing forever) is what lets
        # the retry test assert the documented recovery path instead of just
        # re-observing the outage.
        class _FailingStore(InMemoryMemoryRepository):
            def __init__(self):
                super().__init__()
                self.puts = 0

            def put_memory(self, entry):
                self.puts += 1
                if self.puts == 2:
                    raise error
                super().put_memory(entry)

        return _build(
            auto_promotion_threshold=self.THRESHOLD,
            memory_repository=_FailingStore(),
        )

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_store_failure_mid_loop_is_a_503_partial_that_keeps_the_mints(self):
        client, analysis, project_id = self._client_failing_on_the_second_put(
            _STORAGE_FAILURE("connection to the canonical store was lost")
        )
        job_id, candidates = self._two_candidates_in_one_job(analysis, project_id)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 503)
        body = response.json()
        # Exact keys: the envelope is returned via JSONResponse, which bypasses
        # response_model validation, so this assertion is its only runtime lock.
        self.assertEqual(
            set(body), {"auto_promotion_threshold", "promoted", "promotion_error"}
        )
        self.assertEqual(body["auto_promotion_threshold"], self.THRESHOLD)
        self.assertEqual(len(body["promoted"]), 1)
        self.assertEqual(body["promoted"][0]["source_candidate_id"], candidates[0].id)
        self.assertTrue(body["promotion_error"])
        # The reported mint is durable, not a claim the failure rolled back. This
        # is the whole reason D1=B exists: response and stored state must agree.
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(
            [m["source_candidate_id"] for m in stored], [candidates[0].id]
        )

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_retrying_after_recovery_promotes_only_what_is_left(self):
        # The recovery path the 503 description promises. Promotion idempotency
        # ((project_id, source_candidate_id) unique) means the retry must not
        # re-report or re-mint the candidate that already succeeded.
        client, analysis, project_id = self._client_failing_on_the_second_put(
            _STORAGE_FAILURE("connection to the canonical store was lost")
        )
        job_id, candidates = self._two_candidates_in_one_job(analysis, project_id)
        path = f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"

        self.assertEqual(client.post(path).status_code, 503)
        recovered = client.post(path)

        self.assertEqual(recovered.status_code, 200)
        promoted = recovered.json()["promoted"]
        self.assertEqual([m["source_candidate_id"] for m in promoted],
                         [candidates[1].id])
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(
            sorted(m["source_candidate_id"] for m in stored),
            sorted(c.id for c in candidates),
        )

    def test_healthy_auto_promote_still_returns_200(self):
        # Over-strict guard: the new clauses must not turn working runs into
        # errors, and the success envelope must keep its own key set.
        client, analysis, project_id = _build(
            auto_promotion_threshold=self.THRESHOLD
        )
        job_id, candidates = self._two_candidates_in_one_job(analysis, project_id)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()),
                         {"auto_promotion_threshold", "promoted"})
        self.assertEqual(len(response.json()["promoted"]), 2)

    def test_unrelated_failure_is_not_relabelled_as_a_store_outage(self):
        # Over-strict guard on the clause's *width*, and the reason the catch is
        # a named type instead of ``Exception``: a bare catch would pass every
        # other test in this class while reporting programming errors as 503
        # "recover the store and retry" — pointing an operator at a healthy DB
        # and hiding the bug. Only the storage types are a 503.
        client, analysis, project_id = self._client_failing_on_the_second_put(
            RuntimeError("not a storage transport failure")
        )
        job_id, _candidates = self._two_candidates_in_one_job(analysis, project_id)

        with self.assertRaises(RuntimeError):
            client.post(
                f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
            )

    def _client_with_outbox_failing_on_the_second_enqueue(self, error):
        # The *other* failure mode, and the one the shipped v1.7.35 regressions
        # missed: a promotion is two writes (put_memory, then the reindex outbox)
        # and only the second fails. The default test harness injects no outbox
        # at all, which is exactly why this mode stayed invisible.
        #
        # The real IndexSyncOutboxService is used rather than a stub so the
        # replay re-enqueue (v1.7.37) runs against real dedup: while an entry is
        # PENDING a second enqueue for the same memory must collapse onto it.
        # A stub that just appended would hide that and report false duplicates.
        # The injected failure is transient — one enqueue fails, later ones work
        # — because a permanent one cannot model the recovery being asserted.
        class _FailingOnceOutbox(IndexSyncOutboxService):
            def __init__(self, repo):
                super().__init__(repo)
                self.calls = 0
                self.failed = False

            def enqueue_memory_upserted(self, **kwargs):
                self.calls += 1
                if not self.failed and self.calls == 2:
                    self.failed = True
                    raise error
                return super().enqueue_memory_upserted(**kwargs)

        repo = InMemoryIndexSyncRepository()
        service = MemoryService(
            InMemoryMemoryRepository(),
            auto_promotion_threshold=self.THRESHOLD,
            reindex_outbox=_FailingOnceOutbox(repo),
        )
        client, analysis, project_id = _build(memory=service)
        return client, analysis, project_id, repo

    @staticmethod
    def _reindexed_memory_ids(repo):
        return sorted(
            entry.source.mongo_id for entry in repo.outbox_entries.values()
        )

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_enqueue_failure_after_the_mint_still_reports_that_mint(self):
        # The envelope's whole promise is that it agrees with the stored state.
        # Here the candidate IS durably minted and only its reindex enqueue
        # failed, so leaving it out of ``promoted`` would understate the mints by
        # one and make the SoT claim false — which is what v1.7.35 shipped and an
        # independent verification reproduced (F3).
        client, analysis, project_id, _repo = (
            self._client_with_outbox_failing_on_the_second_enqueue(
                _STORAGE_FAILURE("outbox write lost mid-call")
            )
        )
        job_id, candidates = self._two_candidates_in_one_job(analysis, project_id)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 503)
        body = response.json()
        reported = [m["source_candidate_id"] for m in body["promoted"]]
        stored = [
            m["source_candidate_id"]
            for m in client.get(f"/projects/{project_id}/memory").json()["memory"]
        ]
        self.assertEqual(reported, [c.id for c in candidates])
        self.assertEqual(reported, stored)

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_promotion_error_names_the_stage_that_failed(self):
        # Brief Follow-up #2. The two modes leave *different* states behind — one
        # minted nothing for the failing candidate, the other minted it and lost
        # only the reindex — and an operator reading the 503 body cannot tell
        # which without being told. A bare str(exc) (v1.7.35) says neither.
        failure = _STORAGE_FAILURE("connection lost")

        client, analysis, project_id = self._client_failing_on_the_second_put(failure)
        job_id, _ = self._two_candidates_in_one_job(analysis, project_id)
        before_mint = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        ).json()["promotion_error"]

        client, analysis, project_id, _repo = (
            self._client_with_outbox_failing_on_the_second_enqueue(failure)
        )
        job_id, _ = self._two_candidates_in_one_job(analysis, project_id)
        after_mint = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        ).json()["promotion_error"]

        self.assertIn("was not minted by this call", before_mint)
        self.assertIn("was minted", after_mint)
        self.assertIn("reindex enqueue failed", after_mint)
        self.assertNotEqual(before_mint, after_mint)

    @unittest.skipIf(_STORAGE_FAILURE is None, "pymongo is not installed")
    def test_retry_recovers_a_reindex_enqueue_lost_after_a_mint(self):
        """Retry recovers the lost reindex — SoT v1.7.37, owner decision.

        Until v1.7.36 this was the documented residue: a reindex enqueue lost
        *after* its mint was never retried, because ``promote_candidate``
        short-circuited an already-promoted candidate as an idempotent replay
        before reaching ``_enqueue_reindex`` (v1.6.46 exempted replays). The
        memory stayed canonical-but-unindexed until a backfill ran.

        The owner took the fork: the replay now re-enqueues, so the choke point
        is unconditional and the retry that the 503 body already told the
        operator to run is what repairs the index too.

        Under-strict: reverting the replay branch leaves the enqueue lost and
        fails here. Over-strict: the retry must still not re-*promote* — the
        recovered candidate is a replay, so ``promoted`` stays empty and no
        second memory is minted.
        """
        client, analysis, project_id, repo = (
            self._client_with_outbox_failing_on_the_second_enqueue(
                _STORAGE_FAILURE("outbox write lost mid-call")
            )
        )
        job_id, candidates = self._two_candidates_in_one_job(analysis, project_id)
        path = f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"

        first = client.post(path)
        retry = client.post(path)

        self.assertEqual(first.status_code, 503)
        # Both candidates are minted, so the retry finds nothing left to promote
        # (over-strict: recovery must not mint a second memory or re-report one).
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["promoted"], [])
        stored = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(stored), len(candidates))
        # ...and the enqueue lost for the second mint is now recovered: every
        # stored memory has had a reindex requested.
        self.assertEqual(
            self._reindexed_memory_ids(repo), sorted(m["id"] for m in stored)
        )

    def test_memory_not_found_mid_loop_is_404(self):
        # D3. Unreachable through the HTTP surface today (the candidates come
        # from list_candidates(project_id=...), so promote_candidate's project
        # mismatch cannot fire), but the branch existed with no mapping, which is
        # exactly the 500 leak this slice closes. Injected at the service seam
        # because no request can produce it.
        class _MissingMemoryService(MemoryService):
            def auto_promote_candidate(self, *, project_id, candidate):
                raise MemoryNotFound("analysis candidate not found")

        service = _MissingMemoryService(
            InMemoryMemoryRepository(),
            auto_promotion_threshold=self.THRESHOLD,
        )
        client, analysis, project_id = _build(memory=service)
        job_id, _candidates = self._two_candidates_in_one_job(analysis, project_id)

        response = client.post(
            f"/projects/{project_id}/analysis/jobs/{job_id}/auto-promote"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.json()), {"detail"})


class CandidateReviewApiTest(unittest.TestCase):
    """Phase 6 (v1.6.61): confirm/reject candidate HTTP endpoints."""

    def _confirm(self, client, project_id, candidate_id):
        return client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate_id}/confirm"
        )

    def _reject(self, client, project_id, candidate_id):
        return client.post(
            f"/projects/{project_id}/analysis/candidates/{candidate_id}/reject"
        )

    def test_confirm_transitions_and_promotes(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        response = self._confirm(client, project_id, candidate.id)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "confirmed")
        self.assertIsNotNone(body["memory_id"])
        self.assertFalse(body["idempotent_replay"])
        # promoted to a canonical memory
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual([m["id"] for m in listed], [body["memory_id"]])

    def test_confirm_is_idempotent(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        first = self._confirm(client, project_id, candidate.id).json()
        replay = self._confirm(client, project_id, candidate.id).json()
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["memory_id"], first["memory_id"])
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(listed), 1)

    def test_reject_transitions_without_promotion(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        response = self._reject(client, project_id, candidate.id)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "rejected")
        self.assertIsNone(body["memory_id"])
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(listed, [])

    def test_confirm_after_reject_conflicts_409(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        self._reject(client, project_id, candidate.id)
        response = self._confirm(client, project_id, candidate.id)
        self.assertEqual(response.status_code, 409)

    def test_confirm_missing_candidate_returns_404(self):
        client, _analysis, project_id = _build()
        self.assertEqual(
            self._confirm(client, project_id, "nope").status_code, 404
        )

    def test_confirm_missing_project_returns_404(self):
        client, analysis, project_id = _build()
        candidate = _seed_candidate(analysis, project_id=project_id)
        self.assertEqual(
            self._confirm(client, "missing", candidate.id).status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
