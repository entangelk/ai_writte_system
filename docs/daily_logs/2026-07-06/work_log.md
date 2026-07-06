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

## Phase 2B.3 착수·구현 (2026-07-06, SoT v1.6.42)

### 착수 결정 브리프 + 오너 결정

- 2B.3 kickoff 브리프 `docs/plans/02b-3-analysis-compare-action-decisions.md`를 작성해 D1~D7 결정을 받았다. 헤드라인 긴장: **D3=A 결정적 scope key(`memory_type+scope_type+scope_id+정규화 name`)가 event/open_question에는 자연 적용 불가**(엔티티 id 없이 서술 텍스트뿐)임을 CLAUDE.md §1대로 surface했다.
- **오너 결정**: D1=A(터미널 JSON 1-turn compare, flat-loop tool-call은 상류 정지로 후속), **D2=A(character만 결정적 name key로 대조, event/open_question은 identity 대조 제외+semantic seam 후속)**, D3=A(하이브리드: 결정적 key→LLM 라벨), D4=A(proposal only, 쓰기는 2B.4), D5=A(scope 저장+승격 시 산출, 2B.1 승격 코드 확장 승인), D6=fixture로 확정(self-exclusion 유지 무게), D7=A(`POST .../jobs/{job_id}/compare`).

### 구현 (4.1→4.2 리듬: 이 증분=계약+fake judge, 실 adapter+live=2B.3.2)

- 변경 파일: `services/application/app/memory/scope.py`(신규), `memory/models.py`·`memory/service.py`·`memory/mongo_repository.py`(scope 필드/승격 산출/round-trip), `context_search/models.py`·`context_search/prior_memory.py`(PriorMemoryItem.scope), `analysis/compare.py`(신규), `main.py`(scope 직렬화·compare endpoint·wiring), `tests/test_memory_scope.py`·`tests/test_analysis_compare.py`·`tests/test_analysis_compare_api.py`(신규).
- **scope key(D2=A)**: `derive_scope(memory_type, payload)` — character만 `MemoryScope("character", 정규화(name))`(공백 collapse + casefold로 "Ariel Song"="  ariel   song"), event/open_question은 `None`. `MemoryEntry`에 `scope` 필드(default None) 추가하고 2B.1 승격이 산출(D5=A). Mongo `_memory_doc`/`_to_memory` round-trip과 HTTP `_memory_payload`에 scope 포함.
- **§8 ⑧ 완전 완성**: `PriorMemoryItem.scope` 추가로 taxonomy가 위임한 scope까지 채워졌다(2B.2가 "5필수 완성"으로 남긴 추적 항목 폐쇄).
- **compare(D1/D3=A)**: `AnalysisCompareService.compare_job`이 job candidate별로 결정적 scope 매칭 → (a) 매칭 0개=`create`(결정적, event/question은 scope 없어 항상 여기), (b) 1개=주입 `CompareJudge`(sync/async seam)가 `update/add_evidence/no_change/conflict` 라벨(judge가 `create` 반환 시 `InvalidJudgeResult`로 거절 — create는 no-match 결정적 전용), (c) 복수 canonical 동일 identity=결정적 `conflict`(2B.1이 허용한 중복 canonical을 재조정 신호로 표면화). proposal only(D4=A).
- **D6 self-exclusion 확정(fixture로)**: `_find_matches`가 `analysis_job_id == 대상 job`인 memory를 제외한다. 근거: 같은 job이 승격한 memory가 자기 자신을 prior로 잡으면 항상 no_change 노이즈. 양방향 회귀(`test_self_exclusion_is_two_directional`: 같은 job→제외→create+judge 미호출 / 다른 job→매칭→judge 호출)로 잠갔다. 2B.2의 잠정값을 여기서 "유지"로 확정.
- **HTTP(D7=A)**: `POST /projects/{id}/analysis/jobs/{job_id}/compare`. no-match(create)/multi-match(conflict)는 judge 없이 200. 매칭인데 judge 미구성이면 503(`CompareJudgeNotConfigured`), `InvalidJudgeResult`는 502, missing project/job 404. `create_app`에 `compare_service` 주입 param 추가(기본 judge=None).

### 회귀 19개 + 검증

- `tests/test_memory_scope.py`(5): character scope/정규화(case·whitespace)/event·open_question None/normalize_name.
- `tests/test_analysis_compare.py`(8): no-match create, event 항상 create(prior event 있어도), 1개 매칭→judge 라벨, 정규화 name 매칭, judge 미구성→`CompareJudgeNotConfigured`, **judge의 create 반환 거절(over-strict)**, 복수 canonical→conflict, **self-exclusion 양방향**.
- `tests/test_analysis_compare_api.py`(6): no-match→create(judge 없이 200), 매칭+judge 미구성→503, 주입 fake judge→라벨 proposal, **승격 character memory scope 직렬화(§8 ⑧)**, missing project/job 404.
- 검증: `python3 -m unittest tests.test_memory_scope tests.test_analysis_compare tests.test_analysis_compare_api` → 19 OK. `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **526 passed / 45 skipped**. `git diff --check` 통과. (mongo 3개는 종전 환경 인증 이슈, 무관.)

### 2B.3 검증 후속 보강 (독립 검증 PASS 후)

- 독립 검증 `docs/verifications/2026-07-06/phase_2b_3_compare_action.md` **합격**. non-blocking 관찰 G1~G4 중 코드/문서로 닫을 수 있는 것을 보강.
- **G1(음방향 회귀)**: `test_character_with_different_identity_is_create` 추가 — 다른 이름의 prior character memory는 매칭 안 됨→create, judge 미호출. scope 매칭의 음방향(under-strict는 잠겨 있었으나 명시 음방향 부재)을 채웠다.
- **G2(HTTP 502)**: `test_judge_returning_create_maps_to_502` 추가 — judge가 매칭 pair에 `create` 반환 시 HTTP 502(`InvalidJudgeResult`) 매핑을 API 레벨에서 잠갔다(기존엔 service-layer raise만 검증).
- **G3(문서 정정)**: 브리프 D5 요약표(line 137)가 "scope를 MemoryEntry/candidate/PriorMemoryItem에 저장"으로 상세 결정(line 125: candidate는 즉석 산출, 2A 스키마 미변경)과 갈렸다 → 요약표를 "MemoryEntry/PriorMemoryItem 저장 + candidate 즉석 산출"로 정정(코드는 상세 결정을 따름, `analysis/models.py` 미변경으로 확인).
- **G4(설계 의도)**: 운영 `/compare` judge 미주입 시 매칭 503은 4.1→4.2 리듬으로 투명 명시 — 코드 변경 없음.
- 재검증: 회귀 19→21, `pytest -q --ignore=tests/test_memory_mongo.py` → **528 passed / 45 skipped**, `git diff --check` 통과.

## Phase 2B.3.2 — 실제 Gateway 터미널-JSON compare judge (2026-07-06, SoT v1.6.43)

- 2B.3의 `CompareJudge` seam을 실 adapter로 채웠다(4.1→4.2→2B.3→2B.3.2 리듬, D1=A 터미널 JSON). 변경 파일: `services/application/app/analysis/compare_judge.py`(신규), `main.py`(`_default_compare_service` env wiring), `tests/test_analysis_compare_judge.py`(신규), `tests/test_analysis_compare_api.py`(env factory 회귀 2), `scripts/phase2b3_compare_judge_live_smoke.py`(신규).
- **adapter**: `TerminalJsonCompareJudge`(async)가 versioned prompt `analysis_compare_v1`(task_type `analysis_compare`)로 매칭 (candidate payload + 기존 memory payload)을 Gateway `/v1/generate` 1-turn에 보내 `{"action","rationale"}` JSON을 strict parse. malformed/fenced/out-of-set이면 1회 repair, 그래도 실패면 `InvalidJudgeResult`(→502). 허용 action은 matched-pair 4종(update/add_evidence/no_change/conflict)뿐이고 **`create`는 거절**(no-match 결정적 전용, `_action`이 `JUDGE_ACTIONS` 멤버십 강제). 2A extraction/4.2 planner와 동일 구조(async provider·versioned prompt·single repair).
- **wiring**: `_default_compare_service(memory)`가 env `LLM_GATEWAY_BASE_URL` 있으면 `GatewayGenerateProvider` + seed된 `analysis_compare_v1` 템플릿으로 judge를 붙이고(`ANALYSIS_COMPARE_MAX_TOKENS` 기본 512), 없으면 judge 미주입(매칭 pair 503) — analysis runner/context search planner env-gating과 동일 패턴. `create_app`의 `compare = compare_service or _default_compare_service(memory)`.
- **회귀 13개**: `tests/test_analysis_compare_judge.py`(11) — valid parse, 4종 action 전수(subTest), fenced 1회 repair, unknown action repair→성공, **create 출력 거절(under-strict, repair 후에도 InvalidJudgeResult, 정확히 2 provider 호출)**, bad-shape/non-JSON repair→실패, template 부재→InvalidJudgeResult(provider 미호출), prompt payload에 candidate/memory·allowed_actions에 create 없음, parse 직접(빈 rationale/extra field 거절). `tests/test_analysis_compare_api.py`(+2) — **env 설정 시 `_default_compare_service`가 실 judge wiring→매칭 pair가 update로 라벨**(fake provider 주입, GatewayGenerateProvider 패치), env 부재 시 judge None(over-strict).
- **판정 경계 심화 + live smoke 실행은 후속**: adapter는 parse/repair를 잠갔고, update↔add_evidence↔no_change↔conflict 의미 판정 자체의 fixture 심화와 실제 12B 관통 live smoke(`scripts/phase2b3_compare_judge_live_smoke.py`, sandbox 밖 실행 필요)는 다음이다.
- 검증: `python3 -m unittest tests.test_analysis_compare_judge tests.test_analysis_compare_api` → 20 OK. `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **541 passed / 45 skipped**. `git diff --check` 통과.

## Phase 2B.3.2 독립 검증 후속 보강 (검증자 직접, 2026-07-06)

2B.3.2 독립 검증(`docs/verifications/2026-07-06/phase_2b_3_2_compare_judge.md`, PASS)이 발견한 2건을 검증자가 직접 보강했다(작업자 교체). 변경 파일: `services/application/app/main.py`, `tests/test_analysis_compare_api.py`, `scripts/phase2b3_compare_judge_live_smoke.py`.

- **ProviderError 누출 수정(compare endpoint)**: `GatewayGenerateProvider.generate`가 Gateway 장애(timeout/unavailable/5xx) 시 raise하는 `ProviderError`가 `analysis_compare_endpoint`에서 uncaught → HTTP 500 누출임을 재현으로 확인(매칭 pair의 judge turn에서 발화; 재현은 prior를 별도 job에 넣어 D6 self-exclusion을 우회). v1.6.34 오류 taxonomy(LLM/Gateway error→502)가 이미 정한 매핑을 이 endpoint가 누락한 결함이라 `except ProviderError → 502`를 추가(`main.py`, `ProviderError` import 포함). 회귀 `test_provider_error_during_judge_maps_to_502`(under-strict: catch 제거 시 500 재누출로 재실패; over-strict는 기존 happy-path 200/라벨 회귀가 cover).
- **패턴 수준 부채(수정 X, 추적)**: 같은 `ProviderError` 누출이 `/context-search`(planner 4.2)와 2A extraction adapter에도 있다(`provider.generate` bare 호출, global exception_handler 부재). 2B.3.2 범위 밖이라 이번엔 compare만 고치고 sibling은 HANDOFF Next Tasks에 추적.
- **live smoke 4 경계 강화(J1 후속)**: `phase2b3_compare_judge_live_smoke.py`가 단일 pair만 다루던 것을 matched-pair 4 경계(update/add_evidence/no_change/conflict) 대표 pair로 확장 — 각 경계에서 12B가 실제 낸 action을 per-boundary JSON으로 출력(J1 empirical signal). `ProviderError`도 clean 처리(`provider_error` status + non-zero exit)해 Gateway down 시 crash 대신 상태 출력. py_compile/`--help` 확인(실실행은 sandbox 밖).
- 검증: compare 계열 30 passed(신규 ProviderError 회귀 +1 포함), `pytest -q --ignore=tests/test_memory_mongo.py` → **542 passed / 45 skipped**, `git diff --check` 통과.

## Phase 2B.4 — proposal→실제 memory versioned upsert (2026-07-06, SoT v1.6.44)

### 착수 결정 브리프 + 오너 결정

- 2B.4 kickoff 브리프 `docs/plans/02b-4-memory-versioned-upsert-decisions.md`를 작성해 D1~D7 결정을 받았다. 헤드라인 긴장(CLAUDE.md §1): HANDOFF는 "Chroma 재색인(memory→vector)도 이때"라 묶었으나 **memory→vector 색인 자체가 존재하지 않음**(현재 Chroma/embedding은 source_block만 색인)을 조사로 확인해 surface했다 — 재색인은 임베딩 대상·collection·트리거가 전부 신규인 독립 slice 규모.
- **오너 결정**: D1=A(compare와 분리된 명시 apply, 안전 action 4종만 자동), D2=A(append-only 새 row + supersedes + `superseded` status), D3=추천(update:payload 교체·source union·conf=candidate / add_evidence:payload 보존·source union·conf=max), **D4=A(재색인 분리→2B.5)**, D5=A(`(project,source_candidate_id)` idempotency), D6=A(`POST .../apply`), D7=A(conflict/merge/split review-only).

### 구현

- 변경 파일: `services/application/app/memory/models.py`(`MemoryStatus.SUPERSEDED`·`MemoryEntry.supersedes`), `memory/repository.py`·`memory/service.py`·`memory/mongo_repository.py`(`update_memory` + `_versioned_upsert`/`record_updated_version`/`record_evidence_version` + supersedes round-trip), `analysis/apply.py`(신규 `MemoryApplyService`), `main.py`(apply endpoint·request model·wiring·`_memory_payload` supersedes), `context_search/prior_memory.py`(O1 마커→회귀 문구), `tests/test_memory_apply.py`·`tests/test_analysis_apply_api.py`(신규), `tests/test_analysis_context.py`(O1 회귀), `tests/test_memory_mongo.py`(versioned upsert live round-trip).
- **versioned upsert(D2/D3)**: `_versioned_upsert`는 idempotency 확인(`find_memory_by_candidate`) → target canonical/타입 검증 → 새 canonical(version=prev+1, supersedes=prev.id) put → 이전 entry `superseded` 전이(append-only: 새 version 먼저 삽입 후 이전 supersede). update=payload를 candidate로 교체·conf=candidate·prov=candidate, add_evidence=payload 보존·conf=max·prov=prev, 둘 다 source_ref_ids order-preserving union.
- **apply 오케스트레이션(D1)**: `MemoryApplyService.apply_proposals`가 proposal별로 no_change→쓰기 없음, conflict→skipped_review(D7), create→`promote_candidate(MANUAL)` 재사용, update/add_evidence→versioned upsert. AI 없음(라벨은 2B.3 proposal에서 확정).
- **HTTP(D6)**: `POST /projects/{id}/analysis/jobs/{job_id}/apply`가 검토한 proposal을 body(`{proposals:[{candidate_id,action,matched_memory_id?}]}`)로 받아 반영하고 action별 결과(created/versioned/no_change/skipped_review)를 반환한다. unknown action/candidate 400, missing matched memory·cross-project 404. deterministic이라 env/injection seam 없음.
- **2B.2 O1 폐쇄**: `MemoryStatus.SUPERSEDED` 도입으로 canonical-only prior 필터의 non-canonical 제외 방향이 처음으로 테스트 가능해졌다. `test_superseded_memories_excluded_from_prior_memory` 추가 + 필터 mutation으로 non-vacuity 재실증(필터 무력화 시 재실패, 파일 복원). `prior_memory.py`의 O1 마커 주석을 회귀 참조로 교체.

### 회귀 19개 + 검증

- `tests/test_memory_apply.py`(10): create version=1, create idempotent replay, update(payload 교체·source union·conf/prov·prior superseded·이전 version 불변 보존), update matched 없음→`MissingMatchedMemory`, 타입 불일치→`MemoryError`, update idempotent replay(3번째 version 미생성), add_evidence(payload 보존·source union·conf=max), no_change 무쓰기, conflict skipped_review 무쓰기, unknown candidate→`UnknownCandidate`.
- `tests/test_analysis_apply_api.py`(8): create 200, update 200(supersede·status 전이), 재post idempotent, no_change 무쓰기, unknown action 400, candidate 부재 400, matched memory 부재 404, missing project/job 404.
- `tests/test_analysis_context.py`(+1): O1 superseded 제외(양방향 1케이스).
- 검증: `python3 -m unittest tests.test_memory_apply tests.test_analysis_apply_api` → 18 OK. O1 mutation 재실증(exit 1, 복원). `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **561 passed / 45 skipped**. `git diff --check` 통과.
- **live Mongo**: throwaway `mongo:7`(port 27055)로 `CORE_SOT_TEST_MONGO_URI=... python3 -m unittest tests.test_memory_mongo` → 4 OK(신규 `test_versioned_update_round_trips_supersedes_and_status` 포함, `update_memory` replace_one + supersedes/superseded round-trip 실검증). 컨테이너 정리 완료. (기본 sandbox의 localhost:27017 auth 이슈로 인한 mongo 3(+1) error는 종전과 동일한 환경 문제, 내 변경 무관.)

### 2B.4 검증 후속 보강 (독립 검증 조건부 합격 → 폐쇄)

- 독립 검증 `docs/verifications/2026-07-06/phase_2b_4_versioned_upsert.md`는 **조건부 합격**. 차단 1건(non-canonical target 거절 분기 회귀 부재, boundary matrix #11 빈 셀)과 비차단 관찰(§3/O2/O3)을 보강했다.
- **차단 폐쇄(#11)**: `test_update_of_superseded_target_rejected` 추가 — 서로 다른 candidate 2개가 같은 prior를 순차 update → 두 번째가 superseded(non-canonical) target에 도달 → `MemoryError`. 검증자가 지적한 "도달 가능하나 미잠금" 분기를 실사용 경로로 잠갔다. mutation 재실증: `if target.status is not CANONICAL` guard 무력화 시 재실패(NO RAISE).
- **§3(update confidence over-strict)**: `test_update_takes_candidate_confidence_even_when_lower` 추가 — prior 0.8 > candidate 0.4에서 update 결과 conf=0.4(candidate)임을 잠가 max 규칙과 구분. mutation 재실증: `confidence=max(...)`로 바꾸면 재실패.
- **O2(add_evidence replay)**: `test_add_evidence_is_idempotent_replay` 추가 — update replay와 공유하는 `_versioned_upsert` 상단 replay 체크를 add_evidence 분기에서도 명시(3번째 version 미생성).
- **O3(MissingMatchedMemory-None HTTP)**: `test_update_without_matched_memory_returns_400` 추가 — matched_memory_id 생략(None) 시 HTTP 400(비존재 id→404와 구분).
- **O4(브리프 D7 표현)**: 브리프 D7의 "conflict/merge/split review-only" 표현이 살짝 과대(merge/split은 2B.3 미산출이라 apply에 도달 못 하고 unknown action 400). 브리프 D7 본문에 "merge/split은 2B.3 미산출이므로 실제로는 conflict만 apply에 도달"을 명시(코드/SoT는 종전대로 정합).
- 재검증: `python3 -m unittest tests.test_memory_apply tests.test_analysis_apply_api` → 22 OK. non-canonical/confidence guard mutation 각각 재실패 확인(복원). `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **565 passed / 45 skipped**. `git diff --check` 통과. 회귀 19→23.

## Next steps

- **Phase 2B.5 — memory→vector 재색인**(D4가 분리): apply가 만든 canonical memory version을 vector index에 반영. memory 색인이 미존재라 임베딩 대상 payload·별도 collection·재색인 트리거(inline vs Phase 3B outbox/worker 패턴) 결정 브리프 필요.
- **conflict/merge/split review queue 영속화**(2B.4는 skipped 반환까지), event/open_question 의미적 entity resolution(D2 semantic seam), ⑤ Writing canonical 포함.
- **Phase 2B.3.2 live smoke 실행**(sandbox 밖): `scripts/phase2b3_compare_judge_live_smoke.py`(이제 matched-pair 4 경계 커버)를 실제 llama.cpp 12B endpoint로 돌려 각 경계에서 12B가 내는 action을 관찰·기록. 의미 판정 품질(update↔add_evidence↔no_change↔conflict 구분)이 충분하면 해당 결과로 판정 경계 회귀를 잠그고, 부족하면 prompt `analysis_compare_v1` 개정.
- **Phase 2B.4**: proposal→실제 memory versioned upsert/재색인(Chroma), `MemoryStatus` 두 번째 literal(superseded 등) 도입 시 prior_memory canonical-only 필터의 non-canonical 제외 회귀(2B.2 O1) 추가.
- ⑤ Writing canonical 포함(Gate candidate 금지를 "canonical 허용 + 미승인 candidate 금지"로 정련), event/open_question 의미적 resolution(D2 semantic seam).
- 곁가지(막힘/저우선): worker→real Chroma live smoke(sandbox 밖), ES lexical(브리프 필요), embedding 이미지 최적화(최후순위).
