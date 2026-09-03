# 계약 스키마 중복 전수조사 결정 브리프

**상태**: 확정 · **시행 완료(2026-09-03)** — 후보 4종 전부 확인을 거쳐 시행됐다. 아래 "시행 결과" 절 참조.

**정본**: `docs/system-contract-sot.md` v1.8.18

**계기**: HANDOFF ⑦, 오너 관찰 "계약 스키마가 중복되어 있을 수도 있다."

## Decision needed

8개 LLM 호출부에서 발견된 에코/결정적 필드/호출 분산 후보를 제거할지, 서버 유도값으로 바꿀지, 현행 self-check 계약으로 유지할지 결정해야 한다. 이 선택은 prompt 출력 schema, parser, 감사 관측 방식을 함께 바꾸므로 이 브리프에서는 방향만 확정하고 구현은 별도 작업일에 진행한다.

## Options table

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 삭제 우선** | 불필요한 출력 schema 필드는 모델 요청/응답 계약에서 제거한다. id값도 서버 위에서 통제 가능하면 제외 대상이다. | 프롬프트와 parse schema가 가장 작아진다. 결정적 값을 모델이 틀리게 복사하는 실패가 사라진다. | 기존 진단/회귀가 보는 출력 모양이 바뀐다. 제거 전후 KPI 의미가 동일함을 확인해야 한다. |
| B. 서버 유도 후순위 선 | 삭제만으로 닫히지 않지만 서버가 결정적으로 만들 수 있는 값은 public/domain 결과에서 서버가 유도한다. 모델이 낸 값은 필요 시 diagnostic 또는 parse_error 근거로만 쓴다. | 결정적 결과는 서버가 책임지고, 모델 불안정성도 관측할 수 있다. | schema가 잠시 넓어질 수 있고, 어떤 값이 정본인지 문서화하지 않으면 더 헷갈린다. |
| C. 현행 유지 + 가드 명시 | 현재처럼 모델이 aggregate/anchor를 내고 서버가 검산한다. 대신 각 필드가 "self-check"인지 "정본"인지 계약에 적고 셀을 보강한다. | 구현 위험이 가장 낮다. 지금 dogfood 데이터를 바로 비교할 수 있다. | 중복 schema와 토큰 비용은 그대로다. 에코 필드가 모델 오류를 만들 수 있다. |
| D. 호출 재배치 | generation -> report -> gate -> revise 체인의 프롬프트 중복을 줄이도록 호출 순서나 요약 산출물을 바꾼다. 확인이 끝난 뒤 필요하다고 판정되면 별도 장기 유예 없이 곧바로 다음 구현 후보로 올린다. | 반복 context 주입 비용을 크게 줄일 수 있다. | 계약 면이 가장 넓게 흔들린다. 품질 회귀와 부분 실패 envelope 재설계가 필요하다. |

## Recommendation + reason

**확정 기준은 A -> B -> C 순서다.** 불필요한 schema라면 삭제를 우선한다. 삭제하면 기능 계약이 비거나 transition 비용이 과한 필드만 서버 유도 후순위 선으로 둔다. id값 같은 식별자도 서버 위에서 통제 가능하면 모델 출력 schema에서 제외한다. 현행 self-check 유지는 마지막 선택이며, 유지할 때는 그 필드가 KPI 의미를 바꾸지 않는다는 근거와 회귀 가드가 있어야 한다.

**KPI 영향 없음이 공통 gate다.** 어떤 제거/서버 유도도 `llm_call_audits`의 호출당 1행, `call_site`, `outcome`, token counts, context window/cap, latency 의미를 바꾸면 안 된다. 필드 삭제가 prompt/output shape를 줄이는 것은 허용되지만, 성공률·parse_error율·토큰 분해·site별 집계가 다른 의미를 갖게 되면 그 변경은 이 브리프의 승인 범위를 벗어난다.

호출 분산은 더 크다. writing 체인은 같은 `ContextPackage`를 여러 호출에 싣고 있으나, Gate/Report/Revision이 각각 다른 실패 envelope과 사용자 표면을 가진다. 확인이 끝난 뒤 실제 중복 비용이 크고 KPI 의미를 보존할 수 있으면 별도 장기 유예 없이 곧바로 호출 재배치 slice로 진행한다. 단, 이 브리프 당일에는 구현하지 않는다.

## 전수 결과

| call_site | 현재 출력/계약 | 에코/결정적 후보 | 호출 분산 후보 | 판단 |
|---|---|---|---|---|
| `analysis_extractor` | `candidates[]`가 `candidate_type`, `provenance`, `confidence`, `source_anchors`, `payload`를 낸다. | `source_anchors`가 catalog의 `source_ref_id/start_offset/end_offset/quote/content_hash`를 모두 복사한다. 모델이 고를 것은 근거 항목이고, span/quote/hash는 서버 catalog에서 재구성 가능할 수 있다. `logical_key`는 이미 서버가 만든다. | `writing_candidate_report`와 raw snapshot을 함께 받는다. report가 방금 생성된 경우 분석 extractor가 candidate report schema를 한 번 더 소비한다. | **확정 기준 적용**: span/quote/hash가 서버 catalog에서 통제 가능하면 삭제 우선, 불가하면 최소 id/번호만 모델 출력으로 남기고 서버 유도. KPI 의미는 유지해야 한다. |
| `compare_judge` | matched pair에 대해 `action`, `rationale`만 낸다. `create`는 서버 결정이다. | 큰 에코 없음. `allowed_actions`는 입력으로 주고 action은 실제 판단이다. | matched pair마다 호출한다. 여러 candidate가 같은 memory와 비교되면 memory payload가 반복된다. | 현행 유지 가능. batch judge는 품질/부분 실패 계약이 커져 별도 후속. |
| `query_planner` | `steps[]`를 내고 parser는 optional `plan_id`를 허용한다. `project_id`는 parser 인자로 서버가 넣는다. | `plan_id`는 prompt의 output_contract에 없고 없으면 `context_search_plan`으로 기본화된다. 서버 기본값이면 모델 출력 schema에서 제외하는 편이 맞다. | writing 생성/수정 전에 검색 계획 호출이 선행되고, 뒤 호출들이 다시 context를 싣는다. | **확정 기준 적용**: `plan_id`는 서버 통제 id이므로 삭제 우선. compatibility가 필요하면 서버 기본값만 유지하고 모델 출력은 정본으로 읽지 않는다. |
| `writing_generation` | plain prose만 낸다. 서버가 `WritingCandidate` metadata를 감싼다. | 에코 없음. `intent`/`next_unit`은 최근 결함 폐쇄처럼 서버 요청 metadata로 보존한다. | `ContextPackage`와 draft excerpt를 싣는다. 뒤의 report/gate가 다시 candidate/context를 본다. | 현행은 건강한 쪽. 호출 분산 분석의 기준 호출이다. |
| `writing_gate` | `decision`, `findings[]`, `checked_constraints[]`를 낸다. 서버가 findings priority로 decision을 재계산해 불일치를 거부한다. | `decision`은 `findings.recommended_decision`에서 결정적으로 유도된다. `checked_constraints`도 입력 context/request에서 서버가 체크 대상 목록을 만들 수 있는지 검토 여지가 있다. | candidate report와 full `ContextPackage`를 다시 싣는다. | **확정 기준 적용**: `decision`은 서버 유도 가능하므로 모델 출력 schema에서 삭제 우선. 삭제가 parse_error/KPI 의미를 바꾸면 transition 동안 서버 유도 + mismatch 관측으로 둔다. |
| `writing_retrieval_planner` | `query`, `needs[]`만 낸다. | 큰 에코 없음. allowed needs는 서버가 제한하고 중복을 거부한다. | Gate의 retrieve_more finding만 받아 후속 검색을 좁힌다. full context를 다시 싣지 않는다. | 현행 유지 쪽. |
| `writing_revision` | replacement prose fragment만 낸다. 서버가 anchor validation과 splicing을 한다. | 에코 없음. evidence 그대로 반환은 서버가 거부한다. | `candidate_text`, exact finding, full `ContextPackage`를 싣는다. | 현행 유지 가능. 다만 full context가 항상 필요한지는 감사 표본으로 측정. |
| `writing_report` | candidate self-report JSON을 낸다. context pointer는 번호만 내고 서버가 pointer로 매핑한다. | R-e가 이미 큰 에코를 제거했다. 남은 `requires_gate_check`와 `should_analyze_after_save`는 판단값인지 서버 정책값인지 경계가 애매하다. | generation 직후 candidate와 numbered `ContextPackage`를 다시 싣는다. | **확정 기준 적용**: bool 둘이 서버 정책값이면 삭제 우선, 판단값이면 유지 가능. 유지해도 KPI 의미는 바꾸지 않는다. |

## Audit material gap

HANDOFF ⑦은 `llm_call_audits`에 "프롬프트 본문·토큰"이 남는다고 했지만, 현재 저장 schema는 `project_id`, `call_site`, `correlation_id`, `model`, `outcome`, `decision`, `gate_quality_score`, token counts, window/cap, latency, `error_type`, `created_at`만 가진다. `ObservedProvider`도 request body를 저장하지 않는다. 따라서 **입력 본문과 출력 본문 대조는 감사 레코드만으로 재현할 수 없다**.

결정 후보:

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 토큰 통계만 사용 | 기존 audit의 `prompt_tokens`/`completion_tokens`/`context_window`로 중복량을 추정한다. | 코드 변경 없음. 운영 데이터 오염 없음. | 어떤 필드가 에코인지 직접 증명하지 못한다. |
| B. redacted prompt snapshot audit 추가 | dogfood 기간에 request/output 일부를 redaction/hash와 함께 별도 debug collection에 남긴다. | 입력↔출력 대조가 재현 가능하다. | 민감 본문 저장 정책, 파기 그래프, retention 계약이 필요하다. |
| C. 진단 캡처 스크립트로 표본만 재현 | 기존 live diag/capture 패턴으로 오너가 고른 표본 workflow를 실행해 prompt/output을 저장소 밖 또는 검증 문서에 요약한다. | 영속 schema 변경 없이 빠르게 판단 재료를 만든다. | 운영 dogfood 전체 분포가 아니라 표본 분석이다. |

확정: **C로 1차 표본을 만들고, 반복 측정이 필요할 때만 B를 별도 브리프로 연다.** 프롬프트 본문을 영속 감사에 넣는 결정은 KPI 의미를 바꾸거나 민감 본문 retention을 열 수 있으므로 이 브리프의 기본 경로가 아니다.

## Follow-up considerations

- identity group Slice 1이 전용 judge를 추가하면 `LlmCallSite` 새 리터럴이 필요할 가능성이 높다. 새 리터럴은 schema 변경이 아니지만, `ObservedProvider` 감싸기와 `llm_call_scope` 개방은 함께 잠가야 한다.
- 에코 제거를 적용할 때는 under-strict만 보지 말고 over-strict도 잠근다. 예: Gate에서 `decision`을 제거하면 findings가 비어 있는 pass와 style-only pass가 모두 유지되어야 한다.
- analysis anchor를 줄이면 `source_ref_id`만으로 충분한지 먼저 확인해야 한다. 현재 `source_ref_catalog`의 단위가 모델이 고른 근거 단위와 정확히 같은지에 따라 서버 유도 가능성이 갈린다.
- 호출 분산 최적화는 비용 절감 slice다. 품질과 부분 실패 envelope을 보존하려면 기존 `llm_call_audits` token 분해로 후보 workflow를 먼저 고른다. 확인 결과 필요성이 크고 KPI 의미가 유지되면 곧바로 다음 구현 후보로 올린다.

## Deferred / out of scope

- 이 브리프에서는 prompt/parser/schema 코드를 바꾸지 않는다. **[→ 시행 완료 2026-09-03, 아래 절 참조]**
- 새 `identity_group_judge` 구현은 Slice 1 착수 범위로 남긴다.
- 운영 DB의 실제 dogfood 레코드 조회와 민감 본문 저장 정책은 별도 오너 결정이 필요하다.
- public OpenAPI/`schema.d.ts` 변경은 없다.

## 시행 결과 (2026-09-03, SoT v1.8.19)

확정 기준(A→B→C)을 코드 실측 확인에 통과시킨 뒤 그대로 적용했다. 커밋 `a63b521`(planner) · `226a821`(gate) · `6e9d497`(report) · `159157b`(extractor).

| 후보 | 확인 결과 | 시행 | 근거 |
|---|---|---|---|
| query_planner `plan_id` | 프롬프트가 요구한 적 없음. 모델 값이 검증 0회로 API 응답 trace에 그대로 흘러가던 틈 | **A(무시)** — 파서가 모델 값 무시, 서버 상수 `context_search_plan` 통일. 공개 응답 필드는 유지(브리프 "public schema 변경 없음" 울타리 안에서의 완전 삭제 회피) | 완전 삭제는 `SearchPlan.plan_id`·API trace·fixture 7종까지 건드리는 공개 계약 변경이라 범위 밖 |
| writing_gate `decision` | 서버가 findings priority로 재계산해 불일치 거부 — 모델값은 순수 자기복사. mismatch 관측은 error_type이 단일라 분리 관측된 적 없었음 | **A(즉시 삭제)** — 프롬프트 v2·파서 2키. decision은 서버 유도값(응답 무변). legacy `decision` 키는 정확키 검사 거부 | "transition 서버 유도+mismatch 관측"은 신규 관측 인프라가 필요해 오히려 고비용 — 브리프 대안 B 기각 근거 |
| report bool 둘 | 서버 제어흐름에서 완전 무시(조건분기 0건) — gate·분석 job 모두 무조건 실행. 모델은 예시 리터럴 `true` 에코(실측 유일 샘플 전부 true) | **A(모델 출력에서 삭제)** — 프롬프트 v3·파서 3키. 공개 페이로드 유지를 위해 데이터클래스 기본값 True(서버 정책 상수)로 채움 | 판단이 아니라 정책값 — D5 선택지 C가 기각하던 "소비자 없는 speculative data"가 실상이었다 |
| analysis `source_anchors` | 카탈로그 단위 == 모델 선택 단위(4중 확인: 프롬프트 exact-copy 요구·파서 전필드 대조·서비스 재대조·운영 프로듀서 풀블록). 모델의 span/quote/hash 자유도 0 | **A(id 선택+서버 조립)** — 프롬프트 v6(sha 핀·v5 동결)·파서가 카탈로그에서 조립·카탈로그 렌더 슬림(id·block_id·quote). **logical_key 무변**(이행 전 핀값으로 셀 잠금) | 조립이 파싱 안에서 일어나므로 옛 전필드 일치 강제가 구조적으로 보장됨 — drift 클래스 원천 제거 |

**checked_constraints는 유지했다**(gate): 서버 재구성값이 상수(4카테고리 고정)라 모델 자기 보고가 유일한 정보원 — 삭제는 정보 손실이었다. `compare_judge`·`writing_generation`·`writing_retrieval_planner`·`writing_revision`은 브리프 판정 그대로 현행 유지(에코 없음).

**검증 하드닝 반영(2026-09-03, 판정 합격 후 — SoT v1.8.20)**: ① 표의 "모르는 id는 기존대로 repair 1회"는 부정확한 와글이었다 — 옛 구현은 repair-후 카탈로그 재검증이 죽은 검사(양 갈래 `return repaired`)여서 repair 출력이 사실상 무조건 수용됐고, v6 파서는 **repair 출력도 조립 검증 통과 필수**(실패 시 그 호출로 종료)라 **수용 경계가 엄격해졌다**(독립 검증이 발견한 옛 코드의 숨은 구멍이 신규 코드에서 같이 닫힘). ② planner site에도 parse_error 빈도 단절이 있다(빈·비문자 `plan_id`가 더 이상 에러 아님) — KPI 시계열 경계는 **gate·extractor·planner 세 site**. ③ 정책 bool의 공개 표면 이중 잠금 셀 신설(실 파서 통과 후보가 generate 응답에 True를 싣는지).

**KPI gate 실측**: OpenAPI 덤프가 슬라이스 전 트리(8655653)와 바이트 동일(공개 계약 무변 → `schema.d.ts` 무변). `llm_call_audits` 스키마·outcome 분류 무변. gate·extractor·planner의 parse_error에서 mismatch/drift/빈-id 원인이 사라져 **빈도 단절**이 있다(의미 불변) — 시계열 비교 시 이 날짜를 경계로 본다.

**남은 축(호출 분산 D·진단 캡처 C)**: 이 날 시행하지 않았다. `llm_call_audits` 토큰 분해 + 진단 캡처 표본(브리프 Audit material 확정 C)으로 중복 비용을 잰 뒤 필요성 판단 — 그때 별도 슬라이스로 연다. **D축 비용 분석 재료(검증 지적)**: 게이트 입력 렌더(`gate_prompt.py`의 claims/hints 직렬화)와 accept advisory copy(`accept.py`)가 이제 **상수 true만 실어 나르는 bool 둘을 계속 렌더**한다 — 출력 계약 밖이라 무해하나 남은 토큰 노이즈로 함께 볼 것.
