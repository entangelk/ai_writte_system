"""장면 메모 읽기 표면 (``/projects/{id}/notes`` · ``/…/drafts/{id}/note``, 2 operation).

장면 메모 Slice 1(결정 브리프 D1=C+A·D3=A). **읽기 전용**이다 — `PUT` 과 활동 기록은
Slice 2 다. 그래서 이 모듈에는 `activity` 협력자가 없다.

인가는 새로 만들지 않는다. ``_REQUIRE_PROJECT_OWNER`` 가 소유자와 **유효한 access
grant 를 가진 관리자의 GET** 을 함께 통과시키고, grant 사용 기록(access-log)은 그
dependency 한 곳(choke point)에서 남는다 — 여기서 다시 기록하면 두 벌이 된다.

미리보기는 **검색과 연계**한다(오너 2026-08-31): query 가 있으면 매치를 중심에 둔
스니펫, 없으면 머리 200자다. 12000자 메모에서 8000번째 글자가 매치됐을 때 머리 200자는
"왜 이 메모가 나왔는지"를 전혀 보여주지 못한다.
"""

from __future__ import annotations

from fastapi import HTTPException, Query

from services.application.app.core_sot.service import (
    DraftOrderIntegrityError,
    NotFound,
)

from ..api.models import (
    SceneNoteListResponse,
    SceneNotePayload,
)
from ..api.errors import _ERRORS_404, _ERRORS_404_MIGRATION, _owned
from ..api.dependencies import _REQUIRE_PROJECT_OWNER

#: 목록 미리보기 길이. 활동 로그의 "짧은 값" 상한(`ACTIVITY_VALUE_MAX_CHARS`)과 같은
#: 값이다 — 같은 성격(목록에 싣는 텍스트 조각)에 두 번째 숫자를 만들지 않는다.
SCENE_NOTE_PREVIEW_MAX_CHARS = 200

#: 스니펫이 본문 중간에서 잘렸음을 나타내는 표식.
_ELLIPSIS = "…"


def build_note_preview(body: str, query: str | None) -> tuple[str, bool]:
    """``(preview, truncated)`` — 검색어가 있으면 매치를 중심에 둔다.

    query 가 없거나 본문에서 안 잡히면 머리 200자다(제목만 매치된 행이 그렇다).
    잡히면 매치 앞뒤로 남는 예산을 반씩 나눠 창을 잡고, 잘린 쪽에만 `…` 를 붙인다.
    ``truncated`` 는 **본문이 미리보기보다 길다**는 뜻이지 창의 위치와는 무관하다.
    """

    if len(body) <= SCENE_NOTE_PREVIEW_MAX_CHARS:
        return body, False

    start = 0
    if query:
        found = body.casefold().find(query.strip().casefold())
        if found != -1:
            # 매치를 창 가운데에 둔다. 본문 끝에 가까우면 창을 왼쪽으로 민다 —
            # 그러지 않으면 예산의 절반이 빈 채로 낭비된다.
            start = max(0, found - (SCENE_NOTE_PREVIEW_MAX_CHARS // 2))
            start = min(start, len(body) - SCENE_NOTE_PREVIEW_MAX_CHARS)

    window = body[start:start + SCENE_NOTE_PREVIEW_MAX_CHARS]
    prefix = _ELLIPSIS if start > 0 else ""
    suffix = (
        _ELLIPSIS
        if start + SCENE_NOTE_PREVIEW_MAX_CHARS < len(body)
        else ""
    )
    return f"{prefix}{window}{suffix}", True


def register_notes(app, *, core_sot) -> None:
    @app.get(
        "/projects/{project_id}/notes",
        response_model=SceneNoteListResponse,
        responses=_owned(_ERRORS_404_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_scene_notes(
        project_id: str, query: str | None = Query(None),
    ) -> dict[str, object]:
        try:
            items = core_sot.list_scene_notes(
                project_id=project_id, query=query
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # 목록 순서를 list_drafts 에서 가져오므로 그 503 얼굴도 함께 온다
            # (평면 legacy 데이터의 처방은 재시도가 아니라 migration 이다).
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        preview_and_flag = [
            build_note_preview(item.note.body, query) for item in items
        ]
        return {"notes": [
            {
                "draft_id": item.scene.id,
                "scene_title": item.scene.title,
                "scene_archived": item.scene.archived,
                "chapter_id": item.chapter.id,
                "chapter_title": item.chapter.title,
                "chapter_archived": item.chapter.archived,
                "body_preview": preview,
                "truncated": truncated,
                "updated_at": item.note.updated_at,
            }
            for item, (preview, truncated) in zip(items, preview_and_flag)
        ]}

    @app.get(
        "/projects/{project_id}/drafts/{draft_id}/note",
        response_model=SceneNotePayload,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_scene_note(
        project_id: str, draft_id: str
    ) -> dict[str, object]:
        try:
            note = core_sot.get_scene_note(
                project_id=project_id, draft_id=draft_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # 메모가 없는 장면은 404 가 아니다 — body=None 이 "아직 없음"이다.
        return {
            "draft_id": draft_id,
            "body": None if note is None else note.body,
            "updated_at": None if note is None else note.updated_at,
        }
