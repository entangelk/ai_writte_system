"""Canonical memory route (``/projects/{id}/memory*`` 4 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). 읽기 2개의
handler 본문은 byte-동일이다.

**읽기 2개는 여전히 읽기 전용이다** — memory 는 append-only 이고 canonical 승격은
analysis 쪽 경로(review/apply/auto-promote)를 지난다. 그 쓰기 경로는 아직 ``main.py``
에 있고 같은 ``_memory_payload`` 를 쓴다. 그래서 그 직렬화기는 이 모듈이 아니라
``..api.payloads`` 에 있다.

2026-10-06(오너 결정 B안): 세 번째 operation **PUT** 이 열렸다 — 승격이 아니라
**이미 canonical 인 항목의 사람 직접 수정**이다. append-only 는 유지된다(새 버전
발행 + 이전 버전 SUPERSEDED 보존, ``edit_canonical_version`` 참조). 검토함 후보
절차를 거치지 않는 유일한 canonical 쓰기 경로라 활동 로그 행
``canonical_memory_edited`` 가 함께 남는다.

2026-10-06(같은 날, A안): 네 번째 operation **POST /memory/merge** — 같은 인물이
분석에 따라 갈라져 만들어진 canonical 둘을 하나로 통합한다. 병합 결과는 생존 쪽의
다음 버전이고 흡수된 항목은 ``merged_into`` 앞링크로 결과를 가리킨다(사슬 연결
보존). 활동 로그 행은 ``canonical_memory_merged``.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from services.application.app.analysis.schema import InvalidAnalysisPayload
from services.application.app.core_sot.service import NotFound
from services.application.app.memory.service import (
    MemoryError,
    MemoryNotFound,
)

from ..api.dependencies import (
    _REQUIRE_PROJECT_OWNER,
    project_existence_check,
    require_authenticated_user,
)
from ..api.errors import _ERRORS_400_404_409, _ERRORS_404, _owned
from ..api.models import EditMemoryRequest, MergeMemoryRequest
from ..api.payloads import _memory_payload


def register_memory(app, *, core_sot, memory, activity) -> None:
    _require_project_exists = project_existence_check(core_sot)

    @app.get("/projects/{project_id}/memory", responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_memory(project_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "memory": [
                _memory_payload(entry)
                for entry in memory.list_memories(project_id=project_id)
            ]
        }

    @app.get("/projects/{project_id}/memory/{memory_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_memory(project_id: str, memory_id: str) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            entry = memory.get_memory(project_id=project_id, memory_id=memory_id)
        except (MemoryNotFound, NotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _memory_payload(entry)

    @app.post(
        # 정적 세그먼트 "merge" — `{memory_id}` 패턴보다 앞에 둔다(메서드가 달라
        # 어차피 충돌은 없지만, 읽는 사람에게 별도 operation 임이 먼저 보이게).
        "/projects/{project_id}/memory/merge",
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def merge_memory(
        project_id: str, body: MergeMemoryRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if project.archived:
            raise HTTPException(status_code=409, detail="project is archived")
        try:
            result = memory.merge_canonical_entries(
                project_id=project_id,
                survivor_memory_id=body.survivor_memory_id,
                absorbed_memory_id=body.absorbed_memory_id,
                base_survivor_version=body.base_survivor_version,
                base_absorbed_version=body.base_absorbed_version,
                idempotency_key=body.idempotency_key,
                payload=body.payload,
            )
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MemoryError as exc:
            # 상태 충돌 축: 낡은 base(양쪽 각각)·비-canonical 대상·자기 병합·
            # 타입 불일치·인물 외 taxonomy.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnalysisPayload as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not result.idempotent_replay:
            # 활동 로그 D2=ⓑ — replay 는 행을 안 남긴다. after 요약은 그룹
            # 승인 선례의 모양이다(무엇이 흡수됐는지 한 줄로).
            activity.record(
                project_id=project_id, actor_user_id=current.id,
                action="canonical_memory_merged", target_type="memory",
                target_id=body.survivor_memory_id,
                after=f"version={result.memory.version}, absorbed=1",
            )
        return {
            "memory": _memory_payload(result.memory),
            "idempotent_replay": result.idempotent_replay,
        }

    @app.put(
        "/projects/{project_id}/memory/{memory_id}",
        responses=_owned(_ERRORS_400_404_409),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def edit_memory(
        project_id: str, memory_id: str, body: EditMemoryRequest,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        try:
            _require_project_exists(project_id)
            project = core_sot.get_project(project_id=project_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if project.archived:
            # brief PUT 과 같은 답(409): 보관된 프로젝트의 정본은 읽기만 허용한다.
            # sibling 승격 경로(promote)에는 이 가드가 없는데, 그 차이는 이 슬라이스의
            # SoT 항목에 명시했다.
            raise HTTPException(status_code=409, detail="project is archived")
        try:
            result = memory.edit_canonical_version(
                project_id=project_id,
                target_memory_id=memory_id,
                base_version=body.base_version,
                idempotency_key=body.idempotency_key,
                payload=body.payload,
            )
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MemoryError as exc:
            # 두 상태 충돌(non-canonical 대상·낡은 base_version)이 이 축이다.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnalysisPayload as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not result.idempotent_replay:
            # 활동 로그 D2=ⓑ — replay 는 행을 안 남긴다(brief PUT 과 같은 규칙).
            activity.record(
                project_id=project_id, actor_user_id=current.id,
                action="canonical_memory_edited", target_type="memory",
                target_id=memory_id,
                after=f"version={result.memory.version}",
            )
        return {
            "memory": _memory_payload(result.memory),
            "idempotent_replay": result.idempotent_replay,
        }
