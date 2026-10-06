"""정본 기억 수동 수정(오너 결정 2026-10-06, B안) — ``PUT /projects/{id}/memory/{memory_id}``.

승격·버전 적용과 같은 append-only 사슬을 사람 직접 수정에도 유지하는 것이 이
경로의 계약이다: 고친 값은 **새 canonical 버전**, 대상은 ``SUPERSEDED`` 보존.

**양방으로 문다**(records-and-handoff 의 회귀 규칙):

- under-strict — supersede 보존·provenance ``human_edited``·scope 재계산·재색인
  enqueue·활동 로그 행 중 어느 하나라도 빼면 해당 셀이 재실패한다.
- over-strict — 멱동 replay 를 새 버전으로 잘못 세거나(셀: 같은 키 재요청이
  version 3 을 만들면 실패), 낡은 ``base_version``·비-canonical 대상·보관 프로젝트를
  통과시키는 과잉 관대함도 실패한다.
"""

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
    MemoryService,
)
from tests.auth_support import authenticate


class TestClient:
    """test_memory_api.py 의 것과 같은 seam — 인증은 우회하고 도메인만 본다."""

    def __init__(self, app):
        authenticate(app)
        self._app = app

    def _request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self._request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._request("DELETE", path, **kwargs)


def _seed_candidate(
    analysis: AnalysisService,
    *,
    project_id: str,
    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
    payload=None,
):
    if payload is None:
        payload = {"name": "Ariel", "observation": "brave under pressure"}
    job = analysis.create_job(
        project_id=project_id,
        snapshot_id="snapshot-1",
        idempotency_key="run-1",
    ).job
    task = analysis.create_task(
        project_id=project_id, job_id=job.id, candidate_type=candidate_type
    )
    return analysis.record_candidate(
        project_id=project_id,
        task_id=task.id,
        logical_key="lk-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload=payload,
    ).candidate


def _build():
    """outbox 를 진짜 서비스로 묶는다 — 재색인 enqueue 단정 때문에(test_memory_api
    의 502 계열과 같은 이유로 stub 을 쓰지 않는다)."""
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    outbox_repo = InMemoryIndexSyncRepository()
    memory = MemoryService(
        InMemoryMemoryRepository(), reindex_outbox=IndexSyncOutboxService(outbox_repo)
    )
    app = create_app(
        service=core_sot,
        analysis_service=analysis,
        memory_service=memory,
    )
    client = TestClient(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, analysis, project_id, outbox_repo


def _promote_one(client, analysis, project_id, **kwargs):
    candidate = _seed_candidate(analysis, project_id=project_id, **kwargs)
    response = client.post(
        f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
    )
    assert response.status_code == 200, response.text
    return response.json()["memory"]


def _edit_body(version, payload, key="edit-key-1"):
    return {
        "base_version": version,
        "idempotency_key": key,
        "payload": payload,
    }


class ManualEditHappyPathTest(unittest.TestCase):
    def test_edit_mints_a_new_canonical_version_and_supersedes_the_target(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        response = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel Song", "observation": "cautious"}),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        v2 = body["memory"]
        self.assertEqual(v2["status"], "canonical")
        self.assertEqual(v2["version"], 2)
        self.assertEqual(v2["supersedes"], v1["id"])
        self.assertEqual(v2["provenance"], "human_edited")
        self.assertEqual(v2["payload"]["name"], "Ariel Song")
        self.assertEqual(v2["payload"]["observation"], "cautious")
        # 근거·신뢰도·분석 잡은 이어받는다 — 편집은 내용 교정이지 근거 재판정이 아니다.
        self.assertEqual(v2["source_ref_ids"], v1["source_ref_ids"])
        self.assertEqual(v2["confidence"], v1["confidence"])
        self.assertEqual(v2["analysis_job_id"], v1["analysis_job_id"])
        # 사람 편집의 합성 후보 키 — 후보 절차를 안 거쳤음이 저장소 키에 드러난다.
        self.assertEqual(v2["source_candidate_id"], "manual:edit-key-1")

        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        by_id = {entry["id"]: entry for entry in listed}
        # append-only: 옛 버전은 지워지지 않고 SUPERSEDED 로 보존된다.
        self.assertEqual(by_id[v1["id"]]["status"], "superseded")
        self.assertEqual(by_id[v2["id"]]["status"], "canonical")

    def test_edit_rederives_the_scope_from_the_edited_payload(self):
        """over-strict — scope 를 이어받는 과잉 교정을 문다. 이름을 고친 인물이
        옛 identity key 에 묶이면 compare·별칭 매처가 계속 옛 이름을 본다."""
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(
            client, analysis, project_id,
            payload={"name": "Ariel", "observation": "brave"},
        )
        self.assertEqual(v1["scope"]["scope_id"], "ariel")

        edited = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Maren", "observation": "brave"}),
        ).json()["memory"]

        self.assertEqual(
            edited["scope"], {"scope_type": "character", "scope_id": "maren"}
        )

    def test_edit_enqueues_a_memory_reindex(self):
        """under-strict — 2B.5 D3=B 의 초크 포인트가 사람 편집 경로에도 열려 있다."""
        client, analysis, project_id, outbox_repo = _build()
        v1 = _promote_one(client, analysis, project_id)

        client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "quieter"}),
        )

        self.assertEqual(len(outbox_repo.outbox_entries), 2)  # 승격 1 + 편집 1

    def test_edit_records_one_activity_row_and_a_replay_records_none(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "quieter"}),
        )

        events = client.get(f"/projects/{project_id}/activity").json()["events"]
        edits = [e for e in events if e["action"] == "canonical_memory_edited"]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["target_type"], "memory")
        self.assertEqual(edits[0]["target_id"], v1["id"])
        self.assertEqual(edits[0]["after"], "version=2")


class ManualEditIdempotencyTest(unittest.TestCase):
    def test_same_key_replays_the_minted_version_instead_of_minting_again(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)
        payload = {"name": "Ariel", "observation": "quieter"}

        first = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, payload, key="retry-me"),
        )
        replay = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, payload, key="retry-me"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(
            replay.json()["memory"]["id"], first.json()["memory"]["id"]
        )
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        # over-strict: 재시도가 세 번째 버전을 만들면 실패한다.
        self.assertEqual(len(listed), 2)

    def test_different_key_on_the_stale_base_is_rejected(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        first = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "a"}, key="k1"),
        )
        second = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "b"}, key="k2"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        self.assertEqual(len(listed), 2)


class ManualEditRejectionTest(unittest.TestCase):
    def test_stale_base_version_is_a_409(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        response = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(99, {"name": "Ariel", "observation": "x"}),
        )

        self.assertEqual(response.status_code, 409)

    def test_editing_a_superseded_version_is_a_409(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)
        client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "a"}),
        )

        # 사슬의 옛 버전을 다시 고치는 시도 — 대상은 더 이상 canonical 이 아니다.
        response = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "b"}, key="late"),
        )

        self.assertEqual(response.status_code, 409)

    def test_invalid_payload_is_a_400(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        missing_field = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel"}),  # observation 없음
        )
        unknown_field = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(
                1, {"name": "Ariel", "observation": "x", "extra": "y"}
            ),
        )
        blank_value = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": ""}),
        )

        self.assertEqual(missing_field.status_code, 400)
        self.assertEqual(unknown_field.status_code, 400)
        self.assertEqual(blank_value.status_code, 400)

    def test_missing_memory_or_project_is_a_404(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)

        missing_memory = client.put(
            f"/projects/{project_id}/memory/nope",
            json=_edit_body(1, {"name": "Ariel", "observation": "x"}),
        )
        missing_project = client.put(
            "/projects/missing/memory/whatever",
            json=_edit_body(1, {"name": "Ariel", "observation": "x"}),
        )

        self.assertEqual(missing_memory.status_code, 404)
        self.assertEqual(missing_project.status_code, 404)

    def test_archived_project_is_a_409(self):
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)
        client.delete(f"/projects/{project_id}")  # 1단계 보관(soft)

        response = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "x"}),
        )

        self.assertEqual(response.status_code, 409)

    def test_second_edit_versions_the_new_canonical_entry(self):
        """사슬이 이어 붙는다 — v2 를 다시 고치면 v3 (supersedes=v2)."""
        client, analysis, project_id, _outbox = _build()
        v1 = _promote_one(client, analysis, project_id)
        v2 = client.put(
            f"/projects/{project_id}/memory/{v1['id']}",
            json=_edit_body(1, {"name": "Ariel", "observation": "a"}, key="k1"),
        ).json()["memory"]

        v3 = client.put(
            f"/projects/{project_id}/memory/{v2['id']}",
            json=_edit_body(2, {"name": "Ariel", "observation": "b"}, key="k2"),
        ).json()["memory"]

        self.assertEqual(v3["version"], 3)
        self.assertEqual(v3["supersedes"], v2["id"])
        listed = client.get(f"/projects/{project_id}/memory").json()["memory"]
        statuses = {e["version"]: e["status"] for e in listed}
        self.assertEqual(
            statuses, {1: "superseded", 2: "superseded", 3: "canonical"}
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
