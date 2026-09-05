"""``quota_replay_responses`` 어댑터 — 가짜 몽고 회귀 (S-1 검증 B2 폐쇄, 2026-09-05).

SoT v1.8.32 가 "인메모리+mongo" 저장을 등재했는데 몽고 쪽은 테스트가 0건이었다 —
TTL 인덱스 86400 이 리팩터링으로 사라져도 무엇도 안 물렸다. 같은 날 S-3 폐쇄가
``test_auth_signup_guard_mongo.py`` 로 세운 규범(신규 몽고 저장소는 가짜 컬렉션
테스트를 둔다)을 이 저장소도 지킨다.
"""

from __future__ import annotations

import unittest

from services.application.app.quota.replay import (
    DEFAULT_REPLAY_TTL_SECONDS,
    MongoReplayResponseRepository,
    replay_key,
)


class _Collection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: list[tuple] = []

    def create_index(self, keys, *, name=None, **kwargs):
        self.indexes.append((keys, name, kwargs))

    def find_one(self, query):
        return self.docs.get(query["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.docs.get(query["_id"])
        if doc is None:
            if not upsert:
                return
            doc = {"_id": query["_id"]}
            self.docs[query["_id"]] = doc
        doc.update(update["$set"])


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "quota_replay_responses"
        return self.collection


class _Client:
    def __init__(self, collection):
        self.database = _Database(collection)

    def __getitem__(self, _name):
        return self.database


def _repo(collection, *, ttl_seconds=DEFAULT_REPLAY_TTL_SECONDS):
    return MongoReplayResponseRepository(
        _Client(collection), ttl_seconds=ttl_seconds
    )


class MongoReplayResponseRepositoryTest(unittest.TestCase):
    def test_declares_the_ttl_index_at_the_registered_literal(self):
        """TTL literal 핀 — SoT v1.8.32·§43H 의 "24시간"이 여기서 온다.

        under-strict: ``create_index`` 를 없애거나 상수를 3600 으로 줄이면
        실패한다(검증 B1 의 몽고 면). over-strict: 창을 늘려도 literal 핀이
        실패한다. ``max(1, …)`` 바닥도 같이 잰다(0 설정이 no-replay 로 조용히
        풀리는 것은 1 초 짜리 창이지 0 이 아니다).
        """
        self.assertEqual(DEFAULT_REPLAY_TTL_SECONDS, 86400)
        for ttl_seconds, expected in [
            (DEFAULT_REPLAY_TTL_SECONDS, 86400), (3600, 3600), (0, 1),
        ]:
            with self.subTest(ttl_seconds=ttl_seconds):
                collection = _Collection()
                _repo(collection, ttl_seconds=ttl_seconds)
                self.assertEqual(
                    collection.indexes,
                    [("stored_at", None,
                      {"expireAfterSeconds": expected})],
                )

    def test_put_then_get_round_trips_the_payload_bytes(self):
        collection = _Collection()
        repo = _repo(collection)
        key = replay_key("u1", "writing_report", "rep-1")
        repo.put(key, b'{"candidate": true}')
        self.assertEqual(repo.get(key), b'{"candidate": true}')
        self.assertIsNone(repo.get(replay_key("u1", "writing_report", "nope")))

    def test_the_document_id_is_the_replay_key_axis(self):
        """축 literal — 원장 유니크 인덱스와 같은 세 축이 하나의 ``_id`` 로
        접힌다(회원·동작·키). 행 하나가 재생 하나다."""
        collection = _Collection()
        repo = _repo(collection)
        repo.put(replay_key("u1", "writing_report", "rep-1"), b"{}")
        repo.put(replay_key("u2", "writing_report", "rep-1"), b"{}")
        self.assertEqual(
            set(collection.docs),
            {"u1:writing_report:rep-1", "u2:writing_report:rep-1"},
        )

    def test_put_overwrites_the_stored_response_for_the_same_key(self):
        """확인 재실행의 저장 응답 덮어쓰기(§43H) — 재생은 **마지막** 응답이다.

        같은 키에 두 번 과금 성공이 일어나면(원본 + 확인 재실행) 재생은 나중
        응답을 준다. 첫 응답을 돌려주면 확인 재실행의 결과를 유실 보관한다.
        """
        collection = _Collection()
        repo = _repo(collection)
        key = replay_key("u1", "writing_report", "rep-1")
        repo.put(key, b"first")
        repo.put(key, b"second")
        self.assertEqual(repo.get(key), b"second")
        self.assertEqual(len(collection.docs), 1)


if __name__ == "__main__":
    unittest.main()
