"""Prompt assembly for Phase 2A analysis extraction."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

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
            "raw_text": snapshot.raw_text,
        },
        "writing_candidate_report": (
            _without_server_identifiers(snapshot.writing_candidate_report)
            if snapshot.writing_candidate_report is not None else None),
        # Keep the authoritative namespace after the advisory report in the
        # serialized prompt. Small local models overweight the last identifier
        # namespace they see; putting the current catalog here makes the
        # contract structural as well as instructional.
        "source_ref_catalog": [
            _source_ref_payload(index, ref)
            for index, ref in enumerate(source_refs)
        ],
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


def _source_ref_payload(index: int, source_ref: SourceRef) -> dict[str, object]:
    # v7: 영속 source_ref/block id는 모델 경계를 넘지 않는다. 순번은 이 요청의
    # 배열에서만 유효하고, 서버가 응답 순번을 원래 SourceRef로 되돌린다.
    return {
        "source_ref_index": index,
        "quote": source_ref.quote,
    }


_SERVER_IDENTIFIER_KEYS = {
    "project_id",
    "snapshot_id",
    "source_ref_id",
    "block_id",
    "document_id",
    "version_id",
    "content_hash",
}


def _without_server_identifiers(value: Any) -> Any:
    """Keep report semantics while removing storage pointers from the prompt."""
    if isinstance(value, Mapping):
        return {
            key: _without_server_identifiers(item)
            for key, item in value.items()
            if key not in _SERVER_IDENTIFIER_KEYS
            and key != "related_context_pointers"
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_without_server_identifiers(item) for item in value]
    return value
