# Work Log — 2026-07-07

## Goals

- HANDOFF와 2026-07-06 work log를 읽고 다음 작업(Phase 2B.5 — memory→vector 재색인)을 진행한다.
- 2B.5는 착수 결정 브리프가 필요한 slice(memory→vector 색인 자체가 미존재)이므로, 조사 → 브리프 작성 → 오너 결정 → 구현의 리듬을 따른다.

## Completed work

### Phase 2B.5 착수 결정 브리프 + 오너 결정

- 착수 조사로 **canonical memory가 vector index에 전혀 색인되지 않음**(현재 `IndexRecordKind.SOURCE_BLOCK`만)을 확인했다. 임베딩 스택(`RemoteEmbeddingProvider` BGE-m3-ko + `ChromaVectorIndexAdapter` upsert/delete + `DeterministicFakeEmbeddingProvider` fallback)과 두 색인 트리거 패턴(동기 rebuild / outbox→worker async)은 존재해 재사용 가능함을 파악했다.
- 브리프 `docs/plans/02b-5-memory-vector-reindex-decisions.md`(Resolved)를 작성해 D1~D7을 제시했다. **헤드라인 긴장(CLAUDE.md §1)**: apply는 이미 Mongo에 canonical을 커밋한 뒤 vector를 채우므로, 색인 트리거를 동기로 하면 slice는 작지만 색인 실패 시 "Mongo엔 새 version, vector엔 없음" skew가 생긴다는 것을 surface했다.
- **오너 결정**: **D3=B** async outbox→worker(skew 무관용, Phase 4 인프라를 memory record kind로 확장), **D6=write-only 분리**(semantic read는 후속). 나머지는 추천값 잠금 — D1=A(memory_type별 결정적 text projection), D2=A(별도 `memory_vectors` collection + `IndexRecordKind.MEMORY`), D4=A+교정, D5(memory 전용 record 신설), D7=A(backfill 스크립트).

### 구현 — 증분 1 (계약 + fake 인프라 + 회귀, SoT v1.6.45)

이 repo의 "4.1→4.2 리듬"에 맞춰 증분 1=계약+fake+회귀, 증분 2=실 Chroma memory collection+라이브 배선+live(sandbox 밖)로 나눴다.

- 변경 파일: `services/application/app/indexing/models.py`(literal), `indexing/memory_index.py`(신규), `indexing/service.py`(enqueue+worker dispatch), `analysis/apply.py`(enqueue seam), `main.py`(주석·seam 미배선 명시), `tests/test_memory_vector_index.py`(신규), `docs/plans/02b-5-...md`(신규), `docs/system-contract-sot.md`.
- **신설 literal**: `IndexRecordKind.MEMORY`, `IndexSyncEvent.MEMORY_UPSERTED`, `MemoryIndexRecord`(id/kind/project_id/memory_id/memory_type/version/status/text/vector).
- **projection(D1=A)**: `derive_memory_index_text(memory_type, payload)` — character=`f"{name}\n{observation}"`, event=`event`, open_question=`question`. payload는 타입의 required 필드만(= `analysis/schema.py`가 검증)이라 계약 필드만 읽는다.
- **벡터 adapter(D2/D5)**: `MemoryVectorIndexAdapter` Protocol(upsert/delete/list) + `InMemoryMemoryVectorIndexAdapter`(memory_id keyed). `MEMORY_VECTOR_COLLECTION="memory_vectors"`.
- **worker adapter(D4 교정)**: `MemoryIndexSyncAdapter.index_memory(entry)`가 memory 로드 → (a) `MemoryNotFound`면 그 id 벡터 삭제 후 return, (b) status가 canonical이 아니면 그 id 벡터 삭제 후 return(순서 무관 self-healing), (c) canonical이면 새 version 벡터 upsert + `memory.supersedes`가 있으면 그 이전 id 벡터 삭제. 멱등·결정적.
- **트리거(D3=B)**: `IndexSyncOutboxService.enqueue_memory_upserted`(source=`memory_entries`/memory_id/version), `IndexSyncWorker`에 optional `memory_adapter` + `MEMORY_UPSERTED` dispatch(미구성 시 RuntimeError), `MemoryApplyService`에 optional `reindex_outbox`(CREATED/VERSIONED만 enqueue, no_change/conflict 무enqueue). 기존 `_enqueue_archive_event`를 generic `_enqueue_event`로 개명(archive 2 + memory 1 공용).
- **라이브 배선은 증분 2**: 실 Chroma `memory_vectors` adapter가 아직 없어, 증분 1 `create_app`은 `reindex_outbox`를 apply에 미배선(배포 worker가 drain 못 하는 undrainable entry 미생성). enqueue seam은 unit test로 잠금 — 2B.3의 judge-None seam이 503으로 유예하던 리듬과 동일.

## Issues found

- **D4 원 추천과 2B.4 append-only 모델의 모순(구현 중 발견, CLAUDE.md §1)**: 브리프 D4 추천은 "record id=memory_id, upsert가 최신으로 교체"였으나, 2B.4는 각 version이 **새 id를 가진 별개 `MemoryEntry`**이고 이전 id는 `superseded`로 전이된다(`AppliedProposal.memory_id ≠ superseded_memory_id`). 단순 upsert면 이전 version 벡터가 index에 잔류해 canonical-only가 깨진다.
  - **해소**: 임의로 구현하지 않고 브리프 D4에 교정을 기록(id=memory_id 유지하되 worker가 status 확인 + `supersedes` 삭제로 canonical-only 보장). `MemoryStatus`/`supersedes`(2B.4 도입)로 순서 무관·멱등하게 성립.

## Decisions

- **증분 분할**: D3=B가 Phase 4 outbox/worker를 memory kind로 확장하는 큰 slice라, 증분 1(infra-free 계약+fake+회귀)과 증분 2(실 Chroma+라이브+live)로 분리했다. 이유: 실 Chroma memory collection adapter는 sandbox 밖 live 검증이 필요하고, 증분 1을 먼저 잠그면 계약·회귀가 독립적으로 검증·머지 가능하다.
- **create_app 미배선 유지(증분 1)**: apply→enqueue를 배포에 켜면 worker가 아직 drain 못 해 실패 로그만 쌓이므로, drain 측(실 adapter)이 준비되는 증분 2까지 미배선. 대신 enqueue/worker/adapter seam 전부 unit test로 잠갔다.

## User Decisions and Rationale

- 오너가 D3=**B(async outbox→worker)**를 택했다. skew(Mongo canonical과 vector 불일치)를 재시도/로그로 흡수하는 내구성을 우선하고, Phase 4 인프라를 memory record kind로 확장하는 더 큰 slice를 수용했다.
- 오너가 D6=**write-only 분리**를 택했다. 2B.5는 index를 채우는 쓰기 경로만 잠그고, event/open_question 의미 대조(vector semantic read = `PriorMemoryBackend` 교체)는 다음 slice로 분리해 compare(2B.3)의 결정적 name-key 경로와 얽히지 않게 한다.

## Verification

- `python3 -m py_compile` (변경 5파일 + 테스트) 통과.
- 신규 회귀: `python3 -m unittest tests.test_memory_vector_index` → **14 OK**(projection 3 + enqueue 5 + worker 6).
- **양방향 non-vacuity mutation 재실증(CLAUDE.md)**: (1) `supersedes` 삭제 무력화 시 `test_update_replaces_prior_version_vector` 재실패(canonical-only guard 유효). (2) status self-heal 무력화 시 `test_superseded_id_is_dropped_not_reindexed` 재실패(self-heal guard 유효) — 최초 stale 테스트가 self-heal을 고립하지 못하고 supersedes-delete로 우연히 커버되던 것을 발견해 adapter 직접 구동 테스트로 교체했다.
- 관련 묶음: `tests.test_memory_apply tests.test_analysis_apply_api tests.test_index_sync_worker_script tests.test_indexing_phase3a tests.test_chroma_adapter` → 81 OK(skip 1). enqueue/worker 확장 회귀 없음 확인.
- 전체: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **579 passed / 45 skipped**(기존 565 → +14). `git diff --check` 통과.
- (mongo 3개 error는 종전 localhost:27017 auth 환경 이슈, 내 변경 무관.)

## 검증 후속 보강 (2026-07-07, 독립 검증 조건부 합격 → 폐쇄)

독립 검증 기록 `docs/verifications/2026-07-07/phase_2b_5_memory_vector_reindex_increment_1.md`는 **조건부 합격**(차단 1건 + 비차단 관찰). 차단을 닫고 값싼 비차단 2건을 보강했다.

- **차단 폐쇄(boundary matrix 행 16)**: SoT v1.6.45가 명시한 "worker가 `MEMORY_UPSERTED`를 optional `memory_adapter`로 dispatch(**미구성 시 RuntimeError**)" 분기의 회귀가 없었다. `test_memory_upserted_without_adapter_records_backend_error` 추가 — adapter=None으로 `MEMORY_UPSERTED`를 drain하면 dispatch가 RuntimeError를 던지고 worker가 `IndexSyncLastError(BACKEND_ERROR)` + requeue로 기록함을 잠갔다. mutation 재실증: dispatch가 raise 대신 return하도록 무력화하면 재실패(entries_failed 0). 증분 1 배포면에선 도달 불가지만 SoT 명시 계약이라 잠근다.
- **비차단(행 13 delete seed 강화)**: `test_missing_memory_removes_stale_vector_without_crash`가 ghost id(벡터 없음)로 no-crash만 증명하던 것을, ghost id에 stale 벡터를 미리 seed해 not-found 경로가 **능동 삭제**함을 입증하도록 강화. mutation 재실증: not-found 분기의 delete를 제거하면 재실패.
- **비차단(브리프 D1 prose drift)**: 브리프 D1 Owner decision prose가 "character=name+**description**류"였으나 코드/SoT/2A 스키마는 모두 `observation`이다. 브리프를 정본 스키마 필드(`name`+`observation`, `event`, `question`)로 정정 — 코드는 종전대로 정합(코드 변경 없음).
- **판단 보류(행 17)**: `derive_memory_index_text`의 미지원 type `ValueError`는 enum 3종 고정이라 현재 도달 불가한 fail-fast 방어 코드다(CLAUDE.md §2). 검증도 non-blocking으로 뒀고, 4번째 type 추가 시 조용한 None 대신 즉시 실패하는 것이 안전해 유지한다(회귀 미추가).
- 재검증: `python3 -m unittest tests.test_memory_vector_index` → **15 OK**. 신규/강화 guard 2개 mutation 각각 재실패 확인(복원). `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **580 passed / 45 skipped**. `git diff --check` 통과. 회귀 14→15.

## Phase 2B.5 증분 2 — 라이브 배선 (2026-07-07, SoT v1.6.46)

증분 1 커밋(`67b5362`) 후 오너가 "main 직접 커밋(브랜치 불필요) + 다음작업" 지시. 증분 2 착수 전 브리프가 오너 확인으로 이월한 결정을 받았다.

### 오너 결정 + 설계

- **오너 결정**: canonical 생성 3경로(2B.4 apply·2B.1 수동 promote·auto-promote)가 **모두 재색인 enqueue**(정기 backfill-only 아님). 승격 memory 즉시 검색 반영(incremental correctness).
- **설계 — `MemoryService` 단일 choke point 중앙화**: 세 경로에 각각 붙이면 중복/누락 위험 → canonical mint의 유일 지점인 `promote_candidate`/`_versioned_upsert`(둘 다 `PromoteMemoryResult(idempotent_replay)` 반환)의 비-replay 성공 return에서 `_enqueue_reindex` 호출. apply·수동 promote·auto-promote가 모두 이 두 메서드를 지나 한 번에 커버. **증분 1의 `MemoryApplyService.reindex_outbox` seam은 중복이 되어 제거**(apply는 promote/versioned를 호출하므로 자동 커버). memory→indexing 순환 회피 위해 `MemoryReindexOutbox` Protocol을 `memory/service.py`에 로컬 정의.

### 구현

- 변경/신규 파일: `memory/service.py`(reindex_outbox param·`MemoryReindexOutbox` Protocol·`_enqueue_reindex`·두 mint 사이트 enqueue), `analysis/apply.py`(증분 1 seam 제거), `indexing/chroma.py`(`ChromaMemoryVectorIndexAdapter`+memory record 직렬화), `main.py`(`_default_memory_service(reindex_outbox=)`·create_app outbox→memory 순서), `scripts/index_sync_worker.py`(`_build_memory_adapter`·summary `memory_backend`), `scripts/phase2b5_reindex_memory.py`(신규 backfill), `scripts/phase2b5_memory_reindex_live_smoke.py`(신규 live), 테스트 `test_chroma_memory_adapter.py`(신규)·`test_phase2b5_reindex_memory_script.py`(신규)·`test_memory_vector_index.py`(promote-path +4)·`test_analysis_apply_api.py`(HTTP enqueue wiring +1)·`test_index_sync_worker_script.py`(memory adapter 분기 +2).
- **실 Chroma adapter**: `ChromaMemoryVectorIndexAdapter`가 `MemoryVectorIndexAdapter` seam(upsert/delete/list)을 실 collection에 구현. delete는 `{$and:[project_id, memory_id]}` where(project-scoped, cross-project id 충돌 방지). record↔chroma metadata round-trip. collection `memory_vectors`(env `CHROMA_MEMORY_COLLECTION`), source_block과 분리.
- **create_app 배선**: outbox를 memory보다 먼저 만들고 `_default_memory_service(reindex_outbox=sync_outbox)`로 3경로 enqueue를 켠다. 주입 memory_service(테스트)는 자체 wiring 유지.
- **worker**: `_build_memory_adapter`가 Mongo MemoryService + embedding(`EMBEDDING_SERVICE_URL` 실/fake) + Chroma/fake memory collection으로 `MemoryIndexSyncAdapter`를 만들어 `MEMORY_UPSERTED`를 drain. summary에 `memory_backend`.
- **backfill**: `phase2b5_reindex_memory.py`가 project canonical 전수를 직접 embed+upsert(superseded 제외, outbox 우회 D7). 기존(2B.5 이전) canonical catch-up.
- **live smoke**: `phase2b5_memory_reindex_live_smoke.py`가 promote→outbox→worker→실 Chroma record 확인(sandbox 밖 실행, 테스트 project·Chroma record 정리).

### 회귀 +20 + 검증

- `test_chroma_memory_adapter.py`(11): record round-trip·chroma id=memory_id·upsert/list·empty short-circuit·project scope·delete target·delete project-scoped(over-strict).
- `test_memory_vector_index.py` PromotePathEnqueueTest(4): 수동 promote enqueue·promote replay 미중복(over-strict)·auto-promote threshold 발화 enqueue·threshold 미만 미enqueue(over-strict).
- `test_analysis_apply_api.py`(+1): create_app 기본 배선에서 apply HTTP→MEMORY_UPSERTED enqueue(end-to-end).
- `test_index_sync_worker_script.py`(+2): `_build_memory_adapter` fake/chroma backend 분기(from_uri patch).
- `test_phase2b5_reindex_memory_script.py`(4): canonical-only 필터·project 격리·main 배관·usage error.
- **mutation 재실증**: `MemoryService._enqueue_reindex` 본문 무력화 시 promote-path 4개 + apply wiring 재실패(choke-point load-bearing 확인).
- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **598 passed / 45 skipped**(증분 1 580 → +18). `git diff --check` 통과. 스크립트 `--help`/usage-error 경로 확인(실 live는 sandbox 밖).

## User Decisions and Rationale (증분 2)

- 오너가 **promote 경로도 재색인 enqueue**를 택했다(정기 backfill-only 아님). 근거: 수동 승격한 canonical memory가 다음 backfill을 기다리지 않고 즉시 analysis compare의 prior 검색에 반영돼야 한다(incremental correctness). 이 결정이 enqueue를 `MemoryService` choke point로 중앙화하는 설계로 이어졌고, 증분 1의 apply-seam을 흡수했다.

## Next steps

- **Phase 2B.5 live 실행(sandbox 밖, 코드 완료)**: `scripts/phase2b5_memory_reindex_live_smoke.py`를 배포 stack(실 Mongo+Chroma+embedding)에서 실행해 promote→outbox→worker→실제 `memory_vectors` Chroma record를 관통 확인. 필요 시 backfill `scripts/phase2b5_reindex_memory.py`로 기존 canonical 전수 재색인.
- **후속 slice**: event/open_question 의미적 resolution — `PriorMemoryBackend`를 vector semantic 검색으로 교체(2B.5가 채운 `memory_vectors` index 소비). ⑤ Writing canonical 포함, conflict/merge/split review queue 영속화.
- **곁가지(막힘 없음, sandbox 밖)**: 2B.3.2 compare judge live smoke, worker→real Chroma archive live smoke.
- **추적 부채(2026-07-06 이월)**: `ProviderError`→502 패턴이 `/context-search`·2A extraction adapter에 미적용(HANDOFF Next Tasks #8).
