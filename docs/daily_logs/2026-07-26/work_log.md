# 2026-07-26 작업 로그

## Task — 관측 KPI 증분 C: 잔여 호출부 계측 + site 매핑·scope 범위 결정 (SoT v1.7.47)

### Goals

- HANDOFF가 지정한 다음 작업. 증분 B(gate → seam C 이행)까지 끝난 상태에서 잔여 호출부
  `compare_judge`·`query_planner`·`writing_generation`을 계측한다.
- HANDOFF가 명시한 "새 호출부 3종 세트"(조립에서 감싸기 · 요청 경로 scope 개방 · 조립 가드)를
  각 site마다 적용하고, site별 `outcome` 범위를 계측과 **동시에** 본문에 적는다(v1.7.46 H1의 교훈).

### Issues found — 실측이 계획을 두 곳에서 뒤집었다

착수 전 실측(코드 직독)에서 HANDOFF에 적힌 "3개 site"가 코드 구조와 1:1이 아니었다.

- **리터럴 5개 vs 실제 LLM 어댑터 8개.** `query_planner` 하나에 대응하는 planner가 **둘**이고
  ([`context_search/planner.py:78`](../../../services/application/app/context_search/planner.py#L78) ·
  [`writing/retrieval.py:76`](../../../services/application/app/writing/retrieval.py#L76)),
  writing loop의 **reviser·self-report 호출은 어느 리터럴에도 매핑돼 있지 않았다**.
  `_default_writing_service`는 한 provider 인스턴스를 generation과 reporter가 **공유**하므로
  한 번만 감싸면 두 호출이 같은 라벨을 달게 된다는 것도 이때 드러났다.
- **provider를 감싸도 레코드가 안 생긴다.** 레코드는 `llm_call_scope`가 열린 경로에서만 만들어지는데
  scope를 여는 곳이 `main.py`에 **2곳뿐**이었다(analysis run · gate). `build_context_package`를 부르는
  요청 경로는 **7곳**이고, 주력인 revise-and-gate loop은 그중 하나도 아니었다 —
  즉 계측만 하고 끝냈으면 **주력 워크플로가 0건**인 채로 집계 API를 켜게 된다.
  덤으로 확인된 사실: **loop 내부 gate 호출은 지금까지도 기록되지 않고 있었다**(`writing_gate` site의
  기존 레코드는 독립 `/writing/gate` 호출뿐).
- 리터럴·집계 의미론을 정하는 문제라 §1에 따라 임의 선택 대신 결정 브리프를 썼다:
  [`plans/observability-site-mapping-decisions.md`](../../plans/observability-site-mapping-decisions.md).

### User Decisions and Rationale

오너가 브리프의 **4개 결정 전부 추천안을 채택**했다.

- **D1 = planner 분리**(신규 `writing_retrieval_planner`). 근거는 **비가역성**: 합쳐 기록한 과거 레코드는
  나중에 갈라낼 수 없는 반면, 리터럴 추가는 계약이 이미 "스키마 변경이 아니다"라고 못박은 값싼 연산이다.
- **D2 = 신규 리터럴 2개**(`writing_revision`·`writing_report`). 같은 비가역성 논리 + loop 비용의 대부분이
  생성인지 보고인지 수정인지가 KPI의 실제 질문이기 때문.
- **D3 = LLM을 부르는 전 경로 + async 생성 worker**에 scope 개방. worker는 claim한 job이 실
  `project_id`·`request_id`를 들고 있어 "추측한 project_id" 금지 조항에 걸리지 않는 **유일한 scope 밖 경로**다.
  빼면 medium/long preset(가장 비싼 생성)이 KPI에서 통째로 빠진다.
- **D4 = repair 구조 site의 최종 거부만 `parse_error` 재분류**. 재분류가 마지막 호출 1건만 건드리므로
  회수된 첫 호출은 `success`로 남아 repair 빈도 신호가 손상되지 않는다. 이 선택은 `analysis_extractor`의
  v1.7.46 결정(재분류 안 함)과 **불일치**하며, 그 사실을 브리프와 본문에 명시했다 — extractor 정렬은
  별도 증분의 오너 판단으로 남겼다.

### Completed work

- **리터럴 3종 추가** [`observability/llm_call_audit.py`](../../../services/application/app/observability/llm_call_audit.py):
  `WRITING_RETRIEVAL_PLANNER`·`WRITING_REVISION`·`WRITING_REPORT`.
- **재분류 시행 함수** [`llm_call_scope.py`](../../../services/application/app/observability/llm_call_scope.py)
  `LlmCallScope.reclassify_last_as_parse_error`: 마지막 레코드가 `success`일 때만 동작한다.
  raw `annotate_last`가 아니라 이름 붙인 연산으로 만든 이유는 **안전 조건이 호출자의 기억이 아니라 계약**이기
  때문이다 — `ContextSearchFailed(llm_error)`는 "provider가 답을 못 함"과 "답했는데 plan이 거부됨"을
  구분하지 않으므로, 가드가 없으면 `provider_error` 행의 taxonomy가 지워지고 토큰을 모르는 행이
  토큰 집계 대상으로 들어간다.
- **provider 6곳 추가 감싸기** [`main.py`](../../../services/application/app/main.py):
  compare judge · context planner · writing retrieval planner · generation · report · revision.
  generation/report는 공유 인스턴스를 **각자 라벨로** 감싸 두 site가 갈린다.
- **scope 개방 7경로 추가**(총 9) + **async worker**: compare · context-search · generate · report ·
  revise · revise-and-gate · accept, 그리고 [`generation_worker.py`](../../../services/application/app/writing/generation_worker.py)
  `execute_generation_job`. `GenerationCollaborators.llm_call_audit`은 `None` 기본값이라 손으로 조립한
  collaborator는 그대로 유효하고 아무것도 기록하지 않는다.
- **planner 계보 가드** `_reclassify_planner_parse_error`: `ContextSearchFailed`의 네 계보 중
  `llm_error`일 때만 재분류한다. plan이 성공한 뒤의 저장소·임베딩 장애를 planner 탓으로 적으면
  모델 품질 지표가 인프라 장애로 오염된다.
- **gate endpoint의 재분류를 같은 연산으로 통일**: `annotate_last(outcome=PARSE_ERROR, ...)` →
  `reclassify_last_as_parse_error`. gate의 분기는 원래 모호하지 않아 행동은 무변이지만,
  같은 계약 조항에 두 가지 관용구가 남아 있으면 다음 슬라이스가 모호한 site에서 가드 없는 쪽을 고른다.
  §3에 따라 이 이행으로 사용처가 0이 된 `LlmCallOutcome` import를 제거했다.
- **정본** [`system-contract-sot.md`](../../system-contract-sot.md) v1.7.46 → **v1.7.47**: 8종 리터럴과
  각 site의 `outcome` 범위, scope 개방 경로 목록 + "감싸기와 scope 개방은 항상 함께",
  `correlation_id`는 **site와 함께** 읽어야 한다는 집계 규칙, 재분류 범위와 두 가드, 그리고 아래 공백.
- **회귀 신규 32** [`tests/test_llm_call_sites.py`](../../../tests/test_llm_call_sites.py):
  조립 가드 6(리터럴까지 단정 — 잘못된 site로 감싸는 것은 안 감싸는 것과 똑같이 틀렸다) ·
  scope 개방 8 · 최종 거부 재분류 7(endpoint 레벨) · 실 judge의 N레코드/repair 2레코드/
  **clean 1레코드 over-strict** · planner 계보 **양방향** · **`provider_error` 미재분류 over-strict** ·
  무호출 재분류 no-op over-strict · worker audit 미설정 시 무기록 over-strict · 리터럴 8종 전수 고정.

### Issues found — 계약이 요구하는 분기 하나가 회귀 없이 통과하고 있었다

- mutation 실증 중 **M7(compare endpoint의 재분류 삭제)이 아무 테스트도 물지 않았다.** 재분류를
  scope 객체 위에서만 검증했기 때문이다 — 연산이 동작한다는 것과 **endpoint가 그것을 호출한다는 것**은
  다른 명제다. D4는 계약 필수 분기이므로 "차단"으로 취급하고, endpoint 레벨 재분류 회귀 7건
  (compare · context-search 양방향 · generate · report · revise · loop 2단계 · accept)을 추가한 뒤
  mutation을 다시 돌려 각각 물리는 것을 확인했다.
- 두 endpoint suite를 상속으로 묶었다가 부모 케이스가 **중복 실행**되는 것을 발견해
  `_EndpointHarness`(TestCase 아님) mixin으로 갈랐다. 이 프로젝트는 슬라이스마다 회귀 증감을
  대조하므로 중복 카운트는 그 대조를 무의미하게 만든다.

### Verification

- **mutation 10종** — 각각 해당 회귀만 물었다:

  | 변이 | 물린 테스트 |
  |---|---|
  | compare 조립에서 `ObservedProvider` 제거 | 조립 가드(compare) 1 |
  | report가 generation provider를 그대로 사용(D2 붕괴) | 조립 가드 2(report · generation/report 분리) |
  | retrieval planner를 `query_planner`로 기록(D1 붕괴) | 조립 가드(retrieval planner) 1 |
  | revise-and-gate가 scope를 안 엶 | scope 개방(loop) 1 |
  | worker가 scope를 안 엶 | worker 기록 1 |
  | 재분류의 `success` 가드 제거 | `provider_error` 미재분류 over-strict 1 |
  | compare endpoint가 재분류 안 함 | endpoint 재분류(compare) 1 |
  | planner 계보 가드 제거(모든 `ContextSearchFailed` 재분류) | 계보 양방향 3 subtest |
  | loop의 gate 분기가 재분류 안 함 | loop 재분류 1 subtest |
  | accept가 재분류 안 함 | endpoint 재분류(accept) 1 |

- **회귀 전량**: **1531 passed / 4 skipped / 600 subtests**(test-mongo 기동). 직전(v1.7.46 커밋)
  1499/4/593 대비 **+32 passed / +7 subtests** = 신규 파일의 테스트·subtest 수와 정확히 일치.
  설명되지 않는 증감 0.
- **공개 계약 무변 실측**: `responses=`·`response_model` 무변경 → `npm run gen:api` 후
  `frontend/openapi.json`·`src/api/schema.d.ts` **no diff**(`git status` 빈 출력).

### Issues found — 작업 중 사고

- **mutation 되돌리기에 `git checkout <path>`를 써서 `main.py`의 미커밋 변경을 통째로 날렸다.**
  증분 C의 endpoint 배선 17곳이 한 번에 사라졌고, 스크립트가 계속 돌면서 "패턴을 못 찾는다"는
  형태로만 드러나 원인 파악이 한 박자 늦었다. 전량 복구했고(복구 후 회귀가 기준선과 정확히 일치하는 것으로
  확인) 이후 mutation은 **scratchpad 파일 백업 → `cp` 복원**으로 바꿨다.
  교훈: 커밋되지 않은 작업 트리에서 `git checkout <path>`는 되돌리기가 아니라 **삭제**다.

### Decisions (구현자 판단)

- **재분류를 이름 붙인 연산으로 승격했다**(raw `annotate_last` 유지 대신). 가드 조건이 호출자마다
  재구현되면 언젠가 하나가 틀리고, 그 결과는 조용히 오염된 KPI다 — 격리를 한 곳에 모은 것과 같은 논리다.
- **loop 내부 gate 레코드의 `decision`·파생점수 공백을 메우지 않고 계약에 적었다.** 메우려면
  `WritingReviseGateService`가 round별 gate 판정을 노출해야 하는데(현재 `WritingLoopStage`는
  stage/ordinal/status만 가진다) 그건 도메인 계약 변경이라 이 슬라이스 범위 밖이다. 대신
  **집계가 이 필드를 전수로 가정하면 안 된다**는 것을 본문에 명시했다 — 적지 않으면 증분 5가
  커버리지 공백을 데이터 부족으로 오독한다.
- **`analysis_extractor`를 D4로 정렬하지 않았다.** 같은 repair 구조인데 재분류 정책이 갈리는 것은
  알고 있고 계약에 적었지만, v1.7.46에서 오너가 보는 앞에서 확정된 결정을 이번 슬라이스가
  조용히 뒤집는 것은 §5 위반이다. 정렬 여부는 오너 판단 항목으로 남겼다.

### Next steps

- **증분 5**: `GET …/observability/kpi` 집계 API + H3 에러 선언. 집계 규칙이 계약에 3개 고정돼 있다 —
  토큰은 `success`+`parse_error`만, repair 빈도는 **site 고정** `correlation_id`당 레코드 수,
  `gate_quality_score`는 커버리지가 전수가 아니다(loop 공백).
- **오너 판단 대기**: ① `analysis_extractor`를 D4(최종 거부 재분류)로 정렬할지 ②
  loop이 round별 gate decision을 노출하게 해 파생점수 공백을 메울지(D2-B와 함께 볼 사안).

### 독립 검증 반영 (합격·차단 0건, 비차단 2건 모두 조치)

오너 요청 독립 검증(`docs/verifications/2026-07-26/increment_c_site_mapping_reclassify.md`)이
**합격(차단 사유 0건)**. 검증자가 mutation 5종(under-strict 3·over-strict 2)을 cp 백업→수정→실행→
`diff -q` 복원으로 독립 실증했고, 특히 **M1이 이 슬라이스의 핵심 통찰을 재현**했다 — compare endpoint의
재분류 호출을 지우면 endpoint 회귀가 잡는 반면 **scope 객체 레벨 회귀 8건은 무관하게 통과**한다.
"연산이 동작한다"와 "endpoint가 그것을 호출한다"가 다른 명제라는 진단이 외부에서 확인됐다.
비차단 2건을 모두 닫았다.

- **H-1 — planner 계보 네 번째 경계값(`system_error`) 명시 잠금.** 계약(SoT)이 네 계보를 **열거**로
  기술하는데 회귀는 3계보만 잠그고 있었다. 검증자 판단대로 실질 회귀 경로는 아니다(코드가
  `is LLM_ERROR` 단일 분기라 나머지 셋이 같은 경로를 탄다). 그럼에도 닫은 이유는 **규칙이 열거로
  기술된 이상 경계 테스트도 전수여야** 향후 `system_error`를 별도 분기로 세분화할 때 물리기 때문이다.
  케이스 한 줄과 함께 `assertEqual(len(ContextSearchErrorType), 4)`를 넣어 **계보가 늘면 이 테스트가
  먼저 깨지도록** 했다 — 열거가 조용히 자라는 것이 이 종류 갭의 실제 발생 경로다.
- **H-2 — worker의 planner 재분류 인라인 복제를 공통 헬퍼로 통합.** `_reclassify_planner_parse_error`를
  `main.py`에서 [`observability/llm_call_scope.py`](../../../services/application/app/observability/llm_call_scope.py)의
  **`reclassify_planner_parse_error`**(공개)로 옮기고 endpoint 8곳과 worker가 한 정의를 따르게 했다.
  - **배치 근거**: worker → `main.py` import는 순환이다(`main`이 `GenerationCollaborators`를 import한다).
    관측 모듈에 두는 것은 계층 역행처럼 보일 수 있으나 **같은 패키지에 이미 선례가 있다** —
    `llm_call_audit.py`가 `writing.models`를 import한다. 그리고 이 함수가 인코딩하는 규칙("어떤 행을
    재분류해도 되는가")은 도메인 규칙이 아니라 **관측 규칙**이라, 재분류 정책 3종(가드 2단 + 계보 판별)이
    한 모듈에 모이는 것이 격리를 `_flush` 한 곳에 모은 것과 같은 논리다.
  - 예외 타입 참조는 `TYPE_CHECKING` 아래로 내려 런타임 import 표면을 넓히지 않았다.
  - §3에 따라 이 이행으로 사용처가 0이 된 `ContextSearchErrorType` import를 `main.py`·
    `generation_worker.py` 양쪽에서 제거했다.

**검증**: 이동 후 mutation을 다시 돌려 **공통 헬퍼의 계보 가드 제거가 여전히 물리는 것**을 확인했다
(제거 시 4건 실패). 회귀 전량 **1531 passed / 4 skipped / 601 subtests** — 직전 600 대비 **+1 subtest**는
H-1이 추가한 `system_error` 케이스이며 passed 수는 무변(테스트 함수는 안 늘었다). 공개 계약은
`gen:api` 재실행 후 여전히 no diff.

**검증자와 passed 절대값이 다른 건**(검증 1455 vs 본 작업 1531) 머신별 skip 정책 차이(80 vs 4)로
완전히 설명되며, subtests와 신규 증분은 양쪽이 정확히 일치했다 — 검증 기록이 이미 교차 확인했다.

---

## Task — 관측 KPI 증분 5: 집계 read-out `GET …/observability/kpi` (SoT v1.7.48)

### Goals

- 증분 4·B·C가 쌓아 온 per-call 레코드를 처음으로 **읽는** 슬라이스. 브리프가 이미 D3=A(범위)·
  D4=A(read API)로 승인해 둔 것을 구현한다.

### Issues found — 승인된 범위의 두 항목이 이 read-model 밖에 있었다

- **D3=A가 나열한 "루프 미수렴율"은 `writing_loop_audits`에 있고 그 영속은 opt-in·기본 off**다
  ([`main.py`](../../../services/application/app/main.py) `WRITING_LOOP_AUDIT_DEFAULT` 기본 False).
  그대로 넣으면 기본 배포에서 분모가 0인 지표가 된다.
- **"승격 카운트"는 애초에 LLM 호출이 아니다**(memory 도메인). per-call 감사의 정의를 넘는다.
- 응답 형태는 `openapi.json`→`schema.d.ts`로 흘러가는 **공개 계약**인데 브리프는 "안정적으로 명명"
  까지만 지시했다. 둘 다 스펙만으로 도출되지 않아 §1에 따라 결정 브리프를 썼다:
  [`plans/observability-kpi-readout-decisions.md`](../../plans/observability-kpi-readout-decisions.md).

### User Decisions and Rationale

- **D1 = per-call + loop 미수렴율(분모 동반)**. 승인된 D3=A 범위를 **말없이 좁히지 않되**,
  `runs_considered`를 함께 실어 0을 "데이터 없음"으로 읽게 한다. extractor의 `parse_error`=0을
  "구조적 사실"로 본문에 적어야 했던 v1.7.46의 교훈을 페이로드 형태로 옮긴 것이다.
- **D2 = 요약 + `sites` 배열**(map 아님). `call_site` 리터럴은 계속 늘어나므로(증분 C에서 5→8,
  Phase 7 예정) map으로 두면 site 추가가 매번 프론트 생성 타입 변경이 된다.

### Completed work

- **[`observability/kpi.py`](../../../services/application/app/observability/kpi.py) 신설** — 순수 집계
  함수. endpoint 밖에 둬서 계약이 고정한 규칙을 HTTP를 통하지 않고 규칙으로 시험한다.
  집계 대상 집합(`TOKEN_COUNTED_OUTCOMES`)과 루프 상태 분류(`NON_CONVERGED_LOOP_STATUSES`·
  `NOT_A_LOOP_ATTEMPT`)를 모듈 상수로 단일 정의.
- **endpoint + 응답 모델 5종** [`main.py`](../../../services/application/app/main.py):
  `GET /projects/{id}/observability/kpi`, `responses=_ERRORS_404`(404 + 저장소 503),
  `response_model=ObservabilityKpiResponse`. provider를 부르지 않고 scope도 열지 않는다.
- **정본** v1.7.47 → **v1.7.48**: read-out 조항(소스·형태·분모 3종·표본 0이면 `null`·
  `multi_call_correlations`의 의미·지연 평균의 실패 포함·루프 상태 6종 분류).
- **회귀 신규 23** [`tests/test_observability_kpi.py`](../../../tests/test_observability_kpi.py).
- **공개 계약 갱신**: `gen:api` 재생성으로 `schema.d.ts` +128줄. 프론트 tsc/build/vitest 194 통과,
  build JS 399.03 kB 무변(소비 코드는 아직 없다 — 대시보드는 다음 페이즈).

### Issues found — 테스트가 필드 **이름**의 거짓을 잡았다

- endpoint payload 회귀를 쓰다가 기대값이 틀린 것을 발견했는데, 파고들자 **코드가 아니라 이름이
  문제**였다. 착수 시 `repair_correlations`(레코드 2건 이상인 correlation 수)로 설계했으나,
  writing loop은 gate·reviser·reporter를 **설계상 여러 번** 부른다
  (`WRITING_LOOP_MAX_GATE_EVALUATIONS` 기본 3). 즉 loop site에서 "2건 이상 = repair"는 **거짓**이고,
  그 이름을 출하했으면 대시보드가 정상 루프 라운드를 재시도율로 표시했을 것이다.
- **`multi_call_correlations`로 바꿨다** — 필드는 **잰 사실**만 말하고, "이것이 repair인가"의 해석은
  site의 모양(repair 구조 vs loop)에 맡긴다. 계약 본문에 두 해석을 함께 적었다.
- 브리프의 예시 JSON은 오너가 무엇을 보고 D2=A를 골랐는지의 기록이라 **소급 수정하지 않고**
  정정 노트를 붙였다(v1.7.42 H2 선례와 같은 처리).

### Verification

- **mutation 6종** — 각각 해당 회귀만 물었다:

  | 변이 | 물린 테스트 |
  |---|---|
  | `provider_error`를 토큰 집계에 포함 | 토큰 분모 1 + 집계 집합 over-strict 1 + endpoint payload 1 |
  | 표본 0일 때 비율을 `0.0`으로 | 루프 null 1 + 빈 프로젝트 1 |
  | `not_eligible`을 분모에 포함 | 루프 상태 전수 subtest |
  | 게이트 평균을 미채점 호출까지 0.0으로 포함 | 파생점수 2 + endpoint payload 1 |
  | site 고정을 풀고 correlation을 전역 집계 | site 고정 양방향 1 |
  | endpoint의 503 선언 제거 | H3 선언 2 |

- **회귀 전량**: **1554 passed / 4 skipped / 610 subtests**. 직전(v1.7.47 커밋) 1531/4/601 대비
  **+23 passed / +9 subtests** = 신규 파일과 정확히 일치. 설명되지 않는 증감 0.
- **프론트**: `gen:api` → `npx tsc --noEmit` 0 → `npm run build` 성공(399.03 kB, 무변) →
  `npx vitest run` **194 passed / 13 files**.

### Decisions (구현자 판단)

- **루프 상태 6종을 3분류했다**: 수렴 = `pass`·`terminal_decision` / 미수렴 = `budget_exhausted`·
  `no_change`·`failed` / 분모 제외 = `not_eligible`. `terminal_decision`을 수렴에 넣은 이유는 그것이
  루프가 판단을 **사람에게 정상 인계**한 설계된 종료이기 때문이고, `not_eligible`을 뺀 이유는 루프가
  아예 돌지 않아 시도가 아니기 때문이다. 규칙이 열거인 만큼 회귀도 6종 전수 + `len()` 단정으로
  잠갔다(증분 C 검증 H-1 패턴).
- **지연 평균에 실패 호출을 포함했다**. provider timeout은 실제로 그 시간을 썼고, 빼면 열화 중인
  gateway가 빨라 보인다.
- **시간 창·페이지네이션을 두지 않았다** — 선례(`GET …/writing/loop-audits`)가 프로젝트 전량을
  반환하고, `project_id` 인덱스가 있으며, 로컬 1인 단계에서 필요가 관측되지 않았다(§2). 필요해지면
  `?since=`는 additive로 들어간다.

### Next steps

- **관측 KPI 페이즈의 계측·read-out은 이것으로 닫힌다.** 남은 것은 소비(대시보드)이며 오너가 이미
  다음 페이즈로 분리해 뒀다.
- **CHANGELOG**: 페이즈가 닫혔으므로 이제 일괄 반영 시점이다(오너 확인 대기).
- 오너 결정 대기 2건(v1.7.47에서 이월): `analysis_extractor`의 D4 정렬 · loop round별 gate decision 노출.

### 독립 검증 반영 — 증분 5 (합격·차단 0건, 비차단 2건 모두 조치)

오너 요청 독립 검증(`docs/verifications/2026-07-26/increment_5_kpi_readout.md`)이 **합격(차단 0건)**.
검증자가 mutation 6종을 독립 실증하고 신규 23/9 · `schema.d.ts` +128 · 프론트 build 399.03 kB ·
vitest 194를 재측정해 **전부 일치**했다(passed 절대값 차이 76은 증분 C와 같은 머신별 skip 정책).

- **H-1 — gate 평균의 "진짜 0.0 도달" under-strict 가드를 loop와 대칭으로 추가.** 검증자 판단대로
  `_gate`가 단일 분기라 동작 위험은 없다. 그럼에도 넣은 이유는 이 값이 **`BLOCK`(=0.0), 즉 게이트의
  가장 강한 판정**을 나르기 때문이다 — "표본 0이면 null" 규칙이 언젠가 `or None` 같은 형태로 흐르면
  가장 보고 싶은 값이 조용히 사라진다. mutation(`... or None`)으로 실제로 물리는 것을 확인했다.
- **H-2 — `sites` 정렬 순서와 `avg_latency_ms` 반올림을 계약에 명시하고 회귀로 잠갔다.**
  대시보드가 다음 페이즈의 입력이므로 "정렬·반올림은 API가 보장한다"가 계약이어야 클라이언트가
  재정렬·재반올림하지 않는다. 반올림은 **동점 양방향**(100.5→100, 101.5→102)을 잠갔다 —
  파이썬 `round`가 동점을 짝수로 보내는 것은 읽는 사람이 자주 틀리는 지점이라 테스트가 그 사실을
  문서 역할까지 한다. 정렬·버림 mutation 2종으로 물리는 것을 확인했다.

**검증**: 회귀 **1556 passed / 4 skipped / 612 subtests** — 직전 1554/610 대비 **+2 passed
(H-1 1 + H-2 1) / +2 subtests(반올림 동점 2종)**. 계약 본문만 늘고 구현은 무변이라
`gen:api` 재실행 대상 없음(응답 값·형태 불변).

### CHANGELOG 일괄 반영 (오너 지시)

관측 KPI 페이즈 6개 증분(v1.7.41~48)이 SoT 변경이력에만 있던 것을 **페이즈 단위 한 행**으로
`CHANGELOG.md`에 반영했다. 증분별로 쪼개지 않은 이유는 CHANGELOG가 "major design or feature
changes" 층이고, 이 페이즈에서 오너에게 의미 있는 단위는 개별 증분이 아니라 **"파이프라인이
자기 자신을 계측하고 그것을 읽을 수 있게 됐다"**는 사실 하나이기 때문이다. 행에는 페이즈를 끈
결정 브리프 3개와 계약이 방어하는 오독 3종을 함께 적었다(결정과 근거를 CHANGELOG에 남기라는 §5).

---

## Task — 관측 KPI 대시보드 첫 슬라이스 (프론트 전용, SoT bump 없음)

### Goals

- 계측·read-out이 닫혔으므로 남은 **소비**를 만든다. 오너가 대시보드를 별도 페이즈로 분리해 뒀고,
  그 첫 슬라이스의 범위·위치·시각화 수준은 정해져 있지 않았다.

### Issues found — 스펙에서 도출되지 않는 것이 셋이었다

- **"대시보드"가 차트를 함의하는데 프론트에 차트 라이브러리가 없다**(실측: `dependencies`가
  `jszip`·`react`·`react-dom`·`react-router`뿐). 새 런타임 의존성은 되돌리기 싼 결정이 아니다.
- **진입 위치**: 이 화면은 창작 흐름이 아니라 운영 관측이라 기존 3개 route 중 어디에도 속하지 않는다.
- **무엇을 그릴지**: API가 내는 값 중 셋은 **분모를 함께 읽어야** 옳게 해석된다(SoT v1.7.48).
  화면이 그 방어를 물려받지 않으면 **대시보드가 오독을 시각화한다**.
- 브리프: [`plans/observability-dashboard-decisions.md`](../../plans/observability-dashboard-decisions.md).

### User Decisions and Rationale

- **D1 = 차트 라이브러리 도입**(추천이던 A "숫자 표만"과 **다른 선택**). 오너가 대시보드에 실제
  시각화를 원했고, 그 결정으로 진행했다. 추천 문단은 오너가 무엇을 보고 C를 골랐는지의 기록이라
  브리프에서 소급 수정하지 않고 결정 절을 위에 덧붙였다.
- **D2 = 별도 route + 진입 링크**(`/projects/:id/observability`). 검토함 선례와 동일 구조.
- **D3 = API가 내는 전부 + 분모 방어**.

### Completed work

- **[`ObservabilityDashboard.tsx`](../../../frontend/src/observability/ObservabilityDashboard.tsx) 신설** —
  요약 카드 5종 + 스택 막대(호출부별 결과) + 막대(호출부별 토큰) + 전 컬럼 표.
- **client**: `getObservabilityKpi` + 생성 타입 재수출(`ObservabilityKpiResponse`·`...SitePayload`).
  손으로 선언한 타입 없음.
- **route + 진입 링크**: `App.tsx`에 route, `DraftList` 헤더에 "파이프라인 관측 →".
- **회귀 신규 10** [`ObservabilityDashboard.test.tsx`](../../../frontend/src/observability/ObservabilityDashboard.test.tsx):
  단일 `/api` origin 경로 · 요약/행 렌더 · **오독 방어 3종을 각각 잠금** · 서버 정렬 보존 ·
  전 숫자 컬럼 · 빈 상태 · API 실패 시 alert.

### Issues found — 오너 선택의 비용이 추정보다 컸고, 그것을 실측으로 잡았다

- **번들이 399.03 kB → 786.13 kB로 뛰었다**(gzip 122.91 → 237.00). Vite가 직접 500 kB 초과 경고를 냈다.
  브리프에 적은 "+100~200 kB" 추정은 **틀렸다** — recharts가 d3 모듈을 끌고 온다.
- **대응 = route 코드 분할**: 관측 화면만 `React.lazy` + `Suspense`로 분리했다. 진입 번들
  **401.19 kB**(이 슬라이스 이전 399.03 대비 +2.16 kB)로 복귀하고, 차트 청크 385.67 kB는 **그 화면을
  열 때만** 내려간다. 대부분의 집필 세션은 이 화면을 열지 않으므로 비용을 내지 않는다.
- 이건 결정을 되돌린 것이 아니라 **결정의 비용을 지역화한 것**이다. 오너 선택은 그대로 출하됐다.

### Decisions (구현자 판단)

- **차트 색을 눈으로 고르지 않고 검증기로 골랐다**(dataviz 절차). 직관적 선택인 초록(성공)+호박(거부)은
  **적록색약에서 ΔE 2.4로 붕괴**해 탈락했다. 최종 `#1a6d99`(성공)·`#a8742a`(응답 거부)·`#9d2f2f`(응답 실패)는
  명도대·채도 하한·전 쌍 CVD 분리·정상시 하한·표면 대비 **전 항목 PASS**다. 색만으로 식별하게 두지 않았다 —
  범례 + 아래 표가 같은 값을 반복한다.
- **폴링을 넣지 않았다**(D3-C 각하와 별개로). KPI는 누적 스냅샷이라 초 단위로 변하지 않는다.
- **화면이 재정렬·재반올림하지 않는다.** 정렬·반올림은 API 계약이 보장하므로(v1.7.48) 클라이언트가
  다시 하면 화면이 계약과 어긋날 수 있다. 그 사실을 회귀로 잠갔다(서버 순서 보존).

### Verification

- **프론트**: `npx tsc --noEmit` 0 · `npm run build` 성공(진입 401.19 kB + 분할 청크 385.67 kB) ·
  `npx vitest run` **204 passed / 14 files**(직전 194/13 대비 +10/+1 = 신규 파일과 정확히 일치).
- **백엔드·계약 무변 실측**: `services/`·`tests/`·SoT에 변경 0, `gen:api` 재실행 후
  `schema.d.ts` **no diff**(`client.ts`만 수정). 이 슬라이스는 순수 소비라는 브리프 성공 기준 충족.
- **미검증으로 남긴 것**: 실제 브라우저 렌더는 확인하지 않았다. 이 머신의 스택이 내려가 있고 기동은
  오너 몫이라(HANDOFF), 차트의 시각적 배치·라벨 충돌은 **dogfood 첫 세션의 확인 항목**이다.

### Next steps

- **대시보드 확장은 시간 창(`?since=`)이 API에 생긴 뒤**가 옳다. 지금 차트가 그리는 것은 누적
  스냅샷이라 추세가 없고, 막대는 표와 같은 정보를 말한다.
- 관측 화면에 무엇을 더하든 **`React.lazy` 경계 안**에 둔다 — 밖으로 나가면 진입 번들이 다시 두 배가 된다.

### 독립 검증 반영 — 대시보드 첫 화면 (합격·차단 0건, 비차단 3건 모두 조치)

오너 요청 독립 검증(`docs/verifications/2026-07-26/increment_dashboard_first_screen.md`)이
**합격(차단 0건)**. 검증자가 mutation 4종으로 오독 방어를 양방향 실증했고, 색 접근성을
**Python으로 독립 재계산**(sRGB→Lab→WCAG/CVD 시뮬)해 결론이 일치했다. 실측 수치(vitest 204/14 ·
진입 401.19 kB · 차트 청크 385.67 kB · 백엔드 612 subtests · `schema.d.ts` no-drift)도 전부 일치.

- **H-3 — 대비 여유가 가장 작은 색(호박 3.55)을 보강.** 검증자 제안대로 호박만 어둡게 하면
  **적갈과의 분리가 무너진다**는 것이 재검증에서 드러났다(`#8f6020`: 정상시 ΔE 14.0 < 하한 15,
  CVD도 FAIL). **대비를 얻고 분리를 잃는 교환**이라 그대로 적용하지 않고, 실패 색을 crimson으로
  함께 옮겨(`#8c1f4a`) 전 검사 PASS를 유지하면서 최저 대비를 **3.55 → 4.14**로 올렸다.
  최종 `#1a6d99`(성공)·`#9a6a24`(응답 거부)·`#8c1f4a`(응답 실패).
  교훈: 팔레트의 한 칸은 혼자 못 움직인다 — 대비·분리는 같은 좌표계의 두 축이다.
- **H-1 — 루프 비율 역산 제거.** 화면이 `percent(rate * runs, runs)`로 API가 이미 한 나눗셈을 다시
  하고 있었다. 값은 같지만 "정렬·반올림은 API가 보장한다"는 이 슬라이스 자신의 명제와 어긋난다.
  전용 `rate()` 포매터로 바꿔 **형식만** 담당하게 했다. 회귀는 정수로 복원되지 않는 비율(1/3)을
  골라 잠갔다 — 역산이 드리프트하는 바로 그 경우다.
- **H-2 — 빈 상태 중복 표시 제거.** 다만 **`sites.length === 0`으로 숨기지 않았다**: 루프 감사는
  per-call 계측 이전(v1.7.41 전)에도 기록됐을 수 있어 호출 레코드가 0이어도 **실측된 미수렴율이
  있을 수 있다**. `totals.calls === 0 && loop.runs_considered === 0`일 때만 숨기고, "루프만 있는
  경우 요약이 살아 있음"을 over-strict 회귀로 잠갔다.

**검증**: mutation 2종(역산 되돌리기 · 숨김 조건을 sites 기준으로)이 각각 해당 회귀를 물었다.
프론트 **207 passed / 14 files**(직전 204 대비 +3 = 신규 3건), tsc 0, 진입 번들 401.19 kB 무변.
백엔드·계약은 이번에도 무변이다.

