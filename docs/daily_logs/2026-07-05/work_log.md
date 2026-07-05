# Work Log — 2026-07-05

## Goals

- HANDOFF와 최신 work log를 읽고 다음 작업을 진행한다.
- HANDOFF Next Tasks 1이 "오너 우선순위 결정 필요"로 막혀 있으므로 다음 slice 방향을 오너에게 확인한다.
- 승인된 방향(공유 in-process vector index)을 브리프로 확정한 뒤 구현·검증한다.

## Completed work

### 다음 slice 방향 오너 결정

- HANDOFF Next Tasks 1의 후보 4종(A 공유 in-process vector index / B real Chroma·ES / C prior-memory purpose / D tool-call planner 전환)을 제시했다.
- 오너는 **A(공유 in-process vector index)**를 선택했다. C는 오너가 뒤로 미룬 항목, D는 상류 wire 계약 미해소로 차단이라 근시일 후보에서 제외됐다.
- A는 "fake vector adapter는 request마다 throwaway·비지속" 특성을 프로세스 수명 공유로 바꾸는 비persistence 계약 변경이라 착수 전 브리프가 필요했다.

### 공유 vector index 착수 브리프 (docs/plans/04-shared-vector-index-decisions.md)

- 신규 브리프를 작성하고 `Approved (2026-07-05)`로 확정했다.
- rebuild가 채운 파생 index를 같은 프로세스 context search가 실제로 조회하도록 `create_app`이 단일 in-process vector index를 공유하는 것이 목적이다.
- 오너 결정 2건: (1) 방향은 A 채택, (2) rebuild HTTP summary는 **기존 계약 유지(snapshot scope)**. 공유 index가 여러 snapshot rebuild를 누적하더라도 summary count는 해당 rebuild의 `snapshot_id`로 scope해 per-rebuild 의미(v1.6.22/v1.6.23 "누적 없음")를 그대로 둔다.

### 공유 in-process vector index 구현 (SoT v1.6.35)

- 변경 파일: `services/application/app/main.py`, `services/application/app/indexing/service.py`, `tests/test_context_search_shared_index.py`(신규), `docs/plans/04-shared-vector-index-decisions.md`(신규), `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-05/work_log.md`.
- `create_app`이 단일 `InMemoryVectorIndexAdapter`(+ `DeterministicFakeEmbeddingProvider`)를 소유한다. `LLM_GATEWAY_BASE_URL` 유무와 무관하게 항상 생성되며, 테스트 주입용 `vector_index` param을 열었다.
- rebuild HTTP endpoint(`_rebuild_source_block_index_payload`)가 이 공유 adapter/embeddings를 `rebuild_source_block_index_summary(...)`에 넘겨 여기에 write한다.
- `_default_context_search_service`가 공유 `vector_index`/`embeddings`를 받아 context search의 `vector_search`(query)와 `indexing_service`(stale guard)를 같은 인스턴스로 wiring한다 → 같은 프로세스 rebuild 후 context search가 실제 vector hit을 서빙한다.
- `rebuild_source_block_index_summary`에 optional `vector_index`/`embeddings` 인자를 추가했다. 미제공 시 종전대로 throwaway adapter(CLI script 비지속 유지). summary count(`records_indexed`/`records_query_visible`/`records_archived`)는 항상 해당 rebuild의 `snapshot_id`로 필터해 per-rebuild 의미를 유지한다 — throwaway 경로에서는 adapter가 이미 해당 snapshot만 담으므로 값이 동일하고, 공유 경로에서도 같은 값을 낸다.
- staleness 안전성: 공유 adapter는 fake archive mutation을 받지 않지만 context search가 hit마다 `validate_source_block_record()` stale guard + SOT 재조회를 거치므로 rebuild 후 archive/drift record는 query-time에 제외된다(Slice 4.1 방어선 재사용).

## Issues found

- 없음(신규 구현). rebuild summary가 v1.6.23에서 "누적 없음"으로 잠긴 계약을 공유 index 누적이 깨뜨릴 위험이 있었으나, snapshot scope로 봉쇄했다.

## Decisions

- 방향은 A(공유 in-process vector index). B/C/D는 후속(사유: C 후순위, D 상류 차단).
- rebuild summary는 snapshot scope로 per-rebuild 계약을 보존한다(오너 결정). 이유: v1.6.22/v1.6.23 관측 계약과 Slice 4.3가 잠근 "누적 없음" 회귀를 불변으로 두고 계약 변경 blast radius를 최소화하기 위함. 트레이드오프: summary가 공유 index의 전체 상태를 드러내지 않지만, 그것은 이 slice의 목적이 아니다.

## Verification

- 자체 회귀: `python3 -m py_compile services/application/app/main.py services/application/app/indexing/service.py tests/test_context_search_shared_index.py` 통과.
- `python3 -m unittest tests.test_context_search_shared_index -v` 3개 통과: (1) rebuild HTTP endpoint가 채운 공유 index를 같은 프로세스 context search가 조회해 rebuild 전 empty → rebuild 후 non-empty micro_evidence(sot_reloaded=True), (2) 두 번째 큰 snapshot을 누적한 뒤에도 각 rebuild summary count가 snapshot scope per-rebuild 값을 유지(누적 total보다 작음), (3) rebuild 후 draft archive 시 hit이 stale guard로 제외.
- Mutation 실증(이 slice가 새로 넣은 guard마다): (A) rebuild payload에서 공유 `vector_index`/`embeddings` 주입을 제거하면 (1)/(3)이 재실패(`micro_evidence == []`). (B) `rebuild_source_block_index_summary`의 snapshot-scope 필터(`if record.snapshot_id == snapshot_id`)를 제거하면 (2)가 재실패(`records_indexed` 6 != 15, A+B 누적) → per-rebuild 계약 guard가 vacuous하지 않음을 실증. 복원은 `diff -q`로 byte-identical 확인.
- 관련 묶음 `python3 -m unittest tests.test_context_search_shared_index tests.test_context_search_api tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script tests.test_indexing_phase3a tests.test_context_search -v` 117개 통과.
- 전체 `python3 -m unittest discover tests` Ran 473 OK(skipped=44). `python3 -m pytest -q` 429 passed / 44 skipped. `git diff --check` 통과.

### 독립 검증 후속 보강 (2026-07-05)

- 독립 검증 판정은 **합격**(`docs/verifications/2026-07-05/shared_vector_index_slice.md`), 조건 사유 없음. 경계 매트릭스 전 셀 lock, 빈 셸 없음.
- 검증 AI 비차단 관찰 2건을 보강했다:
  1. worker(자체) mutation 증명이 shared-wiring 제거만 다루고 이 slice가 새로 넣은 snapshot-scope 필터의 무력화 mutation을 빠뜨렸다. 위 "Mutation 실증 (B)"를 직접 돌려 `records_indexed` 6 != 15 재실패를 확인·기록했다(계약 guard non-vacuous 재입증). boundary 자체는 회귀로 이미 lock되어 있어 차단 사유가 아니었다.
  2. `tests/test_context_search_shared_index.py`의 httpx driver helper `TestClient`가 pytest `Test*` 수집 규칙에 걸려 `PytestCollectionWarning`을 냈다. `__test__ = False`를 달아 이 파일 경고를 제거했다(pytest warnings 3→2, 남은 2건은 기존 `test_context_search_api.py` 등 pre-existing이라 surgical 범위 밖). 기능 영향 없음.

## Next steps

- deployed(compose stack) smoke로 실제 12B planner + 공유 index 관통 시 vector need가 실제 hit을 내는지 확인(sandbox 밖 승인 네트워크 실행 필요). 현재 `scripts/phase4_context_search_deployed_smoke.py`는 rebuild를 호출하지 않으므로, rebuild → context-search 순서를 관통하려면 스크립트 확장 또는 수동 2-step 실행이 필요하다.
- real ChromaDB persistent vector adapter / ES lexical 경로(§8, 착수 전 브리프)는 계속 후속.
- prior-memory(analysis 비교) purpose §8 C 완성(Phase 2B 착수 브리프)도 후속.
