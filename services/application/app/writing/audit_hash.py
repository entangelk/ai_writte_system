"""Pure fingerprint helpers for the Writing bounded-loop audit trail.

Shared by the loop (``revise_gate``) and the persisted audit
(``loop_audit``) so per-stage and run-level hashes are computed the same
way — a run's ``final_candidate_hash`` therefore equals its last stage's
``candidate_hash``. Bodyless by design (Phase 5.9 L9 B, P1=B): stores
hashes/fingerprints/pointers, not intermediate artifact bodies.
"""

from __future__ import annotations

import hashlib
import json

from services.application.app.context_search.models import ContextPackage
from services.application.app.writing.models import WritingGateFinding


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def finding_fingerprint(finding: WritingGateFinding) -> str:
    return _fingerprint({
        "type": finding.finding_type.value,
        "severity": finding.severity.value,
        "message": finding.message,
        "evidence": finding.evidence,
        "recommended_decision": finding.recommended_decision.value,
    })


def package_pointer_ids(package: ContextPackage) -> tuple[str, ...]:
    ids: set[str] = set()
    for item in (*package.macro_items, *package.micro_evidence):
        ids.update(item.source_ref_ids)
        ids.add(item.snapshot_id)
        ids.add(item.pointer.document_id)
        if item.pointer.version_id:
            ids.add(item.pointer.version_id)
    return tuple(sorted(value for value in ids if value))


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
