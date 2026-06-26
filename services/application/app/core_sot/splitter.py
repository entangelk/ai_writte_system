"""Deterministic raw-text splitter for MVP source references."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from services.application.app.core_sot.models import BlockKind, SourceBlock


@dataclass(frozen=True, slots=True)
class RawBlock:
    kind: BlockKind
    start_offset: int
    end_offset: int
    text: str


def content_hash(raw_text: str) -> str:
    """Return SHA-256 over the exact raw UTF-8 bytes."""

    return sha256(raw_text.encode("utf-8")).hexdigest()


def split_source_blocks(raw_text: str) -> tuple[RawBlock, ...]:
    """Split raw text into deterministic source-reference blocks.

    Offsets are Python string indices, matching the approved Unicode code point
    contract. The splitter uses only explicit structure: Markdown headings,
    standalone scene markers, and blank-line paragraph boundaries.
    """

    blocks: list[RawBlock] = []
    paragraph_start: int | None = None
    paragraph_end: int | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_start, paragraph_end
        if paragraph_start is None or paragraph_end is None:
            return
        text = raw_text[paragraph_start:paragraph_end]
        if text:
            blocks.append(
                RawBlock(
                    kind=BlockKind.PARAGRAPH,
                    start_offset=paragraph_start,
                    end_offset=paragraph_end,
                    text=text,
                )
            )
        paragraph_start = None
        paragraph_end = None

    offset = 0
    for line in raw_text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        line_content = line.rstrip("\r\n")
        line_end = line_start + len(line_content)
        stripped = line_content.strip()

        if not stripped:
            flush_paragraph()
            continue

        if _is_heading(stripped):
            flush_paragraph()
            blocks.append(
                RawBlock(
                    kind=BlockKind.HEADING,
                    start_offset=line_start,
                    end_offset=line_end,
                    text=raw_text[line_start:line_end],
                )
            )
            continue

        if _is_scene_marker(stripped):
            flush_paragraph()
            blocks.append(
                RawBlock(
                    kind=BlockKind.SCENE_MARKER,
                    start_offset=line_start,
                    end_offset=line_end,
                    text=raw_text[line_start:line_end],
                )
            )
            continue

        if paragraph_start is None:
            paragraph_start = line_start
        paragraph_end = line_end

    flush_paragraph()
    return tuple(blocks)


def materialize_blocks(
    *,
    project_id: str,
    snapshot_id: str,
    raw_blocks: tuple[RawBlock, ...],
) -> tuple[SourceBlock, ...]:
    return tuple(
        SourceBlock(
            id=f"{snapshot_id}:block:{index + 1}",
            project_id=project_id,
            snapshot_id=snapshot_id,
            block_index=index + 1,
            kind=block.kind,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            text=block.text,
        )
        for index, block in enumerate(raw_blocks)
    )


def _is_heading(stripped_line: str) -> bool:
    if not stripped_line.startswith("#"):
        return False
    marker = stripped_line.split(maxsplit=1)[0]
    return 1 <= len(marker) <= 6 and set(marker) == {"#"}


def _is_scene_marker(stripped_line: str) -> bool:
    return stripped_line in {"---", "***"}

