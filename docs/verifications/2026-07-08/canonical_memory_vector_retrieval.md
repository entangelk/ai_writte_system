# 검증 기록 — 2026-07-08 SoT v1.6.51 독립 감사 (canonical memory retrieval vector 확장)

## Subject metadata

- **날짜**: 2026-07-08
- **요청자**: 오너("작업 AI가 작업한 내용 확인하고 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(독립 감사 — 작업자 주장을 그대로 믿지 않고 1차 사료에서 재도출)
- **검증 대상 slice/아티팩트**: SoT v1.6.51 — ⑤ §5 B D2 후속 "Writing canonical memory retrieval의 vector 확장". 신설 `VectorCanonicalMemoryRetriever`(`context_search/service.py`) + `_build_canonical_memory_retriever`(`main.py`) + 회귀 5개(`tests/test_context_search_memory_vector_retrieval.py`) + 브리프(`docs/plans/04-writing-memory-vector-retrieval-decisions.md`).
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.51(Approved, 2026-07-08 갱신); `docs/plans/04-writing-memory-vector-retrieval-decisions.md`(Resolved); 선례 `docs/plans/04-writing-canonical-context-decisions.md`(v1.6.48 D2=A "retrieval 교체·권위 재유도 불변" 위임).
- **작업 원본(source of work)**: working tree, **uncommitted**(main 브랜치). `git status` 변경 5개 + 신규 2개(HANDOFF/work_log/SoT/service.py/main.py + decisions/test).

## Scope

계약↔구현↔테스트↔fixture(in-memory/stub) 스택을 하나의 whole로 취급. 검증 표면:

- **계약(브리프 + SoT changelog)**: D0–D5 오너 결정의 일관성, "순수 주입 교체·step/item/Gate 무변" 불변식, 권위 재유도(D1)·단일 풀 병합(D2)·env 배선(D3)·fake 회귀 범위(D4)·ES 제외(D5) literal.
- **구현**: `VectorCanonicalMemoryRetriever.retrieve`/`_merge_hits`, `_build_canonical_memory_retriever` env 분기, 의존 심볼 시그니처 정합(`query_similar`/`MemoryIndexRecord`/`get_memory`/`_cosine_similarity`/`AnalysisCandidateType`).
- **회귀 +5**: boundary matrix cell 매핑, 양방향 guard(under/over-strict), seam 불변 실증.
- **계약 자기 일관성**: SoT 섹션 간 모순, spec-silent-but-code-enforced gap, envelope 수치 재계산.
- **문서**: SoT v1.6.51 갱신, HANDOFF, work_log, Project Structure 버전 주석.

## Methodology

각 주장을 1차 사료에서 재도출. work_log/SoT changelog 인용은 출발점일 뿐, 코드·테스트·실행 결과로 독립 확인.

1. **계약 스코프先行**: 브리프(`04-writing-memory-vector-retrieval-decisions.md`)와 SoT v1.6.51 changelog 항목을 먼저 읽어 boundary matrix 구성 후 코드를 읽음(CLAUDE.md "scope the contract read before opening it").
2. **diff 검사**: `git diff -- service.py main.py docs/system-contract-sot.md HANDOFF.md`로 전체 변경 확보. 미커밋 working tree이므로 `git diff`(HEAD 대비) 사용.
3. **의존 심볼 독립 확인**: `query_similar`(Protocol/InMemory/Chroma 3종), `MemoryIndexRecord` 필드, `get_memory` 시그니처·예외, `AnalysisCandidateType` 멤버, `_cosine_similarity` 사용 관례, `_build_semantic_matcher` 선례를 grep+targeted read로 재확인(작업자 주장에 의존 않음).
4. **실행 재현**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`(전체) + 타깃 파일/테스트. mutation은 Edit→실행→Edit 복구(working tree 미커밋이라 `git checkout`은 신규 클래스까지 날리므로 불가).
5. **mutation 양방향 독립 재실증**: CANONICAL 필터 무력화(under-strict), `_merge_hits` round-robin 교체(over-strict) 각각 독립 실행 후 복구.

## Findings

### 1. 계약(브리프 + SoT v1.6.51 changelog) — 일치

- SoT v1.6.51 changelog(`system-contract-sot.md:36`)와 브리프 오너 결정(D0=A~D5=A, `04-writing-memory-vector-retrieval-decisions.md:7-12`)이 literal 수준에서 일치. D2=단일 풀 병합 + `_merge_hits` 격리, D1=권위 재유도(`get_memory`+`status is CANONICAL`+`MemoryNotFound` skip), D3=`CHROMA_HOST`+`EMBEDDING_SERVICE_URL` 양쪽 env 배선, D4=fake 회귀(실 Chroma sandbox 후속), D5=ES 별도 — 전부 changelog에 명시.
- "순수 주입 교체·step/item/Gate 무변" 불변식: changelog가 `_run_canonical_memory_step`/`_item_from_memory`/`_gate_memory_findings` "한 줄도 안 바뀜"을 명시. 구현 diff도 `service.py`는 신규 클래스 추가 + import만(기존 메서드 본문 무변), `main.py`는 `_build_canonical_memory_retriever` 신규 + 주입점 1행 교체만 — **확인됨**.
- 헤드라인 긴장 2건 surface(브리프 §1): (1) HANDOFF "canonical·candidate 둘 다 vector"는 candidate 쪽 index 부재로 성립 않음 → D0=A로 canonical만 좁힘; (2) ES §8 인프라 전무 → D5=A 별도. 둘 다 코드 재확인으로 사실 확인(`indexing/`에 candidate 참조 0건, compose/코드에 ES 없음).

### 2. 구현 — `VectorCanonicalMemoryRetriever`(`service.py:156-226`)

- `retrieve`(`service.py:186-214`): (1) `embeddings.embed(query)`(`:189`), (2) 3종 `_MEMORY_TYPES`(`:173` = `tuple(AnalysisCandidateType)`) 각 `query_similar(memory_type=memory_type.value, limit=limit)`(`:191-199`), (3) `_merge_hits` 단일 풀(`:201`), (4) `get_memory` 권위 재유도 + `MemoryNotFound` skip(`:202-209`), (5) `status is MemoryStatus.CANONICAL` 필터(`:210`), (6) `len(entries) >= limit` global limit(`:212`). **D1/D2 literal과 불변**.
- `_merge_hits`(`service.py:216-226`): `sorted(hits, key=lambda hit: (-_cosine_similarity(vector, hit.vector), hit.id))` — cosine 단일 풀 + id tie-break, 격리된 단일 메서드(D2 "per-type 후속 분리 가능" swap point). **확인됨**.
- **의존 심볼 정합(전부 독립 확인)**:
  - `AnalysisCandidateType(StrEnum)` 정확히 3종(`analysis/models.py:11-14`), `.value`는 문자열. `MemoryEntry.memory_type: AnalysisCandidateType`(`memory/models.py:39`) → `_MEMORY_TYPES`가 memory_type 도메인과 정확히 일치(주석 "== MemoryEntry.memory_type domain" 정확).
  - `MemoryIndexRecord`에 `id`/`memory_id`/`memory_type`/`vector` 전부 존재(`indexing/models.py:145-153`) → `hit.memory_id`/`hit.vector`/`hit.id` 접근 안전.
  - `query_similar(*, project_id, memory_type: str, vector, limit)`(`memory_index.py:70-77` Protocol, `:98-121` InMemory, `chroma.py:340-361` Chroma) — `memory_type: str`에 `.value` 전달 정합. InMemory는 `project_id`+`memory_type` 필터 후 cosine 랭킹, Chroma는 `$and` where + `n_results=limit`. 둘 다 `vector` 포함 `MemoryIndexRecord` 반환.
  - `get_memory(*, project_id, memory_id)`(`memory/service.py:320`) → `_require_memory`(`:325-329`)가 deleted/cross-project엔 `MemoryNotFound`, **superseded는 반환**(2B.4 append-only 보존). → retriever의 `MemoryNotFound` skip(deleted) + `CANONICAL` 필터(superseded)가 두 stale case를 정확히 분담.
  - `_cosine_similarity`(`indexing/service.py:673`) — private import는 **기존 관례**(`semantic_matcher.py:23`, `memory_index.py:30`도 동일 import). 새 코드가 관례 준수.
- **Chroma real path vector 반환(deferred 정확성)**: `_memory_records_from_query`(`chroma.py:380`) → `memory_record_from_chroma`(`:284 vector=tuple(float(value) for value in embedding)`)가 vector 채움. → real path에서도 `_merge_hits`의 `hit.vector` 접근 안전(잠재 버그 아님). semantic_matcher(`semantic_matcher.py:75`)도 동일 `record.vector` 사용으로 이미 real path 검증 선례.

### 3. 구현 — `_build_canonical_memory_retriever`(`main.py:422-446`)

- env 분기(`main.py:430-431`): `if not host or not os.environ.get("EMBEDDING_SERVICE_URL"): return MongoDirectCanonicalMemoryRetriever(memory)` — **양쪽 env 모두 있어야 vector**. D3 literal과 일치.
- collection 배선(`main.py:433-440`): `ChromaMemoryVectorIndexAdapter(connect_chroma_collection(host, port=CHROMA_PORT 기본 8000, collection_name=CHROMA_MEMORY_COLLECTION or MEMORY_VECTOR_COLLECTION))`. `MEMORY_VECTOR_COLLECTION="memory_vectors"`(`memory_index.py:35`) — v1.6.46 선례와 일치.
- **선례 일관성(해소)**: `_build_semantic_matcher`(`main.py:331-360`)도 `CHROMA_HOST`+threshold 배선 + `EMBEDDING_SERVICE_URL` 누락 시 `RuntimeError` fail-fast. 새 빌더의 "양쪽 env 요구"는 선례와 동일(net effect). "선례 재사용" 주장 성립. 비대칭(semantic_matcher는 fail-fast, retriever는 silent fallback)은 retriever에 안전한 Mongo-direct fallback이 있어 정당.
- embedding 차원 안전: retriever는 `EMBEDDING_SERVICE_URL` 있을 때만 생성 → `_build_embedding_provider()`가 real `RemoteEmbeddingProvider`(1024-dim, `expected_dimensions` guard, `main.py:449-465`) 반환 → real Chroma `memory_vectors`(1024-dim)와 차원 일치.

### 4. 회귀 +5 — boundary matrix 매핑(`tests/test_context_search_memory_vector_retrieval.py`)

| # | 계약 branch | 방향 | 테스트 | 상태 |
|---|---|---|---|---|
| 1 | embed→vector로 cosine 랭킹 | should-fire | `test_returns_store_entries_in_relevance_order` | pinned¹ |
| 2 | 3종 type 각 query | should-fire | `test_merges_all_types_into_one_global_pool` | ✓ |
| 3 | 단일 풀 + global limit | should-fire | `test_respects_global_limit` + merge test | ✓ |
| 4 | `get_memory` 권위 재유도(store payload 반환) | should-fire | `test_returns_store_entries_in_relevance_order`(payload≠index text) | ✓ |
| 5 | `status is CANONICAL`만 | should-fire | `test_stale_vectors_are_dropped`(superseded) | ✓ + mutation A |
| 6 | deleted→`MemoryNotFound`→skip | should-fire | `test_stale_vectors_are_dropped`(ghost 부재) | ✓ |
| 7 | seam: retrieve→step→micro item(memory pointer, CANONICAL) | should-fire | `test_vector_retriever_produces_micro_memory_items` | ✓ |
| 8 | D3 fallback(env 없음→Mongo-direct) | should-NOT-fire(vector) | `test_context_search_api.py`가 `create_app` 관통(test env=Mongo-direct) | ✓² |
| 9 | D3 vector(양쪽 env→Vector) | should-fire | — | **D4 deferred**(live smoke) |
| 10 | index record text NOT 권위 | should-NOT-fire | `test_returns_store_entries_in_relevance_order` | ✓ |
| 11 | stale/superseded NOT 노출 | should-NOT-fire | `test_stale_vectors_are_dropped` | ✓ + mutation A |
| 12 | per-type round-robin NOT 사용 | should-NOT-fire | `test_merges_all_types_into_one_global_pool` | ✓ + mutation B |
| 13 | candidate 무변 | should-NOT-fire | 56 seam 회귀 + candidate retriever diff 무변 | ✓ |
| 14 | Gate memory 재검증(최종 방어선) | should-fire(prod) | v1.6.48 회귀(Gate retriever-무관) + endpoint `memory_service=memory`(`main.py:1453`) | ✓(무변) |

¹ embed→vector **mechanism**은 pinned(null vector→cosine 0→id 정렬→relevance 테스트 실패). 단, `query 인자가 embed에 전달되는지`는 `_FixedEmbeddings`가 query-무지각이라 hardcode-vector mutation으로부터 lock 안 됨 — D4가 "relevance 품질(실 embedding)"을 spike로 위임한 것과 인접(이슈 #4 참조).
² D3 fallback 분기는 `test_context_search_api.py:34,156,280`의 `create_app` 호출이 test env(env 없음)에서 `_build_canonical_memory_retriever`→MongoDirect를 실제 관통.

- **seam 불변 실증**: 기존 `test_context_search_canonical_memory.py`+`test_context_search_candidate_memory.py`+`test_context_search.py`+`test_context_search_api.py` = **56 passed**(retriever 교체 무영향).
- **전체 스위트**: `636 passed / 45 skipped`(재실행 일치, 631→+5). `git diff --check` clean. mongo-ignore 4개(env artifact, 프로젝트 관례).

### 5. mutation 양방향 독립 재실증(작업자 주장 재현)

- **Mutation A(under-strict)**: `if entry.status is MemoryStatus.CANONICAL:` → `if True:`(`service.py:210`). `test_stale_vectors_are_dropped` **FAILED**: `['old', 'live'] != ['live']`(superseded "old" 누출). → CANONICAL 필터 load-bearing. 복구 후 5 passed.
- **Mutation B(over-strict)**: `_merge_hits`를 round-robin(유형별 1개씩)으로 교체(`service.py:219-226`). `test_merges_all_types_into_one_global_pool` **FAILED**: `['char-a', 'event'] != ['char-a', 'char-b']`(유형별 1개씩이라 2번째 character hit이 더 낮은 event에 밀림). → 단일 풀 랭킹 load-bearing. 복구 후 5 passed.
- 복구 후 `MUTATION` 마커 잔여 0, `git diff --check` clean, service.py +80/-1(신규 클래스+import).

### 6. Gate 최종 방어선 확인(production 경로)

- `ContextSearchService.__init__`(`service.py:271-307`)는 `memory_service`를 받지 않고, `build_context_package`는 `evaluate_context_gate`를 호출 않음(정의만 `service.py:841`, package는 pre-Gate 빌드).
- **endpoint가 Gate에 memory_service 전달**: `main.py:1448-1453`가 `package = await build_context_package(request)` 후 `gate = evaluate_context_gate(..., memory_service=memory, ...)`. → production에서 Gate가 memory_id pointer로 `get_memory` 재검증. retriever CANONICAL 필터 + Gate 재검증 = stale 벡터 이중 방어선. **"Gate 불변·최종 방어선" 주장 확인**.
- 단, 신규 seam 테스트(`test_vector_retriever_produces_micro_memory_items`)는 pre-Gate package를 검사(Gate 미호출). 이는 설계적 정당: Gate는 retriever-무관(memory_id pointer 사용)이며 v1.6.48 회귀가 Gate memory 재검증을 이미 pin. 신규 테스트는 새 표면(retriever→step→item)에 집중. gap 아님.

## Issues / Risks

### 차단(blocking) — 없음

boundary matrix 14 cell 중 13 cell이 회귀로 pin됨. 유일한 빈 셀(#9, D3 vector env 분기)은 **D4=A 오너 결정으로 sandbox 밖 live smoke에 명시 위임** — 숨겨진 gap이 아니라 선언된 scope 경계. v1.6.36/46/47이 동일하게 real-Chroma live smoke를 추적 후속으로 두고 "합격" 받은 선례와 정합.

### 비차단 관찰

- **이슈 #1(doc nit, v1.6.51 도입, 반복 패턴)**: `HANDOFF.md:100` Project Structure의 SoT 버전 주석이 `v1.6.50`으로 stale. 작업 AI가 Current Status(`:8`)는 v1.6.51로 올렸으나 Project Structure 주석은 갱신 누락. 직전 보강(`work_log:84` 이슈 #1)이 같은 줄의 v1.6.48→v1.6.50 정정이었으므로 **동일 패턴 반복**. → `v1.6.51`로 정정 권장.
- **이슈 #2(doc nit, pre-existing)**: `system-contract-sot.md:100` "문서 역할" 표가 `Approved SoT v1.6.43`. v1.6.51 diff가 건드린 줄 아님(누적 stale). 본 slice 범위 밖이나 계약 자기 일관성 차원에서 기록.
- **이슈 #3(doc 일관성)**: SoT Phase 4 섹션 prose(`system-contract-sot.md:407`)가 v1.6.48(canonical Mongo-direct)까지만 서술되고 v1.6.50/v1.6.51 미반영. changelog(`:36`)는 권위 있고 완전하나 phase 요약 prose가 뒤처짐. v1.6.48이 Phase 4 prose에 추가된 선례를 고려하면 1줄 갱신 권장. literal 모순(아님)이 아니라 누락.
- **이슈 #4(test-coverage, scope 인접)**: `embed(query)`의 query 인자가 랭킹에 반영됨을 lock하는 query-민감 fake-embedding 테스트 부재. 현재 `_FixedEmbeddings`가 query-무지각이라 `embed(query)`를 상수 벡터로 hardcode해도 테스트가 통과. 단, D4=A가 "relevance 품질(실 embedding cosine 분포)"을 별도 spike로 위임했고 embed mechanism 자체는 pinned이므로, 본 slice 선언 scope 내에서는 차단 아님. cheap 보강(query-민감 fake로 "query가 embed에 전달" lock) 후속 권장.
- **경계 위험(무조치)**: per-type `query_similar(limit=limit)` 캡(브리프 D2 명시) + stale 필터링 결합 시, stale 벡터가 type별 top-`limit` 안에 몰리면 유효 canonical이 존재함에도 yield가 `limit` 미달일 수 있음. 단, (a) D2가 per-type `limit=L`을 명시 지정, (b) Mongo-direct retriever도 canonical-only라 `limit` 미달 가능성 동일, (c) stale은 과거 상태(reindex drain 전 일시적) — 설계적 속성, 코드 편차 아님.

## Verdict

**합격(pass)** — 본 slice가 선언한 scope(D4=A: 계약 + fake 회귀) 내에서.

load-bearing 근거:
1. **계약↔구현 literal 일치**: D1/D2/D3 literal(`get_memory` 재유도·`CANONICAL` 필터·`MemoryNotFound` skip·3-type 단일 풀 cosine·`_merge_hits` 격리·양쪽 env 배선)이 코드에 불변再现. 의존 심볼 시그니처 전부 독립 확인.
2. **seam 불변 실증**: retriever 교체가 step/item/Gate에 무영향(56 seam 회귀 + 신규 seam 테스트). production Gate 경로(`main.py:1453`)가 memory 재검증으로 최종 방어선 유지.
3. **양방향 mutation 독립 재실증**: CANONICAL 필터(under-strict)·`_merge_hits` round-robin(over-strict) 각각 타깃 테스트 재실패 → 두 guard 모두 load-bearing.
4. **boundary matrix 빈 셀 없음(선언 scope 내)**: 13/14 cell pinned, 잔여 1 cell(#9 real-Chroma env 분기)은 D4=A로 live smoke에 명시 위임된 scope 경계 — v1.6.36/46/47 선례와 정합.
5. **envelope 재계산**: 636 passed/45 skip, git diff --check clean — 작업자 주장과 정확 일치.

비차단 관찰 4건(doc nit 3 + test-coverage 인접 1)은 합격을 뒤집지 않으며, 이슈 #1(HANDOFF 버전 주석)·#4(query-민감 embed lock)은 cheap 후속 보강 권장.

## Outstanding items

- **미커밋**(main 브랜치, working tree). 오너 결정 대기: 브랜치 생성 후 커밋 여부. 본 검증은 working tree 상태로 수행.
- **D4 후속(sandbox 밖)**: `VectorCanonicalMemoryRetriever` live smoke(실 Chroma `memory_vectors` + BGE-m3-ko relevance 관통, #9 cell 채움) + relevance 품질 spike + #4 query-민감 embed lock 보강.
- **D0/D5 후속 slice**: (b-2) candidate vector(색인 파이프라인 선행), (b-3) ES lexical(§8 별도 브리프, 머신 `tf-ai-harness-elasticsearch-step1` 9201/nori 활용 검토).
- **doc 정리(비차단)**: HANDOFF:100 v1.6.51 정정, SoT:100 v1.6.43 누적 stale, SoT Phase 4 prose v1.6.50/v1.6.51 반영.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 전체 스위트(envelope 재계산)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 636 passed / 45 skipped 기대

# 2. 신규 회귀 + seam 불변
python3 -m pytest -q tests/test_context_search_memory_vector_retrieval.py          # 5 passed
python3 -m pytest -q tests/test_context_search_canonical_memory.py \
                     tests/test_context_search_candidate_memory.py \
                     tests/test_context_search.py tests/test_context_search_api.py  # 56 passed

# 3. mutation A(under-strict): service.py:210 의 `if entry.status is MemoryStatus.CANONICAL:` → `if True:`
python3 -m pytest -q tests/test_context_search_memory_vector_retrieval.py::VectorRetrieverStaleIsolationTest::test_stale_vectors_are_dropped  # FAILED 기대(['old','live']!=['live'])
# 복구 후 5 passed

# 4. mutation B(over-strict): service.py _merge_hits 본문을 round-robin으로 교체
python3 -m pytest -q tests/test_context_search_memory_vector_retrieval.py::VectorRetrieverMergeTest::test_merges_all_types_into_one_global_pool  # FAILED 기대(['char-a','event']!=['char-a','char-b'])
# 복구 후 5 passed

# 5. 변경 세트 + diff check
git status --short
git diff --check   # clean 기대
```
