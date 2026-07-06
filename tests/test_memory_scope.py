import unittest

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.memory.scope import (
    MemoryScope,
    derive_scope,
    normalize_name,
)


CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
EVENT = AnalysisCandidateType.EVENT_OBSERVATION
OPEN_QUESTION = AnalysisCandidateType.OPEN_QUESTION_OBSERVATION


class DeriveScopeTest(unittest.TestCase):
    def test_character_scope_over_normalized_name(self):
        scope = derive_scope(CHARACTER, {"name": "  Ariel ", "observation": "x"})
        self.assertEqual(scope, MemoryScope(scope_type="character", scope_id="ariel"))

    def test_name_normalization_is_case_and_whitespace_insensitive(self):
        a = derive_scope(CHARACTER, {"name": "Ariel Song", "observation": "x"})
        b = derive_scope(CHARACTER, {"name": "  ariel   song ", "observation": "y"})
        self.assertEqual(a, b)

    def test_event_has_no_deterministic_scope(self):
        # D2=A: event carries only descriptive text, no entity id.
        self.assertIsNone(derive_scope(EVENT, {"event": "the storm hit"}))

    def test_open_question_has_no_deterministic_scope(self):
        self.assertIsNone(
            derive_scope(OPEN_QUESTION, {"question": "who is the traitor?"})
        )

    def test_normalize_name_direct(self):
        self.assertEqual(normalize_name("  Foo   Bar "), "foo bar")


if __name__ == "__main__":
    unittest.main()
