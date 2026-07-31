"""Self-regression for the report input-budget measurement CLI (R-a/R-c).

The live measurement needs a model server, so what is locked here is the part
that decides whether the measurement is **meaningful**: the seed manuscript
really saturates the current scene, the PASS/REJECT rule is the guard's rule at
the boundary in both directions, and a run that failed to saturate says so
instead of printing a table that looks like a boundary but is not one.
"""

import io
import unittest

from scripts.report_budget_measure import (
    BudgetRow,
    Overheads,
    build_arg_parser,
    build_manuscript,
    format_measurement,
    main,
    seed_saturating_project,
)
from services.application.app.context_search.service import _split_scene_blocks
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)


def _row(**overrides) -> BudgetRow:
    fields = dict(
        budget=8192, items=30, budget_excluded=3, accounting_tokens=8100,
        package_tokens=7600, input_tokens=12000, output_cap=6144, window=16384,
    )
    fields.update(overrides)
    return BudgetRow(**fields)


class ManuscriptTest(unittest.TestCase):
    def test_the_manuscript_reaches_the_requested_size_and_is_deterministic(self):
        first = build_manuscript(target_chars=5000)
        self.assertGreaterEqual(len(first), 5000)
        self.assertEqual(first, build_manuscript(target_chars=5000))

    def test_the_manuscript_carries_no_heading(self):
        """Over-strict guard for the saturation itself.

        ``_split_scene_blocks`` treats only the paragraphs *after* the last
        heading as the current scene. A heading anywhere in the seed would
        silently shrink the scene to its tail, so the package would stop
        filling the budget and the measurement would report a boundary that
        does not exist. A future edit that adds a title must fail here.
        """
        for line in build_manuscript(target_chars=3000).splitlines():
            self.assertFalse(line.startswith("#"), line)
            self.assertFalse(line.strip() in {"***", "---", "* * *"}, line)

    def test_every_seeded_block_lands_in_the_current_scene(self):
        core_sot = CoreSotService(InMemoryCoreSotRepository())
        project_id, _draft_id, version_id = seed_saturating_project(
            core_sot, name="probe", target_chars=6000,
        )
        detail = core_sot.get_draft_version(
            project_id=project_id,
            draft_id=core_sot.list_drafts(project_id=project_id)[0].id,
            version_id=version_id,
        )
        current, recent = _split_scene_blocks(detail.blocks, recent_limit=5)
        self.assertGreater(len(current), 5)
        self.assertEqual(len(current), len(detail.blocks))
        self.assertEqual(recent, ())


class VerdictTest(unittest.TestCase):
    """The verdict must be the guard's own rule (`입력 + 출력 ≤ 창`), inclusive."""

    def test_exactly_filling_the_window_passes(self):
        row = _row(input_tokens=10240, output_cap=6144, window=16384)
        self.assertEqual(row.total, 16384)
        self.assertEqual(row.headroom, 0)
        self.assertEqual(row.verdict, "PASS")

    def test_one_token_over_the_window_is_rejected(self):
        row = _row(input_tokens=10241, output_cap=6144, window=16384)
        self.assertEqual(row.headroom, -1)
        self.assertEqual(row.verdict, "REJECT")


class GuardParityTest(unittest.IsolatedAsyncioTestCase):
    """스크립트의 판정과 **프로덕션 가드의 판정**이 같은 입력에서 갈리지 않는지.

    `VerdictTest`는 스크립트 쪽 규칙만 잠근다. 가드 식이 미래에 드리프트하면(예: 누군가
    `<=`를 `<`로 바꾸면) 스크립트는 PASS라 말하는데 배포는 거부하고, 그 순간 이 리그의
    측정값은 배포를 설명하지 못한다 — 스크립트 주석이 "사본을 만들지 않는다"고 강조하는
    실패 모드가 정확히 이것이다(독립 검증 하드닝 #2).
    """

    async def _guard_rejects(self, *, input_tokens: int, max_output: int,
                             window: int) -> bool:
        from services.llm_gateway.app.client import LlamaCppProvider
        from services.llm_gateway.app.transport import (
            FakeJsonTransport, JsonResponse,
        )

        transport = FakeJsonTransport([
            JsonResponse(status_code=200, body={"prompt": "x" * input_tokens}),
            JsonResponse(status_code=200,
                         body={"tokens": list(range(input_tokens))}),
        ])
        provider = LlamaCppProvider(
            transport=transport, default_model="m",
            default_thinking=False, provider_name="p",
        )
        provider._context_window = window
        provider._window_probed = True
        decision = await provider._window_decision(
            {"messages": [], "chat_template_kwargs": {}}, max_output,
        )
        return decision is not None

    async def test_the_script_and_the_guard_agree_on_both_sides_of_the_boundary(self):
        window, cap = 16384, 6144
        for input_tokens in (window - cap - 1, window - cap, window - cap + 1):
            with self.subTest(input_tokens=input_tokens):
                row = _row(input_tokens=input_tokens, output_cap=cap, window=window)
                guard_rejects = await self._guard_rejects(
                    input_tokens=input_tokens, max_output=cap, window=window,
                )
                self.assertEqual(row.verdict == "REJECT", guard_rejects)


class FormatTest(unittest.TestCase):
    def setUp(self):
        self.overheads = Overheads(
            system_tokens=465, candidate_tokens=4096,
            wrapper_tokens_by_budget={4096: 150, 8192: 150},
        )

    def test_a_run_that_never_saturated_says_the_table_is_not_a_boundary(self):
        text = format_measurement(
            [_row(budget_excluded=0, input_tokens=5000)],
            overheads=self.overheads, window=16384, output_cap=6144,
            project_id="p1", llama_base_url="http://llama:9080",
            candidate_chars=7000,
        )
        self.assertIn("예산 제외가 0건", text)
        self.assertNotIn("권장 예산", text)

    def test_a_saturated_run_reports_the_largest_passing_budget_and_a_recommendation(self):
        rows = [
            _row(budget=4096, budget_excluded=12, accounting_tokens=4090,
                 package_tokens=3800, input_tokens=8500),
            _row(budget=8192, budget_excluded=3, accounting_tokens=8100,
                 package_tokens=7600, input_tokens=12400),
        ]
        text = format_measurement(
            rows, overheads=self.overheads, window=16384, output_cap=6144,
            project_id="p1", llama_base_url="http://llama:9080",
            candidate_chars=7000,
        )
        # 4096 → 8,500 + 6,144 = 14,644 (통과) · 8192 → 12,400 + 6,144 = 18,544 (거부)
        self.assertIn("통과하는 최대 예산: 4096", text)
        self.assertIn("권장 예산", text)

    def test_the_recommendation_does_not_move_with_the_budget_list(self):
        """권장치는 **만재에 가장 가까운 예산**에서 뽑는다 — 목록의 첫 행이 아니라.

        회계/실측 비율은 예산이 커질수록 오른다(패키지의 구조적 래퍼가 상각된다). 첫 행을
        쓰면 같은 배포·같은 프로젝트인데 `--budgets`를 어떻게 주느냐로 권장치가 달라진다 —
        독립 검증이 실제로 5,330(2048부터 준 실행) vs 5,381(4096부터 준 실행)로 이 흔들림을
        잡았다. 작은 예산을 **덧붙였을 뿐인데** 권장치가 바뀌면 이 테스트가 문다.
        """
        big = _row(budget=8192, budget_excluded=3, accounting_tokens=8185,
                   package_tokens=8358, input_tokens=13076)
        small = _row(budget=2048, budget_excluded=102, accounting_tokens=1979,
                     package_tokens=2050, input_tokens=6768)
        kwargs = dict(overheads=self.overheads, window=16384, output_cap=6144,
                      project_id="p1", llama_base_url="http://llama:9080",
                      candidate_chars=7000)

        def _recommendation(rows):
            line = [line for line in format_measurement(rows, **kwargs).splitlines()
                    if "권장 예산" in line]
            self.assertEqual(len(line), 1)
            return line[0].split("약")[-1].strip()

        self.assertEqual(_recommendation([big]), _recommendation([small, big]))

    def test_a_wrapper_that_varies_by_budget_is_reported_instead_of_averaged_away(self):
        """"고정 오버헤드"라는 단언을 출력이 직접 증명하게 한다(하드닝 #3).

        프롬프트 포장이 항목 수에 따라 달라지는 변경이 들어오면 하나만 재서 "고정"이라고
        적는 출력은 그것을 숨긴다. 산식은 보수적으로 **최대치**를 쓴다.
        """
        overheads = Overheads(
            system_tokens=465, candidate_tokens=4096,
            wrapper_tokens_by_budget={4096: 94, 8192: 130},
        )
        self.assertFalse(overheads.wrapper_is_constant)
        self.assertEqual(overheads.wrapper_tokens, 130)
        text = format_measurement(
            [_row(budget_excluded=3)], overheads=overheads, window=16384,
            output_cap=6144, project_id="p1", llama_base_url="http://llama:9080",
            candidate_chars=7000,
        )
        self.assertIn("⚠ 예산마다 다르다", text)
        self.assertIn("4096:94", text)

    def test_it_reports_when_no_budget_fits_the_window(self):
        text = format_measurement(
            [_row(budget_excluded=3, input_tokens=12400)],
            overheads=self.overheads, window=8192, output_cap=6144,
            project_id="p1", llama_base_url="http://llama:9080",
            candidate_chars=7000,
        )
        self.assertIn("통과하는 예산이 없다", text)


class ArgumentTest(unittest.TestCase):
    def test_measuring_an_existing_project_requires_its_position(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--project-id", "p1"], run=lambda args, out: 0,
                 out=io.StringIO())
        self.assertEqual(raised.exception.code, 2)

    def test_seeding_needs_no_project_arguments(self):
        seen = {}

        def _run(args, out):
            seen["budgets"] = args.budgets
            return 0

        self.assertEqual(main(["--seed"], run=_run, out=io.StringIO()), 0)
        self.assertEqual(seen["budgets"], [2048, 4096, 6144, 8192])

    def test_budgets_must_be_positive(self):
        with self.assertRaises(SystemExit):
            build_arg_parser().parse_args(["--seed", "--budgets", "0,4096"])


if __name__ == "__main__":
    unittest.main()
