# Work Log — 2026-09-03 (베타)

## Goals

- 계약 스키마 중복 전수조사 브리프(`docs/plans/contract-schema-duplication-audit-decisions.md`, 2026-09-02 확정)의 **구현일**: 4개 후보를 확정 기준(A 삭제 우선 → B 서버 유도 → C 유지)에 따라 시행한다.
- KPI gate 준수 실측: `llm_call_audits` 의미 무변 + 공개 OpenAPI/`schema.d.ts` 바이트 무변.
- 오너 지시: "중요한 작업이니까 서브 에이전트 활용해도 괜찮아" — 사전 확인 4건을 병렬 서브에이전트로 돌렸다.

## Completed work

### 사전 확인(병렬 서브에이전트 4종, 읽기 전용)

각 후보의 프롬프트·파서·소비처·잠금 테스트를 file:line까지 조사했다. 요약 판정:

1. **query_planner `plan_id`** — 프롬프트가 요구한 적 없고(브리프 기술 맞음), 모델이 내면 **검증 0회로 API 응답 trace에 흘러가던 틈**이었다(빈 문자열만 parse error). Mongo 영속·감사·writing 소비 전부 0건.
2. **writing_gate `decision`** — 서버가 findings priority로 재계산·불일치 거부(모델값=순수 자기복사). **mismatch는 error_type이 `InvalidWritingGateResult` 하나로 뭉개져 분리 관측된 적이 없다** — "transition 동안 mismatch 관측" 옵션은 신규 관측 인프라가 필요한 고비용 경로였다. `checked_constraints`는 소비처가 응답 노출뿐이나 서버 재구성값이 상수(4카테고리)라 **모델 자기 보고가 유일 정보원** — 유지.
3. **report bool 둘** — 서버 제어흐름에서 완전 무시(gate `accept.py:148` 무조건·분석 job `accept.py:255-269` 무조건, 조건분기 전수 0건). 프롬프트에 true/false 의미 정의 문구가 없어 모델은 예시 리터럴을 에코(실측 유일 샘플 전부 true).
4. **analysis `source_anchors`** — 카탈로그 단위 == 모델 선택 단위(4중 확인: 프롬프트 exact-copy 요구·파서 전필드 byte 대조·서비스 라이브 재대조·운영 카탈로그 프로듀서 풀블록만). 모델의 span/quote/hash 자유도 0. 영속·승격은 이미 id만 저장, review API는 이미 id→재구성.

### 구현(슬라이스 4개, 슬라이스마다 커밋→뮤테이션→원복)

| 슬라이스 | 커밋 | 내용 | 파일 |
|---|---|---|---|
| plan_id 서버 통일 | `a63b521` | 파서가 모델 값 무시, `DEFAULT_PLAN_ID` 상수 통일. 응답 필드 유지(공개 계약 무변) | `context_search/planner.py`, `tests/test_context_search_planner.py` |
| gate decision 서버 유도 | `226a821` | 프롬프트 v2(2키 출력 계약)·파서가 findings max로 decision 계산. legacy `decision` 키는 정확키 거부. mismatch 거부 경로 소멸 | `writing/gate_prompt.py`·`gate.py`·`gate_live_diag.py`, 테스트 3파일 |
| report 정책 bool | `6e9d497` | 프롬프트 v3·파서 3키(claims/hints). 데이터클래스 기본값 True(서버 정책 상수) — 공개 페이로드 무변 | `writing/report.py`·`models.py`, 테스트 3파일 |
| analysis 앵커 id 선택 | `159157b` | 프롬프트 v6(sha 핀 신규 버전 절차, v5 동결)·파서가 카탈로그에서 앵커 조립·카탈로그 렌더 슬림(id·block_id·quote). **logical_key 무변**(이행 전 핀값 셀 잠금) | `analysis/prompt_templates.py`·`extractor.py`·`prompt_builder.py`·`main.py`, 테스트 6파일 |

**KPI gate 실측**: 슬라이스 전 트리(`8655653`)와 현재 HEAD의 OpenAPI 덤프 **바이트 동일**(`scripts/dump_openapi.py` — 공개 계약 무변, `schema.d.ts` 무변). `llm_call_audits` 스키마·outcome 분류 무변. gate·extractor의 parse_error에서 mismatch/drift 원인이 사라져 **빈도에 단절**이 생긴다(의미 불변) — KPI 시계열 비교 시 2026-09-03을 경계로 본다.

### 뮤테이션(전종 기명 재실패 확인 후 원복·`git diff` clean)

| 슬라이스 | 변이 | 재실패 셀 |
|---|---|---|
| plan_id | M1 모델 값 통과 복원(`root.get("plan_id") or DEFAULT`) | `test_valid_plan_parses_literals_and_injects_project_id` + `test_model_emitted_plan_id_is_ignored` SUBFAILED 2 (3 failed) |
| plan_id | M2 plan_id 키 존재 자체 거부(과잉) | 플래너 12 failed(fixture 전면) |
| gate | M1 유도식 항상 PASS로 약화 | 16 failed(derived·chain·style 등) |
| gate | M2 style을 우선순위에 포함(과잉 교정) | `test_style_only_findings_still_pass`·`test_style_does_not_lift_a_non_style_decision` |
| gate | M3 스키마를 부분집합으로 완화(decision 키 통과) | 7 failed(신규 거부 셀 포함) |
| report | M1 정책 기본값 False로 반전 | `test_parse_typed_report_and_empty_arrays`(정책 핀) |
| report | M2 `_claim` exact-key를 부분집합으로 완화 | `test_legacy_bool_keys_are_rejected` |
| report | M3 프롬프트에 `"requires_gate_check": true` 복원 | `test_invalid_first_output_repairs_once`(assertNotIn) |
| extractor | M1 조립값을 카탈로그 무시 상수로 채우기 | 조립 핀·identity 핀·legacy repair 3셀 |
| extractor | M2 앵커 exact-key를 부분집합으로 완화 | legacy 셀 2종 |
| extractor | M3 v6 본문을 같은 버전에서 편집(배포 부팅 파괴 시나리오) | sha 핀 셀 |

### 회귀

- 전수(test-mongo healthy 후): **2701 passed / 1 skipped / 3131 subtests, exit 0, 1786초(베타)**. **검산**: 직전 기준 2697/1/3125 대비 셀 +4(report legacy bool 거부·extractor unknown id 거부·logical_key 이행 무손실 핀·프롬프트 v6 계약 셀) — 교체 셀들은 1:1라 수 무변. subtest +6 분해: plan_id 무시 셀 +3 · gate decision 키 거부 셀 순증 +2(옛 overstated 셀이 이미 subtest 3을 갖고 있었다) · 프롬프트 핀 테이블 v5 행 +1 — 예고값(3133)과의 −2는 교체 셀의 옛 subtest 수를 예측에서 빠뜨린 것, 남는 차이 없음. **skip 1 = 이 머신 관례(ES 패키지 탑재)**. 예측·실측 일치로 마감.
- 집중: 슬라이스별 관련 파일 전부 green(위 각 커밋 시점 실측) + mypy 가드 8셀 green + 문서 인덱스 가드 13셀 green(README SoT 버전 핀 갱신 포함).
- 프런트 무변: OpenAPI 덤프가 바이트 동일하므로 `schema.d.ts`도 무변(재생성 불요), 프런트 코드·테스트 무접촉.

## Issues found

- **`_saved_source` fixture의 5필드 앵커 dict가 두 용도로 쓰이던 것**(모델 출력 + `CandidateSourceAnchor(**d)` 조립) — `_candidate`가 id만 추출하도록 분리했다(runner 테스트).
- **runner preflight 셀의 "모델이 quote를 틀린" 축이 구조적으로 소멸** — 서버 조립 이후 남은 실제 실패 축("추출 카탈로그에는 있지만 정본 카탈로그에 없는 id", ghost ref)으로 재구성했다. 의미(전 draft 사전 검증 후 저장)는 동일 보존.
- **`test_writing_report_live_diag.py`의 `assertIn("_v2", text)`** — 상수 기반 단정 바로 아래의 하드코딩 중복 줄이 이번 버전 올림에서 정확히 그 함정(주석이 경고하던 리터럴 복사)을 밟아서 제거했다.

## Decisions

- **plan_id는 완전 삭제가 아니라 "파서 무시+서버 상수"로 시행** — 완전 삭제는 `SearchPlan.plan_id`·API trace 필드·fixture 7종까지 건드리는 공개 계약 변경으로, 브리프가 못박은 "public OpenAPI/`schema.d.ts` 변경은 없다" 울타리 밖이다. 모델 출력 계약(이 조사의 대상)은 이미 사실상 비어 있었으므로 A 기준의 목적은 달성된다.
- **gate는 "transition 서버 유도+mismatch 관측"(브리프 대안)을 버리고 즉시 삭제** — mismatch 관측이 현재 스키마로 불가능(error_type 단일)해 그 옵션이 신규 개발인 데다, 분리 관측된 적도 없는 신호를 보존할 가치가 없었다(조사 에이전트 결론 채택).
- **report bool은 데이터클래스 필드를 남기고 기본값 True** — 공개 페이로드 보존(브리프 울타리) + "모델이 낸 값"이 아니라 "서버 정책 상수"로 의미가 정직해진다. 값 다양성에 의존하는 소비자는 없다(프론트는 count만 렌더 — 조사 확인).
- **카탈로그 렌더 슬림(offset/hash 제거)도 같은 슬라이스에 포함** — 모델이 복사할 수 없는 것을 보여주지 않는 것이 에코 제거의 완결이고, 토큰 비용(브리프의 중복 축)도 함께 줄어든다. `block_id`는 남겼다(근거 선택 맥락).

## Next steps

- **호출 분산(D)축 분석** — `llm_call_audits` 토큰 분해 + 진단 캡처 표본(브리프 Audit material 확정 C)으로 `ContextPackage` 반복 비용을 잰 뒤 필요성 판단(별도 슬라이스). **D축 재료(검증 지적)**: 게이트 입력 렌더·accept advisory copy의 상수 true bool 둘.
- identity group Slice 1(shortlist와 판정 서비스)은 그대로 대기(HANDOFF 참조).
- 배포: 앱 계열 이미지 재빌드 필요(프롬프트 v2/v3/v6·파서 변경). 운영 Mongo의 `prompt_templates`에 v5 행이 있어도 충돌 없음(신규 v6 행 insert — 핀 테스트가 시드 절차를 잠금).

---

# Work Log — 2026-09-03 세션 2 (검증 하드닝, 베타)

## Goals

- 독립 검증(`verifications/2026-09-03/contract_schema_duplication_execution.md`, 판정 **합격**·차단 0·뮤테이션 14/14)의 비차단 하드닝 4건을 반영한다.

## Completed work

검증자가 세션 1의 표 11종을 재실행하고 신설 3종(max→first 유도 약화·유령 SourceRef 합성·legacy decision 키 조용한 pop)까지 전부 물림을 확인했다. 하드닝 4건 반영(커밋 `63669a0`):

| 항목 | 반영 |
|---|---|
| ① repair 수용 경계 명문화 | **SoT v1.8.20** — 옛 구현의 repair-후 카탈로그 재검증은 죽은 검사(양 갈래 `return repaired`)였고 v6 파서는 repair 출력도 조립 검증 통과 필수라 수용이 엄격해졌음을 §Phase 2A 조항에 명문화. 브리프 시행 결과의 "모르는 id는 기존대로 repair 1회" 와글도 정정(검증이 발견한 옛 코드 숨은 구멍 — ghost id가 러너 사전검증으로만 잡히던 이중 방어가 파서 단층 방어로 정리) |
| ② planner KPI 단절 병기 | 같은 v1.8.20 행 — 빈·비문자 `plan_id`가 더 이상 parse error가 아니므로 2026-09-03 시계열 경계는 **gate·extractor·planner 세 site**(planner는 `multi_call_correlations` repair 구조 site) |
| ③ 입력측 상수 bool 렌더 | 코드 무변(검증 권고대로) — `gate_prompt.py`·`accept.py`의 상수 true bool 둘을 D축 비용 분석 재료로 브리프·HANDOFF에 등재 |
| ④ 정책 bool 이중 잠금 셀 | `tests/test_writing.py::test_policy_bools_are_server_constants_on_the_public_envelope` 신설 — 실 파서(v3 3키)를 통과한 후보가 generate 응답 wire에 True를 싣는지(파서 기본값 반전 셀의 짝). `_FakeReporter`는 dataclass 직접 생성으로 파서를 우회하므로 진짜 `WritingCandidateReportService`를 reporter로 배선했다 |

**뮤테이션(신규 셀)**: `routers/writing.py` payload 조립 값 `not` 반전 → 신규 셀 1 재실패 → 원복·green(`test_writing.py` 68 passed).

### 회귀(세션 2)

- 전수(test-mongo healthy 후): **2702 passed / 1 skipped / 3132 subtests, exit 0, 2258초(베타)**. **검산**: 직전 2701/1/3131 대비 셀 +1(④ 이중 잠금 셀 — subtest 없음), subtest +1은 **검증 기록(`contract_schema_duplication_execution.md`) 등재분**(판정 열 전수 축 — 문서 가드 단독 실행에서 285→286으로 이미 관측한 값). 예고값(3131)에서 그 +1을 빠뜨린 것은 예측 누락이고 실측 잔차는 없다. **skip 1 = 이 머신 관례**.

## Issues found

- 검증 과정 노트(검증 기록 §Methodology·과정): 검증자가 /tmp 사전 트리 CWD에서 grep을 돌려 사전 트리를 검색한 것을 본 트리로 재실행해 정정했고, docs/README.md 카운트 누락은 문서 가드가 즉시 잡았다 — 가드가 스스로의 몫을 한 반증.

## Decisions

- **v1.8.19 이력 행은 편집하지 않고 v1.8.20 행으로 정정했다** — 이력은 그 시점의 믿음을 보존하고, 부정확했던 와글("기존대로")은 다음 행이 명시적으로 짚는 것이 이 저장소의 변경이력 관례다.
- **④는 셀을 HTTP generate 경로로 통과시켰다** — accept 페이로드 경로도 가능했지만 generate 응답이 가장 짧은 실 파서→공개 wire 왕복이며, envelope 키 셀과 같은 클래스에 둬 상태를 공유한다.

## Next steps

- (세션 1과 동일 — D축 분석·identity Slice 1·배포 대기)
