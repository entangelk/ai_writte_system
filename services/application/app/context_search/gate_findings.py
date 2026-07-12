"""Durable Context Gate findings for Phase 6 review."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable, Protocol

from services.application.app.context_search.models import (
    ContextPackage, ContextSearchRequest, GateDecision,
)


class GateFindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class StoredGateFinding:
    id: str
    project_id: str
    idempotency_key: str
    ordinal: int
    check: str
    detail: str
    status: GateFindingStatus
    query: str
    purpose: str
    needs: tuple[str, ...]
    pointer_ids: tuple[str, ...]
    request_fingerprint: str
    result_fingerprint: str
    created_at: datetime
    terminal_at: datetime | None = None


class GateFindingRepository(Protocol):
    def upsert(self, finding: StoredGateFinding) -> None: ...
    def get(self, finding_id: str) -> StoredGateFinding | None: ...
    def list_open(self, project_id: str) -> tuple[StoredGateFinding, ...]: ...


class InMemoryGateFindingRepository:
    def __init__(self) -> None:
        self.entries: dict[str, StoredGateFinding] = {}

    def upsert(self, finding: StoredGateFinding) -> None:
        self.entries[finding.id] = finding

    def get(self, finding_id: str) -> StoredGateFinding | None:
        return self.entries.get(finding_id)

    def list_open(self, project_id: str) -> tuple[StoredGateFinding, ...]:
        return tuple(sorted(
            (entry for entry in self.entries.values()
             if entry.project_id == project_id
             and entry.status is GateFindingStatus.OPEN),
            key=lambda entry: entry.id,
        ))


class GateFindingError(RuntimeError):
    pass


class GateFindingNotFound(GateFindingError):
    pass


class InvalidGateFindingTransition(GateFindingError):
    pass


class GateFindingService:
    def __init__(self, repository: GateFindingRepository, *,
                 clock: Callable[[], datetime] | None = None) -> None:
        self._repo = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def persist_rejection(self, *, request: ContextSearchRequest,
                          idempotency_key: str, package: ContextPackage,
                          gate: GateDecision) -> tuple[StoredGateFinding, ...]:
        if gate.decision != "reject":
            return ()
        if not idempotency_key.strip():
            raise GateFindingError("idempotency_key is required")
        request_payload = {
            "project_id": request.project_id, "query": request.query,
            "purpose": request.purpose.value,
            "needs": [need.value for need in request.needs],
            "current_position": (
                None if request.current_position is None else {
                    "draft_id": request.current_position.draft_id,
                    "version_id": request.current_position.version_id,
                }
            ),
        }
        request_fingerprint = _fingerprint(request_payload)
        result_fingerprint = _fingerprint({
            "decision": gate.decision,
            "findings": [
                {"check": finding.check, "detail": finding.detail}
                for finding in gate.findings
            ],
            "package_status": package.status,
            "token_estimate_total": package.token_estimate_total,
        })
        pointer_ids = _pointer_ids(package)
        stored = []
        for ordinal, finding in enumerate(gate.findings):
            finding_id = derive_gate_finding_id(
                project_id=request.project_id, idempotency_key=idempotency_key,
                ordinal=ordinal, check=finding.check,
            )
            existing = self._repo.get(finding_id)
            if existing is not None:
                stored.append(existing)
                continue
            entry = StoredGateFinding(
                id=finding_id, project_id=request.project_id,
                idempotency_key=idempotency_key, ordinal=ordinal,
                check=finding.check, detail=finding.detail,
                status=GateFindingStatus.OPEN, query=request.query,
                purpose=request.purpose.value,
                needs=tuple(need.value for need in request.needs),
                pointer_ids=pointer_ids,
                request_fingerprint=request_fingerprint,
                result_fingerprint=result_fingerprint,
                created_at=self._clock(),
            )
            self._repo.upsert(entry)
            stored.append(entry)
        return tuple(stored)

    def list_open(self, project_id: str) -> tuple[StoredGateFinding, ...]:
        return self._repo.list_open(project_id)

    def get(self, *, project_id: str, finding_id: str) -> StoredGateFinding:
        finding = self._repo.get(finding_id)
        if finding is None or finding.project_id != project_id:
            raise GateFindingNotFound("gate finding not found")
        return finding

    def transition(self, *, project_id: str, finding_id: str,
                   target: GateFindingStatus) -> tuple[StoredGateFinding, bool]:
        finding = self.get(project_id=project_id, finding_id=finding_id)
        if target is GateFindingStatus.OPEN:
            raise InvalidGateFindingTransition("cannot transition to open")
        if finding.status is target:
            return finding, True
        if finding.status is not GateFindingStatus.OPEN:
            raise InvalidGateFindingTransition(
                "gate finding is already terminal with a different status"
            )
        updated = replace(finding, status=target, terminal_at=self._clock())
        self._repo.upsert(updated)
        return updated, False


def derive_gate_finding_id(*, project_id: str, idempotency_key: str,
                           ordinal: int, check: str) -> str:
    return "gf:" + _fingerprint({
        "project_id": project_id, "idempotency_key": idempotency_key,
        "ordinal": ordinal, "check": check,
    })


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pointer_ids(package: ContextPackage) -> tuple[str, ...]:
    ids: set[str] = set()
    for item in (*package.macro_items, *package.micro_evidence):
        ids.update(item.source_ref_ids)
        ids.add(item.snapshot_id)
        ids.add(item.pointer.document_id)
        if item.pointer.version_id:
            ids.add(item.pointer.version_id)
    return tuple(sorted(value for value in ids if value))
