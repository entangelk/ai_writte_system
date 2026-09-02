"""소유자 프로젝트 purge + 관리자 아카이브 (오너 결정 2026-08-28).

설정탭의 "프로젝트 삭제" 버튼이 부를 경로가 이것이다. 잠그는 계약:

1. **소유자 purge(``POST /projects/{id}/purge``)** — admin purge 와 **같은 파괴
   그래프**를 탄다(감사·이름 이력·12 서비스·outbox). 어느 한쪽만 파괴를 흘리면
   조용한 고아가 된다(D5 부분 삭제) — derived 스파이로 잠근다.
2. **소유권** — 남의 프로젝트 purge 는 403(관리자 경로가 아닌 이상).
3. **아카이브 선행(409)** — admin purge 와 같은 2단계 강제.
4. **관리자 아카이브(``POST /admin/projects/{id}/archive``)** — 관리 콘솔의 purge
   진입점. 이것이 없으면 purge 는 archived 프로젝트만 받는데 그 상태로 만들 화면
   경로가 없어 도달 자체가 막힌다(2026-08-28 발견).

**양방향**:
- under — derived 파괴를 흘리면 스파이 단정이, outbox 를 빼면 enqueue 단정이 실패한다.
- over — 소유자 경로에 admin 검사를 얹으면(또는 그 반대) 403/204 단정이 실패한다.
"""

from __future__ import annotations

import unittest

from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService,
    InMemoryCandidateIdentityGroupRepository,
)
from services.application.app.auth.admin_audit import (
    AdminAuditService,
    InMemoryAdminAuditRepository,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.deletion.project_name_history import (
    InMemoryProjectNameHistoryRepository,
    ProjectNameHistoryService,
)
from services.application.app.indexing.models import IndexSyncEvent
from services.application.app.indexing.service import (
    InMemoryIndexSyncRepository,
    IndexSyncOutboxService,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)
from tests.test_auth_api import _PurgeSpy, _client


class OwnerProjectPurgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.outbox_repo = InMemoryIndexSyncRepository()
        self.sync_outbox = IndexSyncOutboxService(self.outbox_repo)
        self.memory_spy = _PurgeSpy(MemoryService(InMemoryMemoryRepository()))
        self.analysis_spy = _PurgeSpy(AnalysisService(InMemoryAnalysisRepository()))
        # 2026-09-02 Slice 0: identity group 3컬렉션도 같은 파괴 그래프를 탄다.
        self.identity_spy = _PurgeSpy(CandidateIdentityGroupService(
            InMemoryCandidateIdentityGroupRepository()
        ))
        self.admin_audit = AdminAuditService(InMemoryAdminAuditRepository())
        self.name_history = ProjectNameHistoryService(
            InMemoryProjectNameHistoryRepository()
        )
        self.client, self.users, _ = _client(
            core_sot=self.core_sot, index_sync_outbox=self.sync_outbox,
            memory_service=self.memory_spy, analysis_service=self.analysis_spy,
            identity_group_service=self.identity_spy,
            admin_audit=self.admin_audit, project_name_history=self.name_history,
        )
        self.users.create_user(username="bob", password="pw456")
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        project = self.client.post("/projects", json={"name": "내 소설"}).json()
        self.project_id = project["id"]

    def _purge(self) -> object:
        return self.client.post(
            f"/projects/{self.project_id}/purge", json={"reason": "정리"}
        )

    def test_owner_purge_is_409_until_archived(self) -> None:
        response = self._purge()
        self.assertEqual(response.status_code, 409)
        self.assertIsNotNone(
            self.core_sot.get_project(project_id=self.project_id)
        )

    def test_owner_purge_returns_204_and_destroys_the_graph(self) -> None:
        self.client.delete(f"/projects/{self.project_id}")
        response = self._purge()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])
        # D5 전수 — 소유자 경로라고 derived 파괴를 흘리면 안 된다.
        self.assertEqual(self.memory_spy.purged, [self.project_id])
        self.assertEqual(self.analysis_spy.purged, [self.project_id])
        self.assertEqual(self.identity_spy.purged, [self.project_id])
        # worker drain(6c) 용 enqueue — 이것이 빠지면 vector/index 가 잔류한다.
        # (아카이브가 남긴 PROJECT_ARCHIVED 행도 같이 있다 — 그것이 선행 단계다.)
        entries = list(self.outbox_repo.outbox_entries.values())
        self.assertIn(IndexSyncEvent.PROJECT_PURGED, [e.event for e in entries])
        # 파기가 살리는 이름 한 값(8.2c) — 소유자 경로도 같이 남긴다.
        self.assertEqual(
            self.name_history.get(project_id=self.project_id).name, "내 소설",
        )

    def test_another_user_cannot_purge_someone_elses_project(self) -> None:
        self.client.post(
            "/auth/login", json={"username": "bob", "password": "pw456"}
        )
        response = self._purge()
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(
            self.core_sot.get_project(project_id=self.project_id)
        )

    def test_second_owner_purge_is_404(self) -> None:
        self.client.delete(f"/projects/{self.project_id}")
        self.assertEqual(self._purge().status_code, 204)
        self.assertEqual(self._purge().status_code, 404)


class AdminArchiveProjectTest(unittest.TestCase):
    """관리 콘솔의 purge 진입점 — purge 의 선행 조건을 admin 권한으로 만든다."""

    def setUp(self) -> None:
        self.core_sot = CoreSotService(InMemoryCoreSotRepository())
        self.client, self.users, _ = _client(core_sot=self.core_sot)
        self.users.create_user(username="root", password="pw789", is_admin=True)
        # alice 의 프로젝트 — admin 은 소유자가 아니다.
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        project = self.client.post("/projects", json={"name": "남의 소설"}).json()
        self.project_id = project["id"]
        self.client.post(
            "/auth/login", json={"username": "root", "password": "pw789"}
        )

    def test_admin_archive_marks_archived_and_leaves_no_activity_row(self) -> None:
        response = self.client.post(
            f"/admin/projects/{self.project_id}/archive"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])
        self.assertTrue(
            self.core_sot.get_project(project_id=self.project_id).archived
        )
        # 관리자 행위는 활동 로그가 아닌 관리자 축이다(I3) — 소유자 타임라인에
        # 행이 남지 않는다. 소유자 아카이브(DELETE /projects/{id})만 행을 남긴다.
        self.client.post(
            "/auth/login", json={"username": "alice", "password": "pw123"}
        )
        events = self.client.get(
            f"/projects/{self.project_id}/activity"
        ).json()["events"]
        self.assertFalse(
            any(e["action"] == "project_archived" for e in events),
        )

    def test_admin_archive_of_unknown_project_is_404(self) -> None:
        response = self.client.post("/admin/projects/proj-none/archive")
        self.assertEqual(response.status_code, 404)

    def test_archived_by_admin_is_now_reachable_for_admin_purge(self) -> None:
        # 이 슬라이스가 존재하는 이유 — 이 도달 경로가 막혀 있었다.
        self.client.post(f"/admin/projects/{self.project_id}/archive")
        response = self.client.post(
            f"/admin/projects/{self.project_id}/purge",
            json={"reason": "관리자 정리"},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual([p.id for p in self.core_sot.list_projects()], [])


if __name__ == "__main__":
    unittest.main()
