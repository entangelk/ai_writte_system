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


def validate_candidate_payload(
    candidate_type: AnalysisCandidateType,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise InvalidAnalysisPayload("payload must be an object")
    if candidate_type not in _REQUIRED_FIELDS:
        raise InvalidAnalysisPayload("unsupported analysis candidate type")

    required_fields = _REQUIRED_FIELDS[candidate_type]
    allowed_fields = set(required_fields)
    observed_fields = set(payload.keys())
    if observed_fields != allowed_fields:
        raise InvalidAnalysisPayload("payload fields do not match candidate type")

    normalized: dict[str, str] = {}
    for field in required_fields:
        value = payload[field]
        if not isinstance(value, str) or not value:
            raise InvalidAnalysisPayload("payload fields must be non-empty strings")
        normalized[field] = value
    return normalized
