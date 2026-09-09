"""사용자명 이력 — 계정 파기를 살아남는 이름 한 값 (계정 탈퇴 Slice 3).

오너 결정 2026-09-07(*"사용량 원장과 사용자명 한 값은 남긴다"*)과 2026-09-09
(브리프 ``slice3-withdrawal-purge-daemon-decisions.md`` — 식별 규칙 ⓑ).
[`project_name_history`](project_name_history.py) 와 **같은 목적, 다른 키 모양**이다.

★ **키 모양이 왜 다른가 — 선례 위반이 아니라 선례가 여기서 자기 발을 문다.**
프로젝트 축의 묘비는 ``_id`` 를 project id 로 써서 파기를 비껴간다: reconciler 가
``project_id`` **필드**로 대상을 찾으므로 필드를 안 쓰면 안 지워진다. 그런데 계정 축의
파기는 오너 결정 ⓑ 로 **두 규칙**(``user_id`` 필드 **또는** ``_id`` 가 그 user id)을
쓰므로, 같은 모양을 따르면 **파기 데몬이 방금 자기가 쓴 묘비를 지운다.**

그래서 이 컬렉션의 표식은 **필드 이름 ``target_user_id``** 다 — 사용량 원장(D4)·
관리자 감사 원장이 이미 쓰는 그 이름이고, ⓑ 가 계정 축의 규칙을 한 문장으로 만든다:

    ``user_id`` · ``_id`` 로 사용자를 가리키면 지운다. ``target_user_id`` 로
    가리키면 남긴다.

``_id`` 는 ``user_name:<user id>`` 로 **접두를 붙인다.** 두 가지를 동시에 한다 —
회원당 한 행을 기본 키가 강제하고(``project_name_history`` 의 N2 와 같은 계약),
동시에 ``_id`` 가 user id 와 **같지 않아** 두 규칙 중 ``_id`` 축에도 안 걸린다.

**TTL 이 없다.** 보존 기간은 무기한이며(정책 결정 2, 2026-09-07 — 삭제 요청 전까지),
프로젝트 이름 이력과 같은 자리에서 같은 정책을 받는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol

#: ``_id`` 접두. 값 자체가 계약이다 — 떼면 `_id` 가 user id 와 같아져 파기 데몬의
#: 두 번째 규칙이 이 묘비를 지운다(핀 셀이 잠근다).
ID_PREFIX = "user_name:"


def document_id(user_id: str) -> str:
    return ID_PREFIX + user_id


@dataclass(frozen=True, slots=True)
class UserNameSnapshot:
    target_user_id: str
    username: str
    purged_at: datetime


class UserNameHistoryRepository(Protocol):
    def put(self, snapshot: UserNameSnapshot) -> None: ...

    def get(self, user_id: str) -> UserNameSnapshot | None: ...


class InMemoryUserNameHistoryRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, UserNameSnapshot] = {}

    def put(self, snapshot: UserNameSnapshot) -> None:
        self.snapshots[snapshot.target_user_id] = snapshot

    def get(self, user_id: str) -> UserNameSnapshot | None:
        return self.snapshots.get(user_id)

    def count(self) -> int:
        return len(self.snapshots)


class UserNameHistoryService:
    def __init__(
        self,
        repository: UserNameHistoryRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def record_purged(self, *, user_id: str, username: str) -> UserNameSnapshot:
        """파기 **직전에** 이름을 스냅샷한다. 실패는 삼키지 않는다 — 호출자가 fail-closed다.

        이름은 정본이 허용한 그대로 남긴다. 여기서 손대면 원장 조회가 회원이 쓰던
        이름과 다른 것을 말한다(프로젝트 축 N3 과 같은 이유).
        """
        snapshot = UserNameSnapshot(
            target_user_id=user_id, username=username, purged_at=self._clock()
        )
        self._repo.put(snapshot)
        return snapshot

    def get(self, *, user_id: str) -> UserNameSnapshot | None:
        return self._repo.get(user_id)
