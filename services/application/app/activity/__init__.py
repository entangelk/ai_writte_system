"""서비스 활동 로그 (Phase 9 Slice 9.0) — **누가 · 언제 · 무엇을 바꿨는가**.

오너 결정 A1~A8(2026-08-09, `plans/09-0-service-activity-log-decisions.md`).

- `actions.py` — mutating operation **40 전수 분류표**(`logged`/`excluded`).
- `log.py` — `ActivityEvent` + 저장소 Protocol + in-memory + 서비스(격리 경계).
- `log_mongo.py` — `activity_events` Mongo 어댑터.

**이 컬렉션은 프로젝트 자식이다**(부모 계획 §4 I1·I2): `project_id` 필드를 쓰고
purge 가 지우며 reconciler 가 고아를 쓸어 간다. 8.2c `project_name_history` 와
**정반대 방향이고 그것이 의도다** — 그쪽은 `_id` 를 project id 로 써서 reconciler 를
구조적으로 피한다. 여기서 그 흉내를 내면 삭제 계약(D8-6)이 무너진다.
"""
