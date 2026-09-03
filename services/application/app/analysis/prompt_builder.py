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
        "writing_candidate_report": (
            dict(snapshot.writing_candidate_report)
            if snapshot.writing_candidate_report is not None else None),
        # Keep the authoritative namespace after the advisory report in the
        # serialized prompt. Small local models overweight the last identifier
        # namespace they see; putting the current catalog here makes the
        # contract structural as well as instructional.
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
                    separators=(",", ":"),
                ),
            ),
        ),
        model=model,
        max_tokens=max_tokens,
        thinking=False,
    )


def _source_ref_payload(source_ref: SourceRef) -> dict[str, object]:
    # 스키마 중복 전수조사 A(2026-09-03): 카탈로그 렌더는 모델이 근거를 고르는 데
    # 필요한 필드만 싣는다(id·블록·인용문). start/end offset과 content_hash는 모델에게
    # 무의미한 에코 원천이었고(v6 이전 출력 계약이 그대로 복사하게 했다) 이제 서버가
    # id로 조립하므로 렌더에서도 뺀다.
    return {
        "source_ref_id": source_ref.id,
        "block_id": source_ref.block_id,
        "quote": source_ref.quote,
    }
