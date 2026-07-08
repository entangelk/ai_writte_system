# 검증 기록 — 2026-07-08 세 커밋 독립 감사 (HANDOFF 정리 / SoT v1.6.49 / SoT v1.6.50)

## Subject metadata

- **날짜**: 2026-07-08
- **요청자**: 오너("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(독립 감사 — 작업자의 주장을 그대로 믿지 않고 1차 사료에서 재도출)
- **검증 대상 slice/아티팩트**: 작업 AI가 "모두 완료"라고 보고한 세 커밋
  1. `835215d` — HANDOFF.md 정리(410줄→129줄, 문서 전용)
  2. `e8ba45a` — SoT v1.6.49: 추적 부채 #8(`ProviderError`→502) 조사·폐쇄
  3. `f61d29a` — SoT v1.6.50: `needs_review` candidate의 Writing 포함(⑤ §5 B 후속)
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.50(Approved, 2026-07-08 갱신); `docs/plans/04-writing-candidate-context-decisions.md`(Resolved, v1.6.50 브리프); `docs/plans/04-writing-canonical-context-decisions.md`(v1.6.48 선례)
- **작업 원본(source of work)**: 커밋 `835215d`, `e8ba45a`, `f61d29a`(HEAD). 작업 tree는 검증 시작 시 `git status` clean.

## Scope

감사는 계약↔구현↔테스트↔fixture(여기서는 in-memory/stub) 스택을 하나의 whole로 취급한다. 각 커밋별 검증 표면:

- **(1) HANDOFF 정리**: 링크/참조 경로 유효성, 버전·precedence 정합성, Project Structure 드리프트 교정(memory/) 정확성, 삭제 정보 손실 여부(CHANGELOG/daily_logs/verifications 보존 대조).
- **(e) v1.6.49**: "부채는 stale" 핵심 주장(두 경로가 이미 502), 실제 extraction→runner→endpoint 체인의 502 매핑, 명시적 `except ProviderError` 분기 배치, 회귀 +2의 양방향 guard.
- **(a) v1.6.50**: 브리프 D1–D7 결정·안전선(Phase 6 §62)·Gate 재편(전역 금지→candidate origin 예외 좁힘)의 계약 일관성, boundary matrix 9 cell의 테스트 매핑, mutation 양방향, v1.6.48 candidate 금지 회귀 보존, 교차 프로젝트 누출 방어.

## Methodology

각 주장을 1차 사소스에서 재도출. 작업자의 work_log/SoT changelog 인용은 출발점일 뿐, 코드·테스트·실행 결과로 독립 확인.

1. **계약 스코프先行**: 브리프(`04-writing-candidate-context-decisions.md`)와 SoT changelog(v1.6.49/v1.6.50 항목)를 먼저 읽어 boundary matrix를 구성한 뒤 코드를 읽음.
2. **diff 검사**: `git show <commit> -- <path>`로 세 커밋의 전체 diff(코드·테스트·SoT·브리프)를 확보. 커밋 전 상태(`e8ba45a^:`, `f61d29a^:`)를 대조해 "stale 부채"/"회귀 무변" 주장을 검증.
3. **실행 재현**: `python3 -m pytest -q`(전체) 및 타깃 파일·타깃 테스트 실행. mutation은 소스를 치환→타깃 테스트 실행→`git checkout`/백업 복원으로 각 케이스마다 clean state 보장.
4. **계약 일관성 grep**: `CANDIDATES_COLLECTION` vs 실제 Mongo 컬렉션명, `MEMORIES_COLLECTION`, `MACRO_NEEDS`, `derive_memory_index_text` 시그니처, `get_candidate` project scoping 등 계약 literal이 코드 전체에서 불변인지 확인.
5. **pattern sweep**(CLAUDE.md §4): (e) 다른 provider-call 엔드포인트의 502 누출, (a) `evaluate_context_gate` 호출처가 모두 `analysis_service`를 주입하는지.

명령은 Reproduction 섹션에 재현 가능한 형태로 둠.

## Findings

### Surface 1 — (1) HANDOFF.md 정리(835215d, 문서 전용)

- **정보 손실 없음(삭제 전 보존 확인)**: work_log(`docs/daily_logs/2026-07-08/work_log.md`)가 삭제 전 `CHANGELOG.md`가 전 마일스톤을 daily_logs 링크와 보존, `docs/verifications/`가 독립 검증 보존, `docs/daily_logs/`가 상세 회귀/mutation 이력 보존함을 명시. 감사자가 `CHANGELOG.md`에서 v1.6.46~v1.6.50 항목과 daily_logs 링크가 모두 존재함을 확인. ✓ 삭제는 안전.
- **Project Structure 드리프트 교정 정확**: `HANDOFF.md:117`이 `memory/`를 "models · scope · service · repository · mongo_repository"로 기술. 실제 `services/application/app/memory/`는 `__init__.py, models.py, mongo_repository.py, repository.py, scope.py, service.py`(`ls` 확인) — 기술과 일치. ✓
- **참조 경로 유효**: work_log가 존재를 주장한 6개 경로 독립 확인 — `docs/runbooks/local-llama-server.md`, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`, `docs/system-contract-sot.md`, `services/embedding/app/main.py`, `services/application/app/memory/service.py`, `scripts/phase2b5_reindex_memory.py`·`scripts/phase2b5_memory_reindex_live_smoke.py` — 전부 존재. ✓
- **이슈 #1(비차단, doc nit)**: `HANDOFF.md:8`은 "현재 **v1.6.50**"이라 정확하나, `HANDOFF.md:99`(Project Structure 주석)은 "정본 계약 SoT(Approved, v1.6.48)"로 stale. 실제 `docs/system-contract-sot.md`는 `계약 버전: v1.6.50`. (e)/(a)가 SoT 버전을 올리며 Current Status(line 8)는 갱신했지만 Project Structure 주석(line 99)은 미갱신. 정리 커밋 자체는 v1.6.48 시점이어서 당시 정확했으나, 후속 (e)/(a)가 동일 라인을 못 보았음.
- **이슈 #2(비차단, doc nit)**: `HANDOFF.md:107`이 daily_logs 범위를 "2026-06-24 … 2026-07-07"로 표기하나 `docs/daily_logs/2026-07-08/`(오늘 work_log)가 존재. 범위가 하루 부족.

### Surface 2 — (e) SoT v1.6.49: `ProviderError`→502 부채 폐쇄(e8ba45a)

- **"부채는 stale" 핵심 주장 — 검증자가 커밋 전 상태에서 독립 확인(참)**:
  - `/context-search`: 커밋 전(`e8ba45a^`) `_build_plan`이 `except Exception as exc: raise ContextSearchFailed(ContextSearchErrorType.LLM_ERROR, f"planner failed: {exc}")`(`service.py` parent)를 가짐. 엔드포인트가 `ContextSearchFailed(llm_error)`→502. → 이미 502. ✓
  - 2A `/run`: 커밋 전(`e8ba45a^`) 엔드포인트가 `except Exception as exc: raise HTTPException(status_code=502, detail=str(exc))` catch-all(`main.py:1036-1037` parent)을 가짐. → 이미 502. ✓
  - compare 엔드포인트: `main.py:1231`에 `except ProviderError → 502`가 **사전 존재**(v1.6.34, 주석로 확인). (e) SoT가 "compare만 catch-all이 없어 누출"이라 한 것과 정합. ✓
- **실제 extraction→runner→endpoint 체인 502 매핑 — 코드 검사로 확인(참)**: stub runner 테스트가 끝점 매핑만 검증하므로, 감사자가 실제 체인을 직접 추적.
  - extractor: `services/application/app/analysis/extractor.py:108-148`의 `extract()`에서 provider 호출 `result = await self._provider.generate(request)`(line 128)은 prompt-building `try`(line 109-126, `except (PromptTemplateError, AnalysisPromptBuildError)` — 좁음) **밖**에 있음. 즉 `ProviderError`는 좁은 except에 잡히지 않고 원형 전파. ✓
  - runner: `services/application/app/analysis/runner.py:155-162`가 `except Exception`→`mark_job_failed(failure_reason=_failure_reason(exc))`→`raise`(원예외 재던짐, wrap 아님). `_failure_reason`(`runner.py:176-190`)은 `ProviderError`가 어떤 isinstance에도 안 걸려 fallback `AnalysisJobFailureReason.PROVIDER_ERROR` 반환. ✓
  - endpoint: 재던져진 `ProviderError`가 `/run`의 `except ProviderError → 502`(`main.py:1044`, (e) 추가) 또는 catch-all `except Exception → 502`에 도달. ✓
  - 결론: (e)의 "2A extraction adapter에는 wrap하지 않는다(감싸면 400 오분류)" 결정은 정확 — extractor가 이미 ProviderError를 wrap하지 않으므로 종점에서 502.
- **코드 변경**: `context_search/service.py:240-252`에 `_build_plan`의 `except ProviderError → ContextSearchFailed(LLM_ERROR, "planner provider error: …")`(generic catch 앞); `main.py:1038-1044`에 `/run`의 `except ProviderError → 502(str(exc))`(catch-all 앞). 둘 다 generic catch 앞에 배치되어 의도 가독·refactor 방어. ✓
- **회귀 +2**: `tests/test_context_search_api.py`의 `_AsyncProviderErrorPlanner`(coroutine이 await에서 실 `ProviderError(UNAVAILABLE)` raise)→`test_planner_provider_error_maps_to_502_llm_error`(502 + "llm_error" + "provider error" detail); `tests/test_application_api.py:1323-1352`의 `_ApiRealProviderErrorRunner`(실 `ProviderError` 재던짐)→`test_analysis_run_endpoint_maps_real_provider_error_to_502`(502 + failure_reason=provider_error). ✓
- **mutation 양방향 — 감사자가 직접 실행하여 확인**:
  - **Mutation 3a**(service의 명시 `except ProviderError` 분기 제거): `test_planner_provider_error_maps_to_502_llm_error`가 `AssertionError: 'provider error' not found in 'llm_error: planner failed: gateway is unavailable'`로 **FAIL**(over-strict guard — detail assert가 명시 분기 발화를 pin). 상태는 여전히 502(generic catch가 아직 502) → "stale 부채" 부언 확인. ✓
  - **Mutation 3b**(명시 분기 + generic catch 둘 다 제거): `ProviderError: gateway is unavailable` uncaught 전파 → **FAIL**(under-strict — 500). ✓
- **이슈 #3(비차단, test-coverage 관찰)**: `/run` 502 테스트 2개(기존 `test_analysis_run_endpoint_maps_provider_exception_to_502` + 신규) 모두 **stub runner** 사용. 실제 extractor→runner→endpoint 체인이 ProviderError를 wrap 없이 전달하는 것은 **코드 검사로만** 확인됨(위). e2e로 실제 extractor에 실패 provider를 주입해 502를 끝까지 관통하는 테스트는 없음. 동작은 정확하나 회귀 lock이 종점 매핑에 머묾.

### Surface 3 — (a) SoT v1.6.50: `needs_review` candidate Writing 포함(f61d29a)

#### 계약 일관성(브리프 D1–D7 ↔ 코드 literal)

- **D1=A**: `ContextNeed.CANDIDATE_MEMORY = "candidate_memory"`(`models.py`) 신설; `NEED_ALLOWED_TOOLS[CANDIDATE_MEMORY] = (SearchTool.MONGO,)`; `MACRO_NEEDS = (CURRENT_SCENE, RECENT_SCENES)`(`models.py:88`)에 **미포함** = micro. ✓
- **D4=B**: `ContextItem.review_status: str = ""`(`models.py`) 신설(candidate origin만 의미, canonical/source-block은 빈값 inert). `_item_from_candidate`가 `review_status=str(candidate.status)` 설정; canonical `_item_from_memory`는 설정 안 함(기본값 ""). ✓
- **D2=A**: `CandidateMemoryRetriever` Protocol + `MongoDirectCandidateMemoryRetriever`(`service.py:150-191`) — `list_needs_review_candidates` 호출, `query` 무시, `limit` 적용. analysis 층에 `list_needs_review_candidates`(Protocol `repository.py:66-69`·InMemory `service.py`·Mongo `mongo_repository.py:226-234`·`AnalysisService` wrapper) 신설. ✓
- **D5/D6=A**: `_item_from_candidate`가 `derive_memory_index_text(candidate.candidate_type, candidate.payload)` **재사용**. `derive_memory_index_text(memory_type: AnalysisCandidateType, payload)`(`indexing/memory_index.py:38`) 시그니처가 `AnalysisCandidateType`를 받으므로 `candidate.candidate_type`과 정확히 호환(D6 "candidate payload는 memory와 동일 taxonomy" 주장 확인). pointer = `collection=CANDIDATES_COLLECTION`·`document_id=candidate.id`·`version_id=""`·`content_hash=""`; `snapshot_id=""`·`sot_reloaded=True`(inert, canonical과 동일). ✓
- **D3=A Gate 재편(핵심 안전 정정)**: `evaluate_context_gate`(`service.py:765-820`)에 `analysis_service` param 추가. `is_candidate_origin = item.pointer.collection == CANDIDATES_COLLECTION`; `if item.status is ContextItemStatus.CANDIDATE and not is_candidate_origin: → candidate_item_not_allowed`(**전역 금지를 폐지가 아닌 candidate origin만 예외로 좁힘**); `elif is_candidate_origin: _gate_candidate_findings(...)`. `_gate_candidate_findings`(`service.py:878-918`): service None→`candidate_gate_unconfigured`; `get_candidate` `AnalysisNotFound`→`stale_item`; `status is not NEEDS_REVIEW`→`stale_item`(Phase 6 forward-defense); else pass. ✓
- **교차 프로젝트 누출 방어**: `AnalysisService.get_candidate`(`service.py:446`)→`_require_candidate`가 `candidate.project_id != project_id → AnalysisNotFound`(`service.py` `_require_candidate`). 따라서 타 프로젝트 candidate는 `stale_item` 분기로 처리(누출 없음). Mongo `get_candidate`는 `_id` only 조회지만 서비스층 project check가 보장. ✓
- **CANDIDATES_COLLECTION 일관성**: `service.py:70` `CANDIDATES_COLLECTION = "analysis_candidates"` == 실제 Mongo 컬렉션명 `mongo_repository.py:79` `self._candidates = self._db["analysis_candidates"]`. 주석의 "Matches the analysis Mongo repository's candidate collection" 정확. ✓
- **§62 불변식**: candidate item은 `micro_evidence`에만, `macro`/`constraints`/`do_not_use` 배제. CANDIDATE_MEMORY ∉ MACRO_NEEDS이므로 항상 micro. ✓
- **D7 no-dedup**: 브리프 §1 정정대로 `needs_review→confirmed/rejected` 전이는 Phase 6이므로 현재 승격 candidate는 needs_review 유지 → canonical·candidate 양쪽 노출 가능. Gate의 `status≠needs_review→stale`은 Phase 6 forward-defense(회귀는 stub으로 실증). ✓
- **배선**: `create_app`가 `_default_context_search_service(analysis=)`(`main.py`) + candidate retriever 주입 + gate `analysis_service=analysis`(`main.py:1422`) + item payload `review_status`(`main.py:1330`). 프로덕션 Gate 호출처는 `/context-search` 단一处(`main.py:1420`)이고 `analysis_service` 주입 — candidate가 프로덕션에서 `candidate_gate_unconfigured`로 잘못 거부되지 않음. ✓

#### Boundary matrix — 9 cell 전부 테스트에 매핑(`tests/test_context_search_candidate_memory.py`)

| # | 계약 분기(should / should-NOT fire) | 테스트 | line |
|---|---|---|---|
| 1 | candidate는 micro에, CANDIDATE 라벨·pointer·review_status; macro/constraints/do_not_use는 비어야(§62) | `test_candidate_lands_in_micro_labeled_with_candidate_pointer` | 178 |
| 2 | retriever 미주입 → 빈 step, 무실패(NOT degrade) | `test_unwired_retriever_yields_empty_without_failure` | 194 |
| 3 | retriever 예외 → BACKEND_ERROR step failure, search 비-crash | `test_retriever_failure_maps_to_backend_error_without_crashing` | 202 |
| 4 | retriever는 needs_review-only + limit(promoted 제외) | `test_returns_needs_review_only_and_respects_limit` | 218 |
| 5 | Gate: needs_review candidate → PASS | `test_needs_review_candidate_item_passes` | 272 |
| 6 | Gate: missing/타프로젝트 → REJECT stale(under-strict) | `test_missing_candidate_is_stale` | 277 |
| 7 | Gate: status≠needs_review → REJECT stale(forward-defense, over-strict) | `test_no_longer_needs_review_candidate_is_stale` | 283 |
| 8 | Gate: analysis 미주입 → REJECT candidate_gate_unconfigured | `test_unconfigured_analysis_service_rejects` | 291 |
| 9 | 비-candidate-origin의 candidate-status → REJECT candidate_item_not_allowed(v1.6.48 보존, over-strict) | `test_candidate_status_on_non_candidate_origin_still_rejected` | 298 |

- **빈 cell 없음** — 브리프 검증 계획이 열거한 모든 분기(pass/missing-stale/status-stale/unconfigured/비-candidate-origin 거부/retriever 예외/§62)가 named test로 lock됨. ✓
- **v1.6.48 candidate 금지 회귀 보존**: v1.6.48 lock `test_candidate_status_memory_item_still_rejected`(`tests/test_context_search_canonical_memory.py:311`, memory-origin candidate-status 거부)가 (a) 이후에도 무변 통과(감사자 실행 확인). 신규 cell #9가 동일 계약을 candidate-origin 외 관점에서 추가 lock. ✓

#### mutation 양방향 — 감사자가 직접 실행하여 확인

- **Mutation 1**(`_gate_candidate_findings`의 `status is not NEEDS_REVIEW → stale` 분기 무력화): `test_no_longer_needs_review_candidate_is_stale`가 `AssertionError: 'pass' != 'reject'`로 **FAIL**(under-strict — forward-defense가 없으면 promoted candidate가 통과). ✓
- **Mutation 2**(candidate-origin narrowing을 전역 금지로 되돌림: `and not is_candidate_origin` 제거):
  - `test_needs_review_candidate_item_passes` **FAIL**(narrowing이 load-bearing — candidate가 거부됨). ✓
  - `test_candidate_status_on_non_candidate_origin_still_rejected` **PASS**(over-strict 보존 — narrowing 되돌려도 비-candidate-origin 거부는 유지). ✓
  - 양방향 모두 확인: narrowing이 필요함(pass 방향) + 동시에 over-strict(비-candidate-origin 거부)를 약화시키지 않음.

### Surface 4 — 전체 스위트·smoke envelope 재계산

- **전체 실행**: `python3 -m pytest -q` → **4 failed, 630 passed, 45 skipped, 99 subtests passed**(16.28s).
- **4 failed = mongo env artifact**: 전부 `tests/test_memory_mongo.py::MongoMemoryRepositoryTest`(`pymongo` `create_index` → 네트워크 명령 실패, sandbox에 Mongo 서버 없음). `git diff --name-only e8ba45a^..f61d29a -- services/`에 `memory/` 파일 **없음** → (a)/(e)가 원인 아님. v1.6.48 changelog(ce60cdb)부터 "비차단 #3 env artifact(무조치)"로 문서화, SoT v1.6.50 항목 "(mongo env 제외)" 표기와 정합.
- **smoke envelope**: "630 passed / 45 skipped" 주장 — 감사자 실행이 정확히 630 passed / 45 skipped(4 failed는 mongo env로 제외). 주장 충실. ✓
- **`git diff --check`**: clean(mutation 복원 후 전 tree). ✓

## Issues / Risks

- **이슈 #1(비차단, doc)**: `HANDOFF.md:99` Project Structure의 SoT 버전 주석이 `v1.6.48`로 stale(실제 v1.6.50, line 8은 정확). (e)/(a)가 버전을 올리며 놓침.
- **이슈 #2(비차단, doc)**: `HANDOFF.md:107` daily_logs 범위가 `…2026-07-07`로 2026-07-08 누락.
- **이슈 #3(비차단, test-coverage)**: (e) `/run` 502 회귀가 stub runner 사용. 실제 extractor→runner→endpoint 체인(ProviderError wrap 없음 → 502)은 코드 검사로 정확히 확인했으나, e2e failing-provider 테스트로 lock되지 않음. 종점 매핑은 lock됨.
- **위험(경계, 비차단)**: (a) Gate의 origin 분기는 `pointer.collection` 기반. 향후 새 collection이 origin으로 들어오면 `else`(source-block `_gate_stale_findings`)로 떨어져 의도치 않은 검증을 받을 수 있음. 현재 3 collection(source_blocks/memory_entries/analysis_candidates)만 존재하므로 당장 문제 아님 — forward concern.
- **차단 사항 없음**: boundary matrix 빈 cell 없음, 계약↔코드↔테스트 literal 불일치 없음, mutation 양방향 모두 작동, v1.6.48 계약 보존 확인.

## Verdict

**합격(pass)** — 세 커밋 모두.

- (1) HANDOFF 정리: 정보 손실 없이 이력을 참조로 위임, Project Structure 드리프트 교정 정확. 2개 doc nit(버전 주석·daily_logs 범위)은 비차단.
- (e) v1.6.49: "부채 stale" 핵심 주장 참(커밋 전 상태에서 독립 확인). 실제 체인 502 매핑 코드 검사로 확인. mutation 양방향 작동. 회귀 lock은 종점 매핑에 머물러도 동작은 정확.
- (a) v1.6.50: 브리프 D1–D7·안전선(§62)·Gate 재편(좁힘, 폐지 아님)이 코드와 정합. boundary matrix 9 cell 전부 named test로 lock, 빈 cell 없음. mutation 양방향 확인. v1.6.48 candidate 금지 회귀 보존. 교차 프로젝트 누출 방어 실재.

load-bearing 이유: (a)의 핵심 안전 정정("전역 candidate 금지 → candidate origin만 예외 좁힘")이 Mutation 2로 양방향 실증됐고(narrowing 없으면 pass 못 함 + over-strict 보존), (e)의 "stale 부채"가 커밋 전 코드 대조로 참임이 확인됐다.

## Outstanding items

- (비차단) HANDOFF line 99 SoT 버전 주석 v1.6.48→v1.6.50, line 107 daily_logs 범위 `…2026-07-08`로 갱신 권장(오너 판단).
- (비차단) (e) e2e failing-provider through real extractor 회귀 추가 여부(오너 판단 — 종점 매핑은 이미 lock됨).
- 오너가 다음 slice(b/c/d/e)를 선택 대기 중(HANDOFF Next Tasks #1). 본 검증은 slice 선택에 영향을 주지 않음 — 다음 slice 착수 가능.
- 작업 tree는 clean(검증 중 mutation은 전부 복원). 새 커밋 불필요(검증 기록만 본 파일로 추가).

## 후속 보강 (2026-07-08, 오너 지시로 비차단 3건 폐쇄)

감사 직후 오너가 "보강할 부분 보강한다음 커밋"을 지시하여 비차단 이슈 3건을 모두 폐쇄했다(상세: `docs/daily_logs/2026-07-08/work_log.md` "검증 후속 보강").

- **이슈 #1**: `HANDOFF.md:99` SoT 버전 주석 `v1.6.48`→`v1.6.50` 정정.
- **이슈 #2**: `HANDOFF.md:107` daily_logs/verifications 범위 `…2026-07-07`→`…2026-07-08` 갱신.
- **이슈 #3**: `tests/test_analysis_runner.py::…test_runner_provider_error_propagates_unwrapped_as_provider_error` 추가 — 실제 `AnalysisExtractionAdapter`에 ProviderError-raising provider를 물려 extractor→runner 체인(비-wrap 전파 + `provider_error` 매핑 + 원예외 재던짐)을 e2e로 lock. mutation(extractor가 ProviderError를 wrap)으로 load-bearing 실증. 이로써 extractor→runner→endpoint 전 체인이 회귀로 잠김(종점 매핑은 기존 stub 테스트 유지).
- 재검증: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **631 passed / 45 skipped**(630 → +1). `git diff --check` clean.
- 경계 위험(Gate origin `else` fallback)은 forward concern으로 무조치(오너 판단 반영).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 전체 스위트(630 passed / 45 skipped / 4 mongo-env fail 재현)
python3 -m pytest -q

# 2. (a)+(e) 타깃 회귀 + v1.6.48 candidate 금지 lock
python3 -m pytest tests/test_context_search_candidate_memory.py \
  tests/test_context_search_api.py tests/test_application_api.py \
  tests/test_context_search_canonical_memory.py -q

# 3. (a) Mutation 1 — Gate status-check 무력화 → forward-defense FAIL
F=services/application/app/context_search/service.py; cp "$F" /tmp/b.py
python3 -c "import pathlib,pathlib; p=pathlib.Path('$F'); s=p.read_text(); t='    if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:\n        return (\n            GateFinding(\n                check=\"stale_item\",\n                detail=f\"candidate {item.pointer.document_id} is no longer \"\n                f\"needs_review (status {candidate.status.value})\",\n            ),\n        )\n    return ()'; p.write_text(s.replace(t,'    # MUT\n    return ()'))"
python3 -m pytest tests/test_context_search_candidate_memory.py::CandidateMemoryGateTest::test_no_longer_needs_review_candidate_is_stale -q
cp /tmp/b.py "$F"  # restore

# 4. (a) Mutation 2 — narrowing 되돌림 → pass FAIL + over-strict PASS
python3 -c "import pathlib; p=pathlib.Path('$F'); s=p.read_text(); p.write_text(s.replace('if item.status is ContextItemStatus.CANDIDATE and not is_candidate_origin:','if item.status is ContextItemStatus.CANDIDATE:'))"
python3 -m pytest 'tests/test_context_search_candidate_memory.py::CandidateMemoryGateTest::test_needs_review_candidate_item_passes' \
  'tests/test_context_search_candidate_memory.py::CandidateMemoryGateTest::test_candidate_status_on_non_candidate_origin_still_rejected' -q
cp /tmp/b.py "$F"  # restore

# 5. (e) Mutation 3a — 명시 ProviderError 분기 제거 → detail assert FAIL(상태는 502)
python3 -c "import pathlib; p=pathlib.Path('$F'); s=p.read_text(); old='        except ProviderError as exc:\n            # A Gateway/provider failure (timeout/unavailable/5xx) raised by\n            # the planner'\''s provider turn is an LLM-tier error → llm_error →\n            # 502 at the HTTP boundary. This is the context-search counterpart\n            # of the compare endpoint'\''s explicit \`\`except ProviderError\`\` (the\n            # provider call lives at the service layer here, so the Context\n            # SearchFailed lineage is applied here, not at the endpoint). The\n            # generic catch below would also reach llm_error; this explicit\n            # branch keeps the intent legible and refactor-safe.\n            raise ContextSearchFailed(\n                ContextSearchErrorType.LLM_ERROR,\n                f\"planner provider error: {exc}\",\n            ) from exc\n        except Exception as exc:'; p.write_text(s.replace(old,'        except Exception as exc:'))"
python3 -m pytest 'tests/test_context_search_api.py::ContextSearchApiTest::test_planner_provider_error_maps_to_502_llm_error' -q
cp /tmp/b.py "$F"  # restore

# 6. 최종 — tree clean 확인
git diff --check && git diff --quiet && echo "clean"
```

> 참고: 위 mutation 스크립트는 literal 문자열 치환으로, 본 검증 당시의 코드 텍스트와 정확히 일치할 때만 작동한다. 코드가 바뀌면 치환 대상 문자열을 해당 시점의 diff에서 재추출해야 한다. 본 검증에서는 각 mutation 후 `git diff --quiet`로 복원을 확인했다.
