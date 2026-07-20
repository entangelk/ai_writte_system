"""Unaccepted Writing candidate recovery store regressions.

Brief: docs/plans/unaccepted-candidate-persistence-decisions.md (D0=B / D1=B /
D2=A, 2026-07-20). Locks the pre-dogfood safety net both directions:

- generate persists the candidate to the recovery store (under-strict: the net
  fires) but ONLY when a draft key exists (over-strict: no current_position →
  no orphan save).
- D1=B keeps a per-draft **history**, newest-first, bounded by a provisional cap
  (over-strict: the cap trims the oldest, never the newest).
- a *saved* accept clears the draft's scratch (under-strict), while a non-PASS
  accept leaves it intact (over-strict: the user can still recover the bounced
  draft).
- list/discard HTTP surfaces + project 404.

Retention values here are the provisional implementer decision pending owner
SoT ratification (see the brief's "잠정 보존/만료 정책").
"""

import asyncio
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx

from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import (
    _default_writing_scratch_service,
    create_app,
)
from services.application.app.writing.models import WritingGateDecision
from services.application.app.writing.scratch import (
    MAX_SCRATCH_PER_DRAFT,
    InMemoryWritingScratchRepository,
    WritingScratchService,
)

from tests.test_writing import _FakeContextSearch, _FakeProvider, _package, _service
from tests.test_writing_accept import _Context, _FailingAnalysis, _Gate


def _clock_seq(start=None):
    now = start or datetime(2026, 7, 20, tzinfo=UTC)
    state = {"n": 0}

    def tick():
        state["n"] += 1
        return now + timedelta(seconds=state["n"])

    return tick


def _id_seq():
    state = {"n": 0}

    def factory():
        state["n"] += 1
        return f"wds:{state['n']}"

    return factory


def _service_with(repo, *, max_per_draft=20):
    return WritingScratchService(
        repo, clock=_clock_seq(), id_factory=_id_seq(),
        max_per_draft=max_per_draft,
    )


class ScratchServiceTest(unittest.TestCase):
    def _saved(self, svc, project, draft, text):
        return svc.save(
            project_id=project, draft_id=draft, request_id="wr1",
            task_type="continue_scene", output_type="draft_patch",
            instruction="이어서", candidate_text=text,
        )

    def test_save_appends_and_lists_newest_first(self):
        svc = _service_with(InMemoryWritingScratchRepository())
        self._saved(svc, "p1", "d1", "첫 초안")
        self._saved(svc, "p1", "d1", "둘째 초안")
        items = svc.list_for_draft("p1", "d1")
        self.assertEqual([e.candidate_text for e in items],
                         ["둘째 초안", "첫 초안"])

    def test_history_is_capped_dropping_oldest(self):
        # D1=B keeps history but bounded. With cap=3, a 4th save evicts the
        # oldest. Over-strict guard: the cap must trim the OLDEST, never a newer
        # entry, and must keep exactly `cap` entries.
        svc = _service_with(InMemoryWritingScratchRepository(), max_per_draft=3)
        for i in range(4):
            self._saved(svc, "p1", "d1", f"초안{i}")
        items = svc.list_for_draft("p1", "d1")
        self.assertEqual(len(items), 3)
        self.assertEqual([e.candidate_text for e in items],
                         ["초안3", "초안2", "초안1"])
        self.assertNotIn("초안0", [e.candidate_text for e in items])

    def test_clear_draft_removes_all_and_returns_count(self):
        svc = _service_with(InMemoryWritingScratchRepository())
        self._saved(svc, "p1", "d1", "a")
        self._saved(svc, "p1", "d1", "b")
        self.assertEqual(svc.clear_draft("p1", "d1"), 2)
        self.assertEqual(svc.list_for_draft("p1", "d1"), ())

    def test_isolation_by_project_and_draft(self):
        svc = _service_with(InMemoryWritingScratchRepository())
        self._saved(svc, "p1", "d1", "p1d1")
        self._saved(svc, "p1", "d2", "p1d2")
        self._saved(svc, "p2", "d1", "p2d1")
        self.assertEqual([e.candidate_text for e in svc.list_for_draft("p1", "d1")],
                         ["p1d1"])
        # clearing one draft leaves the others untouched
        svc.clear_draft("p1", "d1")
        self.assertEqual(len(svc.list_for_draft("p1", "d2")), 1)
        self.assertEqual(len(svc.list_for_draft("p2", "d1")), 1)


class ScratchCapConfigTest(unittest.TestCase):
    """The per-draft cap is env-tunable (owner, 2026-07-20): the useful history
    depth differs per writer, and the value is provisional pending SoT
    ratification, so it must not be a code constant.
    """

    def _service(self):
        return _default_writing_scratch_service()

    def test_default_cap_is_twenty_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WRITING_SCRATCH_MAX_PER_DRAFT", None)
            os.environ.pop("CORE_SOT_MONGO_URI", None)
            self.assertEqual(MAX_SCRATCH_PER_DRAFT, 20)
            self.assertEqual(self._service()._max_per_draft, 20)

    def test_env_overrides_the_cap(self):
        with patch.dict(os.environ, {"WRITING_SCRATCH_MAX_PER_DRAFT": "3"}):
            os.environ.pop("CORE_SOT_MONGO_URI", None)
            service = self._service()
        self.assertEqual(service._max_per_draft, 3)

    def test_configured_cap_actually_trims(self):
        # The knob has to reach the trim path, not just be parsed.
        with patch.dict(os.environ, {"WRITING_SCRATCH_MAX_PER_DRAFT": "2"}):
            os.environ.pop("CORE_SOT_MONGO_URI", None)
            service = self._service()
        for i in range(3):
            service.save(project_id="p1", draft_id="d1", request_id="wr",
                         task_type="continue_scene", output_type="draft_patch",
                         instruction="이어서", candidate_text=f"초안{i}")
        self.assertEqual(
            [e.candidate_text for e in service.list_for_draft("p1", "d1")],
            ["초안2", "초안1"])

    def test_cap_below_one_is_rejected_loudly(self):
        # over-strict: a misconfigured cap must not silently trim away the very
        # drafts the safety net exists to protect — it fails at construction.
        for raw in ("0", "-1"):
            with self.subTest(raw=raw):
                with patch.dict(
                    os.environ, {"WRITING_SCRATCH_MAX_PER_DRAFT": raw}
                ):
                    os.environ.pop("CORE_SOT_MONGO_URI", None)
                    with self.assertRaises(ValueError):
                        self._service()

    def test_non_numeric_cap_is_rejected_loudly(self):
        with patch.dict(os.environ, {"WRITING_SCRATCH_MAX_PER_DRAFT": "many"}):
            os.environ.pop("CORE_SOT_MONGO_URI", None)
            with self.assertRaises(ValueError):
                self._service()


class _ScratchClient:
    __test__ = False

    def __init__(self, app):
        self._app = app

    def _run(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def post(self, path, **kwargs):
        return self._run("POST", path, **kwargs)

    def get(self, path, **kwargs):
        return self._run("GET", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._run("DELETE", path, **kwargs)


def _generate_app(scratch, *, content="이어진 장면."):
    core = CoreSotService(InMemoryCoreSotRepository())
    app = create_app(
        service=core,
        writing_service=_service(_FakeProvider(content=content)),
        context_search_service=_FakeContextSearch(_package()),
        writing_scratch_service=scratch,
    )
    client = _ScratchClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, project_id


class ScratchGenerateHttpTest(unittest.TestCase):
    def test_generate_with_position_persists_scratch(self):
        # under-strict: the safety net fires — the generated candidate is
        # recoverable for the draft it continues.
        scratch = WritingScratchService(InMemoryWritingScratchRepository())
        client, project_id = _generate_app(scratch, content="복구 대상 초안")
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.",
                  "current_position": {"draft_id": "d1", "version_id": "v1"}},
        )
        self.assertEqual(response.status_code, 200)
        items = scratch.list_for_draft(project_id, "d1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].candidate_text, "복구 대상 초안")
        self.assertIsNone(items[0].intent)

    def test_generate_without_position_does_not_persist(self):
        # over-strict: no draft key → no orphan scratch entry. The recovery net
        # is draft-scoped; a positionless generate has nothing to key on.
        scratch = WritingScratchService(InMemoryWritingScratchRepository())
        client, project_id = _generate_app(scratch)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(scratch.list_for_draft(project_id, "d1"), ())


class ScratchListDiscardHttpTest(unittest.TestCase):
    def _app_with_seeded(self):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        scratch = WritingScratchService(
            InMemoryWritingScratchRepository(),
            clock=_clock_seq(), id_factory=_id_seq(),
        )
        app = create_app(service=core, writing_scratch_service=scratch)
        client = _ScratchClient(app)
        scratch.save(project_id=project.id, draft_id="d1", request_id="wr1",
                     task_type="continue_scene", output_type="draft_patch",
                     instruction="이어서", candidate_text="오래된")
        scratch.save(project_id=project.id, draft_id="d1", request_id="wr2",
                     task_type="continue_scene", output_type="draft_patch",
                     instruction="이어서", candidate_text="최신")
        return client, project.id

    def test_list_returns_items_newest_first_with_keys(self):
        client, project_id = self._app_with_seeded()
        response = client.get(
            f"/projects/{project_id}/writing/scratch", params={"draft_id": "d1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["draft_id"], "d1")
        self.assertEqual([i["candidate_text"] for i in body["items"]],
                         ["최신", "오래된"])
        first = body["items"][0]
        self.assertEqual(set(first), {
            "id", "draft_id", "request_id", "task_type", "output_type",
            "instruction", "candidate_text", "intent", "created_at"})

    def test_discard_clears_and_reports_count(self):
        client, project_id = self._app_with_seeded()
        response = client.delete(
            f"/projects/{project_id}/writing/scratch", params={"draft_id": "d1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 2)
        after = client.get(
            f"/projects/{project_id}/writing/scratch", params={"draft_id": "d1"})
        self.assertEqual(after.json()["items"], [])

    def test_list_and_discard_unknown_project_are_404(self):
        client, _ = self._app_with_seeded()
        listing = client.get(
            "/projects/nope/writing/scratch", params={"draft_id": "d1"})
        self.assertEqual(listing.status_code, 404)
        discard = client.delete(
            "/projects/nope/writing/scratch", params={"draft_id": "d1"})
        self.assertEqual(discard.status_code, 404)


class ScratchAcceptCleanupHttpTest(unittest.TestCase):
    def _setup(self, *, decision=WritingGateDecision.PASS, analysis=None):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        draft = core.create_draft(project_id=project.id, title="Draft")
        base = core.save_draft(project_id=project.id, draft_id=draft.id,
                               raw_text="기존.", idempotency_key="base")
        scratch = WritingScratchService(InMemoryWritingScratchRepository())
        scratch.save(project_id=project.id, draft_id=draft.id, request_id="wr1",
                     task_type="continue_scene", output_type="draft_patch",
                     instruction="이어서", candidate_text="복구 대상")
        app = create_app(
            service=core,
            analysis_service=analysis or AnalysisService(
                InMemoryAnalysisRepository()),
            context_search_service=_Context(),
            writing_gate_service=_Gate(decision),
            writing_scratch_service=scratch)
        client = _ScratchClient(app)
        return client, project.id, draft.id, base.draft_version.id, scratch

    def _accept(self, client, project, draft, base):
        return client.post(f"/projects/{project}/writing/accept", json={
            "request_id": "wr1", "draft_id": draft, "base_version_id": base,
            "idempotency_key": "accept-1", "instruction": "이어서 써줘",
            "candidate_text": "새 글.",
            "current_position": {"draft_id": draft, "version_id": base}})

    def test_saved_accept_clears_scratch(self):
        # under-strict: a PASS accept saved a canonical version → scratch history
        # for the draft is cleared.
        client, project, draft, base, scratch = self._setup()
        response = self._accept(client, project, draft, base)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["accepted"])
        self.assertEqual(scratch.list_for_draft(project, draft), ())

    def test_non_pass_accept_keeps_scratch(self):
        # over-strict: a REVISE accept saved nothing (accepted=false) → the
        # recovery net must survive so the user can still restore the draft.
        client, project, draft, base, scratch = self._setup(
            decision=WritingGateDecision.REVISE)
        response = self._accept(client, project, draft, base)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["accepted"])
        self.assertEqual(len(scratch.list_for_draft(project, draft)), 1)

    def test_partial_analysis_failure_still_clears_scratch(self):
        # H-2 (verification 2026-07-20): the 502 partial saved a canonical
        # version and only the analysis job failed, so the brief's rationale
        # ("정본 확정 → scratch 무의미") applies here too. Under-strict guard:
        # moving the cleanup back below the 502 return re-fails this.
        client, project, draft, base, scratch = self._setup(
            analysis=_FailingAnalysis(InMemoryAnalysisRepository()))
        response = self._accept(client, project, draft, base)
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertIsNotNone(body["saved"])
        self.assertEqual(scratch.list_for_draft(project, draft), ())


class _ExplodingScratch(WritingScratchService):
    """Every scratch write/delete raises — the safety net's worst case."""

    def save(self, **kwargs):
        raise RuntimeError("scratch store down")

    def clear_draft(self, project_id, draft_id):
        raise RuntimeError("scratch store down")


class ScratchBestEffortIsolationTest(unittest.TestCase):
    """H-1/H-4 (verification 2026-07-20): the safety net never breaks the
    primary flow, and never fires when the primary flow failed.

    The brief's best-effort clause is currently a *provisional* policy; these
    guards are added ahead of its SoT promotion so the branch is not an empty
    cell the moment it becomes canonical.
    """

    def test_generate_succeeds_when_scratch_save_raises(self):
        scratch = _ExplodingScratch(InMemoryWritingScratchRepository())
        client, project_id = _generate_app(scratch, content="살아남는 초안")
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "이어서 써줘.",
                  "current_position": {"draft_id": "d1", "version_id": "v1"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "살아남는 초안")

    def test_accept_succeeds_when_scratch_clear_raises(self):
        core = CoreSotService(InMemoryCoreSotRepository())
        project = core.create_project(name="Novel")
        draft = core.create_draft(project_id=project.id, title="Draft")
        base = core.save_draft(project_id=project.id, draft_id=draft.id,
                               raw_text="기존.", idempotency_key="base")
        app = create_app(
            service=core,
            analysis_service=AnalysisService(InMemoryAnalysisRepository()),
            context_search_service=_Context(),
            writing_gate_service=_Gate(WritingGateDecision.PASS),
            writing_scratch_service=_ExplodingScratch(
                InMemoryWritingScratchRepository()))
        response = _ScratchClient(app).post(
            f"/projects/{project.id}/writing/accept", json={
                "request_id": "wr1", "draft_id": draft.id,
                "base_version_id": base.draft_version.id,
                "idempotency_key": "accept-1", "instruction": "이어서 써줘",
                "candidate_text": "새 글."})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["accepted"])

    def test_failed_generate_leaves_no_scratch(self):
        # over-strict: the net must not persist anything for a generation that
        # never produced a candidate.
        scratch = WritingScratchService(InMemoryWritingScratchRepository())
        client, project_id = _generate_app(scratch)
        response = client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": "wr1", "instruction": "",
                  "current_position": {"draft_id": "d1", "version_id": "v1"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(scratch.list_for_draft(project_id, "d1"), ())


if __name__ == "__main__":
    unittest.main()
