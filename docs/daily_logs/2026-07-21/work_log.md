# Work Log — 2026-07-21

## Task — 문체/분량 슬라이스 증분 2: 생성 분량 프리셋 (D3=A, SoT v1.7.22)

### Goals

- `plans/writing-style-and-length-control-decisions.md`의 확정 결정 **D3=A**(프리셋 매핑 1024/2048/4096)를 구현한다.
- 출력 길이를 서버 전역 고정값에서 **요청별 프리셋**으로 승격하되, 서버가 프리셋→토큰 매핑을 소유한다.
- 기존 입력 예산 필드 `max_tokens`의 의미·이름을 바꾸지 않는다.
- `long`(4096)을 단일 generate 전용으로 두고 자동 revise/gate 루프에 태우지 않는다.

### Completed work

- **backend — 도메인 계약**: `writing/models.py`에 `OutputLength` StrEnum(`short|medium|long`)을 추가했다(WritingIntent/WritingTaskType 옆). 작가 언어의 심볼릭 프리셋이며 토큰 매핑은 서버가 소유해 wire 계약이 모델 교체에 불변이다.
- **backend — 프리셋→토큰 매핑(fail-loud)**: `main.py`에 `_writing_output_length_tokens() -> dict[OutputLength, int]`를 추가했다. 증분 1의 `_project_brief_style_example_limits()`를 동형 미러링해 env 조정 가능(`WRITING_OUTPUT_LENGTH_SHORT|MEDIUM|LONG`)·1 미만이면 기동 실패다. **`short`는 미설정 시 기존 `WRITING_GENERATE_MAX_TOKENS`를 승계**해 이미 그 env를 튜닝한 운영자의 값을 보존한다(하위 호환). `create_app` 진입부에서 style-example 상한 옆에 호출해 잘못된 env를 기동 시점에 시끄럽게 실패시킨다.
- **backend — 요청 필드 + 엔드포인트 배선**: `WritingGenerateRequest`에 `output_length: str = OutputLength.SHORT.value`를 추가했다. generate 엔드포인트가 `OutputLength(body.output_length)`로 프리셋을 해석(알 수 없는 값은 task_type과 동형으로 **400**)하고 매핑 dict에서 토큰을 뽑아 `writing.generate(..., max_output_tokens=output_tokens)`로 넘긴다.
- **backend — 서비스 override**: `WritingService.generate`에 `max_output_tokens: int | None = None`을 추가했다. None이면 생성 시점 기본값(`self._max_tokens`)을 유지해 직접 호출자/테스트는 무변이고, HTTP 경로만 프리셋 값을 override한다.
- **frontend — 프리셋 선택 + long 루프 스킵**: `WritingPanel.tsx`에 `outputLength` state(기본 `short`)와 "생성 분량" select(짧은 수정/중간부터 이어쓰기/전체 작성)를 배선했다. generate 요청에 `output_length`를 실어 보내고, **`long` 선택 시 적격 finding이 있어도 자동 revise/gate 루프를 건너뛰고** 안내 notice를 띄운다(4096≈91초는 loop wall clock 60초 초과 → 단일 generate 전용). `gen:api`로 `schema.d.ts`에 `output_length` 1개만 additive.

### Issues found

- **없음(신규 결함)**. 기존 `WritingPanel.test.tsx`의 generate body exact-match(`toEqual`)가 새 필드로 깨져 `output_length: "short"`를 기대값에 추가했다(내 변경이 원인, 계약 확장에 따른 예상된 갱신).

### User Decisions and Rationale

- 이 슬라이스는 **오너 확정 결정(D3=A, 매핑 1024/2048/4096)**의 구현이며 새 오너 결정은 없다. 구현자 판단으로 정한 사항은 아래 Decisions 참조.

### Decisions (구현자 판단)

- **`output_length`는 심볼릭 프리셋(`short|medium|long`)이지 원시 토큰 수가 아니다.** D3의 근거("작가 언어", "UI 계약이 모델 교체에 불변", "서버가 매핑 소유")가 심볼릭을 요구한다 — 클라이언트가 숫자를 보내면 서버가 매핑을 소유하지 않게 된다.
- **매핑을 env 조정 가능 + fail-loud로 두었다(고정 상수가 아님).** Next Tasks의 "확정값"과 Follow-up의 "env 조정 가능"은 "확정값을 기본값으로, env override 가능"으로 화해된다. 증분 1(오너 2=B)이 style-example 상한에 정확히 이 패턴을 썼으므로 슬라이스 내 일관성을 위해 동형 적용했다. `short`가 기존 `WRITING_GENERATE_MAX_TOKENS`를 승계하도록 해 기존 env가 고아가 되지 않게 했다.
- **`long` 단일 generate 전용 강제 = `output_length`를 generate 전용 knob으로 둔다.** revise-and-gate 요청 모델(`WritingReviseRequest`)에는 필드를 넣지 않아 구조적으로 4096을 루프에 태울 수 없다(루프 내부 revise는 512tok로 무관). 프론트도 `long` 뒤 자동 루프를 건너뛰어 계약 의도("단일 generate 전용")를 표현으로도 지킨다. 이는 비동기 패드 D5(1024 동기 / 2048·4096 비동기) 방향과도 정합한다.
- **compose 무변**: 확정 기본값(1024/2048/4096)이 코드 기본이라 compose에 env를 추가하지 않았다(증분 1 style-example 상한도 compose에 없음 — 선례 일치). loop wall clock(60000)은 기존 그대로.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1238 passed / 73 skipped / 320 subtests**. 신규 `tests/test_writing.py::WritingOutputLengthPresetTest` 9건:
  - under-strict: 기본 프리셋=short=1024, 세 프리셋→1024/2048/4096(매핑 제거 시 medium/long이 서비스 기본 1024로 떨어져 bite), **short 경로 독립 잠금**(검증 후속 hardening #1 — `WRITING_OUTPUT_LENGTH_SHORT=1500` override 시 필드 생략 요청도 1500 도달; short가 서비스 기본값 1024와 우연히 일치해 "override 제거"를 단독 못 잡던 gap을 닫음).
  - not-fire: 알 수 없는 프리셋→400 + 모델 미도달.
  - over-strict: `output_length`가 입력 `max_tokens`와 독립(한 축을 움직여도 다른 축 불변), env override 재매핑, `short`의 `WRITING_GENERATE_MAX_TOKENS` 승계, 잘못된 env(0/음수/비정수) 기동 실패, `output_length`가 revise-and-gate 요청 모델에 부재(generate에만 존재).
- frontend: `npx vitest run` → **161 passed / 11 files**(WritingPanel +2: 선택 프리셋 전송, `long` 루프 스킵+notice[over-strict: outputLength 체크 제거 시 3번째 fetch로 bite]). `npx tsc --noEmit` clean. `npm run build` 101 modules(CSS 18.48 / JS 394.62 kB). `npm run gen:api`는 generate 요청에 `output_length` 1개만 additive.
- `git diff --check` clean. LLM 미사용 슬라이스다.

### Next steps

- **증분 3(D4+D5+D6)**: `character_observation` payload에 `aspect` 추가(taxonomy 3종 유지), Gate `style` finding(warning 전용·자동 revise 제외·block 없음), `저자 설정 > canonical 관찰 > candidate 관찰` 우선순위 명시.
- 증분 2 완료로 **비동기 패드 D5의 분기 기준(1024 동기 / 2048·4096 비동기)이 성립**한다 — 비동기 생성+결과 패드 슬라이스(`plans/async-generation-pad-decisions.md` D1~D7)의 soft ordering 선행 조건 충족.
- 실 12B 관통(프리셋별 실측 시간·타임아웃)은 오너 풀스택 후속(sandbox는 12B 불가).

## Task — 오너 독립 검증 PASS(조건 없음) 후 비차단 hardening 반영

### User Decisions and Rationale

- 오너가 증분 2를 독립·적대적 감사해 **PASS(조건 없음)** 판정을 주고(`docs/verifications/2026-07-21/increment2_d3_output_length_preset.md`), "보강할 부분 보강하고 커밋"을 지시했다. 검증자는 self-claim 수치를 인용하지 않고 backend 1237/73/320·frontend 161/11·tsc/gen:api/diff를 전부 재실행해 일치를 확인했고, boundary matrix에 빈 셀이 없음과 정본 자기모순 부재를 재도출했다.

### Completed work

- **hardening #1 반영 — short 경로 독립 잠금(`test_short_preset_override_reaches_generation`)**: 검증이 지적한 유일한 실질 gap은 short under-strict가 서비스 생성 기본값(1024)과의 우연 일치로 "endpoint override 전체 제거"를 단독으로 못 잡는다는 것이었다(bite는 medium/long이 담당해 cell 자체는 채워져 있었음). `WRITING_OUTPUT_LENGTH_SHORT=1500` override 하에 필드 생략 요청이 1500에 도달하는지 단정해 short 경로를 독립적으로 load-bearing하게 만들었다 — `max_output_tokens=` 제거 시 provider가 서비스 기본 1024를 받아 이 테스트가 bite한다.
- **hardening #2 반영 — 비정수 env 기동 실패 명문화**: SoT v1.7.22 버전로그와 Phase 5 clause의 "1 미만이면 기동 실패"를 "**값이 1 미만이거나 정수로 파싱되지 않으면 기동 실패**"로 정정했다. 코드/테스트는 이미 `_env_int`의 `int()` 파싱으로 잠겨 있었고 fail-loud 정신에 포함되나, 정본 문구에는 열거되지 않아 계약 완전성을 보강했다.
- **조치 불요(검증자 판단 수용)**: #3(`05-writing-ai.md:81`의 dormant agent-loop budget "1024" — 역사 plan doc, 정본 무영향)·#4(long ≈91초 실측 — sandbox 12B 불가, 오너 풀스택 후속)·#5(`output_length: string` enum 아님 — task_type 선례와 일관된 설계 선택)는 차단 사유가 아니고 조치가 오히려 churn/추측이라 skip했다.

### Verification

- backend: **1238 passed / 73 skipped / 320 subtests**(`WritingOutputLengthPresetTest` 8→9). frontend·tsc·build·gen:api는 무변(백엔드 테스트 1건 + SoT 문구만 추가). `git diff --check` clean.

## Task — 문체/분량 슬라이스 증분 3(1/2): character_observation optional aspect (D4=B, SoT v1.7.23)

### Goals

- 브리프 D4=B(`character_observation` payload에 어투 식별용 `aspect` 필드 추가)를 구현한다.
- taxonomy 3종 동결(2A D5=A)을 지키면서 payload만 확장한다.

### User Decisions and Rationale

- **D4 aspect = optional (오너 결정, 2026-07-21)**: 브리프 D4=B 옵션 표의 원 리터럴은 exact `(name, observation, aspect)` **필수**였다. 착수 시점 코드 스코핑에서 **candidate 생성 경로가 payload를 검증**함(`record_candidate`→`record_candidates`→`_prepare_candidate_record`→`_validate_payload`→`validate_candidate_payload`, exact-match)을 확인했고, 필수화 시 `{name, observation}`으로 candidate를 만드는 **테스트 25개 파일 + 저장된 live candidate가 즉시 무효**가 되어 대규모 fixture 수정 + 마이그레이션 스크립트가 필요함이 드러났다. 반면 이 필드의 핵심 가치(캐릭터 어투 검증)는 브리프 Follow-up상 **캐릭터-어투 설정 저장이 deferred**라 이번 증분에서는 forward-defense다. 이 blast radius/deferred 근거를 오너에게 제시(required vs optional 선택지 표)했고 오너가 **optional**을 채택했다. CLAUDE.md §1("더 단순한 접근이 있으면 말하고, 정당하면 밀어붙인다") + exact-tuple 리터럴 대비 대폭 축소된 표면.

### Completed work

- **validator(`analysis/schema.py`)**: `_REQUIRED_FIELDS`에 더해 `_OPTIONAL_FIELDS` 매핑을 신설(character = `("aspect",)`). exact-match 단정을 (a) required ⊆ observed(누락 required 거절), (b) observed ⊆ required∪optional(unknown field 거절)로 분해했다. present field는 required든 optional이든 non-empty string 검증, normalized는 required→optional 순으로 결정적 조립. event/open_question은 optional 없음 → aspect가 unknown field로 거절된다.
- **추출 프롬프트(2곳)**: `prompt_templates.py`(기본)·`extractor.py`(repair)의 character payload 설명에 optional `aspect`("voice"/"trait" 예시, 생략 가능) 안내를 추가했다.
- **surface(추가 코드 0)**: 저장된 payload는 `main.py`가 `dict(candidate.payload)`로 wholesale 직렬화(1646/2673행)하므로 aspect가 review inbox/candidate detail/conflict diff(`_payload_diff`)에 자동 노출된다. `memory/scope.py`(name만)·`indexing/memory_index.py`(name+observation)는 aspect-agnostic이라 무변(색인 enrich·Gate 대조는 D5).

### Decisions (구현자 판단)

- **aspect는 자유 문자열(enum 아님)**: 브리프 Follow-up "값 집합을 캐릭터 전용으로 못 박지 말고 확장 가능하게 둔다" — validator는 non-empty string만 강제하고 값 어휘(voice/trait/…)는 프롬프트 convention. over-strict 회귀로 임의 값 통과를 잠갔다.
- **마이그레이션 없음**: optional이라 기존 payload가 그대로 유효 — W3 ordered-unit식 migration script 불요.
- **색인/Gate 미배선**: aspect를 index text나 Gate 대조에 넣는 것은 D5 범위. D4는 "저장 + surface"까지.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1245 passed / 73 skipped / 322 subtests**(신규 `tests/test_analysis_extractor_schema.py::CharacterAspectPayloadTest` 7건, boundary matrix):
  - under-strict: `{name,observation}` 하위호환 유효, `{name,observation,aspect}` aspect 보존, empty aspect 거절, 기타 unknown field(mood) 거절, required 누락 거절.
  - over-strict: aspect 값이 자유 문자열(enum 아님), aspect가 event/open_question엔 불허(character-only optional).
- 회귀 무손상: 기존 `test_all_three_phase2a_payload_shapes_are_accepted`(정상 3 shape)·`test_malformed_payload_is_rejected_by_service`(누락/빈/extra/타입혼동) 그대로 통과.
- frontend/gen:api 무변(payload는 무타입 dict). `git diff --check` clean. LLM 미사용.

### Next steps

- 증분 3 D5+D6은 같은 날 이어서 구현했다(아래 Task 참조).

## Task — 문체/분량 슬라이스 증분 3(2/2): Gate style finding + 문체 우선순위 (D5=A/D6=A, SoT v1.7.24)

### Goals

- 브리프 D5=A(`style` finding type, warning 전용·자동 revise 제외·block 없음)와 D6=A(우선순위 `저자 설정 > canonical 관찰 > candidate 관찰`을 문체에 적용, 경고이지 차단 아님, 최종 결정은 사용자)를 구현한다.

### User Decisions and Rationale

- 이 슬라이스는 오너 확정 결정(D5=A/D6=A)의 구현이며 새 오너 결정은 없다. 아래 "Decisions"의 advisory-vs-escalate는 D6에서 파생한 구현 판단이다.

### Completed work

- **`WritingGateFindingType`에 `STYLE` 추가**(`writing/models.py`).
- **Gate 파서(`writing/gate.py`)**: (a) `_finding`에 style 제약 추가 — style은 severity=warning·recommendation=needs_user_review만 허용(그 외 `ValueError`), 즉 error/block/revise/retrieve_more 불가. (b) `parse_writing_gate_result`의 decision 우선순위 계산을 **non-style finding으로 한정**(`decision_driving`) — style은 findings에 남아 저자에게 노출되나 decision을 끌어올리지 않는다.
- **Gate 프롬프트(`writing/gate_prompt.py`)**: "Check only: do_not_use, POV, and continuity"를 "…, continuity, and style"로 열고, style은 **저자의 project_brief 문체 설정(tone/style_rules/preferred_patterns/forbidden_patterns/style_examples)과만 대조**하는 advisory(warning·needs_user_review·never block/auto-revise)이며 **decision을 non-style로만 계산**함을 명시. 정당한 저자 선택엔 style finding을 내지 말라는 지침 포함.
- **auto-revise 제외**: `revise_gate._is_eligible_continuity_revise`가 이미 continuity 전용이라 style은 자연 제외되나, 회귀로 명시 잠금(style이 revise를 권해도 type 때문에 ineligible).
- **프론트(`WritingPanel.tsx`)**: 코어 로직 변경 없음 — findings는 decision 무관 렌더되고 `canAccept`는 `decision==="pass"`만 보므로 `pass`+style이면 accept 유지 + style finding 표시가 이미 성립. style finding에 advisory 안내("문체 참고 사항입니다. 의도한 표현이라면 그대로 채택할 수 있습니다.") 1줄 + `.finding-advisory` CSS만 추가. `gen:api`로 `WritingGateFindingType` enum에 `style` additive.

### Decisions (구현자 판단)

- **style은 advisory이며 decision을 escalate하지 않는다(D6에서 파생)**: Gate 계약상 decision은 findings에서 파생되고(`decision==max(recommendation)`) 프론트 accept는 `decision==="pass"` 조건이다. style을 needs_user_review로 escalate하면 accept가 막혀 저자가 **의도적 이탈을 채택 못 하고 재생성을 강요**받는데, 이는 D5/D6의 "차단하거나 재생성 루프를 태우면 안 된다 / 최종 결정은 사용자"와 정면충돌한다. 따라서 style을 **decision 우선순위에서 제외**해 `pass`를 유지(accept 가능)하고 경고만 표시한다. "pass only with no findings" 불변식을 "no non-style findings"로 완화하는 Gate 계약 변경이며, 임의 선택이 아니라 D6 문언에서 파생된다. style의 recommendation을 needs_user_review로 못박은 것은 "사람이 봐야 함" 신호(decision엔 미반영)이자 warning-only·block 없음의 parse 잠금이다.
- **캐릭터 어투(D4 aspect) 대조는 이번 범위 밖**: 캐릭터-어투 **설정** 저장이 deferred(Follow-up)라, 이번 style 대조는 **프로젝트 문체 설정**(ProjectBrief)까지다. aspect 관찰(D4)은 forward-defense.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1250 passed / 73 skipped / 326 subtests**. 신규 `tests/test_writing_gate.py::GateStyleFindingTest` 5건 + `test_writing_revise.py` 회귀에 style ineligible 케이스 1:
  - over-strict(D6 핵심): style만 있으면 decision=pass(우선순위에 style 포함 시 needs_user_review로 bite), style+continuity(revise)→revise, style+do_not_use(block)→block(style은 findings에 동승하나 decision 미구동).
  - under-strict: style은 warning이어야(error 거절), needs_user_review만 권고 가능(block/revise/retrieve_more 거절).
  - auto-revise: style finding은 revise를 권해도 auto-revise 안 됨(type으로 ineligible, `_is_eligible_continuity_revise` 완화 시 bite).
- frontend: `npx vitest run` → **162 passed / 11 files**(WritingPanel +1: pass+style에서 accept 유지·style finding 메시지·advisory 안내 표시, style은 loop 미진입[2 fetch]). `npx tsc --noEmit` clean. `npm run build` 101 modules(JS 394.79 kB). `gen:api`는 `WritingGateFindingType`에 `style` 1개 additive.
- `git diff --check` clean. LLM 미사용.

### Next steps

- **문체/분량 슬라이스 전체(증분 1~3) 종료.** 다음 갈림길은 **비동기 생성 + 결과 패드**(`plans/async-generation-pad-decisions.md` D1~D7 확정, 미구현) — 문체/분량 완료로 2048/4096 프리셋이 생겨 D5(1024 동기/2048·4096 비동기) 분기 기준이 성립한다. 캐릭터 어투 **설정** 저장·mood(Phase 7)는 별도 후속.

## Task — 증분 3 독립 검증 후 비차단 hardening 보강 (#1·#2·#3)

### Goals

- 독립 검증(`docs/verifications/2026-07-21/increment3_d4_d5_d6_style_and_aspect.md`, **합격·조건 없음**)이 제시한 비차단 hardening 후보 중 **code-testable 3건**을 회귀 테스트로 채운다. (#4는 LLM 행동 계약이라 code test 불가 → 후속 풀스택 12B smoke 권장으로 남김.)

### Completed work

- **D4 #1 — aspect 비문자열 거절**: `tests/test_analysis_extractor_schema.py::CharacterAspectPayloadTest::test_non_string_aspect_is_rejected`(aspect=123 → `InvalidAnalysisPayload`). 같은 `isinstance` 가드가 잡지만 전용 케이스가 없었음.
- **D4 #2 — aspect + 다른 unknown 혼합**: `…::test_aspect_does_not_permit_other_unknown_fields_alongside`(`{name,observation,aspect,mood}` → 거절). aspect 허용이 닫힌 집합을 열지 않음을 핀.
- **D5 #3 — style + 비style `needs_user_review` 혼합**: `tests/test_writing_gate.py::GateStyleFindingTest::test_style_does_not_suppress_a_non_style_needs_user_review`(continuity needs_user_review + style → decision `needs_user_review`, findings 2건). "style advisory 과적용이 genuine needs_user_review를 억제"하는 over-correction 버그를 잡는 셀.

### Decisions (구현자 판단)

- **양방향 가드를 mutation으로 경험적으로 증명했다** (문서 주장만 믿지 않음, 매 mutation 후 `git checkout` 원복):
  - #1: `isinstance` 가드를 truthy-only(`if not value`)로 완화 → aspect=123 통과 → 테스트 FAIL.
  - #2: unknown-field 검사를 `if False and …`로 중화 → mood 유입 → 테스트 FAIL.
  - #3: over-correction(style 존재 시 `expected=PASS` 강제) → 비style needs_user_review 억제 → 테스트 FAIL(`ValueError: decision does not match finding priority`).
  - 즉 3케이스 모두 under-strict(bug 재발 시 재실패) 방향이 실제로 잡힘.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1253 passed / 73 skipped / 326 subtests**(1250 + 3 신규, subtest 무변, 회귀 없음).
- frontend·tsc·gen:api는 backend-only 테스트 추가라 무변(162/11, tsc clean, schema.d.ts 무변).
- `git diff --check` clean. LLM 미사용. 계약·schema·프롬프트 무변(테스트만 추가).

### Next steps

- 검증 기록의 hardening #4(D6 "설정 기준만 판정/관찰→설정 자동 반영 없음" LLM 행동)는 code test 불가 → 후속 풀스택 12B smoke에서 관찰.
- 문체/분량 슬라이스는 이번 보강으로 boundary matrix가 더 조밀해졌고, 여전히 종료 상태. 비동기 생성+결과 패드가 다음.

## Task — 비동기 생성 + 결과 패드 슬라이스 증분 1: scratch tier 패드 준비 (D2=A + D7, SoT v1.7.25)

### Goals

- 브리프 `plans/async-generation-pad-decisions.md`(D1~D7 확정, 2026-07-20)의 착수. 큰 슬라이스라 3증분으로 쪼갠다: **증분 1 = scratch 계약 개정(D2+D7, backend+SoT)**, 증분 2 = 비동기 job 인프라(D4+D3+D5, worker LLM 루프·1024 동기/2048·4096 비동기 분기), 증분 3 = 패드 UI(D6, 읽기 전용 패드·배지·5초 폴링).
- 증분 1은 패드가 accept를 살아남고("채택 항목만 정리") 어느 version 기준인지 표시할 수 있도록 scratch tier를 준비한다. 비동기 실행 자체는 증분 2.

### Completed work

- **D7 — scratch `version_id`(additive nullable)**: `ScratchCandidate`에 `version_id: str | None = None`을 추가(`intent` seam 선례 동형). generate가 `body.current_position.version_id`를 실어 저장하고(`main.py`), Mongo 어댑터 `_doc`/`_entry`가 write/read(`doc.get("version_id")`)하며, `_writing_scratch_payload`가 노출한다. 기존 레코드는 None으로 읽혀 **마이그레이션 불요**.
- **D2=A — accept 정리를 draft 전체 → 채택 항목 단위로 축소**: 신규 repo 메서드 `delete_for_request(project_id, draft_id, request_id)`(InMemory+Mongo)와 서비스 `clear_accepted_item(...)`을 추가. `_clear_scratch_for_saved_accept`가 `clear_draft` 대신 `clear_accepted_item(project_id, cleanup_draft_id, body.request_id)`를 호출한다 — 채택된 항목(`request_id` 일치)만 삭제, 같은 draft의 다른 생성 결과는 보존, 대응 항목 없으면 no-op. **연결 수단은 이미 존재**(브리프 검증 H1): accept 요청이 `request_id`를 필수로 싣고 accept 서비스가 candidate와 일치를 검증하므로 신규 식별자 불요. 명시적 버리기(DELETE)는 `clear_draft`로 draft 전체 삭제를 유지.
- **SoT v1.7.25 개정 2곳(구현과 함께)**: §264 정리 규칙을 "draft 전체" → "채택 항목(`request_id` 일치)만"으로 축소하고 **granularity를 문구로 명시**(검증 H2: v1.7.20 승격 당시 whole-draft 의미가 rationale·구현에만 있고 문구에 없던 정밀도 결함 해소). §267 schema에 `version_id` nullable seam 추가. 버전로그 행 + 헤더 버전 bump.
- **frontend 미러 동기화**: 무타입 scratch payload를 hand-declare한 `ScratchCandidate`(client.ts, 주석에 "mirroring `_writing_scratch_payload`")에 `version_id: string | null` 추가. 로직 무변(증분 3에서 소비).

### User Decisions and Rationale

- 이 슬라이스는 오너 확정 결정(D1~D7, 2026-07-20)의 구현이며 새 오너 결정은 없다. 증분 경계와 §261 purpose-line 지연은 아래 구현자 판단.

### Decisions (구현자 판단)

- **§261 scratch 용도 확장("복구 전용" → "복구 + 비동기 결과 보관")은 증분 2로 지연**했다. 브리프는 개정 2곳(용도+정리)을 "구현과 함께"로 요구하나, worker가 비동기 결과를 scratch에 **실제로 쓰기 전**에는 용도가 여전히 복구 전용이다 — 지금 용도 문구를 확장하면 SoT가 존재하지 않는 동작을 서술한다(CLAUDE.md "SoT는 현재 사실을 반영"). 정리 granularity(§264)는 이번에 **동작을 바꾸므로** 함께 개정하고, version_id(§267)는 `intent` 선례 동형의 additive forward-defense로 정직하게 기술한다.
- **D2 per-item 정리는 패드 없이도 정합**: 다른 생성 결과는 accept 뒤에도 복구·복사 가치가 있다는 rationale은 패드 UI 존재와 무관하게 참이라, 증분 1 단독으로도 회귀가 성립한다.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1257 passed / 73 skipped / 326 subtests**(1253 + 4 net). 회귀:
  - D2 over-strict(핵심): `test_saved_accept_clears_only_the_accepted_item`·`test_partial_analysis_failure_still_clears_the_accepted_item` — 채택 항목만 삭제하고 sibling(`request_id="wr-other"`)은 생존(whole-draft `clear_draft`로 되돌리면 bite). `test_non_pass_accept_keeps_scratch`는 REVISE→둘 다 생존(len==2). 서비스 단위 `test_clear_accepted_item_removes_only_the_matching_request`·`test_clear_accepted_item_no_match_is_a_no_op`(브리프 "대응 항목 없으면 no-op").
  - Mongo 어댑터: `test_delete_for_request_removes_only_the_matching_item`(project+draft+request 3키 격리), `test_legacy_doc_without_version_id_reads_none`. round-trip에 version_id 실린 항목 포함(_doc↔_entry drift 잠금).
  - D7: `test_generate_with_position_persists_scratch`에 `version_id=="v1"` 단정 + list 키셋에 `version_id` 추가.
  - best-effort: `_ExplodingScratch`에 `clear_accepted_item` raise 추가(accept가 이제 이 메서드 호출).
- frontend: `npx vitest run` → **162 passed / 11 files**(무변). `npx tsc --noEmit` clean. `npm run gen:api` → `schema.d.ts` byte-identical(scratch endpoint `response_model` 없음).
- `git diff --check` clean. LLM 미사용.

### 독립 검증 PASS(조건 없음) + 비차단 hardening 2건 반영

- 오너가 증분 1을 독립·적대적으로 재도출(계약→구현→테스트→green bar 전부 재실행, backend 1257·frontend 162·diff 일치)해 **합격(조건 없음)** 판정을 줬다(`docs/verifications/2026-07-21/increment1_d2_d7_scratch_pad_prep.md`). §265 boundary matrix 빈 셀 없음, accept 정리 호출 지점(saved 200·502에만 per-item, DELETE에만 whole-draft, non-PASS 미진입)을 직접 확인. 동작 결함·추적 안 된 분기·누락 가드 0.
- **H-1(계약 일관성, doc-only)**: §262가 scratch를 "복구 전용"이라 하는데 §265 per-item rationale은 "비동기 결과 패드가 재사용할 기반"을 인용해 표면적 긴장이 있었다. §261 용도 확장을 증분 2로 미룬 건 투명하나, §262에 **전방 포인터 1줄**을 추가해 독자 혼동을 없앴다(규칙 모순은 아니라 non-blocking).
- **H-2(정밀도, doc-only)**: §268의 `version_id` "(없으면 None)"이 `ContextPositionBody.version_id` 필수 문자열(main.py:1283)과 표면 충돌해 보였다. HTTP generate 경로는 항상 실값을 싣고 None은 **legacy 레코드·필드 생략 직접 호출자**를 위한 seam임을 문구로 분리했다.
- 두 건 모두 코드/테스트 무변(SoT 문구만) → green bar·검증 verdict 불변. `git diff --check` clean.

### Next steps

- **증분 2(D4+D3+D5)**: Analysis식 생성 job collection(`pending/running/succeeded/failed`), worker에 생성 job 폴링·claim 루프 추가(**worker가 처음으로 LLM/gateway 호출** — 접근·타임아웃·실패 분류 신규), generate endpoint 2048/4096은 동기 실행 대신 job enqueue(1024는 동기 유지). 색인 sync outbox는 **건드리지 않는다**(검증 H3: 성격이 다른 CDC). 이때 §261 scratch 용도 문구를 "복구 + 비동기 결과 보관"으로 확장한다(§262 전방 포인터가 이미 이를 가리킨다).
- 증분 3(D6): 읽기 전용 패드 + 완료 배지 + 생성 중에만 5초 폴링(브라우저 Notification 미사용).

## Task — 비동기 생성 + 결과 패드 증분 2a: 생성 job 저장소 (D4=A 데이터층, 순수 additive)

### Goals

- 오너가 증분 2를 A(2a/2b/2c 3슬라이스)로 쪼개기로 확정. **2a = 데이터층만**: 생성 job 모델·상태 머신·저장소 경계·atomic claim. worker(2b)·endpoint(2c)의 소비 대상을 먼저 격리해 worker 최초 LLM 실행 diff를 깨끗하게 둔다.
- **다음 작업자가 이어받을 수 있게** 설계·핸드오프를 명시적으로 남긴다.

### User Decisions and Rationale

- **오너: 증분 2를 작게(A) + 다른 작업자 인계 고려**. 2a는 기존 코드를 전혀 건드리지 않는 신규 파일만이라 회귀 위험 0, 리버트 단위 명확.

### Completed work

- **신규 `writing/generation_job.py`(데이터층 코어)**: `WritingGenerationJobStatus`(pending/running/succeeded/failed) + `WritingGenerationJobFailureReason`(6종: invalid_request·invalid_report·context_budget_exceeded·context_search_failed·provider_error·provider_timeout — **generate endpoint의 except 블록에서 도출**, docstring에 예외→reason 정확 매핑을 남겨 2b가 그대로 구현), frozen `WritingGenerationJob`(generate 재현에 필요한 입력 일체 + version_id[D7 scratch 저장·패드용] 적재), `InMemoryWritingGenerationJobRepository`, `WritingGenerationJobService`(enqueue[idempotent on (project_id,request_id)]·claim_next·mark_succeeded/failed·get·list_for_draft), `_ALLOWED_TRANSITIONS`(PENDING→RUNNING / RUNNING→{SUCCEEDED,FAILED}) + `InvalidJobStateTransition`. Analysis job 선례(`analysis/models.py`·`service.py`) 미러.
- **신규 `writing/generation_job_mongo.py`(어댑터)**: `MongoWritingGenerationJobRepository`. **claim_next = `find_one_and_update` + lease**(index-sync outbox `claim_next_outbox_entry` 동형): PENDING 또는 lease 만료 RUNNING을 원자적으로 RUNNING 전이 → **동시/replica worker 이중 실행 방지**(D3=B 핵심). unique `(project_id,request_id)` 인덱스가 enqueue 중복을 backstop(add가 DuplicateKeyError swallow). claim/list 인덱스.
- **테스트 2파일**: `test_writing_generation_job.py`(22 케이스 중 서비스/InMemory: enqueue 멱등 양방향·claim oldest-first·fresh RUNNING skip[이중 실행 방지 over-strict]·stale RUNNING 재claim[크래시 복구 under-strict]·전이 양방향·금지 전이 raise·list 격리), `test_writing_generation_job_mongo.py`(fake-collection round-trip[status/failure_reason StrEnum + nullable 필드 drift 잠금]·중복 swallow·claim lease·update 영속·list). **신규 `*_mongo.py`는 fake-collection round-trip 필수** 관행 준수(선례 인용은 선례의 테스트까지 인용).

### Decisions (구현자 판단 — 2b/2c 작업자가 알아야 할 것)

- **async는 draft anchor를 요구한다**: 패드는 `(project_id, draft_id)` 키라 draft 없이는 표시할 곳이 없다 → 모델의 `draft_id`/`version_id`는 **required**(generate의 `current_position`에서 옴). **2c의 endpoint는 async 프리셋(2048/4096)에 `current_position`이 없으면 400**을 내야 한다(모델이 이미 이를 전제; `main.py` generate는 현재 positionless를 허용하므로 async 분기에서 명시 거부 필요). 이는 "패드가 per-draft"에서 강제되는 것이지 오너 결정 사안이 아니다.
- **FAILED→PENDING(재시도) 전이는 2a에서 뺐다**: D4=A는 "orphan/retry Analysis 계약 재사용"이나, 2a에 caller가 없어 dead/untested 분기가 된다. 재시도를 실제로 구동하는 public 메서드와 **함께** 추가해(재시도 UI 슬라이스) callerless 전이를 남기지 않는다. crash된 RUNNING 복구는 claim lease가 담당(전이 아님).
- **job은 resolved `max_output_tokens`를 싣는다**: 서버가 프리셋→토큰 매핑을 소유(D3=A). enqueue 시점(2c)에서 이미 `output_tokens`를 뽑으므로 그 값을 job에 넣으면 worker가 env를 다시 읽지 않아도 된다(자기완결). symbolic `output_length`도 패드/디버그용으로 함께 저장.

### 2b 착수 가이드 (다음 작업자용)

- **worker 스크립트**: `scripts/index_sync_worker.py`의 `_GracefulShutdown`·`run_loop`·SIGTERM 패턴을 그대로 미러한 **별도 스크립트 `scripts/generation_job_worker.py` + 별도 compose 서비스** 권장(실패 격리·독립 확장, 선례 일치). 색인 outbox는 **건드리지 않는다**(H3).
- **실행 루프**: `service.claim_next()` → 없으면 idle-sleep. 있으면: (1) `ContextSearchService.build_context_package`로 컨텍스트 빌드(main.py generate의 `search_request` 구성 그대로: `needs=_WRITING_CONTINUE_SCENE_NEEDS`, `query=job.query or job.instruction`, `current_position=(job.draft_id, job.version_id)`, `max_tokens=job.max_tokens`), (2) `WritingService.generate(request=WritingRequest(job.request_id, project, task_type, job.instruction, job.draft_excerpt), package, max_output_tokens=job.max_output_tokens)`, (3) 결과를 `WritingScratchService.save(project_id, job.draft_id, job.request_id, candidate.task_type.value, candidate.output_type.value, job.instruction, candidate.text, version_id=job.version_id)`, (4) `service.mark_succeeded(job, result_scratch_id=scratch.id)`. 예외는 `generation_job.py` docstring의 매핑대로 `mark_failed(reason, detail)`.
- **worker의 gateway 접근**: `main.py`의 `_default_writing_service()`·context search 팩토리(env로 gateway/embedding 구성)를 worker 조립에 재사용. 이게 **worker 최초 LLM/gateway 호출**이라 타임아웃·ProviderError 분류가 신규 표면.
- **§261 SoT 개정은 2b에서**: worker가 결과를 실제로 scratch에 쓰는 시점 → scratch 용도를 "복구 전용" → "복구 + 비동기 생성 결과 보관"으로 확장(§262 전방 포인터가 이미 가리킴). 버전 bump.
- **★ 2b가 반드시 다뤄야 할 리스크(2a 독립 검증 H-2/H-3, `verifications/2026-07-21/increment2a_d4_generation_job_store.md`)**:
  - **H-2 catch-all failure reason**: 현 taxonomy 6종은 generate의 **매핑된** 예외만 커버한다. worker 루프가 unmapped infra 오류(pymongo/httpx)나 버그를 만나면 분류할 reason이 없어 job이 terminal에 못 가고 **RUNNING→lease 재claim→재실패 livelock**에 빠진다. 2b에서 catch-all reason(예: `UNKNOWN`/`INTERNAL`을 enum에 추가)이나 최외곽 `mark_failed` fallback을 반드시 넣는다(이때 caller가 생기므로 dead 분기 아님). `generation_job.py` `WritingGenerationJobFailureReason` docstring에 같은 NOTE를 인접 배치했다.
  - **H-3 reclaim 재실행 idempotency**: crash한 worker가 scratch 부분 기록 후 죽으면 lease 재claim 시 generate가 재실행돼 scratch 항목이 중복 생길 수 있다(상한 20이 결국 수렴시키나 인지 필요). 2b에서 결과 write를 job 기준 멱등(예: `result_scratch_id`가 이미 있으면 skip, 또는 job.id로 scratch 항목 upsert)으로 설계할지 결정한다.
  - **H-1(반영 완료)**: taxonomy docstring의 provenance를 정정했다 — generate endpoint는 ProviderError를 항상 502로 매핑(타임아웃 분리 없음)하므로 "(504)" HTTP 괄호를 제거하고, timeout 분리는 writing endpoint 관행(`accept`의 `ProviderErrorCode.TIMEOUT`)을 따르며 worker는 HTTP status가 아니라 job reason으로 분류함을 명시했다.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1279 passed / 73 skipped / 326 subtests**(1257 + 신규 22). 기존 코드 무변이라 회귀 위험 0(신규 파일 2 + 테스트 2뿐).
- frontend/gen:api 무변(endpoint 미배선). `git diff --check` clean. LLM 미사용.

### Next steps

- **증분 2b(D3)**: 위 "2b 착수 가이드"대로 worker 실행 루프 + §261 개정. seeded pending job으로 테스트(endpoint 불필요). 배포 후에도 endpoint가 아직 sync라 async 경로는 dormant(2c까지).
- **증분 2c(D5)**: generate endpoint 2048/4096 → job enqueue(pending 반환, 블록 안 함)·1024 동기 유지; async 프리셋 + no `current_position` → 400; `GET .../generation-jobs/{id}` 상태 read(증분 3 폴링용). 이 flip이 async end-to-end 개통.

## Task — 비동기 생성 + 결과 패드 증분 2b: 생성 worker 실행 루프 (D3=B, SoT v1.7.26)

### Goals

- 2a 저장소에 이어, worker가 job을 claim해 **실제로 실행**하는 조각. **worker 최초 LLM/gateway 호출**이라 가장 위험. 2a 검증 hardening H-2(catch-all)·H-3(reclaim 멱등)을 설계에 반영.

### User Decisions and Rationale

- 오너 확정 결정(D3=B)의 구현 + "다른 작업자 인계 고려" 지시. 새 오너 결정 없음. 오너가 외부 LLM(192.168.1.22:9080) 접근 가능함을 알려 라이브 스모크 경로를 열었다.

### Completed work

- **`writing/generation_worker.py`(테스트 가능한 실행 코어)**: `execute_generation_job(job, collaborators)` async — 동기 generate와 같은 파이프라인(ContextSearch build → WritingService.generate)을 돌리고 결과를 `scratch.save(version_id=job.version_id)` 후 `jobs.mark_succeeded(result_scratch_id=)`. 예외는 taxonomy대로 `mark_failed`. `GenerationCollaborators` frozen dataclass(context_search·writing·scratch·jobs·needs). CLI/loop와 분리해 fake provider로 단위 테스트(no Mongo/gateway/daemon).
- **H-2 catch-all**: `WritingGenerationJobFailureReason`에 `INTERNAL` 추가 + executor 최외곽 `except Exception → mark_failed(INTERNAL)`. 이제 caller가 생겼으므로 dead 분기 아님(2a에서 미리 안 넣은 이유가 여기서 해소). 매핑 안 된 infra/버그도 종료 상태 → RUNNING livelock 방지.
- **H-3 reclaim 멱등**: 성공 저장 직전 `scratch.clear_accepted_item(project, draft, request_id)`로 이전 (crash) 시도의 scratch를 지우고 다시 써, reclaim 재실행에도 draft당 job 결과가 정확히 1건. 2a의 per-request delete 재사용.
- **`scripts/generation_job_worker.py`(CLI/daemon)**: `index_sync_worker.py`의 `_GracefulShutdown`·`run_loop`·SIGTERM·JSON 이벤트 패턴 미러. async per-job 실행(`asyncio.run(execute_generation_job)` per pass). claim 없으면 interval idle-sleep, 있으면 즉시 다음 pass. `--loop`/one-shot. gateway 미구성이면 exit 2. 주입 seam(build_fn·run_pass_fn·stop·sleep_fn·stdout)으로 결정적 테스트.
- **`main.build_async_generation_collaborators()`**: create_app과 같은 env 팩토리 재사용(core_sot·memory·analysis·embeddings·vector_index·context_search·writing·scratch·job) → worker는 이 한 seam만 import. `_default_writing_generation_job_service()`(scratch 팩토리 동형, Mongo/in-memory env 게이팅, claim lease env `WRITING_GENERATION_CLAIM_TIMEOUT_SECONDS` 기본 600). create_app 무변(순수 additive 함수).
- **compose `generation_worker` 서비스**: `worker`(색인) 옆에 신설. application과 같은 gateway+context env(색인 outbox와 무관, 브리프 H3). `stop_grace_period: 180s`(SIGTERM이 in-flight generate를 끝내도록, gateway timeout 120s 초과). command `python scripts/generation_job_worker.py --loop`.
- **SoT v1.7.26**: §261 (2) 비동기 결과 보관 용도 확장(증분 1에서 지연했던 유일한 개정 — worker가 결과를 실제로 scratch에 append하는 시점) + 신규 `writing_generation_jobs`/worker 계약 clause(claim 원자성·lease·상태·taxonomy 6+catch-all·H-2/H-3 멱등). **endpoint 배선(D5)은 2c**라 현재 async 경로 dormant임을 명시.

### Decisions (구현자 판단)

- **endpoint enqueue/400/sync-split(D5)은 SoT에 "2c" forward로 표기**: 2b 후 저장소·worker는 갖췄으나 생산자(endpoint)가 없어 production async 경로는 dormant. 지금 endpoint 동작을 현재형으로 쓰면 SoT가 없는 동작을 서술한다(증분 1 §261 지연과 같은 원칙). §261 (2)도 "worker append(2b) / 패드 read(증분 3)"로 단계 분리.
- **context search live는 2b 새 리스크 아님**: 파이프라인의 context 빌드 부분은 Phase 4 deployed e2e에서 이미 라이브 검증됨(HANDOFF). 2b의 새 표면은 worker가 gateway로 generate를 호출하고 결과를 scratch에 쓰는 wiring이다.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1295 passed / 73 skipped / 326 subtests**(신규 16: `test_writing_generation_worker.py` executor 성공·실패 매핑 7종·catch-all INTERNAL·H-3 멱등 / `test_generation_job_worker.py` run_pass·loop drain/idle-sleep·gateway 게이팅·one-shot). `docker compose config` OK(generation_worker 유효). frontend·gen:api 무변(endpoint 미배선). `git diff --check` clean.
- **실 12B 라이브 스모크 PASS**: 외부 llama(192.168.1.22:9080) 관통. gateway를 `LLAMA_BASE_URL=http://192.168.1.22:9080 GATEWAY_PORT=8011 docker compose up -d --no-deps gateway`로 띄우고(`/health/ready`=ready), **실제 `execute_generation_job`을 gateway-backed `WritingService`(_default_writing_service, `LLM_GATEWAY_BASE_URL=http://localhost:8011`)로 실행**. job(medium/2048) enqueue→claim→execute 결과: job `succeeded`, scratch 1건, `version_id="v-live"` 보존, 실 12B가 생성한 자연스러운 한국어 산문 166자("그녀는 가느다란 손가락을 뻗어 차갑게 식은 성문의 쇠손잡이를…"). worker의 **최초 gateway generate 호출 + 결과→scratch 배선 + mark_succeeded**가 실 12B에서 관통 확인. context search는 stub(빈 package) — 2b의 새 리스크는 gateway generate 호출이고 context 빌드는 Phase 4 deployed e2e에서 이미 라이브 검증됨. 실패 taxonomy 매핑은 결정적 라이브 유발이 어려워 fake 단위 테스트로 잠금(7종+catch-all). **완전 스택 e2e(실 context search + Mongo + compose `generation_worker` 서비스, endpoint 배선 2c 후)는 오너 풀스택 후속**. 스모크 스크립트는 scratchpad(throwaway, context stub이라 커밋 안 함).

### Next steps

- **증분 2c(D5)**: generate endpoint 2048/4096 → job enqueue(pending 반환)·1024 동기 유지·async+no current_position=400·`GET .../generation-jobs/{id}` 상태 read. 이 flip이 async 개통(2b worker가 처리).
- 증분 3(D6): 읽기 전용 패드 + 완료 배지 + 생성 중에만 5초 폴링.

## Task — 비동기 패드 증분 2b 독립 검증 후 hardening + 문서 완성 (H-1(2b) catch-all persist 커버리지)

### Goals

- 증분 2b(커밋 9f012fe) 독립 검증(`docs/verifications/2026-07-21/increment2b_d3_generation_worker.md`)에서 건넨 비차단 hardening H-1(2b)을 적용하고, 작업 AI가 핸드오프 작성 중 지쳐 빠뜨린 CHANGELOG(v1.7.25·v1.7.26)을 채운다.

### Completed work

- **H-1(2b) catch-all persist 커버리지 확장**: `execute_generation_job`의 result-persist 단계(`scratch.clear_accepted_item` + `scratch.save`)를 try 블록 안으로 옮겨, 최외곽 `except Exception → INTERNAL` catch-all이 generate 단계뿐 아니라 **저장 단계까지 덮도록** 했다(`generation_worker.py`). 근거: H-2 catch-all이 이미 "fault→terminal"로 색인 worker의 crash-reclaim에서 출발했는데 generate만 덮고 scratch 저장은 안 덮는 게 비일관적. generate 성공 후 scratch 장애 시 이제 INTERNAL로 종료되어 (a) worker 루프 crash, (b) 600s lease 만료 후 비싼 generate를 재실행하는 reclaim 루프, 둘 다 막는다. H-2 docstring("never livelock")이 execute 전체에 참이 됨. trade-off(scratch blip에 성공 생성 상실)는 드문 edge이고 무한 LLM 루프보다 낫다 — H-3가 결과 중복은 여전히 막는다. `mark_succeeded` 자체는 try 밖에 둬(종료 write; jobstore down이면 mark_failed도 실패해 어차피 crash—불가피).
- **회귀 추가**: `test_persist_failure_terminates_job_not_crash`(`test_writing_generation_worker.py`) — `_RaisingScratch`로 save 실패 시 FAILED/INTERNAL 종료를 잠금(under-strict: persist가 try 밖이면 re-raise로 실패).
- **CHANGELOG backfill**: v1.7.24에서 멈춘 CHANGELOG에 v1.7.25(증분 1, D2=A/D7)·v1.7.26(증분 2b, D3=B) 행 추가 — 작업 AI가 SoT는 올렸으나 CHANGELOG를 못 채운 결손 마감.
- **검증 기록 후속**: `increment2b_d3_generation_worker.md`의 Outstanding items 업데이트(라이브 스모크는 5b6ba87에서 이미 PASS, H-1(2b)은 이번에 적용).

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1296 passed / 73 skipped / 326 subtests**(1295 + H-1(2b) 회귀 1). 집중 `test_writing_generation_worker.py`·`test_generation_job_worker.py` → 17 passed. `git diff --check` clean. LLM 미사용.

### Next steps

- 증분 2c(D5): generate endpoint 2048/4096 → job enqueue·1024 동기·async+no current_position=400·`GET .../generation-jobs/{id}` 상태 read.

## Task — 비동기 생성 + 결과 패드 증분 2c: generate endpoint 동기/비동기 분기 (D5=A, SoT v1.7.27)

### Goals

- 2b의 저장소·worker에 이어 **생산자(endpoint)를 배선**해 async 경로를 end-to-end로 개통한다.
- `POST .../writing/generate`를 `output_length`로 분기: `short`(1024)=동기, `medium`(2048)/`long`(4096)=job enqueue 후 비블로킹 반환.
- async 프리셋 + `current_position` 없음 → 400. `GET .../generation-jobs/{job_id}` 상태 read(증분 3 폴링용) 추가.
- 프론트가 async 응답을 인식해 candidate/Gate/루프를 건너뛰고 "백그라운드 생성 시작" notice만 표시(패드·5초 폴링은 증분 3).

### Completed work

- **응답 모델(`writing/http_models.py`)**: `WritingGenerationJobPayload`(12 필드: job_id·request_id·project_id·draft_id·version_id·task_type·output_length·status·created_at·result_scratch_id·failure_reason·failure_detail — AnalysisJobPayload 선례 동형 status/failure_reason 평문 str) + `WritingGenerationJobAcceptedPayload`(`{job, idempotent_replay}`, Analysis create envelope 동형) + `GENERATE_ASYNC_RESPONSES={202: …}`. GET은 `response_model=WritingGenerationJobPayload`(성공 경로 exact-width), 202 envelope는 `responses={}` 문서 전용(JSONResponse가 검증 우회, exact-key 회귀가 runtime lock — 기존 partial envelope 패턴 동형).
- **generate endpoint 분기(`main.py`)**: output_length 해석 후 `medium`/`long`이면 `current_position` 필수(else 400) → `writing_generation_jobs.enqueue(...)` → `JSONResponse(202, {job, idempotent_replay})` 즉시 반환. **endpoint는 async 분기에서 writing/context_search/scratch를 부르지 않고**(전부 worker 역할) 동기 전용 503 검사도 우회한다(async는 endpoint에서 둘 다 불필요). `short` 동기 경로 무변. 라우트에 `responses=GENERATE_ASYNC_RESPONSES` 추가.
- **GET 상태 read**: `GET /projects/{project_id}/writing/generation-jobs/{job_id}`(`response_model=WritingGenerationJobPayload`, 404 if 미발견·타 프로젝트). `_writing_generation_job_payload(job)` 헬퍼(GET + 202 중첩共用).
- **create_app**: `writing_generation_job_service` 파라미터 + `writing_generation_jobs` 해석(scratch 팩토리 동형, Mongo/in-memory env 게이팅). `build_async_generation_collaborators`(2b)와 같은 `_default_writing_generation_job_service()` — production Mongo로 양측 공유.
- **SoT v1.7.27**: 버전 bump + changelog 행. §271 endpoint 배선 forward-marker를 현재형으로 전환(202 + envelope + GET path + 400 + 동기/비동기 분기 + 503 우회 명시). §270 라벨에 v1.7.27/2c 추가. §508 "status는 항상 candidate"를 **동기 후보 응답 한정**으로 정밀화(비동기는 candidate가 아닌 job).
- **frontend**: `client.ts`에 `WritingGenerationJob`/`WritingGenerationJobAccepted` 타입 + `generateWriting` 반환을 `WritingCandidate | WritingGenerationJobAccepted`로 widen. `WritingPanel.runGenerate`가 `"job" in produced` 가드로 async를 감지해 "백그라운드 생성을 시작했습니다. 완료되면 결과 패드에 표시됩니다." notice + early return(candidate/Gate/루프 건너뜀). long이 async가 되어 죽은 long-skip 루프 분기 제거(제 변경이 만든 orphan). `gen:api`로 `schema.d.ts`에 신규 2 스키마 + generate 202 응답 additive.

### User Decisions and Rationale

- 이 슬라이스는 오너 확정 결정(D5=A)의 구현이며 새 오너 결정은 없다. 아래 상태코드 202는 구현자 판단.

### Decisions (구현자 판단)

- **상태코드 202(200 아님)**: async 분기 응답을 200+JSONResponse로 주면 `response_model=WritingCandidatePayload`(200) 선언이 거짓이 된다(runtime은 우회하지만 OpenAPI가 async 본문을 반영 못 함). 200+Union oneOf는 선례 없고 codegen을 복잡하게 한다. **202**면 200=candidate 정직성을 유지하면서 async envelope를 `responses={202}`로 문서화한다 — 이 코드베이스의 유일한 분기 응답 메커니즘(revise-and-gate/accept의 `responses={}`)과 동형이며 HTTP 의미론(202 Accepted=백그라운드 처리 수락)에 정확히 부합. Analysis create가 200을 쓰는 것은 response_model 자체가 없어(untyped plain dict) 정직성 충돌이 없기 때문이고, writing generate는 v1.7.1에서 타입화됐으므로 상황이 다르다.
- **endpoint는 async에서 writing/context_search/scratch를 부르지 않는다**: worker가 전부 담당(2b). 따라서 동기 전용 503 검사도 async에서 우회한다(worker는 자체 gateway/context config를 갖는다 — endpoint의 writing=None이 worker gateway 부재를 의미하지 않는다).
- **패드·폴링은 증분 3**: 2c는 endpoint 분기 + GET 상태 read + 프론트 최소 인식(notice)까지만. medium/long 결과 표시(패드)·5초 폴링은 증분 3이 담당한다. 2c와 3 사이에 medium/long 결과를 볼 UI가 일시적으로 없으나, 증분 분할 설계상 허용.

### Verification

- **독립 adversarial self-verification 워크플로 6 dimensional**(spec↔code·boundary-matrix·양방향 가드·envelope-key·SoT 일관성·worker 호환): 5 PASS + 1 CONDITIONAL_PASS(spec↔code). **blocking 1건 폐쇄** + 비차단 load-bearing 보강 반영 후 PASS.
- **blocking(폐쇄)**: SoT §272 "async는 동기 전용 503 검사도 우회" clause에 회귀 부재 — verifier가 mutation(503 guard를 async 분기 위로)으로 suite가 green임을 입증. `test_async_bypasses_sync_only_503_checks`(provider=None + with_context=False + medium → 202)로 잠갔고, **동일 mutation으로 이 test가 `503 != 202`로 re-fail함을 직접 확인**(양방향 가드 원칙).
- **비차단 보강 반영**: (1) medium 테스트에 `context.last_request is None` 추가(async가 context_search를 부르지 않는 third invariant 명시), (2) `test_async_idempotency_key_is_project_plus_request`(다른 request_id → distinct job, 둘 다 `idempotent_replay=false` — 멱등키가 `(project_id, request_id)`임을 over-strict로 lock), (3) v1.7.27 changelog 행의 깨진 §NNN locator 제거(verifier 지적 — §NNN은 비공식이라 descriptive text로 대체).
- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1312 passed / 73 skipped / 325 subtests**(1296 + 신규 16: async 분기 14[medium/long/short-sync/no-position-400/short-no-position-200/idempotent/idempotency-key/503-bypass/no-scratch-write/GET 200/GET 404 unknown/GET 404 nonexistent-project/GET 404 wrong-project/terminal fields] + envelope-key 2; 단, 기존 preset 테스트 2건을 2c 동기/비동기에 맞게 재작성해 증분은 +2). frontend: `npx vitest run` → **163 passed / 11 files**(신규 1 net: medium async·long async·short-stays-sync over-strict — 기존 2건 재작성). `npx tsc --noEmit` clean. `npm run build` 101 modules(JS 394.75 kB). `npm run gen:api` 신규 2 스키마 + 202 응답 additive. `git diff --check` clean. LLM 미사용(단위).

### Next steps

- 증분 3(D6): 읽기 전용 패드 + 완료 배지 + 생성 중에만 5초 폴링. `GET .../generation-jobs/{job_id}`로 종료 감지 → scratch 재조회로 결과 표시. 브라우저 Notification 미사용.
- verifier 비차단 hardening 후보(필요시 증분 3에서): long-preset per-preset assertion 강화·terminal-state full-envelope·`extra='forbid'`·worker Mongo-미설정 startup warn·producer→worker end-to-end 통합 테스트.

## Task — 증분 2c 오너 독립 검증 PASS 후 보강 + 커밋

### User Decisions and Rationale

- 오너가 증분 2c를 독립·대항(adversarial) 검증해 **PASS(조건 없음, blocking 없음)** 판정을 줬다(`docs/verifications/2026-07-21/increment2c_d5_generate_endpoint_async_branch.md`). 정본→코드→테스트→schema 전 스택 추적 + 4종 mutation(백업→변형→re-fail→`diff -q` 원복)으로 작업자 주장을 refute했다. boundary matrix 18 cell 빈 곳 없음, 카운트 재실행 확정(backend 1311·frontend 163·tsc exit 0).
- **오너 결정 — 상태코드 202 유지**: 작업자가 "구현자 판단"으로 202를 선택하고 오너 확인을 요청한 항목에 대해, 오너가 검증 근거(response_model 정직성 + `responses={}` 선례 동형 + HTTP 의미론; Analysis create가 200인 것은 response_model 자체가 없어 상황이 다름)를 수용해 **202 유지**를 확정했다. 200을 원하면 `main.py` status_code + `GENERATE_ASYNC_RESPONSES` 키만 국소 변경이나, 오너는 202를 추천했다. → 코드 무변.

### Completed work

- **비차단 hardening #1(SoT 수치 정정, 오너 명시)**: v1.7.27 changelog 행(`system-contract-sot.md:36`)만 "backend 1309 passed" + "async 분기 11"이라고 쓰고 있었고(work_log/HANDOFF/요약은 1311·13). SoT가 정본이므로 수치를 정정했다. 단, 이 보강에서 GET 존재-불가 project 404 테스트 1건을 추가(아래)해 backend가 1311→**1312**, async 분기 13→**14**, 신규 15→**16**로 확정됐으므로, SoT·HANDOFF·본 work_log 모두 **1312/14/16**으로 일치시켰다(1296 baseline + 16 net-new = 14 async-branch-class + 2 envelope-key).
- **비차단 hardening #3(GET 존재-불가 project 404 잠금)**: 검증 기록이 GET endpoint의 `_require_project_exists` 404 경로(존재 않는 project path)가 테스트에 잠기지 않았다고 지적(unknown job_id·타 프로젝트 job만 cover). `test_get_generation_job_404_nonexistent_project`(`/projects/ghost/writing/generation-jobs/wgj:any` → 404)을 추가해 GET-404 매트릭스 3 arms(존재-불가 project·unknown job·타 프로젝트 job)을 완전히 잠갔다. 코드는 계약대로 동작하므로 비차단이나, "404 미발견" arm의 인접 케이스를 명시 단정.
- **검증 기록 Outstanding items 갱신**: 202 확정(Outstanding #1 해소)·수치 정정(#3 해소)·존재-불가 project 404 잠금(record hardening #3 해소) 반영.

### 조치 불요 (검증자 판단·오너 수용)

- **record hardening #2(producer→worker end-to-end 통합 테스트)**: 비차단, 증분 3(패드/폴링)에서 추가 시 유효 — 양 절반(2b worker 실행·2c endpoint enqueue)은 독립 입증됐고 seam은 공유 service로 자명. 증분 3으로 지연.
- **record hardening #4(`extra='forbid'` 미설정)**: 비차단, `WritingGenerationJobEnvelopeKeyTest`가 `set(body)==_JOB_KEYS`로 정확한 키 집합을 pin해 extra key 시 bite. 기존 partial envelope 패턴도 default ignore라 선례 일치. 코드 무변.

### Verification

- backend: **1312 passed / 73 skipped / 325 subtests**(1311 + 존재-불가 project 404 회귀 1). frontend·tsc·build·gen:api는 backend-only 테스트 + 문서 수치 정정이라 무변(163/11, tsc clean, build 101 modules). `git diff --check` clean.

### Next steps

- 커밋 후 증분 3(읽기 전용 패드 + 완료 배지 + 생성 중 5초 폴링). 위 지연된 비차단 hardening(e2e 통합 테스트·`extra='forbid'` 등)은 증분 3에서 재검토.
