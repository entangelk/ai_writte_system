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

