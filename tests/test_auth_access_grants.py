"""Administrator access grants (D8-5e, F1=C) — service rules and Mongo round-trip.

HTTP behaviour (what a live grant opens and refuses) lives in
``test_auth_api.py::AdminAccessGrantTest``. This module drives the domain
directly, so the owner decisions have a guard that does not depend on routing:
C-1 (1시간 TTL) · C-3 (append-only = the issuance audit record) · C-5 (사유 필수).
"""

import unittest
from datetime import UTC, datetime, timedelta

from services.application.app.auth.access_grants import (
    DEFAULT_ACCESS_GRANT_TTL,
    AccessGrantService,
    InMemoryAccessGrantRepository,
)
from services.application.app.auth.access_grants_mongo import (
    MongoAccessGrantRepository,
)
from services.application.app.auth.models import AccessGrant

_T0 = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def _service(clock=None):
    return AccessGrantService(
        InMemoryAccessGrantRepository(), clock=clock or (lambda: _T0)
    )


class AccessGrantServiceTest(unittest.TestCase):
    def test_the_ttl_literal_is_one_hour(self) -> None:
        # C-1 (owner 2026-08-02). A contract literal, not a tuning knob: pinning
        # it here means widening the window is a visible, deliberate edit.
        self.assertEqual(DEFAULT_ACCESS_GRANT_TTL, timedelta(hours=1))
        grant = _service().issue(
            admin_user_id="admin:1", project_id="p1", reason="지원"
        )
        self.assertEqual(grant.expires_at - grant.created_at, timedelta(hours=1))

    def test_a_blank_reason_is_refused_at_the_domain_boundary(self) -> None:
        # C-5. Enforced here rather than only in the HTTP model, so a script
        # cannot mint a reasonless grant. Whitespace counts as blank.
        service = _service()
        for reason in ["", "   ", "\n\t"]:
            with self.subTest(reason=repr(reason)):
                with self.assertRaises(ValueError):
                    service.issue(
                        admin_user_id="admin:1", project_id="p1", reason=reason
                    )

    def test_active_returns_the_grant_before_expiry_and_none_after(self) -> None:
        now = _T0
        service = _service(clock=lambda: now)
        service.issue(admin_user_id="admin:1", project_id="p1", reason="지원")

        self.assertIsNotNone(
            service.active(admin_user_id="admin:1", project_id="p1")
        )
        now = _T0 + timedelta(hours=1)  # expiry is exclusive: <= now is expired
        self.assertIsNone(service.active(admin_user_id="admin:1", project_id="p1"))

    def test_expiry_is_a_judgement_not_a_delete(self) -> None:
        # C-3: the row *is* the issuance audit record. Over-strict guard against
        # a future "cleanup" that reaps expired grants — the store must still
        # hold it long after the grant stopped working.
        now = _T0
        service = _service(clock=lambda: now)
        service.issue(admin_user_id="admin:1", project_id="p1", reason="감사 대상")
        now = _T0 + timedelta(days=365)

        self.assertIsNone(service.active(admin_user_id="admin:1", project_id="p1"))
        row = service._repo.latest_for(admin_user_id="admin:1", project_id="p1")
        self.assertIsNotNone(row)
        self.assertEqual(row.reason, "감사 대상")

    def test_a_grant_is_scoped_to_one_admin_and_one_project(self) -> None:
        # Both directions of the scope. If either leaked, "expiring reach into
        # one project" would quietly become something much wider.
        service = _service()
        service.issue(admin_user_id="admin:1", project_id="p1", reason="지원")

        self.assertIsNone(service.active(admin_user_id="admin:1", project_id="p2"))
        self.assertIsNone(service.active(admin_user_id="admin:2", project_id="p1"))

    def test_reissuing_extends_by_taking_the_latest_row(self) -> None:
        # Append-only means a second issue does not overwrite the first; the
        # newest row is the one that counts, and the older one stays as history.
        now = _T0
        service = _service(clock=lambda: now)
        service.issue(admin_user_id="admin:1", project_id="p1", reason="첫 번째")
        now = _T0 + timedelta(minutes=59)
        service.issue(admin_user_id="admin:1", project_id="p1", reason="두 번째")

        now = _T0 + timedelta(minutes=61)  # past the first grant's expiry
        active = service.active(admin_user_id="admin:1", project_id="p1")
        self.assertIsNotNone(active)
        self.assertEqual(active.reason, "두 번째")

    def test_purging_a_project_removes_its_grants(self) -> None:
        # D5: grants carry a project id and the reason someone read it, so they
        # are project-scoped data and must not survive the project.
        service = _service()
        service.issue(admin_user_id="admin:1", project_id="p1", reason="지원")
        service.issue(admin_user_id="admin:1", project_id="p2", reason="지원")

        service.purge_project(project_id="p1")
        self.assertIsNone(
            service._repo.latest_for(admin_user_id="admin:1", project_id="p1")
        )
        self.assertIsNotNone(
            service._repo.latest_for(admin_user_id="admin:1", project_id="p2")
        )


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, *, name=None, **kwargs):
        self.indexes.append((keys, name, kwargs))

    def insert_one(self, doc):
        # The driver stores BSON UTC and hands it back **naive**. Stripping at
        # write time (rather than mutating docs in setUp) means every later
        # insert behaves the same way — otherwise a test that adds a row after
        # setUp silently gets aware dates the deployment would never return.
        stored = dict(doc)
        for field in ("created_at", "expires_at"):
            stored[field] = stored[field].replace(tzinfo=None)
        self.docs[doc["_id"]] = stored

    def find_one(self, query, sort=None):
        matches = [
            doc for doc in self.docs.values()
            if all(doc.get(key) == value for key, value in query.items())
        ]
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda d: d[field], reverse=direction < 0)
        return matches[0] if matches else None

    def delete_many(self, query):
        for key in [
            k for k, d in self.docs.items()
            if all(d.get(f) == v for f, v in query.items())
        ]:
            del self.docs[key]


class _Database:
    """Serves the two collections the repository opens, and nothing else.

    The assert is the point: a repository that starts touching a third
    collection has to say so here rather than silently getting a fake.
    """

    def __init__(self, grants, uses):
        self._by_name = {"access_grants": grants, "access_grant_uses": uses}

    def __getitem__(self, name):
        assert name in self._by_name, name
        return self._by_name[name]


class _Client:
    def __init__(self, grants, uses):
        self.database = _Database(grants, uses)

    def __getitem__(self, _name):
        return self.database


def _grant(grant_id="g1", project_id="p1", created_at=_T0):
    return AccessGrant(
        id=grant_id, admin_user_id="admin:1", project_id=project_id,
        reason="지원", created_at=created_at,
        expires_at=created_at + timedelta(hours=1),
    )


class MongoAccessGrantRepositoryTest(unittest.TestCase):
    """The same naive-BSON trap sessions hit in deployment (2026-07-27).

    The fake collection hands dates back **naive**, the way the driver actually
    does, so a missing re-labeling fails here instead of only in production.
    """

    def setUp(self) -> None:
        self.collection = _Collection()
        self.uses = _Collection()
        self.repo = MongoAccessGrantRepository(
            _Client(self.collection, self.uses)
        )
        self.repo.insert(_grant())

    def test_read_back_timestamps_are_utc_aware(self) -> None:
        # Under-strict: drop `_aware` and both asserts fail — which in the
        # deployment is `active()` raising TypeError on every grant check.
        grant = self.repo.latest_for(admin_user_id="admin:1", project_id="p1")
        self.assertIsNotNone(grant.created_at.tzinfo)
        self.assertIsNotNone(grant.expires_at.tzinfo)

    def test_normalization_does_not_shift_the_instant(self) -> None:
        # Over-strict: BSON already stores UTC, so re-labeling must not move the
        # value. A tz *conversion* here would silently change when a grant dies.
        grant = self.repo.latest_for(admin_user_id="admin:1", project_id="p1")
        self.assertEqual(grant.created_at, _T0)
        self.assertEqual(grant.expires_at, _T0 + timedelta(hours=1))

    def test_the_service_judges_expiry_against_naive_stored_dates(self) -> None:
        service = AccessGrantService(self.repo, clock=lambda: _T0 + timedelta(minutes=1))
        self.assertIsNotNone(
            service.active(admin_user_id="admin:1", project_id="p1")
        )

    def test_there_is_no_ttl_index_on_either_collection(self) -> None:
        # ★ The deliberate difference from `sessions`. A TTL index would let
        # Mongo reap expired grants (or the record of what was read under them),
        # deleting the evidence that an access happened (C-3). Sessions have
        # one; neither of these may.
        for label, collection in [
            ("access_grants", self.collection), ("access_grant_uses", self.uses),
        ]:
            self.assertTrue(collection.indexes, f"{label}: an index is expected")
            for _keys, name, kwargs in collection.indexes:
                with self.subTest(collection=label, index=name):
                    self.assertNotIn("expireAfterSeconds", kwargs)

    def test_latest_for_returns_the_newest_row(self) -> None:
        self.repo.insert(_grant(grant_id="g2", created_at=_T0 + timedelta(minutes=30)))
        grant = self.repo.latest_for(admin_user_id="admin:1", project_id="p1")
        self.assertEqual(grant.id, "g2")

    def test_purge_removes_only_the_named_project(self) -> None:
        self.repo.insert(_grant(grant_id="g2", project_id="p2"))
        self.repo.purge_project(project_id="p1")
        self.assertIsNone(
            self.repo.latest_for(admin_user_id="admin:1", project_id="p1")
        )
        self.assertIsNotNone(
            self.repo.latest_for(admin_user_id="admin:1", project_id="p2")
        )


if __name__ == "__main__":
    unittest.main()
