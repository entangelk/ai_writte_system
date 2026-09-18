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
    ANALYSIS_EXTRACT_PROMPT_VERSION_V6,
    ANALYSIS_EXTRACT_PROMPT_VERSION_V7,
    ANALYSIS_EXTRACT_TASK_TYPE,
    ANALYSIS_EXTRACT_TEMPLATE,
    ANALYSIS_EXTRACT_TEMPLATE_V1,
    ANALYSIS_EXTRACT_TEMPLATE_V2,
    ANALYSIS_EXTRACT_TEMPLATE_V3,
    ANALYSIS_EXTRACT_TEMPLATE_V4,
    ANALYSIS_EXTRACT_TEMPLATE_V5,
    ANALYSIS_EXTRACT_TEMPLATE_V6,
    ANALYSIS_EXTRACT_TEMPLATE_V7,
    InMemoryPromptTemplateRepository,
    PromptTemplateConflict,
    PromptTemplateError,
    PromptTemplateNotFound,
    PromptTemplateService,
)
from services.application.app.analysis.compare_judge import (
    ANALYSIS_COMPARE_PROMPT_VERSION,
    ANALYSIS_COMPARE_PROMPT_VERSION_V1,
    ANALYSIS_COMPARE_TEMPLATE,
    ANALYSIS_COMPARE_TEMPLATE_V1,
)
from services.application.app.analysis.identity_judge import (
    ANALYSIS_IDENTITY_PROMPT_VERSION,
    ANALYSIS_IDENTITY_PROMPT_VERSION_V1,
    ANALYSIS_IDENTITY_TEMPLATE,
    ANALYSIS_IDENTITY_TEMPLATE_V1,
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
    # v6 (2026-09-03): id-선택 계약 — v7 등장으로 출시 동결본이다.
    ANALYSIS_EXTRACT_PROMPT_VERSION_V6: (
        "7e2c5f93f5a53c276af93472906da9d0ccb619d6aba50b0b2e58649835be4c3a"
    ),
    # v7 (2026-09-17): 실제 source_ref id를 LLM 경계 밖으로 이동 — v8 등장으로
    # 출시 동결본이다.
    ANALYSIS_EXTRACT_PROMPT_VERSION_V7: (
        "443b0ea3199733477e16476e32a623253fbb7dccbca8faac4fc37e00e9a999dc"
    ),
    # v8 (2026-09-18): 추출 payload 문장 필드의 출력 언어를 한국어로 고정(현행).
    ANALYSIS_EXTRACT_PROMPT_VERSION: (
        "cb041faaa153ef25e122de10f81549fe4f80649a43112034d9d252325d406ad7"
    ),
}

# 판단자 축도 같은 계약 아래 있다 — 배포 Mongo가 v1 본문을 저장했으므로
# 코드에서 v1 본문을 고치면 재기동 시 PromptTemplateConflict 로 부팅이 죽는다
# (extract 축과 완전히 같은 실패 방식). 2026-09-18 v2 등장으로 v1 은 동결본이다.
_IMMUTABLE_JUDGE_DIGESTS = {
    ANALYSIS_COMPARE_PROMPT_VERSION_V1: (
        ANALYSIS_COMPARE_TEMPLATE_V1,
        "3b05f540cf672a61e0769dbc543f108f07780b32bba115fc9a0235f6c4e65543",
    ),
    ANALYSIS_IDENTITY_PROMPT_VERSION_V1: (
        ANALYSIS_IDENTITY_TEMPLATE_V1,
        "1178931acf35e690f8ed2fcb67be9935203c6c975a0f7f4422a45876187af783",
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

    def test_seed_analysis_extract_v8_is_current_and_keeps_v1_through_v7(self):
        service = PromptTemplateService(InMemoryPromptTemplateRepository())

        legacy = service.seed_analysis_extract_v1()
        v2 = service.seed_analysis_extract_v2()
        v3 = service.seed_analysis_extract_v3()
        v4 = service.seed_analysis_extract_v4()
        v5 = service.seed_analysis_extract_v5()
        v6 = service.seed_analysis_extract_v6()
        v7 = service.seed_analysis_extract_v7()
        current = service.seed_analysis_extract_v8()

        self.assertEqual(current.version, ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(current.template, ANALYSIS_EXTRACT_TEMPLATE)
        self.assertEqual(v4.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V4)
        self.assertEqual(v4.template, ANALYSIS_EXTRACT_TEMPLATE_V4)
        self.assertEqual(v5.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V5)
        self.assertEqual(v5.template, ANALYSIS_EXTRACT_TEMPLATE_V5)
        self.assertEqual(v6.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V6)
        self.assertEqual(v6.template, ANALYSIS_EXTRACT_TEMPLATE_V6)
        self.assertEqual(v7.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V7)
        self.assertEqual(v7.template, ANALYSIS_EXTRACT_TEMPLATE_V7)
        self.assertEqual(legacy.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V1)
        self.assertEqual(v2.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V2)
        self.assertEqual(v2.template, ANALYSIS_EXTRACT_TEMPLATE_V2)
        self.assertEqual(v3.version, ANALYSIS_EXTRACT_PROMPT_VERSION_V3)
        self.assertEqual(v3.template, ANALYSIS_EXTRACT_TEMPLATE_V3)
        self.assertNotEqual(current.version, legacy.version)
        self.assertNotEqual(current.version, v3.version)
        self.assertNotEqual(current.version, v5.version)
        self.assertNotEqual(current.version, v7.version)
        self.assertIn("advisory provenance", current.template)
        self.assertIn("source_ref_catalog", current.template)

    def test_current_output_contract_uses_indexes_and_keeps_v6_v7_frozen(self):
        """현행(v8)도 서버 id를 숨기고, 배포된 v6·v7 본문은 그대로 보존한다."""
        self.assertIn(
            '{"source_ref_index": 0}', ANALYSIS_EXTRACT_TEMPLATE)
        self.assertNotIn("source_ref_id", ANALYSIS_EXTRACT_TEMPLATE)
        self.assertIn("server-owned", ANALYSIS_EXTRACT_TEMPLATE)
        self.assertIn(
            '{"source_ref_index": 0}', ANALYSIS_EXTRACT_TEMPLATE_V7)
        self.assertIn(
            '{"source_ref_id": "..."}', ANALYSIS_EXTRACT_TEMPLATE_V6)

    def test_v8_writes_payload_text_in_korean_and_v7_stays_english_neutral(self):
        """v8 (2026-09-18): 추출 문장 필드는 한국어 — 오너 관측(검토함에 영어로
        노출됨)의 원천 수정.

        Under-strict: 한국어 지시 문장을 v8에서 빼면 실패한다(회귀되돌림).
        Over-strict: 동결된 v7 본문에 같은 지시를 역수입하면 v7 단정이 실패한다
        — 이미 배포된 Mongo 가 저장한 본문을 고치는 것이므로 부팅 결함이다.
        """
        self.assertIn("in Korean", ANALYSIS_EXTRACT_TEMPLATE)
        self.assertIn("observation", ANALYSIS_EXTRACT_TEMPLATE)
        self.assertNotIn("in Korean", ANALYSIS_EXTRACT_TEMPLATE_V7)

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
            ANALYSIS_EXTRACT_PROMPT_VERSION_V6: ANALYSIS_EXTRACT_TEMPLATE_V6,
            ANALYSIS_EXTRACT_PROMPT_VERSION_V7: ANALYSIS_EXTRACT_TEMPLATE_V7,
            ANALYSIS_EXTRACT_PROMPT_VERSION: ANALYSIS_EXTRACT_TEMPLATE,
        }
        # 핀 목록이 **출시된 버전 전부**를 덮는지 함께 본다. v4가 빠져 있던 것을
        # 2026-07-30에 발견했는데, 빠진 줄을 알아채는 유일한 방법이 이 단정이다.
        self.assertEqual(set(_IMMUTABLE_TEMPLATE_DIGESTS), set(bodies))
        for version, expected_digest in _IMMUTABLE_TEMPLATE_DIGESTS.items():
            with self.subTest(version=version):
                digest = hashlib.sha256(bodies[version].encode()).hexdigest()
                self.assertEqual(digest, expected_digest)

    def test_shipped_judge_template_bodies_are_immutable(self):
        """판단자 v1 본문도 배포 Mongo 가 저장했다 — 고치면 재기동이 죽는다.

        Under-strict: v1 본문을 고치면 다이제스트가 갈라져 실패한다.
        Over-strict: v2 가 등장해도 v1 핀이 사라지면 안 되므로, 이 표가
        채우는 키 셋 자체를 늘리지 않는 한 그대로 둬야 실패하지 않는다.
        """
        for version, (body, expected_digest) in _IMMUTABLE_JUDGE_DIGESTS.items():
            with self.subTest(version=version):
                digest = hashlib.sha256(body.encode()).hexdigest()
                self.assertEqual(digest, expected_digest)

    def test_judge_rationales_are_korean_in_current_and_frozen_in_v1(self):
        """v2 (2026-09-18): 판단 근거(rationale)는 검토함 그룹 행·상세에서 사용자에게
        그대로 노출되므로 한국어로 생성한다.

        Under-strict: v2 본문에서 한국어 지시를 빼면 실패한다(회귀되돌림).
        Over-strict: 동결 v1 본문에 지시를 역수입하면 v1 단정이 실패한다 —
        배포 Mongo 가 저장한 본문을 고치면 재기동이 죽는다.
        """
        self.assertEqual(ANALYSIS_COMPARE_PROMPT_VERSION, "analysis_compare_v2")
        self.assertEqual(ANALYSIS_IDENTITY_PROMPT_VERSION, "analysis_identity_v2")
        self.assertIn("written in Korean", ANALYSIS_COMPARE_TEMPLATE)
        self.assertIn("written in Korean", ANALYSIS_IDENTITY_TEMPLATE)
        self.assertNotIn("written in Korean", ANALYSIS_COMPARE_TEMPLATE_V1)
        self.assertNotIn("written in Korean", ANALYSIS_IDENTITY_TEMPLATE_V1)

    def test_judge_seed_replays_both_versions_against_deployed_storage(self):
        """seed 함수는 v1(동결)·v2(현행) 둘 다 시드한다 — 배포 Mongo 재기동 재현."""
        from services.application.app.analysis.compare_judge import (
            seed_analysis_compare_template,
        )
        from services.application.app.analysis.identity_judge import (
            seed_analysis_identity_judge_template,
        )

        repository = InMemoryPromptTemplateRepository()
        deployed = PromptTemplateService(repository)
        seed_analysis_compare_template(deployed)
        seed_analysis_identity_judge_template(deployed)

        restarted = PromptTemplateService(repository)
        seed_analysis_compare_template(restarted)
        current = seed_analysis_identity_judge_template(restarted)

        self.assertEqual(current.version, ANALYSIS_IDENTITY_PROMPT_VERSION)
        self.assertEqual(
            restarted.get_template(
                task_type="analysis_compare",
                version=ANALYSIS_COMPARE_PROMPT_VERSION_V1,
            ).template,
            ANALYSIS_COMPARE_TEMPLATE_V1,
        )

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
        deployed.seed_analysis_extract_v4()
        deployed.seed_analysis_extract_v5()
        deployed.seed_analysis_extract_v6()
        deployed.seed_analysis_extract_v7()

        restarted = PromptTemplateService(repository)
        restarted.seed_analysis_extract_v1()
        restarted.seed_analysis_extract_v2()
        restarted.seed_analysis_extract_v3()
        restarted.seed_analysis_extract_v4()
        restarted.seed_analysis_extract_v5()
        restarted.seed_analysis_extract_v6()
        restarted.seed_analysis_extract_v7()
        current = restarted.seed_analysis_extract_v8()

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
