"""Prompt assembly for Phase 2A analysis extraction."""

from __future__ import annotations

import json

from services.application.app.analysis.models import SnapshotText
from services.application.app.analysis.prompt_templates import PromptTemplate
from services.application.app.core_sot.models import SourceRef
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage


class AnalysisPromptBuildError(ValueError):
    pass


def build_analysis_extract_request(
    *,
    snapshot: SnapshotText,
    source_refs: tuple[SourceRef, ...],
    prompt_template: PromptTemplate,
    model: str | None = None,
    max_tokens: int = 2048,
) -> ChatCompletionRequest:
    if not source_refs:
        raise AnalysisPromptBuildError("source_ref catalog is required")
    for source_ref in source_refs:
        if (
            source_ref.project_id != snapshot.project_id
            or source_ref.snapshot_id != snapshot.snapshot_id
            or source_ref.content_hash != snapshot.content_hash
        ):
            raise AnalysisPromptBuildError("source_ref catalog does not match snapshot")

    user_payload = {
        "task_type": prompt_template.task_type,
        "prompt_version": prompt_template.version,
        "snapshot": {
            "project_id": snapshot.project_id,
            "snapshot_id": snapshot.snapshot_id,
            "content_hash": snapshot.content_hash,
            "block_ids": list(snapshot.block_ids),
            "raw_text": snapshot.raw_text,
        },
        "source_ref_catalog": [_source_ref_payload(ref) for ref in source_refs],
        "output_contract": {
            "type": "json_object",
            "top_level_key": "candidates",
            "empty_result": {"candidates": []},
        },
    }
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=prompt_template.template),
            ChatMessage(
                role="user",
                content=json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
        model=model,
        max_tokens=max_tokens,
        thinking=False,
    )


def _source_ref_payload(source_ref: SourceRef) -> dict[str, object]:
    return {
        "source_ref_id": source_ref.id,
        "block_id": source_ref.block_id,
        "start_offset": source_ref.start_offset,
        "end_offset": source_ref.end_offset,
        "quote": source_ref.quote,
        "content_hash": source_ref.content_hash,
    }
