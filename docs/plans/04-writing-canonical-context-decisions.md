# 착수 결정 브리프 — Writing ContextPackage에 canonical memory 포함 (⑤ §5 B, unblocked)

**상태**: Resolved (오너 결정 완료 2026-07-07) — 구현 완료(SoT v1.6.48). candidate 포함·relevance vector retrieval은 후속 slice.
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.47)
**선행 브리프**: `04-context-package-completion-decisions.md`(D1=B로 ⑤를 Phase 2B에 종속), `04-agentic-search-kickoff-decisions.md` §5.
**선행 slice**: Phase 2B.1~2B.6 완료(canonical `MemoryEntry` store + `memory_vectors` vector index + query 경로).

---

## 왜 지금 열리나 (framing 전환)

2026-07-05 `04-context-package-completion-decisions.md`는 ⑤(`needs_review` candidate를 Writing에 포함)를 **D1=B로 미뤘다** — 근거는 "canonical store가 없어 '미검증 후보 vs 없음'의 선택이고, Gate의 candidate 금지는 Writing-안전성 방어선"이었다. **Phase 2B가 그 종속을 해소했다**: 이제 승인·승격된 canonical `MemoryEntry` store가 존재하므로, Writing이 **미검증 candidate가 아니라 canonical memory**를 근거로 쓸 수 있다.

→ **원 브리프의 D2~D4(candidate 검색 경로·`prior_memory` need·Gate 완화)는 candidate 전제였다. 이제 대상이 canonical로 바뀌어 결정 형태가 달라진다.** 이 재framing을 명시하고 새로 결정한다.

---

## 현재 확정된 경계 (결정이 아니라 사실)

- **Writing ContextPackage는 현재 source_block만 담는다.** `build_context_package`(`context_search/service.py`)가 planner의 need(`current_scene`/`recent_scenes`→mongo, `event_context`/`source_quote`→vector)를 source block/SOT로 실행해 `ContextItem`(전부 `status=CANONICAL`, source-block pointer)을 만든다. canonical memory는 안 들어간다.
- **`ContextItemStatus.CANDIDATE`/`CANONICAL` 라벨 필드는 이미 열려 있다**(`models.py:48`). 현재 모든 item은 `CANONICAL`(source block).
- **Gate는 이미 canonical 허용·candidate 금지다.** `evaluate_context_gate`(`service.py:469`)가 `status is CANDIDATE`면 `candidate_item_not_allowed`로 reject한다. 즉 "candidate 금지 → canonical 허용 + 미승인 candidate 금지"의 **candidate 금지 절반은 이미 성립**. 빠진 것은 canonical memory를 실제로 **넣는 것**과, 그 memory item을 **Gate가 검증할 방법**이다.
- **⚠ Gate의 stale 검증이 source-block 전용이다.** `_gate_stale_findings`(`service.py:523`)가 `core_sot.get_snapshot(snapshot_id)` + `content_hash` 드리프트 + block 존재로 item을 재검증한다. canonical memory는 snapshot/block/content_hash가 없어, **지금 memory item을 넣으면 Gate가 `stale_item`(snapshot missing)으로 무조건 reject**한다. memory item은 별도 검증 lineage가 필요하다.
- **canonical memory 재료는 두 곳에 있다**: Mongo `memory_entries`(2B.1, `MemoryService.list_memories`) + `memory_vectors` Chroma vector index(2B.5, `query_similar` 2B.6). 후자는 실 Chroma·worker drain 필요(eventual consistency).
- **PriorMemoryItem/`prior_memory` need는 Analysis용이다**(2B.2, `ANALYSIS_CONTEXT` purpose). Writing(`WRITING_CONTEXT`)은 planner 경유라 별도 need/tool 매핑이 필요하다(`NEED_ALLOWED_TOOLS`에 `prior_memory` 없음).

---

## ⚠ 헤드라인 긴장

### 긴장 1 — 대상이 candidate가 아니라 canonical이다 (원 브리프 재framing)
원 브리프 D2~D4는 candidate 전제(검색 경로·`prior_memory` need·Gate **완화**)였다. canonical은 이미 Gate가 허용하므로 "Gate 완화"가 아니라 **"memory item 검증 lineage 추가"**가 핵심이다. 이 slice가 candidate 포함까지 확장하는지(위험) 아니면 canonical만인지 D1에서 확정한다.

### 긴장 2 — Gate가 memory item을 어떻게 검증하나 (source-block 가정 붕괴)
현 Gate는 SOT snapshot 재검증으로 item 신뢰성을 재유도한다("orchestration flag를 믿지 않는다"). memory item은 snapshot이 없으므로, Gate가 **memory store를 재조회해 "여전히 canonical인가"로 검증**하는 새 분기가 필요하다. 이걸 안 하면 Gate의 독립 재검증 원칙이 memory item에 대해 무너진다(D4).

---

## 제안하는 slice 범위

**포함**: Writing ContextPackage가 canonical memory를 micro evidence로 담고, Gate가 memory item을 memory store 재조회로 검증한다.
- canonical memory 검색 need + tool 경로.
- memory `MemoryEntry` → `ContextItem`(또는 신규 item) 변환(status=CANONICAL, memory pointer).
- Gate 분기: source-block item은 SOT snapshot 검증, memory item은 "memory 존재·canonical" 재검증.
- candidate 금지 유지(라벨 그대로 reject).

**제외(후속)**: `needs_review` candidate 포함(여전히 미검증), `constraints`/`do_not_use` populate(Phase 5 착수 브리프, 원 D5), ⑧ Analysis 절(2B.2로 이미 완성), Phase 5 Writing prompt 소비.

---

## 결정 필요 항목

### D1. 이 slice가 담는 것 [헤드라인 1]
- **A**: canonical memory만 포함. candidate는 종전대로 Gate가 금지(방어선 유지).
- **B**: canonical + 라벨된 candidate(원 브리프 D4=A: candidate는 micro·라벨 필수·macro 금지).
- 추천: **A** — Phase 2B가 canonical을 줬으니 안전한 canonical부터. candidate 포함은 review 지위(Phase 6)와 얽혀 별도 결정. HANDOFF의 "canonical 포함"과 정합.

### D2. canonical memory 검색 경로
- **A(Mongo-direct)**: `MemoryService.list_memories` project scope + memory_type/need 필터. 랭킹 없음(전수 또는 recency). 최소·실 Chroma 불요·결정적.
- **B(memory_vectors vector)**: 2B.5/2B.6 `query_similar`로 writing query 유사도 검색. 관련성 랭킹. 단 실 Chroma·worker drain·eventual consistency 의존, 2B.6 threshold와 별개 경로.
- **C(하이브리드)**: vector 있으면 vector, 없으면 mongo fallback.
- 추천: **논의 필요.** Writing은 "현재 장면에 관련된 소수 canonical"이 필요해 관련성(B)이 자연스럽다. 그러나 실 Chroma 의존·off-기본과의 상호작용을 감안하면, **A(Mongo-direct)로 계약·Gate를 먼저 세우고 B는 후속 relevance 증분**이 4.1→4.2 리듬과 맞을 수 있다. 오너 판단(관련성 즉시 vs 계약 먼저).

### D3. memory → ContextItem 형태
- `ContextItem`은 source-block 중심 필드(`pointer` IndexPointer·`snapshot_id`·`sot_reloaded`·content_hash)를 가진다. memory item은 이들이 없거나 의미가 다르다.
- **A(ContextItem 재사용)**: memory pointer = `IndexPointer(project_id, collection="memory_entries", document_id=memory_id, version_id=str(version), content_hash="")`, `snapshot_id`는 빈 문자열/sentinel, `text`=projection(`derive_memory_index_text` 재사용?), status=CANONICAL. Gate가 pointer.collection으로 분기.
- **B(신규 item 타입)**: `MemoryContextItem` 별도 dataclass, package에 별도 필드.
- 추천: **A + collection 분기** — 단일 item 스키마 유지(D3=A 계열 선례), Gate·budget이 pointer.collection으로 origin을 구분. content_hash 없는 것은 Gate가 memory 분기에서 안 쓴다.

### D4. Gate 검증 분기 [헤드라인 2]
- source-block item: 현행 `_gate_stale_findings`(SOT snapshot). memory item: **memory store 재조회**로 (a) 존재, (b) `status is CANONICAL`(superseded/삭제면 stale), (c) project 일치 검증.
- candidate 금지: 유지(`status is CANDIDATE` → reject).
- 추천: `evaluate_context_gate`가 item origin(pointer.collection == `memory_entries`)으로 분기 — memory item은 `MemoryService.get_memory`로 canonical 재검증, 아니면 `stale_item`. cross-project·budget은 공통.

### D5. macro vs micro 배치
- **A**: canonical memory는 **micro_evidence 전용**(prior 지식 증거), macro(scene 골격)엔 금지. 원 브리프 D4 정신과 정합.
- 추천: **A**.

### D6. need literal + tool 매핑
- canonical memory를 서빙하는 need를 새로 둔다(예: `character_state`/`canonical_memory`) + tool(mongo 또는 vector). `NEED_ALLOWED_TOOLS`·`MACRO_NEEDS`(micro라 미포함) 확장.
- 추천: D2 결정에 종속(mongo면 tool=mongo, vector면 vector). need 이름은 Writing 의미로(예: `canonical_memory`).

### D7. 검증/소비 경계
- 이 slice는 계약+회귀(fake). 실 Chroma vector 경로(D2=B)면 실 관통은 sandbox 밖 후속. Phase 5 Writing prompt가 이 canonical을 어떻게 쓰는지는 Phase 5 착수 브리프.
- 추천: 4.1→4.2 리듬.

---

## 후속 (이 브리프 범위 밖)

- **바로 다음 slice**: `needs_review` candidate 포함 — 이 slice의 memory-item + Gate-origin-분기 machinery를 재사용해 candidate origin + `status=candidate` 라벨 처리(micro 전용·라벨 필수)를 얹는다. review 지위(Phase 6) 라벨/소비 계약을 함께 결정한다.
- **retrieval 레이어 확장(D2 연장)**: Mongo-direct → `memory_vectors` vector 검색(relevance 랭킹) → 검색엔진(ES lexical, §8). item 변환·Gate 권위 재유도(Mongo)는 불변, retrieval만 교체.
- `constraints`/`do_not_use` populate(Phase 5 착수 브리프, 원 D5).

## 결정 요약 (추천값)

| # | 결정 | 추천 |
|---|------|------|
| D1 | 담는 것 | A (canonical만, candidate 금지 유지) |
| D2 | 검색 경로 | Mongo-direct 먼저 vs memory_vectors vector — **오너 판단** |
| D3 | item 형태 | A (ContextItem 재사용 + collection 분기) |
| D4 | Gate 분기 | memory item은 store 재조회로 canonical 재검증 |
| D5 | 배치 | A (micro 전용) |
| D6 | need/tool | 신규 `canonical_memory` need (tool은 D2 종속) |
| D7 | 검증 | 계약+fake 증분, 실 vector는 후속 |

## Owner decisions — 2026-07-07

- **D1 = A (오너 논의 후 확정: A는 B의 토대다).** canonical memory만 포함한다. 오너가 "B가 더 확장적/리뷰 지위라도 뚫어놓기"를 제기했으나, 확장성 직관은 반대다 — 이 slice가 세우는 machinery(memory→ContextItem 변환, `pointer.collection` origin 분기, Gate의 origin별 재검증 분기)를 candidate 포함이 **그대로 재사용**하므로, **A 먼저 = B(candidate)가 작은 후속**(origin + 라벨 처리만 추가)이 된다. B를 한 slice에 다 하면 두 origin·두 안전 자세를 섞고, 게다가 `needs_review` candidate는 **review 지위(Phase 6)가 미정**이라 "어떻게 라벨·소비하나"를 추측해야 한다(배관이 아닌 미해결 의존). "Gate 라벨 경로만 열기"는 검색 경로 없이 소비 대상이 없어 무의미. **따라서 candidate 포함은 차단이 아니라 이 slice 바로 다음 slice**로 둔다(A의 machinery 위에 얹음).
- **D2 = A (오너 확정: retrieval/권위-재유도 분리).** 오너가 명시한 서비스 그림은 "벡터에서 찾고 → SoT인 Mongo를 찔러 권위 레코드 재유도"(source-block의 vector hit→SOT reload와 동일)다. 이 slice는 **retrieval 레이어(지금 Mongo-direct)와 권위 재유도(항상 memory store=Mongo)를 분리 설계**해, 후속에서 retrieval을 vector(`memory_vectors` `query_similar`)·나아가 검색엔진(ES lexical)으로 교체해도 item 변환·Gate 재검증이 불변이도록 한다. 지금은 Mongo-direct(project scope + memory_type)로 계약·Gate를 잠그고, relevance vector와 검색엔진 확장을 retrieval 레이어 교체로 얹는다.
- **D3 = 추천 잠금.** `ContextItem` 재사용 + `pointer.collection`으로 origin 분기(memory pointer: collection=`memory_entries`, document_id=memory_id, version_id=str(version)). 단일 item 스키마 유지, Gate/budget이 collection으로 memory vs source-block을 구분.
- **D4 = 추천 잠금.** `evaluate_context_gate`가 memory item(pointer.collection==`memory_entries`)은 `MemoryService.get_memory` 재조회로 (존재 + `status is CANONICAL` + project 일치) 재검증하고, source-block item은 현행 SOT snapshot 검증을 유지. candidate 금지 유지. cross-project·budget 공통.
- **D5 = A.** canonical memory는 micro_evidence 전용, macro(scene 골격) 금지.
- **D6 = 추천 잠금.** 신규 need `canonical_memory`(Writing 의미) + tool `mongo`(D2=A). `NEED_ALLOWED_TOOLS`에 `canonical_memory→(mongo,)` 추가, `MACRO_NEEDS`에는 미포함(micro).
- **D7 = 추천 잠금.** 계약+fake 회귀 증분. relevance vector 경로(D2 후속)의 실 관통은 sandbox 밖. Phase 5 Writing prompt 소비는 Phase 5 착수 브리프.
