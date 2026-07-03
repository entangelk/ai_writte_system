# Phase 3B Archive Outbox 첫 code slice 독립 검증

## Subject metadata

- 검증일: `2026-07-03`
- 요청자: 프로젝트 오너("클로드 작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? … Phase 3B archive outbox 첫 slice가 들어갔고 SoT를 v1.6.26으로 올렸습니다.")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상 slice: Phase 3B archive outbox 첫 code slice — `index_sync_outbox` domain model/service/in-memory+Mongo repository skeleton, Application archive endpoint wiring, 4개 회귀 신규 + 3개 API 회귀 보강, Mongo index setup 회귀 2개.
- 정합 스펙 기준(canonical contract scope):
  - `docs/plans/03-index-sync-outbox-decisions.md` §7 Schema lock, §8 첫 구현 slice 제안, §3 저장 단위, §5 retry/backoff, §1 event source 후속 고려
  - `docs/system-contract-sot.md` v1.6.26 changelog 항목 + v1.6.25 브리프 승인 항목 + §Phase 3 Phase 3B 단락
  - 교차 계약(브리프가 인용): `docs/contracts.md` §7.2(`IndexSyncRequest`, `targets` list), §7.3(`IndexSyncResult`, `targets` object + `success`), `docs/mongo_collections.md` §39(`index_sync_logs`, `targets` object + `success`)
- 검증 대상 작업 출처: working tree, uncommitted. `git status`로 `services/application/app/indexing/mongo_repository.py`·`tests/test_indexing_mongo_indexes.py`·`docs/daily_logs/2026-07-03/` untracked, 9개 파일 modified 확인.

## Scope

정합 스펙 스코프를 (1) 결정 브리프 §7/§8/§3/§5/§1, (2) SoT v1.6.26/v1.6.25 changelog 항목으로 좁혔다. 브리프가 canonical envelope 인용로 삼는 `contracts.md` §7.2/§7.3·`mongo_collections.md` §39는 직접 열독해 브리프 인용의 정확성과 계약 자체 일관성을 교차 점검했다. 브리프 §승인 전 보류(Mongo live round-trip, worker loop, retry 실행, real adapter, stale-hit wiring, `analysis_completed` wiring)는 본 slice 범위가 아니므로 구현 여부만 확인하고 회귀 부재를 결함으로 삼지 않았다.

검증 surface:

1. 정합 계약(브리프 §7/§8 + SoT v1.6.26) 내부 정합성 + literal 일치 + 상위 계약(§7.2/§7.3/§39) 인용 정확성
2. 구현 코드: `indexing/models.py`(신규 모델/enum), `indexing/service.py`(`IndexSyncOutboxService`, `InMemoryIndexSyncRepository`, dedup), `indexing/mongo_repository.py`(index setup + 직렬화), `main.py`(archive endpoint wiring)
3. 회귀 테스트: `tests/test_indexing_phase3a.py` 신규 4개, `tests/test_application_api.py` 보강 3개, `tests/test_indexing_mongo_indexes.py` 신규 2개 — 각 분기 ↔ clause 추적 + 양방향 가드(under/over-strict) 점검
4. 작업자 주장 카운트(focused 17 / application 50 / broader 79 / full 394·37skip) 독립 재현 + py_compile + `git diff --check`
5. 패턴 스윕: enqueue 호출자 단일성, `analysis_completed` code enum 부재, Mongo 직렬화 커버리지, collection registry 등록 여부

## Methodology

정합 스펙을 먼저 끝까지 읽어 boundary matrix(should-fire / should-NOT-fire / literal 전부)를 구성한 뒤, 코드·테스트에 역추적. 작업자 주장·work_log를 복사하지 않고 명령을 재실행·재도출. envelope 카운트는 직접 재실행으로 입증.

실행한 명령:

- `git status`, `git diff --stat`, `git status --porcelain | grep '^??'`(untracked 확인)
- `Read`로 결정 브리프·work_log·`models.py`·`service.py`·`mongo_repository.py`·`test_indexing_mongo_indexes.py` 전량 열독; `git diff`로 `main.py`·`test_indexing_phase3a.py`·`test_application_api.py`·SoT·`03-indexing.md`·HANDOFF·CHANGELOG 변경분 확보
- `Read`로 `contracts.md:1050-1104`(§7.2/§7.3), `mongo_collections.md:2086-2140`(§39) 열독 — 상위 계약 인용 정확성 교차 점검
- `python3 -m py_compile services/application/app/indexing/{models,service,mongo_repository}.py services/application/app/main.py tests/test_{indexing_phase3a,indexing_mongo_indexes,application_api}.py`
- `python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes -v`(17)
- `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script tests.test_phase3a_deployed_rebuild_smoke_script tests.test_indexing_phase3a tests.test_application_api`(79)
- `python3 -m unittest discover tests`(394 / skipped=37)
- `git diff --check`
- 패턴 스윕 grep: `put_outbox_entry|get_outbox_entry_by_dedup_key|_to_outbox_entry|_outbox_doc|_to_target_state|_to_source|_to_last_error|next_sync_request_id` / `IndexSyncLog` / `analysis_completed|ANALYSIS_COMPLETED` / `enqueue_project_archived|enqueue_draft_archived|archive_project\(|archive_draft\(` / `index_sync_outbox` in `mongo_collections.md` / `target` in `models.py`

## Findings

### 1. 정합 계약 내부 정합성 + literal + 상위 계약 인용

- 브리프 §7.2가 "`contracts.md` §7.2는 request를 `targets` list로, §7.3/§39는 result/log를 `targets` object로 표현한다"고 인용 → 직독 확인. §7.2(`contracts.md:1064`) `"targets": ["chroma", "elasticsearch"]`(list), §7.3(`:1077`) `"targets": {"chroma": {...}, ...}`(object), §39(`mongo_collections.md:2112`) 동일 object shape + `:2122` `"status": "success"`. 인용 정확, 계약 내부 충돌 없음.
- 완료 literal 재사용: 브리프 §7.1/§5가 "완료 literal은 기존 §7.3/§39의 `success`를 재사용, lifecycle은 `pending|running|success|failed`" → `models.py:26-30` `IndexSyncStatus`가 정확히 `PENDING/RUNNING/SUCCESS/FAILED = pending/running/success/failed`. ✅
- event literal: §8.1이 "`project_archived`, `draft_archived` / 후보 `analysis_completed`(아직 code enum에는 열지 않음)" → `models.py:21-23` `IndexSyncEvent`는 2개만. grep으로 `analysis_completed|ANALYSIS_COMPLETED`가 `services/`·`tests/`에 부재 확인. ✅
- error type 분리: §5/§8.1 "`backend_error`, `not_found`, 둘 다 `max_attempts=3`" → `models.py:33-35` `IndexSyncErrorType = backend_error/not_found`, `service.py:30` `INDEX_SYNC_MAX_ATTEMPTS = 3`. ✅
- target envelope: §8.1/§7.2 "canonical `targets` shape, 첫 target은 `chroma`에 `backend="in_memory_fake"`" → `service.py:178-183`가 `targets={CHROMA_TARGET: IndexSyncTargetState(status=PENDING, backend=IN_MEMORY_FAKE)}`로 생성. ✅
- reduced `target="vector"` 비영속: §8.4 "Phase 3A reduced `target="vector"`를 persistent outbox에 저장하지 않는다" → `models.py:74-85` `IndexSyncOutboxEntry`는 `targets: dict`(line 80)만 갖고 단수 `target` field가 없다. `models.py:51`의 `target: IndexSyncTarget`은 Phase 3A `IndexSyncRequest`(line 47-51) 소속이어서 구조적으로 outbox entry는 reduced literal을 담을 수 없다. ✅(구조적 보장)
- source shape: §8.1 "source: `mongo_collection`, `mongo_id`, optional `mongo_version`" → `models.py:54-58` 정확히 일치. ✅

### 2. 구현 코드 — service / repository / wiring

- `IndexSyncOutboxService.enqueue_project_archived`(`service.py:134-144`): source=`(PROJECTS_COLLECTION="projects", mongo_id=project_id)`. `enqueue_draft_archived`(`:146-156`): source=`(DRAFTS_COLLECTION="drafts", mongo_id=draft_id)`. §7.4 "`project_archived` source는 `projects/{project_id}`, `draft_archived`는 `drafts/{draft_id}`"와 정합(component 분해 형태). ✅
- `_enqueue_archive_event`(`:158-191`): `get_outbox_entry_by_dedup_key` 선행 → 존재하면 기존 entry 반환(없으면 신규 pending entry 생성). 생성 entry의 retry metadata는 `attempt_count=0, max_attempts=3, next_attempt_at=None, last_error=None, status=PENDING, user_id=None`. §8.1/§5와 정합. ✅
- dedup key(`:376-379`): `(project_id, event, source.mongo_collection, source.mongo_id)`. §7.4와 정확히 일치. `mongo_version`은 key에서 제외 → §7.4 "versioned content sync 추가 시 `mongo_version`/`content_hash` 포함 여부는 별도 결정"과 정합(archive event는 version 의미 없음). ✅
- `InMemoryIndexSyncRepository.put_outbox_entry`(`:80-86`): dedup key 중복 시 silent return. service도 선행 get으로 guard → 이중 idempotency 보장. ✅
- `main.py` wiring(`git diff`): `_default_index_sync_outbox_service()`(`CORE_SOT_MONGO_URI` 부재 시 InMemory, 존재 시 `MongoIndexSyncRepository.from_uri`), `create_app(index_sync_outbox=...)` optional 주입. `DELETE /projects/{id}`(`:381-385`)는 `core_sot.archive_project()` 성공 후 `enqueue_project_archived`, `DELETE /projects/{id}/drafts/{draft_id}`(`:390-395`)는 `archive_draft()` 성공 후 `enqueue_draft_archived`. §8.2 "archive 성공 후 outbox entry 생성" 순서·표면 정합. enqueue 호출자는 grep으로 `main.py`만 확인(단일 경로). ✅
- `MongoIndexSyncRepository`(`mongo_repository.py`): unique dedup index `(project_id, event, source.mongo_collection, source.mongo_id)`(`:48-57`), `index_sync_outbox_by_status_next_attempt`(`:58-65`), `index_sync_logs_by_request_attempt`/`index_sync_logs_by_project_request`(`:66-73`). `put_outbox_entry`(`:99-103`)는 `DuplicateKeyError` catch로 Mongo 수준 idempotency. `OperationFailure` → `MongoIndexSyncRepositorySetupError`. ✅ index setup 부분은 회귀로 잠김(아래 §4).

### 3. 회귀 테스트 ↔ clause 추적 + 양방향 가드

boundary matrix 추적 결과(should-fire / should-NOT-fire / literal):

| clause | 분기 유형 | 회귀 테스트 | 가드 방향 | 결과 |
|---|---|---|---|---|
| project_archived → pending entry, source=(projects,id) | should-fire | `test_project_archive_creates_pending_chroma_outbox_entry` + API `test_archive_project_via_delete_blocks_writes_kept_reads` | 정상 케이스 | ✅ |
| draft_archived → pending entry, source=(drafts,id) | should-fire | `test_draft_archive_creates_distinct_dedup_source` + API `test_archive_draft_via_delete` | 정상 케이스 | ✅ |
| entry 전 필드(user_id/status/attempt_count/max_attempts/next_attempt_at/last_error/targets) | literal | `test_project_archive_creates_pending_chroma_outbox_entry` | literal pin | ✅ |
| targets={chroma:{pending, in_memory_fake}} / reduced vector 비영속 | should-fire + should-NOT-fire | 동상(`set(entry.targets)=={chroma}` + backend/status) | canonical shape pin | ✅(구조 보강) |
| 같은 key 재archive → entry 1개 | should-NOT-fire(중복) | `test_repeated_archive_replays_same_outbox_entry`(len==1, first==second) + API `test_archive_is_idempotent` | under-strict(dedup 제거 시 len>1로 재실패) | ✅ |
| 다른 event(project/draft) 동일 project → 2개 | over-strict(과잉 dedup 방지) | API `test_archive_is_idempotent`(len==2, events=={draft,project}) | over-strict(잘못 collapse 시 1개로 실패) | ✅ |
| error_type backend_error≠not_found / max_attempts=3 | literal | `test_error_types_are_distinct_and_share_three_attempt_limit` | literal pin | ✅ |
| archive 후 read 보존 | should-fire | API `test_archive_project_via_delete_blocks_writes_kept_reads` / `test_archive_draft_via_delete`(GET archived==True) | 정상 케이스 | ✅ |
| Mongo index 4종 + setup error | should-fire | `test_ensure_indexes_creates_required_outbox_and_log_indexes` + `test_conflicting_index_failure_is_stable_setup_error` | 정상 + 실패 | ✅ |

- 회귀 테스트가 public surface(service method 반환 entry, API archive 응답 + 주입된 repo 상태)를 검사하고, 내부 헬퍼가 아닌 caller가 의존하는 표면을 pin한다. ✅
- idempotency의 양방향 가드가 service 단위 테스트(under-strict: 동일 key)와 API 테스트(over-strict: 상이 event 비-collapse)로 나뉘어 상호 보완. ✅

### 4. 작업자 주장 카운트 재현 + hygiene

- `py_compile`(7 파일) → OK.
- focused `test_indexing_phase3a test_indexing_mongo_indexes -v` → 17 ok(재현).
- broader 4-module → 79 ok(재현).
- `python3 -m unittest discover tests` → `Ran 394 tests … OK (skipped=37)`(재현).
- `git diff --check` → clean.

## Issues / Risks

> 본 slice의 §8 contract 대상으로는 결함이 아닌 항목들이다. 명시적 future-defer(브리프 §승인 전 보류 + 오너가 다음 slice로 명시한 Mongo live round-trip), 또는 문서 완전성/향후 slice 경계 정제에 해당한다. 단, owner가 인지해야 할 비블로킹 리스크로 명시한다.

1. **[Risk — 본 slice 범위 밖이나, shipping된 코드에 커버리지 없음] Mongo round-trip 직렬화가 무테스트.** `MongoIndexSyncRepository.put_outbox_entry` / `get_outbox_entry_by_dedup_key`와 직렬화 헬퍼 `_outbox_doc` / `_to_outbox_entry` / `_to_source` / `_to_target_state` / `_to_last_error`(`mongo_repository.py:99-196`)가 완전 구현돼 있고, `CORE_SOT_MONGO_URI` 설정 시 `main.py`가 이 repository를 archive endpoint의 service에 연결하므로 **production-reachable**이다. 그러나 `mongo_repository.py`에 대한 유일한 테스트는 `ensure_indexes`(fake collection)이며, insert→find_one→재구성 round-trip이나 직렬화 헬퍼를 직접 검사하는 테스트가 단 하나도 없다(grep으로 `tests/`에서 해당 심볼 참조 부재 확인). `_outbox_doc`에서 field 누락이나 `_to_target_state` 오타가 나도 suite가 잡지 못한다. 오너가 명시한 다음 slice(Mongo live round-trip smoke)가 live 경로를 다루지만, **live Mongo 의존 없이도 잠글 수 있는 fake-collection round-trip 단위 테스트를 추가**해 직렬화를 독립적으로 pin할 것을 권장한다.

2. **[Doc-completeness] `index_sync_outbox` collection이 `mongo_collections.md` 정본 레지스트리에 없다.** `docs/mongo_collections.md`는 `index_sync_logs`(§39)만 문서화하며, 새 영속 collection `index_sync_outbox`(document schema + 4 index를 코드가 생성)에 대한 §N 항목이 없다(grep `index_sync_outbox` in `mongo_collections.md` → 부재). schema는 현재 code + 브리프 §7/§8 + SoT v1.6.26 항목에만 존재한다. "code-enforced collection not in registry" 원칙상 collection 레지스트리 갱신(§N 추가 또는 명시적 cross-ref)이 필요하다.

3. **[Boundary — worker slice 정제 필요] dedup이 entry status를 무시한다.** `get_outbox_entry_by_dedup_key`는 status(pending/running/success/failed)에 무관하게 기존 entry를 반환한다. §3은 재archive 시 "active request가 하나만 남아야 한다"고 한다. 본 slice는 worker가 없어 entry가 항상 pending → 재archive가 단일 pending entry를 올바르게 반환한다. 그러나 worker가 entry를 terminal(success/failed)로 옮길 수 있게 되면, terminal 이후 재archive가 신규 active request를 만들지 않고 terminal entry를 그대로 반환하게 된다. dedup-by-key-without-status-filter를 worker slice에서 정제해야 한다. 현재 결함 아님.

4. **[Boundary — hardening 권장] `analysis_completed` not-in-enum에 명시적 회귀가 없다.** 해당 should-NOT-fire 경계는 StrEnum이 정확히 2 member를 가져 구조적으로 만족되며, grep으로 `analysis_completed`/`ANALYSIS_COMPLETED`가 `services/`·`tests/`에 부재임을 확인했다. 다만 명시적 pin 테스트(예: `assertNotIn("analysis_completed", [e.value for e in IndexSyncEvent])`)가 없다. 1-line 테스트로 조기 추가를 막을 수 있다. 저위험.

5. **[Doc nit] work_log의 SoT 버전 기록이 불완전.** `work_log.md:19`은 브리프 승인 단계의 "v1.6.25로 올렸다"만 기록하고, code slice 단계의 v1.6.26 갱신을 code slice 섹션에 적지 않았다. SoT 자체는 header(`v1.6.26`) + version log(v1.6.24→v1.6.25→v1.6.26)에서 정확하다. 표기 일관성만의 문제.

## Verdict

**합격(PASS)** — 결정 브리프 §8 / SoT v1.6.26 contract 대상 본 slice.

load-bearing 사유:
- §8 in-scope 분기 전부(archive→pending outbox, idempotency 양방향, dedup key, canonical targets, error-type 분리, max_attempts=3, archive read 보존, Mongo index setup)가 구현됐고, 각 분기가 명명된 회귀 테스트에 추적되며, 적용 가능한 곳에 under-strict + over-strict 가드가 둘 다 있다.
- literal(event/status/error_type/backend/max_attempts/dedup key/targets shape)이 spec과 변경 없이 일치.
- 상위 계약 인용(§7.2 list / §7.3·§39 object + `success` literal)이 정확하고, 계약 자체 일관성에 충돌이 없다.
- 작업자 주장 카운트가 독립 재현됨: focused 17 / broader 79 / full 394·37skip; `py_compile` OK; `git diff --check` clean.

위 Issues/Risks는 전부 (a) contract가 명시적으로 future-defer한 항목(Mongo live round-trip, worker), (b) 문서 완전성(collection registry, work_log 버전 표기), 또는 (c) 향후 slice 경계 정제(dedup-status)로, 본 slice 구현 결함이 아니다. 단, 항목 1·2는 owner의 다음 slice 전에 인지해야 할 실질 리스크이므로 별도 단락으로 명시했다(비블로킹 권고로 은폐하지 않음).

## Outstanding items

- 본 slice는 working tree에 uncommitted(`git status`: 3 untracked + 9 modified). commit/publish 여부는 owner 결정 대기.
- 오너가 명시한 다음 slice: `index_sync_outbox` Mongo live round-trip smoke. 본 검증 권고: live smoke와 함께 항목 1의 fake-collection round-trip 단위 테스트로 직렬화를 선(先)pin.
- 항목 2(`mongo_collections.md` §N `index_sync_outbox` 등록), 항목 3(worker slice의 dedup-status 정제), 항목 4(`analysis_completed` pin 테스트), 항목 5(work_log 버전 표기)는 후속 정리 후보.

## Reproduction

```bash
# 정합 스펙 + 코드 + 테스트 일관성
git status
git diff --stat
git diff services/application/app/main.py docs/system-contract-sot.md docs/plans/03-indexing.md HANDOFF.md CHANGELOG.md

# compile
python3 -m py_compile \
  services/application/app/indexing/models.py \
  services/application/app/indexing/service.py \
  services/application/app/indexing/mongo_repository.py \
  services/application/app/main.py \
  tests/test_indexing_phase3a.py \
  tests/test_indexing_mongo_indexes.py \
  tests/test_application_api.py

# 회귀
python3 -m unittest tests.test_indexing_phase3a tests.test_indexing_mongo_indexes -v   # 17
python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script \
  tests.test_phase3a_deployed_rebuild_smoke_script tests.test_indexing_phase3a \
  tests.test_application_api                                                          # 79
python3 -m unittest discover tests                                                     # 394 / skipped=37
git diff --check

# 패턴 스윹 / 커버리지 갭 확인
rg -n "put_outbox_entry|get_outbox_entry_by_dedup_key|_to_outbox_entry|_outbox_doc|_to_target_state|_to_source|_to_last_error" tests/   # → 부재(Mongo 직렬화 무테스트)
rg -n "analysis_completed|ANALYSIS_COMPLETED" services/ tests/                         # → 부재(enum 미개방 확인)
rg -n "index_sync_outbox" docs/mongo_collections.md                                     # → 부재(collection registry 갭)
rg -n "target" services/application/app/indexing/models.py                             # → line 51(IndexSyncRequest), 80/96(targets dict)
```
