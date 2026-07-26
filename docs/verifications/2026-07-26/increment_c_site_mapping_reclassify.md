# 독립 검증 — 관측 KPI 증분 C (site 매핑 · scope 개방 · 최종 거부 재분류)

## Subject metadata

- **날짜**: 2026-07-26
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증자 (Claude, 별개 세션)
- **대상 슬라이스**: 관측 KPI 증분 C — `call_site` 리터럴 5→8, scope 개방 경로 2→9(+worker), repair 구조 site의 최종 거부 `parse_error` 재분류. SoT v1.7.47.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.47 §"LLM 파이프라인 관측(KPI)" (361–400줄), v1.7.47 변경이력 (36줄). 결정 브리프 `docs/plans/observability-site-mapping-decisions.md` (D1·D2·D3·D4 전부 추천안 채택, Approved 2026-07-26).
- **작업 소스**: 작업 트리, **미커밋** (오너 요청 없음). `git diff HEAD` 대상 6개 파일 + 신규 3개(`tests/test_llm_call_sites.py`, `docs/plans/observability-site-mapping-decisions.md`, `docs/daily_logs/2026-07-26/work_log.md`).

## Scope

정본 계약 스코프(SoT §"LLM 파이프라인 관측(KPI)" 및 v1.7.47 변경이력이 명시적/참조로 묶는 범위)에서 아래 표면을 검증:

1. **계약 본문 절**(SoT 361–400) — call_site 8종 리터럴·site별 `outcome` 범위·scope 개방 경로 목록·재분류 규칙·`correlation_id` 집계 규칙·알려진 공백. 절 내 자기 모순 탐지 포함.
2. **구현 코드** — `observability/llm_call_scope.py`(`reclassify_last_as_parse_error`, `llm_call_scope`, `_flush`, `ObservedProvider`), `observability/llm_call_audit.py`(`LlmCallSite` enum), `main.py`(조립 6곳 + endpoint `with llm_call_scope` 7경로 + `_reclassify_planner_parse_error` 헬퍼), `writing/generation_worker.py`(worker scope 개방 + 인라인 재분류).
3. **회귀 테스트** — `tests/test_llm_call_sites.py`(신규 32 케이스 / 7 subtest). 각 케이스가 계약의 어느 분기를 잠그는지, under-strict/over-strict 양방향 가드 존재 여부, parametrized 경계값 커버리지.
4. **공개 계약** — `frontend/openapi.json`·`frontend/src/api/schema.d.ts` 무변 여부(`gen:api` 재생성 대비).
5. **전체 회귀 스위트** — 증분 전후 증감 실측.

## Methodology

스코프된 계약 읽기 → boundary matrix 구축 → 매트릭스 각 셀을 코드·테스트·실행으로 채우는 순서. "틀렸다 until 깨뜨리는 데 실패" 스탠스.

**정확한 명령**:

- 코드/계약/테스트 정적 독해: `Read`, `git --no-pager diff HEAD -- <file>`, `grep`.
- 계약 자기 모순 탐지: SoT 361–400 줄 end-to-end 독해 후, site별 `outcome` 범위(380–387) ↔ 재분류 규칙(394–400) ↔ 리터럴 목록(366) 교차 대조.
- 신규 회귀 실행: `python3 -m pytest tests/test_llm_call_sites.py -q` → `32 passed, 7 subtests passed`.
- 전체 회귀 실행(백그라운드): `python3 -m pytest tests/ -q -p no:cacheprovider`.
- 공개 계약 재생성·비교: `python3 scripts/dump_openapi.py > /tmp/openapi_regenerated.json` 후 `python3`(정규화 JSON) 동치 비교 (`jq` 없어서 python `json.load`로 대체).
- **mutation 5종 (cp 백업 → Edit → 해당 테스트 실행 → diff -q 복원)** — under-strict 3(M1·M4·M5), over-strict 2(M2·M3):
  - **M1**: `main.py` compare endpoint의 `scope.reclassify_last_as_parse_error(...)` 호출 삭제 → `EndpointReclassifiesTheFinalRejectionTest::test_compare_endpoint_marks_the_finally_rejected_verdict` + `ParseErrorReclassificationTest`/`CompareJudgeRecordsEveryTurnTest` 동시 실행으로 "endpoint 호출" vs "scope 객체" 잠금 분리 실증.
  - **M2**: `llm_call_scope.py` `reclassify_last_as_parse_error`의 `if outcome is not SUCCESS: return` 가드 삭제 → `test_a_provider_failure_is_never_relabelled_as_parse_error`.
  - **M3**: `main.py` `_reclassify_planner_parse_error`의 `if error_type is LLM_ERROR:` 가드 삭제 → `test_only_the_llm_error_lineage_reclassifies`.
  - **M4**: `generation_worker.py` `with llm_call_scope(c.llm_call_audit, …)` → `llm_call_scope(None, …)` → `GenerationWorkerOpensAScopeTest`.
  - **M5**: `main.py` `_build_report_service`의 `WRITING_REPORT` → `WRITING_GENERATION` → `SiteAssemblyIsInstrumentedTest` report 2건.
  - 각 mutation 후 `cp /tmp/<file>.bak <file>` + `diff -q`로 복원, 마지막에 신규 파일 재실행(32/7)로 무결성 확인.

## Findings

### 1. 계약 본문 절 (SoT 361–400)

- **call_site 리터럴 8종** (366줄): `query_planner`·`writing_gate`·`compare_judge`·`analysis_extractor`·`writing_generation`·`writing_retrieval_planner`·`writing_revision`·`writing_report`. 코드 `llm_call_audit.py:42-62`와 1:1 일치, 테스트 `test_llm_call_sites.py:944-953`가 `{site.value for site in LlmCallSite}` 집합으로 전수 고정. **신규 3종(`writing_retrieval_planner`·`writing_revision`·`writing_report`)의 비가역성 근거**(367줄)가 브리프 D1·D2와 정확히 대응.
- **site별 `outcome` 범위** (380–387) ↔ **재분류 규칙** (394–400) 자기 모순 탐지: **모순 없음**. `analysis_extractor`만 "둘"(재분류 안 함, 380·396), 나머지 7 site는 "셋"(재분류함, 381–387·397). 코드의 재분류 호출 지점이 이 분할과 정확히 일치(아래 §3).
- **scope 개방 경로** (388줄): 9 endpoint + worker. 코드 `main.py`의 `with llm_call_scope(...)` 7경로 신규 추가(compare·context-search·generate·report·revise·revise-and-gate·accept) + 기존 2(run·gate) + `generation_worker.py:83` worker = 10. 계약 9 endpoint + worker와 일치.
- **`correlation_id` 집계 규칙** (392줄): "site와 함께 읽는다". `revise-and-gate` 1요청 = 4 site를 같은 `correlation_id`로 묶는 회귀(`test_revise_and_gate_endpoint_scopes_every_site_in_the_loop`, 584–617줄)가 이 규칙을 잠금.
- **알려진 공백** (393줄): "loop 내부 gate 레코드에는 `decision`·`gate_quality_score`가 없다". 계약이 명시적으로 공백으로 기록 — 메우지 않고 계약에 적은 것은 CLAUDE.md("spec-silent 갭은 계약 개정") 정신에 부합. 작업 AI 보고와 일치.
- **planner 계보 4종** (399줄): "네 계보(`llm_error`·`backend_error`·`system_error`·`sot_error`)". `context_search/models.py:65-71`의 `ContextSearchErrorType` 4종과 정확히 일치.

### 2. `reclassify_last_as_parse_error` 시행 함수 (`llm_call_scope.py:86-108`)

- 가드 2단: `if not self.calls: return`(102–103줄) + `if self.calls[-1].outcome is not LlmCallOutcome.SUCCESS: return`(104–105줄). D4 계약("마지막 레코드가 `success`일 때만 동작 — `provider_error` taxonomy 보존", SoT 398)과 **문자 그대로 일치**.
- **M2 실증**: 가드(104–105줄) 삭제 시 `provider_error` 행이 `parse_error`로 덮해씌워지고, `test_a_provider_failure_is_never_relabelled_as_parse_error`(281–301줄)가 잡음(`'parse_error' != 'provider_error'`). over-strict 가드 생존 확인.
- `error_type`을 `type(exc).__name__`로 채움(108줄) — provider code를 덮지 않고 도메인 예외명을 싣는 구조가 docstring(89–100줄) 설명과 일치.

### 3. `_reclassify_planner_parse_error` 헬퍼 (`main.py:452-465`)

- `if exc.error_type is ContextSearchErrorType.LLM_ERROR:` 단일 조건(465줄) → SoT 399("llm_error 계보일 때만")과 일치.
- **M3 실증**: 가드 삭제 시 `BACKEND_ERROR`·`SOT_ERROR`가 `parse_error`로 오엩되고, `test_only_the_llm_error_lineage_reclassifies`(316–341줄)의 2 subtest가 잡음(`'parse_error' != 'success'`), `LLM_ERROR` 케이스는 통과. 양방향 가드 생존 확인.
- 모든 context-package-building endpoint(compare 제외 6곳: context-search 3424·generate 3480·report 4106·revise 4726·revise-and-gate의 retrieval 분기 5730·accept 4928, 그리고 gate 3856)가 이 헬퍼 또는 직접 `reclassify_last_as_parse_error`를 호출 — SoT 397 재분류 site 목록과 1:1.

### 4. 조립(감싸기) 6곳 (`main.py`)

- compare judge(656–663)·context planner(867–874)·retrieval planner(739–746)·generation(706)·report(714)·revision(727) 전부 `ObservedProvider(inner, call_site=…)`로 감쌈. 리터럴이 각 site와 정확히 대응.
- **D2 핵심**(SoT 369): `_default_writing_service`가 generation과 reporter를 **같은 gateway provider 인스턴스**에서 각각 다른 라벨로 감쌈(706–714). 한 번만 감싸면 self-report가 generation으로 뭉개지는 비가역성을 회피.
- **M5 실증**: `_build_report_service`의 `WRITING_REPORT` → `WRITING_GENERATION` 교체 시 `test_report_assembly_is_wrapped`·`test_generation_and_its_reporter_are_wrapped_as_different_sites`(163–179줄) 2건이 잡음. D2 분리 회귀 생존 확인.

### 5. endpoint 재분류 회귀 7건 (`EndpointReclassifiesTheFinalRejectionTest`)

- **M1 실증(핵심)**: compare endpoint의 `scope.reclassify_last_as_parse_error(...)`(main.py 2990 근처) 삭제 시 `test_compare_endpoint_marks_the_finally_rejected_verdict`(660–684줄)이 잡음(`'success' != 'parse_error'`). 동시에 **scope 객체 레벨** 테스트(`ParseErrorReclassificationTest` + `CompareJudgeRecordsEveryTurnTest`)는 **8 passed**로 무관하게 통과. 이것은 작업 AI의 통찰("재분류를 scope 객체 위에서만 검증하면 endpoint의 *호출*을 못 잡는다")을 독립 실증한 것 — endpoint 7건이 reclassify *호출*을 잡고, scope 단위 테스트만으로는 부족함이 확인됨.
- 7건이 SoT 397의 재분류 site 7종(compare·query_planner·generate·report·revise·loop 내 report/gate·accept)을 커버.

### 6. worker scope 개방 (`generation_worker.py`)

- `execute_generation_job`(76–146) 전체를 `with llm_call_scope(c.llm_call_audit, project_id=job.project_id, correlation_id=job.request_id)`로 감쌈(83–84). `c.llm_call_audit`가 `None`이어도 scope 객체는 유효하고 `_flush`(139–145)가 audit=None 시 return하므로 no-crash — SoT 390와 일치.
- **M4 실증**: `c.llm_call_audit` → `None` 교체 시 `test_worker_records_the_generation_it_runs`(903–921줄)이 잡음(빈 집합 ≠ 예상), `test_worker_without_an_audit_records_nothing_and_still_runs`(923–941줄)은 통과. "감싸기+scope 함께" 규칙의 worker 면이 살아있음 확인.
- worker의 planner 재분류 로직이 인라인(134–136줄)으로 헬퍼 `_reclassify_planner_parse_error`를 복제 — 동작은 동일하나 DRY 위반(아래 Hardening).

### 7. 공개 계약 무변

- `frontend/package.json`의 `gen:api` = `dump_openapi.py > openapi.json && openapi-typescript openapi.json -o schema.d.ts`.
- `python3 scripts/dump_openapi.py` 재생성 → `python3` 정규화 비교: **`openapi.json` 재생성 == 커밋본 (NO DIFF)**. `openapi.json`이 무변이면 `schema.d.ts`도 파생 무변. 작업 AI 보고 실증.
- call_site 리터럴은 공개 계약에 노출되지 않음(내부 enum) — `grep` 매칭은 `/writing/report` endpoint의 `operationId`뿐.

### 8. 전체 회귀 증감

- 검증자 환경(WSL2, 드라이버 일부 부재): **1455 passed / 80 skipped / 600 subtests, 실패·에러 0** (47.65s).
- 신규 파일 단독: **32 passed / 7 subtests** — 작업 AI 보고 +32/+7과 정확히 일치.
- subtests 600 = 작업 AI 보고와 **정확히 일치**.
- passed 차이 76(1531−1455) = **skip 정책 차이**로 완전 설명: 검증자 환경 skip 80, 작업 AI 보고 skip 4. 80−4=76. HANDOFF.md가 이미 "skip 수는 머신마다 다르다(elasticsearch 패키지 부재 시 lexical retrieval 3건 + live Chroma 1건)"라고 명시한 내용 — 교차 검증됨. "설명되지 않는 증감 0" 주장 유효.

### 9. 작업 AI 자기 보고 교차 검증 (work_log.md / HANDOFF.md)

- **git checkout 사고**(work_log 116–120줄): mutation 되돌리기에 `git checkout <path>`를 써 `main.py` 미커밋 변경 17곳을 통째로 날림 → 전량 복구, 이후 cp 백업 전환. 투명하게 기록됨. 검증자도 동일 사고 위험을 인지하고 cp 백업(`diff -q` 복원 확인)으로 진행.
- **endpoint 회귀 7건 추가 근거**(work_log 84–86줄): "D4는 계약 필수 분기이므로 차단" — M1 실증과 동일 근거.
- **`_EndpointHarness` mixin**(work_log 87–89줄): 상속 중복 실행 → mixin 분리로 회귀 증감 대조 정확성 유지(코드 449–457줄 주석과 일치).
- HANDOFF v1.7.46→v1.7.47 승격·8종 계측 완료·재분류 규칙·correlation_id 규칙·loop 공백·회귀 기준선 1531/600 갱신 — 전부 코드·SoT와 일치.

## Issues / Risks

### Blocking (계약 의무)

**없음.** boundary matrix의 계약 필수 분기(should fire / should NOT fire) 전부가 명명된 회귀 테스트에 매핑되며, mutation 5종으로 각 잠금의 양방향 생존을 실증했다. SoT 절 내 자기 모순 없음. 공개 계약 무변 실측. 회귀 실패·에러 0.

### Hardening recommendations (non-blocking)

**H-1 — planner 계보 parametrized 4번째 경계값(`system_error`) 명시 잠금.** SoT 399가 "네 계보(`llm_error`·`backend_error`·`system_error`·`sot_error`)"를 명시적으로 열거하지만, `test_only_the_llm_error_lineage_reclassifies`(`test_llm_call_sites.py:332-336`)는 3계보(`LLM_ERROR`·`BACKEND_ERROR`·`SOT_ERROR`)만 잠그고 `SYSTEM_ERROR`가 빠져 있다. endpoint 변형(`test_planner_lineage_decides_whether_the_plan_row_is_reclassified`, 690–692줄)은 2계보(LLM·BACKEND)만.

- **blocking이 아닌 이유**: 재분류 로직의 실제 분기는 `is LLM_ERROR` 단일 조건(`main.py:465`, `generation_worker.py:135`)의 2-분기(`LLM_ERROR` vs not) 구조다. `BACKEND_ERROR`·`SOT_ERROR`가 이미 not-LLM 경로를 잠갔으므로, `SYSTEM_ERROR`는 같은 코드 경로를 타 묵시적으로 커버된다. `SYSTEM_ERROR`만 단독으로 깨지려면 코드가 매우 기묘하게 변해야 하므로 실질 회귀 경로가 아니다.
- **권장 이유**: SoT가 명시적으로 네 계보를 나열한 만큼, 네 번째도 parametrized 케이스로 명시 잠금하면 계약(열거)↔코드(분기)↔테스트(경계값) 삼위일체가 완성되고, 향후 `SYSTEM_ERROR`를 별도 분기로 세분화할 때 회귀를 잡는다. 한 줄 추가(`(ContextSearchErrorType.SYSTEM_ERROR, LlmCallOutcome.SUCCESS),`).

**H-2 — worker의 planner 재분류 로직 인라인 복제 → 헬퍼 통합.** `generation_worker.py:134-136`이 `if exc.error_type is ContextSearchErrorType.LLM_ERROR: scope.reclassify_last_as_parse_error(...)`를 인라인으로 처리하는데, 이는 `main.py:452-465`의 `_reclassify_planner_parse_error` 헬퍼와 동일 로직의 복제다.

- **blocking이 아닌 이유**: 동작은 동일(둘 다 `is LLM_ERROR` 가드 + `reclassify_last_as_parse_error`). SoT가 이를 계약으로 명시하지 않음.
- **권장 이유**: 두 복제가 어긋나면 worker와 endpoint의 planner 재분류 정책이 조용히 갈라진다. 헬퍼를 공통 모듈(예: `llm_call_scope` 또는 별도 유틸)로 빼면 양쪽이 한 군데를 따른다. 단, worker→main.py import는 순환 위험이 있으므로 헬퍼를 `llm_call_scope.py`나 새 유틸로 옮기는 것이 깔끔하다.

## Verdict

**합격 (pass).**

이유(유효 하중):
1. 계약 필수 분기 전부가 명명된 회귀로 잠겼고, mutation 5종(under-strict 3·over-strict 2)이 각 잠금의 양방향 생존을 실증. 특히 **M1은 작업 AI의 핵심 통찰("endpoint 재분류 *호출*을 잡려면 endpoint 레벨 회귀가 필요 — scope 객체 단위 테스트로는 부족")을 독립 재현**했고, 이 통찰이 없었으면 compare endpoint 재분류 삭제가 조용히 통과했을 것(작업 AI도 이 갭을 스스로 발견해 7건을 추가했음을 work_log 84–86줄이 뒷받침).
2. SoT §"LLM 파이프라인 관측(KPI)" 절 내 자기 모순 없음. site별 `outcome` 범위·재분류 규칙·리터럴 목록·scope 경로가 상호 일관.
3. 공개 계약 무변을 실측(`openapi.json` 재생성 == 커밋본).
4. 회귀 1455 passed/600 subtests(검증자 환경); subtests 600과 신규 32/7은 작업 AI 보고와 정확히 일치, passed 차이 76은 HANDOFF가 명시한 머신별 skip 정책으로 설명.
5. 작업 AI 자기 보고(git checkout 사고·endpoint 회귀 추가 근거·mixin 분리)가 코드·work_log와 투명하게 일치.

Hardening 2건(H-1 `system_error` 명시 잠금, H-2 worker 헬퍼 통합)은 모두 동작이 이미 보장된 경로의 계약 충실도·유지보수성 제안이며, 계약이 요구하는 잠금이 빠진 것이 아니다.

## Outstanding items

- **미커밋 작업**: 오너 요청 없음. 6개 수정 파일 + 신규 3개가 작업 트리에 보존 중. 검증자는 mutation 복원 후 `diff -q`로 원본 일치를 확인했으므로 작업 트리는 검증 시작 시점과 동일.
- **오너 결정 대기 2건**(HANDOFF "Owner Decisions Needed"에 기록됨): ① `analysis_extractor`를 D4로 정렬할지(v1.7.46 결정 유지 vs v1.7.47의 나머지 7 site와 정렬), ② loop의 round별 gate decision 노출(loop 내부 gate 레코드에 파생점수를 얹을 수 있는 유일한 경로, D2-B와 연계). 둘 다 도메인 계약 변경을 동반하므로 별도 증분+이행 무손실 증명 필요.
- **CHANGELOG 미갱신**: 작업 AI가 관측 KPI 페이즈 증분 5건(v1.7.41~46)이 SoT 변경이력에만 기록된 선례를 따랐음. 증분 5(집계 API) 시점에 일괄 반영을 제안 중 — 오너 확인 사항.

## Reproduction

```bash
# 1. 신규 회귀 (32/7)
python3 -m pytest tests/test_llm_call_sites.py -q

# 2. 전체 회귀 (skip 수는 머신마다 상이)
python3 -m pytest tests/ -q -p no:cacheprovider

# 3. 공개 계약 무변 실측
python3 scripts/dump_openapi.py > /tmp/openapi_regenerated.json
python3 - <<'PY'
import json
a=json.load(open("frontend/openapi.json")); b=json.load(open("/tmp/openapi_regenerated.json"))
print("NO DIFF" if a==b else "DIFF")
PY

# 4. mutation (cp 백업 → Edit → 실행 → 복원). 예: M1
cp services/application/app/main.py /tmp/main.py.bak
# Edit: compare endpoint의 scope.reclassify_last_as_parse_error(...) 줄 삭제
python3 -m pytest "tests/test_llm_call_sites.py::EndpointReclassifiesTheFinalRejectionTest::test_compare_endpoint_marks_the_finally_rejected_verdict" -q  # → FAILED
python3 -m pytest "tests/test_llm_call_sites.py::ParseErrorReclassificationTest" -q  # → 8 passed (무관)
cp /tmp/main.py.bak services/application/app/main.py && diff -q services/application/app/main.py /tmp/main.py.bak  # 복원
```
