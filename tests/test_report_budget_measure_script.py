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


class FormatTest(unittest.TestCase):
    def setUp(self):
        self.overheads = Overheads(
            system_tokens=465, candidate_tokens=4096, wrapper_tokens=150,
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
