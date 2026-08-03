"""Slice 8.0 전수 가드 — LLM 경로가 분류 없이 열리지 못한다.

브리프 ``08-0-billable-request-boundary-decisions.md`` **B6=A**(오너 2026-08-03).
부모 계획 §5의 불변식 "새 AI 경로가 quota 적용 여부를 분류하지 않은 채 조용히 열리면
테스트가 실패해야 한다"를 규칙이 아니라 **강제**로 만든다. 선례는 새 포트에 분류를
강요하는 ``test_compose_exposure.py``와 tier 전수 가드
``test_auth_api.py::CombinedBoundaryMatrixTest``다.

**양방향으로 문다**(어느 한 방향만 무는 가드는 절반이다):

- under-strict — LLM 을 부르는 endpoint 를 표에 안 넣으면 실패한다.
- over-strict — provider 를 안 부르는 무료 경로를 표에 넣거나(B4 위반), 오타·삭제된
  경로를 남겨 두면 실패한다.

**여기서 잠그지 않는 것**: repair 호출이 자기 레코드로 남는다는 사실은
``test_llm_call_sites.py``·``test_llm_call_scope.py``가 이미 잠근다. 그 사실과 이 파일의
"모든 유료 경로가 scope 를 연다"가 합쳐져야 B2 의 관측 요구(내부 호출이 전부 관측
안에 있다)가 성립하므로, 두 파일을 함께 읽어야 한다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from services.application.app.main import create_app
from services.application.app.quota.billable_actions import (
    BILLABLE_ACTIONS,
    BILLABLE_OPERATIONS,
)

_APP_ROOT = Path(__file__).resolve().parents[1] / "services" / "application" / "app"
_MAIN = _APP_ROOT / "main.py"
_GENERATION_WORKER = _APP_ROOT / "writing" / "generation_worker.py"

# 다중행 데코레이터도 잡는다(`@app.post(\n    "/path"`). 이 정규식이 라우트를 놓치면
# 가드가 조용히 약해지므로, 아래 첫 셀이 파싱 결과를 실제 app.routes 와 대조한다.
_ROUTE = re.compile(r'@app\.(get|post|put|patch|delete)\(\s*\n?\s*"([^"]+)"')


def _route_bodies() -> dict[tuple[str, str], str]:
    """``(path, method)`` → 그 endpoint 의 소스 본문(다음 라우트 직전까지)."""
    source = _MAIN.read_text(encoding="utf-8")
    matches = list(_ROUTE.finditer(source))
    bodies: dict[tuple[str, str], str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        bodies[(match.group(2), match.group(1).lower())] = source[match.start():end]
    return bodies


def _operations(app) -> set[tuple[str, str]]:
    return {
        (route.path, method.lower())
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


class BillableActionInventoryTest(unittest.TestCase):
    """분류표가 실제 라우트·실제 provider 사용과 일치하는가."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.operations = _operations(cls.app)
        cls.bodies = _route_bodies()

    def test_the_static_parse_sees_exactly_the_registered_operations(self) -> None:
        # 이 파일의 다른 셀은 전부 소스 파싱에 기대므로, 파싱이 라우트를 놓치거나
        # 지어내면 그 셀들이 조용히 약해진다. 먼저 파싱 자체를 앱과 대조해 못박는다.
        self.assertEqual(set(self.bodies), self.operations)

    def test_every_provider_calling_operation_is_classified(self) -> None:
        """B6 양방향 핵심 셀.

        under-strict: LLM 을 부르는 endpoint 를 표에 안 넣으면 왼쪽에 남아 실패.
        over-strict: provider 를 안 부르는 경로를 표에 넣으면 오른쪽에 남아 실패.
        """
        opens_scope = {
            operation
            for operation, body in self.bodies.items()
            if "llm_call_scope(" in body
        }
        self.assertEqual(opens_scope, set(BILLABLE_OPERATIONS))

    def test_every_classified_action_is_a_live_operation(self) -> None:
        # 경로 오타와 삭제된 endpoint 를 잡는다. 위 셀은 파싱 결과끼리 비교하므로
        # "소스에는 있지만 앱에 등록되지 않은" 경우를 이 셀이 따로 본다.
        for action in BILLABLE_ACTIONS:
            with self.subTest(action=action.action):
                self.assertIn(
                    (action.path, action.method.lower()), self.operations
                )

    def test_free_operations_never_open_a_provider_scope(self) -> None:
        # B4 의 무료 쪽을 명시적으로 단정한다. 위 집합 동치의 따름정리지만, 무료
        # 경로에 provider 호출을 얹는 변경이 무엇을 깨는지 이름으로 보이게 둔다.
        for operation, body in self.bodies.items():
            if operation in BILLABLE_OPERATIONS:
                continue
            with self.subTest(operation=operation):
                self.assertNotIn("llm_call_scope(", body)

    def test_action_literals_are_unique_and_pinned(self) -> None:
        # 원장·회원 화면이 쓸 리터럴이라 조용한 개명은 과거 사용량과의 대조를 끊는다.
        literals = [action.action for action in BILLABLE_ACTIONS]
        self.assertEqual(len(literals), len(set(literals)))
        self.assertEqual(set(literals), {
            "writing_generate", "writing_gate", "writing_revise",
            "writing_revise_and_gate", "writing_report", "writing_accept",
            "analysis_extract", "analysis_compare", "context_search",
        })

    def test_the_fan_out_marking_matches_the_measured_paths(self) -> None:
        # B3: 표시가 목적이므로 표시 자체를 잠근다. compare 는 매칭 후보 1건마다
        # 판정을 부르고(analysis/compare.py 의 후보 루프), 나머지는 요청당 호출 수가
        # 정책 상수로 묶여 있다.
        marked = {a.action for a in BILLABLE_ACTIONS if a.fan_out}
        self.assertEqual(marked, {"analysis_compare"})


class SameLogicalRequestTest(unittest.TestCase):
    """B5=A — 비동기 실행과 재시도는 같은 논리 요청이라 표에 없다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bodies = _route_bodies()

    def test_the_generation_worker_is_observed_but_not_billed(self) -> None:
        # 워커는 route 가 아니라 위 전수 가드의 사각지대다. 두 가지를 함께 단정한다:
        # ① provider 를 부르므로 **관측**은 되어야 한다(B2 의 관측 요구)
        # ② 그러나 enqueue 한 writing_generate 와 같은 논리 요청이라 **과금은 안 된다**
        source = _GENERATION_WORKER.read_text(encoding="utf-8")
        self.assertIn("llm_call_scope(", source)
        self.assertNotIn(
            ("/projects/{project_id}/writing/generation-jobs", "post"),
            BILLABLE_OPERATIONS,
        )

    def test_retrying_a_failed_generation_is_not_a_new_billable_request(self) -> None:
        # 실패한 job 재시도는 회원이 결과를 아직 못 받은 같은 요청의 재실행이다.
        # 이 경로를 표에 넣으면 실패를 회원에게 청구하게 된다.
        retry = ("/projects/{project_id}/writing/generation-jobs/{job_id}/retry",
                 "post")
        self.assertIn(retry, self.bodies)
        self.assertNotIn(retry, BILLABLE_OPERATIONS)
        self.assertNotIn("llm_call_scope(", self.bodies[retry])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
