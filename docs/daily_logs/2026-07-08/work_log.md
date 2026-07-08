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

## Next steps

- **다음 구현 slice 선택 대기**(HANDOFF Next Tasks #1 후보 b~e). b(vector/ES retrieval 확장)는 canonical·candidate 두 retriever가 같은 seam이라 함께 확장 가능. e(canonical↔candidate dedup)는 v1.6.50 D7 후속.
