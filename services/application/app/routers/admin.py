"""관리자 표면 route (``/admin/*`` 8 operation, D8-5·D8-6).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다. 이 모듈은 **Slice 2(관리자 주소 분리)** 의 재료가 된다 —
``create_admin_app()`` 가 이 ``register_admin`` 만 호출하는 별도 앱을 올리면
product 앱에는 ``/admin`` 라우트가 남지 않는다(A1=ⓑ).

14개 서비스를 명시 인자로 받는다(purge 핸들러가 파괴 그래프 전체를 쓴다).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, HTTPException

from services.application.app.auth.users import (
    DuplicateUsername,
    InvalidUserInput,
    LastActiveAdmin,
    UserNotFound,
)

from ..api.models import (
    AccessGrantCreateRequest,
    AccessGrantCreateResponse,
    AdminAuditEventListResponse,
    AdminObservabilityKpiResponse,
    AdminProjectListResponse,
    AdminUserListResponse,
    AdminUserPayload,
    CreateUserRequest,
    PurgeProjectRequest,
)
from ..api.errors import (
    _ERRORS_ADMIN,
    _ERRORS_ADMIN_400_409,
    _ERRORS_ADMIN_404,
    _ERRORS_ADMIN_404_409,
    _STORAGE_ERRORS,
)
from ..api.dependencies import (
    _REQUIRE_ADMIN,
    require_admin_user,
)
from services.application.app.auth.admin_audit import AdminAuditEvent
from services.application.app.core_sot.service import NotFound
from services.application.app.observability.kpi import aggregate_global_kpi


def register_admin(
    app,
    *,
    users,
    core_sot,
    access_grants,
    admin_audit,
    llm_call_audit,
    writing_loop_audit,
    memory,
    analysis,
    review_queue,
    gate_findings,
    writing_generation_jobs,
    writing_scratch,
    sync_outbox,
    project_name_history,
) -> None:
    # --- Admin (D8-5, D6=A minimal admin) ---------------------------------
    # Users only: the all-projects list and the global KPI are their own slices,
    # and project *content* stays behind the ownership boundary — an admin
    # reaches another user's project only through the audited, expiring grant
    # the owner chose in F1=C, which is a later slice too.

    def _admin_user_payload(user) -> dict[str, object]:
        return {
            "id": user.id, "username": user.username,
            "is_admin": user.is_admin, "is_active": user.is_active,
        }

    @app.get("/admin/users", response_model=AdminUserListResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def list_users() -> dict[str, object]:
        return {"users": [_admin_user_payload(u) for u in users.list_users()]}

    @app.post("/admin/users", response_model=AdminUserPayload,
              responses=_ERRORS_ADMIN_400_409, dependencies=_REQUIRE_ADMIN)
    async def create_user(request: CreateUserRequest) -> dict[str, object]:
        try:
            user = users.create_user(
                # C-6: an administrator is choosing a password for someone else,
                # so it is single-use — the account replaces it at first sign-in.
                must_change_password=True,
                username=request.username,
                password=request.password,
                is_admin=request.is_admin,
            )
        except DuplicateUsername as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidUserInput as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _admin_user_payload(user)

    @app.post("/admin/users/{user_id}/deactivate",
              response_model=AdminUserPayload,
              responses=_ERRORS_ADMIN_404_409, dependencies=_REQUIRE_ADMIN)
    async def deactivate_user(user_id: str) -> dict[str, object]:
        try:
            user = users.deactivate_user(user_id)
        except UserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LastActiveAdmin as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _admin_user_payload(user)

    @app.get("/admin/observability/kpi",
             response_model=AdminObservabilityKpiResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def admin_observability_kpi_endpoint() -> dict[str, object]:
        # D8-5c: the deployment-wide read-out. Pure aggregation, like its
        # per-project sibling — no provider call, no scope. No 404: unlike the
        # project route there is nothing to look up, and no 403 for ownership
        # either, because it reads counts rather than any project's content.
        kpi = aggregate_global_kpi(
            calls=llm_call_audit.list_all_calls(),
            loop_runs=writing_loop_audit.list_all_runs(),
        )
        return {
            "projects_considered": kpi.projects_considered,
            "totals": asdict(kpi.totals),
            "sites": [asdict(site) for site in kpi.sites],
            "gate": asdict(kpi.gate),
            "loop": asdict(kpi.loop),
        }

    def _admin_audit_payload(event: AdminAuditEvent) -> dict[str, object]:
        return {
            "id": event.id,
            "operation_id": event.operation_id,
            "admin_user_id": event.admin_user_id,
            "action": event.action,
            "target_type": event.target_type,
            "target_project_id": event.target_project_id,
            "reason": event.reason,
            "outcome": event.outcome,
            "at": event.at,
            "error_kind": event.error_kind,
        }

    @app.get("/admin/audit-events", response_model=AdminAuditEventListResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def list_admin_audit_events() -> dict[str, object]:
        return {"events": [
            _admin_audit_payload(event)
            for event in admin_audit.list_project_purge_events()
        ]}

    @app.get("/admin/projects", response_model=AdminProjectListResponse,
             responses=_ERRORS_ADMIN, dependencies=_REQUIRE_ADMIN)
    async def list_all_projects() -> dict[str, object]:
        # D8-5b (F1=C): every project, whoever owns it — id·name·archived·owner.
        # **Metadata only.** This is the one admin surface that names projects it
        # does not own, so the boundary matters: it lists *that* they exist and
        # who owns them, and nothing from inside them. Reading a project's
        # contents still requires the audited, expiring grant of D8-5e.
        #
        # `owner_id` is returned raw rather than resolved to a username: the
        # admin console already lists users (`GET /admin/users`), so joining here
        # would add an N+1 to serve a name the caller can already map.
        #
        # Archived projects are included — an administrator asking "what exists"
        # wants the archived ones too (they are soft-deleted, not gone), and the
        # flag lets the caller decide.
        return {"projects": [
            {
                "id": p.id, "name": p.name, "archived": p.archived,
                "owner_id": p.owner_id,
            }
            for p in core_sot.list_projects()
        ]}

    @app.post("/admin/projects/{project_id}/access-grants",
              response_model=AccessGrantCreateResponse, status_code=201,
              responses=_ERRORS_ADMIN_404, dependencies=_REQUIRE_ADMIN)
    async def issue_access_grant(
        project_id: str, request: AccessGrantCreateRequest,
        current=Depends(require_admin_user),
    ) -> dict[str, object]:
        # D8-5e (F1=C, owner 2026-08-02). Ownership refuses administrators too;
        # this is the audited, expiring way past it. It sits in the ADMIN tier
        # for the same reason purge does — the path names a project but the
        # check is "are you an administrator", not "do you own this".
        #
        # 404 before issuing: a grant to a project that does not exist would be
        # an audit record about nothing, and it would let an administrator probe
        # for project ids through a 201.
        try:
            core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        grant = access_grants.issue(
            admin_user_id=current.id,
            project_id=project_id,
            reason=request.reason,
        )
        return {"grant": {
            "id": grant.id,
            "project_id": grant.project_id,
            "admin_user_id": grant.admin_user_id,
            "reason": grant.reason,
            "created_at": grant.created_at,
            "expires_at": grant.expires_at,
        }}

    @app.post("/admin/projects/{project_id}/purge", status_code=204,
              response_model=None, responses=_ERRORS_ADMIN_404_409,
              dependencies=_REQUIRE_ADMIN)
    async def purge_project(
        project_id: str, request: PurgeProjectRequest,
        current=Depends(require_admin_user),
    ) -> None:
        # D8-6d: 영구 파기(불가역). archive(soft)와 달리 18컬렉션을 hard delete 하고
        # indexing outbox 로 worker 가 vector/index 5백엔드를 파기(6c _drain_purge).
        # D5 전체 그래프 파기. 응답은 204(리소스 소멸). 2단계 삭제는 UI 관례가
        # 아니라 여기서 강제한다: active project 는 먼저 archive해야 하며 아니면 409.
        #
        # ★ 알려진 한계 — **재시도는 멱등이 아니다**(2026-08-02 정정. v1.7.74 는 이 자리에
        # "클라이언트 재시도(멱등)"라고 적었으나 거짓이었다). core_sot 이 **먼저** 지워지므로,
        # 아래 derived 단계에서 mongo 장애가 나 전역 handler 가 503 을 내면 **수습할 방법이
        # 없다**: 재시도는 core_sot 이 비어 404 로 끝나고 derived 에 도달하지 못한다. 남는
        # derived 는 무해하지 않다 — llm_call_audits 에 프롬프트 본문이, scratch 에 원고
        # 후보가 남는다(D5 부분 삭제 금지 위반). **수습은 `scripts/purge_reconciler.py`**
        # 가 한다(projects 에 없는 project_id 의 잔류를 찾아 파기 + PROJECT_PURGED enqueue).
        # D4=A(오너 2026-08-02)로 현행 순서+reconciler를 유지한다. 장래 D4-D
        # operation journal/saga는 원격 저장소·다중 worker에서 수동 수습이 실제
        # 부담이 될 때 연다.
        # 한계 자체는 AdminProjectPurgeTest 의
        # test_a_second_purge_is_404_and_never_reaches_the_derived_services 가 잠근다.
        try:
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not project.archived:
            raise HTTPException(
                status_code=409, detail="project must be archived before purge"
            )

        # D3/D5=A. This first write is fail-closed: without it the destructive
        # action does not begin. It intentionally survives the project graph.
        requested = admin_audit.record_purge_requested(
            admin_user_id=current.id,
            target_project_id=project_id,
            reason=request.reason,
        )
        try:
            # Slice 8.2c (N3=A, owner 2026-08-05): snapshot the name **before**
            # anything is destroyed. This is the one product value that outlives
            # the purge, so that a usage-ledger row can be read by a human
            # instead of answering with a bare id.
            #
            # Order and failure direction are both load-bearing. Moving this
            # below ``core_sot.purge_project`` would destroy the project first
            # and then, on a storage failure, lose the name forever — the exact
            # state the owner decision reverses. Wrapping it in ``try/except``
            # would do the same silently. It sits inside this block so a failure
            # still records the ``failed`` audit outcome and answers 503.
            project_name_history.record_purged(
                project_id=project_id, name=project.name
            )
            core_sot.purge_project(project_id=project_id)
            memory.purge_project(project_id=project_id)
            analysis.purge_project(project_id=project_id)
            review_queue.purge_project(project_id=project_id)
            gate_findings.purge_project(project_id=project_id)
            writing_generation_jobs.purge_project(project_id=project_id)
            writing_scratch.purge_project(project_id=project_id)
            writing_loop_audit.purge_project(project_id=project_id)
            llm_call_audit.purge_project(project_id=project_id)
            # D8-5e grants are project children and disappear. The separate
            # admin tombstone above is the explicit minimal D5 exception.
            access_grants.purge_project(project_id=project_id)
            sync_outbox.enqueue_project_purged(project_id=project_id)
        except Exception as exc:
            try:
                admin_audit.record_purge_outcome(
                    requested,
                    outcome="failed",
                    error_kind=(
                        "storage_error"
                        if isinstance(exc, _STORAGE_ERRORS)
                        else "not_found" if isinstance(exc, NotFound)
                        else "internal_error"
                    ),
                )
            except Exception:
                # D5=A: outcome is best-effort after the fail-closed requested
                # row. Never replace the actual purge failure with audit noise.
                pass
            if isinstance(exc, NotFound):
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            raise
        try:
            admin_audit.record_purge_outcome(requested, outcome="succeeded")
        except Exception:
            # The irreversible work already completed. Returning 503 here would
            # falsely tell the client to retry an endpoint that cannot retry.
            pass
        return None
