"""Phase 9 Slice 9.0 전수 가드 — mutating 경로가 분류 없이 열리지 못한다 (A2=B·A7=A).

오너 결정 2026-08-09. 선례는 `test_billable_actions.py`(유료 분류)·
`test_compose_exposure.py`(포트 분류)이고 형태도 같다 — **표가 정본이고 가드가 강제**다.

**왜 40 전수인가**(A2 확정 조건 ①). 오너가 B 를 고른 것은 범위 판단이지 C 의 각하가
아니다. 기록하지 않는 20 경로까지 **사유와 함께** 등재돼야 "빠진 것"과 "일부러 뺀 것"이
구분되고, **C 로 넓히는 일이 `ai_request` 행의 값을 바꾸는 것**으로 끝난다.

**양방향으로 문다**:

- under-strict — 새 mutating route 를 분류 없이 열면 실패한다. 기록하기로 한 경로에서
  `activity.record(` 를 빼도 실패한다.
- over-strict — 기록하지 않기로 한 경로에 기록을 넣으면 실패한다(A8=A: AI 요청을
  세 번째로 복제하는 것이 정확히 그 형태다). 오타·삭제된 경로가 표에 남아도 실패한다.
"""

from __future__ import annotations

import inspect
import unittest

from fastapi.routing import APIRoute

from services.application.app.activity.actions import (
    ACTIVITY_ACTIONS,
    CLASSIFIED_OPERATIONS,
    EXCLUDED_BY_OPERATION,
    LOGGED_OPERATIONS,
)
from services.application.app.main import create_app

_MUTATING_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

#: 기록 호출의 표식. 배선이 이 이름을 쓰지 않으면 가드가 못 본다.
_RECORD_CALL = "activity.record("


def _mutating_routes(app) -> dict[tuple[str, str], str]:
    """``(path, method)`` → endpoint 소스. route-driven 이라 파일 배치와 무관하다."""
    bodies: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):  # pragma: no cover
            source = ""
        for method in route.methods:
            if method in _MUTATING_METHODS:
                bodies[(route.path, method.lower())] = source
    return bodies


class ActivityActionClassificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routes = _mutating_routes(create_app())

    def test_every_mutating_operation_is_classified(self) -> None:
        """새 mutating route 는 `logged` 또는 `excluded(사유)` 로 등재돼야 한다."""
        unclassified = sorted(set(self.routes) - CLASSIFIED_OPERATIONS)
        self.assertEqual(
            unclassified, [],
            "분류되지 않은 mutating operation 이 있다 — activity/actions.py 의 "
            "ACTIVITY_ACTIONS(기록) 또는 EXCLUDED_OPERATIONS(사유와 함께) 에 넣는다",
        )

    def test_the_table_names_no_operation_that_does_not_exist(self) -> None:
        """over-strict — 오타·삭제된 경로가 표에 남으면 실패한다."""
        stale = sorted(CLASSIFIED_OPERATIONS - set(self.routes))
        self.assertEqual(stale, [], "표에만 있고 앱에는 없는 경로")

    def test_the_logged_set_is_the_twenty_the_owner_approved(self) -> None:
        """A2=B — 정본 변경 **11** + 검토 결정 9.

        착수 결정은 19 였고, 2026-08-09 에 오너가 `writing/accept`(정본 draft
        version 저장)를 더해 **20** 이 됐다.

        숫자를 셀에 적는 이유는 범위가 **오너 결정**이기 때문이다. 넓히는 것은
        결정이지 리팩터링이 아니므로, 여기서 눈에 띄게 실패해야 한다.
        """
        self.assertEqual(len(LOGGED_OPERATIONS), 20)
        self.assertEqual(len(ACTIVITY_ACTIONS), 20)
        self.assertEqual(
            len({action.action for action in ACTIVITY_ACTIONS}), 20,
            "action 리터럴이 중복이다 — 조회 화면이 두 사건을 구분 못 한다",
        )

    def test_every_ai_request_is_excluded_with_that_reason(self) -> None:
        """★ A2 확장 조건 — C 로 넓히는 일이 "이 행들의 값 바꾸기" 여야 한다.

        AI 요청이 `ai_request` 사유로 **모여** 있어야 그 확장이 한 자리에서 끝난다.
        흩어지거나 사유가 뒤섞이면 다음 사람이 무엇을 뒤집어야 하는지 모른다.
        """
        ai_requests = {
            operation for operation, excluded in EXCLUDED_BY_OPERATION.items()
            if excluded.reason == "ai_request"
        }

        self.assertEqual(len(ai_requests), 13)
        self.assertTrue(all(
            EXCLUDED_BY_OPERATION[operation].note
            for operation in ai_requests
        ), "사유 리터럴만으로는 부족하다 — 왜 뺐는지 한 줄이 함께 간다")

    def test_every_logged_route_actually_records(self) -> None:
        """under-strict — 표에 넣고 배선을 잊으면 실패한다.

        A4=A(격리) 때문에 **배선 누락은 런타임에 아무 소리도 내지 않는다** — 로그가
        비어도 요청은 200 이다. 그래서 이 방향의 가드가 특히 필요하다.
        """
        for operation in sorted(LOGGED_OPERATIONS):
            with self.subTest(operation=operation):
                self.assertIn(
                    _RECORD_CALL, self.routes[operation],
                    f"{operation} 이 활동 로그를 남기지 않는다",
                )

    def test_no_excluded_route_records(self) -> None:
        """over-strict — 기록하지 않기로 한 경로가 기록하면 실패한다.

        A8=A 가 걸린 자리다: AI 요청을 여기에 더하면 같은 사건이 관측·원장·활동 로그
        셋에 살게 되고, 그것은 A2 를 C 로 넓히는 **결정**이지 배선 실수가 아니다.
        """
        for operation in sorted(EXCLUDED_BY_OPERATION):
            with self.subTest(operation=operation):
                self.assertNotIn(
                    _RECORD_CALL, self.routes[operation],
                    f"{operation} 은 기록하지 않기로 분류됐는데 기록한다 — 넓히려면 "
                    "activity/actions.py 의 분류를 먼저 옮긴다(A2 결정)",
                )

    def test_the_recorded_action_literal_matches_the_table(self) -> None:
        """배선이 표와 **같은 리터럴**을 써야 한다.

        표는 정본인데 endpoint 가 다른 이름을 쓰면 조회 화면과 표가 갈라진다.
        `test_billable_actions` 가 같은 이유로 리터럴까지 단정한다.
        """
        for operation in sorted(LOGGED_OPERATIONS):
            with self.subTest(operation=operation):
                from services.application.app.activity.actions import (
                    ACTIVITY_ACTION_BY_OPERATION,
                )
                action = ACTIVITY_ACTION_BY_OPERATION[operation]
                self.assertIn(
                    f'"{action.action}"', self.routes[operation],
                    f"{operation} 이 표의 리터럴 {action.action!r} 을 쓰지 않는다",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
