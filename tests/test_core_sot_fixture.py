import unittest

from tests.fixtures.core_sot import (
    CONTENT_HASH,
    EXPECTED_BLOCKS,
    EXPECTED_SOURCE_REFS,
    IDEMPOTENCY_KEY,
    RAW_TEXT,
    build_core_sot_fixture,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)


class CoreSotReusableFixtureTest(unittest.TestCase):
    def test_fixture_locks_snapshot_blocks_and_source_refs(self):
        fixture = build_core_sot_fixture()

        self.assertEqual(fixture.save.snapshot.raw_text, RAW_TEXT)
        self.assertEqual(fixture.save.snapshot.content_hash, CONTENT_HASH)
        self.assertEqual(fixture.save.draft_version.version_number, 1)
        self.assertFalse(fixture.save.idempotent_replay)

        actual_blocks = tuple(
            (
                block.block_index,
                block.kind,
                block.start_offset,
                block.end_offset,
                block.text,
            )
            for block in fixture.save.blocks
        )
        expected_blocks = tuple(
            (
                block.block_index,
                block.kind,
                block.start_offset,
                block.end_offset,
                block.text,
            )
            for block in EXPECTED_BLOCKS
        )
        self.assertEqual(actual_blocks, expected_blocks)

        blocks_by_index = {
            block.block_index: block for block in fixture.save.blocks
        }
        for expected in EXPECTED_SOURCE_REFS:
            with self.subTest(source_ref=expected.name):
                source_ref = fixture.source_refs[expected.name]
                expected_block = blocks_by_index[expected.block_index]
                self.assertEqual(source_ref.project_id, fixture.project.id)
                self.assertEqual(source_ref.snapshot_id, fixture.save.snapshot.id)
                self.assertEqual(source_ref.block_id, expected_block.id)
                self.assertEqual(source_ref.start_offset, expected.start_offset)
                self.assertEqual(source_ref.end_offset, expected.end_offset)
                self.assertEqual(source_ref.quote, expected.quote)
                self.assertEqual(source_ref.content_hash, CONTENT_HASH)
                self.assertEqual(
                    fixture.service.get_source_ref(
                        project_id=fixture.project.id,
                        source_ref_id=source_ref.id,
                    ),
                    source_ref,
                )

    def test_fixture_idempotency_key_replays_same_version(self):
        fixture = build_core_sot_fixture()

        replay = fixture.service.save_draft(
            project_id=fixture.project.id,
            draft_id=fixture.draft.id,
            raw_text="changed retry body",
            idempotency_key=IDEMPOTENCY_KEY,
        )

        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(replay.draft_version.id, fixture.save.draft_version.id)
        self.assertEqual(replay.snapshot.raw_text, RAW_TEXT)

    def test_multibyte_offsets_are_unicode_code_point_indices(self):
        service = CoreSotService(InMemoryCoreSotRepository())
        project = service.create_project(name="Unicode Fixture")
        draft = service.create_draft(project_id=project.id, title="한글")
        raw_text = "# 장면\n\n민아는 파란 문을 열었다."
        phrase = "파란"
        start_offset = raw_text.index(phrase)
        end_offset = start_offset + len(phrase)
        byte_start = len(raw_text[:start_offset].encode("utf-8"))

        self.assertNotEqual(start_offset, byte_start)

        save = service.save_draft(
            project_id=project.id,
            draft_id=draft.id,
            raw_text=raw_text,
            idempotency_key="unicode-save-1",
        )
        source_ref = service.create_source_ref(
            project_id=project.id,
            snapshot_id=save.snapshot.id,
            start_offset=start_offset,
            end_offset=end_offset,
        )

        self.assertEqual(source_ref.quote, phrase)
        self.assertEqual(raw_text[start_offset:end_offset], phrase)


if __name__ == "__main__":
    unittest.main()
