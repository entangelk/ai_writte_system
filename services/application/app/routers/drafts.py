"""원고(draft)·버전 표면 route (``/projects/{id}/drafts*`` 10 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**``DraftOrderIntegrityError`` → 503 은 상류 장애가 아니라 데이터 무결성 얼굴이다**
(H3 의 503 세 얼굴 중 두 번째). 저장된 draft 가 W3 순서 불변식보다 오래된
경우이며 처방은 재시도가 아니라 ``scripts/migrate_ordered_units.py`` 다 — 그래서
문구가 그렇게 적혀 있다. 이것을 502 나 500 으로 바꾸면 계약이 깨진다.

직렬화기 둘(``_draft_payload`` · ``_version_meta_payload``)은 이 도메인 전용이다.
``_version_meta_payload`` 가 ``idempotency_key`` 를 일부러 뺀다는 주석은 계약이다
(내부 저장 토큰이지 공개 읽기 표면이 아니다).
"""

from __future__ import annotations

from fastapi import HTTPException, Query

from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    DraftOrderIntegrityError,
    InvalidDraftOrder,
    NotFound,
    UnsupportedExportFormat,
)

from ..api.models import (
    CreateDraftRequest,
    DraftListResponse,
    DraftOrderPutRequest,
    DraftOrderPutResponse,
    DraftPayload,
    DraftVersionDetailResponse,
    DraftVersionExportResponse,
    DraftVersionListResponse,
    RenameDraftRequest,
    SaveDraftRequest,
    SaveDraftResponse,
)
from ..api.errors import (
    _ERRORS_400_404,
    _ERRORS_400_404_409,
    _ERRORS_404,
    _ERRORS_404_409,
    _ERRORS_404_409_MIGRATION,
    _ERRORS_404_MIGRATION,
    _owned,
)
from ..api.dependencies import _REQUIRE_PROJECT_OWNER


def register_drafts(app, *, core_sot, sync_outbox) -> None:
    def _draft_payload(draft) -> dict[str, object]:
        assert draft.unit_kind is not None
        assert draft.position is not None
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "title": draft.title,
            "archived": draft.archived,
            "unit_kind": draft.unit_kind,
            "position": draft.position,
        }

    def _version_meta_payload(version) -> dict[str, object]:
        # idempotency_key is intentionally omitted: it is an internal save token,
        # not part of the public read surface.
        return {
            "id": version.id,
            "project_id": version.project_id,
            "draft_id": version.draft_id,
            "version_number": version.version_number,
            "snapshot_id": version.snapshot_id,
        }

    @app.patch(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def rename_draft(
        project_id: str, draft_id: str, request: RenameDraftRequest
    ) -> dict[str, object]:
        try:
            draft = core_sot.rename_draft(
                project_id=project_id, draft_id=draft_id, title=request.title
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.delete(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def archive_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.archive_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        sync_outbox.enqueue_draft_archived(
            project_id=project_id,
            draft_id=draft_id,
        )
        return _draft_payload(draft)

    @app.get("/projects/{project_id}/drafts", response_model=DraftListResponse,
             responses=_owned(_ERRORS_404_MIGRATION),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_drafts(project_id: str) -> dict[str, object]:
        try:
            drafts = core_sot.list_drafts(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Stored drafts predate the W3 ordered-unit invariant (or are corrupt).
            # The fix is the one-shot scripts/migrate_ordered_units.py, not a
            # corrected request, so surface a 503 instead of leaking an opaque 500.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"drafts": [_draft_payload(d) for d in drafts]}

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_draft(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            draft = core_sot.get_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions",
        response_model=DraftVersionListResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_draft_versions(project_id: str, draft_id: str) -> dict[str, object]:
        try:
            versions = core_sot.list_draft_versions(
                project_id=project_id, draft_id=draft_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"versions": [_version_meta_payload(v) for v in versions]}

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions/{version_id}",
        response_model=DraftVersionDetailResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_draft_version(
        project_id: str, draft_id: str, version_id: str
    ) -> dict[str, object]:
        try:
            detail = core_sot.get_draft_version(
                project_id=project_id, draft_id=draft_id, version_id=version_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "draft_version": _version_meta_payload(detail.draft_version),
            "snapshot": {
                "id": detail.snapshot.id,
                "project_id": detail.snapshot.project_id,
                "draft_id": detail.snapshot.draft_id,
                "version_id": detail.snapshot.version_id,
                "raw_text": detail.snapshot.raw_text,
                "content_hash": detail.snapshot.content_hash,
            },
            "blocks": [
                {
                    "id": block.id,
                    "project_id": block.project_id,
                    "snapshot_id": block.snapshot_id,
                    "block_index": block.block_index,
                    "kind": block.kind,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                    "text": block.text,
                }
                for block in detail.blocks
            ],
        }

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export",
        response_model=DraftVersionExportResponse,
        responses=_owned(_ERRORS_400_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def export_draft_version(
        project_id: str,
        draft_id: str,
        version_id: str,
        format: str = Query("txt"),
    ) -> dict[str, object]:
        try:
            export = core_sot.export_draft_version(
                project_id=project_id,
                draft_id=draft_id,
                version_id=version_id,
                fmt=format,
            )
        except UnsupportedExportFormat as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "format": export.format,
            "filename": export.filename,
            "content_type": export.content_type,
            "body": export.body,
            "project_id": export.project_id,
            "draft_id": export.draft_id,
            "version_id": export.version_id,
            "version_number": export.version_number,
            "snapshot_id": export.snapshot_id,
            "content_hash": export.content_hash,
        }

    @app.post("/projects/{project_id}/drafts", response_model=DraftPayload,
              responses=_owned(_ERRORS_404_409_MIGRATION),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def create_draft(
        project_id: str, request: CreateDraftRequest
    ) -> dict[str, object]:
        try:
            draft = core_sot.create_draft(
                project_id=project_id,
                title=request.title,
                unit_kind=request.unit_kind,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Appending a unit reads the existing ordered set; unmigrated legacy
            # data blocks it. Same migration-required 503 as list/export.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _draft_payload(draft)

    @app.put(
        "/projects/{project_id}/draft-order",
        response_model=DraftOrderPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_draft_order(
        project_id: str, request: DraftOrderPutRequest
    ) -> dict[str, object]:
        try:
            drafts = core_sot.reorder_drafts(
                project_id=project_id,
                ordered_draft_ids=tuple(request.ordered_draft_ids),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, InvalidDraftOrder) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"drafts": [_draft_payload(draft) for draft in drafts]}

    @app.post(
        "/projects/{project_id}/drafts/{draft_id}/versions",
        response_model=SaveDraftResponse,
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def save_draft(
        project_id: str, draft_id: str, request: SaveDraftRequest
    ) -> dict[str, object]:
        try:
            result = core_sot.save_draft(
                project_id=project_id,
                draft_id=draft_id,
                raw_text=request.raw_text,
                idempotency_key=request.idempotency_key,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CoreSotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "draft_version": {
                "id": result.draft_version.id,
                "version_number": result.draft_version.version_number,
                "snapshot_id": result.draft_version.snapshot_id,
            },
            "snapshot": {
                "id": result.snapshot.id,
                "content_hash": result.snapshot.content_hash,
            },
            "blocks": [
                {
                    "id": block.id,
                    "kind": block.kind,
                    "start_offset": block.start_offset,
                    "end_offset": block.end_offset,
                }
                for block in result.blocks
            ],
            "idempotent_replay": result.idempotent_replay,
        }
