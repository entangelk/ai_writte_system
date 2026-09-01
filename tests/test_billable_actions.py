"""Slice 8.0 전수 가드 — LLM 경로가 분류 없이 열리지 못한다.

브리프 ``08-0-billable-request-boundary-decisions.md`` **B6=A**(오너 2026-08-03).
부모 계획 §5의 불변식 "새 AI 경로가 quota 적용 여부를 분류하지 않은 채 조용히 열리면
테스트가 실패해야 한다"를 규칙이 아니라 **강제**로 만든다 — 단 그 강제의 사정거리는
**scope를 여는 route까지**다(맨 아래 Coverage 클래스의 "여전히 못 잡는 것" 참조).
선례는 새 포트에 분류를
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

import importlib
import inspect
import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from services.application.app.main import create_app
from services.application.app.quota.billable_actions import (
    BILLABLE_ACTIONS,
    BILLABLE_OPERATIONS,
)

_APP_ROOT = Path(__file__).resolve().parents[1] / "services" / "application" / "app"
_GENERATION_WORKER = _APP_ROOT / "writing" / "generation_worker.py"


def _route_bodies(app) -> dict[tuple[str, str], str]:
    """``(path, method)`` → 그 endpoint 함수의 소스 본문.

    route-driven: ``app.routes`` 를 순회해 각 ``APIRoute.endpoint`` 의 소스를
    ``inspect.getsource`` 로 읽는다. **파일 배치와 무관**하게 동작한다 — 라우터가
    ``main.py`` 한 파일이든 ``register_xxx(app, …)`` 모듈로 쪼개졌든, endpoint 가
    정의된 파일에서 본문을 가져온다(라우터 분해, 2026-08-05). ``main.py`` 를 정적
    정규식으로만 읽던 종전과 달리 ``include_router``·``prefix``·별도 모듈에 숨은
    route 도 빠짐없이 본다.
    """
    bodies: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            source = ""  # 아래 canary 셀이 빈 본문을 물어 fails 로 가리킨다
        for method in route.methods:
            bodies[(route.path, method.lower())] = source
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
        cls.bodies = _route_bodies(cls.app)

    def test_every_registered_operation_has_readable_endpoint_source(self) -> None:
        # 이 파일의 다른 셀은 전부 ``inspect.getsource`` 결과에 기대므로, 어떤
        # endpoint 의 소스를 못 읽으면(빈 본문) 그 셀들이 조용히 약해진다. route-driven
        # 파싱의 전제 자체를 여기서 못박는다 — 종전 "정적 정규식 == app.routes" 카나리를
        # 대체한다(라우터가 main.py 밖으로 나가도 route 는 app.routes 에 그대로 있다).
        unreadable = sorted(op for op, body in self.bodies.items() if not body)
        self.assertEqual(
            unreadable, [],
            f"endpoint 소스를 읽지 못한 operation: {unreadable} — 분류 셀이 조용히 "
            "빈 본문을 보게 된다",
        )

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
            "analysis_extract", "analysis_compare", "draft_finalize", "context_search",
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
        cls.bodies = _route_bodies(create_app())

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
        # 2026-08-03 독립 검증 H2: 종전에는 "scope 를 연다"만 봤다. **어떤 상관키로**
        # 여는지가 B5 의 실체다 — job 의 project/request 로 열어야 enqueue 한 그
        # writing_generate 와 같은 논리 요청으로 묶인다. 새 상관키를 지어내면(예:
        # job.id) 관측은 되지만 귀속이 갈라져 "같은 한 번"이 깨진다.
        self.assertIn("project_id=job.project_id", source)
        self.assertIn("correlation_id=job.request_id", source)

    def test_retrying_a_failed_generation_is_not_a_new_billable_request(self) -> None:
        # 실패한 job 재시도는 회원이 결과를 아직 못 받은 같은 요청의 재실행이다.
        # 이 경로를 표에 넣으면 실패를 회원에게 청구하게 된다.
        retry = ("/projects/{project_id}/writing/generation-jobs/{job_id}/retry",
                 "post")
        self.assertIn(retry, self.bodies)
        self.assertNotIn(retry, BILLABLE_OPERATIONS)
        self.assertNotIn("llm_call_scope(", self.bodies[retry])


class BillableActionObservabilityCoverageTest(unittest.TestCase):
    """B2 관측 요구를 **동작별로** 기존 셀에 묶는다 (2026-08-03 독립 검증 H1 대응).

    이 파일의 다른 셀은 route 본문에 ``llm_call_scope(`` **문자열**이 있는지만 본다.
    문자열이 있는데 실제로는 레코드가 안 남는 경우까지 보려면 요청을 구동해 감사
    저장소를 읽는 셀이 필요한데, 그 셀들은 이미 세 파일에 흩어져 존재한다. 문제는
    **그 대응이 관습이었다는 것**이다 — 새 유료 동작이 관측 셀 없이 추가돼도 아무것도
    실패하지 않았다.

    그래서 대응을 표로 못박고 ① 표의 키가 유료 동작 전수와 같은지 ② 지목한 셀이
    실제로 존재하는지를 단정한다. 새 유료 동작을 추가하면 여기 한 줄을 더해야 하고,
    그 줄은 실존하는 셀을 가리켜야 한다.

    **여전히 못 잡는 것**(정직하게): provider 를 부르되 scope 를 아예 안 여는 미래
    route. `ObservedProvider.generate` 는 scope 가 없으면 호출을 미기록 통과시키므로
    (worker 진입점·script 를 위해 계약이 그렇게 정했다) 그런 route 는 관측도 분류도
    비껴간다. 그것은 이 슬라이스가 만든 구멍이 아니라 관측 계약의 잔존 한계이며
    HANDOFF 추적 부채에 있다.
    """

    #: 유료 동작 → 그 동작에서 **레코드가 실제로 남는 것**을 단정하는 기존 셀.
    COVERAGE: dict[str, tuple[str, str, str]] = {
        "writing_generate": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_generate_endpoint_scopes_planner_and_generation"),
        "writing_gate": (
            "tests.test_writing_gate", "WritingGateObservabilityTest",
            "test_successful_gate_call_is_recorded_with_its_derived_quality_score"),
        "writing_revise": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_revise_endpoint_scopes_the_revision_call"),
        "writing_revise_and_gate": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_revise_and_gate_endpoint_scopes_every_site_in_the_loop"),
        "writing_report": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_report_endpoint_scopes_the_report_call"),
        "writing_accept": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_accept_endpoint_scopes_its_gate_call"),
        "analysis_extract": (
            "tests.test_llm_call_scope", "RunEndpointOpensAScopeTest",
            "test_run_endpoint_records_the_calls_its_runner_makes"),
        "analysis_compare": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_compare_endpoint_scopes_the_whole_job"),
        "draft_finalize": (
            "tests.test_billable_actions", "BillableActionObservabilityCoverageTest",
            "test_finalize_endpoint_opens_the_analysis_scope"),
        "context_search": (
            "tests.test_llm_call_sites", "EndpointOpensAScopeTest",
            "test_context_search_endpoint_scopes_the_planner"),
    }

    def test_every_billable_action_has_an_observability_cell(self) -> None:
        self.assertEqual(
            set(self.COVERAGE), {a.action for a in BILLABLE_ACTIONS},
            "유료 동작과 관측 셀 대응표가 갈라졌다 — 새 동작을 추가했으면 그 동작의 "
            "레코드가 남는 것을 단정하는 셀도 함께 지목한다",
        )

    def test_finalize_endpoint_opens_the_analysis_scope(self) -> None:
        operation = ("/projects/{project_id}/drafts/{draft_id}/finalize", "post")
        body = _route_bodies(create_app())[operation]
        self.assertIn("llm_call_scope(", body)

    def test_every_named_observability_cell_exists(self) -> None:
        # 셀 이름을 문자열로 들고 있으므로, 그 셀이 개명·삭제되면 표가 조용히
        # 거짓이 된다. 여기서 해석해 실존을 확인한다.
        for action, (module_name, class_name, method) in self.COVERAGE.items():
            with self.subTest(action=action):
                module = importlib.import_module(module_name)
                suite = getattr(module, class_name, None)
                self.assertIsNotNone(
                    suite, f"{module_name}.{class_name} 가 없다")
                self.assertTrue(
                    callable(getattr(suite, method, None)),
                    f"{module_name}.{class_name}.{method} 가 없다",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
