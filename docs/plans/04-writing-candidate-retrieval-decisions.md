# ⑤ §5 B 후속 — `needs_review` candidate의 lexical/vector retrieval 착수 결정 브리프 (b-2)

상태: `Resolved` (2026-07-09 오너 결정)
관련: SoT v1.6.50(candidate Mongo-direct 포함), v1.6.51(canonical vector), v1.6.52(canonical ES lexical/hybrid), v1.6.53(compose ES 서비스)
선행 slice: `04-writing-candidate-context-decisions.md`(Resolved, D2=A Mongo-direct), `02b-5-memory-vector-reindex-decisions.md`(canonical 색인 파이프라인 선례)

## 오너 결정 (2026-07-09)

- **G0=A**: 2 증분(증분1 = candidate 색인 파이프라인, 증분2 = retriever + 배선).
- **G4=A**: 증분2에서 vector + lexical + hybrid(RRF)를 한 slice로(canonical end-state 미러).
- **G1=A / G2=A / G3=A / G5=A / G6=A**: 추천값 잠금(저장소 물리 분리 / `record_candidate` choke point enqueue / 권위 재유도 needs_review-only / `derive_memory_index_text` 재사용 / canonical env 스위치·worker composite·out-of-band).

## 배경

v1.6.50이 `needs_review` candidate를 Writing package에 micro·라벨로 포함하며 `CandidateMemoryRetriever` seam + `MongoDirectCandidateMemoryRetriever`를 세웠다. 그 D2는 canonical과 대칭으로 "retrieval 레이어와 권위 재유도(항상 analysis store 재검증)를 분리해 후속에서 vector/ES 교체 가능"으로 남겼다.

canonical은 그 후속을 실현했다: v1.6.51 vector(`VectorCanonicalMemoryRetriever`) → v1.6.52 lexical/hybrid(`Lexical`/`HybridCanonicalMemoryRetriever`, RRF). **candidate는 같은 seam을 아직 못 바꾼다** — 이유는 하나: **candidate 색인 표면이 없다**. canonical은 `memory_vectors`(Chroma) + `memory_lexical`(ES nori)에 색인되지만(2B.5 outbox→worker), candidate는 어떤 파생 index에도 들어가지 않아 vector/lexical query 대상이 없다.

따라서 b-2는 canonical의 vector/lexical retrieval 확장(retriever만 교체)과 **성격이 다르다**: **색인 파이프라인을 새로 지어야** 한다(enqueue 트리거 → outbox 이벤트 → worker drain → candidate vector/lexical index). 그 위에 retriever를 얹는다. 사실상 2B.5(canonical 색인) + v1.6.51/52(canonical retrieval)를 candidate에 대해 한꺼번에 재현하는 slice다.

## 조사에서 확인한 사실 (코드 primary source)

1. **candidate 상태는 `needs_review` **하나뿐**** ([analysis/models.py:26](../../services/application/app/analysis/models.py#L26) `AnalysisCandidateStatus` = `NEEDS_REVIEW` 단일). `confirmed`/`rejected` 전이는 Phase 6(`06-review-ui.md`). 승격(2B.1)은 canonical `MemoryEntry`를 mint하되 원본 candidate는 건드리지 않는다(v1.6.50 D5 정정). → **현재 candidate는 생성 후 불변**이고 상태 전이·삭제가 없다.
2. **결과: de-index 이벤트가 존재하지 않는다.** canonical은 append-only versioning이라 superseded 발생 시 이전 벡터를 삭제하는 self-heal이 필요했으나([memory_index.py](../../services/application/app/indexing/memory_index.py) `status is not CANONICAL → delete`), candidate는 아직 그런 전이가 없다. candidate 색인은 지금 **생성 시 upsert만** 있고 삭제 경로는 Phase 6 전이가 도입될 때 도달 가능한 forward-defense다(v1.6.50 Gate `status≠needs_review→stale` 분기와 동일 자세).
3. **canonical 색인 파이프라인(미러 대상)**: enqueue는 `MemoryService` 단일 choke point([memory/service.py](../../services/application/app/memory/service.py) `_enqueue_reindex`→`enqueue_memory_upserted`) → `MEMORY_UPSERTED` outbox([indexing/models.py:29](../../services/application/app/indexing/models.py#L29)) → worker가 `CompositeMemoryIndexSyncAdapter`(vector `MemoryIndexSyncAdapter` + lexical `MemoryLexicalIndexSyncAdapter`)로 fan-out drain.
4. **candidate 생성 choke point**: extraction이 `record_candidate`/`record_candidates`([analysis/service.py:308,339](../../services/application/app/analysis/service.py#L308))로 persist → repo `put_candidate`/`put_candidates`. project-wide `list_needs_review_candidates`(v1.6.50 신설)이 이미 존재.
5. **candidate retriever 현행**: `MongoDirectCandidateMemoryRetriever`([context_search/service.py:336](../../services/application/app/context_search/service.py#L336))는 `list_needs_review_candidates`를 limit 슬라이스만(query 무시=랭킹 없음). item 변환은 `derive_memory_index_text(candidate_type, payload)` 재사용([service.py:683](../../services/application/app/context_search/service.py#L683)).

## 헤드라인 긴장 (CLAUDE.md §1 — 임의 구현 없이 surface)

1. **규모.** 이 slice는 남은 retrieval 후보 중 가장 크다. canonical vector/lexical은 색인이 이미 있어 retriever 순수 교체(v1.6.51 회귀 6, v1.6.52 회귀 14)였으나, candidate는 색인 파이프라인 전체(enqueue·outbox 이벤트·worker drain·저장소 2종)를 신설한 뒤 retriever를 얹는다. 증분 분할(G0)로 원장·검증 단위를 관리한다.
2. **needs_review-only 필터가 현재 tautology.** retriever 권위 재유도의 `status is NEEDS_REVIEW` 필터는 지금 항상 참이다(상태가 1종). 이는 canonical의 CANONICAL 필터와 대칭 구조지만, candidate에서는 Phase 6 전이 전까지 실효가 없다 — **이 사실을 브리프에 명시하고 회귀는 forward-defense로 잠근다**(값이 늘 때 도달). 색인 self-heal delete도 같은 이유로 지금은 도달 불가 분기다.
3. **canonical↔candidate index 물리 분리 필요.** 두 index는 권위 재유도 source(memory store vs analysis store)와 라이프사이클(superseded self-heal vs needs_review 불변)이 다르다. 저장소를 섞으면(kind 판별자 재사용) 필터·삭제 로직이 흐려진다 → 물리 분리 권장(G1).

## 결정 항목

### G0 — slice 증분 분할 (추천: A)
- **A(추천)**: 2 증분. **증분1 = candidate 색인 파이프라인**(enqueue at `record_candidate` choke point → `CANDIDATE_UPSERTED` outbox 이벤트 → worker composite drain → candidate vector + lexical index 적재). **증분2 = retriever + 배선**(`Vector`/`Lexical`/`HybridCandidateMemoryRetriever` + env 선택). canonical이 색인(2B.5)과 retrieval(v1.6.51/52)을 분리한 선례. 각 증분 독립 회귀·커밋.
- B: 한 커밋 관통 — 거부(원장 단위 과대, 검증 표면이 한 커밋에 색인+retrieval 뭉침).

### G1 — 색인 저장소 (추천: A)
- **A(추천)**: canonical과 **물리 분리**. vector = 별도 Chroma collection `candidate_vectors`(env `CHROMA_CANDIDATE_COLLECTION`), lexical = 별도 ES index `candidate_lexical`. `IndexRecordKind.CANDIDATE` 신설 + `IndexSyncEvent.CANDIDATE_UPSERTED` 신설. 근거 §긴장3(재유도 source·라이프사이클 상이).
- B: `memory_vectors`/`memory_lexical` 재사용 + `kind` 판별자 — 거부.

### G2 — enqueue 트리거 / choke point (추천: A)
- **A(추천)**: `record_candidate`/`record_candidates`(extraction persist)를 choke point로 `CANDIDATE_UPSERTED` enqueue(MemoryService 중앙화 선례 대칭). candidate 불변이라 생성 시 1회 색인. **de-index 이벤트 없음**(§긴장2): 색인은 upsert-only, retriever 권위 재유도가 정합 보장, self-heal delete는 Phase 6 전이 도입 시 도달하는 forward-defense.
- B: backfill-only 정기 재색인 — 거부(canonical D6=write-only enqueue 선례).
- **outbox per-target bookkeeping**: v1.6.52 정정대로 enqueue는 배포 sink 구성을 모르므로 무조건 target을 넣지 않고 worker가 configured sink로만 fan-out(영구 pending 회피). candidate도 동일 자세.

### G3 — retriever 권위 재유도 (추천: A, canonical 대칭)
- **A(추천)**: vector/lexical hit → `candidate_id` → analysis store `get_candidate` 재유도 → 존재 + `status is NEEDS_REVIEW` + project만 반환. index text는 근거 아님(contracts §1.3 "정본 재조회 후 grounding"). canonical `get_memory`→CANONICAL 대칭. 삭제/전이된 candidate의 잔존 벡터는 재유도에서 skip(canonical stale-vector 격리 대칭).

### G4 — backend legs (추천: A)
- **A(추천)**: canonical end-state 미러 — vector + lexical + hybrid(RRF k=60) **한 slice**(증분2). env 선택: `CHROMA_HOST`+`EMBEDDING_SERVICE_URL`→vector, `ELASTICSEARCH_URL`→lexical, 둘 다→hybrid, 없으면 종전 Mongo-direct fallback. canonical `HybridCanonicalMemoryRetriever`의 RRF·`_merge_hits` 로직을 candidate로 평행 구현(제네릭 추출은 §2 최소변경 위배 위험이라 범위 밖, 필요 시 후속).
- B: vector leg 먼저 lexical 후속(canonical v1.6.51/52 분할) — 색인을 이미 composite로 짓는데 retriever만 나누는 건 원장만 늘림. 단 규모 우려 시 채택 가능(오너 판단).

### G5 — text projection (추천: A)
- **A(추천)**: `derive_memory_index_text(candidate_type, payload)` 재사용(canonical과 동일 taxonomy, 이미 `_item_from_candidate`·canonical 색인이 사용). 색인 text = write projection 동일 → vector/lexical 매칭 일관(2B.6 "쓰기·query 동일 projection" 선례).

### G6 — 배선 / 배포 (추천: A)
- **A(추천)**: retriever env 스위치는 canonical과 동일 env 재사용(별도 candidate env 신설 없음, §2). worker(`index_sync_worker.py`)가 `CANDIDATE_UPSERTED`도 composite drain(vector+lexical). worker는 여전히 compose 미추가(out-of-band, b-5 G6 선례). retriever는 index 비어도 graceful empty.

## 검증 계획 (구현 시)
- **증분1(색인)**: enqueue choke point가 `record_candidate(s)` 시 `CANDIDATE_UPSERTED`를 넣음(idempotent replay 미enqueue), worker composite drain이 candidate vector+lexical index 적재, self-heal delete 분기(forward-defense, status 전이 stub). enqueue·drain mutation 양방향.
- **증분2(retriever)**: 권위 재유도 needs_review-only(under-strict: 전이된 candidate 잔존 hit 격리) + relevance 순서 + global limit + hybrid RRF 양신호 융합·dedup + 단일 backend 저하 + retriever 미주입→빈 step·예외→BACKEND_ERROR(v1.6.50 cell 대칭). seam 반환 타입 불변 → `_run_candidate_memory_step`/`_item_from_candidate`/Gate `_gate_candidate_findings` 무변경 lock. mutation 양방향(RRF·needs_review 필터·embed query 무시).
- **§62 보존**: candidate item은 여전히 micro·`status=candidate` 라벨·권위필드 배제(v1.6.50 회귀 무변 통과 확인).
- 실 Chroma/ES live smoke(candidate 색인→retriever 관통)는 canonical 선례대로 sandbox 밖 후속 또는 docker 가용 시 실행.

## 범위 밖
- candidate↔canonical semantic dedup(HANDOFF (e), v1.6.50 D7 후속).
- Phase 6 `confirmed`/`rejected` 전이 및 그에 따른 de-index 실발화(forward-defense만 이 slice).
- hybrid 가중치/RRF k 튜닝(HANDOFF (b-4)).
- worker compose 서비스화(HANDOFF (b-6)).
- retriever RRF/merge 제네릭 추출(canonical과 공유 추상화) — 필요 시 별도 리팩터 slice.
