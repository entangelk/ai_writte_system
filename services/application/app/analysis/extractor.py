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
from services.application.app.writing.json_extract import strip_code_fence
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
        source_refs: Sequence[SourceRef] = (),
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> None:
        self._provider = provider
        self._source_refs = tuple(source_refs)
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
        return parse_analysis_extraction(
            result.content, source_refs=self._source_refs
        )


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
            # 스키마 중복 전수조사 A: 앵커 조립이 파싱 안에서 일어난다. 모델은
            # source_ref_id만 내고 span/quote/hash는 카탈로그에서 채운다 — 옛
            # 사후 대조(_catalog_anchor_error)가 강제하던 전필드 일치가 이제
            # 구조적으로 보장된다(모델이 복사할 수 없으므로 틀릴 수 없다).
            return parse_analysis_extraction(
                result.content, source_refs=source_refs
            )
        except AnalysisExtractionError as first_error:
            return await self._repair_once(
                request=request,
                invalid_content=result.content,
                error=str(first_error),
                source_refs=source_refs,
            )

    async def _repair_once(
        self,
        *,
        request: ChatCompletionRequest,
        invalid_content: str,
        error: str,
        source_refs: tuple[SourceRef, ...],
    ) -> tuple[AnalysisCandidateDraft, ...]:
        repair = await self._provider.generate(
            _repair_request(
                original_request=request,
                invalid_content=invalid_content,
                parser_error=error,
            )
        )
        return parse_analysis_extraction(repair.content, source_refs=source_refs)


def parse_analysis_extraction(
    content: str,
    *,
    source_refs: Sequence[SourceRef] = (),
) -> tuple[AnalysisCandidateDraft, ...]:
    catalog = {source_ref.id: source_ref for source_ref in source_refs}
    root = _json_object(content)
    raw_candidates = root.get("candidates")
    if not isinstance(raw_candidates, list):
        raise AnalysisExtractionError("candidates must be an array")
    return tuple(_candidate_draft(item, catalog) for item in raw_candidates)


_REPAIR_SYSTEM_PROMPT = """Repair Phase 2A analysis extraction output.

Return valid JSON only. Do not wrap the JSON in markdown fences. Do not add prose.

The output must be one object with top-level key "candidates".
Each candidate must contain exactly these fields:
- candidate_type: one of character_observation, event_observation, open_question_observation
- provenance: source_observed or ai_inferred
- confidence: number from 0.0 to 1.0
- source_anchors: non-empty array of {"source_ref_id": "..."} naming current catalog items — span, quote, and content_hash are derived by the server, so emit nothing else
- payload: character_observation requires {"name": "...", "observation": "..."} and may add an optional "aspect" (e.g. "voice", "trait"); event_observation requires {"event": "..."}; open_question_observation requires {"question": "..."}

Use only source_ref_id values from the original source_ref catalog. If no valid candidate can be produced, return {"candidates":[]}.
Treat writing_candidate_report pointers as advisory provenance only. Never copy document_id, block_id, or any report identifier into source_anchors.
Every source anchor must come from authoritative_source_ref_catalog in the repair payload.
"""


def _repair_request(
    *,
    original_request: ChatCompletionRequest,
    invalid_content: str,
    parser_error: str,
) -> ChatCompletionRequest:
    original_payload = json.loads(original_request.messages[-1].content)
    payload = {
        "parser_error": parser_error,
        "invalid_output": invalid_content,
        # Repair needs the source text and authoritative anchors, not the
        # advisory report's old-snapshot pointer namespace. Keeping those IDs
        # out of the repair turn prevents the exact namespace collision this
        # second chance is meant to correct.
        "snapshot_raw_text": original_payload["snapshot"]["raw_text"],
        "authoritative_source_ref_catalog": original_payload["source_ref_catalog"],
    }
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=_REPAIR_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=json.dumps(
                    payload,
                    ensure_ascii=False,
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


def _candidate_draft(
    item: object,
    catalog: Mapping[str, SourceRef],
) -> AnalysisCandidateDraft:
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
    source_anchors = _source_anchors(item["source_anchors"], catalog)
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
        payload = json.loads(strip_code_fence(content))
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


def _source_anchors(
    value: object,
    catalog: Mapping[str, SourceRef],
) -> tuple[CandidateSourceAnchor, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise AnalysisExtractionError("source_anchors must be a non-empty array")
    return _dedupe_source_anchors(
        tuple(_source_anchor(item, catalog) for item in value)
    )


def _source_anchor(
    item: object,
    catalog: Mapping[str, SourceRef],
) -> CandidateSourceAnchor:
    # 스키마 중복 전수조사 A: 모델이 내는 것은 카탈로그 항목의 id 하나다.
    # span/quote/hash는 서버가 그 id의 카탈로그 행에서 조립한다(옛 전필드 일치
    # 강제의 구조적 버전). 레거시 5필드 앵커는 정확키 검사에서 거부된다.
    if not isinstance(item, Mapping):
        raise AnalysisExtractionError("source_anchor must be an object")
    _require_fields(item, {"source_ref_id"})
    source_ref_id = _non_empty_string(item["source_ref_id"], "source_ref_id")
    source_ref = catalog.get(source_ref_id)
    if source_ref is None:
        raise AnalysisExtractionError(
            "source_ref_id must exactly match the source_ref catalog"
        )
    return CandidateSourceAnchor(
        source_ref_id=source_ref.id,
        start_offset=source_ref.start_offset,
        end_offset=source_ref.end_offset,
        quote=source_ref.quote,
        content_hash=source_ref.content_hash,
    )


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AnalysisExtractionError(f"{field} must be a non-empty string")
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
