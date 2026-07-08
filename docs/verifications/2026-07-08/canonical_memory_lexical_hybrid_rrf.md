# 검증 기록 — 2026-07-08 SoT v1.6.52 독립 감사 (canonical memory retrieval ES lexical + hybrid RRF)

## Subject metadata

- **날짜**: 2026-07-08
- **요청자**: 오너("다음 작업 검증해줘. 이번에는 좀 큰 slice라서 신경써서 해줘.")
- **검증자**: Claude(독립 감사 — 작업자 주장을 그대로 믿지 않고 1차 사료에서 재도출)
- **검증 대상 slice/아티팩트**: SoT v1.6.52 — ⑤ §5 B / §8 "Writing canonical memory retrieval의 ES lexical + hybrid(RRF) 확장". 신설 `memory_lexical_index.py`(ES adapter+InMemory fake+sync adapter), `LexicalCanonicalMemoryRetriever`+`HybridCanonicalMemoryRetriever`(service.py), `CompositeMemoryIndexSyncAdapter`(memory_index.py), env 배선(main.py), worker composite drain(index_sync_worker.py), live smoke(scripts/), 회귀 13개.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.52(Approved, 2026-07-08); `docs/plans/04-writing-memory-lexical-retrieval-decisions.md`(Resolved); 선례 v1.6.51(`04-writing-memory-vector-retrieval-decisions.md`), v1.6.26 outbox envelope.
- **작업 원본(source of work)**: 커밋 `8e3aaa0`(HEAD, main). working tree 검증 시작·종료 모두 clean.

## Scope

계약↔구현↔테스트↔fixture(in-memory/fake ES client)↔실 ES 스택을 whole로 취급. 검증 표면:

- **계약(브리프 E0–E6 + SoT v1.6.52 changelog)**: E3 오너 상향(hybrid), §1 정정(outbox `targets.elasticsearch` → worker composite fan-out, envelope bookkeeping 미룸)의 정합성·일관성.
- **구현**: `LexicalCanonicalMemoryRetriever`(ES query→`get_memory` 재유도→canonical-only), `HybridCanonicalMemoryRetriever`(RRF `1/(k+rank)` k=60, id dedup), `ElasticsearchMemoryIndexAdapter`(nori 매핑·멱등 delete·8.x kwargs), `MemoryLexicalIndexSyncAdapter`(worker drain, vector leg 대칭), `CompositeMemoryIndexSyncAdapter`(fan-out), env 배선(vector/lexical/hybrid/mongo-direct), worker composite drain.
- **회귀 +13**: boundary matrix 매핑, RRF [b,a,c] 고유 순서 pin, 양방향 mutation.
- **실 ES live smoke**: 실 ES 8.13.4+nori 관통(독립 재실행), ephemeral 정리.
- **계약 자기 모순**: outbox envelope 무변경, SoT 섹션 간 일관, envelope 수치 재계산.

## Methodology

1. **계약 스코프先行**: 브리프(`04-writing-memory-lexical-retrieval-decisions.md`)와 SoT v1.6.52 changelog(`git show 8e3aaa0 -- docs/system-contract-sot.md`)를 먼저 읽어 boundary matrix 구성.
2. **diff 검사**: `git show 8e3aaa0 -- <path>`로 전체 diff 확보(service.py/memory_index.py/main.py/worker/requirements + 신규 memory_lexical_index.py/smoke/test).
3. **의존 심볼 독립 확인**: `MemoryLexicalRecord` 필드, `MemoryLexicalIndexAdapter` Protocol, `ElasticsearchClient` Protocol(8.x kwargs), `MemoryService.get_memory` 시그니처, `IndexSyncOutboxEntry` 무변경 여부 grep.
4. **실행 재현**: `python3 -m pytest -q`(전체 650/45) + 타깃 13개 + 기존 seam 81개. mutation은 Edit→실행→`git checkout`(커밋된 코드라 안전) 복구.
5. **실 ES 독립 관통**: ES 8.13.4+nori 컨테이너(localhost:9201) 도달성·nori 설치 확인 → live smoke 재실행(`PYTHONPATH=.`) → 잔여 인덱스 확인·정리. timeout 진단을 위한 최소 ES 클라이언트 테스트(`request_timeout=30`) 별도 실행.

## Findings

### 1. 계약(브리프 + SoT v1.6.52 changelog) — 일치, §1 정정 투명

- SoT v1.6.52 changelog(`system-contract-sot.md:36`)와 브리프 오너 결정(E0/E1=A, E2=A, E3=hybrid, E4=A, E5=A, E6=A)이 일치. E3는 브리프 본문 "A(추천)=결합 안 함"에서 **오너가 hybrid(RRF)로 상향** — 브리프 상단 "오너 결정"에 "(추천 A 대신 오너가 상향)" 명시, SoT가 E3=hybrid로 기록. 정규 계약(SoT)은 명확.
- **§1 정정 정합**: 브리프 E1 "outbox `targets.elasticsearch` 추가"를 **worker composite fan-out로 구현, persisted envelope per-target bookkeeping은 미룄**. SoT changelog가 이 정정을 명시. `IndexSyncOutboxEntry`/`indexing/models.py`/`indexing/service.py`에 `elasticsearch`/`targets.elasticsearch` 참조 0건(grep 확인) → **v1.6.26 outbox envelope 무변경 확인**. 사유(enqueue는 배포 ES 구성을 몰라 무조건 ES target 시 비-ES 배포에서 영구 pending)은 코드로 실증됨: worker `_build_memory_adapter`가 `ELASTICSEARCH_URL` 있을 때만 composite build(`index_sync_worker.py:107-129`), 없으면 vector-only.
- **all-or-nothing semantics**: `CompositeMemoryIndexSyncAdapter.index_memory`(`memory_index.py:211-213`)가 각 sink의 `index_memory`를 순차 호출, any-raises→entry 실패·requeue. idempotent replay로 부분 상태(vector만 색인·ES 누락) 방지. envelope `targets.chroma.status`가 combined 결과 반영 → per-target ES bookkeeping 미지연이 추적/관측 gap일 뿐 정합성 gap 아님.

### 2. 구현 — `LexicalCanonicalMemoryRetriever`(`service.py:232-266`)

- `retrieve`: `lexical.search(project_id, query, limit)` → 각 hit `get_memory` 재유도 → `MemoryNotFound` skip → `status is CANONICAL` 필터. **vector retriever와 완전 대칭**(E2=A, embed→query_similar 자리에 ES query). seam·반환 타입 불변.
- `test_query_drives_ranking`이 query가 ES search에 전달됨을 lock(v1.6.51 #4 관찰의 lexical 대칭 보강).

### 3. 구현 — `HybridCanonicalMemoryRetriever`(`service.py:272-315`) — RRF 정합

- `DEFAULT_RRF_K = 60`(`:269`). `retrieve`가 양 sub-retriever의 canonical-resolved 순위 리스트를 받아 `scores[entry.id] += 1.0 / (rrf_k + rank + 1)`(rank 0-based enumerate → 1-based RRF `1/(k+rank)`)로 융합, `entries.setdefault(id, entry)` dedup, `sorted(-score, id)` → `fused[:limit]`.
- **RRF 공식 정확**: Cormack et al. 2009 표준(k=60, 1-based rank). 양 신호에서 권위 재유도가 이미 끝났으므로 fusion은 pure rank merge. 이중 재유도(각 sub-retriever各自)는 idempotent·비효율 only(정합 영향 없음).

### 4. 구현 — `memory_lexical_index.py`(신규 300줄)

- `MemoryLexicalRecord`(`:31-45`): `memory_id`/`project_id`/`memory_type`/`version`/`status`/`text`/`score=0.0`. retriever가 `hit.memory_id` 사용 → 정합.
- `memory_lexical_text`(`:59-62`) = `derive_memory_index_text` 재사용 → **양 leg 동일 projection**("같은 canonical surface rank").
- `InMemoryMemoryLexicalIndexAdapter`(`:84-131`): 토큰-overlap fake(distinct query token 수로 score, `(-score, memory_id)` 랭킹).
- `ElasticsearchMemoryIndexAdapter`(`:149-222`): `index_memory_records`→`client.index(index, id, document)`(8.x kwargs), `search`→`bool.must.match.text` + `filter:[term project_id, term status=canonical]`, `delete`→`client.delete` + `except Exception: pass`(멱등). nori 매핑(`:228-241`, `analyzer: korean type=nori`).
- `MemoryLexicalIndexSyncAdapter`(`:244-281`): canonical→index/superseded·deleted→delete/`supersedes`→delete old. **vector leg `MemoryIndexSyncAdapter`와 대칭**(2B.4 append-only 불변).
- `connect_elasticsearch_memory_index`(`:284-300`): lazy `from elasticsearch import Elasticsearch`, 인덱스 부재 시 nori settings+mappings로 create.

### 5. 구현 — env 배선(`main.py:429-489`) + worker drain(`index_sync_worker.py:107-129`)

- `_build_canonical_memory_retriever`: `_build_vector_canonical_retriever`(None when CHROMA_HOST/EMBEDDING_SERVICE_URL 부재 — v1.6.51의 Mongo-direct 반환에서 None 반환으로 변경) + `_build_lexical_canonical_retriever`(None when ELASTICSEARCH_URL 부재) → both=hybrid / vector-only / lexical-only / neither=Mongo-direct. **E6=A**.
- worker: `ELASTICSEARCH_URL` 시 `CompositeMemoryIndexSyncAdapter((vector_adapter, lexical_adapter))` 반환, backend label `f"{backend}+elasticsearch"`. **§1 fan-out 구현 확인**.
- `requirements.txt`: `elasticsearch>=8,<9` 추가(설치됨 8.19.3, 범위 내).

### 6. 회귀 +13 — boundary matrix 매핑(`tests/test_context_search_memory_lexical_retrieval.py`)

| # | 계약 branch | 방향 | 테스트 | 상태 |
|---|---|---|---|---|
| 1 | InMemory lexical 랭킹 + project scope | should-fire | `test_ranks_by_token_overlap_and_scopes_project` | ✓ |
| 2 | ES adapter pointer 문서 | should-fire | `test_index_builds_pointer_document` | ✓ |
| 3 | ES adapter filtered query + hit parse | should-fire | `test_search_filters_project_and_canonical_and_parses_hits` | ✓ |
| 4 | ES adapter 멱등 delete | should-fire | `test_delete_is_idempotent` | ✓ |
| 5 | lexical retriever 권위 재유도 + canonical-only | should-fire | `test_authority_re_derivation_and_canonical_only` | ✓ + mut B |
| 6 | lexical query-drives-ranking | should-fire | `test_query_drives_ranking` | ✓ |
| 7 | hybrid RRF 양신호 융합 | should-fire | `test_rrf_fuses_both_signals` | ✓ + mut A |
| 8 | hybrid dedup + limit | should-fire | `test_dedup_and_limit` | ✓ |
| 9 | hybrid 단일 backend 저하 | should-fire | `test_single_backend_degrades_to_that_backend` | ✓ |
| 10 | worker drain canonical→index | should-fire | `test_canonical_memory_is_indexed` | ✓ |
| 11 | worker drain superseded→delete | should-fire | `test_superseded_memory_is_deleted` | ✓ |
| 12 | worker drain missing→delete | should-fire | `test_missing_memory_deletes_without_crash` | ✓ |
| 13 | composite fan-out | should-fire | `test_fans_out_to_every_sink` | ✓ |
| 14 | 실 ES nori 한국어 query + 권위 + hybrid + 정리 | should-fire | live smoke(독립 재실행 통과) | ✓ (E5) |
| 15 | worker ES-composite 배선(ELASTICSEARCH_URL→composite) | should-fire | — | **GAP**(이슈 #1) |
| 16 | seam 불변(step/item/Gate 무변) | should-NOT-fire | 81 기존 seam 회귀 | ✓ |
| 17 | stale/superseded NOT 노출(lexical) | should-NOT-fire | #5 + mut B | ✓ |
| 18 | RRF NOT naive concat/single-signal | should-NOT-fire | #7 + mut A | ✓ |
| 19 | cross-project NOT 누출 | should-NOT-fire | #1(project-2 제외) + #3(ES filter) | ✓ |
| 20 | outbox envelope NOT 변경(§1) | should-NOT-fire | grep(targets.elasticsearch 0건) | ✓ |
| 21 | candidate NOT 변경 | should-NOT-fire | 81 seam 회귀(candidate 무변) | ✓ |

- **RRF [b,a,c] pin 검증**: vector=[a,b], lexical=[b,c]. RRF(k=60): a=1/61, b=1/62+1/61(최고), c=1/62 → [b,a,c]. 이 순서는 naive concat([a,b,c])·single-signal([a,b]/[b,c])·round-robin([a,b,c])과 모두 달라 **RRF 고유**. test #7이 RRF-specific property를 pin.
- **seam 불변**: 기존 canonical/candidate/vector/context_search/api/memory_vector_index = **81 passed**(신규 lexical/hybrid 무영향).
- **전체 스위트**: `650 passed / 45 skipped`(재실행 일치, 637→+13). `git diff --check` clean.

### 7. mutation 양방향 독립 재실증

- **Mutation A(RRF→naive concat)**: `HybridCanonicalMemoryRetriever.retrieve`의 RRF scoring을 naive concat(dedup, fusion 없음)으로 교체. `test_rrf_fuses_both_signals` **FAILED**: `['a','b','c'] != ['b','a','c']`(b가 양 신호에 있어도 fusion 없으면 a가 먼저). → RRF fusion load-bearing(over-strict). `git checkout` 복구 후 13 passed.
- **Mutation B(canonical 필터 무력화)**: `LexicalCanonicalMemoryRetriever`의 `if entry.status is MemoryStatus.CANONICAL:` → `if True:`. `test_authority_re_derivation_and_canonical_only` **FAILED**: `['live','old'] != ['live']`(superseded "old" 누출). → canonical 필터 load-bearing(under-strict). `git checkout` 복구 후 13 passed.
- 복구 후 working tree clean, `git diff --check` clean, 잔여 0.

### 8. 실 ES live smoke 독립 재실행(`scripts/phase4_lexical_memory_live_smoke.py`)

- **ES 컨테이너 실측**: localhost:9201 → ES 8.13.4, `analysis-nori 8.13.4` 설치 확인.
- **smoke 재실행 통과**(nori 웜업 후): `{"ok": true, "lexical_ids": ["storm"], "hybrid_ids": ["storm","calm"], "nori": true}`. 한국어 "폭풍" query → canonical storm만 매칭(superseded "stale" 제외), 권위 재유도(store payload), hybrid RRF, ephemeral `ai_writte_smoke_<uuid>` 인덱스 `finally` 삭제 → 잔여 0.
- smoke 구조: ephemeral uuid 네임스페이스(line 88), 실 worker drain 경로(`MemoryLexicalIndexSyncAdapter`), `finally: client.indices.delete(ignore_unavailable=True)`. exit 0/1/2 구분.
- **최소 ES 진단 별도 실행**(`request_timeout=30`): nori create 4.04s / index 0.19s / search 0.01s→1 hit / cleanup OK → real ES nori lexical matching 독립 확인.

## Issues / Risks

### 차단(blocking) — 없음

boundary matrix 21 cell 중 20 cell pinned. 1 cell(#15 worker ES-composite 배선)은 wiring glue로, composite 클래스(#13)·lexical drain(#10-12)·실 ES smoke(#14)가 substance를 cover. 정합성 boundary(권위 재유도·canonical-only·stale 필터·RRF)는 전부 pin됨.

### 비차단 관찰

- **이슈 #1(test-coverage, slice 최약점)**: worker `_build_memory_adapter`의 `ELASTICSEARCH_URL` composite 분기(`index_sync_worker.py:107-129`)가 **단위테스트·live smoke 모두에서 미실증**. `test_index_sync_worker_script.py`는 no-chroma/with-chroma 분기는 테스트하지만 ES composite 분기는 없고(grep 0건), smoke는 worker 배선이 아닌 `MemoryLexicalIndexSyncAdapter`를 직접 사용. composite 클래스는 테스트(#13)되므로 gap은 wiring glue로 한정 — broken 시 ES+Chroma 배포에서 worker가 vector-only drain로 silent 저하(lexical hit 누락, 정합성은 권위 재유도가 보장). `test_with_chroma_host_builds_chroma_memory_adapter` 선례처럼 `connect_elasticsearch_memory_index` mock으로 `test_with_elasticsearch_url_builds_composite_memory_adapter` 추가 권장.
- **이슈 #2(smoke 견고성, 실측 발견)**: smoke가 `Elasticsearch(url)`로 **명시적 `request_timeout` 없이** 기본(10s) 사용. nori 인덱스 create가 ~4s(부하 시 더). 첫 재실행 시 create>10s로 `ConnectionTimeout`(exit 2) + **`finally` delete도 같은 timeout으로 잔여 인덱스 `ai_writte_smoke_*` 남음**(공유 컨테이너). 오너 실행 시엔 ES가 빨라 통과했을 것이나, E5가 명시한 "공유 컨테이너 생성/삭제 격리"가 timeout 시 깨짐. 검증자가 잔여 수동 정리. `request_timeout=30` + finally-delete timeout 보장(또는 재시도) 권장. 최소 진단(`request_timeout=30`)에서는 전부 정상 동작.
- **이슈 #3(spec-literal 미세 편차)**: ES 문서 필드가 `memory_id`인데 브리프 E4는 `mongo_id`로 명명(`memory_lexical_index.py:169`). SoT changelog는 "mongo pointer + nori text"(필드명 미pin). 구현 내 `memory_id`로 일관·retriever `hit.memory_id` 정합. 비차단.
- **이슈 #4(spec 권장 편차)**: ES `search`가 `project_id`+`status=canonical` 필터만 하고 `memory_type` 필터 없음(브리프 E4는 memory_type 필터 권장). cross-type BM25 랭킹으로 유효하고 canonical 필터+권위 재유도가 정합성 보장. 비차단.
- **이슈 #5(코드 일관성)**: ES `delete_memory_record`가 `except Exception: pass`(광역) — Chroma delete(`chroma.py:319`)는 예외 전파. 광역 catch가 실제 ES 장애(연결 오류 등)를 silent success로 마스킹 가능. 단 stale ES doc은 retrieval 시 `get_memory`+CANONICAL 필터로 거름(정합 영향 없음). Chroma와의 일관성 위해 `NotFoundError` 한정 catch 권장.
- **이슈 #6(doc, pre-existing)**: `system-contract-sot.md:101` "문서 역할" 표가 `Approved SoT v1.6.43`으로 누적 stale(v1.6.51/52 모두 미갱신). 본 slice 범위 밖이나 계약 자기 일관성 차원 재지적.
- **이슈 #7(doc, 브리프 내부)**: 브리프 "결정 필요 항목" E3가 여전히 "A(추천)=결합 안 함" 권장(오너가 hybrid로 상향했음에도). 상단 "오너 결정"에 상향 명시돼 있어 정규 계약(SoT)은 명확하나, options 섹션이 stale. 비차단.

## Verdict

**합격(pass)** — 본 slice가 선언한 scope(E0–E6, E5=fake+실 ES smoke) 내에서.

load-bearing 근거:
1. **계약↔구현 일치**: E2(lexical=vector 대칭)·E3(RRF `1/(k+rank)` k=60, 공식 정확)·E4(nori 매핑)·E6(env 배선)·E1(worker composite drain) literal이 코드에 불변再现. §1 정정(outbox 무변·worker fan-out) 투명·정합.
2. **RRF 정합성 독립 검증**: [b,a,c]가 naive concat/single-signal/round-robin과 구별되는 RRF 고유 순서임을 수학적으로 확인 + mutation A(naive concat)로 재실패 실증.
3. **권위 재유도 이중 방어**: lexical retriever CANONICAL 필터 + Gate `memory_service=memory`(`main.py:1453` 무변) 재검증. mutation B(canonical 필터 무력화)로 under-strict 재실패.
4. **실 ES 독립 관통**: ES 8.13.4+nori 컨테이너에서 smoke 재실행 통과(한국어 "폭풍"→canonical storm만, hybrid RRF, 잔여 0). E5 셀 독립 종료.
5. **seam 불변**: 81 기존 seam 회귀 무변(retriever 교체·step/item/Gate 무영향).
6. **envelope 재계산**: 650 passed/45 skip, git diff --check clean, working tree clean — 주장 정확 일치.
7. **outbox 무변경**: §1 정정이 v1.6.26 envelope 계약을 건드리지 않음 grep 확인.

비차단 관찰 7건(이슈 #1 worker ES 배선 테스트·#2 smoke timeout 견고성이 주요; #3-#7 spec/doc 미세 편차). 합격을 뒤집지 않으나 #1·#2는 cheap 보강 권장 — #1은 silent 저하 회피, #2는 공유 컨테이너 잔여 회피(E5 의도).

## Outstanding items

- **커밋 완료**(8e3aaa0, main). working tree clean. 본 검증 중 생성한 ES 잔여 인덱스 1건(초기 smoke timeout 시 발생) 수동 정리 완료, 공유 컨테이너 잔여 0 확인.
- **비차단 보강 권장**: (1) `test_with_elasticsearch_url_builds_composite_memory_adapter` 추가(이슈 #1); (2) smoke `request_timeout=30` + finally-delete 견고화(이슈 #2).
- **후속 slice(HANDOFF Next Tasks)**: (b-2) candidate lexical/vector(색인 파이프라인 선행), (b-4) hybrid 튜닝(RRF k·가중치), (b-5) compose 전용 ES 서비스, outbox per-target bookkeeping.
- **doc 정리(비차단)**: SoT:101 "문서 역할" v1.6.43 stale(이슈 #6), 브리프 E3 options 섹션(이슈 #7).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 전체 스위트(envelope 재계산)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 650 passed / 45 skipped 기대

# 2. 신규 lexical/hybrid 회귀 + seam 불변
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py          # 13 passed
python3 -m pytest -q tests/test_context_search_canonical_memory.py \
                     tests/test_context_search_candidate_memory.py \
                     tests/test_context_search_memory_vector_retrieval.py \
                     tests/test_context_search.py tests/test_context_search_api.py \
                     tests/test_memory_vector_index.py                              # 81 passed

# 3. mutation A(RRF→naive concat): service.py HybridCanonicalMemoryRetriever.retrieve 의
#    RRF scoring을 naive concat(dedup, fusion 없음)으로 교체
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py::HybridRRFTest::test_rrf_fuses_both_signals  # FAILED 기대(['a','b','c']!=['b','a','c'])
git checkout -- services/application/app/context_search/service.py   # 복구(커밋됐으므로 안전)

# 4. mutation B(canonical 필터 무력화): LexicalCanonicalMemoryRetriever 의
#    `if entry.status is MemoryStatus.CANONICAL:` → `if True:`
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py::LexicalRetrieverTest::test_authority_re_derivation_and_canonical_only  # FAILED 기대(['live','old']!=['live'])
git checkout -- services/application/app/context_search/service.py   # 복구

# 5. 실 ES live smoke(ES 8.13.4+nori 컨테이너 9201 필요)
PYTHONPATH=. python3 scripts/phase4_lexical_memory_live_smoke.py   # {"ok": true, "lexical_ids": ["storm"], "hybrid_ids": ["storm","calm"], "nori": true}
curl -s "http://localhost:9201/_cat/indices/ai_writte_smoke_*?h=index"  # 빈 출력 = 잔여 0
```
