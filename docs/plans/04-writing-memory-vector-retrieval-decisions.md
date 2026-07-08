# 착수 결정 브리프 — Writing memory retrieval의 vector/검색엔진 확장 (⑤ §5 B D2 후속)

**상태**: `Resolved` (2026-07-08 오너 결정) — canonical vector leg 구현 완료(SoT v1.6.51).

## 오너 결정 (2026-07-08)

- **D0 = A**: 이번 slice는 **canonical vector만**. candidate는 색인 index가 없어 Mongo-direct 유지 — candidate vector는 색인 파이프라인(2B.5 규모)을 선행하는 별도 slice로 분리한다.
- **D1 = A**: 권위 재유도 — 벡터에서 id를 찾고 Mongo memory store로 재유도(`get_memory`), `status is CANONICAL`만 반환. seam 시그니처·반환 타입 불변.
- **D2 = 단일 풀 병합(MVP)**: 3종 memory_type을 각각 `query_similar` 후 cosine 유사도로 **하나의 풀**로 병합·global limit. 단 오너 지시대로 병합 지점(`_merge_hits`)을 격리해 후속에 per-type 별도 선발 전략으로 **분리 가능하게** 둔다. (`MemoryIndexRecord.vector`가 fake·real 모두 노출돼 어댑터 변경 없이 retriever가 cosine 재계산 — 구현 착수 시 확인함.)
- **D3 = A**: 배포 배선. `CHROMA_HOST`+`EMBEDDING_SERVICE_URL` 둘 다 있으면 vector, 아니면 Mongo-direct fallback. tool 리터럴은 `mongo` 유지(dispatch가 need 기준).
- **D4 = A**: 계약 + fake 회귀. 실 Chroma+BGE-m3-ko 관통은 sandbox 밖 live smoke 후속.
- **D5 = A**: ES lexical(§8)은 이번 slice 범위 밖 별도 브리프. **단 오너 관찰**: 이 머신에 다른 용도의 ES 컨테이너(`tf-ai-harness-elasticsearch-step1`, ES 8.13.4 + nori 한국어 분석기, host 포트 **9201**)가 떠 있어, ES leg 착수 시 실 테스트 백엔드로 활용 가능성 확인 대상.

---

(원 브리프 — 참고)

**상태**: `Discussion` (오너 결정 대기)
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.50)
**선행 브리프**: `04-writing-canonical-context-decisions.md`(Resolved, D2=A로 "retrieval 레이어 교체·권위 재유도 불변"을 명시적으로 후속에 위임), `04-writing-candidate-context-decisions.md`(Resolved).
**선행 slice**: v1.6.48(canonical inclusion), v1.6.50(candidate inclusion) — 둘 다 retrieval을 **Mongo-direct(랭킹 없음, query 무시)**로 잠갔다.

---

## 왜 지금 열리나

canonical(v1.6.48)·candidate(v1.6.50) 둘 다 retriever seam(`CanonicalMemoryRetriever`/`CandidateMemoryRetriever`의 `.retrieve(project_id, query, limit)`)을 세우되 구현은 `MongoDirect*`로 잠갔다 — project 전수 리스팅에서 앞 `limit`개, **query 무시(=랭킹 없음)**. canonical D2=A가 이 형태를 고른 이유는 "retrieval 레이어(지금 Mongo-direct)와 권위 재유도(항상 memory store=Mongo)를 **분리 설계**해, 후속에서 retrieval을 vector·검색엔진으로 교체해도 item 변환·Gate 재검증이 불변이도록" 하기 위함이었다. 이 slice가 그 후속이다: retrieval을 relevance-aware로 교체한다.

## 현재 확정된 경계 (결정이 아니라 사실 — 코드 재확인함)

- **seam은 순수 주입 교체점이다.** `ContextSearchService._execute_step_tool`(`context_search/service.py:351`)은 memory need를 **need로 분기**(`step.need is CANONICAL_MEMORY`/`CANDIDATE_MEMORY`)하며 tool 리터럴을 보지 않는다. `_run_canonical_memory_step`/`_run_candidate_memory_step`은 주입된 retriever의 `.retrieve()`만 호출한다. → **다른 retriever 구현을 주입하면 step/item/Gate 코드는 한 줄도 안 바뀐다.**
- **canonical vector 인프라는 이미 다 있다.** `MemoryVectorIndexAdapter.query_similar(project_id, memory_type, vector, limit) → tuple[MemoryIndexRecord, ...]`(`indexing/memory_index.py:70`), in-memory fake(`InMemoryMemoryVectorIndexAdapter`) + 실 `ChromaMemoryVectorIndexAdapter`(`indexing/chroma.py`), `EmbeddingProvider.embed`(`indexing/memory_index.py:55`) 존재. `create_app`은 이미 semantic matcher용으로 `ChromaMemoryVectorIndexAdapter`를 `CHROMA_HOST` 있을 때 배선한다(`main.py:351`).
- **`memory_vectors`는 canonical `MemoryEntry` 전용이다.** 색인 경로(`MemoryIndexSyncAdapter.index_memory`, `indexing/memory_index.py:168`)는 `status is CANONICAL`이 아니면 벡터를 삭제한다. → **canonical만 vector로 조회 가능.**
- **candidate(`analysis_candidates`)는 어떤 vector/lexical index에도 색인돼 있지 않다.** `services/application/app/indexing/`에 candidate 참조 0건(재확인함). → candidate를 vector로 검색하려면 **candidate 색인 파이프라인을 먼저 만들어야 한다**(색인 서비스·outbox·worker drain — 2B.5 canonical 색인과 대등한 규모의 선행 작업).
- **ES/Elasticsearch 인프라는 전무하다.** compose에 ES 서비스 없음, 코드에 ES adapter 없음. SoT는 아키텍처 표(`system-contract-sot.md:128` "Elasticsearch | lexical/metadata retrieval index | canonical memory")에서 **의도만** 명시하고 §8 lexical 경로는 미착수다.
- **권위 재유도는 이미 Gate가 소유한다.** vector hit이 stale(예: superseded memory의 잔존 벡터)여도 `_gate_memory_findings`가 `get_memory` 재조회로 `status is CANONICAL`을 재검증해 거른다(candidate는 `_gate_candidate_findings`가 `needs_review` 재검증). retrieval이 잘못된 id를 줘도 Gate가 최종 방어선.

---

## ⚠ 헤드라인 긴장 (임의 구현 없이 surface — CLAUDE.md §1)

### 긴장 1 — HANDOFF의 "canonical·candidate 둘 다 vector로 함께 확장"은 candidate 쪽에서 성립하지 않는다
HANDOFF Next Tasks #1(b)는 "canonical·candidate 둘 다 현재 Mongo-direct … retrieval 레이어를 `memory_vectors` vector·ES로 교체(두 retriever가 같은 seam)"라고 적었다. seam이 같은 건 맞지만, **candidate는 조회할 vector index 자체가 없다**(위 사실 참조). 따라서 이번 slice에서 candidate까지 vector로 하려면 candidate 색인 파이프라인(2B.5 규모)이 **선행**돼야 한다. 이걸 한 slice에 묶으면 slice가 비대해지고 "미검증 candidate를 vector cache에 실체화"라는 §62 인접 위험(권위 재유도는 Gate가 막지만 색인 표면이 늘어남)도 새로 연다. → **canonical vector만 이번 slice, candidate vector는 별도 slice**를 추천(D0에서 확정).

### 긴장 2 — vector 검색은 `memory_type`을 요구하지만 retriever seam에는 없다
`query_similar`는 `memory_type`(character/event/open_question) per-type 인자를 요구한다. 그러나 retriever seam은 `.retrieve(project_id, query, limit)`로 type이 없다(현 Mongo-direct는 3종 전부 리스팅). vector retriever는 **3종을 각각 query해 병합**하거나, need에 type을 실어야 한다. 병합 시 서로 다른 type의 cosine score를 어떻게 통합·정렬·`limit` 적용하느냐가 결정 사항이다(D2).

### 긴장 3 — ES lexical(§8)은 vector와 같은 slice가 아니다
ES는 인프라가 전무해 (compose 서비스 + 색인 sync + adapter + query 계약) from-scratch 빌드다. vector(주입 교체 규모)와 묶으면 slice 크기가 질적으로 달라진다. → **ES는 이번 slice 범위 밖, 별도 브리프**를 추천(D5).

---

## 결정 필요 항목

### D0 — 이번 slice의 대상 [헤드라인 1]
- **A(추천)**: **canonical vector retrieval만.** candidate는 Mongo-direct 유지(색인 없음). candidate vector는 candidate 색인 파이프라인을 선행 slice로 분리.
- B: canonical + candidate 둘 다 vector (candidate 색인 파이프라인까지 이 slice에 포함) — 비대·§62 색인 표면 확대.
- 추천: **A** — canonical D2=A가 세운 seam 위에 인프라 있는 canonical만 얹으면 순수 주입 교체. candidate는 "색인부터"라 별도 축.

### D1 — canonical vector retriever의 권위 재유도 형태 [헤드라인 3의 역·불변식]
- **A(추천)**: 신규 `VectorCanonicalMemoryRetriever`가 (1) `embeddings.embed(query)` → vector, (2) `memory_vector_index.query_similar` → `MemoryIndexRecord`(id·memory_type), (3) 각 hit id로 `memory_service.get_memory` **권위 재유도**(canonical D2=A "벡터에서 찾고 Mongo를 찔러 권위 레코드 재유도"와 동형), (4) `status is CANONICAL`만 남겨 `tuple[MemoryEntry, ...]` 반환. **seam 시그니처·반환 타입 불변** → step/item/Gate 무변경.
- B: retriever가 `MemoryIndexRecord`를 바로 item으로 → 거부(vector cache text를 권위로 취급, canonical D2=A의 "Mongo가 권위" 원칙 위반, stale 벡터 노출).
- 추천: **A**.

### D2 — memory_type 다중 조회·병합 [헤드라인 2]
- **A(추천)**: 3종(character/event/open_question)을 각각 `query_similar(memory_type=t, limit=L)` 호출 후, 반환 `MemoryIndexRecord`를 **한 풀로 모아** cosine score 내림차순 정렬 → 상위 `limit`. (score tie-break은 fake 어댑터 관례인 `-score, id`.) 단 현 `query_similar` 반환에 score가 노출되는지 확인 필요 — 없으면 D2-A는 어댑터에 score 노출 또는 per-type round-robin 병합으로 축소.
- B: per-type round-robin(각 type에서 고르게) — score 비교 회피하나 relevance가 약해짐.
- C: need가 memory_type을 실어 단일 type만 — 현 planner/need 계약에 type이 없어 계약 확장 필요(범위 초과).
- 추천: **A 우선, 단 `query_similar`의 score 노출 여부를 구현 착수 시 확인해 A/B 확정**(surface: 지금 어댑터가 정렬만 하고 score를 안 돌려주면 A는 소폭 어댑터 변경 수반).

### D3 — 배선/fallback (deployment vs planner-selectable)
- **A(추천, deployment 배선)**: `create_app`이 `CHROMA_HOST`+`EMBEDDING_SERVICE_URL` 있으면 `VectorCanonicalMemoryRetriever`, 없으면 현 `MongoDirectCanonicalMemoryRetriever` fallback 주입. tool 리터럴은 `mongo` 유지(dispatch가 need 기준이라 무관). embedding fake↔실 불일치 방지는 기존 semantic matcher 배선의 가드(`main.py:345`) 선례 재사용.
- B: planner-selectable — `NEED_ALLOWED_TOOLS[CANONICAL_MEMORY]`에 `VECTOR` 추가하고 dispatch가 tool을 존중. `models.py:81` 주석이 이 여지를 남겼으나, 검색 backend는 배포 사실이지 planner 판단이 아니므로 계약 표면만 늘림.
- 추천: **A** — canonical D2=A의 "retrieval 레이어 교체는 배포 관심사, 계약 불변" 정신과 정합.

### D4 — 검증 경계 (4.1→4.2 리듬)
- **A(추천)**: 이번 slice = 계약 + **fake**(`InMemoryMemoryVectorIndexAdapter` + `DeterministicFakeEmbeddingProvider`) 회귀. 실 Chroma+BGE-m3-ko 관통은 sandbox 밖 live smoke 후속(2B.5 `phase2b5_memory_reindex_live_smoke.py` 선례에 canonical retrieval leg 추가). relevance 품질(실 embedding cosine 분포)은 별도 spike.
- 추천: **A**.

### D5 — ES lexical(§8) 위치 [헤드라인 3]
- **A(추천)**: 이번 slice 범위 밖. ES는 인프라 from-scratch라 별도 착수 브리프(§8, compose 서비스 + 색인 sync + adapter + lexical query 계약). SoT 아키텍처 표(line 128)의 의도는 보존.
- B: 이번 slice에 포함 — 거부(질적으로 다른 규모).
- 추천: **A**.

---

## 제안 slice 범위 (추천값 기준)

**포함**: `VectorCanonicalMemoryRetriever`(embed→`query_similar`→`get_memory` 권위 재유도→canonical-only), `create_app` 조건부 배선(Chroma+embedding 있으면 vector, 없으면 Mongo-direct fallback), 3-type 병합, fake 회귀.
**제외(후속)**: candidate vector(색인 파이프라인 선행), ES lexical(§8 별도 브리프), 실 Chroma live smoke(sandbox 밖), relevance 품질 spike, planner-selectable backend.

## 검증 계획 (구현 시)
- 신규 `tests/test_context_search_memory_vector_retrieval.py`:
  - vector retriever가 query embedding으로 `query_similar`를 호출하고 hit id를 `get_memory`로 재유도해 canonical `MemoryEntry`를 반환(권위 재유도 lock).
  - **stale 벡터 격리(under-strict)**: `query_similar`가 superseded/삭제 memory id를 돌려줘도 retriever가 `status is CANONICAL` 필터로 제외(또는 Gate가 최종 거름 — 어느 층이 책임지는지 D1에서 확정해 그 층을 assert).
  - **3-type 병합(D2)**: 서로 다른 type의 hit이 하나의 relevance 순서로 병합되고 `limit` 적용됨을 assert.
  - **fallback(D3)**: retriever 미주입/Chroma 미구성 시 Mongo-direct 경로가 그대로 동작(기존 v1.6.48 회귀 무변).
  - **seam 불변 회귀**: 기존 `test_context_search_canonical_memory.py`·`test_context_search_candidate_memory.py`가 retriever 교체와 무관하게 통과(step/item/Gate 무변경 실증).
  - **mutation 양방향**: 권위 재유도(`get_memory`)를 제거해 vector cache text를 바로 item화하면 stale-벡터 테스트가 재실패(over-correction 방어); embed 호출을 제거하면 query가 랭킹에 반영 안 돼 relevance 테스트 재실패(under-strict).

## 열린 질문 (오너에게)
1. **D0**: 이번 slice를 canonical vector만으로 좁히고 candidate vector는 색인 파이프라인 선행 별도 slice로 두는 데 동의하는가?
2. **D2**: 3-type 병합에서 cross-type relevance 정렬(A)을 원하는가, round-robin(B)이면 충분한가? (`query_similar` score 노출 여부에 따라 A가 소폭 어댑터 변경을 수반할 수 있음 — 구현 착수 시 확인해 보고.)
3. **D5**: ES lexical(§8)을 이번 slice 범위 밖 별도 브리프로 미루는 데 동의하는가?
