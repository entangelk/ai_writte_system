"""Explicit W3 one-shot migration for legacy Draft ordering metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace

from services.application.app.core_sot.models import Draft, UnitKind
from services.application.app.core_sot.repository import CoreSotRepository


@dataclass(frozen=True, slots=True)
class OrderedUnitMigrationFailure:
    project_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class OrderedUnitMigrationReport:
    migrated_project_ids: tuple[str, ...]
    unchanged_project_ids: tuple[str, ...]
    failures: tuple[OrderedUnitMigrationFailure, ...]
    position_index_installed: bool

    @property
    def succeeded(self) -> bool:
        return not self.failures


class OrderedUnitMigrationService:
    def __init__(self, repository: CoreSotRepository) -> None:
        self._repo = repository

    def run(self) -> OrderedUnitMigrationReport:
        migrated: list[str] = []
        unchanged: list[str] = []
        failures: list[OrderedUnitMigrationFailure] = []

        for project in self._repo.list_projects():
            try:
                drafts = self._repo.list_drafts(project.id)
                migrated_drafts = self._plan_project(drafts)
                if migrated_drafts is None:
                    unchanged.append(project.id)
                    continue
                self._repo.replace_draft_metadata(project.id, migrated_drafts)
                migrated.append(project.id)
            except Exception as exc:
                failures.append(
                    OrderedUnitMigrationFailure(project_id=project.id, detail=str(exc))
                )

        installed = False
        if not failures:
            self._repo.ensure_draft_position_index()
            installed = True
        return OrderedUnitMigrationReport(
            migrated_project_ids=tuple(migrated),
            unchanged_project_ids=tuple(unchanged),
            failures=tuple(failures),
            position_index_installed=installed,
        )

    @staticmethod
    def _plan_project(drafts: tuple[Draft, ...]) -> tuple[Draft, ...] | None:
        if not drafts:
            return None
        missing = tuple(
            draft.unit_kind is None and draft.position is None for draft in drafts
        )
        if all(missing):
            return tuple(
                replace(draft, unit_kind=UnitKind.OTHER, position=index)
                for index, draft in enumerate(drafts, start=1)
            )
        if any(missing) or any(
            draft.unit_kind is None or draft.position is None for draft in drafts
        ):
            raise ValueError("draft metadata is partially migrated")
        if any(not isinstance(draft.unit_kind, UnitKind) for draft in drafts):
            raise ValueError("draft unit_kind is invalid")
        positions = tuple(sorted(draft.position for draft in drafts))
        if positions != tuple(range(1, len(drafts) + 1)):
            raise ValueError("draft positions are duplicate or gapped")
        return None
