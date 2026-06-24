# 검증 기록 — LLM Gateway Slice 0.1~0.5 F1/F2 폐쇄 delta

## Subject metadata

- 일자: 2026-06-24
- 요청자: 사용자(HANDOFF Next Task #1 — F1/F2 보강 후속 독립 재검증 후 조건부 합격 verdict 승격 여부 결정)
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact: Slice 0.1~0.5 조건부 합격의 두 폐쇄 조건(F1, F2) + direct live smoke
- canonical spec reference:
  - `docs/plans/llm-gateway.md` 상태 `Proposed`, `현재 request preconditions`(73-81줄)·`현재 text-completion response preconditions`(95-103줄)
  - `docs/plans/implementation-plan.md` 상태 `Draft`, Slice 0.1(54-64줄)·Slice 0.5(98-110줄)·`완료: 검증 조건 F1/F2 보강과 direct live smoke`(112-117줄)
  - 검증 브리프: `docs/verification_briefs/2026-06-24/llm_gateway_f1_f2_live_smoke.md`
- source of the work being verified: commit `4b4129b test: close LLM provider verification gaps`(working tree clean, `git status --porcelain` 빈 출력). delta 12개 파일 +478/-16. 원 검증 대상 `c87fec3` 이후의 회귀/계약 보강 분량만 포함.
- 구현 환경: Python 3.12.3, 표준 라이브러리만 사용.

## Scope

브리프가 지정한 canonical delta scope만 읽었고, `docs/` 루트 장문 설계와 Slice 0.6(httpx adapter)는 제외했다(0.6은 별도 기록에서 이미 합격). 점검한 표면:

1. spec contract — `llm-gateway.md` request/response preconditions + `implementation-plan.md` F1/F2 closure 섹션
2. delta 구현 코드 — `services/llm_gateway/app/{payload,errors,client}.py`(F2 표면) + `transport.py`(exhaustion pattern sweep)
3. regression tests — `tests/test_llm_{gateway_payload,provider_errors,transport_mapping}.py`, `tests/test_llama_provider_client.py`
4. contract 자기 모순 — `llm-gateway.md` precondition prose ↔ `errors.py` literal ↔ 테스트 기대값 교차 대조
5. pattern sweep — gateway app 전체 `raise` 사이트의 spec-silent 거부 잔존 여부
6. full test suite — `python3 -m unittest discover -s tests`
7. direct live smoke — `http://192.168.1.29:9080` health/models/completion 재실행

## Methodology

1. **컨트랙트 스코핑 먼저**: 코드를 열기 전에 브리프와 두 plan 문서의 delta 섹션만 end-to-end로 읽어 boundary matrix를 세웠다. Slice 0.6과 0.6 이전 장문은 읽지 않았다.
2. **delta 범위 확인**: `git show 4b4129b`로 delta가 브리프 scope와 정확히 일치하는지(plan precondition 섹션 추가 + 회귀 추가, 불필요 변경 혼입 없음) 확인했다.
3. **경계 매트릭스 구축**: F1(default true/false 대칭) + F2(7 request precondition + 7 response precondition)의 should-fire/should-NOT-fire 분기와 모든 literal을 추출해 코드·테스트에 1:1 매핑했다(빈 칸 점검).
4. **코드 literal 대조**: payload/errors/client를 literal 단위로 1:1 대조. paraphrase 불허.
5. **테스트 코드 감사**: 각 회귀가 (a) public 표면 고정, (b) under-strict guard, (c) over-strict guard, (d) parametrize 전 경계값을 덮는지.
6. **양방향 가드 증명(F1 핵심)**: 원 검증이 지적한 under-strict 위험을 직접 변이로 증명했다. `payload.py:65-69`의 `else default_thinking`을 `else False`로 바꾸면 default=True 회귀가 실패하고, `else True`로 바꾸면 default=False 회귀가 실패하는 것을 확인한 뒤 원본 복원(`git diff --stat` 빈 출력, `git status --porcelain` 빈 출력).
7. **pattern sweep**: `grep -rn raise services/llm_gateway/app/`로 모든 거부 사이트가 contract precondition, stable error mapping, 또는 test-harness exhaustion 중 하나에 해당하는지 점검.
8. **독립 재현**: 검증자가 직접 전체 회귀와 live smoke 3종을 재실행(아래 Reproduction). 작성자 관측치는 믿지 않고 재도출.

사용한 정확한 명령은 Reproduction 섹션에 있다.

## Findings

### 1. delta 범위 일치

`git show --stat 4b4129b`에서 delta는 브리프가 지정한 표면에 정확히 부합한다:
- `llm-gateway.md` +20: request/response preconditions 섹션 신규 추가
- `implementation-plan.md` +11: Slice 0.1 precondition 줄, Slice 0.5 exhaustion 줄, F1/F2 closure 섹션 추가
- `tests/test_llm_gateway_payload.py` +41: F1 true 회귀 + messages/role/max_tokens/default_model 회귀
- `tests/test_llama_provider_client.py` +58: malformed case 5종(model None, finish_reason None, token 음수/bool/string/float)
- `tests/test_llm_provider_errors.py` +8: 빈 message 회귀
- `tests/test_llm_transport_mapping.py` +18: FakeJsonTransport exhaustion 회귀
- `services/llm_gateway/app/payload.py` +/-8: 회귀 기대값과 일치하도록 기존 로직 정리(새 거부 분기 추가 아님 — 이미 존재한 거부를 회귀로 고정)

불필요한 변경(인접 코드 개선, 포맷)은 없다. ✓

### 2. F1 폐쇄 — 양방향 가드 증명

F1 원 조건: “thinking 생략 시 `default_thinking`이 따라가는 것을 True 한 값으로만 고정해 미추적.”

- 코드 `payload.py:65-69`: `effective_thinking = request.thinking if request.thinking is not None else default_thinking`. 두 방향 모두 default 값을 그대로 전달.
- 회귀:
  - `test_default_thinking_applies_when_request_omits_it`(`tests/test_llm_gateway_payload.py:38-45`): `default_thinking=False` → `assertIs ... False`. ✓
  - `test_default_thinking_true_applies_when_request_omits_it`(47-54줄): `default_thinking=True` → `assertIs ... True`. ✓ (이번 delta 신규)
- **양방향 변이 증명**(검증자 직접 실행):
  - 변이 A `else default_thinking → else False`: default=True 회귀 **FAIL**(`AssertionError: False is not True`). under-strict 방향 포착. ✓
  - 변이 B `else False → else True`: default=False 회귀 **FAIL**(`AssertionError: True is not False`). over-strict 방향 포착. ✓
  - 변이 후 원본 복원, `git status --porcelain` 빈 출력, payload 회귀 12/12 재통과.

F1은 단순히 회귀가 추가된 것이 아니라 두 방향 모두 회귀 도입을 실제로 잡아냄이 증명됐다. ✓

### 3. F2 폐쇄 — request/response precondition의 계약 승격

F2 원 조건: “코드가 거부하는데 contract가 다루지 않는(spec-silent) 입력 분기의 계약 지위 확정.”

해결 방향(작성자 선택): 완화가 아닌 **공식 precondition으로 채택**. `llm-gateway.md` 73-103줄에 request/response precondition이 명문화됐고(commit `4b4129b` delta), 각 분기가 회귀로 고정됐다.

**Request precondition 매트릭스:**

| Precondition(코드) | plan prose(llm-gateway.md) | 회귀 테스트 | 고정 |
|---|---|---|---|
| messages 빈 → ValueError(`payload.py:42-43`) | 75줄 “messages는 하나 이상” | `test_messages_must_not_be_empty` | ✓ |
| role 빈 → ValueError(`payload.py:20-21`) | 76줄 “role은 빈 문자열일 수 없다” | `test_message_role_must_not_be_empty` | ✓ |
| stream=true → ValueError(`payload.py:44-45`) | 77줄 “stream은 false만” | `test_streaming_is_rejected_until_gateway_supports_it` | ✓ |
| max_tokens 0/-1/bool/float/string 거부(`payload.py:46-51`) | 78줄 “생략하거나 1 이상의 정수, 0은 불가” | `test_max_tokens_must_be_positive_and_one_is_valid`(5값 parametrize) | ✓ |
| max_tokens=1 수용 + 전달(over-strict guard) | 동일 | 같은 테스트 `assertEqual(payload["max_tokens"], 1)` | ✓ |
| default_model 빈 → ValueError(`payload.py:62-63`) | 79줄 “default_model은 빈 문자열 불가” | `test_default_model_must_not_be_empty` | ✓ |

**Response precondition 매트릭스:**

| Precondition(코드) | plan prose(llm-gateway.md) | 회귀 테스트 | 고정 |
|---|---|---|---|
| 2xx만 parsing, 3xx는 INVALID_RESPONSE(`client.py:55-64`) | 97줄 “2xx만 성공 후보” | `test_redirect_response_is_not_accepted_as_generation`(307) | ✓ |
| body object 아님/choices 빈 → INVALID_RESPONSE(`client.py:70-74`) | 98줄 “body는 object, choices는 비어있지 않은 list” | `test_malformed_success_response...` case 1,2 | ✓ |
| model/content/finish_reason 비문자열 → INVALID_RESPONSE(`client.py:71,78,79`) | 99줄 “model, content, finish_reason은 문자열” | 같은 테스트 case 3,4,5 | ✓ |
| usage 생략 → 0(over-strict guard, 수용 방향) | 100줄 “usage 생략 가능, token usage는 0” | `test_missing_usage_is_valid_and_defaults_to_zero` | ✓ |
| token 음수/bool/string/float → INVALID_RESPONSE(`client.py:117-119`) | 101줄 “bool이 아닌 0 이상의 정수” | 같은 테스트 case 6,7,8,9 | ✓ |
| public message 빈 → ValueError(`errors.py:47-48`) | 102줄 “message는 빈 문자열 불가” | `test_public_error_message_must_not_be_empty` | ✓ |
| 위반 성공 응답 → provider_invalid_response | 103줄 | 모든 malformed case가 `INVALID_RESPONSE` 단언 | ✓ |

delta boundary matrix 13개 branch가 빈 칸 없이 코드 + 회귀에 매핑된다. parametrize가 모든 열거 경계값을 덮는다(max_tokens `{0,-1,True,1.5,"1"}`, token `{음수,bool,string,float}`, 문자열 필드 `{model,content,finish} None`). ✓

### 4. contract 자기 모순 점검

- `llm-gateway.md` precondition prose ↔ `errors.py` 5 literal ↔ `implementation-plan.md` Slice prose ↔ 테스트 기대값을 교차 대조. 내부 모순 없음.
- error literal 5종(`provider_unavailable/timeout/overloaded/invalid_response/request_rejected`)이 네 출처에서 문자열 그대로 일치. ✓

### 5. pattern sweep — spec-silent 거부 잔존 여부

`grep -rn raise services/llm_gateway/app/`의 22개 raise 사이트를 분류:
- contract precondition(payload/errors 5종) → 회귀 있음 ✓
- stable error mapping(client `error_from_http_status`/`error_from_transport_failure`, transport, httpx → TransportFailure) → 회귀 있음 ✓
- test-harness exhaustion(`FakeProviderExhausted`, `FakeTransportExhausted`) → 회귀 있음 ✓
- mapper misuse guard(`transport.py:105` status<400 ValueError) → `test_success_and_redirect_statuses_are_not_misclassified_as_errors` ✓

F2 표면에 spec-silent code-enforced 거부는 남아있지 않다. ✓

### 6. full test suite — 독립 재현

`python3 -m unittest discover -s tests -v` → **Ran 43 tests, OK**(0 failure, 0 error). 분포: httpx 6 + client 7 + payload 12 + provider(fake) 4 + errors 6 + transport 8 = 43. HANDOFF “43개 통과”·브리프 기대치(42 + I2 close-lifecycle 1 = 43)와 일치. green bar는 보조 증거. ✓

### 7. direct live smoke — 독립 재실행

작성자 관측치를 믿지 않고 동일 endpoint 재실행. 결과 일치:

| 항목 | 작성자 관측 | 검증자 재실행 | 일치 |
|---|---|---|---|
| `/health` | `{"status":"ok"}` | `{"status":"ok"}` | ✓ |
| model | Q4_0, GGUF, context 8192 | `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, `format:gguf`, `n_ctx:8192` | ✓ |
| completion content | `연결 확인 완료` | `연결 확인 완료` | ✓ |
| finish_reason | `stop` | `stop` | ✓ |
| usage | prompt 23 / completion 5 / total 28 | prompt 23 / completion 5 / total 28 | ✓ |
| reasoning_content | 부재(thinking off) | 부재 | ✓ |

이 smoke는 direct curl이며 `LlamaCppProvider`를 실제 network transport로 검증한 것은 아니다(Slice 0.6 기록에서 별도 합격). 브리프의 명시적 제한과 일치. ✓

## Issues / Risks

> blocking 결함 없음. 아래는 모두 비차단 informational이며, CLAUDE.md가 금지하는 “미추적 over-strict guard를 future risk로 재분류” 패턴에 해당하지 않는다 — delta boundary matrix의 모든 should-fire/should-NOT-fire branch에 명명된 회귀가 있다.

### O1 (정보, non-blocking — prose 대칭성)

`max_tokens` precondition prose(`llm-gateway.md:78`)은 “1 이상의 정수”로 표현하고 token-count precondition(101줄)은 “bool이 아닌 0 이상의 정수”로 표현한다. 코드는 양쪽 모두 bool을 거부(`payload.py:47`, `client.py:118`). “정수”가 의미상 bool 배제를 포함하므로 거부 동작은 계약 일관이며, max_tokens 회귀가 `True`를 invalid로 parametrize하므로 분기도 lock됐다. 다만 prose 대칭을 위해 max_tokens 줄에도 “bool이 아닌”을 붙이면 더 명확하다. 동작·검증에는 영향 없음.

### O2 (정보, non-blocking — 구조적 컨테이너 guard)

`client.py:105-108`의 `_mapping`은 `choices[0]`와 `choice["message"]`가 object임을 요구해, 비-object choice/message를 INVALID_RESPONSE로 분류한다. 이는 contract의 “model/content/finish_reason은 문자열” 전제가 구조적으로 요구하는 것이므로 over/under-strict가 아니다. 별도 malformed case(`choices=[42]`)로 명시 테스트하지는 않았으나 같은 `_mapping` 경로이고 case 1(`body=[]`)이 object-아님 분기를 이미 잡는다. 보강 후보로만 기록.

## Verdict

**합격(pass).** 원 조건부 합격의 두 조건이 모두 충족됐으므로 조건부 합격을 합격으로 승격한다.

load-bearing 이유:

1. **F1 폐쇄 확인(양방향 증명)**: `default_thinking` 대칭 회귀가 추가됐을 뿐 아니라, 검증자가 코드를 직접 변이해 두 방향 모두 회귀를 잡아냄을 증명했다(else False → true-test FAIL, else True → false-test FAIL). under-strict·over-strict 양쪽 lock.
2. **F2 폐쇄 확인(계약 승격)**: 7 request + 7 response precondition이 `llm-gateway.md`에 명문화됐고 각각 1:1로 회귀에 매핑된다. delta boundary matrix 13개 branch에 빈 칸 없음. parametrize가 모든 열거 경계값을 덮는다. F2 표면에 spec-silent code-enforced 거부가 남아있지 않다(pattern sweep 확인).
3. **contract 자기 모순 없음**: precondition prose ↔ literal ↔ 테스트가 네 출처에서 일치.
4. **live smoke 독립 재현**: 작성자 관측치 6항목 전부 검증자 재실행으로 일치(content `연결 확인 완료`, usage 23/5/28, non-thinking).
5. **독립 재현**: 43/43 회귀 통과. green bar는 보조 증거이고 주 판단은 위 매트릭스 추적과 양방향 변이 증명이다.

명시적 거부: 남은 O1·O2를 “future enhancement/후속 보강 후보”로 재분류하지 않는다. 단, 두 항목은 분기 lock이 이미 존재하므로(회귀 있음) CLAUDE.md가 금지하는 “미추적 over-strict guard”가 아니며, 합격을 가르는 blocking 조건이 아니다.

원 검증 기록(`llm_gateway_slice_0_1_to_0_5.md`)은 독립 감사 산출물이므로 본문을 수정하지 않는다. 본 기록의 합격 verdict가 원 조건부 합격의 두 조건(F1, F2)을 폐쇄한다.

## Outstanding items

- working tree: clean(commit `23c3519` HEAD, `git status --porcelain` 빈 출력). F1/F2 delta는 `4b4129b`, Slice 0.6은 `23c3519`에 각각 커밋됨.
- F1/F2 delta + direct live smoke 검증이 합격으로 폐쇄됐으므로, HANDOFF Next Task #1(Slice 0.1~0.5 verdict 승격 여부 결정)은 완료. 핸드오프의 “조건부 합격” 표기를 합격으로 갱신한다.
- HANDOFF Next Task #2(flat loop decision/tool/budget 계약 확정)가 다음 과제.
- O1/O2/M3(아래 “Hardening applied” 참조)는 소유자 결정으로 적용 완료됐다. 비차단 informational이었으나 traceability 명확화를 위해 회귀·prose 보강을 반영했다.

## Reproduction

저장소 루트에서:

```bash
python3 --version                                          # 3.12.3 확인
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v   # Ran 43 tests, OK
git status --porcelain                                     # 빈 출력(clean)
git show --stat --oneline 4b4129b                          # F1/F2 delta 범위 확인

# F1 양방향 가드 증명(변이 후 반드시 원본 복원):
cp services/llm_gateway/app/payload.py /tmp/payload_backup.py
# 변이 A: payload.py 의 'else default_thinking' -> 'else False'
python3 -m unittest tests.test_llm_gateway_payload.LlamaPayloadContractTests.test_default_thinking_true_applies_when_request_omits_it   # FAIL
# 변이 B: 'else False' -> 'else True'
python3 -m unittest tests.test_llm_gateway_payload.LlamaPayloadContractTests.test_default_thinking_applies_when_request_omits_it          # FAIL
cp /tmp/payload_backup.py services/llm_gateway/app/payload.py        # 복원
git status --porcelain                                     # 빈 출력(복원 확인)

# direct live smoke(작성자 관측 재실행):
curl -sS --max-time 10 http://192.168.1.29:9080/health      # {"status":"ok"}
curl -sS --max-time 10 http://192.168.1.29:9080/v1/models   # Q4_0 / gguf / n_ctx 8192
curl -sS --max-time 120 http://192.168.1.29:9080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0","messages":[{"role":"user","content":"다음 문장을 그대로 답하세요: 연결 확인 완료"}],"chat_template_kwargs":{"enable_thinking":false},"temperature":0,"max_tokens":32,"stream":false}'
# content "연결 확인 완료", finish_reason stop, usage prompt 23 / completion 5 / total 28

# spec-silent 거부 잔존 pattern sweep(모든 raise가 precondition/mapping/exhaustion에 해당):
grep -rn "raise" services/llm_gateway/app/
```

## Meta-verification addendum

본 섹션은 작업 AI(위 본문의 검증자)의 “합격 승격” verdict를 독립·회의적으로 재검증한 메타검증자의 추가 증거만 기록한다. 작업 AI가 쓴 본문·verdict·findings prose는 일절 수정하지 않았다. 메타검증자는 같은 1차 자료에서 재도출했다.

- 메타검증 일자: 2026-06-24
- 메타검증자: 독립 메타검증 AI(Claude Code)
- 대상: 위 본문의 합격 verdict와 F1/F2/live smoke 주장
- 기준 HEAD: `5cb6f18`(working tree clean, `git status --porcelain` 빈 출력 확인)

### M1. F1 양방향 가드 — 메타검증자 직접 변이 재현

작업 AI의 변이 증명을 메타검증자가 독립 재현했다(백업→변이→FAIL 확인→원본 복원 전 단계 수행).

- 변이 A `else default_thinking → else False`: `test_default_thinking_true_applies_when_request_omits_it`가 `AssertionError: False is not True`로 **FAIL**(under-strict 방향). 동시에 false-test는 통과. 작업 AI 주장과 일치.
- 변이 B `else False → else True`: `test_default_thinking_applies_when_request_omits_it`가 `AssertionError: True is not False`로 **FAIL**(over-strict 방향). 동시에 true-test는 통과. 작업 AI 주장과 일치.
- 원본 복원: `cp /tmp/payload_backup_meta.py` 후 `git status --porcelain` 빈 출력, `git diff --stat` 빈 출력, `payload.py:65-69`의 `else default_thinking` 복귀 확인. 복원 누락 없음.
- 결론: F1 가드는 진짜 양방향이며 단방향만 통과하는 pseudo-guard가 아니다. 메타검증자 평가: 작업 AI의 F1 폐쇄 주장은 **사실**.

### M2. 추가 변이 — max_tokens bool guard pin 확인

작업 AI는 max_tokens parametrize가 `{0,-1,True,1.5,"1"}`를 덮는다고 주장했다. 메타검증자는 bool guard(`payload.py:47`의 `isinstance(self.max_tokens, bool)`)를 제거하는 변이로 이 주장을 보강 검증했다.

- 변이: bool 체크 줄 제거 → `test_max_tokens_must_be_positive_and_one_is_valid`가 `AssertionError: ValueError not raised`로 **FAIL**(under-strict, `max_tokens=True`가 거부되지 않음).
- 결론: max_tokens=True parametrize 값이 bool guard를 실제로 pin한다. 복원 clean.
- 이는 작업 AI가 명시적으로 변이 증명하진 않았지만, 주장(parametrize가 경계값을 덮는다)의 타당성을 메타검증자가 추가 입증.

### M3. 추가 변이 — token=0 over-strict guard (작업 AI 미언급 분기)

메타검증자는 token count 하한 경계(`value < 0`, 즉 `0 이상`)의 over-strict guard를 별도로 점검했다. 작업 AI는 token parametrize가 `{음수,bool,string,float}`를 덮는다고 했으나, **token=0 입력값이 수용되는 경계(하한 0의 should-NOT-fire)**는 전용 회귀가 없다.

- 변이 `value < 0 → value < 1`(token=0을 잘못 거부): `test_missing_usage_is_valid_and_defaults_to_zero`가 **FAIL**(usage 생략 시 기본값 0이 `_token_count(0)`로 들어가 거부됨).
- 결론: token=0 over-strict guard는 전용 token-count 회귀는 없으나, **`test_missing_usage`의 usage-omission 기본값 0 경로가 우회적으로 pin**한다. lock은 존재하지만 traceability가 불투명(전용 token-count 회귀로 명시하면 더 명확).
- 평가: 이는 작업 AI가 놓친 추가 관측이나, **guard 자체는 존재**하므로 합격을 가르지 않는다. 다만 boundary matrix traceability 보강 후보로 기록(전용 `prompt_tokens=0` 수용 case 추가 권장).
- 해결(2026-06-24 소유자 결정): 전용 `test_zero_token_counts_are_accepted_as_valid` 회귀가 추가됐다. 메타검증자가 `_token_count`의 `value < 0 → value < 1` 변이로 이 회귀가 token=0 수용 경계를 실제로 pin함(변이 시 `ProviderError: provider returned an invalid response`로 FAIL)을 확인했다. traceability 명확화 완료.

### M4. boundary matrix 13 branch 삼각검증 — 메타검증자 재추적

작업 AI의 13 branch 매핑을 코드 줄 ↔ 테스트 함수 ↔ 계약 prose(`llm-gateway.md:75-103`) 삼각검증했다.

- request 7 + response 7 = 14 branch 중 F1(thinking 생략)을 제외한 13 branch가 1:1로 추적됨을 메타검증자가 독립 확인. 빈 칸 없음.
- 모든 parametrize 경계값(max_tokens 5값, token 4값, 문자열 필드 3곳 None)이 실제 public 표면(payload dict, INVALID_RESPONSE 단언)을 pin함을 확인.
- 결론: 작업 AI의 “13개 branch 빈 칸 없음” 주장은 **사실**.

### M5. live smoke — 메타검증자 독립 재실행

작성자·작업AI 관측치를 믿지 않고 동일 curl 재실행. 6항목 전부 일치:

- `/health` → `{"status":"ok"}` ✓
- `/v1/models` → `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, `format:gguf`, `n_ctx:8192` ✓
- completion content → `연결 확인 완료` ✓
- finish_reason → `stop` ✓
- usage → prompt 23 / completion 5 / total 28 ✓
- `reasoning_content` → 부재(thinking off) ✓

이 smoke는 direct curl이며 `HttpxJsonTransport`를 경유한 것은 아님을 재확인(Slice 0.6 기록에서 별도 합격).

### M6. spec-silent 거부 잔존 — 메타검증자 독립 pattern sweep

`grep -rn "raise" services/llm_gateway/app/`의 22개 raise 사이트를 메타검증자가 재분류: contract precondition(5종) + stable error mapping(client/transport/httpx) + test-harness exhaustion(Fake*Exhausted) + mapper misuse guard(status<400 ValueError)로 전부 분류됨. F2 표면에 spec-silent *거부* 분기 잔존 없음. 추가 spec-silent 후보(content=None 수용, temperature/top_p 무검증)는 *수용/전달*이지 거부가 아니므로 F2 범위 밖.

### M7. 작업 AI의 “future risk 재분류 금지” 준수 여부

작업 AI는 verdict 160줄에서 O1·O2를 “future enhancement/후속 보강 후보로 재분류하지 않는다”고 명시했다. 메타검증자 평가: CLAUDE.md가 금지하는 “미추적 over-strict guard를 future risk로 재분류” 패턴을 **위반하지 않는다**. O1·O2는 둘 다 분기 lock(회귀)이 이미 존재하므로 “미추적”이 아니다.

### M8. O1/O2 non-blocking 분류 — 메타검증자 평가

- **O1**(max_tokens prose “bool이 아닌” 누락): 동작은 양쪽 모두 bool 거부로 일관(`payload.py:47`, `client.py:118`), max_tokens=True 회귀도 lock됨. prose만 비대칭(78줄 vs 101줄). “정수”의 Python 해석이 bool 포함이냐 배제냐는 해석 의존적이나, 동작·검증이 일관하므로 **진정한 내부 모순(blocking)이 아닌 서술 명확성 gap**. non-blocking 분류에 동의. 다만 소유자 판단으로 78줄을 “bool이 아닌 1 이상의 정수”로 정리하면 traceability가 더 명확해진다.
- **O2**(`choices=[42]` 비-object choice 구조적 guard): `case 1(body=[])`가 동일 `_mapping` 헬퍼의 비-object 분기를 이미 lock하므로, 별도 case가 없어도 구조적 lock은 존재. non-blocking 분류에 동의.

### 메타검증자 verdict

**작업 AI의 “합격 승격” verdict는 타당하다.** load-bearing 근거:

1. F1 양방향 가드가 메타검증자 직접 변이로 양쪽 FAIL 재현됨(M1).
2. F2 13 branch 삼각검증이 메타검증자 독립 추적으로 빈 칸 없음 확인(M4). 추가 spec-silent 거부 잔존 없음(M6).
3. live smoke 6항목 메타검증자 독립 재실행으로 전부 일치(M5).
4. contract 자기 모순(blocking) 없음. O1은 서술 비대칭이지 동작 모순이 아님(M8).
5. 43/43 회귀 통과(메타검증자 재확인). green bar는 보조 증거.
6. 작업 AI가 CLAUDE.md 금지 패턴(future risk 재분류)을 위반하지 않음(M7).

메타검증자가 추가 발견한 것(M3: token=0 over-strict guard의 traceability 불투명, M2: max_tokens bool guard 변이 보강)은 모두 guard *존재*를 확인하는 방향이며, 합격을 가르는 blocking 조건이 아니다. M3의 traceability 보강(전용 `prompt_tokens=0` 수용 case)은 소유자 선택 과제로 기록한다.

## Hardening applied (소유자 결정, 2026-06-24)

메타검증 후 소유자 결정으로 비차단 traceability 보강 3종을 적용했다. verdict(합격)에는 영향이 없으며, 본 기록의 기존 findings·addendum prose는 수정하지 않았다.

- **M3 적용**: `tests/test_llama_provider_client.py`에 `test_zero_token_counts_are_accepted_as_valid` 추가. 명시 `prompt_tokens=0`/`completion_tokens=0` 수용을 고정해 token-count 하한(0)의 should-NOT-fire 경계 traceability를 명확화. 변이 증명(`value < 0 → value < 1`)으로 이 회귀가 경계를 pin함 확인.
- **O1 적용**: `docs/plans/llm-gateway.md:78`의 `max_tokens` precondition을 “bool이 아닌 1 이상의 정수”로 수정해 token-count(101줄)와 서술 대칭. 동작·검증 무변경.
- **O2 적용**: `test_malformed_success_response_is_not_accepted`의 malformed case에 `choices=[42]`(비-object choice) 추가. 동일 `_mapping` 헬퍼의 비-object 분기 traceability 명시.
- 회귀 카운트: 43 → **44**(M3 신규 +1. O2는 기존 parametrized 튜플에 case 추가라 카운트 변동 없음). `python3 -m unittest discover -s tests` → Ran 44 tests, OK.
