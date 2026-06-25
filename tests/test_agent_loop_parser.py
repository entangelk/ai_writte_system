"""Contract tests for provider-response self-report parsing.

Locks the Phase 4 parser-slice wire format for the loop termination channel:
provider content is a JSON object with a top-level ``self_report`` field whose
value is exactly ``finalize`` or ``defer``. The tests guard both directions:

* should-fire: exact top-level literals parse to the matching SelfReport.
* should-NOT-fire: missing, malformed, non-string, case-varied, and artifact-
  nested signals are rejected instead of being defaulted or inferred.
"""

import unittest

from services.application.app.agent_loop.completion import SelfReport
from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.parser import (
    InvalidSelfReport,
    parse_self_report_payload,
)


class SelfReportParserTest(unittest.TestCase):
    def test_top_level_finalize_parses(self):
        self.assertEqual(
            parse_self_report_payload(
                '{"self_report":"finalize","artifact":{"status":"needs_review"}}'
            ),
            SelfReport.FINALIZE,
        )

    def test_top_level_defer_parses(self):
        self.assertEqual(
            parse_self_report_payload('{"self_report":"defer","artifact":{}}'),
            SelfReport.DEFER,
        )

    def test_invalid_self_report_classifies_as_provider_error(self):
        self.assertEqual(InvalidSelfReport.decision, LoopDecision.PROVIDER_ERROR)

    def test_missing_self_report_is_not_defaulted_to_finalize(self):
        with self.assertRaises(InvalidSelfReport):
            parse_self_report_payload('{"artifact":{"status":"ready"}}')

    def test_non_json_or_non_object_content_is_invalid(self):
        for content in ("not-json", "[]"):
            with self.subTest(content=content):
                with self.assertRaises(InvalidSelfReport):
                    parse_self_report_payload(content)

    def test_non_string_self_report_is_invalid(self):
        for content in ('{"self_report":true}', '{"self_report":null}'):
            with self.subTest(content=content):
                with self.assertRaises(InvalidSelfReport):
                    parse_self_report_payload(content)

    def test_case_variants_are_not_coerced(self):
        with self.assertRaises(InvalidSelfReport):
            parse_self_report_payload('{"self_report":"Finalize"}')

    def test_wrong_literal_typo_is_invalid(self):
        with self.assertRaises(InvalidSelfReport):
            parse_self_report_payload('{"self_report":"done"}')

    def test_artifact_nested_self_report_is_not_termination_channel(self):
        with self.assertRaises(InvalidSelfReport):
            parse_self_report_payload(
                '{"artifact":{"self_report":"finalize","status":"needs_review"}}'
            )


if __name__ == "__main__":
    unittest.main()
