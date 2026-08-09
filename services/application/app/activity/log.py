"""활동 로그 저장 계약 (Phase 9 Slice 9.0, A3=B·A4=A·A6=A).

문서 형태·실패 방향·보존이 전부 여기 있다. 분류는 ``actions.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol
from uuid import uuid4

_log = logging.getLogger(__name__)

#: A3=B 의 "짧은 값" 경계. 이름·제목·상태 같은 **라벨**만 담기게 하는 상한이며,
#: 브리프가 계약으로 못박으라고 한 그 숫자다. 이 저장소의 이름·제목에는 길이 제한이
#: 없으므로(실측: `NonBlankName` 은 `min_length=1` 뿐) 상한이 없으면 **본문 길이의
#: 문자열이 그대로 들어올 수 있다** — D(본문 diff)를 기각한 이유가 무의미해진다.
ACTIVITY_VALUE_MAX_CHARS = 200


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """활동 한 건. **키 집합 자체가 계약이다.**

    ★ ``project_id`` 는 반드시 이 이름이어야 한다(부모 계획 §4 I1). purge
    reconciler 가 이 필드를 가진 컬렉션을 DB 에서 발견해 고아를 쓸어 가므로,
    ``target_project_id`` 로 바꾸면 **파기가 이 로그를 못 지운다** — 그것이 곧
    D8-6 삭제 계약 위반이다(8.2c `project_name_history` 와 정확히 반대 방향).
    """

    id: str
    project_id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str
    at: datetime
    #: A3=B. 값 변화가 있는 행만 채운다(개명·상태) — 없으면 ``None``.
    before: str | None = None
    after: str | None = None


class ActivityLogRepository(Protocol):
    def insert(self, event: ActivityEvent) -> None: ...

    def list_for_project(
        self, *, project_id: str, limit: int
    ) -> tuple[ActivityEvent, ...]: ...

    def purge_project(self, *, project_id: str) -> None: ...


class InMemoryActivityLogRepository:
    def __init__(self) -> None:
        self.events: list[ActivityEvent] = []

    def insert(self, event: ActivityEvent) -> None:
        self.events.append(event)

    def list_for_project(
        self, *, project_id: str, limit: int
    ) -> tuple[ActivityEvent, ...]:
        rows = [event for event in self.events if event.project_id == project_id]
        return tuple(sorted(rows, key=lambda event: event.at, reverse=True)[:limit])

    def purge_project(self, *, project_id: str) -> None:
        self.events = [
            event for event in self.events if event.project_id != project_id
        ]


def _short(value: str | None) -> str | None:
    """A3=B 의 "짧은 값" 을 **경계에서** 강제한다.

    자르는 쪽을 고른 이유는 A4=A 다 — 여기서 거절하면 격리가 그 예외를 삼켜
    **행이 통째로 사라진다**(사용자에게는 "기록이 안 됐다"로 보인다). 라벨을
    잘라 남기는 편이 낫고, 상한을 넘긴다는 것 자체가 이미 계약 위반 신호다.
    """
    if value is None:
        return None
    return value[:ACTIVITY_VALUE_MAX_CHARS]


class ActivityLogService:
    """A4=A — **기록 실패는 요청을 실패시키지 않는다.**

    격리 경계를 서비스 안에 둔 것은 의도다. 19 개 호출부가 각자 ``try/except`` 를
    쓰면 한 곳이 빠지는 순간 그 경로만 fail-closed 가 되고, 그 차이는 저장소가
    죽기 전까지 아무 테스트도 못 본다. 판정 기준은 코드가 이미 문장으로 갖고 있다 —
    ``access_grant_uses`` 가 fail-closed 인 것은 *"기록이 없으면 관리자 열람을
    아무도 설명할 수 없어서"* 이고, 활동 로그가 없다고 잘못 열리는 문은 없다.

    **대가는 조용한 구멍이다**(브리프 §후속 고려): 로그가 비어도 아무도 모른다.
    진단 카운터는 이번 범위 밖이며, 지금은 예외를 로거로 흘린다.
    """

    def __init__(
        self,
        repository: ActivityLogRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def record(
        self,
        *,
        project_id: str,
        actor_user_id: str,
        action: str,
        target_type: str,
        target_id: str,
        before: str | None = None,
        after: str | None = None,
    ) -> None:
        event = ActivityEvent(
            id=self._id_factory(),
            project_id=project_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            at=self._clock(),
            before=_short(before),
            after=_short(after),
        )
        try:
            self._repo.insert(event)
        except Exception:  # noqa: BLE001 — A4=A deliberate isolation boundary
            # 같은 형태의 선례: observability/llm_call_scope.py 의 `_flush`.
            # 좁히면 저장소 예외가 전역 handler(v1.7.38)에 도달해 정상 2xx 가
            # 503 으로 뒤집힌다.
            _log.warning("activity log write failed", exc_info=True)

    def list_for_project(
        self, *, project_id: str, limit: int = 100
    ) -> tuple[ActivityEvent, ...]:
        return self._repo.list_for_project(project_id=project_id, limit=limit)

    def purge_project(self, *, project_id: str) -> None:
        """D8-6/I1 — 프로젝트 자식이므로 파기와 함께 사라진다.

        ★ 여기는 **격리하지 않는다**. 파기 경로의 예외는 purge handler 가 감사
        `failed` 로 기록하고 503 을 내야 하며, 삼키면 지워지지 않은 로그가 남은 채
        "성공"이 된다 — 그것이 D5 부분 삭제 금지 위반이다.
        """
        self._repo.purge_project(project_id=project_id)
