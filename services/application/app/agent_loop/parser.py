"""Provider response parsing for flat agent loop termination signals.

This slice fixes the wire format for the self-report termination channel:
provider content is a JSON object with a top-level ``self_report`` field whose
value is exactly ``"finalize"`` or ``"defer"``. Artifact payload fields are
owned by later task-schema slices; this parser only extracts the loop
termination channel and rejects malformed or missing signals as provider output
errors.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from services.application.app.agent_loop.completion import SelfReport
from services.application.app.agent_loop.decision import LoopDecision

_SELF_REPORT_FIELD = "self_report"


class InvalidSelfReport(ValueError):
    """Raised when provider content omits or corrupts the termination channel."""

    decision = LoopDecision.PROVIDER_ERROR


def parse_self_report_payload(content: str) -> SelfReport:
    """Parse the top-level self-report signal from provider JSON content.

    The parser is intentionally strict: no missing-field default, no case
    folding, no coercion, and no fallback to similarly named artifact fields.
    Those guards keep ``completed`` from being inferred when the model did not
    explicitly close the run through the termination channel.
    """
    payload = _parse_json_object(content)
    raw_self_report = payload.get(_SELF_REPORT_FIELD)
    if not isinstance(raw_self_report, str):
        raise InvalidSelfReport("self_report must be a string")

    try:
        return SelfReport(raw_self_report)
    except ValueError as exc:
        raise InvalidSelfReport(
            "self_report must be exactly 'finalize' or 'defer'"
        ) from exc


def _parse_json_object(content: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise InvalidSelfReport("provider content must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise InvalidSelfReport("provider content must be a JSON object")

    return payload
