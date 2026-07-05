# Work Log — 2026-07-05

## Goals

- HANDOFF와 최신 work log를 읽고 다음 작업을 진행한다.
- HANDOFF Next Tasks 1이 "오너 우선순위 결정 필요"로 막혀 있으므로 다음 slice 방향을 오너에게 확인한다.
- 승인된 방향(공유 in-process vector index)을 브리프로 확정한 뒤 구현·검증한다.

## User Decisions and Rationale — Phase 4 real vector backend (B) 착수

- 오너가 HANDOFF Next Tasks 1의 후보 **B(real 영속 vector 백엔드)**를 다음 작업으로 선택했다. 브리프 `docs/plans/04-real-vector-backend-decisions.md`를 이전 kickoff 브리프 형식(옵션 표 + 추천)으로 작성해 6개 결정을 받았다.
- **2026-07-02 결정 갱신**: 그 시점 오너 결정은 "real ChromaDB/ES adapter와 embedding model 선택은 핵심 코어(Phase 5/6 포함) 이후 최후속"이었다. 오너가 지금(Phase 4 중반) B를 앞당기기로 결정해 이 부분을 갱신한다. 근거: 이 작업은 LLM 게이트와 무관해(테스트 스위트 전체가 LLM-독립, LLM은 live smoke 스크립트만 사용) 2-환경 개발(하나는 LLM 게이트 미가용) 제약과 정확히 맞고, vector need 영속화 이득을 조기 확보한다. ES lexical과 real embedding model 중 ES는 여전히 후속이다.
- **embedding model 확정 경위**: 오너가 처음 `dragonkue/bge-reranker-v2-m3-ko`를 지목했으나, 이는 cross-encoder **reranker**라 Chroma 벡터 생성(bi-encoder embedding)에는 부적합함을 확인·surface했다. 저장소에도 이 모델의 사전 확정 기록은 없었다(embedding model은 계속 "미확정"). 오너가 `dragonkue/BGE-m3-ko`(embedding model)로 정정했고, WebFetch로 bi-encoder·1024-dim·sentence-transformers·BAAI/bge-m3 한국어 파인튜닝을 확인했다. reranker는 후속 rerank 단계 후보로 남긴다.
- **인프라 방침**: "다 컨테이너로 관리하자"는 오너 지시에 따라 Chroma와 embedding model 모두 base compose 서비스 컨테이너로 둔다. embedding 서비스는 llama gateway와 분리해 vector 백엔드의 LLM-독립성을 유지한다.
- **embedding seam**: `EmbeddingProvider.embed`는 동기를 유지(짧은 호출, async 파급 회피)하고 `RemoteEmbeddingProvider`는 sync `httpx.Client`로 구현하기로 했다(단순성 우선).
- **B.1 독립 검증 후속(2026-07-05)**: `docs/verifications/2026-07-05/real_vector_backend_brief_b1_embedding_seam.md` 판정 **합격(조건 없음)**. 검증자가 WebSearch로 reranker/embedding 구분과 BGE-m3-ko 1024-dim을 독립 확인했고, bool 거부 guard·`expected_dimensions` guard의 양방향 mutation(bool guard 제거→test 8 재실패, dim guard 제거→test 2 재실패)을 재현했다. 비차단 관찰 2건은 B.1 범위 밖(생산 측은 B.2, wiring은 B.4)이라 B.1 코드는 손대지 않았다. 관찰 #1(MockTransport라 소비 측만 lock)을 잊지 않도록 **B.2 수용 기준에 "생산 측 wire 계약 + B.1↔B.2 round-trip 회귀"를 추적 항목으로 명시**했다(브리프 B.2).

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

### deployed smoke 확장 (rebuild → context-search)

- 변경 파일: `scripts/phase4_context_search_deployed_smoke.py`, `tests/test_phase4_context_search_deployed_smoke_script.py`.
- 기존 smoke는 rebuild를 호출하지 않아 배포 경로에서 공유 index vector hit을 검증하지 못했다. save version → snapshot_id 취득 → `POST .../index/source-blocks/rebuild` → `POST .../context-search` 2-step으로 확장했다.
- summary에 `snapshot_id`/`rebuild_http_status`/`rebuild_records_written`/`rebuild_backend`를 추가했다. exit 규칙을 `search_succeeded`→`smoke_succeeded`(rebuild 200 AND search 200)로 바꿔 두 status를 모두 게이팅한다.
- self-regression: rebuild가 search보다 먼저 호출되고(`summary_step_order_rebuild_before_search`) micro hit(`source_quote`)이 나는 성공 경로, search 502 실패, **rebuild 실패 시 search 200이어도 smoke 실패**(exit 규칙이 두 status 모두에 걸림) 3분기 + CLI 3방향(ok / search_err / rebuild_err). 4→5개.
- 실제 in-process app(진짜 endpoint + 공유 index 주입, fake planner)에 `httpx.ASGITransport`로 smoke를 구동해 mock이 아닌 실경로에서 `rebuild_records_written=6`, `micro_count=6`(source_quote vector need 실hit), gate `pass`, `smoke_succeeded=True`를 확인했다(이 slice 이전이라면 micro 0). compose stack + 실제 12B 관통 live 실행은 sandbox 밖 승인 네트워크가 필요해 미실행이다.

### 독립 검증 후속 보강 — real-app 관통 회귀 (2026-07-05)

- 독립 검증(`docs/verifications/2026-07-05/deployed_smoke_rebuild_first.md`) 판정은 **합격**(조건 없음). 비차단 관찰: 이 slice 회귀가 전부 MockTransport라 HTTP orchestration·exit 규칙·summary 파싱은 lock하지만 "rebuild가 실제로 공유 index를 채워 search가 실hit"은 committed 회귀가 아니었다(수동 ASGITransport 드라이브였음).
- 보강: 수동 드라이브를 committed 회귀로 전환했다. `test_real_app_rebuild_populates_shared_index_and_search_hits`가 real `create_app`(공유 index 주입 + fake planner)에 `httpx.ASGITransport`로 확장 smoke를 구동해 `rebuild_records_written>0`, `micro_count>0`(source_quote 실hit), `smoke_succeeded`를 잠근다. 5→6개.
- non-vacuity mutation: `create_app`에 `vector_index=shared_index` 주입을 빼면 rebuild가 별도 adapter에 쓰여 search가 empty가 되어 `micro_count 0`으로 재실패 → 회귀가 실제 관통을 검증함을 증명. 복원 byte-identical. 전체 475 OK(44 skip)/pytest 431 passed.

## Next steps

- compose stack(실제 12B) 관통 deployed smoke live 실행: 확장된 `scripts/phase4_context_search_deployed_smoke.py`가 이제 rebuild → context-search 2-step을 돌리므로, 승인된 네트워크에서 실행하면 배포 경로 vector 실hit을 관통 검증한다.
- real ChromaDB persistent vector adapter / ES lexical 경로(§8, 착수 전 브리프)는 계속 후속.
- prior-memory(analysis 비교) purpose §8 C 완성(Phase 2B 착수 브리프)도 후속.
