# 검증 기록 — (b-2) candidate lexical/vector retrieval (SoT v1.6.54 + v1.6.55)

## Subject metadata

- **날짜**: 2026-07-09
- **요청자**: 오너 ("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?" → 이어 "보강할 부분 보강해주고 커밋까지 진행해줘")
- **검증자**: Claude(독립 감사, 작업자 구현 비관여)
- **대상 slice/artifact**: (b-2) `needs_review` candidate 의 색인 파이프라인(v1.6.54) + vector/lexical/hybrid(RRF) retrieval(v1.6.55). 결정 브리프 `docs/plans/04-writing-candidate-retrieval-decisions.md`(Resolved).
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.55(버전로그 표 v1.6.54/v1.6.55 행이 정본 변경 기록) + 본문 §Phase 3(~398)·§Phase 4 ⑤§5B(~411).
- **작업 소스**: working tree, uncommitted(커밋 전). HEAD = `082d698`(v1.6.53).
- **검증 방법**: 1차 독립 리드(코드/테스트/계약 직독 + mutation 양방향 재실증 + 전 스위트 재실행) + 9-에이전트 대항 워크플로우(8차원 검증 + completeness critic, mutation testing 포함).

## Scope

1. **계약 리터럴**: `IndexRecordKind.CANDIDATE`·`IndexSyncEvent.CANDIDATE_UPSERTED`·`CandidateIndexRecord` 신설; `candidate_vectors`/`candidate_lexical` 물리 분리(G1).
2. **색인 파이프라인(증분1)**: enqueue choke point(`record_candidate(s)` → 신규만 enqueue), outbox dedup, worker composite drain(vector+lexical), self-heal delete 분기(forward-defense).
3. **어댑터**: `CandidateVectorIndexAdapter`(InMemory·Chroma), `CandidateLexicalIndexAdapter`(InMemory·ES nori, status:needs_review 필터), `connect_elasticsearch_candidate_index`.
4. **retriever(증분2)**: `Vector`/`Lexical`/`HybridCandidateMemoryRetriever`(RRF k=60, id dedup) — canonical과 동형, `get_candidate` 권위 재유도→needs_review-only, `.retrieve()` seam·반환 타입 불변.
5. **배선**: `main.py` env 스위치(canonical 동일), `scripts/index_sync_worker.py` `_build_candidate_adapter`.
6. **회귀**: `tests/test_candidate_index.py`·`tests/test_context_search_candidate_retrieval.py`·`tests/test_index_sync_worker_script.py`(BuildCandidateAdapterTest) + 선행 `tests/test_context_search_candidate_memory.py`(v1.6.50 seam/Gate/§62).
7. **계약 일관성**: 버전로그 표 ↔ 본문 prose ↔ 구현 리터럴.

## Methodology

- 계약 스코프를 먼저 좁혀 정본 경계 매트릭스 구성(브리프 G0~G6, 버전로그 행, 본문 §3/§4). should-fire/should-NOT-fire 분기 전수 매핑 → 테스트 함수 추적(UNTRACED 셀 = 발견).
- 코드 ↔ 계약 리터럴 교차검증(값 그대로, paraphrase 불허).
- **mutation 양방향 재실증**(직접 실행, Edit 기반 — `git checkout` 미사용[작업자가 겪은 실수 회피]):
  - A) vector retriever `needs_review` 필터 제거 → `test_stale_records_are_dropped` 재실패(transitioned "old" 누출).
  - B) ES 필터 `needs_review`→`canonical` → `test_search_filters_project_and_needs_review` 재실패.
  - C) lexical retriever 필터 제거(보강 후) → `test_transitioned_candidate_is_dropped` 재실패.
  - D) G1 candidate collection default `candidate_vectors`→`memory_vectors`(보강 후) → `BuildCandidateAdapterTest` 재실패.
  - E) batch `_enqueue_candidate_reindex` early-return(보강 후) → `test_batch_record_enqueues_only_new_candidates` 재실패(동시에 N=1 singular 테스트는 여전히 통과 = N=1이 못 잡는 버그 입증).
- 전 스위트 재실행: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`.
- 9-에이전트 워크플로우: 8차원(enqueue/drain/es-chroma/composite-worker/retrievers/seam-gate/contract-consistency/wiring) 병행 대항 검증 + completeness critic(교차 검증·누락 탐지, mutation testing으로 빈 셀 입증).

## Findings

### 1. 계약 리터럴·물리 분리 — PASS
`IndexRecordKind.CANDIDATE="candidate"`([models.py:15](../../../services/application/app/indexing/models.py#L15)), `IndexSyncEvent.CANDIDATE_UPSERTED="candidate_upserted"`([models.py:33](../../../services/application/app/indexing/models.py#L33)), `CandidateIndexRecord`([models.py:160](../../../services/application/app/indexing/models.py#L160)), `CANDIDATE_VECTOR_COLLECTION="candidate_vectors"`([candidate_index.py:38](../../../services/application/app/indexing/candidate_index.py#L38)), `CANDIDATE_LEXICAL_INDEX="candidate_lexical"`([candidate_lexical_index.py:30](../../../services/application/app/indexing/candidate_lexical_index.py#L30)). 버전로그 기재와 1:1 일치. canonical `memory_vectors`/`memory_lexical`과 물리 분리(G1).

### 2. canonical 대칭 — PASS
- retriever 구조 동형: per candidate_type query → 단일 풀 cosine merge([service.py:226 `_merge_hits`](../../../services/application/app/context_search/service.py#L226) = canonical `_merge_hits`와 동일 key).
- RRF 공식 동일: `1/(rrf_k + rank + 1)`(rank 0-based enumerate → 1-based), `DEFAULT_RRF_K=60`([service.py:276](../../../services/application/app/context_search/service.py#L276)) 단일 정의, canonical·candidate 동일 사용.
- 권위 재유도 동등: canonical은 inline try/except, candidate는 `_resolve_needs_review` 헬퍼(동작 동등).
- env 스위치 구조 동일(`_build_candidate_memory_retriever` vs `_build_canonical_memory_retriever`).

### 3. 회귀 mutation 양방향 — PASS(재실증)
A·Bmutation 직접 재실증(위 방법론). 둘 다 가드 존재 확인.

### 4. 전 스위트 — PASS
`682 → 689 passed / 45 skipped`(보강 +7). `git diff --check` clean.

### 5. 빈 경계 셀(대항 워크플로우 발견 → 전부 보강 폐쇄)
- **#1 worker `_build_candidate_adapter` 회귀 부재**(BLOCKING, [index_sync_worker.py:136](../../../scripts/index_sync_worker.py#L136)): canonical `_build_memory_adapter`는 `BuildMemoryAdapterTest`로 잠금, candidate는 무회귀. → `BuildCandidateAdapterTest` 3분기 추가 + G1 collection mutation(D) 재실증.
- **#2 composite sink failure 전파 미회귀**(UNTRACED should/should-NOT fire, [candidate_index.py:198](../../../services/application/app/indexing/candidate_index.py#L198)): docstring "sink raises → entry fails"가 무회귀. → `test_sink_failure_propagates_not_swallowed` 추가.
- **#3 lexical retriever needs_review 필터 미회귀**(BLOCKING, [service.py:472](../../../services/application/app/context_search/service.py#L472)): vector는 transitioned 격리 잠금, lexical은 ghost(not-found)만. → `test_transitioned_candidate_is_dropped` 추가 + mutation(C) 재실증.
- **#4 batch `record_candidates` enqueue 미회귀**(BLOCKING, [analysis/service.py:417](../../../services/application/app/analysis/service.py#L417)): 단수 위임(service.py:338)하지만 기존 테스트 N=1만 → production runner.py:151 배치 iteration 무회귀. **감사가 mutation testing(MUT-A wrong-collection·MUT-C early-return)으로 "batch를 깨도 suite green"임을 증명**. → `test_batch_record_enqueues_only_new_candidates` 추가 + early-return mutation(E) 재실증(N=1은 못 잡음을 입증).

### 6. 문서 정합(대항 워크플로우 발견 → 전부 보강 폐쇄)
- **SoT §Phase 3:398**: "ES analyzer, analysis candidate indexing, actual Elasticsearch mutation, `analysis_completed` sync wiring은 미확정" 중 3항(v1.6.52/53/54 구현)이 stale. → "`analysis_completed` sync wiring만 미확정"으로 정정.
- **SoT §5B:411**: "candidate lexical/vector는 색인 파이프라인 선행 후속"이 v1.6.54/55 실현으로 stale(버전로그는 DONE). v1.6.48/50/51/52/53 매-slice clause 관례 누락. → v1.6.54/55 clause 추가.
- **`CandidateMemoryRetriever` Protocol docstring([service.py:328](../../../services/application/app/context_search/service.py#L328))**: "Mongo-direct now; a later vector/search-engine layer…" stale. → 갱신.

## Issues / Risks

- **차단 발견 0건(커밋 시점)**: 위 4건의 빈 셀 + 3건의 문서 정합은 검증 중 발견 즉시 보강·폐쇄(회귀 +7, mutation 재실증). 커밋되는 slice에는 빈 셀이 없다.
- **비차단 관찰(추적유지, 미조치)**:
  - candidate backfill 스크립리 부재: commit-후-enqueue orphan의 수렴 수단이 canonical(`phase2b5_reindex_memory.py`)과 달리 없으나, HANDOFF Next Tasks #2가 candidate backfill을 이미 후속으로 추적중(b-2 범위 밖).
  - `connect_elasticsearch_candidate_index` 별도 회귀 부재: nori·replicas:0 설정은 canonical `connect_` 테스트가 공유 상수(`ELASTICSEARCH_CANDIDATE_SETTINGS = ELASTICSEARCH_MEMORY_SETTINGS`)로 커버, candidate 매핑만 미커버(저값).
  - worker 4번째 env 조합(CHROMA+ES → `chroma+elasticsearch`) 미회귀: composite 경로는 fake-vector로 커버, chroma-in-composite는 vector_index 타입만 차이(저값).
  - `main.py` retriever builder env 스위치·`IndexSyncWorkerScriptTest` fake dict `candidate_backend` 누락: 둘 다 canonical과 대칭인 wiring-level 미회귀(canonical도 동일; b-2 비관여 영역 포함).
  - §62 권위필드 배제(version_id/content_hash/snapshot_id inert on produced item): 코드 정합, `test_context_search_candidate_memory.py`가 `constraints==()`/`do_not_use==()`로 잠금(b-2가 item 생성 안 바꿔 유효).

## Verdict

**합격(PASS)** — 작업자 구현의 핵심 계약(리터럴·물리 분리·canonical 대칭·권위 재유도·mutation 양방향·seam 불변)은 전수 재실증됐고, 대항 워크플로우가 발견한 빈 경계 셀 4건 + 문서 정합 3건은 커밋 전 전부 보강·폐쇄됐다. load-bearing 이유: (1) 회귀가 boundary matrix의 빈 셀 없이 양방향을 잠근다, (2) 버전로그 표 ↔ 본문 ↔ 코드 리터럴이 일치한다, (3) 전 스위트 689 passed.

주: 작업자 인계 상태(보강 전)만 보면 #1/#3/#4 빈 셀 3건이 "조건부 합격" 사유였으나(회귀는 green이나 계약이 요구하는 분기 lock 부재), 보강으로 실제 lock을 채워 합격으로 승격됐다.

## Outstanding items

- **커밋 대기**: 본 보강(회귀 +7·문서) 포함 2커밋 분할 예정(G0=A): 증분1(v1.6.54 색인 파이프라인, +24 회귀) → 증분2(v1.6.55 retriever + 전체 b-2 문서, +11 회귀). `main.py`만 양 증분 hunk 분할.
- **sandbox 밖 후속**: 실 Chroma/ES live 관통(`record_candidate`→`CANDIDATE_UPSERTED`→worker composite drain→실 `candidate_vectors`/`candidate_lexical`→hybrid retriever 서빙); candidate backfill 스크립트; candidate hybrid 튜닝(b-4와 합류).
- **비차단 관찰** 5건은 위 Issues/Risks에 기재(별도 slice 또는 추적 부채).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 전 스위트
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 689 passed / 45 skipped
# b-2 회귀만
python3 -m pytest -q tests/test_candidate_index.py tests/test_context_search_candidate_retrieval.py tests/test_index_sync_worker_script.py::BuildCandidateAdapterTest
# mutation 재실증 예(lexical 필터 제거 → 보강 테스트 재실패)
python3 -c "import pathlib,subprocess; p=pathlib.Path('services/application/app/context_search/service.py'); s=p.read_text(); p.write_text(s.replace('        if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:\n            return None\n        return candidate\n','        return candidate\n',1)); print(subprocess.run(['python3','-m','pytest','-q','tests/test_context_search_candidate_retrieval.py::LexicalRetrieverTest::test_transitioned_candidate_is_dropped'],capture_output=True,text=True).stdout[-300:]); p.write_text(s)"
```
