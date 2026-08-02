# 독립 검증 — 제품 한 장 요약(`docs/product-overview.md`) + 낡은 단언 5건 정정

## Subject metadata

| | |
|---|---|
| 대상 커밋 | `bfd4690` "docs: 기획 축 제품 한 장 요약 + 낡은 단언 5건 정정" |
| 정규 스펙 | 없음(문서 슬라이스). 대조 기준은 **코드 실측**과 `system-contract-sot.md` 변경이력 |
| 검증자 | 구현자와 **다른 세션**. 보고 원문은 오너를 경유해 전달됐다 |
| 구현자 재실측 | 이 기록의 §"구현자 재실측" — 검증자 주장도 사실로 받지 않고 다시 물었다 |
| 판정 | **조건부 합격** — 사실 단언 대부분이 코드로 확증됐으나, 반복 등장하는 단언 하나가 반박됐다 |

## Findings — 확증된 것 (검증자가 코드로 직접 실측)

구현자가 "실측했다"고 보고한 것이 실제로 실측이었음이 확인됐다.

- 추출 **관찰 3종**([`analysis/models.py:11-14`](../../../services/application/app/analysis/models.py)), 장소·관계 미착수
- Gate **지적 4유형 · 판정 5종 · `style`은 판정을 바꾸지 않음**([`writing/gate_prompt.py:21-30`](../../../services/application/app/writing/gate_prompt.py))
- 문체는 **선언**(프로젝트 브리프 4필드) — 학습형 Voice RAG 부재
- RRF 하이브리드 융합([`context_search/service.py:277-333`](../../../services/application/app/context_search/service.py)), 예산 유도 + 창 초과 400 거부, ContextPackage의 confirmed/candidate 구분, revise-and-gate loop 배선
- **화면 부재**(인물카드·타임라인·관계 그래프 0건), 자기 가입 화면 부재
- cross-encoder 리랭커 "결정됐고 코드 없음"(`external-api-expansion-decisions.md` 오너 결정)
- Context Gate의 타 프로젝트 제거([`context_search/service.py:1241`](../../../services/application/app/context_search/service.py)), 소유권 403 강제
- 문서 수치(plans 89 · 브리프 73 · 검증 203), 회귀 **1850 / 4 skipped / 1559 subtests** 재현
- 정정 5건 전부 사실 부합 — 다중 사용자(Argon2id [`auth/password.py:31`](../../../services/application/app/auth/password.py)·세션·소유권 403·admin tier·파기) · 가드명 · v1.7.76 · 검증 203건 · `ReviewConflict` merge/split 배선

## Issues — 반박된 단언 (Hardening, 비차단)

### H-1 [확증] "8개 호출부 전부 계측"의 **근거 인용이 틀렸다**

`product-overview.md` §5-⑤가 "8개 호출부 전부가 표준 감사 레코드를 남긴다"고 단언하면서 근거로
[`observability-kpi-rationale.md`](../../observability-kpi-rationale.md)를 인용했다. **그 파일에는
"8"이라는 숫자도 "8개 호출부"라는 명시도 없다.** 매칭된 3줄(L19·L43·L53)은 "호출부"라는 단어가
있을 뿐이고, **오히려 L53은 "호출부 계측 확대"를 §6 로드맵(= 미완료)으로 나열**한다.

- 오너가 직접 반박을 시도했으나 실패했다 — 지적이 성립한다.
- **더 나쁜 점**: 같은 슬라이스가 바로 그 §6 로드맵이 낡았다고 work_log에 적어 놓고, **그 낡은
  문서를 근거로 인용**했다. 자기가 stale이라 판정한 문서를 근거로 쓴 것이다.

### H-2 [부분 확증] "전부"에 한정이 없다

검증자: "'전부'가 거짓 — worker 경로·`audit=None` worker가 미기록"
([`observability-site-mapping-decisions.md:78`](../../plans/observability-site-mapping-decisions.md),
[`writing/generation_worker.py:78-80`](../../../services/application/app/writing/generation_worker.py)).

**구현자 재실측 결과 이 주장은 절반만 맞다** — §"구현자 재실측" R-2 참조. 프로덕션 워커는
기록한다. 그러나 **script·diagnostic 등 scope 밖 경로가 계약상 미기록**인 것은 사실이고,
"전부"가 *모든 LLM 호출*로 읽히면 거짓이 되므로 한정이 필요하다는 결론은 유지된다.

### H-3 [부분 확증] "8"의 기준이 문서에 없다

검증자: "'8'이 무엇의 개수인지 정의가 어디에도 없음(scope 진입은 10, endpoint는 9, TASK_TYPE은 5)".

**구현자 재실측 결과 기준은 코드에 존재한다**(R-1). 그러나 **문서가 그것을 밝히지 않아** 독자가
검증할 수 없었던 것은 사실이다. 정정 방향은 "숫자를 뺀다"가 아니라 **기준을 명시한다**이다.

### H-4 [확증] 정정문의 시점 버전이 틀렸다

`00-foundations.md` 정정 블록이 다중 사용자 전환을 "`SoT v1.7.57` 이후"라고 적었다. **실제 유예
만료는 `v1.7.49`(2026-07-26, D0=A)**이고 v1.7.57은 전역 관측 KPI(D8-5c)다. `product-overview.md`
§5는 버전 번호를 쓰지 않아 이 문제를 피해 갔다.

### H-5 [확증] SoT 표에 대한 구현자의 "거짓" 판정이 과했다

구현자는 정본 §"현재 구현 상태"의 `Phase 2~6 UI | 미구현` 행을 **거짓**이라고 단정했다.
검증자 실측은 더 정확하다.

- **SoT는 자기 자신과 모순된다** — L696이 "Review Inbox v1.6.67 구현", L709가 "Writing 작업공간
  구현 완료"라고 적으면서 L710이 "Phase 2~6 UI 미구현"이라고 단언한다. 이것이 더 강한 지적이다.
- 다만 **Phase 2/3/4 UI(인물카드·타임라인·관계 그래프)는 실제로 미구현**이므로 그 행은
  **부분적으로 성립**한다. 구현자의 "전부 서 있다"는 이 한정에서 약간 과하다.

## 구현자 재실측 (검증자 주장에 대한 반증 시도)

검증자의 보고도 사실로 받지 않고 다시 물었다. 두 건이 반박됐다.

### R-1 — "8의 기준이 없다"는 **틀렸다**. 코드에 이중으로 있다

| 실측 | 값 |
|---|---|
| [`observability/llm_call_audit.py:42-64`](../../../services/application/app/observability/llm_call_audit.py) `LlmCallSite` 멤버 수 | **8** (`query_planner`·`writing_gate`·`compare_judge`·`analysis_extractor`·`writing_generation`·`writing_retrieval_planner`·`writing_revision`·`writing_report`) |
| `ObservedProvider(` 감싸기 지점 수(앱 전체) | **8** |
| 같은 파일 L56 주석 | *"five literals but **eight real LLM adapters**"* |

즉 "8 = LLM 어댑터(호출부) 수"라는 기준이 코드에 있고 **두 곳에서 독립적으로 확인**된다.
검증자가 대안으로 센 10(scope 진입)·9(endpoint)·5(TASK_TYPE)는 **다른 것의 개수**다 — scope는
호출부보다 많을 수 있고(한 요청이 여러 호출부를 지난다) 정의상 일치할 이유가 없다.
**남는 진짜 결함은 "기준 부재"가 아니라 "문서가 기준을 안 밝힘"이다.**

### R-2 — "worker 미기록"은 **프로덕션에서 틀렸다**

검증자가 인용한 [`generation_worker.py`](../../../services/application/app/writing/generation_worker.py)의
`llm_call_audit: ... | None = None`은 **손으로 조립한 테스트 collaborator를 위한 기본값**이고,
주석이 그 이유를 명시한다. 프로덕션 조립은 다르다.

- 워커 엔트리포인트 [`scripts/generation_job_worker.py:110`](../../../scripts/generation_job_worker.py)의
  기본 `build_fn` = `build_async_generation_collaborators`
- 그 함수([`main.py:2148`](../../../services/application/app/main.py))가
  **`llm_call_audit=_default_llm_call_audit_service()`** 를 배선한다 — 주석: *"Same factory
  create_app uses, so the worker's records land in the same store the KPI aggregation reads"*

따라서 **제품의 주 경로(생성 워커)는 기록된다.** 실제로 미기록인 것은 브리프 L78이 명시한
**`worker` 외 scope 밖 경로(script·diagnostic)** 이며, 이는 누락이 아니라 **계약**이다(추측
`project_id`는 오염이므로 기록하지 않는다).

## Verdict

**조건부 합격.** 문서의 사실 단언은 코드로 확증됐고 회귀도 재현됐다. 조건은 H-1·H-4(확증) 및
H-2·H-3·H-5(정정 방향 수정 후) 반영이다.

## Outstanding items

- **[오너 결정] 정본 §"현재 구현 상태" 표(L696·L709 ↔ L710 자기 모순)** — ⓐ 현재로 갱신
  ⓑ "이력 표이며 현재 상태는 변경이력을 본다"로 성격 명시(구현자 추천) ⓒ 걷어내기. 버전 개정
  사안이라 이번 hardening에서 손대지 않았다.
