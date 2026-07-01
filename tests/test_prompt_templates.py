"""Versioned prompt template contract tests."""

import unittest

from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_TASK_TYPE,
    ANALYSIS_EXTRACT_TEMPLATE,
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
            version=ANALYSIS_EXTRACT_PROMPT_VERSION,
        )

        self.assertEqual(fetched, seeded)
        self.assertEqual(fetched.template, ANALYSIS_EXTRACT_TEMPLATE)

    def test_seed_same_template_version_is_idempotent(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        first = service.seed_analysis_extract_v1()
        replay = service.seed_analysis_extract_v1()

        self.assertEqual(replay, first)

    def test_same_version_different_template_is_conflict(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v1()

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
