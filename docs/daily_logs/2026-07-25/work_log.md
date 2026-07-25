# 2026-07-25 작업 로그

## Task — 관측 KPI 증분 4: 첫 호출부 계측(`writing_gate`) 와이어링 (SoT v1.7.42)

### Goals

- HANDOFF가 지정한 다음 작업. v1.7.41이 만든 per-call 감사 레코드는 **미와이어** 상태였다 — 모델·파생점수·Mongo 어댑터만 있고 실제로 아무것도 기록하지 않았다.
- 목표는 그 레코드가 처음으로 **진짜 값을 받게** 하는 것: `create_app` 와이어링 + `/writing/gate`를 첫 계측 호출부로. production hot-path 변경이라 "관측이 요청을 깨지 못한다"를 코드와 회귀 양쪽으로 잠그는 것이 슬라이스의 절반이다.

### Issues found (착수 전 실측)

- **`evaluate()`는 토큰을 버린다.** [`writing/gate.py:54-62`](../../../services/application/app/writing/gate.py#L54-L62)의 `evaluate`는 `evaluate_metered`를 감싸며 `_usage`를 폐기하는 얇은 래퍼다. endpoint가 이걸 계속 쓰면 계약이 요구하는 `total_tokens`가 **항상 0**이 되어 필드가 죽는다. 그래서 endpoint를 `evaluate_metered`로 전환하고 `MeteredCallError` unwrap(`raise exc.cause from exc`)을 인라인했다 — 래퍼가 하던 것과 정확히 같으므로 응답은 무변이고, 기존 gate 회귀 37건이 그 무변을 지킨다.
- **`MeteredCallError`가 parse 실패의 토큰을 실어 나른다**([`metering.py:18`](../../../services/application/app/writing/metering.py#L18)). 즉 "provider가 답했고 도메인 파싱이 거부한" 경우는 토큰이 **실제로 소진된** 유일한 실패이고, metered 전환은 그 사실까지 기록 가능하게 만든다. `evaluate` 경로로는 이 정보가 존재하지 않는다.
- **계측 경계가 계약에 없었다.** v1.7.41은 레코드 *모양*만 정의했고 "언제 남기는가"는 침묵이었다. 이건 spec-silent-but-code-enforced가 될 자리라(CLAUDE.md §5) 코드로 임의 결정하지 않고 아래 두 원칙을 정본에 명문화했다.

### Decisions (구현자 판단 — 스펙에서 도출, 브리프 대상 아님)

- **레코드 조건 = provider가 실제로 호출된 경우.** gate endpoint의 실패 중 입력 검증 400·`InvalidContextSearchRequest`·`ContextSearchBudgetExceeded`·`ContextSearchFailed`는 **gate LLM 호출 이전**에 끝난다. 이걸 세면 "일어나지 않은 LLM 호출"이 카운트에 들어가 증분 5가 집계할 모든 비율(성공률·site별 분포)이 틀어진다. 그래서 `build_context_package`를 별도 `try`로 분리해 계측 구간 밖에 뒀다.
- **실패한 호출은 기록한다.** work_log 07-24의 증분4 서술은 "`evaluate` 성공 후 레코드"였으나, `LlmCallOutcome`이 이미 `provider_error`·`parse_error`를 정의했고(v1.7.41 계약) 증분 5의 집계 항목에 **"성공/실패율"**이 있다. 성공만 기록하면 실패율이 영구히 0인 KPI가 나온다 — 계약이 이미 답을 갖고 있어 오너 결정 사항이 아니라고 판단했다. `budget_exceeded`는 이 site에서 발화하지 않는다(context budget은 호출 전이라 위 원칙에 따라 미기록); 다른 site에서 쓰인다.
- **격리 시행 지점을 하나로 고정했다.** `create_app` 스코프의 `_record_llm_call` 하나가 `except Exception`을 갖고, 호출부는 인자만 넘긴다. site가 5개로 늘 때 각 호출부가 격리를 재구현하면 언젠가 하나는 틀리고, 그 결과는 "관측이 요청을 깨뜨림"이다. SoT §363이 격리를 계약으로 명시했으므로 그 계약의 단일 시행 지점이기도 하다.
- **이 격리는 v1.7.38 전역 저장소 handler보다 안쪽이어야 한다.** durable 어댑터를 쓰는 배포에서 감사 write가 pymongo 예외를 던지면, 격리가 없을 때 그 예외는 전역 handler에 도달해 **정상 200 gate 응답을 503("정본 저장소 장애")으로 뒤집는다.** 관측 대상이 멀쩡한데 관측 실패가 장애로 보고되는 것이라 특히 나쁘다. 전용 over-strict 회귀로 잠갔다.
- **감사 서비스를 opt-in으로 두지 않았다**(loop audit의 `persist_audit` 선례와 다른 선택). 루프 감사는 진단용이라 opt-in이 맞지만, KPI는 "요청한 사람이 있을 때만 세는" 순간 측정이 아니게 된다. in-memory 기본이라 인프라 없이도 항상 켜져 있다.

### Completed work

- **와이어링** [`main.py`](../../../services/application/app/main.py): `_default_llm_call_audit_service()`(loop audit 팩토리 미러 — in-memory 기본, `CORE_SOT_MONGO_URI` 시 `MongoLlmCallAuditRepository`), `create_app(llm_call_audit_service=...)` 파라미터, 격리 헬퍼 `_record_llm_call`.
- **계측** `writing_gate_endpoint`: `build_context_package`를 별도 `try`로 분리(호출 전 경로 = 미계측), `evaluate` → `evaluate_metered` 전환 + `MeteredCallError` unwrap, 로컬 `_record_gate_call`로 세 outcome 기록 — `SUCCESS`(model·decision·`gate_quality_score`·usage), `PARSE_ERROR`(`MeteredCallError.usage` = 실제 소진 토큰, `error_type`=cause 클래스명), `PROVIDER_ERROR`(`error_type`=`exc.code.value`로 provider taxonomy 보존). `latency_ms`는 `time.perf_counter()`로 gate 호출 구간만 측정(context 빌드 제외).
- **정본** [`system-contract-sot.md`](../../system-contract-sot.md) v1.7.41 → **v1.7.42**: §"LLM 파이프라인 관측(KPI)"에 격리 시행 지점·전역 handler와의 순서·레코드 조건(호출 전 미기록/실패 기록)·`*_metered` 토큰 취득·계측된 호출부 목록을 추가. 변경이력 신규 행.
- **회귀 신규 7** — `tests/test_writing_gate.py::WritingGateObservabilityTest`:
  - 성공 레코드의 **전 필드**(call_site·outcome·correlation_id=request_id·project_id·model·decision·score·tokens=2·latency≥0·error_type=None) — 증분 5가 읽을 것을 "행이 있다"가 아니라 값으로 잠근다.
  - **decision 5종 전수** 파생점수 + `WritingGateDecision` enum 전체를 덮는지 자체 확인(새 decision이 매핑 없이 추가되면 여기서 물린다).
  - provider 실패: outcome·**`error_type`이 provider code 그대로**·상태코드(504/502) 유지·tokens=0.
  - parse 실패: **실제 소진 토큰 2가 기록**(metered 전환의 값) + `error_type="InvalidWritingGateResult"`.
  - **over-strict** — 호출 전 거부 3종(context 실패 502·budget 504·bad task_type 400)에서 레코드 **0건**.
  - 격리: 감사 write 실패에도 200 + 시도 1회.
  - **over-strict** — 감사 저장소 pymongo 실패가 **503으로 새지 않음**(전역 handler 안쪽 경계).
- `WritingGateApiTest._client`에 `llm_call_audit_service` 주입 인자 추가(기존 호출부 무변).

### Verification

- **mutation 5종 실증** — 각각 해당 회귀만 물었다:

  | 변이 | 물린 테스트 |
  |---|---|
  | 성공 레코드 제거 | 성공 필드 1 + decision 전수 5 subtest |
  | `evaluate_metered` → `evaluate`(토큰 유실) | 토큰 단정 2건만(다른 계측 회귀는 green) |
  | 격리 `try/except` 제거 | 감사 실패 격리 2건(RuntimeError·pymongo) |
  | 호출 전 경로에도 계측 추가 | 호출 전 미기록 over-strict 1 subtest |
  | 실패 경로 레코드 제거 | parse 1 + provider 2 subtest |

- **회귀 전량**: **1485 passed / 4 skipped / 593 subtests**(test-mongo 기동). **같은 머신에서 변경 전을 `git stash`로 재측정한 기준선이 1478 / 4 / 584**이므로 **+7 passed(신규 7건) / +9 subtests(decision 5 + provider 2 + 호출 전 2)** — 설명되지 않는 증감 0.
- **기준선 숫자 정정**: HANDOFF에 적힌 `1471 / 1 skipped / 579`는 **v1.7.40 시점 값**이고 v1.7.41의 신규 회귀(+7 passed / +5 subtests)가 반영되지 않은 상태였다(1471+7=1478, 579+5=584로 정확히 맞는다). HANDOFF를 1478/584로 갱신했다.
- **skip 1 → 4는 머신 차이이지 회귀가 아니다**: 늘어난 3건은 전부 `tests/test_context_search_memory_lexical_retrieval.py`의 "elasticsearch package not installed"이고, 이 머신에는 해당 파이썬 패키지가 없다. 기존 1건은 HANDOFF가 말한 live Chroma 건. 변경 전 재측정에서도 동일하게 4건이었다.
- **공개 계약 무변 실측**: `responses=`·`response_model` 무변경 → `npm run gen:api` 후 `frontend/openapi.json`·`src/api/schema.d.ts` **no diff**(git diff 빈 출력). 프론트 소스 무변이라 build/vitest 대상 없음.

### Next steps

- **증분 4 잔여 호출부**: generation → planner → compare → extractor. gate와 같은 두 원칙(호출 전 미기록·실패 기록)과 `*_metered` 토큰 취득이 그대로 적용되며, 각 서비스에 metered 변형이 있는지 확인이 선행한다.
- **증분 5**: `GET …/observability/kpi` 집계 API + H3 에러 선언(404·503). 이제 읽을 데이터가 실제로 쌓인다.

### 독립 검증 반영 (합격·조건 없음, 비차단 4건 중 3건 조치)

오너 요청 독립 검증(`docs/verifications/2026-07-25/observability_kpi_increment4_writing_gate.md`)이 경계 매트릭스 9 cell에 빈 칸 없음·mutation 3종 재현·`gen:api` no-diff를 독립 재도출해 **합격(조건 없음)**. 지적된 hardening 4건 중 3건을 조치했다.

- **H3 — dead branch 제거(코드).** 지적을 primary source로 재도출한 결과 **검증자보다 범위가 넓었다**: 검증자는 build 구간의 `WritingGateError`(`context_search`는 이걸 던지지 않음 — `grep`으로 발생 지점이 `gate.py` 5곳뿐임을 확인)와 `InvalidWritingGateResult` 두 절을 지적했는데, 후자는 검증자가 "pre-existing"으로 읽힐 여지를 남겼으나 실제로는 **둘 다 이번 슬라이스가 죽인 것**이다. 옛 `evaluate()`는 `MeteredCallError`를 unwrap해 `InvalidWritingGateResult`를 그대로 던졌으므로 그 절은 원래 **live**였고, `evaluate_metered` 전환으로 예외가 감싸인 채 오면서 새 `except MeteredCallError`가 먼저 잡게 되어 죽었다. 즉 §3의 "내 변경이 만든 orphan"에 정확히 해당해 둘 다 제거했다(pre-existing dead code였다면 §3에 따라 손대지 않았을 것이다). 행동 무변 — gate 회귀 44건/41 subtest 그대로 green. 남긴 `except WritingGateError`는 **live**다(`evaluate_metered` 첫 줄의 `_validate`와 template 조회 실패), 그 사실을 주석으로 명시했다.
- **H1 — 실패 레코드 토큰 의미론을 계약에 명시.** 코드는 `provider_error`에 0을 넣는데 계약이 침묵했다(spec-silent). 본문에 `parse_error`=실제 소진 토큰 / `provider_error`=0이며 그 0은 **"0을 썼다"가 아니라 "알 수 없다"**임을 적고, 여기서 도출되는 집계 규칙 — **증분 5의 토큰 집계는 `success`+`parse_error`만 대상**(provider_error를 분모에 넣으면 평균이 낮게 왜곡) — 까지 함께 못박았다. 검증자가 "증분 5 집계 시 의사결정 후보"로 남긴 것을 지금 결정한 이유는, 다음 슬라이스가 이 질문을 다시 추측하게 두면 같은 spec-silent가 반복되기 때문이다.
- **H2 — 브리프 D2-A drift에 정정 노트.** 브리프 표가 "ERROR/WARNING 개수 반영"이라 쓰는데 구현·본문은 decision-only 근사다(v1.7.41 잔여). **표 셀은 소급 수정하지 않고** 정정 노트를 붙였다 — 오너가 무엇을 보고 D2=C를 골랐는지가 기록의 값이고, 07-23에 세운 "과거 결정 기록은 소급 수정하지 않는다" 원칙과 같은 성격이다. canonical이 본문임을 노트에 명시했다.
- **H4 — 조치 없음.** "mutation 5종 중 2종은 직접 재현 대신 코드 리딩"은 검증 범위의 선택이고 lock 누락이 아니라는 검증자 판단에 동의한다.

- **검증자와 측정 절대값이 다른 건**(검증 1409/80 vs 본 작업 1485/4) test-mongo 기동 여부 차이이고, **증분 +7 passed / +9 subtests는 양쪽에서 동일하게 성립**한다. 회귀 결함이 아니다.
