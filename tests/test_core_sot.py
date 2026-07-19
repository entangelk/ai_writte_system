"""Contract tests for the Core SOT MVP skeleton.

Locks the approved Slice 1 source-of-truth contracts:

- raw snapshot hash and Unicode-code-point offsets are deterministic;
- MVP source blocks come only from explicit headings, scene markers, and
  paragraph boundaries;
- draft save idempotency prevents duplicate versions on retry;
- source refs reconstruct exact quotes from immutable snapshots;
- project isolation and archive behavior preserve historical source material.
"""

import unittest

from services.application.app.core_sot.models import (
    BlockKind,
    DraftVersion,
    SourceSnapshot,
)
from services.application.app.core_sot.service import (
    Archived,
    CoreSotError,
    CoreSotService,
    InMemoryCoreSotRepository,
    InvalidSourceRef,
    NotFound,
    UnsupportedExportFormat,
)
from services.application.app.core_sot.splitter import content_hash


def _service():
    repo = InMemoryCoreSotRepository()
    return CoreSotService(repo), repo


class CoreSotSaveTest(unittest.TestCase):
    def test_save_creates_immutable_snapshot_hash_and_deterministic_blocks(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "# Chapter 1\n\nOpening line.\nStill opening.\n\n---\n\nNext scene."

        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )

        self.assertEqual(result.snapshot.raw_text, raw_text)
        self.assertEqual(result.snapshot.content_hash, content_hash(raw_text))
        self.assertEqual(
            [block.kind for block in result.blocks],
            [
                BlockKind.HEADING,
                BlockKind.PARAGRAPH,
                BlockKind.SCENE_MARKER,
                BlockKind.PARAGRAPH,
            ],
        )
        self.assertEqual(result.blocks[0].text, "# Chapter 1")
        self.assertEqual(result.blocks[1].text, "Opening line.\nStill opening.")
        self.assertEqual(result.blocks[2].text, "---")
        self.assertEqual(result.blocks[3].text, "Next scene.")

    def test_hash_uses_sha256_over_raw_utf8_bytes(self):
        # Independent known vector: this must fail if the implementation changes
        # to another algorithm, normalization, or non-UTF-8 encoding.
        self.assertEqual(
            content_hash("두번째"),
            "c29de6a8ce7a05ea24880bbcfe84bdf788981a02a7e404e1c8733fe620b97ff2",
        )

    def test_extended_heading_and_star_scene_marker_are_deterministic_blocks(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "## Section\n\nOpening.\n\n***\n\nAfter marker."

        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )

        self.assertEqual(
            [block.kind for block in result.blocks],
            [
                BlockKind.HEADING,
                BlockKind.PARAGRAPH,
                BlockKind.SCENE_MARKER,
                BlockKind.PARAGRAPH,
            ],
        )
        self.assertEqual(result.blocks[0].text, "## Section")
        self.assertEqual(result.blocks[2].text, "***")

    def test_idempotency_key_replay_returns_same_version_without_duplicate(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")

        first = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="first text",
            idempotency_key="same-key",
        )
        replay = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="mutated retry body must not create a new version",
            idempotency_key="same-key",
        )

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.draft_version.id, first.draft_version.id)
        self.assertEqual(replay.snapshot.raw_text, "first text")
        self.assertEqual(repo.version_count(draft.id), 1)

    def test_distinct_idempotency_key_creates_next_version(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")

        first = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="first text",
            idempotency_key="save-1",
        )
        second = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="second text",
            idempotency_key="save-2",
        )

        self.assertNotEqual(second.draft_version.id, first.draft_version.id)
        self.assertEqual(second.draft_version.version_number, 2)
        self.assertEqual(repo.version_count(draft.id), 2)

    def test_missing_idempotency_key_is_rejected(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")

        with self.assertRaises(CoreSotError):
            service.save_draft(
                project_id=project.id,
                draft_id=draft.id,
                raw_text="text",
                idempotency_key="",
            )


class CoreSotSourceRefTest(unittest.TestCase):
    def test_source_ref_reconstructs_exact_quote_and_hash(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "첫 문장입니다.\n두번째 문장입니다."
        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        start = raw_text.index("두번째")
        end = start + len("두번째")

        source_ref = service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=start,
            end_offset=end,
        )

        self.assertEqual(source_ref.quote, "두번째")
        self.assertEqual(source_ref.content_hash, result.snapshot.content_hash)
        self.assertEqual(source_ref.block_id, result.blocks[0].id)

    def test_source_ref_is_persisted_and_retrievable_by_id(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )

        source_ref = service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        self.assertIn(source_ref.id, repo.source_refs)
        fetched = service.get_source_ref(
            project_id=project.id, source_ref_id=source_ref.id
        )
        self.assertEqual(fetched, source_ref)

    def test_source_ref_get_enforces_project_isolation(self):
        service, _repo = _service()
        project_a = service.create_project(name="A")
        project_b = service.create_project(name="B")
        draft = service.create_draft(project_id=project_a.id, title="Episode 1")
        result = service.save_draft(
            project_id=project_a.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )
        source_ref = service.create_source_ref(
            project_id=project_a.id,
            snapshot_id=result.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        with self.assertRaises(NotFound):
            service.get_source_ref(
                project_id=project_b.id, source_ref_id=source_ref.id
            )

    def test_list_source_refs_returns_snapshot_catalog_in_source_order(self):
        """Under-strict: provider input catalog must expose every prepared ref."""

        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "민아는 파란 편지를 발견했다."
        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )
        letter_start = raw_text.index("편지")
        min_a_start = raw_text.index("민아")
        letter = service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=letter_start,
            end_offset=letter_start + len("편지"),
        )
        min_a = service.create_source_ref(
            project_id=project.id,
            snapshot_id=result.snapshot.id,
            start_offset=min_a_start,
            end_offset=min_a_start + len("민아"),
        )

        catalog = service.list_source_refs(
            project_id=project.id, snapshot_id=result.snapshot.id
        )

        self.assertEqual(catalog, (min_a, letter))

    def test_list_source_refs_enforces_project_and_snapshot_boundary(self):
        """Over-strict: cross-project and missing snapshots must not leak refs."""

        service, _repo = _service()
        project_a = service.create_project(name="A")
        project_b = service.create_project(name="B")
        draft = service.create_draft(project_id=project_a.id, title="Episode 1")
        result = service.save_draft(
            project_id=project_a.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )
        service.create_source_ref(
            project_id=project_a.id,
            snapshot_id=result.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        with self.assertRaises(NotFound):
            service.list_source_refs(
                project_id=project_b.id, snapshot_id=result.snapshot.id
            )
        with self.assertRaises(NotFound):
            service.list_source_refs(
                project_id=project_a.id, snapshot_id="source-snapshot-missing"
            )

    def test_get_source_ref_missing_id_raises_not_found(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")

        with self.assertRaises(NotFound):
            service.get_source_ref(
                project_id=project.id, source_ref_id="source-ref-does-not-exist"
            )

    def test_source_ref_cannot_cross_block_boundary(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "Paragraph one.\n\nParagraph two."
        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )

        with self.assertRaises(InvalidSourceRef):
            service.create_source_ref(
                project_id=project.id,
                snapshot_id=result.snapshot.id,
                start_offset=0,
                end_offset=len(raw_text),
            )

    def test_source_ref_offsets_reject_bool_values(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        result = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="text",
            idempotency_key="save-1",
        )

        with self.assertRaises(InvalidSourceRef):
            service.create_source_ref(
                project_id=project.id,
                snapshot_id=result.snapshot.id,
                start_offset=False,
                end_offset=True,
            )


class CoreSotIsolationAndArchiveTest(unittest.TestCase):
    def test_project_id_isolation_blocks_cross_project_draft_access(self):
        service, _repo = _service()
        project_a = service.create_project(name="A")
        project_b = service.create_project(name="B")
        draft_a = service.create_draft(project_id=project_a.id, title="Episode 1")

        with self.assertRaises(NotFound):
            service.save_draft(
                project_id=project_b.id,
                draft_id=draft_a.id,
                raw_text="leak",
                idempotency_key="save-1",
            )

    def test_archive_blocks_new_save_but_preserves_snapshot_and_version(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="archived text",
            idempotency_key="save-1",
        )

        service.archive_draft(project_id=project.id, draft_id=draft.id)

        with self.assertRaises(Archived):
            service.save_draft(
                project_id=project.id,
                draft_id=draft.id,
                raw_text="new text",
                idempotency_key="save-2",
            )
        self.assertIn(saved.draft_version.id, repo.versions)
        self.assertIn(saved.snapshot.id, repo.snapshots)
        self.assertEqual(repo.blocks_by_snapshot[saved.snapshot.id], saved.blocks)

    def test_project_archive_blocks_new_draft_and_save_but_preserves_history(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="project archived text",
            idempotency_key="save-1",
        )

        service.archive_project(project_id=project.id)

        with self.assertRaises(Archived):
            service.create_draft(project_id=project.id, title="Episode 2")
        with self.assertRaises(Archived):
            service.save_draft(
                project_id=project.id,
                draft_id=draft.id,
                raw_text="new text",
                idempotency_key="save-2",
            )
        self.assertIn(saved.draft_version.id, repo.versions)
        self.assertIn(saved.snapshot.id, repo.snapshots)
        self.assertEqual(repo.blocks_by_snapshot[saved.snapshot.id], saved.blocks)

    def test_get_draft_version_rejects_cross_project_version_ownership(self):
        # Defense-in-depth: service.get_draft_version's `version.project_id !=
        # project_id` guard. A version row that references a draft in this
        # project but carries a different project_id must NOT be returned.
        # This isolates the project_id branch (draft_id matches, so only the
        # project_id clause can fire) — removing that clause re-fails this test.
        # Locks plan 01 L93 project_id isolation as defense against corrupt data.
        service, repo = _service()
        project = service.create_project(name="Owner")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        foreign = DraftVersion(
            id=repo.next_version_id(),
            project_id="other-project",
            draft_id=draft.id,
            version_number=1,
            snapshot_id=repo.next_snapshot_id(),
            idempotency_key="x",
        )
        snapshot = SourceSnapshot(
            id=foreign.snapshot_id,
            project_id="other-project",
            draft_id=draft.id,
            version_id=foreign.id,
            raw_text="secret",
            content_hash="deadbeef",
        )
        repo.record_save(
            idempotency_key="x", version=foreign, snapshot=snapshot, blocks=()
        )

        with self.assertRaises(NotFound):
            service.get_draft_version(
                project_id=project.id, draft_id=draft.id, version_id=foreign.id
            )

    def test_archive_preserves_version_read(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="archived body",
            idempotency_key="save-1",
        )

        service.archive_project(project_id=project.id)

        # SoT §115 read-allowed: version list/read survives archive.
        versions = service.list_draft_versions(
            project_id=project.id, draft_id=draft.id
        )
        self.assertEqual([v.id for v in versions], [saved.draft_version.id])
        detail = service.get_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved.draft_version.id,
        )
        self.assertEqual(detail.snapshot.raw_text, "archived body")

    def test_source_ref_creation_allowed_on_archived(self):
        # SoT §115 carve-out (user decision): source_ref is a derived annotation
        # over an immutable, preserved snapshot, so creating one is allowed even
        # after archive — unlike content/metadata writes which are blocked.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )

        service.archive_project(project_id=project.id)

        source_ref = service.create_source_ref(
            project_id=project.id,
            snapshot_id=saved.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )
        self.assertEqual(source_ref.quote, "Paragraph")
        self.assertEqual(
            service.get_source_ref(project_id=project.id, source_ref_id=source_ref.id),
            source_ref,
        )

    def test_archive_preserves_source_ref(self):
        service, repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="Paragraph one.",
            idempotency_key="save-1",
        )
        source_ref = service.create_source_ref(
            project_id=project.id,
            snapshot_id=saved.snapshot.id,
            start_offset=0,
            end_offset=len("Paragraph"),
        )

        service.archive_project(project_id=project.id)

        # SoT §113: source_refs are preserved after archive.
        self.assertIn(source_ref.id, repo.source_refs)
        self.assertEqual(
            service.get_source_ref(project_id=project.id, source_ref_id=source_ref.id),
            source_ref,
        )


class CoreSotExportTest(unittest.TestCase):
    def test_export_body_matches_selected_version_verbatim(self):
        # Acceptance: exported body equals the selected version's snapshot, with
        # no AI metadata injected and no Markdown transformation. Locks against a
        # future change that derives the body from anything but raw_text.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        raw_text = "# Chapter 1\n\n사건이 시작된다.\n\n---\n\n다음 장면."
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="save-1",
        )

        export = service.export_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved.draft_version.id,
            fmt="txt",
        )

        self.assertEqual(export.body, raw_text)
        # Traceable to exactly the version it was produced from.
        self.assertEqual(export.version_id, saved.draft_version.id)
        self.assertEqual(export.version_number, saved.draft_version.version_number)
        self.assertEqual(export.snapshot_id, saved.snapshot.id)
        self.assertEqual(export.content_hash, saved.snapshot.content_hash)

    def test_export_picks_the_requested_version_not_the_latest(self):
        # Two versions exist; exporting v1 must return v1's body, never v2's.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        v1 = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="first body",
            idempotency_key="save-1",
        )
        service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="second body",
            idempotency_key="save-2",
        )

        export = service.export_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=v1.draft_version.id,
        )

        self.assertEqual(export.body, "first body")
        self.assertEqual(export.version_number, 1)

    def test_txt_and_markdown_differ_only_in_content_type_and_extension(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="# Heading\n\nbody",
            idempotency_key="save-1",
        )

        txt = service.export_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved.draft_version.id,
            fmt="txt",
        )
        md = service.export_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved.draft_version.id,
            fmt="markdown",
        )

        # Body is identical across formats (no transformation either way).
        self.assertEqual(txt.body, md.body)
        self.assertEqual(txt.body, "# Heading\n\nbody")
        self.assertTrue(txt.filename.endswith(".txt"))
        self.assertTrue(md.filename.endswith(".md"))
        self.assertIn("text/plain", txt.content_type)
        self.assertIn("text/markdown", md.content_type)

    def test_unsupported_format_is_rejected(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="body",
            idempotency_key="save-1",
        )

        with self.assertRaises(UnsupportedExportFormat):
            service.export_draft_version(
                project_id=project.id,
                draft_id=draft.id,
                version_id=saved.draft_version.id,
                fmt="pdf",
            )

    def test_export_missing_version_raises_not_found(self):
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")

        with self.assertRaises(NotFound):
            service.export_draft_version(
                project_id=project.id,
                draft_id=draft.id,
                version_id="nope",
            )

    def test_export_survives_archive(self):
        # SoT archive read-allowed policy (v1.5; "archive는 보존이자 읽기 전용
        # 상태다 — 읽기는 허용"): export is a read, so it survives archive.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="Episode 1")
        saved = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="archived body",
            idempotency_key="save-1",
        )

        service.archive_project(project_id=project.id)

        export = service.export_draft_version(
            project_id=project.id,
            draft_id=draft.id,
            version_id=saved.draft_version.id,
        )
        self.assertEqual(export.body, "archived body")


class ProjectExportContractTest(unittest.TestCase):
    """Writing Workspace V2 W4 whole-project export (D6=A, SoT v1.7.17).

    Ordered-latest export joins each non-archived unit's latest version in
    ``position`` order. Owner decisions locked here: a per-unit title heading
    (Markdown ``# {title}``, plain title line for txt), archived units excluded
    by default with an opt-in ``include_archived`` flag, and an on-request
    delivery manifest at the HTTP layer (covered by ProjectExportApiTest).
    """

    def _project_with_units(self, service):
        project = service.create_project(name="Novel")
        d1 = service.create_draft(project_id=project.id, title="1장. 출발")
        d2 = service.create_draft(project_id=project.id, title="2장. 도착")
        service.save_draft(
            project_id=project.id,
            draft_id=d1.id,
            raw_text="첫 장의 본문.",
            idempotency_key="d1-save-1",
        )
        service.save_draft(
            project_id=project.id,
            draft_id=d2.id,
            raw_text="둘째 장의 본문.",
            idempotency_key="d2-save-1",
        )
        return project, d1, d2

    def test_export_joins_ordered_latest_non_archived(self):
        # EX-01 (fire): non-archived units joined in position order, each latest
        # version, with a plain title line per unit for txt.
        service, _repo = _service()
        project, d1, d2 = self._project_with_units(service)

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(
            export.body,
            "1장. 출발\n\n첫 장의 본문.\n\n2장. 도착\n\n둘째 장의 본문.",
        )
        self.assertEqual(
            [unit.draft_id for unit in export.units], [d1.id, d2.id]
        )
        self.assertEqual([unit.position for unit in export.units], [1, 2])
        self.assertEqual(export.include_archived, False)
        self.assertEqual(export.filename, f"{project.id}.txt")

    def test_archived_units_excluded_by_default(self):
        # EX-02 (not fire): archived units must not leak into body or units.
        service, _repo = _service()
        project, d1, d2 = self._project_with_units(service)
        service.archive_draft(project_id=project.id, draft_id=d1.id)

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(export.body, "2장. 도착\n\n둘째 장의 본문.")
        self.assertEqual([unit.draft_id for unit in export.units], [d2.id])

    def test_include_archived_flag_includes_archived_units(self):
        # EX-03 (fire): the opt-in flag reinstates archived units in position
        # order (archive does not renumber position).
        service, _repo = _service()
        project, d1, d2 = self._project_with_units(service)
        service.archive_draft(project_id=project.id, draft_id=d1.id)

        export = service.export_project(
            project_id=project.id, fmt="txt", include_archived=True
        )

        self.assertEqual(
            export.body,
            "1장. 출발\n\n첫 장의 본문.\n\n2장. 도착\n\n둘째 장의 본문.",
        )
        self.assertEqual(
            [unit.draft_id for unit in export.units], [d1.id, d2.id]
        )
        self.assertEqual(export.include_archived, True)

    def test_export_uses_latest_version_per_unit(self):
        # EX-04 (fire): a second save must make export pick v2, never v1.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="1장")
        service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="v1 body",
            idempotency_key="save-1",
        )
        v2 = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="v2 body",
            idempotency_key="save-2",
        )

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(export.body, "1장\n\nv2 body")
        self.assertEqual(export.units[0].version_id, v2.draft_version.id)
        self.assertEqual(export.units[0].version_number, 2)
        self.assertEqual(export.units[0].content_hash, v2.snapshot.content_hash)

    def test_body_has_headings_and_verbatim_bodies_only(self):
        # EX-05 (not fire): no AI metadata is injected; only the title heading
        # and the verbatim snapshot bodies appear.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="1장")
        raw = "본문 문단 하나.\n\n두 번째 문단."
        service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw,
            idempotency_key="save-1",
        )

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(export.body, f"1장\n\n{raw}")

    def test_txt_and_markdown_heading_shapes(self):
        # EX-06 (fire): markdown uses '# {title}'; txt uses a plain title line.
        # The unit bodies are byte-identical across formats (no transformation).
        service, _repo = _service()
        project = service.create_project(name="Novel")
        draft = service.create_draft(project_id=project.id, title="1장")
        service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text="# already a heading\n\nbody",
            idempotency_key="save-1",
        )

        txt = service.export_project(project_id=project.id, fmt="txt")
        md = service.export_project(project_id=project.id, fmt="markdown")

        self.assertEqual(txt.body, "1장\n\n# already a heading\n\nbody")
        self.assertEqual(md.body, "# 1장\n\n# already a heading\n\nbody")
        self.assertTrue(txt.filename.endswith(".txt"))
        self.assertTrue(md.filename.endswith(".md"))
        self.assertIn("text/plain", txt.content_type)
        self.assertIn("text/markdown", md.content_type)

    def test_versionless_unit_is_skipped(self):
        # EX-07 (not fire): a draft with no saved version has no snapshot to
        # export and must be skipped from both body and units, without shifting
        # the order of the saved units.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        d1 = service.create_draft(project_id=project.id, title="1장")
        service.create_draft(project_id=project.id, title="2장 (미저장)")
        d3 = service.create_draft(project_id=project.id, title="3장")
        service.save_draft(
            project_id=project.id,
            draft_id=d1.id,
            raw_text="first",
            idempotency_key="d1-save",
        )
        service.save_draft(
            project_id=project.id,
            draft_id=d3.id,
            raw_text="third",
            idempotency_key="d3-save",
        )

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(export.body, "1장\n\nfirst\n\n3장\n\nthird")
        self.assertEqual(
            [unit.draft_id for unit in export.units], [d1.id, d3.id]
        )

    def test_unsupported_format_is_rejected(self):
        # Over-strict guard mirror for whole-project export.
        service, _repo = _service()
        project = service.create_project(name="Novel")
        with self.assertRaises(UnsupportedExportFormat):
            service.export_project(project_id=project.id, fmt="pdf")

    def test_missing_project_raises_not_found(self):
        service, _repo = _service()
        with self.assertRaises(NotFound):
            service.export_project(project_id="nope", fmt="txt")

    def test_archived_project_export_survives(self):
        # EX-11 mirror: archiving the project blocks writes, not reads; export
        # still returns the ordered units.
        service, _repo = _service()
        project, d1, _d2 = self._project_with_units(service)
        service.archive_project(project_id=project.id)

        export = service.export_project(project_id=project.id, fmt="txt")

        self.assertEqual(
            export.body,
            "1장. 출발\n\n첫 장의 본문.\n\n2장. 도착\n\n둘째 장의 본문.",
        )

    def test_empty_project_returns_empty_body(self):
        # EX-13 (not fire): a project with no exportable unit (no drafts, or all
        # drafts version-less) yields an empty body and empty units, with no
        # synthesized heading or separator. Locks W0 contract §6.3
        # ("포함 unit이 0개면 body는 빈 문자열이다").
        service, _repo = _service()
        empty = service.create_project(name="Empty")
        service.create_draft(project_id=empty.id, title="아직 안 쓴 장")

        export = service.export_project(project_id=empty.id, fmt="markdown")

        self.assertEqual(export.body, "")
        self.assertEqual(export.units, ())


if __name__ == "__main__":
    unittest.main()
