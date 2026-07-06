# Work Log — 2026-07-06

## Goals

- HANDOFF와 2026-07-05 work log를 읽고 다음 작업(Phase 2B.2 코드 착수)을 진행한다.
- 착수 결정 브리프(`plans/02b-2-analysis-context-package-decisions.md`, Resolved)의 D1~D6과 F3~F5를 추측 없이 구현하고 양방향 회귀로 잠근다.

## Completed work

### Phase 2B.2 — prior-memory 검색 + Analysis 비교용 ContextPackage (§8 ⑧), SoT v1.6.41

- 변경 파일: `services/application/app/context_search/models.py`, `services/application/app/context_search/prior_memory.py`(신규), `services/application/app/main.py`, `tests/test_analysis_context.py`(신규), `tests/test_analysis_context_api.py`(신규), `docs/system-contract-sot.md`, `docs/plans/02b-2-analysis-context-package-decisions.md`.
- **신설 literal**(D1 요약): `ContextSearchPurpose.ANALYSIS_CONTEXT = "analysis_context"`, `ContextNeed.PRIOR_MEMORY = "prior_memory"`.
- **models.py**: `PriorMemoryItem`(memory_id/memory_type/value/status/version/source_ref_ids/match_reason) 추가 — taxonomy 5필수(값·상태·source·version·비교 이유). `value`는 MemoryEntry의 `payload`(Mapping)로 명시(F3, MemoryEntry에 `value` 필드 없음). `scope`는 MemoryEntry 부재라 미포함 → §8 ⑧은 "5필수 완성", scope는 2B.3까지 열림(D3=A, F2 정정과 정합). `AnalysisContextRequest`(project_id/needs/memory_types/exclude_job_id) 추가. `ContextPackage`에 `prior_memories` field 추가하고 `trace`를 optional(`ContextSearchTrace | None = None`)로 완화 — analysis_context는 planner/plan이 없어 trace가 `None`이다(D3=A: 단일 schema, purpose가 어느 section을 채우는지만 분기).
- **prior_memory.py**(신규): 
  - `PriorMemoryBackend` Protocol = D2=A semantic seam. 현재는 `DeterministicPriorMemoryBackend`(같은 project·같은 `memory_type`의 canonical `MemoryEntry` 결정적 조회, MemoryService 위)만 제공하고, 후속 LLM 의미검색이 같은 인터페이스로 교체된다.
  - `AnalysisContextService.build_prior_memory_package(request)` = 검색+패키징만(D1=A). purpose=analysis_context, macro/micro/trace 비움, `prior_memories`만 채움. `needs`는 `prior_memory`만 허용(그 외 `InvalidAnalysisContextRequest`).
  - 빈 `memory_types` → 빈 package(비교 대상 없음). "절대 전체를 반환하지 않는다"는 안전 기본값(job에 candidate가 없으면 비교 대상 0). backend에 `if not wanted: return ()` 명시 + 회귀로 잠금.
  - **F4 self-exclusion**: `exclude_job_id`가 주어지면 `analysis_job_id == exclude_job_id`인 memory 제외. 2B.1 auto-promote로 같은 job이 승격한 memory가 자기 자신을 prior로 잡는 것을 막는다. **오너 승인 잠정값** — 2B.3 compare(no_change/충돌)와의 상호작용을 실구현에서 관찰한 뒤 self-exclusion 유지 vs no_change 흡수를 확정한다.
  - `evaluate_analysis_context_gate` = D5=A purpose 분기. analysis_context는 canonical만 담아 candidate 금지가 무적용(대상 없음). 유일한 실체 invariant는 Writing item(macro/micro) 누출 차단이다. cross-project 격리는 project-scoped 조회 계약이 보장하므로 재검사하지 않는다(F5) — PriorMemoryItem은 project_id를 담지 않는다(D3 5필드). MemoryStatus가 canonical 단일이라 non-canonical guard는 미도입(불가능 시나리오 방어 회피, CLAUDE.md §2).
- **main.py**(D4=B hybrid + D6=B): `AnalysisContextService(backend=DeterministicPriorMemoryBackend(memory))`를 create_app에서 wiring(결정적이라 env 무관). `POST /projects/{project_id}/analysis/jobs/{job_id}/context` 추가 — job의 candidate types를 조회해 coarse memory_type 집합(중복 제거)을 유도하고, `exclude_job_id=job.id`(F4)로 primitive를 호출한다. missing project/job은 404, invalid request는 400. `/context-search`(Writing 전용)에 purpose guard 추가 — `analysis_context`는 이제 400 거절(두 purpose 표면 분리).

- **회귀 16개**(전부 인프라 없는 fake/in-memory):
  - `tests/test_analysis_context.py`(10): 요청 type의 canonical만 package화, PriorMemoryItem 5필수(value==payload 등), memory_type 필터 양방향(character/event), 빈 memory_types→빈 package(전체 아님), **F4 self-exclusion 양방향**(exclude_job_id로 own 제외 + None이면 둘 다 유지=over-strict 방지), project 격리, needs 검증 2개(빈/non-prior_memory), Gate pass(prior_memory만) + Gate reject(Writing item 누출, `writing_item_in_analysis_package`).
  - `tests/test_analysis_context_api.py`(6): job candidate types 기반 조회 + self-exclusion(현재 job own memory 제외, prior job memory만 반환) + 응답 필드/gate pass, prior 없음→빈 package, job candidate type만 검색(event memory는 character-only job에 안 잡힘), missing project 404, missing job 404, **`/context-search`에 analysis_context purpose→400**.

## Decisions — 2B.2 구현 시 최소 결정 (F5, 작업자)

- **F5(Gate 실제 적용)**: analysis_context 조회는 이미 project-scoped(backend가 project_id로 필터, MemoryService가 project 격리)라 cross-project 격리는 조회 계약이 보장한다. 따라서 별도 cross-project Gate 재검사는 두지 않고(재검사하려면 PriorMemoryItem에 project_id를 추가해야 해 D3 5필드와 충돌), Gate는 purpose 분기 구조를 유지하되 실체 invariant는 "Writing item이 analysis 비교 package로 누출되지 않음" 하나로 최소화했다. 근거: D5=A는 "purpose/단계별 분기 구조"를 결정했고 F5는 "실제 호출 여부를 최소로 결정"하라 했다. 실체 있는 하나의 invariant만 잠그는 것이 과설계(불가능 시나리오 방어)를 피하면서 D5의 분기 구조를 실현한다.
- **요청 계약**: 브리프 D4 권고는 "ContextSearchRequest 재사용 + memory_types optional"이었으나, Writing 요청(query/current_position 필수)에 analysis 전용 필드를 얹으면 Writing 경로가 오염된다. D3=A(단일 *package* schema)는 지키되 request는 전용 `AnalysisContextRequest`로 분리했다(mechanics가 완전히 다름: planner/vector/SOT 없음). package schema는 공유(ContextPackage에 prior_memories), request는 분리 — D3의 "단일 schema"는 package 대상이므로 정합.
- **trace optional**: analysis_context는 SearchPlan/trace가 없다. ContextPackage.trace를 `None` 허용으로 완화했고 Writing 경로는 종전대로 trace를 항상 채운다(회귀 유지 확인).

## User Decisions and Rationale

- 오너가 "바로 진행"을 지시해 2B.2를 착수했다. 착수 결정(D1~D6)은 2026-07-05에 이미 확정돼 있었고 이번엔 그 코드화다. F4 self-exclusion은 오너의 "일단 기본값으로 하되 실구현하며 확인" 입장에 따라 잠정값으로 구현하고 2B.3에서 재확정하도록 문구를 유지했다.

## Verification

- `python3 -m py_compile services/application/app/context_search/{models,prior_memory,service}.py services/application/app/main.py tests/test_analysis_context.py tests/test_analysis_context_api.py` 통과. `create_app()` import 관통 OK.
- 신규 회귀: `python3 -m unittest tests.test_analysis_context tests.test_analysis_context_api -v` → 16개 통과.
- 관련 묶음: `python3 -m unittest tests.test_context_search tests.test_context_search_api tests.test_context_search_planner tests.test_context_search_shared_index tests.test_memory_phase2b tests.test_memory_api tests.test_application_api` → 126개 통과(ContextPackage trace-optional·Writing purpose guard 회귀 없음 확인).
- 전체: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → 506 passed / 45 skipped. `git diff --check` 통과.
- **환경 이슈(내 변경과 무관)**: `tests/test_memory_mongo.py` 3개가 error. 원인은 localhost:27017에 인증이 걸린 Mongo(이전 smoke 잔여)가 떠 있어 skip-aware probe(ping)는 통과하나 `createIndexes`가 `Unauthorized(code 13)`로 실패하는 것. clean HEAD(내 변경 stash 후)에서도 동일하게 3 error 재현 → Phase 2B.2 변경이 아니라 로컬 Mongo 인증 상태 문제. memory Mongo repository 코드는 이번에 손대지 않았다.

## 검증 후속 보강 (2026-07-06, 독립 검증 PASS 후)

- 독립 검증 기록 `docs/verifications/2026-07-06/phase_2b_2_prior_memory_context.md`는 **합격(PASS)**. non-blocking 관찰 O1~O6 중 slice 범위에서 지금 닫을 수 있는 것을 보강했다(O1은 오너 권고대로 강제 미폐쇄).
- **O6(다중-type 합집합/중복제거 회귀 추가)**: `test_job_context_unions_multiple_types_and_dedups_same_type`를 `tests/test_analysis_context_api.py`에 추가. 한 job이 character 2개(dup type)+event 1개 candidate를 가질 때 prior가 두 type 합집합으로 각 1회씩(len==2, {character,event}) 반환됨을 잠갔다 — L14 over-strict 빈 cell을 채웠다(단일 type만 검증되던 것 → 다중 type). 회귀 16→17.
- **O2(dead-code 제거)**: HTTP endpoint의 `except InvalidAnalysisContextRequest → 400` 분기를 제거했다. `needs`가 `(PRIOR_MEMORY,)`로 고정돼 HTTP 경로에서 절대 발생할 수 없는 dead code였다(request 검증은 service layer L9/L10에서 양방향으로 잠겨 있음). CLAUDE.md §2(불가능 시나리오 오류처리 회피)에 맞춰 제거하고, 미사용이 된 `InvalidAnalysisContextRequest` import도 정리했다. 이유 주석을 endpoint에 남겼다.
- **O4(테스트 이름 표기)**: `test_gate_rejects_writing_item_leak_two_directional` → `test_gate_rejects_writing_item_leak`로 개명. 이 테스트는 reject 한 방향만 단언하며 양방향은 `test_gate_passes_prior_memory_only_package`와의 쌍으로 성립한다(주석 명시). 단일 테스트를 "two_directional"로 과대 서술하던 것 정정.
- **O1(추적, 강제 폐쇄 안 함)**: canonical-only 필터의 non-canonical 제외 방향은 `MemoryStatus`가 CANONICAL 단일이라 오늘 테스트 불가. 오너가 "MemoryStatus 확장을 2B.2로 당기지 말라(D1=A/2B.1 위임 존중)"고 했으므로 강제로 닫지 않고, `prior_memory.py`의 필터에 "2B.4가 두 번째 status 도입 시 `test_noncanonical_memories_excluded_from_prior_memory` 추가" 코드 마커를 남겼다. HANDOFF Next Tasks #1(2B.3/2B.4)에도 추적한다.
- **O3/O5(무해, 설계 의도)**: Gate가 HTTP를 hard-block하지 않고 200과 함께 직렬화(2B.3용 정보 신호/defense-in-depth), Writing-item-leak invariant가 단일-status에선 구조적으로 거의 발화 불가 — 둘 다 F5 최소 Gate 결정과 정합하며 코드 변경 없음(오너 인지 사항).
- 재검증: `python3 -m unittest tests.test_analysis_context tests.test_analysis_context_api` → 17 OK. `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **507 passed / 45 skipped**. `git diff --check` 통과.

## Next steps

- **Phase 2B.3 compare→action 판정**: D4 action literal(`create/update/add_evidence/no_change/conflict` + `merge/split` review-only) 실현 + **D3 scope key 산출/매칭**(2B.1·2B.2가 위임한 identity 경계를 여기서 잠금). 이때 `PriorMemoryItem.scope`를 채워 §8 ⑧을 완전 완성하고, F4 self-exclusion 잠정값을 no_change 상호작용 관찰 후 확정한다. provenance/confidence를 PriorMemoryItem에 추가할지도 compare 의존 시 결정(F3).
- 2B.4 versioned upsert/재색인, ⑤ Writing canonical 포함(Gate candidate 금지를 "canonical 허용 + 미승인 candidate 금지"로 정련).
- 2B.2 독립 검증(오너 요청 시): backend seam·F4 self-exclusion 양방향·Gate purpose 분기·`/context-search` purpose 거절을 primary source로 재확인.
- 곁가지(막힘/저우선): worker→real Chroma live smoke(sandbox 밖), ES lexical(브리프 필요), embedding 이미지 최적화(최후순위).
