"""정본 기억 병합(오너 결정 2026-10-06, A안) — ``POST /projects/{id}/memory/merge``.

"나"/"주인공" 처럼 같은 인물이 분석에 따라 갈라져 만들어진 canonical 둘을 하나로
통합하는 경로. 계약의 핵심은 **사슬 연결이 데이터로 보존된다**는 것이다: 병합 결과는
생존 쪽의 다음 버전(``supersedes`` 뒤링크)이고 흡수된 항목은 ``merged_into`` 앞링크로
결과를 가리킨다.

**양방으로 문다**:

- under-strict — merged_into 링크·근거 유니온·생존 사슬 승계·활동 로그 행·재색인
  enqueue 중 어느 하나라도 빼면 해당 셀이 재실패한다.
- over-strict — replay 가 새 버전을 만들거나, 낡은 base(양쪽 어느 축이든)·비-canonical
  대상·자기 병합·타입 불일치·인물 외·보관 프로젝트를 통과시키면 실패한다.
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
    logical_key: str,
    candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
    payload=None,
):
    if payload is None:
        payload = {"name": "아리엘", "observation": "폭풍 속에서도 침착하다"}
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
        confidence=0.5,
        source_ref_ids=(f"source-ref-{logical_key}",),
        payload=payload,
    ).candidate


def _build():
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


def _promote(client, analysis, project_id, logical_key, **kwargs):
    candidate = _seed_candidate(
        analysis, project_id=project_id, logical_key=logical_key, **kwargs
    )
    response = client.post(
        f"/projects/{project_id}/analysis/candidates/{candidate.id}/promote"
    )
    assert response.status_code == 200, response.text
    return response.json()["memory"]


def _merge_body(survivor, absorbed, payload, key="merge-key-1"):
    return {
        "survivor_memory_id": survivor["id"],
        "absorbed_memory_id": absorbed["id"],
        "base_survivor_version": survivor["version"],
        "base_absorbed_version": absorbed["version"],
        "idempotency_key": key,
        "payload": payload,
    }


def _listed(client, project_id):
    return {
        entry["id"]: entry
        for entry in client.get(f"/projects/{project_id}/memory").json()["memory"]
    }


class MergeHappyPathTest(unittest.TestCase):
    def test_merge_continues_the_survivor_chain_and_links_the_absorbed_one(self):
        client, analysis, project_id, _outbox = _build()
        # 같은 인물이 분석 표기에 따라 갈라진 두 canonical — 오너가 본 사례의 모양.
        narrator = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "편지를 발견했다"},
        )
        protagonist = _promote(
            client, analysis, project_id, "lk-2",
            payload={"name": "주인공", "observation": "폭풍을 마주 선다"},
        )

        response = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                protagonist, narrator,
                {"name": "주인공", "observation": "편지를 발견하고 폭풍을 마주 선다"},
            ),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["idempotent_replay"])
        merged = body["memory"]
        # 생존 사슬 승계 — 버전이 리셋되지 않는다(오너: "이어져 있어야지").
        self.assertEqual(merged["version"], 2)
        self.assertEqual(merged["supersedes"], protagonist["id"])
        self.assertEqual(merged["status"], "canonical")
        self.assertIsNone(merged["merged_into"])
        self.assertEqual(merged["provenance"], "human_edited")
        self.assertEqual(merged["source_candidate_id"], "manual:merge-key-1")
        # 근거는 양쪽 유니온 — 인물의 별도 상태(관찰)·근거가 모두 이어진다.
        self.assertEqual(
            merged["source_ref_ids"], ["source-ref-lk-2", "source-ref-lk-1"]
        )
        self.assertEqual(
            merged["scope"], {"scope_type": "character", "scope_id": "주인공"}
        )

        by_id = _listed(client, project_id)
        self.assertEqual(by_id[protagonist["id"]]["status"], "superseded")
        # 흡수된 항목은 앞링크로 병합 결과를 가리킨다 — 조용한 막다름이 아니다.
        self.assertEqual(
            by_id[narrator["id"]]["merged_into"], merged["id"]
        )
        self.assertEqual(by_id[narrator["id"]]["status"], "superseded")
        canonical = [
            e for e in by_id.values() if e["status"] == "canonical"
        ]
        self.assertEqual([e["id"] for e in canonical], [merged["id"]])

    def test_the_merged_chain_accepts_a_later_edit_as_v3(self):
        """병합 뒤에도 사슬은 살아 있다 — 일반 수정이 v3 로 이어 붙는다."""
        client, analysis, project_id, _outbox = _build()
        a = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "관찰 A"},
        )
        b = _promote(
            client, analysis, project_id, "lk-2",
            payload={"name": "주인공", "observation": "관찰 B"},
        )
        merged = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                b, a, {"name": "주인공", "observation": "관찰 A + B"}
            ),
        ).json()["memory"]

        edited = client.put(
            f"/projects/{project_id}/memory/{merged['id']}",
            json={
                "base_version": 2,
                "idempotency_key": "edit-after-merge",
                "payload": {"name": "주인공", "observation": "관찰 A + B + C"},
            },
        ).json()["memory"]

        self.assertEqual(edited["version"], 3)
        self.assertEqual(edited["supersedes"], merged["id"])

    def test_merge_enqueues_a_reindex_and_records_one_activity_row(self):
        client, analysis, project_id, outbox_repo = _build()
        a = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "관찰 A"},
        )
        b = _promote(
            client, analysis, project_id, "lk-2",
            payload={"name": "주인공", "observation": "관찰 B"},
        )

        client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                b, a, {"name": "주인공", "observation": "관찰 A + B"}
            ),
        )

        # 승격 2 + 병합 1 — 2B.5 D3=B 초크 포인트가 병합 경로에도 열려 있다.
        self.assertEqual(len(outbox_repo.outbox_entries), 3)
        events = client.get(f"/projects/{project_id}/activity").json()["events"]
        merges = [
            e for e in events if e["action"] == "canonical_memory_merged"
        ]
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["target_id"], b["id"])
        self.assertEqual(merges[0]["after"], "version=2, absorbed=1")


class MergeIdempotencyTest(unittest.TestCase):
    def test_same_key_replays_the_merge_instead_of_minting_again(self):
        client, analysis, project_id, _outbox = _build()
        a = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "관찰 A"},
        )
        b = _promote(
            client, analysis, project_id, "lk-2",
            payload={"name": "주인공", "observation": "관찰 B"},
        )
        payload = {"name": "주인공", "observation": "관찰 A + B"}

        first = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(b, a, payload, key="retry-me"),
        )
        replay = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(b, a, payload, key="retry-me"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(
            replay.json()["memory"]["id"], first.json()["memory"]["id"]
        )
        self.assertEqual(len(_listed(client, project_id)), 3)  # a + b + merged
        # replay 는 활동 행을 남기지 않는다(D2=ⓑ).
        events = client.get(f"/projects/{project_id}/activity").json()["events"]
        self.assertEqual(
            len([e for e in events if e["action"] == "canonical_memory_merged"]),
            1,
        )


class MergeRejectionTest(unittest.TestCase):
    def _pair(self):
        client, analysis, project_id, _outbox = _build()
        a = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "관찰 A"},
        )
        b = _promote(
            client, analysis, project_id, "lk-2",
            payload={"name": "주인공", "observation": "관찰 B"},
        )
        return client, analysis, project_id, a, b

    def test_stale_survivor_base_is_a_409(self):
        client, _analysis, project_id, a, b = self._pair()
        body = _merge_body(
            b, a, {"name": "주인공", "observation": "결합"}
        )
        body["base_survivor_version"] = 99
        self.assertEqual(
            client.post(f"/projects/{project_id}/memory/merge", json=body)
            .status_code,
            409,
        )

    def test_stale_absorbed_base_is_a_409(self):
        client, _analysis, project_id, a, b = self._pair()
        body = _merge_body(
            b, a, {"name": "주인공", "observation": "결합"}
        )
        body["base_absorbed_version"] = 99
        self.assertEqual(
            client.post(f"/projects/{project_id}/memory/merge", json=body)
            .status_code,
            409,
        )

    def test_merging_an_entry_with_itself_is_a_409(self):
        client, _analysis, project_id, a, b = self._pair()
        body = _merge_body(
            b, b, {"name": "주인공", "observation": "결합"}
        )
        self.assertEqual(
            client.post(f"/projects/{project_id}/memory/merge", json=body)
            .status_code,
            409,
        )

    def test_already_absorbed_entry_cannot_merge_again(self):
        client, analysis, project_id, a, b = self._pair()
        c = _promote(
            client, analysis, project_id, "lk-3",
            payload={"name": "소녀", "observation": "관찰 C"},
        )
        client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                b, a, {"name": "주인공", "observation": "결합"}
            ),
        )
        # a 는 이제 비-canonical — 다른 병합의 생존/흡수 어느 쪽이어도 거절.
        # (키는 첫 병합과 달라야 한다 — 같으면 replay 로 200 이 되어 상태 검증이
        # 아니라 멱등 검증이 되어 버린다.)
        body = _merge_body(
            c, a, {"name": "소녀", "observation": "결합 2"}, key="merge-2"
        )
        self.assertEqual(
            client.post(f"/projects/{project_id}/memory/merge", json=body)
            .status_code,
            409,
        )

    def test_type_mismatch_and_non_character_merges_are_409(self):
        client, analysis, project_id, _outbox = _build()
        person = _promote(
            client, analysis, project_id, "lk-1",
            payload={"name": "나", "observation": "관찰 A"},
        )
        event = _promote(
            client, analysis, project_id, "lk-2",
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
            payload={"event": "다리가 무너졌다"},
        )
        other_event = _promote(
            client, analysis, project_id, "lk-3",
            candidate_type=AnalysisCandidateType.EVENT_OBSERVATION,
            payload={"event": "다리가 다시 세워졌다"},
        )

        mismatch = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                person, event, {"name": "나", "observation": "결합"}
            ),
        )
        both_events = client.post(
            f"/projects/{project_id}/memory/merge",
            json=_merge_body(
                other_event, event, {"event": "다리 이야기"}
            ),
        )

        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(both_events.status_code, 409)

    def test_invalid_payload_is_a_400(self):
        client, _analysis, project_id, a, b = self._pair()
        self.assertEqual(
            client.post(
                f"/projects/{project_id}/memory/merge",
                json=_merge_body(b, a, {"name": "주인공"}),
            ).status_code,
            400,
        )

    def test_missing_entries_or_project_are_404(self):
        client, _analysis, project_id, a, b = self._pair()
        missing_absorbed = _merge_body(
            b, {"id": "nope", "version": 1}, {"name": "x", "observation": "y"}
        )
        self.assertEqual(
            client.post(
                f"/projects/{project_id}/memory/merge", json=missing_absorbed
            ).status_code,
            404,
        )
        self.assertEqual(
            client.post(
                "/projects/missing/memory/merge",
                json=_merge_body(a, b, {"name": "x", "observation": "y"}),
            ).status_code,
            404,
        )

    def test_archived_project_is_a_409(self):
        client, _analysis, project_id, a, b = self._pair()
        client.delete(f"/projects/{project_id}")
        self.assertEqual(
            client.post(
                f"/projects/{project_id}/memory/merge",
                json=_merge_body(b, a, {"name": "주인공", "observation": "결합"}),
            ).status_code,
            409,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
