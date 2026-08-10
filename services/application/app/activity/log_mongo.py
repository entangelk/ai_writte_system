"""`activity_events` Mongo 어댑터 (Phase 9 Slice 9.0)."""

from collections.abc import Sequence
from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING, MongoClient

from services.application.app.activity.log import ActivityEvent
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def _aware(value: datetime) -> datetime:
    """드라이버가 주는 naive 날짜에 UTC 를 다시 붙인다.

    pymongo 는 client 가 ``tz_aware`` 가 아니면 BSON 날짜를 **naive** 로 돌려주는데,
    fake collection 은 넣은 것을 그대로 주므로 **유닛은 green 인데 배포만 깨지는**
    형태가 된다(2026-07-27 세션 `expires_at` 실측). 조회 응답이 `at` 을 그대로
    직렬화하므로 여기서 되붙인다.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class MongoActivityLogRepository:
    def __init__(self, client: MongoClient, *, db_name: str = DEFAULT_DB_NAME) -> None:
        self._events = client[db_name]["activity_events"]
        # 조회는 항상 (project, 최신순) 하나뿐이다(A5=B).
        self._events.create_index(
            [("project_id", ASCENDING), ("at", DESCENDING)],
            name="activity_events_by_project_at",
        )
        # ★ A6=A — **TTL 인덱스를 두지 않는다.** 수명은 프로젝트가 정한다(I1): purge 가
        # 지우고 reconciler 가 고아를 쓸어 간다. 부피가 실제로 문제가 되면 그때
        # project 당 상한(밀어내기)이 다음 수단이며, 지금 N 일을 고를 근거가 없다.

    @classmethod
    def from_uri(cls, uri: str, *, db_name: str = DEFAULT_DB_NAME):
        return cls(MongoClient(uri), db_name=db_name)

    def insert(self, event: ActivityEvent) -> None:
        self._events.insert_one(_doc(event))

    def list_for_project(
        self, *, project_id: str, limit: int
    ) -> tuple[ActivityEvent, ...]:
        return tuple(
            _entry(doc)
            for doc in self._events.find({"project_id": project_id})
            .sort("at", DESCENDING)
            .limit(limit)
        )

    def list_for_projects(
        self, *, project_ids: Sequence[str], limit: int
    ) -> tuple[ActivityEvent, ...]:
        # 9.2 P1=ⓐ. 정렬·상한을 **서버가** 적용하는 것이 이 선택지의 값이다 —
        # 클라이언트 병합은 프로젝트별 상한 안에서만 정확하고 그 경계가 조용하다.
        return tuple(
            _entry(doc)
            for doc in self._events.find(
                {"project_id": {"$in": list(project_ids)}}
            )
            .sort("at", DESCENDING)
            .limit(limit)
        )

    def purge_project(self, *, project_id: str) -> None:
        self._events.delete_many({"project_id": project_id})


def _doc(event: ActivityEvent) -> dict:
    return {
        "_id": event.id,
        # ★ 이 이름이 계약이다 — reconciler 가 이 필드로 컬렉션을 발견한다(I1).
        "project_id": event.project_id,
        "actor_user_id": event.actor_user_id,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "at": event.at,
        "before": event.before,
        "after": event.after,
    }


def _entry(doc: dict) -> ActivityEvent:
    return ActivityEvent(
        id=doc["_id"],
        project_id=doc["project_id"],
        actor_user_id=doc["actor_user_id"],
        action=doc["action"],
        target_type=doc["target_type"],
        target_id=doc["target_id"],
        at=_aware(doc["at"]),
        before=doc.get("before"),
        after=doc.get("after"),
    )
