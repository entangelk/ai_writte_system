# Work Log — 2026-07-08

## Goals

- HANDOFF와 2026-07-07 work log를 읽고 다음 작업을 진행한다.
- (오너 지시로 방향 전환) 비대해진 `HANDOFF.md`를 CLAUDE.md §5 원칙에 맞게 정리한다.

## Completed work

### HANDOFF.md 정리 (문서 전용)

- **문제**: `HANDOFF.md`가 410줄/139KB로 비대해졌다. "Active Decisions"는 slice별 "X가 구현됐다" 완료 일지 ~113개, "Verification"은 2026-06-24~07-05 회귀 실행 로그 ~90개로, 핸드오프가 이력/일지가 되어 있었다(CLAUDE.md §5: 핸드오프 = 현재 상태 스냅샷, 이력 아님).
- **안전 확인(삭제 전)**: 걷어낼 이력이 다른 곳에 보존돼 있는지 먼저 확인했다 — `CHANGELOG.md`가 전 마일스톤(SoT 전 버전·전 slice)을 daily_logs 링크와 함께 보존, `docs/verifications/`가 독립 검증 보존, `docs/daily_logs/`가 상세 회귀/mutation 이력 보존. 따라서 삭제 안전.
- **재작성 내용**:
  - 상단에 목적 타이틀 추가(오너 문구): "다음 작업자를 위한 현재 상태 스냅샷. 이력/일지가 아니라 지금 사실이고 실행 가능한 것만 둔다. 상세 이력은 daily_logs, 독립 검증은 verifications, 주요 마일스톤은 CHANGELOG."
  - **Current Status**: 진화 서사 대신 지금 동작하는 계층(Gateway/Core SOT/Agent loop/Analysis/Memory/Indexing/Context search)을 present-tense 요약 + compose 런타임 + 현재 테스트 수(619 passed/45 skipped)로 교체.
  - **Active Decisions**: ~113개 완료 일지를 표준 제약(향후 작업 구속)만 남겨 문서·아키텍처·Core SOT·Agent loop·Analysis/Memory·추적 부채 6그룹으로 distill.
  - **Verification**: ~90개 실행 로그를 현재 상태 1개(전체 스위트 결과 + 실행법 + mongo-ignore 관례 설명)로 축약.
  - **Next Tasks**: 실행 가능 항목만 5개로 재정렬(다음 slice 후보 a~d, sandbox 밖 잔여, Phase 4 잔여, 추적 부채, 보류 계약층). 내용은 보존.
  - **Project Structure**: 드리프트 교정 — 누락됐던 `memory/` 패키지 추가, daily_logs/verifications 범위 2026-07-07까지, plans/scripts/tests 최신화(embedding·chroma·semantic_matcher·apply·2B.5/6 스크립트 등).
- **결과**: 410줄/139KB → **129줄/15.5KB**(382줄 삭제, 102줄 추가). 코드/계약 변경 없음.

## Issues found

- 없음. (Project Structure 트리에서 `memory/` 패키지 전체 누락과 daily_logs 목록이 2026-07-01에서 멈춰 있던 드리프트를 정리 과정에서 교정했다.)

## Decisions

- **핸드오프는 스냅샷, 이력은 참조로 위임**(오너 지시 반영). 완료 이력/검증 실행 로그는 CHANGELOG/daily_logs/verifications가 이미 보존하므로 HANDOFF에서 중복 유지하지 않는다. 이력을 지우기 전 다른 문서의 보존 여부를 먼저 확인해 정보 손실을 막았다.

## User Decisions and Rationale

- 오너가 다음 구현 slice를 고르기 전에 **HANDOFF 정리를 먼저** 지시했다. 근거: 핸드오프는 다음 작업자를 위한 현재 상태 스냅샷이어야 하고, 주요 사건은 CHANGELOG, 상세는 daily_logs, 독립 검증은 verifications로 분리돼 있어 핸드오프에 이력을 쌓을 이유가 없다. 상단에 이 목적을 명문화한 타이틀을 달아 두라는 지시도 함께 반영했다.

## Verification

- 문서 전용 변경. 참조 경로 유효성 확인: `docs/runbooks/local-llama-server.md`, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`, `docs/system-contract-sot.md`, `services/embedding/app/main.py`, `services/application/app/memory/service.py`, `scripts/phase2b5_*` 전부 존재. SoT 버전 문구(v1.6.48)·테스트 수(619 passed/45 skipped)는 정본/직전 로그와 일치.
- `git diff --check` clean. 코드 미변경이라 테스트 스위트 영향 없음.

### 추적 부채 #8 조사·폐쇄 (SoT v1.6.49)

- **지시**: 오너가 작은 cleanup slice로 부채 #8(`ProviderError`→502 패턴을 `/context-search`·2A extraction adapter에 적용)을 먼저, 그다음 (a) candidate Writing 포함 순으로 지시. e가 후속(a)의 영향을 받으면 a부터 하라는 조건 첨부.
- **의존성 판단**: (e)는 두 경로의 provider 오류 매핑, (a)는 context_search에 candidate retriever step/gate 분기 추가 — 직교. (e)는 (a)의 영향을 받지 않으므로 e→a 순서 유지.
- **조사 결과 — 부채는 stale(CLAUDE.md §1)**: 코드를 읽으니 부채 노트(2026-07-06)의 "uncaught → HTTP 500"이 현재 코드와 어긋났다.
  - `/context-search`: service `_build_plan`(`context_search/service.py`)이 planner 호출을 `try`로 감싸고 async `await`까지 포함해 `except Exception → ContextSearchFailed(llm_error)`로 매핑(slice 4.1 원본 커밋 `44da077`부터 존재). 엔드포인트가 `ContextSearchFailed → 502`. → 이미 502.
  - 2A `/run`: 엔드포인트에 `except Exception → 502` catch-all(main.py). runner가 `ProviderError`를 mark_job_failed(provider_error) 후 재던지면 catch-all이 502로. → 이미 502.
  - 노트가 지목한 **compare** 엔드포인트만 catch-all이 없어 실제 누출했고 그래서 명시적 `except ProviderError`(v1.6.34)가 필요했다. 노트 작성자가 compare 구조를 형제 경로에도 있다고 가정한 것.
  - **재현 실증**: scratchpad에서 async planner가 실제 `ProviderError`를 await에서 던지도록 구성 → `/context-search` 응답 `502 llm_error: planner failed: ...` 확인(500 아님).
- **오너 결정(surface 후)**: 부채 stale임을 보고하고 "회귀 lock만 + 부채 닫기" vs "명시적 except ProviderError 추가" 중 택일 요청 → 오너가 **명시적 분기 추가** 선택(compare와 대칭·의도 가독·미래 refactor 방어).
- **구현**: 동작 변경 없이(이미 502) 실제 provider 호출 지점에 명시적 분기 추가.
  - `main.py` `/run` 엔드포인트: catch-all 앞에 `except ProviderError → 502(str(exc))`.
  - `context_search/service.py` `_build_plan`: generic catch 앞에 `except ProviderError → ContextSearchFailed(llm_error, "planner provider error: …")`. `ProviderError` import 추가.
  - **2A extraction adapter에는 wrap하지 않음**: adapter에서 감싸면 `AnalysisExtractionError`→400으로 **오분류**되므로 502 경계(엔드포인트)에 둔다.
- **회귀 +2 + mutation 재실증**:
  - `test_context_search_api.py::test_planner_provider_error_maps_to_502_llm_error`: `_AsyncProviderErrorPlanner`(coroutine이 await에서 실 `ProviderError`)→502 + detail "provider error". **mutation**: 명시 분기 무력화 시 detail이 "planner failed"로 바뀌어 assert 실패(분기 load-bearing, over-strict).
  - `test_application_api.py::test_analysis_run_endpoint_maps_real_provider_error_to_502`: `_ApiRealProviderErrorRunner`(실 `ProviderError` 재던지기)→502 + failure_reason=provider_error. **mutation**: `/run`의 명시+generic catch 둘 다 무력화 시 uncaught 500으로 재실패(계약 load-bearing, under-strict).
- **검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **621 passed / 45 skipped**(619 → +2). `git diff --check` clean. 계약(ProviderError→502) 변경 없음 — 명시화·회귀 lock·부채 폐쇄만.

### (a) `needs_review` candidate의 Writing 포함 (SoT v1.6.50)

- **리듬**: 착수 브리프(`plans/04-writing-candidate-context-decisions.md`) → 오너 결정 → 구현. v1.6.48이 명시한 "바로 다음 slice".
- **조사**: v1.6.48 canonical machinery(retriever seam→step→item→Gate origin 분기)를 그대로 재사용 가능. `ContextItemStatus`에 CANDIDATE/CANONICAL 이미 존재. Gate는 현재 전역 `candidate_item_not_allowed`. candidate 리스팅은 job별만 있어 project-wide `needs_review` 리스팅 신설 필요. candidate payload는 memory와 같은 taxonomy라 `derive_memory_index_text` 재사용.
- **헤드라인 긴장(§1)**: (1) v1.6.38이 candidate 포함을 미룬 이유="canonical 위장으로 Writing 안전선 완화" → Phase 2B가 종속 해소했으나 **Phase 6 §62("승인 전 candidate가 canonical/검색 constraint로 위장 금지")** 불변식 준수 필요. (2) Gate 전역 candidate 금지를 통째로 여는 게 아니라 candidate origin만 좁혀 허용.
- **오너 결정**: **D1/D2/D3/D5/D6/D7=A**(canonical 대칭) + **D4=B**(review_status 필드 지금 신설) + **안전선=A**(라벨 + micro만 + 권위필드 배제).
- **구현**:
  - `context_search/models.py`: `ContextNeed.CANDIDATE_MEMORY`(micro, mongo) + `ContextItem.review_status` 필드(candidate만 의미, 현재 needs_review; canonical/source-block은 빈값).
  - `context_search/service.py`: `CandidateMemoryRetriever` seam + `MongoDirectCandidateMemoryRetriever`(needs_review-only, limit). `_run_candidate_memory_step`(retriever 미주입→빈, 예외→BACKEND_ERROR) + `_item_from_candidate`(status=CANDIDATE·pointer.collection=`analysis_candidates`·review_status). `_execute_step_tool` 분기. `evaluate_context_gate`에 `analysis_service` param + `_gate_candidate_findings`(get_candidate로 존재+needs_review+project 재검증).
  - `analysis/`: project-wide `list_needs_review_candidates`(service·Protocol·in-memory·mongo).
  - `main.py`: `_default_context_search_service(analysis=)` + candidate retriever 주입 + gate `analysis_service=analysis` + item payload `review_status`.
- **Gate 재편 정정(구현 중, §1)**: 처음엔 candidate 검사를 else(source-block) 분기로만 옮겨 v1.6.48 `test_candidate_status_memory_item_still_rejected`(memory-origin candidate-status 거부)를 깼다. 정정: candidate 금지를 폐지가 아니라 "candidate origin만 예외"로 좁힘(`status is CANDIDATE and not is_candidate_origin → candidate_item_not_allowed`). v1.6.48 계약 보존 + 신규 origin 허용 양립.
- **D5 문구 정정(§1)**: "승격된 candidate가 needs_review set을 떠난다"는 아직 참이 아님 — needs_review→confirmed/rejected 전이는 Phase 6. 현재 승격은 canonical memory만 mint하고 candidate 상태 불변 → 승격 지식은 canonical·candidate 양쪽 노출 가능(D7=A no-dedup 수용). Gate의 status≠needs_review→stale은 Phase 6 forward-defense(회귀는 stub으로 실증).
- **회귀 +9**(`tests/test_context_search_candidate_memory.py`): micro 라벨 배치 + §62 권위필드(constraints/do_not_use) 배제, retriever 미주입 무실패, retriever needs_review-only+limit, retriever 예외→BACKEND_ERROR, Gate 4방향(pass/missing-stale/status-stale[stub]/unconfigured), 비-candidate-origin candidate-status 여전히 거부(over-strict). **mutation 양방향**: Gate status-check 무력화→status-stale 재실패; candidate-origin 예외(`not is_candidate_origin`) 제거→pass 재실패. 각 복원.
- **검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **630 passed / 45 skipped**(621 → +9). 기존 context_search/canonical/analysis 회귀 무변(v1.6.48 candidate 금지 테스트 포함). `git diff --check` clean.

## User Decisions and Rationale (v1.6.50)

- 오너가 **D4=B**(review_status 필드 지금 신설)를 택했다. status=candidate 단일 라벨(A)보다 Phase 6 confirmed/rejected 소비 계약을 미리 forward-compat하는 쪽. 현재 값은 needs_review 고정(2A needs_review 고정 선례와 유사).
- 오너가 **안전선=A**(라벨 + 권위필드 배제)를 택했다. Phase 6 §62(승인 전 canonical 위장 금지)를 candidate를 아예 막는 대신 명시 라벨 + micro 한정 + constraints/do_not_use 배제로 지키며 포함한다.

## 검증 후속 보강 (2026-07-08, 오너 독립 감사 → 비차단 3건 폐쇄)

오너의 독립 감사 기록 `docs/verifications/2026-07-08/sot_v1_6_49_50_audit.md`는 **세 커밋 모두 합격**(차단 없음). 비차단 관찰 3건을 오너 지시로 보강했다.

- **이슈 #1(doc nit)**: `HANDOFF.md:99` Project Structure의 SoT 버전 주석이 `v1.6.48`로 stale → `v1.6.50`으로 정정(line 8 Current Status는 이미 정확했음).
- **이슈 #2(doc nit)**: `HANDOFF.md:107` daily_logs/verifications 범위가 `…2026-07-07` → `…2026-07-08`로 갱신.
- **이슈 #3(test-coverage)**: (e) `/run` 502 회귀가 stub runner만 사용해 실제 extractor→runner 체인(ProviderError wrap 없음)이 코드 검사로만 확인됐던 gap을 닫음. `tests/test_analysis_runner.py`에 `test_runner_provider_error_propagates_unwrapped_as_provider_error` 추가 — **실제** `AnalysisExtractionAdapter`에 `ProviderError`를 던지는 `_ProviderErrorProvider`를 물려 runner를 구동, (a) `ProviderError`가 wrap 없이 전파(expected_exc=ProviderError → extractor가 400으로 오분류하지 않음 확인), (b) runner가 `failure_reason=provider_error`로 매핑 후 원예외 재던짐을 잠갔다. **mutation 실증**: `AnalysisExtractionAdapter.extract`가 provider 호출을 `except ProviderError → AnalysisExtractionError`로 감싸도록 변형 시 이 테스트가 `AnalysisExtractionError`(≠ProviderError)로 재실패(extractor 비-wrap이 load-bearing). 종점 `ProviderError→502` 매핑은 종전대로 endpoint stub 테스트가 잠그므로, 이제 extractor→runner→endpoint 전 체인이 회귀로 lock됨.
- **경계 위험(무조치)**: 감사가 지적한 "Gate origin 분기의 `else` fallback이 새 collection을 source-block으로 처리" 위험은 현재 3 collection만 존재하는 forward concern이라 코드 변경 불요(오너도 비차단·경계로 분류).
- **재검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **631 passed / 45 skipped**(630 → +1). mutation 복원(`git checkout`) 후 clean. `git diff --check` clean.

### (b) Writing canonical memory retrieval의 vector 확장 (SoT v1.6.51)

- **리듬**: 착수 브리프(`plans/04-writing-memory-vector-retrieval-decisions.md`) → 오너 결정 → 구현. v1.6.48/v1.6.50 canonical D2=A가 "retrieval 레이어 교체·권위 재유도 불변"으로 명시 위임한 후속.
- **조사에서 드러난 헤드라인 긴장(§1 — surface)**: HANDOFF Next Tasks #1(b)는 "canonical·candidate **둘 다** vector로 함께 확장(같은 seam)"이라 적었으나, 코드 재확인 결과 **candidate는 어떤 vector index에도 색인돼 있지 않다**(`memory_vectors`는 canonical `MemoryEntry` 전용, 2B.5; `indexing/`에 candidate 참조 0건). → candidate vector는 색인 파이프라인(2B.5 규모) 선행이 필요해 별도 slice. 또 **ES lexical(§8)은 인프라 전무**(compose·코드에 ES 없음, SoT 아키텍처 표 line 128에 의도만). 이 둘을 브리프에 명시하고 오너 결정으로 slice를 canonical vector만으로 좁혔다.
- **오너 결정**: **D0=A**(canonical vector만), **D1=A**(권위 재유도), **D2=단일 풀 병합**(단 `_merge_hits` 격리로 per-type 후속 분리 가능), **D3=A**(env 배선 fallback), **D4=A**(fake 회귀, 실 Chroma 후속), **D5=A**(ES 별도 — 단 머신에 ES 8.13.4+nori 컨테이너 `tf-ai-harness-elasticsearch-step1`가 9201에 있어 후속 실 테스트 활용 가능성 확인 대상).
- **구현(순수 주입 교체 — step/item/Gate 무변)**:
  - `context_search/service.py`: 신설 `VectorCanonicalMemoryRetriever`. `retrieve(project_id, query, limit)`가 (1) `embeddings.embed(query)`, (2) 3종 `AnalysisCandidateType`을 각각 `MemoryVectorIndexAdapter.query_similar(memory_type=…)`로 조회, (3) `_merge_hits`(cosine 유사도 단일 풀 정렬, id tie-break — 격리된 swap point), (4) hit `memory_id`로 `MemoryService.get_memory` 권위 재유도(삭제 memory 잔존 벡터는 `MemoryNotFound`로 skip), (5) `status is CANONICAL`만 global limit까지 반환. `MemoryIndexRecord`·`MemoryVectorIndexAdapter`·`_cosine_similarity`·`AnalysisCandidateType` import 추가.
  - `main.py`: `_build_canonical_memory_retriever(memory)` 신설 — `CHROMA_HOST`+`EMBEDDING_SERVICE_URL` 둘 다면 `ChromaMemoryVectorIndexAdapter`(memory_vectors) 위 `VectorCanonicalMemoryRetriever`, 아니면 종전 `MongoDirectCanonicalMemoryRetriever` fallback(`_build_semantic_matcher`의 memory_vectors 배선 선례 재사용). `_default_context_search_service`가 이 빌더를 호출. candidate retriever·Gate·item 배선 전부 무변.
- **회귀 +5**(`tests/test_context_search_memory_vector_retrieval.py`): 권위 재유도+relevance 순서(index text가 아니라 store payload 반환으로 authority 실증)·global limit·stale 벡터 격리(삭제→MemoryNotFound, superseded→CANONICAL 필터)·**단일 풀 병합이 per-type 아님**(같은 type 2 hit이 다른 type 1 hit을 limit 안에서 이김)·seam 불변(vector retriever가 canonical_memory step으로 micro memory item 산출). **mutation 양방향**: CANONICAL 필터 무력화→stale 테스트 재실패(under-strict); `_merge_hits`를 round-robin으로→병합 테스트 재실패(over-strict). 각 복원 확인.
- **검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **636 passed / 45 skipped**(631 → +5). 기존 canonical/candidate/context_search 회귀 전부 무변(seam 불변 실증). `git diff --check` clean.

## User Decisions and Rationale (v1.6.51)

- 오너가 **D0=A**(canonical vector만)를 택했다. HANDOFF의 "둘 다 함께 확장"은 candidate 쪽에 뒷받침 index가 없다는 사실을 놓친 것으로, candidate를 억지로 묶으면 색인 파이프라인 선행으로 slice가 비대해지고 §62 색인 표면이 확대된다. canonical만 하면 인프라가 이미 있어 순수 주입 교체.
- 오너가 **D2=단일 풀 병합(MVP)**을 택하되 "언제든 per-type 분리 가능하게 설계"를 명시 지시했다. → 병합 로직을 `_merge_hits` 단일 메서드로 격리(추측적 전략 프레임워크는 짓지 않음 — §2)해, 후속에서 per-type 선발로 교체할 지점만 명확히 남겼다.
- 오너가 **D5=A**(ES 별도)를 택하되, 머신에 이미 떠 있는 ES 컨테이너(nori 한국어 분석기 포함)를 ES leg 착수 시 실 테스트에 쓸 수 있는지 확인하라고 했다. 이번 slice에서는 조사만(위치·버전 기록), 활용은 §8 착수 브리프의 몫.

## Next steps

- **candidate vector**(D0 후속): candidate 색인 파이프라인(outbox→worker→candidate vector collection) 선행 후 `VectorCandidateMemoryRetriever`로 같은 seam 확장.
- **ES lexical(§8)**: 별도 착수 브리프. 머신의 `tf-ai-harness-elasticsearch-step1`(9201, nori) 실 테스트 활용 가능성 확인 포함.
- **실 관통(sandbox 밖)**: `VectorCanonicalMemoryRetriever` live smoke(실 Chroma memory_vectors + BGE-m3-ko relevance), relevance 품질 spike.
- 그 외 HANDOFF Next Tasks #1 후보 c/d/e 잔존.

### (b) 검증 후속 보강 (2026-07-08, 오너 독립 감사 → 비차단 관찰 보강)

오너의 독립 감사 기록 `docs/verifications/2026-07-08/canonical_memory_vector_retrieval.md`는 **합격**(차단 없음, boundary matrix 14 cell 중 13 pinned, 잔여 1은 D4=A로 live smoke에 명시 위임). 비차단 관찰 4건 중 cheap·in-scope 3건을 보강했다(#2는 감사자도 pre-existing·범위 밖으로 분류 → CLAUDE.md §3에 따라 미조치).

- **관찰 #1(doc nit, 반복 패턴)**: `HANDOFF.md:100` Project Structure의 SoT 버전 주석이 `v1.6.50`으로 stale(Current Status `:8`은 이미 v1.6.51) → `v1.6.51`로 정정. 직전 candidate slice 보강에서 같은 줄 v1.6.48→50을 고쳤던 동일 패턴 반복.
- **관찰 #3(doc 일관성)**: SoT Phase 4 섹션 prose(`system-contract-sot.md:407`)가 v1.6.48까지만 서술 → v1.6.50(candidate 포함)·v1.6.51(canonical vector) 1문장씩 추가. changelog는 권위 있고 완전했으나 phase 요약 prose가 뒤처진 누락 보강(literal 모순 아님).
- **관찰 #4(test-coverage, cheap 보강)**: `embed(query)`의 query 인자가 랭킹에 반영됨을 lock하는 테스트 부재였다(기존 `_FixedEmbeddings`는 query-무지각이라 embed(query)를 상수로 hardcode해도 통과 = boundary cell #1의 mechanism은 pinned지만 query-flow는 미lock). `_QuerySensitiveEmbeddings`(query 문자열→구별 벡터) + `test_query_drives_ranking` 추가 — 같은 벡터 index에서 query "toward-a"→mem-a, "toward-b"→mem-b 상위. **mutation 재실증**: `retrieve`가 `embed(query)` 대신 상수 벡터 하드코드 시 이 테스트가 두 방향 중 하나로 재실패(query→embed→랭킹 flow가 load-bearing). 복원 후 통과.
- **재검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **637 passed / 45 skipped**(636 → +1). SoT v1.6.51 changelog·HANDOFF 테스트 수(636→637) 동기화. mutation 복원 후 `git diff --check` clean.
- **미조치(범위 밖)**: 관찰 #2(`system-contract-sot.md:100` "문서 역할" 표 v1.6.43 누적 stale)는 본 slice diff가 건드린 줄이 아니고 감사자도 범위 밖으로 분류 → 선재 stale은 요청 없이 건드리지 않음(§3). 관찰의 "경계 위험"(per-type limit 캡 + stale 필터 결합 시 yield<limit 가능)은 Mongo-direct도 동일한 설계적 속성이라 코드 편차 아님(무조치).

### (b-3) ES lexical + hybrid(RRF) 확장 (SoT v1.6.52)

- **리듬**: ES 컨테이너 실측(가용 확인) → 착수 브리프(`plans/04-writing-memory-lexical-retrieval-decisions.md`) → 오너 결정 → 구현. v1.6.51 vector leg에 이은 §8 lexical leg.
- **ES 컨테이너 실측**: 이 머신의 `tf-ai-harness-elasticsearch-step1`가 **ES 8.13.4·인증 없음·analysis-nori(한국어 형태소) 설치·host 9201**로 가용. 기존 인덱스는 `tf_ai_harness_*` 네임스페이스라 `ai_writte_*`로 충돌 없음(단 공유 컨테이너 → ephemeral 취급).
- **오너 결정**: E0/E1=A(색인 파이프라인+retriever 한 slice), E2=A(lexical=vector 대칭 권위 재유도), **E3=hybrid(RRF) 지금**(추천 A 상향 — vector+lexical RRF 결합), E4=A(nori 문서), E5=A(fake+실 smoke), E6=A(env 배선).
- **구현**:
  - `indexing/memory_lexical_index.py`(신규): `MemoryLexicalRecord`, `MemoryLexicalIndexAdapter` Protocol, `InMemoryMemoryLexicalIndexAdapter`(토큰-overlap fake), `ElasticsearchMemoryIndexAdapter`(ES 8.x `query`/`size` kwargs, project+canonical filter, delete 멱등[NotFound swallow]), `MemoryLexicalIndexSyncAdapter`(worker drain: canonical→index/superseded·deleted→delete + supersedes 삭제, vector leg 대칭), nori settings/mappings, `connect_elasticsearch_memory_index`.
  - `context_search/service.py`: `LexicalCanonicalMemoryRetriever`(ES search→`memory_id`→`get_memory`→canonical-only, seam 불변) + `HybridCanonicalMemoryRetriever`(각 sub-retriever의 canonical-resolved 순위 리스트를 RRF `1/(k+rank)` k=60로 융합, id dedup).
  - `indexing/memory_index.py`: `CompositeMemoryIndexSyncAdapter`(worker memory drain 팬아웃).
  - `main.py`: `_build_canonical_memory_retriever`를 `_build_vector_canonical_retriever`+`_build_lexical_canonical_retriever`로 분리 → 둘 다면 hybrid, 하나면 그 backend, 없으면 Mongo-direct. `index_sync_worker.py`: `ELASTICSEARCH_URL` 있으면 composite drain. `requirements.txt`에 `elasticsearch>=8,<9`.
- **구현 중 정정(§1 — outbox 계약 보호)**: 브리프 E1의 "outbox `targets.elasticsearch` 추가"는 **worker composite fan-out(substance)로 구현하고 persisted envelope의 per-target bookkeeping은 미뤘다**. enqueue는 Mongo choke point라 배포의 ES 구성을 모르는데, 무조건 ES target을 심으면 ES 없는 배포에서 **영구 pending** target이 생긴다. v1.6.26 outbox envelope·Mongo repo 직렬화(실 테스트 sandbox-skip)를 건드리지 않고, worker가 configured sink로만 fan-out하도록 했다. per-target status 추적은 outbox multi-target 추적 확보 시 후속.
- **회귀 +13**(`tests/test_context_search_memory_lexical_retrieval.py`): InMemory lexical 토큰-overlap 랭킹·project scope; ES adapter 포인터 문서·필터드 query(size 포함)·멱등 delete(fake client); lexical retriever 권위 재유도(index text 아니라 store payload)·canonical-only(superseded/deleted 격리)·query-drives-ranking; hybrid RRF 양신호 융합([b,a,c] = RRF 고유 순서)·dedup·단일 backend 저하; worker drain canonical 색인/superseded·missing 삭제; composite fan-out. **mutation 양방향**: RRF lexical 신호 제거→융합 테스트 재실패, lexical CANONICAL 필터 무력화→authority 테스트 재실패, 각 복원.
- **실 ES live smoke 통과**(`scripts/phase4_lexical_memory_live_smoke.py`): 실 ES 8.13.4+nori에 ephemeral 인덱스 생성→worker drain(superseded 미색인)→한국어 "폭풍" query가 canonical storm memory("폭풍이 항구를 덮쳤다")만 매칭·권위 재유도·hybrid RRF→인덱스 삭제. 출력 `{"ok": true, "lexical_ids": ["storm"], "hybrid_ids": ["storm","calm"], "nori": true}`, 공유 컨테이너에 잔여 인덱스 0.
- **검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **650 passed / 45 skipped**(637 → +13). 기존 context_search/canonical/candidate/vector/memory-reindex 회귀 무변(seam·vector leg 불변 실증). `git diff --check` clean.

## User Decisions and Rationale (v1.6.52)

- 오너가 **E3=hybrid(RRF)를 지금** 택했다(추천 A "MVP 택1, hybrid 후속"보다 상향). vector 관련성 + lexical(nori 한국어 키워드)을 Reciprocal Rank Fusion으로 결합해 두 신호를 동시에 쓰길 원함. 구현은 각 sub-retriever의 이미-권위화된 순위 리스트를 RRF로 융합(별도 score 정규화 불요)해 v1.6.51 코드를 그대로 재사용.
- 오너가 **머신의 기존 ES 컨테이너를 실 테스트에 활용**하도록 승인했다(E5). 공유 컨테이너라 `ai_writte_smoke_*` 네임스페이스 + 생성/삭제 격리로 다른 프로젝트 인덱스를 건드리지 않는다.

## Next steps

- **candidate lexical/vector**: candidate 색인 파이프라인(outbox→worker→candidate lexical/vector) 선행 후 같은 seam 확장.
- **hybrid 튜닝**: RRF k, per-signal 가중치, sub-retriever fetch depth(현재 각 limit)를 실 데이터로 캘리브레이션.
- **compose 전용 ES 서비스**: 배포용 ES를 `docker-compose.yml`에 추가(테스트는 기존 컨테이너, 배포 ES는 별도).
- **outbox per-target bookkeeping**: ES sink를 envelope에 명시적으로 추적하려면 outbox multi-target status 확장(위 정정 참조).

### (b-3) 검증 후속 보강 (2026-07-08, 오너 독립 감사 → 비차단 관찰 #1·#2)

오너의 독립 감사 기록 `docs/verifications/2026-07-08/canonical_memory_lexical_hybrid_rrf.md`는 **합격**(boundary matrix 21 cell 중 20 pinned, 잔여 1 = worker ES 배선 wiring glue). 감사자가 보강 권장한 비차단 관찰 2건(slice 최약 두 점)을 닫았다.

- **관찰 #1(test-coverage, slice 최약점)**: worker `_build_memory_adapter`의 `ELASTICSEARCH_URL` composite 분기가 단위테스트·live smoke 모두에서 미실증이었다(broken 시 ES+Chroma 배포가 vector-only로 silent 저하). `tests/test_index_sync_worker_script.py`에 `test_with_elasticsearch_url_builds_composite_memory_adapter` 추가 — `connect_elasticsearch_memory_index` mock으로 `ELASTICSEARCH_URL` 시 반환 adapter가 `CompositeMemoryIndexSyncAdapter`(sub-adapter = [vector `MemoryIndexSyncAdapter`, lexical `MemoryLexicalIndexSyncAdapter`], backend `"in_memory_fake+elasticsearch"`)임을 잠금. **mutation 실증**: ES 분기(`if es_url:`)를 `if False:`로 무력화 시 이 테스트가 vector-only 반환으로 재실패, 복원 통과.
- **관찰 #2(smoke 견고성, 감사자 실측)**: live smoke가 `Elasticsearch(url)` 기본 timeout(10s)이라 cold nori create(~4s, 부하 시 초과) 시 `ConnectionTimeout` + `finally` delete도 timeout으로 공유 컨테이너에 잔여 인덱스가 남을 수 있었다(E5 "생성/삭제 격리" 의도 붕괴). `request_timeout=30`(create·cleanup 모두 커버) + `finally` delete를 best-effort 재시도(1회)·실패 시 stderr 경고(원 결과 미마스킹)로 견고화. 재실행 통과, 잔여 0 확인.
- **미조치(§3)**: 관찰 #3(필드명 `memory_id` vs 브리프 `mongo_id` — SoT 미pin, 내부 일관), #4(ES search에 memory_type 필터 없음 — cross-type BM25 유효), #5(ES delete 광역 catch — narrow catch는 fake test의 커스텀 예외와 결합되고 stale doc은 retrieval에서 거름), #6(SoT:101 "문서 역할" 표 v1.6.43 pre-existing stale — 범위 밖), #7(브리프 E3 options 섹션 stale — 정규 계약 SoT는 명확) 모두 감사자 비차단 분류, 선재/미세 편차라 요청 없이 미조치.
- **재검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **651 passed / 45 skipped**(650 → +1). mutation 복원 후 `git diff --check` clean.
