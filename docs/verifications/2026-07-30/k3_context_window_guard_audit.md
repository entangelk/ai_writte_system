# 검증 기록 — K-3 컨텍스트 창 가드(거부 + 경고)

## Subject metadata

- **날짜**: 2026-07-30
- **요청자**: 오너(entangelk) — “다음작업 검증해줘. K-3 완료, 커밋 4개로 정리됐습니다.”
- **검증자**: Claude(독립 검증 에이전트)
- **대상 슬라이스/산물**: K-3 — `입력 + 출력상한 ≤ 창`을 모델 호출 전에 게이트웨이에서 판정해 넘으면 400으로 거부(왕복 0회)하고, 빠듯한 호출은 KPI에서 경고로 보인다. 오너 결정(2026-07-30) “400 거부 및 경고로 가자. 비용 측면에서 필요한 가드니까.”
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.62(본문 §Phase 5 “창 가드” 한 줄 + 버전 로그), `docs/plans/context-budget-korean-tokens-decisions.md` §3 K-3, v1.7.59(헤드룸 파생·저장 금지)·v1.7.60(비대기) 선행 계약.
- **검증 대상 소스**: 커밋 3건 — `5fb292f`(게이트웨이 가드) · `00d57b3`(앱 400 매핑 + job 사유) · `07aa413`(KPI 경고, SoT v1.7.62). HEAD = `07aa413`. (오너가 “4개”라고 한 것은 R-e `9d1b310` 포함 추정; K-3 자체는 3커밋.)

## Scope

오너 결정 “400 거부 및 경고”를 두 갈래로 읽은 구현 전체. 경계 행렬을 계약에서 세운 뒤 각 셀 추적.

1. **게이트웨이 가드**(`client.py`): 식 `입력+출력상한 ≤ 창`, 모델 호출 **전** 판정, 왕복 0회, `/apply-template`+`/tokenize`로 센 실제 입력 수, 판정불가 시 통과.
2. **신규 literal**(`errors.py`): `provider_context_window_exceeded` ≠ `provider_request_rejected`(왕복 0 vs 1).
3. **앱 매핑**(`main.py`): `_provider_error_status`(TIMEOUT 504 · 창초과 400 · 그 외 502) 9개 호출부 통합.
4. **job 사유**(`generation_worker.py`·`generation_job.py`): `context_window_exceeded` ≠ `provider_error`.
5. **KPI 경고**(`kpi.py`): `thin_headroom_calls` + 분모 `headroom_considered`, 창 10% 임계, None 제외, 읽기 시점 파생(저장 금지).
6. **공개 계약**: `schema.d.ts` 변경 = KPI 2필드(site·totals) + compare endpoint 400 선언.
7. **프론트**: 관측 화면이 분모 0을 “측정되지 않음”으로 그린다.
8. **회귀 + 뮤테이션 매트릭스**(양방향).

## Methodology

정본을 먼저 스코핑(R-e 체인과 마찬가지)하고 경계 행렬을 세운 뒤 코드를 댐.

- 계약 읽기: SoT v1.7.62 본문 한 줄·버전 로그·§Phase 5 정독; 선행 v1.7.59(파생값)·v1.7.60(비대기) 계약과의 충돌 점검.
- 코드 읽기: `client.py` 가드(`_reject_if_window_exceeded`·`_window_decision`·`_guard_window`·`_count_prompt_tokens`)·`errors.py`·`main.py::_provider_error_status` + 9개 endpoint·`generation_worker.py`·`kpi.py`(`_headroom_rows`·`_thin_headroom`).
- 페이로드 무결성: `payload.py::build_llama_payload`가 항상 `chat_template_kwargs`를 싣는지 확인(delta-0 근거).
- 공개 계약: `frontend` `gen:api`(`dump_openapi.py` → `openapi-typescript`)로 **독립 재생성** 후 `diff src/api/schema.d.ts`(커밋본과 정확 일치 확인). `git diff 9d1b310 HEAD -- schema.d.ts`로 K-3 추가분 범위 확인.
- 백엔드 회귀: `PYTHONPATH=. pytest tests/test_llama_provider_client.py tests/test_llm_provider_errors.py tests/test_observability_kpi.py tests/test_writing_generation_worker.py tests/test_writing.py tests/test_writing_gate.py tests/test_application_api.py`.
- 프론트 회귀: `npx vitest run src/observability src/writing`.
- 전체 수집(import 손상 + 카운트): `pytest --collect-only -q`.
- **독립 뮤테이션 6종**(Edit → 해당 셀 실행 → 실패 확인 → 역방향 Edit 원복, 트리 clean·py_compile로 원복 확인): 가드 formula `입력≤창` · 경계 `<=`→`<` · fail-closed(내외부 except 양단) · `_provider_error_status` 400 분기 제거 · KPI None 판정 포함 · KPI 임계 `<`→`<=`.

## Findings

### 1. 게이트웨이 가드 — `client.py`

- `_reject_if_window_exceeded`(`client.py:121`): `max_tokens` None → 통과; `wait_for(_window_decision, 5s)`를 `try/except Exception: return`로 감싸 판정불가·예산초과 → 통과; **거부는 `try` 밖에서 `raise decision`** → `except`에 삽켜지지 않음(주석이 이 함정을 명시).
- `_window_decision`(`client.py:144`): 창 None·입력 None → None(판정불가); `input + max_output <= window` → None(통과); 초과 → `ProviderError(CONTEXT_WINDOW_EXCEEDED, retryable=False)`. 경계 **`<=`**(==창 통과)가 계약과 일치.
- `_count_prompt_tokens`(`client.py:191`): `/apply-template`(같은 `chat_template_kwargs`) → `/tokenize`(`add_special=True`) → `len(tokens)`. 세 조건(① kwargs ② add_special ③ apply-template 전체)이 코드에 모두 있고, 어긋 시 `None`(통과) 또는 과소평가.
- `_guard_window`(`client.py:172`): `self._context_window`(캐시)만 반환, **기다리지 않는다** → v1.7.60 비대기 계약 준수. 창 모르는 호출(첫 호출·/props 실패)은 가드 밖(의도된 공백).
- `build_llama_payload`(`payload.py:76`)이 항상 `chat_template_kwargs`(기본 `{}`)를 싣음 → 가드의 `payload["chat_template_kwargs"]`는 KeyError가 아니며 apply-template과 실제 생성이 동일 kwargs → delta-0 근거 성립.

### 2. 신규 literal — `errors.py`

- `ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED = "provider_context_window_exceeded"`(`errors.py:17`). `REQUEST_REJECTED`(모델 서버 거부)과 구분. 계약 리터럴 일치.

### 3. 앱 매핑 — `main.py`

- `_provider_error_status`(`main.py:1319`): TIMEOUT→504 · CONTEXT_WINDOW_EXCEEDED→400 · 그 외 502. 9개 endpoint(gate/revise/report/loop/retrieve/compare 등)가 `504 if TIMEOUT else 502` 복제에서 이 함수로 통합.
- **창초과→400은 모든 endpoint에서 일관**. `/writing/generate`만 손필 분기인데, 이는 **TIMEOUT→502라는 기존 불일치**를 건드리지 않으면서 창초과→400만 더한 것(아래 Issues H2).

### 4. job 사유 — `generation_worker.py`·`generation_job.py`

- `CONTEXT_WINDOW_EXCEEDED` code → `reasons.CONTEXT_WINDOW_EXCEEDED`(`generation_worker.py:143`). `PROVIDER_ERROR`/`PROVIDER_TIMEOUT`과 3-way 분기. “재시도=같은 실패”라 화면 분리가 계약과 일치.

### 5. KPI 경고 — `kpi.py`

- `THIN_HEADROOM_FRACTION = 0.1`(`kpi.py:60`). `_headroom_rows`는 세 값(window·max_output·prompt) 모두 non-None인 행만(분모 방어). `_thin_headroom` = `window − prompt − max_output < window*0.1`(음수=초과 포함). site·totals가 `_thin_headroom` 공유 → 두 화면이 같은 사실.
- 저장하지 않고 읽기 시점 파생 → v1.7.59(파생값) 계약 준수. 감사 레코드는 원천 세 값을 이미 가짐.

### 6. 공개 계약 — `schema.d.ts`

- **독립 재생성 후 `diff` = 커밋본과 정확 일치**. K-3 추가분(`git diff 9d1b310 HEAD`) = `headroom_considered`+`thin_headroom_calls`(site·totals 각) + compare endpoint `400`. 주장과 정확히 일치.

### 7. 프론트

- `ObservabilityDashboard.tsx:186`가 `headroom_considered === 0`일 때 숫자가 아닌 “측정되지 않음”을 그림. 분모 없이 숫자만 그리는 과잉 교정을 테스트가 잠금.

### 8. 회귀 + 뮤테이션

- 백엔드 K-3 표면: **310 passed / 499 subtests**(7파일). 원복 후 재 **83 passed / 40 subtests**.
- 프론트: **86 passed**(observability+writing 5파일).
- 전체 수집: **1737 collected**(=1736 통과 + 1 스킵, 작업자 주장과 일치). import 손상 없음.
- **독립 뮤테이션 6종, 전부 해당 셀에서 실패**(역방향 Edit 원복 후 트리 clean·py_compile·formula=`<=` 복구 확인):
  - 가드 formula `입력+출력 ≤ 창` → `입력 ≤ 창`: 거부 셀이 모델을 불러 큐 소진 예외(★ K-3 존재이유 = 조용한 잘림).
  - 경계 `<=` → `<`: ==창 통과 셀이 거부(`1000 > window 1000`).
  - fail-closed(내외부 `except` 양단 `raise`): 통과 셀 3/4 실패. 단, 한 단계만 바꾸면 물지 않는다 — **두 단계 방어가 의도대로 작동**하는 증거(빈 셀 아님).
  - `_provider_error_status` 400 분기 제거: 전수 셀이 `502 != 400`(작업자가 발견·충전한 빈 셀).
  - KPI `_headroom_rows` None 필터 제거: 분모 셀 TypeError.
  - KPI 임계 `<` → `<=`: 정확히 10% 호출이 경고로(1≠0).

## Issues / Risks

### Blocking (계약 의무) — 없음

경계 행렬의 모든 fire/NOT-fire 셀이 코드·테스트에 매핑됨. 계약 내부 모순 없음 — 특히 가드의 비대기(`_guard_window`)가 v1.7.60과, KPI 파생이 v1.7.59와 각각 일치. “`입력 ≤ 창`으로는 부족하다”는 근거가 뮤테이션 1로 입증됨. spec-silent-but-enforced 갭 발견 안 됨.

### Hardening recommendations (비차단)

- **H1 — 가드 판정 왕복이 생성 핫경로에 있다**: 가드는 창 캐시가 찬 뒤 매 호출마다 `/apply-template`+`/tokenize` 2왕복을 `await`한다(실측 6~67ms, 5s 예산으로 fail-open). 모델 왕복을 아끼는 가드가 입력 측정 왕복 비용을 발생시키는 것은 슬라이스가 받아들인 트레이드오프이고 계약에 기록됐다. 다음 트랙(K-1)과 상호작용할 수 있으니 인지 권장. 결함 아님.
- **H2 — SoT “한 곳으로 모았다” 사소한 과잉 서술**: v1.7.62가 “`_provider_error_status` 한 곳으로 모았다”고 적지만 `/writing/generate`는 손필 분기로 남아있다(TIMEOUT→502, 기존 불일치). K-3 관련(창초과→400)은 전 endpoint 일관이므로 계약 위반 아니다. 문장이 예외를 명시하진 않지만 같은 버전 로그가 별도로 부채로 적고 있어 모순까진 아니다. 문서 정비 후보.
- **H3 — 실측 미재현**: 라이브 12B 타이밍(200/400·29ms·9ms·경계 200)은 외부 12B가 필요해 이 검증에서 독립 재실측 못 함. 결정론적 부분(formula·경계·매핑·임계·분모)은 전부 검증됐으나 왕복 0회의 실측 지연·“조용한 잘림” 재현은 작업자 보고치. 오너 공표 전 재실측 권장.
- **H4 — 전체 1736 green bar 미종단**: K-3 표면(310) + 프론트(86) + 수집(1737) 검증. test mongo/es compose가 안 올라와 있어 전체 suite는 worker 환경 기준.

## Verdict

**합격(PASS).**

하중 이유: (1) 경계 행렬 빈 셀 없음 — 가드 fire/NOT-fire·앱 매핑 전수·KPI 경고 양방향·공개 계약이 전부 회귀로 매핑; (2) 선행 계약(v1.7.59 파생·v1.7.60 비대기)과 충돌 없음 — 작업자가 “경고를 저장 필드가 아닌 읽기 시점 파생”으로, “가드가 창을 기다리지 않는다”로 각각 지켬; (3) 뮤테이션 6종(양방향)이 독립적으로 해당 셀을 물음 — 특히 formula `입력≤창` 퇴행(★ 조용한 잘림)과 400 분기 제거(작업자가 스스로 발견·충전한 빈 셀); (4) `schema.d.ts` 독립 재생성이 커밋본과 정확 일치하며 변경 범위가 주장(KPI 2필드+compare 400)과 일치; (5) fail-open이 두 단계 방어로 구현됨. 비차단 H1~H4는 스펙을 넘어서는 보강/환경 한계이며 합격을 가리지 않음.

## Outstanding items

- **커밋 완료**: K-3 3커밋(`5fb292f`·`00d57b3`·`07aa413`)이 HEAD. 트리 clean.
- **다음 슬라이스 = K-1(밀도)**: 가드는 정확한 토큰수를 쓰지만 예산 회계는 여전히 `len/4`(실제의 1/2.17). 현재 “예산은 틀리고 가드가 막아 준다” 상태. 작업자 추천 (c)+(a)(색인 시 토큰수 저장 + 상수 fallback).
- **추적 부채 3건**: ① 가드 의도 공백(프로세스 첫 호출·/props 실패 프로세스) — 닫으려면 v1.7.60 “기다리지 않는다”를 가드 경로에 한해 개정하는 오너 결정 필요. ② `/writing/generate` TIMEOUT→502 vs 타 endpoint 504(기존 불일치). ③ SoT “한 곳으로 모았다” 문장 정비(H2).
- **실측 재실측**(H3): 라이브 12B로 왕복 0·조용한 잘림 재확인.

## Reproduction

```bash
# 공개 계약 무변 + 변경 범위
cd frontend && node_modules/.bin/openapi-typescript <(python3 ../scripts/dump_openapi.py) -o /tmp/k.d.ts \
  && diff src/api/schema.d.ts /tmp/k.d.ts   # expect: no output
cd .. && git diff 9d1b310 HEAD -- frontend/src/api/schema.d.ts   # expect: 2 KPI fields x2 + compare 400

# K-3 백엔드 + 프론트
PYTHONPATH=. python3 -m pytest tests/test_llama_provider_client.py tests/test_llm_provider_errors.py \
  tests/test_observability_kpi.py tests/test_writing_generation_worker.py tests/test_writing.py \
  tests/test_writing_gate.py tests/test_application_api.py -q   # 310 passed / 499 subtests
cd frontend && npx --no-install vitest run src/observability src/writing   # 86 passed

# 수집
PYTHONPATH=. python3 -m pytest --collect-only -q   # 1737 collected

# 뮤테이션(예: formula 퇴행) — client.py _window_decision 의
# `input_tokens + max_output <= window` 를 `input_tokens <= window` 로 바꾼 뒤:
PYTHONPATH=. python3 -m pytest \
  "tests/test_llama_provider_client.py::ContextWindowGuardTest::test_over_the_window_is_rejected_without_calling_the_model" -q
# expect: FAILED (FakeTransportExhausted — 모델이 불림) → 역방향 Edit 원복
```
