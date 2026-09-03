"""Versioned prompt template storage for analysis provider wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ANALYSIS_EXTRACT_TASK_TYPE = "analysis_extract"
ANALYSIS_EXTRACT_PROMPT_VERSION_V1 = "analysis_extract_v1"
ANALYSIS_EXTRACT_TEMPLATE_V1 = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list.
Use only source_ref_id values from the provided source_ref catalog.
Do not invent facts outside the supplied snapshot text.
"""
ANALYSIS_EXTRACT_PROMPT_VERSION_V2 = "analysis_extract_v2"
ANALYSIS_EXTRACT_TEMPLATE_V2 = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list.
Treat writing_candidate_report source_blocks and related pointers as advisory provenance only.
Never copy document_id, block_id, or any identifier from writing_candidate_report into source_anchors.
Use source_ref_id values only from the current source_ref_catalog, preserving each catalog anchor exactly.
Do not invent facts outside the supplied snapshot text.
"""
ANALYSIS_EXTRACT_PROMPT_VERSION_V3 = "analysis_extract_v3"
ANALYSIS_EXTRACT_TEMPLATE_V3 = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list.
Treat writing_candidate_report source_blocks and related pointers as advisory provenance only.
Never copy document_id, block_id, or any identifier from writing_candidate_report into source_anchors.
Use source_ref_id values only from the current source_ref_catalog, preserving each catalog anchor exactly.
Each candidate must contain exactly candidate_type, provenance, confidence, source_anchors, and payload.
candidate_type is character_observation, event_observation, or open_question_observation.
provenance is source_observed or ai_inferred. confidence is a number from 0.0 to 1.0.
Each source_anchors item must copy source_ref_id, start_offset, end_offset, quote, and content_hash exactly from one current catalog item.
payload is {"name":"...","observation":"..."} for character, {"event":"..."} for event, or {"question":"..."} for open question.
Do not invent facts outside the supplied snapshot text.
"""
ANALYSIS_EXTRACT_PROMPT_VERSION_V4 = "analysis_extract_v4"
ANALYSIS_EXTRACT_TEMPLATE_V4 = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list.
Treat writing_candidate_report source_blocks and related pointers as advisory provenance only.
Never copy document_id, block_id, or any identifier from writing_candidate_report into source_anchors.
Use source_ref_id values only from the current source_ref_catalog, preserving each catalog anchor exactly.
Each candidate must contain exactly candidate_type, provenance, confidence, source_anchors, and payload.
candidate_type is character_observation, event_observation, or open_question_observation.
provenance is source_observed or ai_inferred. confidence is a number from 0.0 to 1.0.
Each source_anchors item must copy source_ref_id, start_offset, end_offset, quote, and content_hash exactly from one current catalog item.
payload is {"name":"...","observation":"..."} for character, {"event":"..."} for event, or {"question":"..."} for open question.
For character, you MAY add an optional "aspect" classifying the observation (e.g. "voice" for how the character speaks, "trait" for a personality trait); omit it for a plain observation.
Do not invent facts outside the supplied snapshot text.
"""
# v5 (2026-08-23): gemma-4-31b-it wraps its JSON in a ```json fence by habit —
# v4 asked for "one JSON object" and the model still fenced. When the output is
# long the closing fence is lost to the token ceiling and parsing fails (see
# the open-fence guard in writing/json_extract.py and the extractor slice in
# work_log 2026-08-23 session 6). Naming the fence explicitly is the cheap half
# of the fix; the parser guard is the reliable half.
# 2026-09-03부터 v5는 출시 동결본이다 — 핀은 test_prompt_templates.py가 잡는다.
ANALYSIS_EXTRACT_PROMPT_VERSION_V5 = "analysis_extract_v5"
ANALYSIS_EXTRACT_TEMPLATE_V5 = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list as raw JSON text only.
Do not wrap the JSON in markdown code fences: no ```json, no ```, no prose before or after.
Treat writing_candidate_report source_blocks and related pointers as advisory provenance only.
Never copy document_id, block_id, or any identifier from writing_candidate_report into source_anchors.
Use source_ref_id values only from the current source_ref_catalog, preserving each catalog anchor exactly.
Each candidate must contain exactly candidate_type, provenance, confidence, source_anchors, and payload.
candidate_type is character_observation, event_observation, or open_question_observation.
provenance is source_observed or ai_inferred. confidence is a number from 0.0 to 1.0.
Each source_anchors item must copy source_ref_id, start_offset, end_offset, quote, and content_hash exactly from one current catalog item.
payload is {"name":"...","observation":"..."} for character, {"event":"..."} for event, or {"question":"..."} for open question.
For character, you MAY add an optional "aspect" classifying the observation (e.g. "voice" for how the character speaks, "trait" for a personality trait); omit it for a plain observation.
Do not invent facts outside the supplied snapshot text.
"""
# v6 (계약 스키마 중복 전수조사 A, 2026-09-03): source_anchors는 id 선택만 남긴다.
# span/quote/hash는 카탈로그 사본일 뿐(서버가 전필드 일치를 강제해 왔다)이므로 모델 출력에서
# 제외하고 파서가 카탈로그에서 조립한다. 카탈로그 렌더도 id/block_id/quote로 슬림해 에코
# 원천과 토큰 비용을 함께 지운다. logical_key는 조립된 앵커로 계산되므로 값이 무변이다.
ANALYSIS_EXTRACT_PROMPT_VERSION = "analysis_extract_v6"
ANALYSIS_EXTRACT_TEMPLATE = """You extract Phase 2A analysis candidates.

Return one JSON object with a top-level candidates list as raw JSON text only.
Do not wrap the JSON in markdown code fences: no ```json, no ```, no prose before or after.
Treat writing_candidate_report source_blocks and related pointers as advisory provenance only.
Never copy document_id, block_id, or any identifier from writing_candidate_report into source_anchors.
Each candidate must contain exactly candidate_type, provenance, confidence, source_anchors, and payload.
candidate_type is character_observation, event_observation, or open_question_observation.
provenance is source_observed or ai_inferred. confidence is a number from 0.0 to 1.0.
Each source_anchors item is {"source_ref_id": "..."} naming one item of the current source_ref_catalog, and nothing else — the server derives span, quote, and content_hash from that item.
payload is {"name":"...","observation":"..."} for character, {"event":"..."} for event, or {"question":"..."} for open question.
For character, you MAY add an optional "aspect" classifying the observation (e.g. "voice" for how the character speaks, "trait" for a personality trait); omit it for a plain observation.
Do not invent facts outside the supplied snapshot text.
"""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    task_type: str
    version: str
    template: str


class PromptTemplateError(ValueError):
    pass


class PromptTemplateNotFound(PromptTemplateError):
    pass


class PromptTemplateConflict(PromptTemplateError):
    pass


class DuplicatePromptTemplate(RuntimeError):
    """Raised when storage loses a task_type/version insert race."""


class PromptTemplateRepository(Protocol):
    def next_template_id(self) -> str: ...

    def get_template(self, *, task_type: str, version: str) -> PromptTemplate | None:
        ...

    def put_template(self, template: PromptTemplate) -> None: ...


class InMemoryPromptTemplateRepository:
    def __init__(self) -> None:
        self._template_seq = 0
        self.templates: dict[tuple[str, str], PromptTemplate] = {}

    def next_template_id(self) -> str:
        self._template_seq += 1
        return f"prompt-template-{self._template_seq}"

    def get_template(self, *, task_type: str, version: str) -> PromptTemplate | None:
        return self.templates.get((task_type, version))

    def put_template(self, template: PromptTemplate) -> None:
        key = (template.task_type, template.version)
        if key in self.templates:
            raise DuplicatePromptTemplate(key)
        self.templates[key] = template


class PromptTemplateService:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repo = repository

    def seed_template(
        self, *, task_type: str, version: str, template: str
    ) -> PromptTemplate:
        task_type = _non_empty_string(task_type, "task_type")
        version = _non_empty_string(version, "version")
        template = _non_empty_string(template, "template")
        existing = self._repo.get_template(task_type=task_type, version=version)
        if existing is not None:
            if existing.template != template:
                raise PromptTemplateConflict("prompt template version already exists")
            return existing

        seeded = PromptTemplate(
            id=self._repo.next_template_id(),
            task_type=task_type,
            version=version,
            template=template,
        )
        try:
            self._repo.put_template(seeded)
        except DuplicatePromptTemplate:
            existing = self._repo.get_template(task_type=task_type, version=version)
            if existing is not None and existing.template == template:
                return existing
            raise PromptTemplateConflict("prompt template version already exists")
        return seeded

    def seed_analysis_extract_v1(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V1,
            template=ANALYSIS_EXTRACT_TEMPLATE_V1,
        )

    def seed_analysis_extract_v2(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V2,
            template=ANALYSIS_EXTRACT_TEMPLATE_V2,
        )

    def seed_analysis_extract_v3(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V3,
            template=ANALYSIS_EXTRACT_TEMPLATE_V3,
        )

    def seed_analysis_extract_v4(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V4,
            template=ANALYSIS_EXTRACT_TEMPLATE_V4,
        )

    def seed_analysis_extract_v5(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION_V5,
            template=ANALYSIS_EXTRACT_TEMPLATE_V5,
        )

    def seed_analysis_extract_v6(self) -> PromptTemplate:
        return self.seed_template(
            task_type=ANALYSIS_EXTRACT_TASK_TYPE,
            version=ANALYSIS_EXTRACT_PROMPT_VERSION,
            template=ANALYSIS_EXTRACT_TEMPLATE,
        )

    def get_template(self, *, task_type: str, version: str) -> PromptTemplate:
        task_type = _non_empty_string(task_type, "task_type")
        version = _non_empty_string(version, "version")
        template = self._repo.get_template(task_type=task_type, version=version)
        if template is None:
            raise PromptTemplateNotFound("prompt template not found")
        return template


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PromptTemplateError(f"{field} must be a non-empty string")
    return value
