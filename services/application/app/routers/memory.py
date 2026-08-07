"""Canonical memory 읽기 route (``/projects/{id}/memory*`` 2 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**읽기 전용이다** — memory 는 append-only 이고 canonical 승격은 analysis 쪽
경로(review/apply/auto-promote)를 지난다. 그 쓰기 경로는 아직 ``main.py`` 에
있고 같은 ``_memory_payload`` 를 쓴다. 그래서 그 직렬화기는 이 모듈이 아니라
``..api.payloads`` 에 있다.
"""

from __future__ import annotations

from fastapi import HTTPException

from services.application.app.core_sot.service import NotFound
from services.application.app.memory.service import MemoryNotFound

from ..api.errors import _ERRORS_404, _owned
from ..api.dependencies import _REQUIRE_PROJECT_OWNER, project_existence_check
from ..api.payloads import _memory_payload


def register_memory(app, *, core_sot, memory) -> None:
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
