"""W3 ordered-unit contract and two-directional regression guards."""

import asyncio
from dataclasses import replace
import unittest

import httpx

from services.application.app.core_sot.models import Draft, UnitKind
from services.application.app.core_sot.ordered_unit_migration import (
    OrderedUnitMigrationService,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    DraftOrderIntegrityError,
    InMemoryCoreSotRepository,
    InvalidDraftOrder,
)
from services.application.app.main import create_app
from tests.auth_support import authenticate


class CountingRepository(InMemoryCoreSotRepository):
    def __init__(self) -> None:
        super().__init__()
        self.metadata_writes = 0
        self.fail_after_metadata_write: int | None = None
        self.fail_with_set_change = False

    def replace_draft_metadata(self, project_id, drafts) -> None:
        if self.fail_with_set_change:
            from services.application.app.core_sot.repository import DraftSetChanged

            raise DraftSetChanged("injected concurrent draft-set change")
        self.metadata_writes += 1
        super().replace_draft_metadata(project_id, drafts)

    def _after_draft_metadata_write(self, draft: Draft) -> None:
        if self.fail_after_metadata_write is not None:
            self.fail_after_metadata_write -= 1
            if self.fail_after_metadata_write == 0:
                raise RuntimeError("injected metadata write failure")


def _seed_legacy(repo: InMemoryCoreSotRepository, project_id: str, count: int):
    drafts = []
    for index in range(1, count + 1):
        draft = Draft(
            id=f"legacy-{index}",
            project_id=project_id,
            title=f"Legacy {index}",
            archived=index == 2,
        )
        repo.drafts[draft.id] = draft
        drafts.append(draft)
    return tuple(drafts)


class OrderedUnitMigrationTest(unittest.TestCase):
    def setUp(self):
        self.repo = CountingRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="Novel")

    def test_legacy_drafts_migrate_in_repository_order(self):
        """OU-01: missing metadata fires; order and archived membership persist."""
        legacy = _seed_legacy(self.repo, self.project.id, 3)

        report = OrderedUnitMigrationService(self.repo).run()

        migrated = self.repo.list_drafts(self.project.id)
        self.assertTrue(report.succeeded)
        self.assertEqual([draft.id for draft in migrated], [d.id for d in legacy])
        self.assertEqual([draft.unit_kind for draft in migrated], [UnitKind.OTHER] * 3)
        self.assertEqual([draft.position for draft in migrated], [1, 2, 3])
        self.assertTrue(migrated[1].archived)

    def test_valid_project_rerun_is_noop(self):
        """OU-02: valid metadata must not be rewritten on a rerun."""
        _seed_legacy(self.repo, self.project.id, 2)
        migration = OrderedUnitMigrationService(self.repo)
        migration.run()
        before = tuple(self.repo.drafts.values())
        writes_before = self.repo.metadata_writes

        report = migration.run()

        self.assertEqual(tuple(self.repo.drafts.values()), before)
        self.assertEqual(self.repo.metadata_writes, writes_before)
        self.assertEqual(report.unchanged_project_ids, (self.project.id,))

    def test_invalid_partial_state_fails_without_write(self):
        """OU-03: mixed/duplicate/gapped/unknown states all fail closed."""
        cases = {
            "mixed": (
                Draft("a", self.project.id, "A"),
                Draft("b", self.project.id, "B", unit_kind=UnitKind.OTHER, position=2),
            ),
            "duplicate": (
                Draft("a", self.project.id, "A", unit_kind=UnitKind.OTHER, position=1),
                Draft("b", self.project.id, "B", unit_kind=UnitKind.OTHER, position=1),
            ),
            "gapped": (
                Draft("a", self.project.id, "A", unit_kind=UnitKind.OTHER, position=1),
                Draft("b", self.project.id, "B", unit_kind=UnitKind.OTHER, position=3),
            ),
            "unknown": (
                Draft("a", self.project.id, "A", unit_kind="volume", position=1),
            ),
        }
        for name, drafts in cases.items():
            with self.subTest(name=name):
                self.repo.drafts = {draft.id: draft for draft in drafts}
                before = dict(self.repo.drafts)
                writes_before = self.repo.metadata_writes

                report = OrderedUnitMigrationService(self.repo).run()

                self.assertFalse(report.succeeded)
                self.assertEqual(self.repo.drafts, before)
                self.assertEqual(self.repo.metadata_writes, writes_before)
                self.assertFalse(report.position_index_installed)

    def test_migration_preserves_existing_draft_artifacts(self):
        """OU-04: migration changes no draft-save identity or immutable body."""
        draft = _seed_legacy(self.repo, self.project.id, 1)[0]
        saved = self.service.save_draft(
            project_id=self.project.id,
            draft_id=draft.id,
            raw_text="immutable body",
            idempotency_key="save-1",
        )
        before = (
            dict(self.repo.versions),
            dict(self.repo.snapshots),
            dict(self.repo.blocks_by_snapshot),
        )

        OrderedUnitMigrationService(self.repo).run()

        self.assertEqual(tuple(self.repo.drafts), (draft.id,))
        self.assertEqual(
            (self.repo.versions, self.repo.snapshots, self.repo.blocks_by_snapshot),
            before,
        )
        self.assertEqual(self.repo.snapshots[saved.snapshot.id].raw_text, "immutable body")

    def test_nontransaction_fallback_failure_leaves_no_partial_order(self):
        """OU-13: injected mid-write failure restores the full before-image."""
        _seed_legacy(self.repo, self.project.id, 3)
        before = dict(self.repo.drafts)
        self.repo.fail_after_metadata_write = 2

        report = OrderedUnitMigrationService(self.repo).run()

        self.assertFalse(report.succeeded)
        self.assertEqual(self.repo.drafts, before)
        self.assertFalse(report.position_index_installed)

    def test_nontransaction_fallback_success_commits_exact_order(self):
        """OU-14: normal fallback commits once without an over-strict rollback."""
        _seed_legacy(self.repo, self.project.id, 3)

        report = OrderedUnitMigrationService(self.repo).run()

        self.assertTrue(report.succeeded)
        self.assertEqual(self.repo.metadata_writes, 1)
        self.assertEqual(
            [draft.position for draft in self.repo.list_drafts(self.project.id)],
            [1, 2, 3],
        )


class OrderedUnitContractTest(unittest.TestCase):
    def setUp(self):
        self.repo = CountingRepository()
        self.service = CoreSotService(self.repo)
        self.project = self.service.create_project(name="Novel")

    def test_create_appends_ordered_unit(self):
        """OU-05: requested/default kinds append at exact N+1."""
        first = self.service.create_draft(
            project_id=self.project.id, title="One", unit_kind=UnitKind.CHAPTER
        )
        second = self.service.create_draft(project_id=self.project.id, title="Two")

        self.assertEqual((first.unit_kind, first.position), (UnitKind.CHAPTER, 1))
        self.assertEqual((second.unit_kind, second.position), (UnitKind.OTHER, 2))
        with self.assertRaises(InvalidDraftOrder):
            self.service.create_draft(
                project_id=self.project.id, title="Bad", unit_kind="volume"
            )
        self.assertEqual(len(self.repo.list_drafts(self.project.id)), 2)

    def test_stored_legacy_data_raises_integrity_subclass(self):
        """Server-integrity vs. input error boundary (503 vs. 4xx classification).

        Under-strict: a stored pre-W3 legacy draft (no unit_kind/position) must
        raise ``DraftOrderIntegrityError`` from ``list_drafts`` — the marker the
        HTTP layer maps to 503. If someone reverts ``_require_ordered_drafts`` to
        the bare ``InvalidDraftOrder``, this fails.

        Over-strict: a bad ``unit_kind`` on create is a *client* input error and
        must stay a plain ``InvalidDraftOrder`` that is NOT the integrity
        subclass — otherwise it would be wrongly swept into the 503 path.
        """
        _seed_legacy(self.repo, self.project.id, count=2)
        with self.assertRaises(DraftOrderIntegrityError):
            self.service.list_drafts(project_id=self.project.id)

        # Over-strict guard: the input-validation face must not be reclassified.
        fresh = CoreSotService(CountingRepository())
        project = fresh.create_project(name="Fresh")
        try:
            fresh.create_draft(
                project_id=project.id, title="Bad", unit_kind="volume"
            )
        except DraftOrderIntegrityError:  # pragma: no cover - guard trips test
            self.fail("bad unit_kind must not raise the integrity subclass")
        except InvalidDraftOrder:
            pass
        else:
            self.fail("bad unit_kind must raise InvalidDraftOrder")

    def test_full_permutation_reorders_atomically(self):
        """OU-07: a complete permutation commits exact contiguous positions."""
        drafts = tuple(
            self.service.create_draft(project_id=self.project.id, title=str(index))
            for index in range(3)
        )

        result = self.service.reorder_drafts(
            project_id=self.project.id,
            ordered_draft_ids=(drafts[2].id, drafts[0].id, drafts[1].id),
        )

        self.assertEqual(
            [draft.id for draft in result],
            [drafts[2].id, drafts[0].id, drafts[1].id],
        )
        self.assertEqual([draft.position for draft in result], [1, 2, 3])
        self.assertEqual(self.repo.metadata_writes, 1)

    def test_same_permutation_is_naturally_idempotent(self):
        """OU-09: same-order replay must not invoke persistence mutation."""
        drafts = tuple(
            self.service.create_draft(project_id=self.project.id, title=str(index))
            for index in range(2)
        )

        result = self.service.reorder_drafts(
            project_id=self.project.id,
            ordered_draft_ids=tuple(draft.id for draft in drafts),
        )

        self.assertEqual(result, drafts)
        self.assertEqual(self.repo.metadata_writes, 0)

    def test_archive_preserves_total_order(self):
        """OU-10: archive changes status only, never compacts positions."""
        first = self.service.create_draft(project_id=self.project.id, title="One")
        second = self.service.create_draft(project_id=self.project.id, title="Two")

        self.service.archive_draft(project_id=self.project.id, draft_id=first.id)

        listed = self.service.list_drafts(project_id=self.project.id)
        self.assertEqual([draft.position for draft in listed], [1, 2])
        self.assertTrue(listed[0].archived)
        self.assertEqual(listed[1].id, second.id)


class OrderedUnitApiTest(unittest.TestCase):
    def setUp(self):
        self.repo = CountingRepository()
        self.service = CoreSotService(self.repo)
        self.app = create_app(self.service)
        authenticate(self.app)

    def request(self, method: str, path: str, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def create_project(self):
        return self.request("POST", "/projects", json={"name": "Novel"}).json()

    def create_draft(self, project_id: str, title: str):
        return self.request(
            "POST", f"/projects/{project_id}/drafts", json={"title": title}
        ).json()

    def test_invalid_unit_metadata_rejected(self):
        """OU-06: bool/zero/unknown kinds and client positions store nothing."""
        project = self.create_project()
        for payload in (
            {"title": "Bad", "unit_kind": True},
            {"title": "Bad", "unit_kind": 0},
            {"title": "Bad", "unit_kind": "volume"},
            {"title": "Bad", "position": 1},
        ):
            with self.subTest(payload=payload):
                response = self.request(
                    "POST", f"/projects/{project['id']}/drafts", json=payload
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.repo.list_drafts(project["id"]), ())

    def test_invalid_permutation_rejected_without_write(self):
        """OU-08: missing/duplicate/foreign/unknown permutations write zero."""
        project = self.create_project()
        foreign_project = self.create_project()
        first = self.create_draft(project["id"], "One")
        second = self.create_draft(project["id"], "Two")
        foreign = self.create_draft(foreign_project["id"], "Foreign")
        before = tuple(self.repo.list_drafts(project["id"]))
        for ids in (
            [first["id"]],
            [first["id"], first["id"]],
            [first["id"], foreign["id"]],
            [first["id"], "unknown"],
        ):
            with self.subTest(ids=ids):
                response = self.request(
                    "PUT",
                    f"/projects/{project['id']}/draft-order",
                    json={"ordered_draft_ids": ids},
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(tuple(self.repo.list_drafts(project["id"])), before)
        self.repo.fail_with_set_change = True
        changed_during_write = self.request(
            "PUT",
            f"/projects/{project['id']}/draft-order",
            json={"ordered_draft_ids": [second["id"], first["id"]]},
        )
        self.assertEqual(changed_during_write.status_code, 409)
        self.assertEqual(tuple(self.repo.list_drafts(project["id"])), before)
        self.assertEqual(self.repo.metadata_writes, 0)
        self.assertEqual(second["position"], 2)

    def test_archived_project_reorder_rejected_without_write(self):
        """OU-11: archived project reorder is 409 and mutation-free."""
        project = self.create_project()
        draft = self.create_draft(project["id"], "One")
        self.request("DELETE", f"/projects/{project['id']}")

        response = self.request(
            "PUT",
            f"/projects/{project['id']}/draft-order",
            json={"ordered_draft_ids": [draft["id"]]},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.repo.metadata_writes, 0)

    def test_missing_project_reorder_returns_not_found(self):
        """OU-12: absent project is distinguished as 404, with no write."""
        response = self.request(
            "PUT", "/projects/missing/draft-order", json={"ordered_draft_ids": []}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.repo.metadata_writes, 0)
