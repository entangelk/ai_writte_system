# (b-6 후속) ES-lexical backfill 스크립트 — 착수 결정 브리프

**상태**: `Resolved` (2026-07-09 오너 결정 — G1=A·G2=A·G3=A·G4=A)
**관련**: SoT v1.6.57 changelog accepted limitation #1(ES-lexical backfill 부재, `docs/system-contract-sot.md:36`). b-6 증분2 브리프 `plans/04-worker-compose-outbox-bookkeeping-decisions.md`:99(한계#1)·:115(제외·후속). b-2 검증 관찰 (a)(candidate backfill 부재, `docs/daily_logs/2026-07-09/work_log.md:120`). HANDOFF Next Tasks #1 후보.
**범위**: b-6 증분2가 남긴 accepted limitation #1("per-sink-max로 terminal drop된 ES 실패는 수렴 수단 없음")을 닫는 backfill 스크립트. `scripts/phase2b5_reindex_memory.py`(vector-only)의 ES 대칭 — memory_lexical + candidate_lexical ES backfill. (G2 결정에 따라) b-2 관찰 (a)의 candidate vector backfill 부재도 함께 닫을지 결정.

## 배경 / 성격

- v1.6.52(canonical ES lexical/hybrid)·v1.6.54/55(candidate 색인·retrieval)·v1.6.53(compose ES)·v1.6.56/57(worker compose + per-sink bookkeeping)까지 색인·retrieval·drain 인프라는 완성됐다. 그러나 **과거 데이터 일괄 backfill은 vector-only 1개뿐**(`phase2b5_reindex_memory.py`, canonical memory만)이고, **ES lexical backfill은 전무**하다.
- b-6 증분2(v1.6.57)가 per-sink bookkeeping를 도입해 ES-only 실패를 관측 가능하게 했으나, per-sink-max로 terminal drop된 ES 실패는 **수렴 수단이 없다**(accepted limitation #1). worker는 outbox-driven increment drain만 하므로, 과거 데이터나 DLQ drop된 ES 실패를 일괄 재적재할 경로가 없다.
- 이 slice는 vector backfill의 ES 대칭을 지어 그 gap을 닫는다. **성격: 순수 운영 스크립트 + 회귀** — 새 계약 literal 없음, forward-defense stub과 무관(candidate는 needs_review 단일이라 upsert-only), helper는 전부 구현·잠금됨.

## 핵심 발견 — 필요 helper는 전부 구현됨 (1차 소스 file:line)

조사의 가장 중요한 발견: **이 slice는 새 모듈/계약 literal 없이 기존 helper의 조립만으로 완성된다.**

- **vector backfill(현재 유일, `scripts/phase2b5_reindex_memory.py`)**: `run_reindex`(:93-125)이 outbox를 우회(D7)해 `list_memories`→canonical 필터(`MemoryStatus.CANONICAL`)→`derive_memory_index_text`+embed→`build_memory_index_record`→`vector_index.upsert_memory_records` 직접 호출. ES leg 전무. `_build_memory_vector_index`(:57-77)가 CHROMA_HOST env로 Chroma/InMemory 결정.
- **ES lexical helper(전부 구현)**: memory — `build_memory_lexical_record`(`memory_lexical_index.py:48`)·`memory_lexical_text`(:59, = `derive_memory_index_text` projection)·`ElasticsearchMemoryIndexAdapter.index_memory_records`(:161)·`InMemoryMemoryLexicalIndexAdapter`(:84)·`connect_elasticsearch_memory_index`(:291, nori index lazy create + replicas 0). candidate — `build_candidate_lexical_record`(`candidate_lexical_index.py:62`)·`candidate_index_text`(`candidate_index.py:127`)·`ElasticsearchCandidateIndexAdapter.index_candidate_records`(`candidate_lexical_index.py:148`)·`InMemoryCandidateLexicalIndexAdapter`(:86)·`connect_elasticsearch_candidate_index`(:247).
- **candidate vector helper(전부 구현, b-2)**: `build_candidate_index_record`(`candidate_index.py:133`)·`InMemoryCandidateVectorIndexAdapter.upsert_candidate_records`(:73)·`ChromaCandidateVectorIndexAdapter`(`indexing/chroma.py`, worker `_build_candidate_adapter`가 사용).
- **list API**: `MemoryService.list_memories(project_id=)`(`memory/service.py:323`, 모든 상태 → canonical 필터 필요)·`AnalysisService.list_needs_review_candidates(project_id=)`(`analysis/service.py:467`, **needs_review만 반환 → 필터 불필요**).
- **worker는 composite drain만**: `_build_memory_adapter`(`index_sync_worker.py:121-143`)·`_build_candidate_adapter`(:199-221)는 ES 구성 시 named-sink composite(vector+lexical)로 entry-driven drain. backfill은 이 composite나 entry 기반 `MemoryLexicalIndexSyncAdapter`가 아닌 **list 기반 직접 `index_*_records`** 호출(vector backfill의 `upsert_memory_records` 직접 호출과 동일 자세).
- **candidate backfill 자체 부재(b-2 관찰 (a))**: candidate vector backfill 스크립트도 없다. 이 slice가 candidate lexical을 담으면 candidate vector도 함께 닫을지가 범위 결정(G2).

## 결정점 (G1~G4)

> 권고는 각 gate 첫 옵션에 "(추천)" 표시.

### G1 — memory ES lexical backfill 구현 형태
- **A(추천)**: 기존 `scripts/phase2b5_reindex_memory.py`에 ES leg 추가. ES 구성(`ELASTICSEARCH_URL`) 시 memory vector + memory lexical을 **같은 canonical 순회**에서 동시 backfill(worker `_build_memory_adapter` composite와 대칭). summary에 `lexical_backend`/`lexical_records_written` 추가. ES 미구성 시 lexical leg는 fake(InMemory) 또는 skip.
- B: 별도 memory lexical 전용 스크립트(`phase2b5_reindex_memory_lexical.py`).
- **근거**: memory의 vector+lexical은 같은 canonical 전수를 같은 projection(`derive_memory_index_text`)으로 같은 `list_memories` 순회로 backfill하므로 한 스크립트가 자연스럽다. worker도 memory adapter를 composite로 하나로 묶는다. B는 canonical 필터·순회·list_memories 호출을 중복.
- **계약**: internal 스크립트 — 새 SoT literal 없음.

### G2 — candidate backfill 범위
- **A(추천)**: candidate lexical + candidate vector를 함께 backfill. b-2 검증 관찰 (a)(candidate vector backfill 부재) + 이 slice의 candidate lexical을 한번에 닫는다. est_size small→medium.
- B: candidate lexical만. candidate vector backfill은 별도 후속(b-2 관찰 (a) 잔존).
- C: candidate backfill 전체 제외 — 이 slice는 memory ES만. candidate lexical/vector backfill 모두 별도 후속(HANDOFF Next Tasks #2 candidate backfill 추적중).
- **근거**: candidate는 vector+lexical이 같은 needs_review 전수를 같은 projection으로 backfill하므로 한 스크립트가 자연스럽다(worker `_build_candidate_adapter` composite 대칭). A가 b-2 관찰 (a)까지 닫아 accepted limitation을 완전 해소. 단, 이 slice의 본질(b-6 한계 #1 = ES-lexical backfill)에서 벗어나 candidate vector까지 포함하면 규모가 확장 — 오너가 small을 선호하면 B/C도 합리적. C는 candidate backfill을 Next Tasks #2(live smoke)와 함께 sandbox 밖으로 미룬다.
- **계약**: internal 스크립트 — 새 SoT literal 없음.

### G3 — candidate backfill 스크립트 구조 (G2≠C일 때)
- **A(추천)**: candidate는 신규 `scripts/phase2b5_reindex_candidate.py`로 memory와 **분리**. memory는 기존 `phase2b5_reindex_memory.py` 확장(G1=A).
- B: memory+candidate를 한 통합 스크립트로.
- **근거**: memory(`MemoryService.list_memories`, canonical 필터)와 candidate(`AnalysisService.list_needs_review_candidates`, needs_review)는 서로 다른 service/repo/상태 필터/list API를 쓰므로 분리가 자연스럽다. vector backfill도 memory만 있는 기존 패턴. B는 두 service를 한 스크립트에 억지로 묶어 결합도만 높인다.
- **계약**: internal 스크립트 — 새 SoT literal 없음. (AskUserQuestion에서 G2 옵션 A/B는 모두 "별도 스크립트"이므로 G3=A가 자동 확정되는 구조로 문의한다.)

### G4 — SoT 버전 bump
- **A(추천)**: 버전 bump(v1.6.58), **새 public literal 없음** — backfill 스크립트는 internal 운영 도구이고 계약 literal·public 표면 변경 없음. changelog에 accepted limitation #1 해소 명시.
- B: SoT changelog만(버전 bump 없음).
- **근거**: b-6 G6=A 선례(새 literal 없으면 bump만). 단, accepted limitation #1 해소는 계약급 기록(b-6 증분2가 명시한 한계를 닫으므로)이므로 **B(버전 bump 없음)는 부적절** — changelog에 한계 해소를 남기려면 버전 bump가 동반되어야 원장 단위가 선다. A 추천.
- **계약**: v1.6.58 changelog entry 1건(accepted limitation #1 해소).

## 한계 / 수용 사항 (오너 인지 필요)

1. **live backfill 실행은 sandbox 밖**: 코드+회귀는 sandbox 안(InMemory lexical adapter + fake/no embedding). 실 backfill(실 Mongo + real ES nori)은 기존 vector backfill과 동일 자세로 sandbox 밖(`phase2b5_reindex_memory.py` docstring이 "Live run is sandbox-external" 명시).
2. **commit-후-enqueue skew는 이 slice가 넓히지 않음**: backfill은 outbox를 우회한 일괄 재적재(D7 자세)이며, transaction 부재 skew는 vector backfill과 동일. CLAUDE.md §3 준수.
3. **candidate de-index forward-defense stub과 무관**: candidate는 needs_review 단일 상태라 backfill은 upsert-only. Phase 6 전이(confirmed/rejected) 시 도달하는 candidate de-index stub(`candidate_index.py:177-184`)과 backfill은 독립.

## 검증 계획

- **memory ES backfill 회귀**(`tests/test_phase2b5_reindex_memory_script.py` 확장): InMemory lexical adapter(또는 fake ES client)로 patch, (a) ES 구성 시 canonical memory가 lexical에 적재·superseded 제외·project 격리, (b) ES 미구성 시 동작(no-op 또는 fake), (c) summary `lexical_*` 필드. mutation 양방향(canonical-only 필터 제거 시 재실패).
- **candidate backfill 회귀**(G2≠C, 신규 `tests/test_phase2b5_reindex_candidate_script.py`): InMemory vector+lexical adapter, needs_review만 적재·project 격리·summary. mutation 양방향.
- **전체 스위트**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`(현재 703 passed/45 skipped 기준 +N).
- **SoT 정합**: v1.6.58 changelog에 accepted limitation #1 해소 명시.

## 제외 (후속)

- 실 backfill live 실행(sandbox 밖) + live smoke(ephemeral ES index create→backfill→검색→삭제).
- (b-4) hybrid 튜닝·(c)~(e)·Phase 6 후보 전이 — HANDOFF Next Tasks #1 잔존.
- commit-후-enqueue skew의 transaction/enqueue-retry 처리 — 한계 #2, 별도.

## 오너에게 묻는 질문

1. **G1**: memory ES backfill을 기존 `phase2b5_reindex_memory.py` 확장(A), 별도 스크립트(B)?
2. **G2**: candidate backfill은 별도 스크립트로 lexical+vector 함께(A), lexical만(B), 제외(C)? (A/B 모두 G3=A 분리 스크립트 전제)
3. **G4**: SoT 버전 bump(v1.6.58) + 새 literal 없음(A), changelog만 bump 없음(B)?
