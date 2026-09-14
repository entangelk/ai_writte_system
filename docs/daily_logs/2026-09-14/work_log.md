# 작업 로그 — 2026-09-14

## 세션 1 — 계획·승인 (오너 요청 "전체적으로 파란 인상을 줄이고 현대적이며 눈길을 끄는 디자인")

## Goals
- 프론트의 과도한 파란색 사용을 확인하고 현대적 디자인 개선 페이즈 작성 및 구현 준비.

## Completed work
- styles.css·ProjectList·Phase 10·Phase W·SoT·CSS 가드를 확인했다. 페이지/침강면/본문까지 블루가 적용된 구조를 확인했다. 실제 브라우저 검수는 아직 하지 않았다.
- `docs/plans/frontend-neutral-studio-phase.md`에 결정 브리프와 N0~N4 작업·검증 순서를 작성하고 계획 인덱스에 등재했다.
- HANDOFF의 구현 백로그 없음 문구를 현재 결정 대기 상태로 대체하고 CHANGELOG를 갱신했다.

## Issues found
- 기존 Phase 10 D2와 W는 블루 유지 승인이다. 새 요청의 색상 교체 범위는 미지정이므로 AGENTS.md §1 및 SoT 문서 우선순위에 따라 확인 질문을 보냈다. CSS 변경은 답변 전 보류했다.

## Decisions — User Decisions and Rationale
- 사용자: 전체적으로 파란 인상을 줄이고 현대적이며 눈길을 끄는 디자인 필요. 현황 확인 후 페이즈 작성과 구현 요청.
- 구현자 제안(미승인): 중성색 페이지·본문과 블루 액션 포인트. 새 키색 교체 및 현행 팔레트 유지 대안도 계획에 기록했다.

## Verification
- 문서 검사: 최초 29 passed / 962 subtests passed, 계획 수 주장 2 subtests 실패. 새 계획 추가로 전체가 140→141개가 되어 루트 README와 계획 인덱스의 숫자를 함께 수정했다. 해당 검사 재실행 1 passed / 5 subtests passed.
- 새 계획 상대 링크 3개 존재 확인, `git diff --check` 통과. 프로덕션 코드 변경 없음. 프론트 테스트·빌드·브라우저 검수는 구현 단계에서 수행한다.

## Next steps
- 색상 범위 답변을 계획에 반영하고 N0 실제 화면 기준선 확보 → N1~N4 구현·검증.

## 후속 승인 및 구현 착수
- 오너가 A(블루 포인트 유지)를 확정하고 나머지 시각 변경을 허용했다. 랜딩과 세부 페이지의 구조 개선도 명시적으로 요청했다. Phase N과 선행 Phase 10/W에 변경 범위를 반영했다.
- 구현 방향: 중성 표면·잉크 본문, 전폭 집필 이미지 랜딩, 작품 목록과 생성 폼의 역할 분리, 원고 중심 편집기와 차분한 보조 패널. 동의 고지·접근성 역할·API·저장/생성 동작은 유지한다.

- 현재 팔레트: WCAG 2.2 AA 59짝 전수 검산, 실패 0. 현재 검산 수의 provenance 연결은 이 로그로 옮겼다(2026-08-11 과거 측정값은 보존). 중성 본문 AAA 가드는 실제 slate-900과 현재 표면을 검사한다.

## 세션 2 — Phase N 구현·마감: 구현 AI 중단 트리 이어받기 (오너 승인 "블루는 주요 버튼과 선택 상태의 포인트로 남기겠습니다")

구현 AI가 N1~N4와 1차 브라우저 검증까지 마친 뒤 사용 한도로 중단했다. 이 세션이 그 트리를 이어받아 수선·검증·커밋·문서를 마감했다.

### Goals
- 승인된 Phase N 구현 완결: 중성 표면·본문, 랜딩 첫 화면 재구성, 서재 정보 위계, 편집기·세부 페이지 배치.
- 중단 트리의 깨진 끝(빌드 실패)을 복구하고 기준선을 다시 재다.

### Completed work
- **구현(`95418bc`)** — 세부는 커밋 메시지와 계획의 N1~N4 표가 정본. 요약: 팔레트 중성화(검산 30→59짝) · 랜딩 전폭 사진 히어로+워드마크+순서 블록+반전 CTA · 서재 2열 · 편집기 독립 읽기 폭 · `:where(button)` 2차 컨트롤 기본값 · 42/26rem 분기 · 신규 셀 `Landing.test.tsx` 2개 · typeScale MIGRATED 9항목 · webp 위생 예외.
- **이어받기 수선 ① — 마지막 빌드가 죽어 있었다**: 중단 세션의 `npm run build`가 `Landing.test.tsx:14` 의 TS 오류(Playwright 의 `exact` 옵션을 testing-library `getByRole` 에 옮긴 것 — `ByRoleOptions` 에 그 키가 없다)로 실패한 채 끝났다. 문자열 `name` 은 전체 일치가 기본이라 `exact` 는 처음부터 불필요했고, 제거로 의미를 보존한 채 수선(주석 한 줄로 근거를 셀에 남김).
- **이어받기 수선 ② — 브라우저 검증이 낡은 dist로 돌아 있었다**: 중단 세션의 스크린샷·results.json(09:31)은 2차 CSS 수정(320px 오버플로 처방)**이전** 빌드였고 페이지 에러 4건이 찍혀 있었다. 빌드 복구 후 하네스를 재실행했다 — **19면 오버플로 0 · 에러 0**(에러 4건은 낡은 dist의 것이었고 재실행에서 소멸). 함정: **실패한 `npm run build` 는 dist 를 못 바꾼다** — 이어받기 세션은 빌드 EXIT 를 먼저 보고 dist 시각을 확인한다.

### Issues found
- 320px: 랜딩 nav 줄바꿈 · 장면 생성 버튼 폼 밖 밀림 → 26rem(nav 링크 숨김)·42rem(폼 요소 full-basis)으로 폐쇄(구현 세션 처방, 이 세션 재실행으로 확인).
- 이 세션 자책 함정 하나: 세션 cwd 가 `frontend/` 에 남은 채 `cd frontend && …` 를 붙여 전수가 **한 줄도 못 돌고 EXIT=1** 로 조용히 죽었다(로그에 `Test Files` 줄이 없는 것으로 바로 판별). 절대경로로 재실행. 원복 명령은 항상 절대경로 — HANDOFF 함정 절의 기존 규칙이 프런트 전수에도 그대로 적용된다.

### Decisions — User Decisions and Rationale
- 오너(2026-09-14): *"블루는 주요 버튼과 선택 상태의 포인트로 남기겠습니다. 이번에는 색상뿐 아니라 랜딩의 첫 화면 구성, 서재의 정보 위계, 편집기와 세부 페이지의 배치도 함께 살펴보겠습니다."* — Phase N 계획의 A안을 확정하고 범위를 구조 개선까지 넓혔다. 기존 Phase 10 D2·Phase W의 "큰 블루 면 유지"는 이 결정으로 대체됐다(양 계획 문서 머리에 안내 문구 추가, SoT v1.8.69).

### Verification
- **프런트 전수**: `frontend/` 안에서 `npx vitest run --reporter=basic > 파일` — **491 passed / 42 files · EXIT=0**. 기준선 489/41 대비 **+2 passed · +1 file** = 신규 `Landing.test.tsx` 2셀의 정확한 몫. 알려진 플레이크 셋은 오늘 발화하지 않았다.
- **빌드**: `tsc --noEmit` 통과 · `npm run build` EXIT=0(17.95s).
- **팔레트**: `10_palette_contrast.py` — **59짝 실패 0**(중성 면×전경 28짝 + 반전면 1짝 신설).
- **백엔드 전수**(test-mongo PRIMARY 확인 후 호스트): **3075 passed / 1 skipped / 4272 subtests · EXIT=0** · 1776.81초(29:36 — 이 머신의 로컬 값, 종전 351초보다 느린 날; 소요는 판정이 아니다). **귀속 +33 subtests 를 양단 실측으로 갈랐다** — 가드 세 파일(`test_docs_indexes`·`test_repo_hygiene`·`test_design_token_provenance`)이 기준점 `3ef1089` 1053 → 계획 커밋 `f8b636f` 1055(**+2 = 신규 계획 등재, 세션 1 몫**) → 작업 트리 1086(**+31 = 검산 29→59짝 +29 · provenance 귀거지 이 로그로 +1 · webp 예외 +1, 세션 2 몫**). passed 무변 = 백엔드 소스 무변과 일치.
- **변이(신규 셀 2개, 구현 커밋 뒤 cp 백업 방식 — 남의 문서 변경이 남은 트리라 `git checkout` 을 쓰지 않았다)**: 4종 전부 기명 재실패 — under ①하단 진입 버튼 배선 제거 → 셀1 실패 ②둘러보기 링크 목적지 제거 → 셀2 실패 · over ③nav 로그인을 가입 콜백으로 → 셀1 실패 ④가입 행동을 고지 앞으로 이동 → 셀2 실패. 원복은 `cmp` 바이트 확인 + 초록 2/2.
- **브라우저**: `/tmp/eright-browser/inspect.cjs`(고정 픽스처 API 라우팅 · 4179 정적 dist) — 랜딩 1440/390/320 · 로그인 390 · 서재·원고·편집기·설정 × 1440/768/390/320 = **19면 전부 오버플로 0 · 페이지 에러 0**. 랜딩 데스크톱/320 · 서재 · 편집기 · 원고 320 · 설정 여섯은 눈으로 확인했다(중성 면 위 작품명·원고 우선, 블루는 주요 버튼·선택 상태에만). 제약: 라이브 LLM 무관 픽스처 경로 — 실사용은 도그푸드 몫.

### Next steps
- 오너 육안 확인(실기기 포함) → 도그푸드 관찰. 웹폰트 자체 호스팅·serif 제목 서체·비활성 버튼 색 갈림길은 그대로 열려 있다(HANDOFF 6번).

## 세션 3 — LLM 출력 가드 조사 + 생성 표면 빈 출력 가드 (오너 요청 "가드 있는지 확인 + 보강")

### Goals
- gemma4_12b 게이트웨이의 LLM 호출/응답 가드 목록(오너 제공 분석)을 기준으로 이 저장소의 가드 현황을 대조·조사하고, 빠진 것이 있으면 보강한다.

### Completed work
- **가드 인벤토리 대조 완료** — 게이트웨이(`services/llm_gateway/`): stream 거부·thinking 토글(gemma4 485c4e2 이식)·창 가드 K-3(호출 전 `입력+출력상한≤n_ctx` 서버 실측 판정)·빈 choices 거부·`<thought>` 마크업 제거(닫히지 않으면 빈 문자열)·usage 엄격 검증. 앱: agent_loop 이중 예산·WritingLoopPolicy 상한(revision 2/검색 1/게이트 3)·`UnchangedWritingRevision` 루프 종료(동일 반복 차단 아날로그)·repair 상한(report 2회/extractor·judge 1회)·job 재시도 상한+쿨다운·gate/report/extractor/judge/planner 전부 strict 파서(스키마 exact-set·enum·증거 실재·1-based 포인터 검증). gemma4에만 있고 여기 없는 것(`reasoning_content` 재전송 차단·eval 금지)은 구조적으로 불필요(`ChatMessage`에 해당 필드 없음·계산기 없음).
- **빈틈 2건 발견** — GAP-1: `finish_reason`을 게이트웨이가 반환하지만 앱 전체에서 아무도 소비하지 않음(`length`=잘린 출력이 완성 후보로 스크래치 저장·job 성공·과금). GAP-2: 생성 표면(산문 경로)만 빈 출력을 판단하지 않음 — 게이트/accept/수동 입력(400)은 이미 같은 계약으로 거부.
- **GAP-2 폐쇄** (`09c002f`) — `WritingService.generate`에서 빈(공백만) `result.content`를 `INVALID_RESPONSE` `ProviderError`(502/PROVIDER_ERROR)로 승격. 게이트웨이 수준 거부는 기각: `닫히지 않은 thought → 빈 content 통과`가 변이 테스트까지 있는 문서화된 계약이라, 거부는 소비자 몫이고 다른 소비자는 전부 이미 거부한다.
- 회귀 테스트 `test_empty_provider_output_is_rejected_as_provider_fault` 신설(양방향 명시).

### Issues found
- GAP-1(finish_reason 미소비)은 정책 방향이 갈리는 진짜 분기라 구현 전 결정 브리프를 제시했다(아래 Decisions). 잘린 report JSON은 같은 상한으로 repair 2회 재생성 후 같은 이유로 잘리는 낭비가 구조적으로 존재한다.

### Decisions — User Decisions and Rationale
- (대기 중) GAP-1 finish_reason 계약 — 브리프 제시: 옵션 A 게이트웨이 에러 승격(기각 권고) / B 산문 경로에서 `stop` 외 종료 거부(추천) / C audit 기록+UI 표시만 / D repair 단락(효율 후속). 오너 결정 대기.

### Verification
- `tests/test_writing.py` 69 passed / 22 subtests(변이 전) → 신규 셀 포함.
- 변이 검증(구현 커밋 `09c002f` 뒤): 가드 조건을 `False and …`로 무력화 → 신규 셀 기명 재실패(1 failed) → `git checkout` 원복, 트리 clean 확인. over-strict 방향은 기존 `test_plain_prose_is_wrapped_into_candidate`(앞뒤 공백 산문 통과)가 잠금.
- 광범위: writing 가족+게이트웨이 provider 8파일 237 passed / 140 subtests.
- 패턴 스윕: `result.content` 소비처 전수 — 나머지는 전부 strict 파서로 빈 출력 이미 거부, 무방비 소비자는 산문 경로뿐이었다.

### Next steps
- GAP-1 오너 결정 → 선택지 반영 구현(선택 시 repair 단락 후속 포함 검토).

### 세션 3 후속 — GAP-1 결정 반영 (B + repair 단락, `8f6682c`)

오너가 브리프에서 **B + repair 단락**을 선택했다("finish_reason=length(출력 잘림) 등 stop 외 종료를 어떻게 다룰까요?" → B+D).

- **B**: `WritingService.generate` 에서 `finish_reason != "stop"` 이면 `INVALID_RESPONSE` `ProviderError`(502/PROVIDER_ERROR)로 거부. 실제 종료 사유를 에러 메시지에 실었다. 빈 content 가드(GAP-2) 바로 뒤 같은 자리·같은 분류다.
- **D**: `report.enrich_metered` 의 repair 루프가 **최신 결과** 기준 `finish_reason == "length"` 면 재시도를 생략한다(repair 도중 잘리면 다음 repair 도 건너뜀) — 같은 `max_tokens` 상한의 재생성은 같은 잘림을 반복하므로 `MAX_REPORT_REPAIRS=2` 만큼의 전체 생성이 예측 가능하게 낭비됐다.

#### Verification
- 신규 셀 2: `test_truncated_provider_output_is_rejected_as_provider_fault`(test_writing.py) · `test_truncated_first_output_skips_the_repair_loop`(test_writing_report.py). 기존 fixture 전수가 `finish_reason="stop"`임을 grep으로 확인(가드가 기존 경로 무변).
- 변이(구현 커밋 뒤): B 조건 `False and …` 무력화 + D 조건 `and True` 무력화 → 두 셀 기명 재실패(2 failed) → `git checkout` 원복, 트리 clean. over-strict 방향은 각각 `test_plain_prose_is_wrapped_into_candidate`·`test_invalid_first_output_repairs_once`이 잠근다.
- 광범위: writing 가족+게이트웨이 provider+분석 파서 13파일 **400 passed / 187 subtests**.

#### 패턴 스윕 — 같은 낭비가 다른 repair 경로에도 있다 (추적 부채)
D와 동일한 "length 인데 repair 를 돈다" 낭비가 1회 repair 파서 4곳에 반복된다. 결정 문면은 report 에 국한됐으므로 이번 슬라이스에서 고치지 않고 부채로 남긴다(트리거: 다음으로 이 경로들의 낭비를 실측하거나 length 관련 결정을 다룰 때 같은 조건으로 확장):
- `services/application/app/analysis/extractor.py:142` (`_repair_once` 호출부)
- `services/application/app/analysis/compare_judge.py:113`
- `services/application/app/analysis/identity_judge.py:109`
- `services/application/app/context_search/planner.py:119`

## 세션 4 — 검증 조건 3건 폐쇄 (오너 지시 "검증기록 확인해서 보강할 부분 보강해줘")

### Goals
- 독립 검증 [`verifications/2026-09-14/llm_output_guards_gap1_gap2.md`](../verifications/2026-09-14/llm_output_guards_gap1_gap2.md)(`df4e909`, 조건부 합격·조건 3)의 C1·C2·C3와 하드닝 H1·H2·H4·H5를 닫는다. H6은 검증자가 "엄격 리터럴이 오히려 정확한 해석"이라 판정한 대로 무동작. H7 기준선은 본 세션 전수로 재갱신(검증자가 3078로 올린 줄을 이번 셀 몫만큼 다시).

### Completed work
- **C1(a) 결정 해석**: 오너의 "보강할 부분 보강해줘"를 브리프 옵션 (a) 확장으로 받았다 — revise의 잘린 치환문이 원고에 splice 되는 것은 GAP-1이 막기로 한 바로 그 실패 모드라 (b) 범위 명시는 보강이 아니다.
- **C1**(`d26fe1e`): `WritingRevisionService.revise_metered` 에 `finish_reason != "stop"` 거부 추가 — `MeteredCallError(ProviderError(INVALID_RESPONSE), usage)` 로 루프 토큰 집계 보존. 셀 `test_truncated_replacement_is_rejected_as_provider_fault`.
- **C2**(`d26fe1e`): mid-loop 분기(`result = retry`) 잠금 — `_Provider` fixture가 (content, finish_reason) 쌍을 받도록 확장(기존 str 셀 무변), 셀 `test_a_repair_that_finishes_length_stops_further_repairs`("bad3" 미끼로 calls 수로 재실패).
- **H4**(`d26fe1e`): generate 빈 content 에러 메시지에 `finish_reason` 동봉.
- **C3**: SoT v1.8.70 — 헤더·버전 행·Phase 5 본문 불릿(계약 구조 "게이트웨이는 통과·소비자가 거부"·산문 두 표면·report length 단락·부채 5곳 트리거). `05-writing-generation-decisions.md` 후속 계약 절·`05-writing-report-api-decisions.md` "1회 repair"→2회 드리프트 정정(근거 `3fb3b08`, 2026-07-18)+length 단락. README ④·HANDOFF 정본 셀 v1.8.70(상호 가드 `test_the_readme_names_the_current_contract_version` 대응).
- **H1**: 부채 목록에 5번째 동일 패턴 `writing/retrieval.py:144` 등재(SoT 불릿·generation 플랜 유예 절 모두 5곳으로).
- **H2/H5**: CHANGELOG "변이 5종"→3종(under) 정정 + 근거 문구, `product-overview.md` 낡은 finish_reason 문구 정정.

### 변이 표 (구현 커밋 `d26fe1e` 뒤 — 매 회 원복·clean 확인)

| # | 방향 | 적용 diff | 위치 | 재실패 셀 |
|---|---|---|---|---|
| M8 | under | `if result.finish_reason != "stop":` → `if False and …:` | `revise.py`(revise_metered) | `test_truncated_replacement_is_rejected_as_provider_fault` (1) |
| M7b | under | `result = retry` 줄 삭제(검증 M7 재현) | `report.py:136` | `test_a_repair_that_finishes_length_stops_further_repairs` (1 — calls 3≠2) |
| M10 | over | `if result.finish_reason != "stop":` → `if True:` | `revise.py` | 정상 revise 셀 3개 재실패 |

### Verification
- 집중(파일 목록, H3): `tests/test_writing_revise.py` `tests/test_writing_report.py` `tests/test_writing.py` — **142 passed / 84 subtests**.
- 문서 가드: `tests/test_docs_indexes.py` `tests/test_repo_hygiene.py` — **29 passed / 966 subtests**(SoT/plans/CHANGELOG/product-overview/README/HANDOFF 편집 뒤).
- 전수(호스트·파일 캡처): **3080 passed / 1 skipped / 4274 subtests · EXIT=0 · 1885.32초** (+2 passed = 신규 셀 2 · +2 subtests = 검증 기록 `df4e909`의 기록 파일·인덱스 행 몫 — 검증자 전수 뒤 커밋돼 이번 전수가 처음 짊어짐. 본 슬라이스 문서는 기존 파일 편집만이라 subtests 무변). 기준선 줄(HANDOFF)·README ②행 동시 갱신.

## 세션 5 — LLM 출력 가드 조건 폐쇄 독립 재감사

### Goals
- C1~C3 폐쇄 주장과 SoT v1.8.70의 산문 두 표면 계약을 구현·테스트·변이로 다시 대조한다.

### Completed work
- C1 length 가드 제거·C2 `result = retry` 삭제·stop도 거부하는 과잉 교정 변이를 각각 재적용했다. 새 revise length 셀, C2 calls=2 셀, 기존 stop 정상 셀이 각각 재실패해 그 세 경계는 성립했다.
- 독립 기록 `verifications/2026-09-14/llm_output_guards_closure_reaudit.md`와 인덱스를 추가했다. 이 검증은 코드·테스트를 수정하지 않았다.

### Issues found
- **B1 차단**: 정본은 revise도 빈/공백 content를 `provider_invalid_response`로 분류하고 finish_reason을 진단에 싣는다고 하나, `revise.py`는 먼저 `InvalidWritingRevision`으로 분기한다.
- **B2 차단**: 계약은 `finish_reason != "stop"` 전체인데 양 표면의 회귀 표본은 `length`뿐이다. revise 가드를 `== "length"`로 좁힌 변이도 기존 length·stop focused 셀이 모두 통과해, 다른 non-stop 문자열을 허용하는 과소 보정을 잡지 못했다.

### Verification
- focused 원 트리: 5 passed (revise length·정상 계량, report initial/mid-loop length·stop repair).
- 변이: C1 가드 제거 → 1 failed; C2 최신 결과 갱신 제거 → calls 3≠2, 1 failed; stop도 거부 → 정상 revise 2 failed; `!= "stop"`→`== "length"` → 기존 focused 2 passed(무셀 증명). 변이마다 역패치로 복원하고 diff가 비었음을 확인했다.
- 새 차단을 확인한 시점에 작업자 전수 3080/1/4274은 이 세션에서 재실행하지 않았다. B1·B2 폐쇄 뒤 clean 트리에서 환경과 함께 재측정할 일이다.

### Next steps
- B1(빈 revise 결과의 `INVALID_RESPONSE` 분류·finish_reason 메시지·usage 보존)과 B2(생성·revise 각 non-stop 일반값 회귀)를 시행한 뒤 독립 승격 재검과 전수를 수행한다.

## 세션 6 — LLM 출력 가드 재감사 차단 B1·B2 폐쇄

### Goals
- 재감사 기록의 B1(빈 revise 결과 분류·진단·usage)과 B2(두 산문 표면의 length 외 non-stop 종료 경계)를 SoT v1.8.70 그대로 최소 변경으로 닫는다.

### Completed work
- **B1**: `WritingRevisionService.revise_metered`의 빈/공백 replacement를 `InvalidWritingRevision`이 아닌 생성 표면과 같은 `ProviderErrorCode.INVALID_RESPONSE`로 분류했다. `MeteredCallError`를 유지해 usage를 보존하고, 메시지에 `finish_reason`을 넣었다. 2026-07-13의 기존 셀이 공백과 unchanged evidence를 같은 도메인 오류로 묶은 것을 발견해, 전자는 public `revise()`의 provider 502·후자는 도메인 오류로 분리했다.
- **B2**: 생성·개정 각각에 `finish_reason="content_filter"` 회귀를 추가했다. 기존 `length` 셀과 합쳐 `!= "stop"` 일반 계약을 잠그며, 각 셀은 code·실제 종료 사유·retryable을, revise는 usage까지 단정한다. 정상 `stop` 경로는 기존 생성/개정 성공 셀이 over-strict 방향으로 유지한다.

### 변이 표 (checkpoint `f5060b8` 뒤 — 매 회 역패치 원복·clean 확인)

| # | 방향 | 적용 diff | 위치 | 재실패 셀 |
|---|---|---|---|---|
| M11 | under | 빈 replacement의 `ProviderError(...)` → `InvalidWritingRevision("replacement must not be empty")` | `revise.py:135` | `test_revise_metered_empty_result_is_provider_fault_and_carries_usage` (1) |
| M12 | under | 두 `if result.finish_reason != "stop"` → `== "length"` | `service.py:130`, `revise.py:151` | `test_non_stop_provider_output_is_rejected_as_provider_fault`, `test_non_stop_replacement_is_rejected_as_provider_fault` (2) |
| M13 | over | 두 `if result.finish_reason != "stop"` → `if True` | `service.py:130`, `revise.py:151` | `test_plain_prose_is_wrapped_into_candidate`, `test_replaces_only_unique_evidence_and_clears_stale_report` (2) |

### Verification
- contract focused: 생성 빈·length·content_filter·정상 stop, 개정 metered 빈·public 빈·length·content_filter·정상 splice·unchanged **10 passed** (`-p no:cacheprovider`).
- related classes: `GenerateTest` + `WritingRevisionServiceTest` **20 passed / 4 subtests** (5.89초).
- 문서 가드: `test_docs_indexes.py` **20 passed / 330 subtests** (13.27초), `test_repo_hygiene.py` **9 passed / 638 subtests** (25.42초).
- 3파일 전체는 실행 셀 30초 제한으로 12개 뒤 강제 종료되어, 변경 경계의 named focused·두 관련 클래스로 분할 검증했다. 전수는 이 작업자가 시작하지 않았다.

### Next steps
- 독립 승격 재검과 환경을 명시한 전수 재측정은 다음 검증자의 몫이다. 1회 repair 파서 5곳의 length 낭비는 SoT 트리거가 올 때까지 유예다.
