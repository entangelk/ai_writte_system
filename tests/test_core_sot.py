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


if __name__ == "__main__":
    unittest.main()
