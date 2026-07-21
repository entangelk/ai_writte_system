# 검증 레코드 — 문체/분량 슬라이스 증분 2: 생성 분량 프리셋 (D3=A, SoT v1.7.22)

## Subject metadata

- **날짜**: 2026-07-21
- **요청자**: 오너 (구현 AI가 완료한 증분 2를 "검증하고 의심하고 또 의심해줄래"로 독립 감사 요청)
- **검증자**: 독립 검증 AI (구현과 무관)
- **대상 슬라이스/산물**: 문체/분량 슬라이스 증분 2 — `output_length` 생성 분량 프리셋 (D3=A). `services/application/app/writing/models.py`·`main.py`·`service.py`, `tests/test_writing.py::WritingOutputLengthPresetTest`, `frontend/src/writing/WritingPanel.tsx`·`.test.tsx`, `frontend/src/api/schema.d.ts`, SoT v1.7.22.
- **정본 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.22 — 버전로그(36행), Phase 5 "생성 분량 프리셋" clause(502행)
  - `docs/plans/writing-style-and-length-control-decisions.md` — D3=A + "Owner decisions" D3행(매핑 1024/2048/4096, long 단일 generate 전용 제약)
- **작업 소스**: commit `296c612` 위 **working tree, uncommitted** (`git status`로 11개 파일 modified + `docs/daily_logs/2026-07-21/` untracked). 구현은 커밋되지 않은 작업 트리 상태.

## Scope

독립 감사가 채운 계약 표면(스코프는 SoT v1.7.22 버전로그 + Phase 5 clause + 브리프 D3가 교차참조하는 체인으로 한정; 관련 없는 Phase 4/6 룰은 제외):

1. **정본 계약(SoT/브리프)** — v1.7.22 버전로그 ↔ Phase 5 clause ↔ 브리프 D3 간 literal 일치 및 자기모순.
2. **구현 코드(backend)** — `OutputLength` enum, `_writing_output_length_tokens()` 매핑+fail-loud, `WritingGenerateRequest.output_length`, generate 엔드포인트 preset 해석(400/override), `WritingService.generate(max_output_tokens=)` override, `create_app` 진입부 기동 검증, `WritingReviseRequest`에 필드 부재.
3. **구현 코드(frontend)** — `outputLength` state 기본 short, generate body에 `output_length`, `long`일 때 자동 revise/gate 루프 스킵 + notice, select 라벨.
4. **회귀 테스트** — `WritingOutputLengthPresetTest` 8건 + frontend WritingPanel +2(및 기존 exact-match 갱신 1건). 각 assertion이 계약을 pin 하는지, under/over-strict guard, 경계값 커버, public surface 타겟.
5. **공개 envelope/schema** — `schema.d.ts`의 `output_length` additive(1필드)와 gen:api 바이트 동일성.
6. **전체 스위트 정량** — backend 1237/73/320, frontend 161/11 재현.
7. **빌드/정적 검증** — `tsc --noEmit`, `git diff --check`.

## Methodology

각 표면의 검증 방법과 **정확한 명령**. 이 절에서 재현 불가한 것은 검증된 게 아니다.

1. **계약 스코프 먼저, 코드 나중**: SoT v1.7.22 버전로그(36행)와 Phase 5 clause(502행)를 먼저 end-to-end로 읽어 boundary matrix(lock list)를 도출한 뒤 브리프 D3의 Owner decisions행과 literal을 교차 비교. 코드를 먼저 열지 않았다.
2. **정본 자기모순 점검**: 버전로그 ↔ Phase 5 clause ↔ 브리프 D3 사이의 모든 literal(enum값, 매핑 1024/2048/4096, env 이름, 400, 기동 실패, long 단일 generate, loop 예산 무변)을 표로 대조. 추가로 `grep -rn "서버 전역 고정\|전역 고정\|WRITING_GENERATE_MAX_TOKENS" docs/system-contract-sot.md docs/plans/05-writing-ai.md docs/plans/05-writing-generation-decisions.md`로 stale 단일값 주장 잔존 여부 확인.
3. **구현 적대적 감사**: `Read`로 `_env_int`(478행)·`_writing_output_length_tokens`(978행)·`_project_brief_style_example_limits`(960행, 증분 1 선례)·요청 모델 5종(1313~1399행)·create_app 진입부(1421~1424행)·generate 엔드포인트(3053~3127행)·`WritingService.generate`(service.py 79~128행)를 읽고, boundary matrix 각 cell이 코드에 그대로 있는지 추적. `grep -rn "\.generate(" services/application/app/`로 `writing.generate()` 호출처가 generate 엔드포인트 단一处인지(루프가 generate가 아닌 revise를 쓰는지) 확인.
4. **테스트 코드 감사(audit subject)**: `WritingOutputLengthPresetTest`(test_writing.py 478~582행) 8개 test를 전부 읽고 각각 (a) assertion이 계약을 pin 하는지 (b) under-strict (c) over-strict (d) 경계값 커버 (e) public surface 타겟 — 5항을 판정. mutation은 구현 주장(work_log)을 신뢰하지 않고 테스트 본문에서 bite 시나리오를 직접 도출.
5. **실제 실행**:
   - backend 신규 클래스: `python3 -m pytest tests/test_writing.py::WritingOutputLengthPresetTest -v -p no:cacheprovider`
   - backend 전체(정량 재현): `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
   - frontend 전체: `cd frontend && npx vitest run`
   - tsc: `cd frontend && npx tsc --noEmit`
   - gen:api 바이트 동일: `cd frontend && npm run gen:api` 후 `git diff --stat src/api/schema.d.ts`로 추가 diff가 0인지(재생성이 working tree와 동일한지) 확인.
   - whitespace: `git diff --check`
6. **smoke vs envelope**: work_log의 정량 주장(1237/73/320, 161/11, gen:api 1필드)을 직접 재실행한 숫자와 1:1 비교.

## Findings

### 1. 정본 계약 — literal 일치·자기모순 점검

세 계약 위치의 모든 load-bearing literal을 대조:

| literal | 버전로그(36행) | Phase 5 clause(502행) | 브리프 D3(Owner decisions) | 코드 |
|---|---|---|---|---|
| enum값 | short\|medium\|long | short\|medium\|long | (테이블에 암시) | models.py:43-45 |
| 매핑 기본 | 1024/2048/4096 | 1024/2048/4096 | 1024/2048/4096 | main.py:987/989/990 |
| env 이름 | `WRITING_OUTPUT_LENGTH_SHORT\|MEDIUM\|LONG` | 동일 | (명시 않음, Follow-up "env 조정 가능") | main.py:986/989/990 |
| 생략 → short(하위호환) | 명시 | 명시 | 명시 | main.py:1326 default |
| 알수없는값 → 400 | 명시 | 명시 | (A 추천, 코드 400) | main.py:3069-3075 |
| short 미설정→`WRITING_GENERATE_MAX_TOKENS` 승계 | 명시 | 명시 | (명시 않음, 구현 판단) | main.py:985-987 |
| env 1미만 기동실패 | 명시 | 명시 | (Follow-up "env 조정") | main.py:992-997 + 1424 |
| long 단일 generate 전용(revise-and-gate 필드 아님) | 명시 | 명시 | 명시(⚠ 구현 제약) | WritingReviseRequest에 부재(1359-1370) |
| loop 예산 10000tok/60000ms 무변 | 명시 | 명시 | 명시 | diff에 WRITING_LOOP_MAX_* 변경 0 |
| output_length ≠ max_tokens(입력 예산, 5 endpoint 공유) | 명시 | 명시 | 명시(D3 주의) | main.py:3076 vs 3099 |

- **자기모순 없음**: 세 위치가 모든 literal에서 일치. env 이름·short 승계는 브리프가 명시하지 않으나 Follow-up "env 조정 가능"과 증분 1 선례에 일관되게 부합해 모순이 아니다(구현 판단으로 계약 내에서 화해됨).
- **stale 단일값 주장 잔존(비차단)**: `05-writing-ai.md:81`이 "writing_generate 1/120s/1024"를 output budget으로 기록. 이는 **agent-loop(dormant tool-call branch) budget profile**로 output_length(HTTP 출력 토큰 축)과 다른 표면이나, 미래 독자가 둘을 혼동할 수 있다. SoT(정본)는 정확히 갱신됐고 plan doc은 역사 산물이라 차단 아니다(Hardening #3).

### 2. 구현 코드(backend) — boundary matrix의 모든 cell이 코드에 존재

- **`OutputLength` StrEnum**(`models.py:37-45`): `SHORT/MEDIUM/LONG = short/medium/long`. 심볼릭 프리셋, 매핑은 서버 소유라는 주석으로 D3 근거 명시. ✓
- **`_writing_output_length_tokens()`**(`main.py:978-997`): 기본 1024/2048/4096, env 조정, `< 1`이면 `ValueError`. 증분 1 `_project_brief_style_example_limits()`(960행)와 **동형**. `short`는 `_env_int("WRITING_OUTPUT_LENGTH_SHORT", _env_int("WRITING_GENERATE_MAX_TOKENS", 1024))`로 **중첩 fallback** — `WRITING_OUTPUT_LENGTH_SHORT` 미설정 시 `WRITING_GENERATE_MAX_TOKENS` 승계. ✓
- **fail-loud 경로**: `create_app` 진입부(1422-1424행)에서 `_project_brief_style_example_limits()` 옆에 `_writing_output_length_tokens()` 호출. raise가 app 생성을 중단 → 기동 실패. `_env_int`(478행)는 비정수 입력에 `int(raw)` → `ValueError`로 자연 거부. 둘 다 `create_app`에서 잡히지 않아 전파. ✓
- **`WritingGenerateRequest.output_length`**(`main.py:1326`): `output_length: str = OutputLength.SHORT.value`. 생략 → "short". wire상 `str`이나 엔드포인트에서 enum 검증(`task_type`과 동형). ✓
- **generate 엔드포인트**(`main.py:3067-3076`): `OutputLength(body.output_length)` 시도 → `ValueError`는 **400**(`detail="unsupported output_length: ..."`). 매핑 dict에서 토큰 추출해 `writing.generate(..., max_output_tokens=output_tokens)`(3112행)로 전달. **400 분기가 provider/service 호출(3077행 `if writing is None` 이후)보다 선행** → 알수없는 프리셋은 모델 미도달. ✓
- **축 독립**: `output_tokens`(출력, 3076행→service max_output_tokens)과 `ContextBudget(max_tokens=body.max_tokens)`(입력, 3099행)은 별개 객체. 한 축을 움직여도 다른 축 불변(코드 구조로 보장). ✓
- **`WritingService.generate` override**(`service.py:84,103-106`): `max_output_tokens: int | None = None`; None이면 `self._max_tokens`(생성 시점 기본 1024), 아니면 override. 직접 호출자/테스트는 None 전달로 무변. ✓
- **`writing.generate()` 호출처 단처**: `grep`으로 HTTP layer에서 유일한 호출처는 generate 엔드포인트(`main.py:3103`). `gate_live_diag.py:62`는 diagnostic wrapper(운영 도구, 루프 아님). revise-and-gate 루프는 `WritingRevisionService.revise`를 쓰며 `WritingReviseRequest`에 `output_length`가 없어 **구조적으로 4096이 루프에 진입 불가**. ✓
- **요청 모델 5종 대조**: `WritingGateRequest`(1329)·`WritingReportRequest`(1340)·`WritingReviseRequest`(1359)·`WritingAcceptRequest`(1384) 어느 것도 `output_length` 없음. 오직 `WritingGenerateRequest`(1326)만 보유 → generate-only knob 만족. ✓

### 3. 구현 코드(frontend) — 계약 의도의 표현적 구현

- **state 기본 short**(`WritingPanel.tsx:204-208`): `useState<"short"|"medium"|"long">("short")`. ✓
- **generate body 전송**(273행 부근 diff): `output_length: outputLength` 추가. 기존 exact-match 회귀(253행 `output_length: "short"` 기대값 추가)로 갱신 — 새 필드 추가에 따른 올바른 갱신. ✓
- **`long` 루프 스킵 + notice**(293-301행 diff): `if (finding !== null && outputLength === "long")` → notice 세팅, `else if (finding !== null)` → `executeLoop`. `long`일 때 적격 finding이어도 루프 미진행, "긴 분량(전체 작성)은 자동 개선을 실행하지 않습니다..." notice. ✓
- **select 라벨**(502-516행 diff): "짧은 수정 / 중간부터 이어쓰기 / 전체 작성 (자동 개선 없음)" — 브리프 D3 매핑표의 의미 라벨과 동일. ✓

### 4. 회귀 테스트 — audit subject (boundary matrix → named test 매핑)

`WritingOutputLengthPresetTest` 8건을 boundary matrix cell에 매핑(모든 cell 채워짐, 빈 cell 없음):

| cell (계약 분기) | named test | under-strict | over-strict | 비고 |
|---|---|---|---|---|
| 생략 → short → 1024 | `test_default_preset_is_short_1024` | provider `last_request.max_tokens==1024` | — | backward-compat |
| short/medium/long → 1024/2048/4096 | `test_presets_map_to_confirmed_tokens` | 3 subtest 전부 | — | medium/long이 매핑 제거 시 1024로 떨어져 bite |
| 알수없는값 → 400 | `test_unknown_preset_is_400_and_never_reaches_model` | status==400 | `provider.last_request is None`(모델 미도달) | 양방향 |
| output_length ≠ max_tokens | `test_preset_is_independent_of_input_max_tokens` | output==4096 | input budget==512 | 양방향(두 축 각각 단언) |
| env override 재매핑 | `test_env_override_remaps_preset` | MEDIUM==3000 | — | 함수 직접 |
| short → WRITING_GENERATE_MAX_TOKENS 승계 | `test_short_defaults_to_generate_max_tokens_env` | 승계(800) + 전용 override 우선(900) | — | 두 분기 |
| env <1/비정수 → 기동 실패 | `test_invalid_env_fails_app_creation` | `create_app()` raises | — | 4 case(0/-1/0/non-int), 3 이름 전부 |
| generate-only(revise-and-gate 필드 아님) | `test_output_length_is_a_generate_only_knob` | generate에 존재 | revise에 부재 | 구조적 lock |

- **under-strict 강도 점검**: `test_default_preset_is_short_1024`와 short subtest는 단독으로는 "기능 전체 제거" 시나리오를 잡지 못함(WritingService 생성 기본값도 1024라 우연히 동일). 그러나 (a) cell은 named test로 채워져 빈 cell이 아니고, (b) under-strict bite는 medium(2048)/long(4096) subtest가 담당(서비스 기본 1024와 달라 매핑 제거 시 즉시 bite), (c) "omitted → 1024"는 backward-compat 계약 자체가 "기존 단일값과 동일"을 요구하므로 기능 제거 시에도 올바른 동작(1024)이 보존됨 = 회귀 아님. work_log가 이 한계를 정직하게 공개. **contract-required cell이 named test로 잠겨 있으므로 차단 아님**(Hardening #1에서更强 guard 후보 명시).
- **경계값 커버**: preset 3값 전부(subtest); invalid env 4 case가 SHORT(0)·MEDIUM(-1, non-int)·LONG(0) 이름 전부 커버.
- **public surface 타겟**: HTTP 엔드포인트 + `provider.last_request.max_tokens`(실제 provider 요청) + status code + `create_app()`(기동 계약) + model field introspection(구조적 lock). 내부 helper가 아닌 호출 agent가 의존하는 표면.
- **frontend +2**: (1) 기본 short + select medium → body `output_length=="medium"`(under+over on select); (2) long → fetch 2회(generate+gate, 3번째 루프 fetch 없음) + notice. over-strict guard 명시("outputLength 체크 제거 시 3번째 fetch로 bite"). ✓

### 5. 공개 envelope/schema — gen:api 바이트 동일

- `schema.d.ts` diff는 **정확히 5줄**(`output_length: string` + `@default short` 주석). `npm run gen:api` 재실행 후 추가 diff **0** → working tree의 schema.d.ts가 완전하고 재생성과 동일. "gen:api는 generate 요청에 output_length 1개만 additive" 주장 확증. ✓
- `output_length: string`(enum이 아님)은 `task_type: str`(unknown → 400) 선례와 동형. 서버가 endpoint에서 enum 검증하므로 계약(short/medium/long, unknown→400) 충족. (Hardening #5: schema enum이 클라이언트 인지에 유리하나 선례 일관성 유지.)

### 6. 전체 스위트 정량 — 재현

| 항목 | work_log 주장 | 독립 재현 | 일치 |
|---|---|---|---|
| backend | 1237 passed / 73 skipped / 320 subtests | **1237 passed / 73 skipped / 320 subtests** | ✓ |
| backend 신규 클래스 | WritingOutputLengthPresetTest 8건 | 8 passed + 7 subtests | ✓ |
| frontend | 161 passed / 11 files | **161 passed / 11 files** | ✓ |
| tsc | clean | exit 0 (출력 0) | ✓ |
| gen:api | output_length 1개 additive | 재생성 diff 0 (5줄 유지) | ✓ |
| `git diff --check` | clean | clean | ✓ |

정량 주장이 전부 1:1로 재현됨. "보고된 숫자를 아무도 재계산 안 했다" 함정 없음.

### 7. 빌드/정적 검증

`tsc --noEmit` exit 0, `git diff --check` clean. 백엔드 diff는 D3에만 추적(surgical): import 1줄 + 함수 1개 + 필드 1개 + create_app 호출 1줄 + 엔드포인트 preset 해석/override. loop 예산(`WRITING_LOOP_MAX_*`) 변경 0. CLAUDE.md §3(surgical changes) 부합.

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix의 모든 contract-required cell(should-fire + should-NOT-fire + literal)이 named 회귀 테스트에 매핑되며, 빈 셀 없음. 정본 3곳의 literal이 코드에 변경 없이 반영. 정본 자기모순 없음. 양방향 guard 존재(`test_preset_is_independent_of_input_max_tokens` 두 축 각각 단언; `test_unknown` 400 + 모델 미도달). spec↔코드 literal 1:1.

### Hardening recommendations (비차단, 현 spec을 넘는 보강)

1. **short 경로의 HTTP-level 독립 guard**: `test_default_preset_is_short_1024`/short subtest는 서비스 생성 기본값(1024)과의 우연 일치로 "기능 전체 제거"를 단독 잡지 못함(under-strict bite는 medium/long이 담당). `test_short_defaults_to_generate_max_tokens_env`가 함수 수준에서 short 승계를 잠그나, **HTTP 경로**가 `_writing_output_length_tokens()`를 타는지(서비스 기본값이 아니라)를 pin 하는 테스트를 추가하면 short cell의 under-strict가更强해짐. 현 계약 요구(short=backward-compat 1024)는 이미 충족돼 차단 아님.
2. **비정수 env 기동 실패의 SoT 명시**: SoT clause는 "1 미만 기동 실패"만 명시하고 비정수를 열거하지 않음. 코드(`_env_int`의 `int()`)가 비정수를 거부하고 테스트(`not-an-integer` case)가 잠그나, SoT에 "1 미만 또는 비정수"로 명시하면 fail-loud 계약이 완전 열거됨. 증분 1 style-example 선례와 동일한 암묵적 처리라 차단 아님.
3. **`05-writing-ai.md:81` stale 참조 보강**: "writing_generate 1/120s/1024"가 agent-loop(dormant) budget profile임을 명시하거나 output_length preset(1024/2048/4096)을 역참조하는 1줄 추가. 미래 독자 혼동 방지. plan doc(역사 산물)이라 SoT(정본, 이미 정확)에 영향 없음.
4. **long 실측 시간 미검증(본질적 sandbox 한계)**: 4096≈91초는 ~45 tok/s 이론 추정. 슬라이스는 long을 구조적으로 루프에서 배제해 계약을 지켰으나, 실 12B 단일 generate 시간·`LLM_GATEWAY_TIMEOUT_SECONDS=120`/nginx `proxy_read_timeout 120s` 대비 실측은 오너 풀스택 후속(sandbox 12B 불가). 계약 논리(91s<120s, 루프 60s 초과로 배제)는 건전. work_log Next steps가 이미 이 한계를 명시.
5. **schema enum 표현**: `output_length: string` 대신 OpenAPI enum으로 short/medium/long을 노출하면 클라이언트 타입 인지 향상. 단 `task_type: str` 선례(unknown→400)와의 일관성 트레이드오프. 설계 선택, 차단 아님.

## Verdict

**PASS (조건 없음).**

근거(load-bearing):
- boundary matrix의 contract-required cell 전부가 named 회귀 테스트로 잠김(빈 셀 0).
- 정본 3곳(버전로그·Phase 5 clause·브리프 D3)의 모든 literal이 코드에 변경 없이 반영되며 서로 모순 없음.
- 양방향 guard(축 독립, 400+모델 미도달) 존재.
- 정량 주장 전부 독립 재현(backend 1237/73/320, frontend 161/11, gen:api 5줄 바이트 동일, tsc clean, diff --check clean).
- `long` 단일 generate 전용 제약이 **구조적으로** 잠김(WritingReviseRequest에 필드 부재 + 프론트 루프 스킵 + 유일 generate 호출처).
- 구현 diff가 D3에만 추적(surgical), loop 예산 무변.

5개 hardening 항목은 전부 현 spec을 넘거나 본질적 sandbox 한계로, 슬라이스를 fail시키지 않는다.

## Outstanding items

- **작업 트리 미커밋**: 증분 2 구현 11개 파일 + 본 검증 레코드가 working tree(uncommitted, commit `296c612` 위). 검증은 커밋하지 않은 상태로 수행됨. 커밋/발행은 오너 승인 대기.
- **오너 풀스택 후속**: long(4096) 실측 시간·타임아웃(sandbox 12B 불가). 증분 3(D4+D5+D6)이 다음 작업.
- 본 검증은 새로운 오너 결정을 만들지 않았다.

## Reproduction

```bash
# 1. backend 신규 클래스
python3 -m pytest tests/test_writing.py::WritingOutputLengthPresetTest -v -p no:cacheprovider

# 2. backend 전체 (정량 재현)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1237 passed, 73 skipped, 320 subtests

# 3. frontend 전체
cd frontend && npx vitest run
# 기대: Test Files 11 passed (11), Tests 161 passed (161)

# 4. tsc
cd frontend && npx tsc --noEmit   # exit 0

# 5. gen:api 바이트 동일 (재생성 후 추가 diff 0)
cd frontend && npm run gen:api && git diff --stat src/api/schema.d.ts

# 6. whitespace
git diff --check   # clean
```
