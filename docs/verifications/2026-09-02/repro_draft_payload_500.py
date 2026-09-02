"""Repro: d02837a flat DraftPayload 500 폭발 반경 (2026-09-02 검증).

`_draft_payload`가 `latest_snapshot_id`를 출력하지만 `DraftPayload`(extra="forbid")에는
그 필드가 없어 response validation이 실패하는 경로를 실증한다. InMemory 서비스만 쓰므로
인프라 의존이 없다. 기대 출력(HEAD d02837a):

    POST /drafts (장면 생성): 500
    GET /drafts (플랫 목록): 500
    GET /drafts/{id} (에디터 로드): 500
    PATCH /drafts/{id} (개명): 500
    GET /chapters (중첩 목록, ScenePayload): 200

실행: PYTHONPATH=. python3 docs/verifications/2026-09-02/repro_draft_payload_500.py
"""

import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from services.application.app.analysis.review_queue import (
    InMemoryReviewQueueRepository,
    ReviewQueueService,
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
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
)
from services.application.app.main import create_app
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)
from tests.auth_support import authenticate

core_sot = CoreSotService(InMemoryCoreSotRepository())
app = create_app(
    service=core_sot,
    analysis_service=AnalysisService(InMemoryAnalysisRepository()),
    memory_service=MemoryService(InMemoryMemoryRepository()),
    index_sync_outbox=IndexSyncOutboxService(InMemoryIndexSyncRepository()),
    review_queue_service=ReviewQueueService(InMemoryReviewQueueRepository()),
)
authenticate(app)
client = TestClient(app, raise_server_exceptions=False)
pid = client.post("/projects", json={"name": "P"}).json()["id"]
cid = client.post(f"/projects/{pid}/chapters", json={"title": "1장"}).json()["id"]
print("POST /drafts (장면 생성):", client.post(
    f"/projects/{pid}/drafts", json={"chapter_id": cid, "title": "장면1"}
).status_code)
did = core_sot.create_scene(project_id=pid, chapter_id=cid, title="장면2").id
print("GET /drafts (플랫 목록):", client.get(f"/projects/{pid}/drafts").status_code)
print("GET /drafts/{id} (에디터 로드):",
      client.get(f"/projects/{pid}/drafts/{did}").status_code)
print("PATCH /drafts/{id} (개명):", client.patch(
    f"/projects/{pid}/drafts/{did}", json={"title": "개명"}
).status_code)
print("GET /chapters (중첩 목록, ScenePayload):",
      client.get(f"/projects/{pid}/chapters").status_code)
