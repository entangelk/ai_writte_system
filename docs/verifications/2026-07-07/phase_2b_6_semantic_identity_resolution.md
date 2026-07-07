# Verification — Phase 2B.6 event/open_question 의미적 identity resolution

## Subject metadata

- **Date**: 2026-07-07
- **Requester**: entangelk (오너) — “다음작업 검증해줘. Phase 2B.6을 완결하고 main에 커밋했습니다 (5ae6e46).”
- **Verifier**: Claude (독립 검증, 구현 작업 미관여)
- **Target slice / artifact**: Phase 2B.6 — `services/application/app/analysis/compare.py`(`SemanticMemoryMatcher` Protocol·`semantic_matcher` seam·`_find_matches` scope-None 분기), `analysis/semantic_matcher.py`(신규 `EmbeddingSemanticMatcher`), `indexing/memory_index.py`(`query_similar` Protocol + fake cosine), `indexing/chroma.py`(`ChromaMemoryVectorIndexAdapter.query_similar` + `_memory_records_from_query`), `main.py`(`_build_semantic_matcher` env-gate 배선), 회귀 `test_analysis_semantic_matcher.py`(8)·`test_chroma_memory_adapter.py`(+2).
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.47(version-table 행 + §Phase 2B prose 2행 갱신).
  - `docs/plans/02b-6-semantic-identity-resolution-decisions.md`(Resolved, D1~D8 + Owner decisions D1=A·D4=A).
  - 하위 계약: v1.6.42(2B.3 `_find_matches`/scope key/create-judge-conflict), v1.6.45/v1.6.46(2B.5 memory_vectors 쓰기 경로 + choke point), v1.6.39 D2=B(threshold off-기본 선례).
- **Source of work being verified**: commit **5ae6e46**(HEAD, `main`).

## Scope

1. **계약**: D1=A(seam = compare `_find_matches`, PriorMemoryBackend 아님)·D4=A(threshold 주입값·기본 off)·D5=A(character 결정적 유지)·D6=A(top-1)·D3(쓰기와 동일 projection/embedding)·D8(read-after-write eventual consistency 수용) + HANDOFF/2B.2 seam-위치 오기 정정.
2. **구현 코드**: `compare.py`(seam), `semantic_matcher.py`, `memory_index.py`(query_similar fake), `chroma.py`(query_similar real), `main.py`(env-gate 배선).
3. **회귀**: `test_analysis_semantic_matcher.py`(8)·`test_chroma_memory_adapter.py`(+2). 기존 compare 회귀 off-기본 무변 확인.
4. **공개 표면/envelope**: `_find_matches` 반환(`tuple[MemoryEntry,...]`), matcher 반환(top-1 or ()), wiring env gate.
5. **전체 스위트**(infra-free 단위; 실 embedding 캘리브레이션/live는 sandbox 밖 후속).

## Methodology

scoped reading(SoT v1.6.47 + 브리프 D1~D8 + 하위 v1.6.42 `_find_matches`/v1.6.45 projection)로 boundary matrix 작성, 분기→회귀 추적. 1차 소스 재유도 + 독립 변이(mutant)로 non-vacuity 증명. character 미도달(D5=A)은 `scope is None` gate 구조로 확인.

```bash
# (1) 위생 + 컴파일
git status --porcelain && git log --oneline -1   # clean / 5ae6e46
python3 -m py_compile services/application/app/analysis/compare.py \
  services/application/app/analysis/semantic_matcher.py \
  services/application/app/indexing/memory_index.py services/application/app/indexing/chroma.py \
  services/application/app/main.py tests/test_analysis_semantic_matcher.py

# (2) focused + 전체 스위트(mongo env 제외)
python3 -m unittest tests.test_analysis_semantic_matcher tests.test_chroma_memory_adapter -v
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 608 passed / 45 skipped

# (3) non-vacuity 변이(threshold guard·memory_type filter 각각 무력화 → over-strict 회귀 재실패)
PYTHONPATH=. python3 - <<'PY'
import unittest
from services.application.app.analysis import semantic_matcher as sm
from services.application.app.indexing import memory_index as mi
# MUT1: threshold guard neutered
orig=sm.EmbeddingSemanticMatcher.match
def m1(self,*,project_id,job_id,candidate):
    t=sm.derive_memory_index_text(candidate.candidate_type,candidate.payload); qv=self._embeddings.embed(t)
    for r in self._vector_search.query_similar(project_id=project_id,memory_type=candidate.candidate_type.value,vector=qv,limit=self._limit):
        e=self._resolve(project_id,r.memory_id)
        if e is None or e.status is not sm.MemoryStatus.CANONICAL or e.analysis_job_id==job_id: continue
        return (e,)
    return ()
sm.EmbeddingSemanticMatcher.match=m1
r1=unittest.TextTestRunner(verbosity=0).run(unittest.TestLoader().loadTestsFromName("tests.test_analysis_semantic_matcher.SemanticMatcherTest.test_dissimilar_event_below_threshold_no_match"))
print("MUT1", "RE-FAILS" if not r1.wasSuccessful() else "passes"); sm.EmbeddingSemanticMatcher.match=orig
# MUT2: memory_type filter neutered in fake query_similar
oqs=mi.InMemoryMemoryVectorIndexAdapter.query_similar
def m2(self,*,project_id,memory_type,vector,limit):
    if limit<1: raise ValueError
    return tuple(sorted([r for r in self.records.values() if r.project_id==project_id],key=lambda r:(-mi._cosine_similarity(vector,r.vector),r.id))[:limit])
mi.InMemoryMemoryVectorIndexAdapter.query_similar=m2
r2=unittest.TextTestRunner(verbosity=0).run(unittest.TestLoader().loadTestsFromName("tests.test_analysis_semantic_matcher.SemanticMatcherTest.test_memory_type_scoped"))
print("MUT2", "RE-FAILS" if not r2.wasSuccessful() else "passes")
PY
```

## Findings

### 1. seam 위치 정정(D1=A) — 핵심 주장 1차 소스로 정확

`compare.py:_find_matches`의 `scope is None` 분기가 곧 event/open_question의 always-create 지점이다. 본 slice는 여기에 `SemanticMemoryMatcher` seam을 끼워넣었다:

```python
if scope is None:
    if self._semantic_matcher is None:
        return ()                      # off → 종전 always-create (무변)
    return self._semantic_matcher.match(project_id=..., job_id=..., candidate=candidate)
```

- **D1=A 정확**: HANDOFF/2B.2 “PriorMemoryBackend 교체”는 seam 오기였고, 실제 누적 지점이 compare `_find_matches`임을 코드가 입증. PriorMemoryBackend(2B.2 coarse 패키징)는 본 slice 무관.
- **D5=A 구조적 보장**: character는 `derive_scope`가 항상 `MemoryScope`를 내므로 `scope is None` gate에 도달 불가 → matcher 호출 없음. character 결정적 name-key 경로 완전 무변.

### 2. off-by-default 안전성(D4=A)

`AnalysisCompareService.__init__`의 `semantic_matcher=None`(기본). matcher None 시 `_find_matches`는 `()` 반환 → event/open_question always-create **종전과 동일**. `_default_compare_service`도 env 없으면 `_build_semantic_matcher`가 `None` 반환. 따라서 기존 compare 회귀는 matcher 주입 없이 실행돼 **무변**(608/45에 기존 compare 회귀 전수 포함, 파손 없음).

### 3. boundary matrix — 빈 셀 없음

| # | 계약 분기 | 코드 | 회귀 | 상태 |
|---|---|---|---|---|
| 1 | above-threshold + 동 type + canonical + 비-self → 매칭(top-1) | `semantic_matcher.py:74-88` | `test_similar_event_matches_prior_canonical` | LOCKED |
| 2 | **below-threshold → 무매칭**(over-strict) | `:75`(< threshold continue) | `test_dissimilar_event_below_threshold_no_match` | LOCKED(mutant) |
| 3 | top-1(첫 eligible만 반환, 다중을 conflict로 안 봄, D6=A) | `:88 return (entry,)` | `test_top_1_only` | LOCKED |
| 4 | **memory_type scope**(다른 type 안 섞임, over-strict) | `memory_index.py` fake filter·`chroma.py` $and | `test_memory_type_scoped`·`test_query_similar_ranks_and_scopes_by_memory_type` | LOCKED(mutant) |
| 5 | self-exclusion(같은 job 승격분 제외, D6) | `:85`(analysis_job_id==job_id continue) | `test_self_exclusion` | LOCKED |
| 6 | superseded/stale index record skip(canonical 필터) | `:83`(status != CANONICAL continue) | `test_superseded_index_record_skipped` | LOCKED |
| 7 | 매칭 → 기존 judge flow 관통(update/no_change/...) | `compare._find_matches` 반환 → 0/1 로직 | `test_semantic_match_flows_through_judge` | LOCKED |
| 8 | **matcher off → always-create**(safety) | `compare.py:193-194` | `test_no_matcher_keeps_event_always_create` | LOCKED |
| 9 | Chroma query 랭킹 + scope | `chroma.py:query_similar`($and, n_results) | `test_query_similar_ranks_and_scopes_by_memory_type` | LOCKED |
| 10 | limit<1 ValueError | fake/real 양쪽 | `test_query_similar_rejects_nonpositive_limit` | LOCKED |

모든 should-fire / should-NOT-fire 분기 추적 가능, over-strict(below-threshold·memory_type) 양방향 포함.

### 4. non-vacuity 변이(mutant) — 독립 재실증

- **MUT1(threshold guard 무력화)**: `match`에서 `< threshold continue` 제거 → `test_dissimilar_event_below_threshold_no_match`가 m1에 오탐 매칭하며 **재실패**. load-bearing.
- **MUT2(memory_type filter 무력화)**: fake `query_similar`에서 memory_type 필터 제거 → `test_memory_type_scoped`가 다른 type q1에 매칭하며 **재실패**. load-bearing.

작업 주장(threshold·memory_type guard mutation 재실증) 정확.

### 5. projection·embedding 일치(D3)

`EmbeddingSemanticMatcher.match`가 `derive_memory_index_text(candidate.candidate_type, candidate.payload)`(2B.5 쓰기와 **동일** projection) → `embeddings.embed(text)`로 query vector 생성. 쓰기 경로(worker)와 읽기 경로(compare)가 같은 projection·같은 `_build_embedding_provider`(EMBEDDING_SERVICE_URL→real / else fake)를 사용 → 코드 수준에서 동일 모델 보장(운영 env 일치 가정 시).

### 6. query_similar 구현(fake + Chroma)

- fake(`memory_index.py`): `limit<1` ValueError, `project_id AND memory_type` 필터, cosine 내림차순(+id tiebreak), top-limit. source_block `query_similar` 미러 + memory_type 추가.
- Chroma(`chroma.py`): `collection.query(query_embeddings=[vector], n_results=limit, where={$and:[project_id, memory_type]}, include=embeddings+metadatas)`. `_memory_records_from_query`가 nested-query 구조(ids_by_query[0] 등) + None guard 처리(v1.6.35/37 numpy-like 패턴 일관).
- canonical-only는 index 불변식(2B.5 self-heal)에 의존 + matcher의 `status != CANONICAL` 2차 방어(이중).

### 7. wiring(D8) — env 이중 gate

`_build_semantic_matcher`(`main.py:402-`)가 `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` **AND** `CHROMA_HOST` 둘 다 있을 때만 matcher 생성. CHROMA_HOST 필수는 정당 — Application 프로세스의 in-memory fake는 worker와 분리돼 memory 벡터가 없으므로, 실 Chroma(워커가 drain한 `memory_vectors`)만이 의미 있는 검색 대상. 둘 중 하나라도 없으면 None(off). `_default_compare_service`는 항상 `semantic_matcher=_build_semantic_matcher(memory)`를 전달(None이면 off).

## Issues / Risks

- **[비차단, 운영 footgun] EMBEDDING_SERVICE_URL 미검증**: wiring이 threshold + CHROMA_HOST만 검사하고 EMBEDDING_SERVICE_URL은 검사하지 않는다. 운영자가 threshold + CHROMA_HOST만 설정하고 EMBEDDING_SERVICE_URL을 빼면, query vector가 fake provider(차원 불일치)로 나와 실제 Chroma(1024-dim) query에서 **차원 오류로 loud 실패**(silent corruption 아님 — Chroma가 dim 검증). D4 off-기본이 보호하므로 결함은 아니나, semantic 활성화 시 EMBEDDING_SERVICE_URL도 필요함을 runbook/SoT에 명시하거나 wiring에 guard 추가 권고.
- **[비차단] n_results=limit + superseded leak**: Chroma query가 status 필터 없이 n_results=limit. index가 canonical-only(2B.5 불변식)이므로 정상이나, stale superseded record가 slot을 소진할 이론적 여지. matcher의 canonical 필터가 정확성 보장, 기본 limit=5가 여유. non-blocking.
- **[비차단, 수용 경계 D8] read-after-write eventual consistency**: 방금 promote된 memory는 worker drain 전이라 index에 없어 매칭 누락 가능. self-exclusion이 같은 job은 흡수, 타-job 최근 promote는 다음 compare/backfill까지 미검색. 브리프 D8 명시 수용 경계.
- **[범위 밖, 정상] 실 embedding threshold 캘리브레이션**: off-기본이라 seam+query 인프라만 세웠고, 실 매칭 발화는 실 embedding+데이터 fixture 캘리브레이션(sandbox 밖) 후. 본 slice 계약/단위 범위 안.

## Verdict

**합격(pass).**

이유:
- D1=A seam 정정이 1차 소스로 정확(`_find_matches` scope-None 분기). character(D5=A)는 구조적 gate로 미도달.
- D4=A off-기본: matcher None 시 `()` 반환 → 기존 compare always-create 무변, 기존 회귀 보존.
- boundary matrix 10 분기 전부 회귀로 잠김(빈 셀 없음). over-strict(below-threshold·memory_type) 양방향 포함.
- non-vacuity: threshold guard·memory_type filter 각각 무력화 시 over-strict 회귀 재실패(mutant 독립 증명).
- projection·embedding 쓰기/읽기 일치(D3), query_similar fake/real 양 구현, env 이중 gate 배선 정확.
- 전체 스위트 **608 passed / 45 skipped** 재현, `py_compile` OK, tree clean, HEAD `5ae6e46` on main.

차단 조건 없음. 잔여는 전부 비차단(EMBEDDING_SERVICE_URL runbook·n_results 여유·read-after-write 수용 경계·sandbox 밖 캘리브레이션).

## Outstanding items

- **[비차단 권고] semantic 활성화 runbook**: threshold + CHROMA_HOST 설정 시 EMBEDDING_SERVICE_URL도 필수임을 SoT/runbook에 명시(또는 wiring guard). loud 실패라 치명적이지 않으나 운영 혼란 방지.
- **[sandbox 밖, 후속]** similarity threshold 실 캘리브레이션(실 embedding + 데이터 fixture/live) — off-기본 상태에서 seam은 완료.
- **[후속 slice]** character 별칭/동명이인 semantic 보강(2B.3 D2=A merge/split review 확장), conflict/merge/split review queue 영속화, ⑤ Writing canonical 포함.

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
git status --porcelain && git log --oneline -1   # clean / 5ae6e46
python3 -m py_compile services/application/app/analysis/compare.py \
  services/application/app/analysis/semantic_matcher.py \
  services/application/app/indexing/memory_index.py services/application/app/indexing/chroma.py \
  services/application/app/main.py
python3 -m unittest tests.test_analysis_semantic_matcher tests.test_chroma_memory_adapter -v
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 기대: 608 passed / 45 skipped
# (MUT1/MUT2 변이 스크립트는 Methodology 블록 참조 — 둘 다 RE-FAILS)
```
