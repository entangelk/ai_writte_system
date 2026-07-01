"""Provider-backed Phase 2A extraction adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any, Protocol

from services.application.app.analysis.prompt_builder import (
    AnalysisPromptBuildError,
    build_analysis_extract_request,
)
from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
    CandidateSourceAnchor,
    SnapshotText,
)
from services.application.app.analysis.prompt_templates import (
    ANALYSIS_EXTRACT_PROMPT_VERSION,
    ANALYSIS_EXTRACT_TASK_TYPE,
    PromptTemplateError,
    PromptTemplateService,
)
from services.application.app.analysis.schema import validate_candidate_payload
from services.application.app.analysis.schema import InvalidAnalysisPayload
from services.application.app.core_sot.models import SourceRef
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.llm_gateway.app.provider import LLMProvider


class AnalysisExtractionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisCandidateDraft:
    candidate_type: AnalysisCandidateType
    provenance: AnalysisProvenance
    confidence: float
    source_anchors: tuple[CandidateSourceAnchor, ...]
    payload: Mapping[str, Any]
    logical_key: str


class AnalysisExtractionAdapter:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens

    async def extract(self, snapshot: SnapshotText) -> tuple[AnalysisCandidateDraft, ...]:
        result = await self._provider.generate(
            ChatCompletionRequest(
                messages=(
                    ChatMessage(
                        role="system",
                        content=(
                            "Return Phase 2A analysis JSON with a top-level "
                            "candidates array."
                        ),
                    ),
                    ChatMessage(role="user", content=snapshot.raw_text),
                ),
                model=self._model,
                max_tokens=self._max_tokens,
                thinking=False,
            )
        )
        return parse_analysis_extraction(result.content)


class SourceRefCatalog(Protocol):
    def list_source_refs(
        self, *, project_id: str, snapshot_id: str
    ) -> tuple[SourceRef, ...]: ...


class VersionedPromptAnalysisExtractionAdapter:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_templates: PromptTemplateService,
        source_ref_catalog: SourceRefCatalog,
        task_type: str = ANALYSIS_EXTRACT_TASK_TYPE,
        prompt_version: str = ANALYSIS_EXTRACT_PROMPT_VERSION,
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> None:
        self._provider = provider
        self._prompt_templates = prompt_templates
        self._source_ref_catalog = source_ref_catalog
        self._task_type = task_type
        self._prompt_version = prompt_version
        self._model = model
        self._max_tokens = max_tokens

    async def extract(self, snapshot: SnapshotText) -> tuple[AnalysisCandidateDraft, ...]:
        try:
            prompt_template = self._prompt_templates.get_template(
                task_type=self._task_type,
                version=self._prompt_version,
            )
            source_refs = self._source_ref_catalog.list_source_refs(
                project_id=snapshot.project_id,
                snapshot_id=snapshot.snapshot_id,
            )
            request = build_analysis_extract_request(
                snapshot=snapshot,
                source_refs=source_refs,
                prompt_template=prompt_template,
                model=self._model,
                max_tokens=self._max_tokens,
            )
        except (PromptTemplateError, AnalysisPromptBuildError) as exc:
            raise AnalysisExtractionError(str(exc)) from exc

        result = await self._provider.generate(request)
        try:
            return parse_analysis_extraction(result.content)
        except AnalysisExtractionError as first_error:
            repair = await self._provider.generate(
                _repair_request(
                    original_request=request,
                    invalid_content=result.content,
                    parser_error=str(first_error),
                )
            )
            try:
                return parse_analysis_extraction(repair.content)
            except AnalysisExtractionError as repair_error:
                raise repair_error from first_error


def parse_analysis_extraction(content: str) -> tuple[AnalysisCandidateDraft, ...]:
    root = _json_object(content)
    raw_candidates = root.get("candidates")
    if not isinstance(raw_candidates, list):
        raise AnalysisExtractionError("candidates must be an array")
    return tuple(_candidate_draft(item) for item in raw_candidates)


_REPAIR_SYSTEM_PROMPT = """Repair Phase 2A analysis extraction output.

Return valid JSON only. Do not wrap the JSON in markdown fences. Do not add prose.

The output must be one object with top-level key "candidates".
Each candidate must contain exactly these fields:
- candidate_type: one of character_observation, event_observation, open_question_observation
- provenance: source_observed or ai_inferred
- confidence: number from 0.0 to 1.0
- source_anchors: non-empty array of catalog anchors, preserving source_ref_id, start_offset, end_offset, quote, content_hash
- payload: character_observation requires {"name": "...", "observation": "..."}; event_observation requires {"event": "..."}; open_question_observation requires {"question": "..."}

Use only source_ref_id values from the original source_ref catalog. If no valid candidate can be produced, return {"candidates":[]}.
"""


def _repair_request(
    *,
    original_request: ChatCompletionRequest,
    invalid_content: str,
    parser_error: str,
) -> ChatCompletionRequest:
    payload = {
        "parser_error": parser_error,
        "invalid_output": invalid_content,
        "original_user_payload": original_request.messages[-1].content,
    }
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=_REPAIR_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ),
        model=original_request.model,
        temperature=original_request.temperature,
        top_p=original_request.top_p,
        max_tokens=original_request.max_tokens,
        thinking=False,
        chat_template_kwargs=original_request.chat_template_kwargs,
    )


def _candidate_draft(item: object) -> AnalysisCandidateDraft:
    if not isinstance(item, Mapping):
        raise AnalysisExtractionError("candidate must be an object")
    _require_fields(
        item,
        {
            "candidate_type",
            "provenance",
            "confidence",
            "source_anchors",
            "payload",
        },
    )
    candidate_type = _candidate_type(item["candidate_type"])
    provenance = _provenance(item["provenance"])
    confidence = _confidence(item["confidence"])
    source_anchors = _source_anchors(item["source_anchors"])
    try:
        payload = validate_candidate_payload(candidate_type, item["payload"])
    except InvalidAnalysisPayload as exc:
        raise AnalysisExtractionError(str(exc)) from exc
    return AnalysisCandidateDraft(
        candidate_type=candidate_type,
        provenance=provenance,
        confidence=confidence,
        source_anchors=source_anchors,
        payload=payload,
        logical_key=_logical_key(
            candidate_type=candidate_type,
            source_anchors=source_anchors,
            payload=payload,
        ),
    )


def _json_object(content: str) -> Mapping[str, object]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisExtractionError("provider content must be JSON") from exc
    if not isinstance(payload, Mapping):
        raise AnalysisExtractionError("provider content must be a JSON object")
    return payload


def _require_fields(payload: Mapping[str, object], required: set[str]) -> None:
    if set(payload.keys()) != required:
        raise AnalysisExtractionError("candidate fields do not match schema")


def _candidate_type(value: object) -> AnalysisCandidateType:
    try:
        return AnalysisCandidateType(value)
    except ValueError as exc:
        raise AnalysisExtractionError("unsupported analysis candidate type") from exc


def _provenance(value: object) -> AnalysisProvenance:
    try:
        return AnalysisProvenance(value)
    except ValueError as exc:
        raise AnalysisExtractionError("unsupported analysis provenance") from exc


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise AnalysisExtractionError("confidence must be a number")
    normalized = float(value)
    if not (0.0 <= normalized <= 1.0):
        raise AnalysisExtractionError("confidence must be between 0.0 and 1.0")
    return normalized


def _source_anchors(value: object) -> tuple[CandidateSourceAnchor, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise AnalysisExtractionError("source_anchors must be a non-empty array")
    return _dedupe_source_anchors(tuple(_source_anchor(item) for item in value))


def _source_anchor(item: object) -> CandidateSourceAnchor:
    if not isinstance(item, Mapping):
        raise AnalysisExtractionError("source_anchor must be an object")
    _require_fields(
        item,
        {"source_ref_id", "start_offset", "end_offset", "quote", "content_hash"},
    )
    source_ref_id = _non_empty_string(item["source_ref_id"], "source_ref_id")
    start_offset = _offset(item["start_offset"], "start_offset")
    end_offset = _offset(item["end_offset"], "end_offset")
    if end_offset <= start_offset:
        raise AnalysisExtractionError("source_anchor offsets are invalid")
    quote = _non_empty_string(item["quote"], "quote")
    content_hash = _non_empty_string(item["content_hash"], "content_hash")
    return CandidateSourceAnchor(
        source_ref_id=source_ref_id,
        start_offset=start_offset,
        end_offset=end_offset,
        quote=quote,
        content_hash=content_hash,
    )


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AnalysisExtractionError(f"{field} must be a non-empty string")
    return value


def _offset(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalysisExtractionError(f"{field} must be a non-negative integer")
    return value


def _logical_key(
    *,
    candidate_type: AnalysisCandidateType,
    source_anchors: tuple[CandidateSourceAnchor, ...],
    payload: Mapping[str, Any],
) -> str:
    canonical = {
        "candidate_type": candidate_type.value,
        "payload": dict(payload),
        "source_anchors": sorted(
            (
                _canonical_anchor(anchor)
                for anchor in _dedupe_source_anchors(source_anchors)
            ),
            key=lambda anchor: (
                anchor["source_ref_id"],
                anchor["start_offset"],
                anchor["end_offset"],
                anchor["quote"],
                anchor["content_hash"],
            ),
        ),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"{candidate_type.value}:{hashlib.sha256(encoded).hexdigest()}"


def _dedupe_source_anchors(
    source_anchors: tuple[CandidateSourceAnchor, ...],
) -> tuple[CandidateSourceAnchor, ...]:
    unique: dict[tuple[str, int, int, str, str], CandidateSourceAnchor] = {}
    for anchor in source_anchors:
        unique.setdefault(_anchor_identity(anchor), anchor)
    return tuple(unique.values())


def _anchor_identity(anchor: CandidateSourceAnchor) -> tuple[str, int, int, str, str]:
    return (
        anchor.source_ref_id,
        anchor.start_offset,
        anchor.end_offset,
        anchor.quote,
        anchor.content_hash,
    )


def _canonical_anchor(anchor: CandidateSourceAnchor) -> dict[str, object]:
    return {
        "source_ref_id": anchor.source_ref_id,
        "start_offset": anchor.start_offset,
        "end_offset": anchor.end_offset,
        "quote": anchor.quote,
        "content_hash": anchor.content_hash,
    }
