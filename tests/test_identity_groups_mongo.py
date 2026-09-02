"""미승인 후보 정체성 그룹 Slice 0 — Mongo 어댑터 round-trip.

선례(``test_writing_loop_audit_mongo.py``·``test_gate_findings_mongo.py``)를 따른
fake-collection round-trip이 표준 suite에서 ``_doc``↔모델 필드 드리프트를 잡고,
test-mongo(rs-test)가 있으면 실 Mongo round-trip이 같은 계약을 잰다
(계획 Slice 0 검증 축: "in-memory와 Mongo round-trip").

unique/index 축 전부에 ``project_id``·``candidate_type``이 들어가야 한다 —
계획의 격리 문장이자 오너 결정(2026-09-02, relation 포함).
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError

    from services.application.app.analysis.identity_groups_mongo import (
        MongoCandidateIdentityGroupRepository,
    )

    _PYMONGO_AVAILABLE = True
except ImportError:  # pragma: no cover - test shell without pymongo
    MongoClient = None
    ConnectionFailure = PyMongoError = Exception
    MongoCandidateIdentityGroupRepository = None
    _PYMONGO_AVAILABLE = False

from services.application.app.analysis.models import AnalysisCandidateType
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroup,
    CandidateIdentityGroupMember,
    CandidateIdentityGroupService,
    CandidateIdentityRelation,
    IdentityGroupMemberStatus,
    IdentityGroupStatus,
    IdentityRelationVerdict,
)

_CHARACTER = AnalysisCandidateType.CHARACTER_OBSERVATION
_EVENT = AnalysisCandidateType.EVENT_OBSERVATION
_MONGO_URI = os.environ.get(
    "CORE_SOT_TEST_MONGO_URI", "mongodb://localhost:27020/?replicaSet=rs-test"
)


class _Cursor(list):
    def sort(self, keys):
        docs = list(self)
        for key, direction in reversed(keys):
            docs.sort(
                key=lambda doc: doc.get(key) or "", reverse=(direction == -1)
            )
        return _Cursor(docs)


class _Collection:
    def __init__(self):
        self.docs: list[dict] = []
        self.indexes: list[tuple[list, dict]] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def _matches(self, doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    def replace_one(self, query, doc, upsert=False):
        assert upsert, "adapter must upsert (idempotent writes)"
        for i, existing in enumerate(self.docs):
            if self._matches(existing, query):
                self.docs[i] = dict(doc)
                return
        self.docs.append(dict(doc))

    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query):
        return _Cursor(
            dict(doc) for doc in self.docs if self._matches(doc, query)
        )

    def delete_many(self, query):
        kept = [doc for doc in self.docs if not self._matches(doc, query)]
        removed = len(self.docs) - len(kept)
        self.docs = kept
        return removed


class _Database:
    def __init__(self, collections: dict[str, _Collection]):
        self._collections = collections

    def __getitem__(self, name):
        return self._collections[name]


class _Client:
    def __init__(self, collections):
        self.database = _Database(collections)

    def __getitem__(self, _name):
        return self.database


def _group(group_id="cig:a", project="p1", *, status=None, revision=0):
    at = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    return CandidateIdentityGroup(
        group_id=group_id, project_id=project,
        candidate_type=_CHARACTER,
        status=status or IdentityGroupStatus.OPEN,
        revision=revision, created_at=at, updated_at=at,
    )


def _member(group_id="cig:a", candidate_id="cand:a", project="p1"):
    return CandidateIdentityGroupMember(
        group_id=group_id, candidate_id=candidate_id,
        project_id=project, candidate_type=_CHARACTER,
        member_status=IdentityGroupMemberStatus.ACTIVE,
        added_at=datetime(2026, 9, 2, 12, 1, tzinfo=UTC),
    )


def _relation(project="p1", left="cand:a", right="cand:b", group_id="cig:a"):
    return CandidateIdentityRelation(
        project_id=project, candidate_type=_CHARACTER,
        left_candidate_id=left, right_candidate_id=right,
        verdict=IdentityRelationVerdict.SAME,
        rationale="근거", source="identity_judge",
        group_id=group_id,
        created_at=datetime(2026, 9, 2, 12, 2, tzinfo=UTC),
    )


class MongoCandidateIdentityGroupRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.groups = _Collection()
        self.members = _Collection()
        self.relations = _Collection()
        self.repo = MongoCandidateIdentityGroupRepository(
            _Client({
                "candidate_identity_groups": self.groups,
                "candidate_identity_group_members": self.members,
                "candidate_identity_relations": self.relations,
            }),
            db_name="test",
        )

    def test_installs_indexes_with_stable_names_and_scoped_axes(self):
        # 모든 unique/index 축에 project_id·candidate_type 선행 — 계획 격리 문장.
        self.assertEqual(
            self.groups.indexes,
            [(
                [("project_id", 1), ("candidate_type", 1), ("status", 1)],
                {"name": "candidate_identity_groups_by_project_type_status"},
            )],
        )
        self.assertEqual(
            self.members.indexes,
            [(
                [
                    ("project_id", 1), ("candidate_type", 1),
                    ("group_id", 1), ("candidate_id", 1),
                ],
                {"name": "uniq_candidate_identity_group_member", "unique": True},
            )],
        )
        self.assertEqual(
            self.relations.indexes,
            [(
                [
                    ("project_id", 1), ("candidate_type", 1),
                    ("left_candidate_id", 1), ("right_candidate_id", 1),
                ],
                {"name": "uniq_candidate_identity_relation", "unique": True},
            )],
        )

    def test_group_round_trip_field_for_field(self):
        group = _group(status=IdentityGroupStatus.CONTRADICTED,
                       revision=3)
        self.repo.save_group(group)

        self.assertEqual(self.repo.get_group("cig:a"), group)
        self.assertIsNone(self.repo.get_group("cig:ghost"))
        self.assertEqual(self.repo.list_groups("p1"), (group,))
        self.assertEqual(self.repo.list_groups("p2"), ())

    def test_member_round_trip_and_idempotent_upsert(self):
        member = _member()
        self.repo.upsert_member(member)
        self.repo.upsert_member(member)

        self.assertEqual(len(self.members.docs), 1)
        self.assertEqual(
            self.repo.get_member("p1", _CHARACTER, "cig:a", "cand:a"), member
        )
        self.assertIsNone(
            self.repo.get_member("p2", _CHARACTER, "cig:a", "cand:a")
        )
        self.assertIsNone(
            self.repo.get_member("p1", _EVENT, "cig:a", "cand:a")
        )
        self.assertEqual(self.repo.list_members("p1", "cig:a"), (member,))
        self.assertEqual(self.repo.list_members("p1", "cig:other"), ())

    def test_relation_round_trip_on_normalized_pair(self):
        relation = _relation()
        self.repo.upsert_relation(relation)

        self.assertEqual(
            self.repo.get_relation("p1", _CHARACTER, "cand:a", "cand:b"),
            relation,
        )
        # 반대 방향 조회는 서비스가 정규화해서 들어온다 — 저장 축은 정규형 하나.
        self.assertIsNone(
            self.repo.get_relation("p1", _CHARACTER, "cand:b", "cand:a")
        )
        self.assertIsNone(
            self.repo.get_relation("p1", _EVENT, "cand:a", "cand:b")
        )
        self.assertEqual(self.repo.list_relations("p1"), (relation,))
        self.assertEqual(self.repo.list_relations("p2"), ())

    def test_purge_project_deletes_all_three_collections(self):
        self.repo.save_group(_group())
        self.repo.save_group(_group("cig:other", project="p2"))
        self.repo.upsert_member(_member())
        self.repo.upsert_member(_member("cig:other", "cand:z", project="p2"))
        self.repo.upsert_relation(_relation())
        self.repo.upsert_relation(_relation(project="p2"))

        self.repo.purge_project("p1")

        self.assertEqual(len(self.groups.docs), 1)
        self.assertEqual(len(self.members.docs), 1)
        self.assertEqual(len(self.relations.docs), 1)
        self.assertEqual(self.repo.list_groups("p1"), ())
        self.assertEqual(self.repo.list_relations("p1"), ())
        # 인접 project 잔류 — 과잉 파기 방향.
        self.assertEqual(len(self.repo.list_groups("p2")), 1)


# --- 실 Mongo round-trip (test-mongo 있을 때만) ------------------------------

_MONGO_AVAILABLE = False
try:
    if _PYMONGO_AVAILABLE:
        _probe = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        _probe.admin.command("ping")
        _probe.close()
        _MONGO_AVAILABLE = True
except (ConnectionFailure, PyMongoError):  # pragma: no cover
    pass


@unittest.skipUnless(_MONGO_AVAILABLE, "test-mongo (rs-test) not reachable")
class MongoCandidateIdentityGroupLiveRoundTripTest(unittest.TestCase):
    """같은 service 계약을 실 Mongo에서 잰다.

    fake 컬렉션이 구조적으로 못 잡는 경계가 둘 — ① 반대 방향 pair가 별도 행으로
    쌓이는 것(정규화의 실질 효과)과 ② pymongo가 naive datetime을 돌려주는 읽기
    경계(검증 B1, sessions 사고와 같은 형태). 둘 다 이 셀이 잠근다."""

    def setUp(self):
        self._client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=800)
        self._db_name = f"identity_groups_test_{uuid.uuid4().hex}"
        self.repo = MongoCandidateIdentityGroupRepository(
            self._client, db_name=self._db_name
        )
        # B1: µs≠0 클록 — BSON 날짼 ms 절단이라 서비스 클록이 같은 해상도로
        # 절단되지 않으면 실몽고 왕복의 데이터클래스 동등성이 깨진다(프로브 실측
        # 760724µs→760000µs). 기본 클록은 운에 맡기는 셈이니 주입으로 고정한다.
        self.clock_value = datetime(2026, 9, 2, 13, 0, 0, 760724, tzinfo=UTC)
        self.service = CandidateIdentityGroupService(
            self.repo, clock=lambda: self.clock_value
        )

    def tearDown(self):
        self._client.drop_database(self._db_name)
        self._client.close()

    def test_round_trip_isolation_and_purge(self):
        group = self.service.create_group("p1", _CHARACTER)
        member = self.service.add_member("p1", group.group_id, "cand:a", _CHARACTER)
        self.service.add_member("p1", group.group_id, "cand:a", _CHARACTER)
        relation = self.service.record_relation(
            "p1", _CHARACTER, "cand:b", "cand:a",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge", group_id=group.group_id,
        )
        # 같은 pair 반대 방향 재기록 — 정규화가 없으면 (b,a)는 (a,b)와 **다른
        # 인덱스 키**라 유일성 위반이 아니라 별도 행으로 쌓이고, 아래 len 단언이
        # 그 중복을 잡는다(2026-09-02 검증 H3 정정 — "유일성 위반"이 아니었다).
        self.service.record_relation(
            "p1", _CHARACTER, "cand:a", "cand:b",
            verdict=IdentityRelationVerdict.SAME,
            rationale="r", source="identity_judge", group_id=group.group_id,
        )
        self.service.create_group("p2", _CHARACTER)

        # B1 충실도: 실몽고에서 읽은 값이 기록한 값과 데이터클래스 동등(==)이어야
        # 한다 — naive 재라벨링 누락이면 tzinfo 불일치로, 클록 ms 절단 누락이면
        # µs 잘림으로 각각 깨진다. fake 셀은 직렬화가 없어 이 축을 못 잰다.
        self.assertEqual(self.service.get_group("p1", group.group_id), group)
        self.assertEqual(
            self.service.list_members("p1", group.group_id), (member,)
        )
        self.assertEqual(
            self.service.get_relation("p1", _CHARACTER, "cand:a", "cand:b"),
            relation,
        )
        self.assertEqual(
            self.service.get_relation("p1", _CHARACTER, "cand:b", "cand:a"),
            relation,
        )

        self.assertEqual(
            len(self.service.list_members("p1", group.group_id)), 1
        )
        self.assertEqual(len(self.service.list_relations("p1")), 1)
        self.assertEqual(len(self.service.list_relations("p2")), 0)

        self.service.purge_project(project_id="p1")

        self.assertEqual(self.service.list_groups("p1"), ())
        self.assertEqual(self.service.list_relations("p1"), ())
        self.assertEqual(len(self.service.list_groups("p2")), 1)


if __name__ == "__main__":
    unittest.main()
