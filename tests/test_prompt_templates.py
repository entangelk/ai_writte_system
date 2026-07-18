"""Versioned prompt template contract tests."""

import unittest

from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V1,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V2,
    ANALYSIS_EXTRACT_TASK_TYPE,
    ANALYSIS_EXTRACT_TEMPLATE,
    ANALYSIS_EXTRACT_TEMPLATE_V1,
    ANALYSIS_EXTRACT_TEMPLATE_V2,
    InMemoryPromptTemplateRepository,
    PromptTemplateConflict,
    PromptTemplateError,
    PromptTemplateNotFound,
    PromptTemplateService,
)


class PromptTemplateServiceTest(unittest.TestCase):
    def test_seed_analysis_extract_v1_and_fetch_by_version(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        seeded = service.seed_analysis_extract_v1()
        fetched = service.get_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V1,
        )

        self.assertEqual(fetched, seeded)
        self.assertEqual(fetched.template, ANALYSIS_EXTRACT_TEMPLATE_V1)

    def test_seed_analysis_extract_v3_is_current_and_keeps_v1_v2(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        legacy = service.seed_analysis_extract_v1()
        v2 = service.seed_analysis_extract_v2()
        current = service.seed_analysis_extract_v3()

        self.assertEqual(current.version, ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(current.template, ANALYSIS_EXTRACT_TEMPLATE)
        self.assertEqual(legacy.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V1)
        self.assertEqual(v2.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V2)
        self.assertEqual(v2.template, ANALYSIS_EXTRACT_TEMPLATE_V2)
        self.assertNotEqual(current.version, legacy.version)
        self.assertIn("advisory provenance", current.template)
        self.assertIn("source_ref_catalog", current.template)

    def test_seed_same_template_version_is_idempotent(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        first = service.seed_analysis_extract_v1()
        replay = service.seed_analysis_extract_v1()

        self.assertEqual(replay, first)

    def test_same_version_different_template_is_conflict(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v3()

        with self.assertRaises(PromptTemplateConflict):
            service.seed_template(
                task_type=ANALYSIS_EXTRACT_TASK_TYPE,
                version=ANALYSIS_EXTRACT_PROMPT_VERSION,
                template="different template",
            )

    def test_missing_template_is_explicit_not_found(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        with self.assertRaises(PromptTemplateNotFound):
            service.get_template(
                task_type=ANALYSIS_EXTRACT_TASK_TYPE,
                version=ANALYSIS_EXTRACT_PROMPT_VERSION,
            )

    def test_template_identity_fields_must_be_non_empty_strings(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        with self.assertRaises(PromptTemplateError):
            service.seed_template(task_type="", version="v1", template="template")
        with self.assertRaises(PromptTemplateError):
            service.seed_template(task_type="task", version="", template="template")
        with self.assertRaises(PromptTemplateError):
            service.seed_template(task_type="task", version="v1", template="")


if __name__ == "__main__":
    unittest.main()
