"""Minimal Phase 2A taxonomy payload validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.application.app.analysis.models import AnalysisCandidateType


class InvalidAnalysisPayload(ValueError):
    pass


_REQUIRED_FIELDS: Mapping[AnalysisCandidateType, tuple[str, ...]] = {
    AnalysisCandidateType.CHARACTER_OBSERVATION: ("name", "observation"),
    AnalysisCandidateType.EVENT_OBSERVATION: ("event",),
    AnalysisCandidateType.OPEN_QUESTION_OBSERVATION: ("question",),
}

# 문체/분량 슬라이스 증분 3 (D4=B, owner=optional): character observations MAY carry
# an ``aspect`` classifier (free string, e.g. "voice"/"trait") so the Writing Gate
# can mechanically compare character voice against the author's setting. It stays
# taxonomy-frozen (still 3 candidate types, 2A D5=A) and OPTIONAL so existing
# ``{name, observation}`` payloads keep validating — no migration. A present aspect
# must still be a non-empty string; unknown fields remain rejected.
_OPTIONAL_FIELDS: Mapping[AnalysisCandidateType, tuple[str, ...]] = {
    AnalysisCandidateType.CHARACTER_OBSERVATION: ("aspect",),
}


def validate_candidate_payload(
    candidate_type: AnalysisCandidateType,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise InvalidAnalysisPayload("payload must be an object")
    if candidate_type not in _REQUIRED_FIELDS:
        raise InvalidAnalysisPayload("unsupported analysis candidate type")

    required_fields = _REQUIRED_FIELDS[candidate_type]
    optional_fields = _OPTIONAL_FIELDS.get(candidate_type, ())
    allowed_fields = set(required_fields) | set(optional_fields)
    observed_fields = set(payload.keys())
    if not set(required_fields) <= observed_fields:
        raise InvalidAnalysisPayload("payload is missing required fields")
    if not observed_fields <= allowed_fields:
        raise InvalidAnalysisPayload("payload has unknown fields")

    normalized: dict[str, str] = {}
    # Required first, then any present optional field, so ordering is deterministic.
    for field in (*required_fields, *optional_fields):
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str) or not value:
            raise InvalidAnalysisPayload("payload fields must be non-empty strings")
        normalized[field] = value
    return normalized
