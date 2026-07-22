"""Versioned prompt template contract tests."""

import hashlib
import unittest

from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V1,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V2,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V3,
    ANALYSIS_EXTRACT_TASK_TYPE,
    ANALYSIS_EXTRACT_TEMPLATE,
    ANALYSIS_EXTRACT_TEMPLATE_V1,
    ANALYSIS_EXTRACT_TEMPLATE_V2,
    ANALYSIS_EXTRACT_TEMPLATE_V3,
    InMemoryPromptTemplateRepository,
    PromptTemplateConflict,
    PromptTemplateError,
    PromptTemplateNotFound,
    PromptTemplateService,
)

# Body digests of every already-seeded (immutable) prompt version. A deployed
# Mongo holds these exact bodies, and seed_template() raises
# PromptTemplateConflict when a stored version's body differs from the code's
# — which aborts create_app() and takes the whole stack down on restart.
# Editing a shipped body must therefore mint a NEW version instead. If this
# test fails, do not update the digest: add the next version.
_IMMUTABLE_TEMPLATE_DIGESTS = {
    ANALYSIS_EXTRACT_PROMPT_VERSION_V1: (
        "b142aa219ef38276172e0f1a04237e14aebf024b826bb39152c42344c2ad6ac7"
    ),
    ANALYSIS_EXTRACT_PROMPT_VERSION_V2: (
        "a6861944c61b80f22ede80dabf45ea189dd0bd825d61a955a10fe2c544b81034"
    ),
    ANALYSIS_EXTRACT_PROMPT_VERSION_V3: (
        "4376310080b4a3420be77cab53e27cc4cb3d89a9e93f136c2e908fcae27eb52a"
    ),
}


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

    def test_seed_analysis_extract_v4_is_current_and_keeps_v1_v2_v3(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        legacy = service.seed_analysis_extract_v1()
        v2 = service.seed_analysis_extract_v2()
        v3 = service.seed_analysis_extract_v3()
        current = service.seed_analysis_extract_v4()

        self.assertEqual(current.version, ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(current.template, ANALYSIS_EXTRACT_TEMPLATE)
        self.assertEqual(legacy.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V1)
        self.assertEqual(v2.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V2)
        self.assertEqual(v2.template, ANALYSIS_EXTRACT_TEMPLATE_V2)
        self.assertEqual(v3.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V3)
        self.assertEqual(v3.template, ANALYSIS_EXTRACT_TEMPLATE_V3)
        self.assertNotEqual(current.version, legacy.version)
        self.assertNotEqual(current.version, v3.version)
        self.assertIn("advisory provenance", current.template)
        self.assertIn("source_ref_catalog", current.template)

    def test_optional_character_aspect_guidance_is_v4_only(self):
        """The v1.7.23 aspect line belongs to v4; v3 stays as it was deployed.

        Under-strict: moving the aspect line back into V3 (the original
        defect) re-fails here. Over-strict: dropping it from V4 also fails,
        so the guidance cannot be silently lost while bumping the version.
        """
        self.assertIn('"aspect"', ANALYSIS_EXTRACT_TEMPLATE)
        self.assertNotIn('"aspect"', ANALYSIS_EXTRACT_TEMPLATE_V3)

    def test_shipped_template_bodies_are_immutable(self):
        """Editing an already-seeded body breaks restart on a deployed Mongo.

        A body change under an unchanged version raises PromptTemplateConflict
        inside create_app(), so application/worker/generation_worker all fail
        to boot against an existing database. Mint a new version instead.
        """
        bodies = {
            ANALYSIS_EXTRACT_PROMPT_VERSION_V1: ANALYSIS_EXTRACT_TEMPLATE_V1,
            ANALYSIS_EXTRACT_PROMPT_VERSION_V2: ANALYSIS_EXTRACT_TEMPLATE_V2,
            ANALYSIS_EXTRACT_PROMPT_VERSION_V3: ANALYSIS_EXTRACT_TEMPLATE_V3,
        }
        for version, expected_digest in _IMMUTABLE_TEMPLATE_DIGESTS.items():
            with self.subTest(version=version):
                digest = hashlib.sha256(bodies[version].encode()).hexdigest()
                self.assertEqual(digest, expected_digest)

    def test_seed_sequence_replays_against_previously_seeded_storage(self):
        """Restart against an existing deployment must not raise.

        This reproduces the 2026-07-22 boot failure: a store already holding
        v1..v3 from an earlier release, re-seeded by the current code.
        """
        repository = InMemoryPromptTemplateRepository()
        deployed = PromptTemplateService(repository)
        deployed.seed_analysis_extract_v1()
        deployed.seed_analysis_extract_v2()
        deployed.seed_analysis_extract_v3()

        restarted = PromptTemplateService(repository)
        restarted.seed_analysis_extract_v1()
        restarted.seed_analysis_extract_v2()
        restarted.seed_analysis_extract_v3()
        current = restarted.seed_analysis_extract_v4()

        self.assertEqual(current.version, ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(
            restarted.get_template(
                task_type=ANALYSIS_EXTRACT_TASK_TYPE,
                version=ANALYSIS_EXTRACT_PROMPT_VERSION_V3,
            ).template,
            ANALYSIS_EXTRACT_TEMPLATE_V3,
        )

    def test_seed_same_template_version_is_idempotent(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        first = service.seed_analysis_extract_v1()
        replay = service.seed_analysis_extract_v1()

        self.assertEqual(replay, first)

    def test_same_version_different_template_is_conflict(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())
        service.seed_analysis_extract_v4()

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
