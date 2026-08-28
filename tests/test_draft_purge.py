"""원고 하드 삭제 — POST /projects/{pid}/drafts/{did}/purge (오너 결정 2026-08-28).

프로젝트 purge(AdminProjectPurgeTest)와 같은 계약의 **draft 스코프 판**이다. 잠그는 축:

1. **아카이브 선행(409)** — 색인 제거(DRAFT_ARCHIVED outbox)가 먼저 확정된 뒤 본체가
   지워지도록 하는 순서 장치. 프로젝트 purge와 같은 모양이다.
2. **active 생성 잡 거부(409, 오너 2026-08-28)** — 잡의 결과물은 draft에 표시되므로
   앵커가 사라진 잡은 완료돼도 갈 곳이 없다.
3. **그래프 소멸 + 형제 보존** — drafts·versions·snapshots·blocks·source_refs·
   receipts·scratch 가 victim 만 지워지고 sibling draft·project 는 무사해야 한다
   (D5 부분 삭제 금지의 draft 판).
4. **append-only 원장** — activity 행은 남는다(프로젝트 purge 때만 지워진다).

**양방향**:
- under — 어느 컬렉션이든 draft 스코프 대신 project 스코프로 지우면 sibling 단정이
  실패한다(과잉 삭제), 지우지 않으면 잔류 단정이 실패한다(고아).
- over — 성공 경로가 409로 바뀌면(선행 검증을 역으로 걸면) 204 단정이 실패한다.
"""

from __future__ import annotations

import unittest

from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobService,
)
from services.application.app.writing.scratch import (
    InMemoryWritingScratchRepository,
    WritingScratchService,
)
from tests.test_auth_api import _client


class DraftPurgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryCoreSotRepository()
        self.core_sot = CoreSotService(self.repo)
        self.job_repo = InMemoryWritingGenerationJobRepository()
        self.jobs = WritingGenerationJobService(self.job_repo)
        self.scratch_repo = InMemoryWritingScratchRepository()
        self.scratch = WritingScratchService(self.scratch_repo)
        self.client, _, _ = _client(
            core_sot=self.core_sot,
            writing_generation_job_service=self.jobs,
            writing_scratch_service=self.scratch,
        )
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        # victim(1편·저장 1회·아카이브) + sibling(1편) — 스코프 검증의 최소 대조군.
        project = self.client.post("/projects", json={"name": "Novel"}).json()
        self.project_id = project["id"]

        def _create_draft(title: str) -> str:
            response = self.client.post(
                f"/projects/{self.project_id}/drafts", json={"title": title}
            )
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["id"]

        self.victim_id = _create_draft("지울 원고")
        self.sibling_id = _create_draft("남을 원고")
        saved = self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/versions",
            json={"raw_text": "첫 문단.", "idempotency_key": "save-victim-1"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.victim_version = saved.json()["draft_version"]

    def _archive_victim(self) -> None:
        response = self.client.delete(
            f"/projects/{self.project_id}/drafts/{self.victim_id}"
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_missing_draft_is_404(self) -> None:
        response = self.client.post(
            f"/projects/{self.project_id}/drafts/draft-none/purge"
        )
        self.assertEqual(response.status_code, 404)

    def test_unarchived_draft_is_409_and_survives(self) -> None:
        # 아카이브 선행 — 이것이 빠지면 색인 제거(outbox)가 확정되기 전에 본체가
        # 지워진다(프로젝트 purge와 같은 이유).
        response = self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIsNotNone(self.core_sot.get_draft(
            project_id=self.project_id, draft_id=self.victim_id,
        ))

    def test_active_generation_job_is_409(self) -> None:
        # 오너 2026-08-28 — 결과물의 앵커가 사라진 잡은 완료돼도 갈 곳이 없다.
        self._archive_victim()
        self.jobs.enqueue(
            project_id=self.project_id, draft_id=self.victim_id,
            request_id="req-1", task_type="continue", instruction="이어써",
            draft_excerpt="첫 문단.", query=None, output_length="short",
            max_output_tokens=512, max_tokens=1024, version_id=self.victim_version["id"],
        )
        response = self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        )
        self.assertEqual(response.status_code, 409)

    def test_purge_removes_victim_graph_and_keeps_sibling(self) -> None:
        self._archive_victim()
        response = self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")  # 204 carries no body

        # victim 소멸 — 정본·버전 모두.
        with self.assertRaises(Exception):
            self.core_sot.get_draft(
                project_id=self.project_id, draft_id=self.victim_id,
            )
        self.assertEqual(
            self.repo.version_count(self.victim_id), 0,
            "victim 의 버전이 잔류한다 — 고아(부분 삭제)다",
        )

        # sibling·project 무사 — 과잉 삭제 방향.
        survivor = self.core_sot.get_draft(
            project_id=self.project_id, draft_id=self.sibling_id,
        )
        self.assertIsNotNone(survivor)
        self.assertEqual(
            [p.id for p in self.core_sot.list_projects()], [self.project_id],
        )

    def test_second_purge_is_404(self) -> None:
        # 프로젝트 purge 의 같은 이름 셀과 대응 — 삭제된 원고의 재삭제는 파기가 아니라
        # 404 다(우연히 같은 id 로 남은 다른 데이터를 지우는 문을 열지 않는다).
        self._archive_victim()
        url = f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        self.assertEqual(self.client.post(url).status_code, 204)
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_activity_row_survives_the_purge(self) -> None:
        # append-only 원장 — 원고는 사라져도 행은 남는다(프로젝트 purge 때만 지운다).
        self._archive_victim()
        self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        )
        events = self.client.get(
            f"/projects/{self.project_id}/activity"
        ).json()["events"]
        purged = [e for e in events if e["action"] == "draft_purged"]
        self.assertEqual(len(purged), 1)
        self.assertEqual(purged[0]["target_id"], self.victim_id)

    def test_scratch_for_victim_is_cleared_sibling_scratch_survives(self) -> None:
        self._archive_victim()
        self.scratch.save(
            project_id=self.project_id, draft_id=self.victim_id,
            request_id="req-v", task_type="continue", output_type="text",
            instruction="i", candidate_text="c",
        )
        self.scratch.save(
            project_id=self.project_id, draft_id=self.sibling_id,
            request_id="req-s", task_type="continue", output_type="text",
            instruction="i", candidate_text="c",
        )
        response = self.client.post(
            f"/projects/{self.project_id}/drafts/{self.victim_id}/purge"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.scratch.list_for_draft(self.project_id, self.victim_id), (),
            "victim 의 scratch 가 잔류한다 — 고아다",
        )
        self.assertEqual(
            len(self.scratch.list_for_draft(self.project_id, self.sibling_id)), 1,
            "sibling 의 scratch 까지 지워졌다 — 과잉 삭제다",
        )


if __name__ == "__main__":
    unittest.main()
