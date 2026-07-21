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
