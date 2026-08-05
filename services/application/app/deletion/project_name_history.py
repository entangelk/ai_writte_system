"""프로젝트 이름 이력 — 파기를 살아남는 이름 한 값 (Slice 8.2c, N1~N3=A).

오너 결정 2026-08-05, 브리프 ``08-2c-project-name-history-decisions.md``.
D8-6이 확정했던 "purge는 이름을 남기지 않는다"의 **개정**이며, 이유는 사용량 원장을
사람이 읽을 수 있어야 하기 때문이다(원장 행의 축은 ``target_project_id`` 하나뿐이라
이름 없이는 삭제된 프로젝트가 id로만 답해진다).

세 가지가 계약이다.

* **N1=A — `_id`가 project id다.** ``project_id`` **필드를 쓰지 않는다**.
  ``scripts/purge_reconciler.py``는 그 필드를 가진 컬렉션을 DB에서 발견해 고아를
  지우므로, 필드를 쓰는 순간 **이 컬렉션이 지워진다**(목적의 정반대). 8.2 원장이
  ``target_project_id``로 개명하며 치른 값과 같은 뿌리다.
* **N2=A — 프로젝트 이름 최신 한 값.** draft 제목도 개명 이력도 아니다. 삭제 뒤에 남는
  사용자 텍스트를 프로젝트당 한 줄로 묶는다.
* **N3=A — 파기 시점에만 쓴다.** 살아 있는 프로젝트의 이름 정본은 ``projects``이고,
  생성·개명 경로에서 복제하면 두 정본 문제가 생긴다.

**TTL이 없다.** 보존 기간은 오너가 "나중에 별도 정책으로" 정한다 — 전용 컬렉션을 고른
이유가 그 정책이 붙을 자리를 만드는 것이었다. 조회 통로(원장 조인)는 8.5다(N4=A).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class ProjectNameSnapshot:
    project_id: str
    name: str
    purged_at: datetime


class ProjectNameHistoryRepository(Protocol):
    def put(self, snapshot: ProjectNameSnapshot) -> None: ...

    def get(self, project_id: str) -> ProjectNameSnapshot | None: ...


class InMemoryProjectNameHistoryRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, ProjectNameSnapshot] = {}

    def put(self, snapshot: ProjectNameSnapshot) -> None:
        self.snapshots[snapshot.project_id] = snapshot

    def get(self, project_id: str) -> ProjectNameSnapshot | None:
        return self.snapshots.get(project_id)

    def count(self) -> int:
        return len(self.snapshots)


class ProjectNameHistoryService:
    def __init__(
        self,
        repository: ProjectNameHistoryRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def record_purged(self, *, project_id: str, name: str) -> ProjectNameSnapshot:
        """파기 **직전에** 이름을 스냅샷한다. 실패는 삼키지 않는다 — 호출자가 fail-closed다.

        이름은 정본이 허용한 그대로 남긴다(정규화·거부 없음). 여기서 손대면 원장 조회가
        사용자가 지은 이름과 다른 것을 말한다.
        """
        snapshot = ProjectNameSnapshot(
            project_id=project_id, name=name, purged_at=self._clock()
        )
        self._repo.put(snapshot)
        return snapshot

    def get(self, *, project_id: str) -> ProjectNameSnapshot | None:
        return self._repo.get(project_id)
