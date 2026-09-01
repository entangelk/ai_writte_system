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

from fastapi import Depends, HTTPException, Query

from services.application.app.core_sot.service import (
    AlreadyFinalized,
    Archived,
    CoreSotError,
    DraftOrderIntegrityError,
    InvalidDraftOrder,
    NotFound,
    UnsupportedExportFormat,
)
from services.application.app.writing.generation_job import (
    WritingGenerationJobStatus,
)

from ..api.models import (
    ChapterListResponse,
    ChapterOrderPutRequest,
    ChapterOrderPutResponse,
    ChapterPayload,
    CreateChapterRequest,
    CreateDraftRequest,
    DraftListResponse,
    DraftPayload,
    DraftVersionDetailResponse,
    DraftVersionExportResponse,
    DraftVersionListResponse,
    FinalizeDraftResponse,
    RenameDraftRequest,
    SaveDraftRequest,
    SaveDraftResponse,
    SceneOrderPutRequest,
    SceneOrderPutResponse,
    ScenePayload,
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
from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER,
    _REQUIRE_PROJECT_OWNER_BILLABLE,
    require_authenticated_user,
)


def register_drafts(
    app, *, core_sot, sync_outbox, activity, writing_generation_jobs, writing_scratch,
    analysis, runner, llm_call_audit,
) -> None:
    def _require_migrated_scene(draft) -> None:
        try:
            chapter_ids = {
                chapter.id for chapter in core_sot.list_chapters(
                    project_id=draft.project_id
                )
            }
        except DraftOrderIntegrityError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if (
            draft.chapter_id not in chapter_ids
            or draft.position is None
            or draft.unit_kind is not None
        ):
            raise HTTPException(
                status_code=503,
                detail="scene hierarchy migration is required",
            )

    def _draft_payload(draft) -> dict[str, object]:
        _require_migrated_scene(draft)
        versions = core_sot.list_draft_versions(
            project_id=draft.project_id, draft_id=draft.id
        )
        latest = max(versions, key=lambda value: value.version_number, default=None)
        job = None if latest is None else analysis.get_job_request(
            project_id=draft.project_id, snapshot_id=latest.snapshot_id,
            idempotency_key=f"analyze:{latest.snapshot_id}",
        )
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "chapter_id": draft.chapter_id,
            "title": draft.title,
            "archived": draft.archived,
            "position": draft.position,
            "finalized_snapshot_id": draft.finalized_snapshot_id,
            "finalized_at": draft.finalized_at,
            "analysis_status": None if job is None else str(job.status),
            "analysis_snapshot_id": None if job is None else job.snapshot_id,
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

    def _scene_payload(draft) -> dict[str, object]:
        assert draft.chapter_id is not None
        assert draft.position is not None
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "chapter_id": draft.chapter_id,
            "title": draft.title,
            "archived": draft.archived,
            "position": draft.position,
        }

    def _chapter_payload(chapter) -> dict[str, object]:
        scenes = core_sot.list_scenes(
            project_id=chapter.project_id, chapter_id=chapter.id
        )
        return {
            "id": chapter.id,
            "project_id": chapter.project_id,
            "title": chapter.title,
            "archived": chapter.archived,
            "position": chapter.position,
            "scenes": [_scene_payload(scene) for scene in scenes],
        }

    @app.get(
        "/projects/{project_id}/chapters",
        response_model=ChapterListResponse,
        responses=_owned(_ERRORS_404_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_chapters(project_id: str) -> dict[str, object]:
        try:
            chapters = core_sot.list_chapters(project_id=project_id)
            return {"chapters": [_chapter_payload(chapter) for chapter in chapters]}
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(
        "/projects/{project_id}/chapters",
        response_model=ChapterPayload,
        responses=_owned(_ERRORS_404_409_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def create_chapter(
        project_id: str,
        request: CreateChapterRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            chapter = core_sot.create_chapter(
                project_id=project_id, title=request.title
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id,
            actor_user_id=current.id,
            action="chapter_created",
            target_type="chapter",
            target_id=chapter.id,
            after=chapter.title,
        )
        return _chapter_payload(chapter)

    @app.post(
        "/projects/{project_id}/chapters/{chapter_id}/archive",
        response_model=ChapterPayload,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def archive_chapter(
        project_id: str,
        chapter_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            scenes = core_sot.list_scenes(
                project_id=project_id, chapter_id=chapter_id
            )
            chapter = core_sot.archive_chapter(
                project_id=project_id, chapter_id=chapter_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        for scene in scenes:
            sync_outbox.enqueue_draft_archived(
                project_id=project_id, draft_id=scene.id
            )
        activity.record(
            project_id=project_id,
            actor_user_id=current.id,
            action="chapter_archived",
            target_type="chapter",
            target_id=chapter.id,
            before="active",
            after="archived",
        )
        return _chapter_payload(chapter)

    @app.post(
        "/projects/{project_id}/chapters/{chapter_id}/purge",
        status_code=204,
        response_model=None,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def purge_chapter(
        project_id: str,
        chapter_id: str,
        current=Depends(require_authenticated_user),
    ) -> None:
        try:
            chapters = core_sot.list_chapters(project_id=project_id)
            chapter = next(
                item for item in chapters if item.id == chapter_id
            )
            scenes = core_sot.list_scenes(
                project_id=project_id, chapter_id=chapter_id
            )
        except StopIteration as exc:
            raise HTTPException(status_code=404, detail="chapter not found") from exc
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not chapter.archived:
            raise HTTPException(
                status_code=409, detail="chapter must be archived before purge"
            )
        if any(
            job.status in (
                WritingGenerationJobStatus.PENDING,
                WritingGenerationJobStatus.RUNNING,
            )
            for scene in scenes
            for job in writing_generation_jobs.list_for_draft(
                project_id, scene.id
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="chapter has a scene with an active generation job; "
                       "wait or discard it",
            )
        for scene in scenes:
            writing_scratch.clear_draft(project_id, scene.id)
            writing_generation_jobs.purge_draft(
                project_id=project_id, draft_id=scene.id
            )
        core_sot.purge_chapter(project_id=project_id, chapter_id=chapter_id)
        activity.record(
            project_id=project_id,
            actor_user_id=current.id,
            action="chapter_purged",
            target_type="chapter",
            target_id=chapter_id,
            before="archived",
            after="purged",
        )

    @app.put(
        "/projects/{project_id}/chapter-order",
        response_model=ChapterOrderPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_chapter_order(
        project_id: str,
        request: ChapterOrderPutRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            chapters = core_sot.reorder_chapters(
                project_id=project_id,
                ordered_chapter_ids=tuple(request.ordered_chapter_ids),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, InvalidDraftOrder) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id,
            actor_user_id=current.id,
            action="chapter_order_changed",
            target_type="project",
            target_id=project_id,
        )
        return {"chapters": [_chapter_payload(chapter) for chapter in chapters]}

    @app.put(
        "/projects/{project_id}/chapters/{chapter_id}/scene-order",
        response_model=SceneOrderPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_scene_order(
        project_id: str,
        chapter_id: str,
        request: SceneOrderPutRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            scenes = core_sot.reorder_scenes(
                project_id=project_id,
                chapter_id=chapter_id,
                ordered_draft_ids=tuple(request.ordered_draft_ids),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, InvalidDraftOrder) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id,
            actor_user_id=current.id,
            action="scene_order_changed",
            target_type="chapter",
            target_id=chapter_id,
        )
        return {"scenes": [_scene_payload(scene) for scene in scenes]}

    @app.patch(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404_409_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def rename_draft(
        project_id: str, draft_id: str, request: RenameDraftRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # 옛 제목은 바꾸기 전에 읽는다(A3=B).
        try:
            previous_draft = core_sot.get_draft(
                project_id=project_id, draft_id=draft_id
            )
            _require_migrated_scene(previous_draft)
            previous = previous_draft.title
        except NotFound:
            previous = None
        try:
            draft = core_sot.rename_draft(
                project_id=project_id, draft_id=draft_id, title=request.title
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_renamed", target_type="draft", target_id=draft.id,
            before=previous, after=draft.title,
        )
        return _draft_payload(draft)

    @app.delete(
        "/projects/{project_id}/drafts/{draft_id}", response_model=DraftPayload,
        responses=_owned(_ERRORS_404_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def archive_draft(
        project_id: str, draft_id: str,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_migrated_scene(core_sot.get_draft(
                project_id=project_id, draft_id=draft_id
            ))
            draft = core_sot.archive_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        sync_outbox.enqueue_draft_archived(
            project_id=project_id,
            draft_id=draft_id,
        )
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_archived", target_type="draft", target_id=draft.id,
            before="active", after="archived",
        )
        return _draft_payload(draft)

    @app.post(
        "/projects/{project_id}/drafts/{draft_id}/purge", status_code=204,
        response_model=None, responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def purge_draft(
        project_id: str, draft_id: str,
        current=Depends(require_authenticated_user),
    ) -> None:
        # 원고 하드 삭제(2026-08-28 오너 결정). 아카이브를 선행 요구하는 것은
        # 프로젝트 purge 와 같은 이유다 — 색인 제거(DRAFT_ARCHIVED outbox → chroma
        # 파기)가 먼저 확정된 뒤 본체를 지운다. 활동 행은 append-only 원장이라
        # 남는다(프로젝트 purge 때만 지워진다).
        try:
            draft = core_sot.get_draft(project_id=project_id, draft_id=draft_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not draft.archived:
            raise HTTPException(
                status_code=409, detail="draft must be archived before purge",
            )
        # active 생성 잡이 붙어 있으면 거부(오너 2026-08-28) — 잡의 결과물은 draft
        # 에 표시되므로 앵커가 사라진 잡은 완료돼도 갈 곳이 없다.
        if any(
            job.status in (
                WritingGenerationJobStatus.PENDING,
                WritingGenerationJobStatus.RUNNING,
            )
            for job in writing_generation_jobs.list_for_draft(
                project_id, draft_id,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="draft has an active generation job; wait or discard it",
            )
        # scratch(재생성 무해한 파생물)를 core 파기 **앞에** 둔다(검증 H1, 2026-08-28).
        # core(비가역)를 먼저 지우고 scratch 삭제가 실패하면 원고 없이 500만 남지만,
        # 이 순서면 scratch 단계 실패 시 원고가 그대로 남아 재시도로 수습된다.
        writing_scratch.clear_draft(project_id, draft_id)
        writing_generation_jobs.purge_draft(
            project_id=project_id, draft_id=draft_id
        )
        core_sot.purge_draft(project_id=project_id, draft_id=draft_id)
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_purged", target_type="draft", target_id=draft_id,
            before="archived", after="purged",
        )

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
        responses=_owned(_ERRORS_404_MIGRATION),
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

    @app.post(
              "/projects/{project_id}/drafts",
              response_model=DraftPayload,
              responses=_owned(_ERRORS_404_409_MIGRATION),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def create_draft(
        project_id: str, request: CreateDraftRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            draft = core_sot.create_scene(
                project_id=project_id,
                chapter_id=request.chapter_id,
                title=request.title,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Appending a unit reads the existing ordered set; unmigrated legacy
            # data blocks it. Same migration-required 503 as list/export.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_created", target_type="draft", target_id=draft.id,
            after=draft.title,
        )
        return _draft_payload(draft)

    @app.post(
        "/projects/{project_id}/drafts/{draft_id}/versions",
        response_model=SaveDraftResponse,
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def save_draft(
        project_id: str, draft_id: str, request: SaveDraftRequest,
        current=Depends(require_authenticated_user),
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
        # 이 행이 부모 계획 §1 의 공백을 닫는다 — `draft_versions` 에는
        # `created_at` 도 `user_id` 도 없어서 "누가 언제 저장했나"에 답할 수 없었다.
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_version_saved", target_type="draft_version",
            target_id=result.draft_version.id,
            after=str(result.draft_version.version_number),
        )
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

    @app.post(
        "/projects/{project_id}/drafts/{draft_id}/finalize",
        response_model=FinalizeDraftResponse,
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE,
    )
    async def finalize_draft(
        project_id: str, draft_id: str, request: SaveDraftRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            finalized = core_sot.finalize_draft(
                project_id=project_id, draft_id=draft_id,
                raw_text=request.raw_text, idempotency_key=request.idempotency_key,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, AlreadyFinalized) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CoreSotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        saved = finalized.saved
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="draft_finalized", target_type="draft_version",
            target_id=saved.draft_version.id,
            after=str(saved.draft_version.version_number),
        )
        analysis_error = None
        job = None
        try:
            # Analysis candidates must carry source anchors. The manual trigger
            # prepares the same full-block catalog in the browser; finalization
            # owns that preparation server-side so an interrupted browser cannot
            # strand its promised analysis.
            covered = {
                (ref.start_offset, ref.end_offset)
                for ref in core_sot.list_source_refs(
                    project_id=project_id, snapshot_id=saved.snapshot.id
                )
            }
            for block in saved.blocks:
                span = (block.start_offset, block.end_offset)
                if span[0] < span[1] and span not in covered:
                    core_sot.create_source_ref(
                        project_id=project_id, snapshot_id=saved.snapshot.id,
                        start_offset=span[0], end_offset=span[1],
                    )
            existing = analysis.get_job_request(
                project_id=project_id, snapshot_id=saved.snapshot.id,
                idempotency_key=f"analyze:{saved.snapshot.id}",
            )
            job = existing or analysis.create_job(
                project_id=project_id, snapshot_id=saved.snapshot.id,
                idempotency_key=f"analyze:{saved.snapshot.id}",
            ).job
            if not finalized.idempotent_replay and runner is not None:
                from services.application.app.observability.llm_call_scope import llm_call_scope
                with llm_call_scope(llm_call_audit, project_id=project_id,
                                    correlation_id=job.id):
                    job = (await runner.run_job(project_id=project_id, job_id=job.id)).job
        except Exception as exc:
            analysis_error = str(exc)
        return {
            "draft_version": {"id": saved.draft_version.id,
                              "version_number": saved.draft_version.version_number,
                              "snapshot_id": saved.snapshot.id},
            "snapshot": {"id": saved.snapshot.id,
                         "content_hash": saved.snapshot.content_hash},
            "analysis_job": None if job is None else {
                "id": job.id, "project_id": job.project_id,
                "snapshot_id": job.snapshot_id, "status": str(job.status),
                "failure_reason": (str(job.failure_reason)
                                   if job.failure_reason is not None else None),
                "failure_detail": job.failure_detail,
            },
            "analysis_error": analysis_error,
            "idempotent_replay": finalized.idempotent_replay,
        }
