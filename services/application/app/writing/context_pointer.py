"""Stable context pointer projection and per-origin invariants.

Kickoff brief: docs/plans/05-writing-stable-context-pointer-decisions.md
(D1=A projection of the existing ``IndexPointer``; sub-decision P-i for the
field invariant).

The model never mints identity: the report extractor is shown the pointers of
the current package and must copy one back exactly (D2=A), which
``report.parse_report`` validates as membership of the allowlist built here.
"""

from __future__ import annotations

import json

from services.application.app.context_search.models import ContextPackage
from services.application.app.context_search.service import CANDIDATES_COLLECTION
from services.application.app.indexing.models import IndexPointer
from services.application.app.indexing.service import (
    MEMORIES_COLLECTION,
    SOURCE_BLOCK_COLLECTION,
)
from services.application.app.writing.models import ContextPointer


POINTER_KEYS = ("collection", "document_id", "version_id", "content_hash")

# Per-origin field invariant (owner sub-decision P-i, 2026-07-15). A store fills
# only the fields it has: memory and candidate items have no SOT snapshot, so
# they carry no content_hash, and a candidate has no version either
# (context_search/service.py _item_from_memory/_item_from_candidate). Empty is
# allowed exactly where the store has no such field and nowhere else, so an
# empty source-block version/hash — a real defect — still fails closed.
# Identity survives the empties: a memory id is version-distinct (2B.4
# append-only) and a candidate id is edit-distinct (v1.6.66).
_NON_EMPTY_FIELDS: dict[str, frozenset[str]] = {
    SOURCE_BLOCK_COLLECTION: frozenset({"document_id", "version_id", "content_hash"}),
    MEMORIES_COLLECTION: frozenset({"document_id", "version_id"}),
    CANDIDATES_COLLECTION: frozenset({"document_id"}),
}


class InvalidContextPointer(ValueError):
    """A package item cannot be projected into a stable pointer."""


def context_pointer_of(pointer: IndexPointer, *, project_id: str) -> ContextPointer:
    """Project one package item pointer, enforcing the P-i origin invariant.

    ``project_id`` is the trusted package/candidate project; an item pointing at
    another project is rejected here, before any provider call (contract 2).
    """
    if pointer.project_id != project_id:
        raise InvalidContextPointer(
            f"context item {pointer.document_id} belongs to project "
            f"{pointer.project_id}, not {project_id}"
        )
    non_empty = _NON_EMPTY_FIELDS.get(pointer.collection)
    if non_empty is None:
        raise InvalidContextPointer(
            f"collection {pointer.collection} is not a pointable context origin"
        )
    for key in POINTER_KEYS[1:]:
        value = getattr(pointer, key)
        if key in non_empty:
            if not value.strip():
                raise InvalidContextPointer(
                    f"{pointer.collection} pointer requires a non-empty {key}"
                )
        elif value != "":
            raise InvalidContextPointer(
                f"{pointer.collection} pointer must leave {key} empty"
            )
    return ContextPointer(
        collection=pointer.collection,
        document_id=pointer.document_id,
        version_id=pointer.version_id,
        content_hash=pointer.content_hash,
    )


def package_pointers(package: ContextPackage) -> tuple[ContextPointer, ...]:
    """The exact pointers a claim of this package may cite (D2=A allowlist)."""
    return tuple(
        context_pointer_of(item.pointer, project_id=package.project_id)
        for item in (*package.macro_items, *package.micro_evidence)
    )


def pointer_wire(pointer: ContextPointer) -> dict[str, str]:
    return {key: getattr(pointer, key) for key in POINTER_KEYS}


def pointer_json(pointer: ContextPointer) -> str:
    """Canonical one-line rendering shown to the report extractor."""
    return json.dumps(
        pointer_wire(pointer), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )
