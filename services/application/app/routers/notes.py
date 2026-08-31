"""장면 메모 표면 (``/projects/{id}/notes`` · ``/…/drafts/{id}/note``, 3 operation).

장면 메모 Slice 1(읽기 2)과 Slice 2(쓰기 1). 결정 브리프 D1=C+A·D3=A·D4=A.

인가는 새로 만들지 않는다. ``_REQUIRE_PROJECT_OWNER`` 가 소유자와 **유효한 access
grant 를 가진 관리자의 GET** 을 함께 통과시키고, grant 사용 기록(access-log)은 그
dependency 한 곳(choke point)에서 남는다 — 여기서 다시 기록하면 두 벌이 된다.
**쓰기는 그 dependency 가 자동으로 소유자에게만 연다**(``_GRANTED_METHODS`` 가
GET/HEAD 뿐이라 grant 로는 PUT 이 403 이다) — D3=A 를 위한 새 검사가 필요 없다.

미리보기는 **검색과 연계**한다(오너 2026-08-31): query 가 있으면 매치를 중심에 둔
스니펫, 없으면 머리 200자다. 12000자 메모에서 8000번째 글자가 매치됐을 때 머리 200자는
"왜 이 메모가 나왔는지"를 전혀 보여주지 못한다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException, Query

from services.application.app.core_sot.models import SceneNote
from services.application.app.core_sot.service import (
    Archived,
    DraftOrderIntegrityError,
    NotFound,
)

from ..api.models import (
    PutSceneNoteRequest,
    SceneNoteListResponse,
    SceneNotePayload,
)
from ..api.errors import (
    _ERRORS_404,
    _ERRORS_404_409,
    _ERRORS_404_MIGRATION,
    _owned,
)
from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER,
    require_authenticated_user,
)

#: 목록 미리보기 길이. 활동 로그의 "짧은 값" 상한(`ACTIVITY_VALUE_MAX_CHARS`)과 같은
#: 값이다 — 같은 성격(목록에 싣는 텍스트 조각)에 두 번째 숫자를 만들지 않는다.
SCENE_NOTE_PREVIEW_MAX_CHARS = 200

#: 스니펫이 본문 중간에서 잘렸음을 나타내는 표식.
_ELLIPSIS = "…"

#: 저장 버튼 연타를 **활동 로그에서만** 접는 창 (오너 결정 2026-08-31).
#:
#: 오너는 "같은 값을 다시 저장해도 행을 남긴다"와 "저장 버튼 여러 번 누르는 건 막는다"를
#: 함께 골랐다. 그 둘을 가르는 축은 **값이 아니라 시간**이다 — 같은 본문을 나중에 다시
#: 저장하는 것은 사용자의 두 번째 저장 행위지만, 응답이 오기 전의 재클릭은 한 번의 행위다.
#: 그래서 억제 조건은 **직전 저장과 본문이 같고 그 저장으로부터 이 창 안**일 때뿐이다.
#:
#: ★ ``quota/lock.py`` 의 ``DEFAULT_MINIMUM_WINDOW_SECONDS`` 와 값이 같지만 **다른
#: 상수다**. 그쪽은 과금되는 동기 AI 요청의 냉각 창(제품 정책)이고 여기는 무료 저장의
#: 활동 행 접기다 — 합치면 quota 정책을 손볼 때 메모 타임라인이 조용히 따라 바뀐다.
#:
#: 억제되는 것은 **활동 행뿐이다**. 저장 자체는 언제나 일어나고 응답도 항상 200 이다.
SCENE_NOTE_DOUBLE_SUBMIT_WINDOW = timedelta(seconds=5)


def _is_double_submit(previous: SceneNote | None, saved: SceneNote) -> bool:
    """직전 저장의 재전송인가 — 값이 같고 창 안이면 참."""

    return (
        previous is not None
        and previous.body == saved.body
        and saved.updated_at - previous.updated_at < SCENE_NOTE_DOUBLE_SUBMIT_WINDOW
    )


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


def register_notes(app, *, core_sot, activity) -> None:
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

    # ★ 이 PUT 은 두 GET **뒤**에 등재한다. 합집합 앱의 route 순서가 OpenAPI `paths`
    # 순서이고 그것이 프론트 `schema.d.ts` 의 입력이라, 앞에 끼우면 기존 두 operation
    # 의 자리가 밀린다(HANDOFF "지금 상태" ③).
    @app.put(
        "/projects/{project_id}/drafts/{draft_id}/note",
        response_model=SceneNotePayload,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_scene_note(
        project_id: str, draft_id: str, request: PutSceneNoteRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # 응답 모델은 단건 GET 과 같은 것을 쓴다. 저장 결과는 그 장면의 현재 메모
        # 그대로라 두 번째 모양을 만들 이유가 없다(`body` 가 여기서는 절대 null 이
        # 아니라는 것만 다르고, 그 사실은 계약이 아니라 이 경로의 성질이다).
        try:
            # 연타 판정에 직전 값이 필요하다. 이 읽기는 쓰기 경계 검사를 하지 않으므로
            # 아래 put_scene_note 가 archived 를 잡는 순서는 그대로다.
            previous = core_sot.get_scene_note(
                project_id=project_id, draft_id=draft_id
            )
            note = core_sot.put_scene_note(
                project_id=project_id, draft_id=draft_id, body=request.body,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not _is_double_submit(previous, note):
            # 성공 뒤에만 남긴다(D4=A). before/after 는 비운다 — A3=B 가 담는 것은
            # 짧은 **라벨**이고 메모 본문(최대 12000자)은 그 자리가 아니다.
            activity.record(
                project_id=project_id, actor_user_id=current.id,
                action="scene_note_saved", target_type="scene_note",
                target_id=draft_id,
            )
        return {
            "draft_id": draft_id,
            "body": note.body,
            "updated_at": note.updated_at,
        }
