"""Phase 2B.3 deterministic scope key derivation (D2=A / D3=A).

A ``MemoryScope`` is the deterministic identity key used to decide whether an
analysis candidate refers to the *same subject* as an existing canonical
memory. D3=A keeps identity matching deterministic (no embedding); D2=A limits
it to the only taxonomy type with a natural stable identifier:

* ``character_observation`` → scope over the normalized ``name``.
* ``event_observation`` / ``open_question_observation`` carry only descriptive
  text (no entity id), so deterministic identity is not derivable — they get
  ``None`` and are always treated as new (``create``) this slice. Semantic
  resolution for them is a later seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.application.app.analysis.models import AnalysisCandidateType


@dataclass(frozen=True, slots=True)
class MemoryScope:
    scope_type: str
    scope_id: str


def normalize_name(name: str) -> str:
    """Deterministic name normalization: collapse whitespace, casefold."""
    return " ".join(name.split()).casefold()


def derive_scope(
    memory_type: AnalysisCandidateType, payload: Mapping[str, Any]
) -> MemoryScope | None:
    if memory_type is AnalysisCandidateType.CHARACTER_OBSERVATION:
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return MemoryScope(
                scope_type="character", scope_id=normalize_name(name)
            )
    return None
