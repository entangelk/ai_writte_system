"""Versioned prompt template contract tests."""

import hashlib
import unittest

from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V1,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V2,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V3,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V4,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V5,
    ANALYSIS_EXTRACT_TASK_TYPE,
    ANALYSIS_EXTRACT_TEMPLATE,
    ANALYSIS_EXTRACT_TEMPLATE_V1,
    ANALYSIS_EXTRACT_TEMPLATE_V2,
    ANALYSIS_EXTRACT_TEMPLATE_V3,
    ANALYSIS_EXTRACT_TEMPLATE_V4,
    ANALYSIS_EXTRACT_TEMPLATE_V5,
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
    # v4는 **현행 버전**이라 더더욱 핀이 필요하다(2026-07-30에 빠져 있는 것을 발견).
    # 옛 버전은 이제 아무도 고칠 이유가 없지만 현행 본문은 고칠 이유가 늘 있고, 고치는
    # 순간 **기존 Mongo를 가진 배포가 전부 부팅에 실패**한다 — 핀이 없으면 그 사실을
    # 배포에서야 알게 된다(2026-07-22·07-27에 실제로 그렇게 잃었다).
    ANALYSIS_EXTRACT_PROMPT_VERSION_V4: (
        "b946a70514de99c2fbe84fbef1f1e41cd6086e496fb0a2642cffa6045e3fd6bd"
    ),
    # v5 (2026-08-23): 펜스 금지 명시 — v6 등장으로 출시 동결본이 됐다.
    ANALYSIS_EXTRACT_PROMPT_VERSION_V5: (
        "bc2a0b126fe3342a31da2fcc566cd29eb5557ea83add13838dbc290400834751"
    ),
    # v6 (2026-09-03, 스키마 중복 전수조사 A): source_anchors id-선택 계약 — 현행
    # 버전이라 더더욱 핀이 필요하다(고치는 순간 기존 Mongo 배포가 부팅에 실패한다).
    ANALYSIS_EXTRACT_PROMPT_VERSION: (
        "7e2c5f93f5a53c276af93472906da9d0ccb619d6aba50b0b2e58649835be4c3a"
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

    def test_seed_analysis_extract_v6_is_current_and_keeps_v1_through_v5(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        legacy = service.seed_analysis_extract_v1()
        v2 = service.seed_analysis_extract_v2()
        v3 = service.seed_analysis_extract_v3()
        v4 = service.seed_analysis_extract_v4()
        v5 = service.seed_analysis_extract_v5()
        current = service.seed_analysis_extract_v6()

        self.assertEqual(current.version, ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(current.template, ANALYSIS_EXTRACT_TEMPLATE)
        self.assertEqual(v4.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V4)
        self.assertEqual(v4.template, ANALYSIS_EXTRACT_TEMPLATE_V4)
        self.assertEqual(v5.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V5)
        self.assertEqual(v5.template, ANALYSIS_EXTRACT_TEMPLATE_V5)
        self.assertEqual(legacy.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V1)
        self.assertEqual(v2.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V2)
        self.assertEqual(v2.template, ANALYSIS_EXTRACT_TEMPLATE_V2)
        self.assertEqual(v3.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V3)
        self.assertEqual(v3.template, ANALYSIS_EXTRACT_TEMPLATE_V3)
        self.assertNotEqual(current.version, legacy.version)
        self.assertNotEqual(current.version, v3.version)
        self.assertNotEqual(current.version, v5.version)
        self.assertIn("advisory provenance", current.template)
        self.assertIn("source_ref_catalog", current.template)

    def test_v6_output_contract_asks_for_ids_only(self):
        """스키마 중복 전수조사 A의 프롬프트 축. 양방향: v6은 id-선택만 가르치고
        (under-strict — 복사 지시가 돌아오면 문다), v5 동결본은 그대로 남아 있다
        (over-strict — 동결본을 몰래 고쳐 v6과 맞추면 문다)."""
        self.assertIn(
            '{"source_ref_id": "..."}', ANALYSIS_EXTRACT_TEMPLATE)
        self.assertNotIn("must copy source_ref_id", ANALYSIS_EXTRACT_TEMPLATE)
        self.assertIn(
            "must copy source_ref_id, start_offset, end_offset, quote, and content_hash",
            ANALYSIS_EXTRACT_TEMPLATE_V5)

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
            ANALYSIS_EXTRACT_PROMPT_VERSION_V4: ANALYSIS_EXTRACT_TEMPLATE_V4,
            ANALYSIS_EXTRACT_PROMPT_VERSION_V5: ANALYSIS_EXTRACT_TEMPLATE_V5,
            ANALYSIS_EXTRACT_PROMPT_VERSION: ANALYSIS_EXTRACT_TEMPLATE,
        }
        # 핀 목록이 **출시된 버전 전부**를 덮는지 함께 본다. v4가 빠져 있던 것을
        # 2026-07-30에 발견했는데, 빠진 줄을 알아채는 유일한 방법이 이 단정이다.
        self.assertEqual(set(_IMMUTABLE_TEMPLATE_DIGESTS), set(bodies))
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
        current = restarted.seed_analysis_extract_v6()

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
                version=ANALYSIS_EXTRACT_PROMPT_VERSION_V4,
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
