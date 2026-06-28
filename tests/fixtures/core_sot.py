"""Reusable Core SOT fixture for downstream phase tests."""

from __future__ import annotations

from dataclasses import dataclass

from services.application.app.core_sot.models import (
    BlockKind,
    Draft,
    Project,
    SaveDraftResult,
    SourceRef,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)


PROJECT_NAME = "Fixture Project"
DRAFT_TITLE = "Episode Fixture"
IDEMPOTENCY_KEY = "fixture-save-1"
RAW_TEXT = (
    "# Episode 1\n\n"
    "Mina opened the brass door.\n\n"
    "---\n\n"
    "The corridor answered with blue light.\n\n"
    "## Notes\n\n"
    "Mina remembered the old promise."
)
CONTENT_HASH = (
    "459fc116afac0a93ad10ea43e529c88fe5c8a5516b37679e89f653a758462e78"
)


@dataclass(frozen=True, slots=True)
class ExpectedBlock:
    kind: BlockKind
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True, slots=True)
class ExpectedSourceRef:
    name: str
    start_offset: int
    end_offset: int
    quote: str
    block_index: int


@dataclass(frozen=True, slots=True)
class CoreSotFixture:
    repository: InMemoryCoreSotRepository
    service: CoreSotService
    project: Project
    draft: Draft
    save: SaveDraftResult
    source_refs: dict[str, SourceRef]


EXPECTED_BLOCKS = (
    ExpectedBlock(BlockKind.HEADING, 0, 11, "# Episode 1"),
    ExpectedBlock(BlockKind.PARAGRAPH, 13, 40, "Mina opened the brass door."),
    ExpectedBlock(BlockKind.SCENE_MARKER, 42, 45, "---"),
    ExpectedBlock(
        BlockKind.PARAGRAPH,
        47,
        85,
        "The corridor answered with blue light.",
    ),
    ExpectedBlock(BlockKind.HEADING, 87, 95, "## Notes"),
    ExpectedBlock(BlockKind.PARAGRAPH, 97, 129, "Mina remembered the old promise."),
)

EXPECTED_SOURCE_REFS = (
    ExpectedSourceRef("brass", 29, 34, "brass", 2),
    ExpectedSourceRef("old_promise", 117, 128, "old promise", 6),
)


def build_core_sot_fixture() -> CoreSotFixture:
    repository = InMemoryCoreSotRepository()
    service = CoreSotService(repository)
    project = service.create_project(name=PROJECT_NAME)
    draft = service.create_draft(project_id=project.id, title=DRAFT_TITLE)
    save = service.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=RAW_TEXT,
        idempotency_key=IDEMPOTENCY_KEY,
    )
    source_refs = {
        expected.name: service.create_source_ref(
            project_id=project.id,
            snapshot_id=save.snapshot.id,
            start_offset=expected.start_offset,
            end_offset=expected.end_offset,
        )
        for expected in EXPECTED_SOURCE_REFS
    }
    return CoreSotFixture(
        repository=repository,
        service=service,
        project=project,
        draft=draft,
        save=save,
        source_refs=source_refs,
    )
