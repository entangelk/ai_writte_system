"""프로젝트 표면 route (``/projects*`` 11 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**인증 tier 가 두 종류 섞여 있는 유일한 라우터다** — ``POST /projects`` ·
``GET /projects`` 는 아직 대상 project 가 없으므로 **인증 전용**
(``_REQUIRE_AUTH``)이고, 나머지 9개는 **소유권**(``_REQUIRE_PROJECT_OWNER``)이다.
그 경계가 곧 D8-3 E1~E4 이며 tier 전수 가드가 둘을 갈라 센다 — 새 route 를
여기 더할 때 어느 쪽인지부터 정한다.

``_project_brief_payload`` 만 ``..api.payloads`` 에서 온다(context-search 와 공유).
``_project_payload`` 는 이 도메인 전용이라 여기 있다.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from services.application.app.core_sot.service import (
    Archived,
    DraftOrderIntegrityError,
    NotFound,
    StaleProjectBriefBase,
    UnsupportedExportFormat,
)

from ..api.models import (
    ActivityLogResponse,
    AccessLogResponse,
    CreateProjectRequest,
    ProjectBriefGetResponse,
    ProjectBriefPutResponse,
    ProjectBriefVersionListResponse,
    ProjectExportResponse,
    ProjectListResponse,
    ProjectPayload,
    PutProjectBriefRequest,
    RenameProjectRequest,
)
from ..api.errors import (
    _ERRORS_400_404_MIGRATION,
    _ERRORS_404,
    _ERRORS_404_409,
    _ERRORS_STORAGE,
    _owned,
)
from ..api.dependencies import (
    _REQUIRE_AUTH,
    _REQUIRE_PROJECT_OWNER,
    require_authenticated_user,
)
from ..api.payloads import _project_brief_payload


def register_projects(
    app, *, core_sot, access_grants, sync_outbox, activity
) -> None:
    def _project_payload(project) -> dict[str, object]:
        return {"id": project.id, "name": project.name, "archived": project.archived}

    @app.post("/projects", response_model=ProjectPayload,
              responses=_ERRORS_STORAGE,
              dependencies=_REQUIRE_AUTH)
    async def create_project(
        request: CreateProjectRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # D8-3a: the creator is no longer optional. The same dependency the
        # decorator declares is taken as a parameter here so the owner comes from
        # the value the guard already resolved — re-reading the cookie would be a
        # second, driftable answer to "who is this".
        #
        # `owner_id=None` therefore stops being reachable through this endpoint.
        # It stays deny-by-default in D8-3b anyway (E1=A): rows with no owner can
        # still arrive from a deletion bug or a future migration.
        project = core_sot.create_project(name=request.name, owner_id=current.id)
        # Phase 9 (A7=A): 결과를 안 **뒤에** 기록한다 — 위에서 예외가 났으면 여기
        # 오지 않으므로 실패한 요청이 "했다"로 남지 않는다.
        activity.record(
            project_id=project.id, actor_user_id=current.id,
            action="project_created", target_type="project", target_id=project.id,
            after=project.name,
        )
        return _project_payload(project)

    @app.get("/projects", response_model=ProjectListResponse,
             responses=_ERRORS_STORAGE,
             dependencies=_REQUIRE_AUTH)
    async def list_projects(
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        projects = core_sot.list_projects_for_owner(owner_id=current.id)
        return {"projects": [_project_payload(p) for p in projects]}

    @app.get("/projects/{project_id}/activity",
             response_model=ActivityLogResponse,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_project_activity(project_id: str) -> dict[str, object]:
        # A5=B (operation 77): 소유자가 자기 프로젝트에서 무슨 일이 있었는지 본다.
        # **소비자가 이미 정해져 있어서** 8.1~8.2c 의 "저장만 하고 소비는 다음
        # 슬라이스" 관례를 따르지 않았다(그 관례의 근거는 응답 형태를 소비자보다
        # 먼저 못박지 말라는 것이었다).
        #
        # 전역(관리자) 조회는 여기 없다 — 그것은 관리자에게 프로젝트 **내용**을
        # 여는 문이라 승격 계약(D8-5e)과 함께 볼 별도 결정이다(A5=C).
        try:
            core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"events": [
            {
                "id": event.id,
                "actor_user_id": event.actor_user_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "at": event.at,
                "before": event.before,
                "after": event.after,
            }
            for event in activity.list_for_project(project_id=project_id)
        ]}

    @app.get("/projects/{project_id}/access-log",
             response_model=AccessLogResponse,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_access_log(project_id: str) -> dict[str, object]:
        # C-4 (owner 2026-08-02): there is no notification channel, so the
        # realistic form of "the owner finds out" is that they can look. This is
        # the after-the-fact view of every request an administrator made into
        # this project under a grant — newest first, each carrying the reason
        # the grant was issued for.
        #
        # project-scoped, so the owner reads their own. An administrator holding
        # a live grant can read it too (it is a GET), which is consistent: they
        # can already read the project, and that read is itself recorded here.
        return {"entries": [
            {
                "grant_id": use.grant_id,
                "admin_user_id": use.admin_user_id,
                "method": use.method,
                "path": use.path,
                "at": use.at,
                "reason": use.reason,
            }
            for use in access_grants.uses_for_project(project_id=project_id)
        ]}

    @app.get("/projects/{project_id}", response_model=ProjectPayload,
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_project(project_id: str) -> dict[str, object]:
        try:
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _project_payload(project)

    @app.get(
        "/projects/{project_id}/brief", response_model=ProjectBriefGetResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_project_brief(project_id: str) -> dict[str, object]:
        try:
            brief = core_sot.get_project_brief(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "brief": _project_brief_payload(brief) if brief is not None else None
        }

    @app.put(
        "/projects/{project_id}/brief", response_model=ProjectBriefPutResponse,
        responses=_owned(_ERRORS_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def put_project_brief(
        project_id: str, request: PutProjectBriefRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            result = core_sot.put_project_brief(
                project_id=project_id,
                base_version_id=request.base_version_id,
                idempotency_key=request.idempotency_key,
                premise=request.premise,
                genre=request.genre,
                tone=request.tone,
                pov=request.pov,
                constraints=tuple(request.constraints),
                style_rules=tuple(request.style_rules),
                preferred_patterns=tuple(request.preferred_patterns),
                forbidden_patterns=tuple(request.forbidden_patterns),
                style_examples=tuple(request.style_examples),
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (Archived, StaleProjectBriefBase) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project_id, actor_user_id=current.id,
            action="project_brief_saved", target_type="project_brief",
            target_id=result.brief.id,
        )
        return {
            "brief": _project_brief_payload(result.brief),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.get(
        "/projects/{project_id}/brief/versions",
        response_model=ProjectBriefVersionListResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def list_project_brief_versions(project_id: str) -> dict[str, object]:
        try:
            versions = core_sot.list_project_brief_versions(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"versions": [_project_brief_payload(brief) for brief in versions]}

    @app.get(
        "/projects/{project_id}/brief/versions/{version_id}",
        response_model=ProjectBriefGetResponse,
        responses=_owned(_ERRORS_404),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def get_project_brief_version(
        project_id: str, version_id: str
    ) -> dict[str, object]:
        try:
            brief = core_sot.get_project_brief_version(
                project_id=project_id, version_id=version_id
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"brief": _project_brief_payload(brief)}

    @app.patch("/projects/{project_id}", response_model=ProjectPayload,
               responses=_owned(_ERRORS_404_409),
               dependencies=_REQUIRE_PROJECT_OWNER)
    async def rename_project(
        project_id: str, request: RenameProjectRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # A3=B 의 대표 자리 — 개명은 덮어쓰기라 지금까지 흔적이 **전혀** 없었다.
        # 옛 이름은 바꾸기 전에 읽어야 한다.
        try:
            previous = core_sot.get_project(project_id=project_id).name
        except NotFound:
            previous = None
        try:
            project = core_sot.rename_project(
                project_id=project_id, name=request.name
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Archived as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        activity.record(
            project_id=project.id, actor_user_id=current.id,
            action="project_renamed", target_type="project", target_id=project.id,
            before=previous, after=project.name,
        )
        return _project_payload(project)

    @app.delete("/projects/{project_id}", response_model=ProjectPayload,
                responses=_owned(_ERRORS_404),
                dependencies=_REQUIRE_PROJECT_OWNER)
    async def archive_project(
        project_id: str, current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # MVP: delete is archive (soft delete); SOT data is preserved (§115).
        # Re-archiving is idempotent.
        try:
            project = core_sot.archive_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        sync_outbox.enqueue_project_archived(project_id=project_id)
        activity.record(
            project_id=project.id, actor_user_id=current.id,
            action="project_archived", target_type="project", target_id=project.id,
            before="active", after="archived",
        )
        return _project_payload(project)

    @app.get(
        "/projects/{project_id}/export",
        response_model=ProjectExportResponse,
        responses=_owned(_ERRORS_400_404_MIGRATION),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def export_project(
        project_id: str,
        format: str = Query("txt"),
        manifest: bool = Query(False),
        include_archived: bool = Query(False),
    ) -> dict[str, object]:
        try:
            export = core_sot.export_project(
                project_id=project_id,
                fmt=format,
                include_archived=include_archived,
            )
        except UnsupportedExportFormat as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DraftOrderIntegrityError as exc:
            # Whole-project export reads the ordered unit set; unmigrated legacy
            # data blocks it. Same migration-required 503 as list/create.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        manifest_payload: dict[str, object] | None = None
        if manifest:
            manifest_payload = {
                "project_id": export.project_id,
                "format": export.format,
                "include_archived": export.include_archived,
                "units": [
                    {
                        "draft_id": unit.draft_id,
                        "title": unit.title,
                        "unit_kind": unit.unit_kind,
                        "position": unit.position,
                        "version_id": unit.version_id,
                        "version_number": unit.version_number,
                        "snapshot_id": unit.snapshot_id,
                        "content_hash": unit.content_hash,
                    }
                    for unit in export.units
                ],
            }
        return {
            "format": export.format,
            "filename": export.filename,
            "content_type": export.content_type,
            "body": export.body,
            "project_id": export.project_id,
            "include_archived": export.include_archived,
            "manifest": manifest_payload,
        }
