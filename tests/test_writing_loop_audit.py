"""Phase 5.9 L9 B — persisted Writing bounded-loop audit regressions.

Locks the owner-approved bundle P1=B (bodyless per-stage trail), P2=A
(every termination audited), P3=A (append-only, retry = new id), P4=A
(list + detail read API), P5=A (immutable, never mutated/auto-deleted).
Both directions: audit must appear for loop terminations and must NOT
appear for pre-loop request rejections.
"""

import unittest
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from services.application.app.context_search.models import (
    ContextItem,
    ContextItemStatus,
    ContextNeed,
    ContextPackage,
    ContextSearchPurpose,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.indexing.models import IndexPointer
from services.application.app.writing.audit_hash import (
    finding_fingerprint,
    hash_text,
)
from services.application.app.writing.loop_audit import (
    InMemoryWritingLoopAuditRepository,
    StoredLoopStage,
    WritingLoopAuditNotFound,
    WritingLoopAuditService,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingGateDecision,
    WritingGateFinding,
    WritingGateFindingType,
    WritingGateResult,
    WritingGateSeverity,
    WritingOutputType,
    WritingTaskType,
)
from services.application.app.writing.revise_gate import (
    WritingLoopStage,
    WritingLoopStageName,
    WritingLoopStageStatus,
    WritingLoopStatus,
    WritingLoopSummary,
)

from tests.test_writing_revise import (
    _Gate,
    _LoopGate,
    _NoWriteCoreSotService,
    _Provider,
    _Reporter,
    _SequenceProvider,
    _body,
    _finding,
    _http,
    _package,
)


_UNSET = object()


def _candidate(text="final text", project_id="p1"):
    return WritingCandidate(
        "r1", project_id, WritingTaskType.CONTINUE_SCENE,
        WritingOutputType.DRAFT_PATCH, text,
    )


def _gate_result(project_id="p1"):
    return WritingGateResult(
        "r1", project_id, WritingGateDecision.PASS,
        (_finding(),), (), "fake-gate",
    )


def _summary(status=WritingLoopStatus.PASS):
    return WritingLoopSummary(status, 2, 0, 2)


def _stages():
    return (
        WritingLoopStage(
            WritingLoopStageName.REVISE, 1, WritingLoopStageStatus.COMPLETED,
            candidate_hash="h-revise", finding_fingerprint="fp-1",
        ),
        WritingLoopStage(
            WritingLoopStageName.GATE, 2, WritingLoopStageStatus.COMPLETED,
            candidate_hash="h-final", pointer_ids=("d1", "s1"),
        ),
    )


class WritingLoopAuditServiceTest(unittest.TestCase):
    def _service(self, *, ids=None):
        repo = InMemoryWritingLoopAuditRepository()
        counter = {"n": 0}
        base = datetime(2026, 7, 13, tzinfo=UTC)

        def next_id():
            counter["n"] += 1
            return (ids or [])[counter["n"] - 1] if ids else f"wla:{counter['n']}"

        def clock():
            return base + timedelta(minutes=counter["n"])

        return WritingLoopAuditService(repo, clock=clock, id_factory=next_id), repo

    def _record(self, service, *, project_id="p1", trigger=None,
                initial="initial text", final=None, gate=_UNSET,
                error_type=None):
        return service.record(
            project_id=project_id, request_id="r1",
            trigger_finding=trigger or _finding(),
            initial_candidate_text=initial,
            summary=_summary(), stages=_stages(),
            final_candidate=final or _candidate(project_id=project_id),
            gate=_gate_result(project_id) if gate is _UNSET else gate,
            error_type=error_type,
        )

    def test_retry_appends_a_new_run_and_never_mutates(self):
        """P3=A/P5=A: same request recorded twice → two distinct, immutable runs."""
        service, repo = self._service(ids=["wla:a", "wla:b"])
        first = self._record(service)
        second = self._record(service)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(repo.entries), 2)
        # Immutable: the stored first run is unchanged after the second write.
        self.assertEqual(service.get(project_id="p1", run_id="wla:a").id, first.id)
        # Frozen dataclass: no in-place mutation is possible.
        with self.assertRaises(Exception):
            first.loop_status = "changed"  # type: ignore[misc]

    def test_record_captures_bodyless_trail_and_final_text(self):
        """P1=B: hashes/fingerprints/pointers per stage; final text is the one body."""
        service, _ = self._service()
        run = self._record(service, initial="initial text",
                           final=_candidate("final text"))
        self.assertEqual(run.initial_candidate_hash, hash_text("initial text"))
        self.assertEqual(run.final_candidate_hash, hash_text("final text"))
        self.assertEqual(run.final_candidate_text, "final text")
        self.assertEqual(run.trigger_finding_fingerprint,
                         finding_fingerprint(_finding()))
        self.assertEqual(run.final_gate_decision, "pass")
        self.assertEqual(run.final_gate_finding_fingerprints,
                         (finding_fingerprint(_finding()),))
        self.assertEqual(
            [(s.stage, s.status, s.candidate_hash, s.finding_fingerprint,
              s.pointer_ids) for s in run.stages],
            [("revise", "completed", "h-revise", "fp-1", ()),
             ("gate", "completed", "h-final", None, ("d1", "s1"))],
        )
        self.assertIsInstance(run.stages[0], StoredLoopStage)

    def test_failed_run_stores_error_type_and_null_gate(self):
        service, _ = self._service()
        run = self._record(service, gate=None, error_type="gate_error")
        self.assertEqual(run.error_type, "gate_error")
        self.assertIsNone(run.final_gate_decision)
        self.assertEqual(run.final_gate_finding_fingerprints, ())

    def test_list_is_project_scoped_and_newest_first(self):
        service, _ = self._service(ids=["wla:1", "wla:2", "wla:3"])
        self._record(service, project_id="p1")
        self._record(service, project_id="p2")
        self._record(service, project_id="p1")
        ids = [run.id for run in service.list_runs("p1")]
        self.assertEqual(ids, ["wla:3", "wla:1"])  # desc by created_at
        self.assertEqual([r.id for r in service.list_runs("p2")], ["wla:2"])

    def test_get_rejects_cross_project_and_missing(self):
        service, _ = self._service(ids=["wla:1"])
        self._record(service, project_id="p1")
        with self.assertRaises(WritingLoopAuditNotFound):
            service.get(project_id="p2", run_id="wla:1")
        with self.assertRaises(WritingLoopAuditNotFound):
            service.get(project_id="p1", run_id="ghost")


class _PointerContext:
    """Second build call returns a delta package carrying pointer ids."""

    def __init__(self):
        self.calls = 0
        self.last_package = None

    async def build_context_package(self, request):
        self.calls += 1
        if self.calls == 1:
            self.last_package = _package(request.project_id)
            return self.last_package
        item = ContextItem(
            ContextNeed.EVENT_CONTEXT, ContextItemStatus.CANONICAL, "근거",
            IndexPointer(request.project_id, "col", "d1", "v1", "ch"),
            "s1", False, 5, source_ref_ids=("sr1",),
        )
        return ContextPackage(
            request.project_id, ContextSearchPurpose.WRITING_CONTEXT,
            (item,), (), (), (), 5, False,
        )


class WritingLoopAuditApiTest(unittest.TestCase):
    def _post(self, client, project, body=None, *, persist=True):
        # P2=B opt-in: audit persists only when the request flag is set.
        # Default persist=True keeps the audited-path tests explicit; pass
        # persist=None to exercise the default-off behaviour, False for
        # explicit opt-out.
        payload = dict(body or _body())
        if persist is not None:
            payload["persist_audit"] = persist
        return client.post(
            f"/projects/{project}/writing/revise-and-gate", payload
        )

    def _audit_service(self):
        counter = {"n": 0}

        def next_id():
            counter["n"] += 1
            return f"wla:{counter['n']}"

        return WritingLoopAuditService(
            InMemoryWritingLoopAuditRepository(), id_factory=next_id
        )

    def test_success_loop_persists_full_trail_and_returns_audit_id(self):
        provider = _SequenceProvider(("고친 문장.", "다시 고친 문장."))
        gate = _LoopGate((WritingGateDecision.REVISE, WritingGateDecision.PASS))
        client, project, _ = _http(
            provider, gate_service=gate, report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        response = self._post(client, project)
        self.assertEqual(response.status_code, 200)
        audit_id = response.json()["audit_id"]
        self.assertTrue(audit_id)
        # B2 forward-defense (SoT v1.6.79): persist-success leaves audit_error
        # null — the failure-only signal must not bleed into a clean run.
        self.assertIsNone(response.json()["audit_error"])

        got = _get(client, f"/projects/{project}/writing/loop-audits/{audit_id}")
        self.assertEqual(got.status_code, 200)
        payload = got.json()
        self.assertEqual(payload["loop_status"], "pass")
        self.assertIsNone(payload["error_type"])
        self.assertEqual(payload["final_candidate_text"],
                         "앞 문장. 다시 고친 문장. 뒤 문장.")
        # P1=B: final hash equals the last recorded stage's candidate hash.
        self.assertEqual(payload["final_candidate_hash"],
                         payload["stages"][-1]["candidate_hash"])
        self.assertEqual(
            [(s["stage"], s["status"]) for s in payload["stages"]],
            [("revise", "completed"), ("report", "completed"),
             ("gate", "completed"), ("revise", "completed"),
             ("report", "completed"), ("gate", "completed")],
        )
        # revise stages carry the trigger finding fingerprint; others do not.
        self.assertTrue(payload["stages"][0]["finding_fingerprint"])
        self.assertIsNone(payload["stages"][2]["finding_fingerprint"])
        # B1 forward-defense: the detail surface is bodyless beyond the final
        # candidate text. Phase 5.10 ("B2") added run-level `total_tokens`/
        # `wall_clock_ms` (M5=A). Stage rows stay bodyless — per-stage usage is
        # still deferred (M5=C); any future stage-level usage must break this set.
        self.assertEqual(set(payload), {
            "audit_id", "request_id", "loop_status", "error_type",
            "revision_rounds", "retrieval_rounds", "gate_evaluations",
            "total_tokens", "wall_clock_ms",
            "created_at", "trigger_finding_fingerprint", "initial_candidate_hash",
            "final_candidate_hash", "final_candidate_text", "final_gate_decision",
            "final_gate_finding_fingerprints", "stages",
        })
        self.assertTrue(all(set(stage) == {
            "stage", "ordinal", "status", "candidate_hash",
            "finding_fingerprint", "pointer_ids",
        } for stage in payload["stages"]))

    def test_opt_in_default_off_persists_nothing(self):
        """P2=B: no flag + no env default → loop runs, audit is not persisted."""
        for persist in (None, False):
            with self.subTest(persist=persist):
                client, project, _ = _http(
                    _Provider(), gate_service=_Gate(),
                    report_service=_Reporter(),
                    loop_audit_service=self._audit_service(),
                )
                response = self._post(client, project, persist=persist)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["audit_id"])
                self.assertIsNone(response.json()["audit_error"])
                self.assertEqual(
                    _get(client, f"/projects/{project}/writing/loop-audits")
                    .json()["items"], [])

    def test_env_default_enables_audit_without_request_flag(self):
        """WRITING_LOOP_AUDIT_DEFAULT toggles the default; request flag overrides."""
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        with patch.dict(os.environ, {"WRITING_LOOP_AUDIT_DEFAULT": "true"}):
            enabled = self._post(client, project, persist=None)
            self.assertTrue(enabled.json()["audit_id"])
            # explicit False overrides the env default back off.
            disabled = self._post(client, project, persist=False)
            self.assertIsNone(disabled.json()["audit_id"])
        # Only the env-enabled run was persisted; the overridden one was not.
        self.assertEqual(
            [i["audit_id"] for i in
             _get(client, f"/projects/{project}/writing/loop-audits")
             .json()["items"]],
            [enabled.json()["audit_id"]],
        )

    def test_persist_failure_is_isolated_from_the_loop_result(self):
        """Folded H3: an audit-write failure returns the loop result with
        audit_id=null + audit_error, never breaking the loop outcome."""
        class _RaisingRepo:
            def add(self, run):
                raise RuntimeError("mongo down")

            def get(self, run_id):
                return None

            def list_for_project(self, project_id):
                return ()

        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            loop_audit_service=WritingLoopAuditService(_RaisingRepo()),
        )
        response = self._post(client, project)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["gate"]["decision"], "pass")  # loop result intact
        self.assertIsNone(body["audit_id"])
        self.assertEqual(body["audit_error"]["type"], "audit_persist_error")
        self.assertIn("mongo down", body["audit_error"]["detail"])

    def test_every_termination_is_audited_including_failure(self):
        gate = _Gate(error=RuntimeError("gate boom"))
        client, project, _ = _http(
            _Provider(), gate_service=gate, report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        response = self._post(client, project)
        self.assertEqual(response.status_code, 502)
        audit_id = response.json()["audit_id"]
        payload = _get(
            client, f"/projects/{project}/writing/loop-audits/{audit_id}"
        ).json()
        self.assertEqual(payload["loop_status"], "failed")
        self.assertEqual(payload["error_type"], "gate_error")
        self.assertIsNone(payload["final_gate_decision"])
        self.assertEqual(payload["stages"][-1]["status"], "failed")

    def test_each_non_pass_200_status_leaves_a_record_with_that_status(self):
        """H2 closure: the uniform success site audits every 200 loop_status,
        not just pass — pin terminal_decision/not_eligible/budget_exhausted/
        no_change against a future conditional-skip regression."""
        cases = (
            (_LoopGate((WritingGateDecision.NEEDS_USER_REVIEW,)),
             _Provider(), "terminal_decision"),
            (_Gate(WritingGateDecision.REVISE), _Provider(), "not_eligible"),
            (_LoopGate((WritingGateDecision.REVISE, WritingGateDecision.REVISE)),
             _SequenceProvider(("고친 문장.", "다시 고친 문장.")),
             "budget_exhausted"),
            (_LoopGate((WritingGateDecision.REVISE,)),
             _SequenceProvider(("고친 문장.", "고친 문장.")), "no_change"),
        )
        for gate, provider, expected in cases:
            with self.subTest(expected=expected):
                client, project, _ = _http(
                    provider, gate_service=gate, report_service=_Reporter(),
                    loop_audit_service=self._audit_service(),
                )
                response = self._post(client, project)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["loop"]["status"], expected)
                audit_id = response.json()["audit_id"]
                payload = _get(
                    client, f"/projects/{project}/writing/loop-audits/{audit_id}"
                ).json()
                self.assertEqual(payload["loop_status"], expected)
                self.assertIsNone(payload["error_type"])

    def test_retry_appends_distinct_runs_summary_is_bodyless_newest_first(self):
        gate = _LoopGate((WritingGateDecision.PASS, WritingGateDecision.PASS))
        client, project, _ = _http(
            _SequenceProvider(("고친 문장.", "고친 문장.")),
            gate_service=gate, report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        first = self._post(client, project).json()["audit_id"]
        second = self._post(client, project).json()["audit_id"]
        self.assertNotEqual(first, second)
        listing = _get(client, f"/projects/{project}/writing/loop-audits").json()
        items = listing["items"]
        self.assertEqual([i["audit_id"] for i in items], [second, first])
        # Summary is bodyless: no candidate text/hashes/stages on the list rows.
        for item in items:
            self.assertNotIn("final_candidate_text", item)
            self.assertNotIn("stages", item)
            self.assertEqual(set(item), {
                "audit_id", "request_id", "loop_status", "error_type",
                "revision_rounds", "retrieval_rounds", "gate_evaluations",
                "total_tokens", "wall_clock_ms", "created_at",
            })

    def test_retrieval_stages_capture_context_pointer_ids(self):
        gate = _LoopGate((
            WritingGateDecision.RETRIEVE_MORE, WritingGateDecision.PASS,
        ))
        from tests.test_writing_revise import _RetrievalPlanner
        client, project, _ = _http(
            _Provider(), gate_service=gate, report_service=_Reporter(),
            retrieval_planner=_RetrievalPlanner(),
            context_service=_PointerContext(),
            loop_audit_service=self._audit_service(),
        )
        audit_id = self._post(client, project).json()["audit_id"]
        payload = _get(
            client, f"/projects/{project}/writing/loop-audits/{audit_id}"
        ).json()
        by_stage = {s["stage"]: s for s in payload["stages"]}
        self.assertEqual(
            tuple(by_stage["context_search"]["pointer_ids"]),
            ("d1", "s1", "sr1", "v1"),
        )
        self.assertEqual(
            tuple(by_stage["merge"]["pointer_ids"]), ("d1", "s1", "sr1", "v1")
        )

    def test_audit_write_does_not_save_to_core_sot(self):
        core = _NoWriteCoreSotService()
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            core_service=core, loop_audit_service=self._audit_service(),
        )
        self.assertEqual(self._post(client, project).status_code, 200)
        self.assertEqual(core.save_calls, 0)

    def test_project_isolation_on_list_and_detail(self):
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        audit_id = self._post(client, project).json()["audit_id"]
        other = client.post("/projects", {"name": "Other"}).json()["id"]
        self.assertEqual(
            _get(client, f"/projects/{other}/writing/loop-audits")
            .json()["items"], [])
        self.assertEqual(
            _get(
                client, f"/projects/{other}/writing/loop-audits/{audit_id}"
            ).status_code, 404)

    def test_pre_loop_rejection_is_not_audited(self):
        """Over-strict guard: request rejected before the loop leaves no run."""
        client, project, _ = _http(
            _Provider(), gate_service=_Gate(), report_service=_Reporter(),
            loop_audit_service=self._audit_service(),
        )
        # Duplicate anchor → 400 validation before the loop runs.
        rejected = self._post(
            client, project, _body(candidate_text="잘못된 문장. 잘못된 문장.")
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(
            _get(client, f"/projects/{project}/writing/loop-audits")
            .json()["items"], [])


def _get(client, path):
    import asyncio

    import httpx

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://test"
        ) as http_client:
            return await http_client.get(path)

    return asyncio.run(send())


if __name__ == "__main__":
    unittest.main()
