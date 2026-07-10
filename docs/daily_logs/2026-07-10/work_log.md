# Work Log — 2026-07-10

## Goals

- HANDOFF와 2026-07-09 work log를 읽고 다음 작업을 진행한다.
- 오너 지시: **튜닝(b-4)은 최후순위로 미루고, 오너 결정 브리프 없이 처리 가능한 작은 작업부터** 진행.
- 반복 추적되던 소부채 **`ConnectElasticsearchTest` skip guard**(b-5 후속)를 닫아 sandbox의 3 환경-의존 failed를 제거한다.

## Completed work

### `ConnectElasticsearchTest` skip guard (b-5 후속, 테스트 전용)

- **선택 근거**: HANDOFF Next Tasks #1의 큰 후보((b-4) 튜닝·(c)~(e)·Phase 6)는 전부 오너 선택 + 착수 결정 브리프가 선행이라 임의 착수 불가. 반면 이 skip guard는 HANDOFF:89·2026-07-09 work_log:267·277에서 반복 추적된 자족적 소부채이고 오너 결정 불필요 — 오너의 "작은 작업부터" 지시에 정확히 부합.
- **문제**: `tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest`(b-5 도입)는 배포 `connect_elasticsearch_memory_index` boot 경로를 검증하려고 `from elasticsearch import Elasticsearch`(구 217행)와 `mock.patch("elasticsearch.Elasticsearch", …)`(구 225행)로 실 `elasticsearch` 패키지를 요구한다. sandbox에 패키지가 없어 3개가 `ModuleNotFoundError`로 **hard-fail** → green bar가 "704 passed + 3 failed"로 오독됨. (같은 파일 docstring 5–7행은 "unit-tested with a fake client — no elasticsearch package"라 주장하지만 이 클래스만은 예외적으로 패키지에 의존 — docstring이 서술하는 대상은 `ElasticsearchAdapterTest`[fake client 주입]이고 `ConnectElasticsearchTest`는 별개 관심사라 docstring은 무변으로 둠.)
- **수정**(외과적, 테스트 전용):
  - `tests/test_context_search_memory_lexical_retrieval.py`: 상단에 `import importlib.util` 추가.
  - `ConnectElasticsearchTest`에 `@unittest.skipUnless(importlib.util.find_spec("elasticsearch") is not None, …)` 클래스 데코레이터 추가. 패키지가 있으면 종전대로 3개 실행, 없으면 skip.
- **다른 테스트 무영향**: 같은 파일의 `ElasticsearchAdapterTest`·`LexicalDrainTest` 등은 fake adapter/client 객체를 직접 주입해 `elasticsearch` 패키지에 의존하지 않는다. 프로덕션 모듈(`indexing/memory_lexical_index.py:303`·`candidate_lexical_index.py:254`)은 함수 내부 lazy import(`# lazy: optional dependency`)라 collection 시점에 실패하지 않는다 → guard가 필요한 곳은 이 클래스 하나뿐.

## Pattern sweep (CLAUDE.md §4)

- `mock.patch("elasticsearch…"` / `from elasticsearch import` repo-wide grep → tests/ 내 유일 발생이 이 파일 217·225행(둘 다 이제 guard된 `ConnectElasticsearchTest` 내부). 다른 테스트엔 동일 패턴 없음.
- 프로덕션 2곳은 lazy import라 무해. 패턴이 한 클래스에 격리 확인 → 추가 조치 불필요.

## Issues found

- 없음.

## Decisions

- **SoT 버전 bump 안 함**: 이 변경은 **테스트 인프라 전용**(skip guard) — 계약 literal·public interface·프로덕션 코드 무변, 동작 변화 0. v1.6.53처럼 프로덕션 `connect_` 기본값을 건드린 slice와 성격이 다르고, 오너가 선택한 slice도 아니라 버전 로그에 항목을 만들지 않는다. HANDOFF의 테스트 카운트(3 failed 제거)만 갱신.
- 3 failed → 3 skipped로 전환(45→48 skipped). "환경 의존 failed"라는 상시 각주 자체를 제거해 green bar 오독 가능성을 없앤다.

## Verification

- `python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py -q` → **13 passed / 3 skipped**(패키지 부재 시 guard 발동).
- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **704 passed / 48 skipped**(종전 704 passed / 45 skipped + 3 failed → failed 0). `git diff --check` clean.
- 이 sandbox엔 `elasticsearch` 미설치라 guard가 skip 경로로 검증됨. 패키지 있는 환경(b-5/b-6 작업 환경, "703 passed" 기록)에선 종전대로 3개 실행되어 회귀 잠금 유지.

## 검증 후속 보강 (오너 독립 감사 PASS → outstanding 2건 closure)

오너 독립 검증(`docs/verifications/2026-07-10/connect_elasticsearch_skip_guard.md`)이 **합격(PASS)** — 모든 카운트 독립 재현, under-strict guard 실증(guard 제거 시 정확히 3 hard-fail 재현). 검증자가 남긴 비차단 outstanding 2건을 오너 지시로 닫았다.

- **outstanding #1 — over-strict 실행 경로 실증**(종전 논리-only): 이 sandbox에 `elasticsearch>=8,<9`(requirements.txt 핀, 설치 8.19.3)를 scratchpad 격리 디렉토리에 `pip install --target`으로 설치하고 **PYTHONPATH 주입으로만** 노출(시스템 Python 무오염, 가역적). 패키지 present 시 guard가 skip하지 않고 3개 실행·전부 PASS(파일 단독 16 passed/0 skipped, 전체 스위트 **707 passed/45 skipped**) → over-strict 방향(`find_spec is not None`→실행) 실증, b-5 회귀 잠금이 패키지 있는 환경에서 유지됨을 확인. PYTHONPATH 미주입 시 `find_spec`=None·파일 단독 13/3으로 원상복구 확인(격리 무오염). under/over 양방향 실증 완료.
- **outstanding #2 — HANDOFF:103 stale 정정**: 오너 승인 하에 `HANDOFF.md:103` Project Structure 주석 `(Approved, v1.6.57)`→`(Approved, v1.6.58)` 1행 정정(8행과 정합). 선재 stale 독립 정정.

## 2차 작업 — HANDOFF Project Structure 정합 소청소 (문서 전용)

- **선택 근거**: 오너가 "튜닝 제외·브리프 불필요·자족적 소슬라이스" 3후보(b-2 candidate live smoke 드라이버 / (d) review queue 착수 브리프 / 문서 정합) 중 **문서 정합**을 선택. 100% sandbox 안 검증 가능하고 계약·프로덕션 코드 무변.
- **문제**: `HANDOFF.md` Project Structure의 `scripts/` 블록 2곳이 stale:
  1. `index_sync_worker.py` 주석이 `# 3B archive drain + 2B.5 memory reindex drain` — 실제로는 **b-2 candidate 색인 drain**(v1.6.54)과 **`--loop` compose 데몬 모드**(b-6 증분1 / v1.6.56)까지 하는데 미반영. (`scripts/index_sync_worker.py:146` `_build_candidate_adapter`, `:236` `--loop`, `:320` `run_loop`로 실증.)
  2. `phase2b5_reindex_candidate.py`(v1.6.58 신설, candidate vector+lexical backfill)가 목록에서 **완전 누락**. 디스크엔 존재.
- **수정**(외과적, 문서 1파일 2행):
  - `index_sync_worker.py` 주석 → `# 3B archive + 2B.5 memory reindex + b-2 candidate 색인 drain (--loop compose 서비스, b-6 증분1)`.
  - 마지막 줄에 `phase2b5_reindex_candidate.py(둘 다 vector+lexical backfill, v1.6.58)` 추가.
- **인접 gap(수정 안 함, §3 준수)**: `scripts/phase3a_rebuild_source_block_index.py`(CLI rebuild)는 `phase3a_*_smoke.py` glob에 안 잡혀 Project Structure에 표현이 없다. 다만 이는 최근 버전 작업과 무관한 **선재 누락**이고 오너가 승인한 스코프(위 2개 항목) 밖이라 이번엔 손대지 않고 기록만 남긴다 — 필요 시 별도 정합에서 처리.

### Verification (2차)

- `git diff --check` clean. 변경은 `HANDOFF.md` Project Structure 2행뿐(계약 literal·SoT 버전·프로덕션 코드 무변 → SoT bump 없음).
- 각 수정 항목을 primary source로 재확인: worker candidate drain/`--loop`은 `scripts/index_sync_worker.py`에서, backfill 스크립트 존재는 `ls scripts/`에서 실증.

## 3차 작업 — (d) conflict review queue 영속화 (SoT v1.6.59)

- **선택 근거**: 오너가 "c,d,e 중 작은 것" 지시. 조사 결과 **(d)가 최소·자족**: (c)는 embedding semantic 매칭+캘리브레이션(live 의존), (e)는 semantic dedup+Phase 6 결합이라 규모/상류 의존이 큼. (d)는 상류 의존 없는 순수 additive 영속화 — 현재 `conflict` proposal이 `apply.py`에서 `SKIPPED_REVIEW`로 버려지던 것을 durable store에 영속화.
- **오너 결정**(AskUserQuestion 2문): **D1=최소 영속화만**(status=`open` 단일, resolve/dismiss 전이는 Phase 6 forward-defense — candidate needs_review-only 동형)·**D2=GET list 엔드포인트 추가**. 브리프 `docs/plans/02b-4-review-queue-persistence-decisions.md`에 D1~D4(+D3 결정적 id 멱등·D4 action generic) 기록.
- **구현**:
  - 신규 `services/application/app/analysis/review_queue.py`: `ReviewQueueEntry`·`ReviewQueueStatus(OPEN)`·`ReviewQueueRepository` Protocol·`InMemoryReviewQueueRepository`·`ReviewQueueService`(enqueue/list_open)·`derive_review_queue_id`(`(project_id,job_id,candidate_id,action)` canonical-JSON SHA-256 — 2A `logical_key` 선례, apply replay 멱등 upsert).
  - 신규 `services/application/app/analysis/review_queue_mongo_repository.py`: `MongoReviewQueueRepository`(collection `review_queue`, deterministic `_id` upsert, project+status index).
  - `analysis/apply.py`: `MemoryApplyService`에 optional `review_queue` 주입. conflict 분기에서 candidate.job_id로 enqueue. **미주입 시 동작 불변**(하위호환) — 기존 conflict 테스트 무영향.
  - `main.py`: `_default_review_queue_service`(Mongo 구성 시 Mongo repo, 없으면 in-memory) + `create_app`에 `review_queue_service` 주입 param + apply_service 배선 + `GET /projects/{id}/analysis/review-queue`(open 조회, missing project 404) + `_review_queue_entry_payload`.
- **회귀 +13**(양방향 guard):
  - `tests/test_review_queue.py`(신규, 5): enqueue 필드·결정적 id·**멱등 upsert 미중복(under-strict)**·**서로 다른 candidate는 별개 entry(over-strict)**·project scope.
  - `tests/test_memory_apply.py`(+4): **conflict→enqueue(under-strict: enqueue 제거 시 재실패)**·**safe action(create/no_change) 미enqueue(over-strict)**·재적용 미중복·queue 미주입 하위호환.
  - `tests/test_analysis_apply_api.py`(+4): conflict apply→GET 관통·재적용 미중복·빈 큐 `[]`·missing project 404.
- **성격**: 새 public HTTP 엔드포인트 + store 계약 신설 → SoT v1.6.59 bump. 기존 계약 literal 무변경(2B.4 apply conflict posture를 "버림"→"영속화"로 확장).

### Verification (3차)

- `python3 -m pytest tests/test_review_queue.py tests/test_memory_apply.py tests/test_analysis_apply_api.py -q` → **36 passed**.
- 전체: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **717 passed / 48 skipped**(종전 704 + 13). `git diff --check` clean.
- `create_app()` 부팅 확인: `/projects/{project_id}/analysis/review-queue` 라우트 등록·`derive_review_queue_id` 결정성 실증.
- 문서: SoT v1.6.59 버전 로그·헤더, CHANGELOG, HANDOFF(Current Status·Active Decisions·Owner Decisions·Next Tasks·Verification·Project Structure) 갱신.
- **미검증(sandbox 밖)**: `MongoReviewQueueRepository` 실 Mongo round-trip(in-memory repo·mongo repo 대칭 구조로 작성, 실 upsert/index는 sandbox 밖 후속 — 프로젝트의 mongo repo 검증 관례와 동일).

## Next steps

- HANDOFF Next Tasks #1의 남은 slice는 **오너 선택 대기**((b-4) hybrid 튜닝[최후순위 지시]·(c) 별칭 semantic·(e) canonical↔candidate dedup·Phase 6). 각 후보는 착수 결정 브리프 선행.
- (d) 후속: resolve/dismiss/reconcile 전이·merge/split 산출·큐 기반 재조정 write는 Phase 6. `MongoReviewQueueRepository` 실 Mongo round-trip은 sandbox 밖.
- sandbox 밖 후속(코드 완료, 여기서 막힘)은 무변: 2B.6 threshold 캘리브레이션·2B.5/b-2/b-6 live 관통·ES-lexical/vector live backfill.
