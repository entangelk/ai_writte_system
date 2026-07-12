"""Prompt assembly tests for Phase 2A provider wiring."""

import json
import unittest

from services.application.app.analysis.models import SnapshotText
from services.application.app.analysis.prompt_builder import (
    AnalysisPromptBuildError,
    build_analysis_extract_request,
)
from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_TASK_TYPE,
    PromptTemplateService,
    InMemoryPromptTemplateRepository,
)
from services.application.app.core_sot.models import SourceRef


class AnalysisPromptBuilderTest(unittest.TestCase):
    def test_build_request_contains_template_snapshot_and_source_ref_catalog(self):
        template = PromptTemplateService(
            InMemoryPromptTemplateRepository()
        ).seed_analysis_extract_v1()
        snapshot = SnapshotText(
            project_id="project-1",
            snapshot_id="snapshot-1",
            raw_text="민아는 파란 편지를 발견했다.",
            content_hash="hash-1",
            block_ids=("block-1",),
        )
        source_ref = SourceRef(
            id="source-ref-1",
            project_id="project-1",
            snapshot_id="snapshot-1",
            block_id="block-1",
            start_offset=0,
            end_offset=2,
            quote="민아",
            content_hash="hash-1",
        )

        request = build_analysis_extract_request(
            snapshot=snapshot,
            source_refs=(source_ref,),
            prompt_template=template,
            model="gemma",
            max_tokens=512,
        )

        self.assertEqual(request.model, "gemma")
        self.assertEqual(request.max_tokens, 512)
        self.assertFalse(request.thinking)
        self.assertEqual(request.messages[0].role, "system")
        self.assertEqual(request.messages[0].content, template.template)
        payload = json.loads(request.messages[1].content)
        self.assertEqual(payload["task_type"], ANALYSIS_EXTRACT_TASK_TYPE)
        self.assertEqual(payload["prompt_version"], ANALYSIS_EXTRACT_PROMPT_VERSION)
        self.assertEqual(payload["snapshot"]["raw_text"], snapshot.raw_text)
        self.assertEqual(
            payload["source_ref_catalog"],
            [
                {
                    "source_ref_id": "source-ref-1",
                    "block_id": "block-1",
                    "start_offset": 0,
                    "end_offset": 2,
                    "quote": "민아",
                    "content_hash": "hash-1",
                }
            ],
        )
        self.assertEqual(payload["output_contract"]["top_level_key"], "candidates")

    def test_build_request_includes_writing_candidate_report_when_present(self):
        # v1.6.71 보강 (B2): when the runner attaches an advisory report, the
        # extract prompt surfaces it so analysis consumes the report as an
        # advisory input. Removing the inclusion re-fails this test.
        template = PromptTemplateService(
            InMemoryPromptTemplateRepository()
        ).seed_analysis_extract_v1()
        report = {"risk_notes": [
            {"type": "pov", "severity": "high", "message": "시점"}]}
        snapshot = SnapshotText(
            project_id="project-1",
            snapshot_id="snapshot-1",
            raw_text="민아는 파란 편지를 발견했다.",
            content_hash="hash-1",
            block_ids=("block-1",),
            writing_candidate_report=report,
        )
        source_ref = SourceRef(
            id="source-ref-1",
            project_id="project-1",
            snapshot_id="snapshot-1",
            block_id="block-1",
            start_offset=0,
            end_offset=2,
            quote="민아",
            content_hash="hash-1",
        )
        request = build_analysis_extract_request(
            snapshot=snapshot,
            source_refs=(source_ref,),
            prompt_template=template,
        )
        payload = json.loads(request.messages[1].content)
        self.assertEqual(payload["writing_candidate_report"], report)

    def test_build_request_omits_writing_candidate_report_when_absent(self):
        # over-strict guard: a snapshot without a report yields null, not a
        # KeyError — analysis runs normally for legacy accepts that carry no
        # candidate report.
        template = PromptTemplateService(
            InMemoryPromptTemplateRepository()
        ).seed_analysis_extract_v1()
        snapshot = SnapshotText(
            project_id="project-1",
            snapshot_id="snapshot-1",
            raw_text="민아는 파란 편지를 발견했다.",
            content_hash="hash-1",
            block_ids=("block-1",),
        )
        source_ref = SourceRef(
            id="source-ref-1",
            project_id="project-1",
            snapshot_id="snapshot-1",
            block_id="block-1",
            start_offset=0,
            end_offset=2,
            quote="민아",
            content_hash="hash-1",
        )
        request = build_analysis_extract_request(
            snapshot=snapshot,
            source_refs=(source_ref,),
            prompt_template=template,
        )
        payload = json.loads(request.messages[1].content)
        self.assertIsNone(payload["writing_candidate_report"])

    def test_empty_source_ref_catalog_is_explicit_error(self):
        template = PromptTemplateService(
            InMemoryPromptTemplateRepository()
        ).seed_analysis_extract_v1()
        snapshot = SnapshotText(
            project_id="project-1",
            snapshot_id="snapshot-1",
            raw_text="text",
            content_hash="hash-1",
            block_ids=("block-1",),
        )

        with self.assertRaises(AnalysisPromptBuildError):
            build_analysis_extract_request(
                snapshot=snapshot,
                source_refs=(),
                prompt_template=template,
            )

    def test_cross_snapshot_source_ref_is_rejected_before_provider_call(self):
        template = PromptTemplateService(
            InMemoryPromptTemplateRepository()
        ).seed_analysis_extract_v1()
        snapshot = SnapshotText(
            project_id="project-1",
            snapshot_id="snapshot-1",
            raw_text="text",
            content_hash="hash-1",
            block_ids=("block-1",),
        )
        source_ref = SourceRef(
            id="source-ref-1",
            project_id="project-1",
            snapshot_id="snapshot-2",
            block_id="block-1",
            start_offset=0,
            end_offset=4,
            quote="text",
            content_hash="hash-1",
        )

        with self.assertRaises(AnalysisPromptBuildError):
            build_analysis_extract_request(
                snapshot=snapshot,
                source_refs=(source_ref,),
                prompt_template=template,
            )


if __name__ == "__main__":
    unittest.main()
