# Phase 2B.5 착수 결정 브리프 — memory→vector 재색인

**상태**: Resolved (오너 결정 완료 2026-07-07) — 증분 1(계약+fake, SoT v1.6.45)·증분 2(라이브 배선, SoT v1.6.46) 구현 완료. 실 Chroma 관통 live 실행만 sandbox 밖 후속.
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.44)
**선행**: 2B.1(store)·2B.2(prior 검색)·2B.3(scope key+compare)·2B.3.2(실 judge)·2B.4(versioned upsert) 완료.

---

## 현재 확정된 경계 (결정이 아니라 사실)

- **canonical memory는 현재 vector index에 전혀 색인되지 않는다.** 유일한 색인 record는 `IndexRecordKind.SOURCE_BLOCK`(draft 본문 블록)뿐이다 (`indexing/models.py`). memory→vector 색인은 임베딩 대상·collection·트리거·record 모델이 **전부 신규**다.
- **임베딩 스택은 존재한다.** `RemoteEmbeddingProvider`(BGE-m3-ko, `/embed`, 1024-dim) + `ChromaVectorIndexAdapter`(upsert/query/get/delete-by-where) + 미설정 시 `DeterministicFakeEmbeddingProvider` fallback. env `EMBEDDING_SERVICE_URL`/`CHROMA_HOST`로 wiring.
- **두 가지 기존 색인 트리거 패턴이 있다.**
  - (a) **동기 rebuild**: `rebuild_snapshot_source_block_index`가 blocks를 즉석 embed+`upsert_records`. 요청/스크립트(`scripts/phase3a_rebuild_source_block_index.py`)로 구동. 결정적·단순.
  - (b) **outbox→worker(async)**: archive 이벤트가 `IndexSyncOutboxEntry`로 enqueue → `scripts/index_sync_worker.py`가 claim/retry/backoff/sync-log로 drain → Chroma 반영. 내구성 있으나 무겁다(Phase 3B/4).
- **2B.4 apply 결과 4종**: create(v=1 새 canonical)·update(v+1, payload 교체)·add_evidence(v+1, payload 보존)·no_change(무쓰기)·conflict(skipped_review). update/add_evidence는 이전 entry를 `superseded`로 전이한다.
- **읽기(소비) 쪽 seam은 이미 있다.** `PriorMemoryBackend` Protocol(2B.2)이 "D2=A semantic seam"으로 설계돼 있고, 현재 구현은 `DeterministicPriorMemoryBackend`(name key 결정적 조회)다. event/open_question의 의미적 대조는 이 seam을 vector 검색 backend로 교체하는 **후속**으로 명시돼 있다.

---

## ⚠ 헤드라인 긴장 — 트리거 결정이 이 slice의 무게를 좌우한다 (CLAUDE.md §1)

memory 색인을 **동기(apply 내부)**로 붙이면 slice가 작다(record 모델 + embed + upsert + version 교체). 하지만 apply가 embedding/Chroma 장애에 직접 결합돼, 색인 실패가 memory 쓰기(이미 Mongo에 커밋된 canonical)와 원자적이지 않다 — "Mongo엔 새 version이 있는데 vector엔 없음"의 skew가 생긴다. **outbox→worker(async)**로 붙이면 이 skew를 재시도/로그로 흡수하지만 Phase 4 인프라를 memory record kind로 확장해야 해 slice가 커진다.

→ **D3에서 오너가 이 축을 결정해야** 나머지(record 모델·idempotency·backfill)의 형태가 정해진다. 임의 선택하지 않는다.

---

## 제안하는 slice 범위 (2B.5)

**포함**: apply가 만든 canonical memory version을 vector index에 반영하는 **쓰기(색인) 경로**.
- create → 새 memory vector record 색인.
- update/add_evidence → 새 version 색인 + 이전 version vector 제거(또는 교체)로 canonical-only 불변 유지.
- no_change/conflict → 색인 변화 없음.
- 기존 canonical(2B.1~2B.4로 이미 존재하는 것) 최초 backfill 경로.

**제외(후속)**: vector를 **읽는** 의미 검색(event/open_question의 D2 semantic seam 교체), ⑤ Writing canonical 포함, review queue 영속화. 즉 2B.5는 index를 **채우기만** 하고, 그것을 소비하는 semantic prior 검색은 다음 slice다.

---

## 결정 필요 항목

### D1. 임베딩 대상 — payload(Mapping)를 무슨 text로 투영하나
`MemoryEntry.payload`는 `memory_type`별로 구조가 다른 Mapping이다. 임베딩은 text 하나가 필요하다.
- **A**: memory_type별 결정적 text projection 함수(예: character = `name` + `description`/특성, event = 서술 text, open_question = 질문 text). 명시적·타입 안전, 단 필드 이름 계약 필요.
- **B**: payload 전체를 canonical JSON 직렬화해 embed. 단순·범용, 단 키/구조 노이즈가 벡터에 섞임.
- **C**: payload에 이미 있는 대표 text 필드 하나(예: `summary`)를 규약화.
- 추천: **A** — 타입별 의미 필드만 임베딩해야 event/character 의미 대조 품질이 나온다. projection 함수는 `derive_scope`(2B.3)와 같은 위치(`memory/scope.py` 인근)에 둔다.

### D2. collection 분리 vs 재사용
- **A**: 별도 collection(`memory_vectors`) + 신규 `IndexRecordKind.MEMORY`. metadata(project_id/memory_type/memory_id/version/status)로 필터. source_block과 쿼리 목적·수명주기가 완전히 달라 격리.
- **B**: source_blocks collection 재사용 + kind 필드로 구분.
- 추천: **A** — source_block은 draft 아카이빙에 묶인 수명, memory는 canonical 버전 수명. 섞으면 archive-where 삭제가 memory를 오염시킬 위험.

### D3. 재색인 트리거 — 동기(apply 내부) vs outbox/worker(async) [헤드라인]
- **A(동기)**: `MemoryApplyService.apply_proposals`가 versioned upsert 직후 embed+upsert(+이전 vector 삭제)를 인라인 수행. 색인 실패 처리 정책 필요(옵션: best-effort 로깅 후 성공 / 색인 실패=apply 실패).
- **B(async outbox/worker)**: apply가 memory index sync outbox entry를 enqueue, `index_sync_worker`(또는 신규 worker)가 drain. `IndexSyncEvent`에 `MEMORY_UPSERTED`류 추가, record kind 확장.
- **C(하이브리드)**: 동기로 붙이되 실패는 outbox로 fallback enqueue(재시도).
- 추천: **A(동기, best-effort)** 를 MVP로 제안하되 **오너 판단**. 근거: apply는 이미 결정적 오케스트레이션이고, 단일 사용자 MVP에서 memory 쓰기 QPS가 낮아 outbox 내구성 오버헤드가 과설계일 수 있다(CLAUDE.md §2). 단 skew를 감수하므로, 실패 시 backfill 스크립트(D7)로 복구 가능해야 한다. 오너가 skew 무관용이면 **B**.

### D4. version/supersede 반영 — canonical-only 유지
- update/add_evidence는 새 version을 색인하고 **이전 version vector를 제거**해야 index가 canonical만 담는다.
- **A**: vector record id = `memory_id`(version 무관). upsert가 같은 id를 덮어써 자연히 최신만 남음. 단 version 추적 메타는 metadata로.
- **B**: vector record id = `memory_id:version`. 이전 id를 명시 delete-by-where(`memory_id` + `superseded`) 후 새 id 색인.
- no_change/conflict = 색인 무변화(재확인).
- 추천: **A** — id를 memory_id로 고정하면 upsert 한 번으로 교체가 idempotent하게 성립(별도 delete 불필요). metadata.version으로 최신성 확인.

### D5. record 모델 + idempotency
- 신규 `MemoryIndexRecord`(id/kind/project_id/memory_id/memory_type/version/status/text/vector) 또는 기존 `SourceBlockIndexRecord`를 일반화.
- idempotency: 같은 canonical version을 두 번 색인해도 결과 동일(D4=A면 upsert가 자연히 보장).
- 추천: memory 전용 record dataclass 신설(source_block record는 draft 전용 필드가 많아 재사용이 오염). Chroma `record_to_chroma`/`record_from_chroma`의 memory 대응 추가.

### D6. 읽기 경로 범위 확인 (2B.5 = write-only?)
- 2B.5는 index를 **채우기만** 하고, event/open_question 의미 대조(`PriorMemoryBackend`의 vector 교체)는 후속으로 분리 — 맞나?
- 추천: **분리 확정**. 이유: 읽기까지 넣으면 compare(2B.3)의 결정적 name-key 경로와 vector semantic 경로 병합 설계가 얽혀 slice가 2배가 된다. write 경로를 먼저 잠그고, semantic read를 D2 seam 교체로 별도 slice.

### D7. 트리거 surface + 초기 backfill
- 이미 존재하는 canonical(2B.1~2B.4로 쌓인 것)을 최초 1회 색인하는 backfill 경로가 필요하다(2B.5 이전 memory는 index에 없음).
- **A**: `scripts/phase2b5_reindex_memory.py`(project별 canonical 전수 재색인) + apply 인라인(D3=A)로 증분.
- **B**: HTTP `POST /projects/{id}/memory/reindex`(운영 트리거).
- 추천: **A** — source_block의 `phase3a_rebuild_...` 스크립트 패턴과 일관. HTTP 운영 트리거는 필요 시 후속.

---

## 후속 (이 브리프 범위 밖)

- event/open_question 의미적 entity resolution — `PriorMemoryBackend`를 vector semantic 검색으로 교체(2B.5가 채운 index 소비). **2B.5 직후 유력 후보.**
- ⑤ Writing canonical 포함(Gate candidate 금지 정련).
- conflict/merge/split review queue 영속화.

## 누적 오너 확인 대상 (2B.1~2B.4에서 이월)

- event/open_question을 identity 대조 제외(항상 create)로 둔 것이 의미적 resolution 전까지 중복 canonical을 누적시키는데, 그게 브리프 의도와 맞는지. **2B.5 D1(임베딩 대상)이 이 중복들을 벡터 공간에서 구분 가능하게 만드는 선결 조건이므로 여기서 재부상한다.**
- 2B.2 F4 / 2B.3 D6 self-exclusion(같은 job 승격분 제외) 최종 유지 확인.

---

## 결정 요약 (추천값)

| # | 결정 | 추천 |
|---|------|------|
| D1 | 임베딩 대상 | A (memory_type별 text projection) |
| D2 | collection | A (별도 `memory_vectors` + kind=memory) |
| D3 | 트리거 | A (apply 동기 best-effort) — **오너 판단** |
| D4 | version 반영 | A (record id=memory_id, upsert 교체) |
| D5 | record/idempotency | memory 전용 record 신설 |
| D6 | 읽기 범위 | write-only (semantic read 분리) |
| D7 | backfill | A (재색인 스크립트) |

## Owner decisions — 2026-07-07

- **D3 = B (async outbox→worker).** apply가 memory index sync outbox entry를 enqueue하고, worker가 retry/backoff/sync-log로 drain해 memory collection에 반영한다. skew 무관용을 택했다 — Mongo canonical과 vector가 재시도로 수렴하는 내구성 경로. 대가: `IndexSyncEvent`/`IndexRecordKind`/record 모델/worker를 memory kind로 확장해야 해 slice가 커진다(오너 인지·수용).
- **D6 = write-only 분리.** 2B.5는 index를 채우는 쓰기 경로만. event/open_question 의미 대조를 위한 vector semantic 읽기(`PriorMemoryBackend` 교체)는 다음 slice. compare(2B.3)의 결정적 name-key 경로와 semantic 경로 병합을 얽지 않는다.
- **D1 = A (추천 잠금).** memory_type별 결정적 text projection. 정본 2A 스키마 필드에 정확히 대응한다(`analysis/schema.py`): character=`name`+`observation`, event=`event`, open_question=`question`. `derive_scope` 인근에 projection 함수.
- **D2 = A (추천 잠금).** 별도 collection(`memory_vectors`) + 신규 `IndexRecordKind.MEMORY`. source_block과 수명주기·archive-where 격리.
- **D4 = A + 교정 (구현 중 계약 교차검증, CLAUDE.md §1).** 원 추천("record id=memory_id, upsert가 최신으로 교체")은 2B.4 append-only 모델과 모순임을 구현 착수 시 발견: 각 version은 **새 id를 가진 별개 `MemoryEntry`**이고 이전 id는 `superseded`로 전이된다(`AppliedProposal.memory_id ≠ superseded_memory_id`). 단순 upsert면 이전 version 벡터가 잔류해 canonical-only가 깨진다. **교정 계약**: vector record id = `memory_id`(version별 distinct) 유지하되, worker가 memory를 로드해 — (a) `status`가 canonical이 아니면(늦게 도착한 stale enqueue) 그 id의 벡터를 삭제하고 skip(색인 순서 무관 self-healing), (b) canonical이면 새 version 벡터 upsert + `memory.supersedes`가 있으면 그 이전 id의 벡터 삭제. `MemoryStatus`(2B.4)와 `supersedes` 링크로 결정적·멱등. no_change/conflict=무색인(enqueue 없음). event/open_question은 항상 create(supersedes=None)라 누적 — 알려진 중복 caveat와 정합(semantic resolution 후속 slice에서 해소).
- **D5 = memory 전용 record 신설 (추천 잠금).** `MemoryIndexRecord`(id/kind/project_id/memory_id/memory_type/version/status/text/vector). source_block record 재사용 금지(draft 전용 필드 오염).
- **D7 = A (추천 잠금).** `scripts/phase2b5_reindex_memory.py` backfill(기존 canonical 전수 재색인) + apply enqueue 증분. HTTP 운영 트리거는 후속.

### D3=B가 요구하는 인프라 확장 (구현 노트)

- `IndexRecordKind`에 `MEMORY = "memory"` 추가.
- `IndexSyncEvent`에 memory upsert 이벤트(예: `MEMORY_UPSERTED`) 추가.
- `IndexSyncSource`는 memory Mongo collection/id/version을 담을 수 있어야 함(현 필드로 충분: `mongo_collection`/`mongo_id`/`mongo_version`).
- outbox entry의 `targets`에 memory→vector target. worker가 memory source를 만나면 payload를 embed(D1) → `memory_vectors`에 upsert(D4).
- apply(`MemoryApplyService`)가 create/update/add_evidence 반영 직후 outbox enqueue. no_change/conflict는 enqueue 없음.
- backfill 스크립트는 outbox를 우회해 canonical 전수를 직접 embed+upsert(또는 전수 enqueue 후 worker drain) — 둘 중 택1은 구현 시 결정(직접 쪽이 단순).

**live 후속 다듬 항목 (독립 검증 관찰 #3, 비차단)**: backfill(`phase2b5_reindex_memory.py`)은 `upsert_memory_records`를 단일 배치로 호출해 원자적(exit 0=성공/2=usage·config error)이라, source_block rebuild 스크립트의 partial-write exit 1 구분은 현재 없다. 실 Chroma/embedding 실패는 uncaught로 전파돼 traceback+non-zero exit이 된다. 실 관통 live에서 대량 재색인 실패 양상을 관찰한 뒤(배치 분할/부분 실패 리포팅 필요 여부) exit-code·오류 리포팅을 다듬는다 — 추측으로 미리 넣지 않는다(CLAUDE.md §2).

### 패턴 스윕 발견 — canonical 생성 경로가 apply만이 아니다 (오너 확인 → 해소됨)

증분 1은 enqueue를 `MemoryApplyService`(2B.4 apply: create/update/add_evidence)에만 붙였다. 그러나 canonical `MemoryEntry`를 만드는 경로는 셋이다:
1. **2B.4 apply** — enqueue seam 배선(증분 1).
2. **2B.1 수동 promote** (`POST .../analysis/candidates/{cid}/promote`) — canonical 생성, enqueue 없음(증분 1 시점).
3. **2B.1 auto-promote** (`POST .../analysis/jobs/{jid}/auto-promote`) — canonical 생성, enqueue 없음(증분 1 시점).

**오너 결정(2026-07-07): promote 경로도 enqueue 배선**(정기 backfill-only 아님). 승격된 memory가 곧바로 analysis compare 검색에 반영되도록 incremental correctness를 택했다.

**증분 2 해소 방식 — `MemoryService` 단일 choke point로 중앙화**: 세 경로에 각각 enqueue를 붙이면 중복/누락 위험이 있어, canonical mint가 실제로 일어나는 유일한 지점인 `MemoryService.promote_candidate`/`_versioned_upsert`(둘 다 `PromoteMemoryResult(idempotent_replay)` 반환)의 비-replay 성공 return에서 `_enqueue_reindex`를 호출한다. apply·수동 promote·auto-promote가 모두 이 두 메서드를 지나므로 한 번에 커버되고, 증분 1의 `MemoryApplyService.reindex_outbox` seam은 중복이 되어 제거했다. memory→indexing 순환을 피하려 `MemoryReindexOutbox` Protocol을 `memory/service.py`에 로컬 정의(구조적 타이핑). `create_app`은 `_default_memory_service(reindex_outbox=sync_outbox)`로 이를 켠다.

**수용된 경계 — commit-후-enqueue skew (독립 검증 관찰 #1, D3=B 본질)**: `put_memory`(canonical commit)가 먼저 성공하고 그 뒤 `_enqueue_reindex`가 outbox에 쓴다. 이 둘은 한 트랜잭션이 아니므로, 사이에서 프로세스가 죽거나 outbox 쓰기가 실패하면 "Mongo엔 canonical, vector엔 없음" skew가 남는다. **중요**: 같은 mint의 재시도는 `find_memory_by_candidate`가 이미 승격된 것을 찾아 **replay 분기로 빠져 enqueue를 재시도하지 않는다** → 이 skew는 결정적 재시도로 self-heal되지 않고 **정기 backfill(`scripts/phase2b5_reindex_memory.py`)이 유일한 수렴 수단**이다. 이는 D3=B(skew 무관용·outbox 내구성으로 수렴)를 택할 때의 알려진 표면이며 결함이 아니다 — 운영에서 memory backfill을 주기 실행(예: 일 1회 project 전수)하는 것을 권고한다. replay에서도 enqueue하도록 바꾸면 self-heal되지만 정상 replay마다 재색인이 돌아 낭비가 되므로 채택하지 않았다(비용/수렴 트레이드오프, 오너 재검토 대상으로 남김).
