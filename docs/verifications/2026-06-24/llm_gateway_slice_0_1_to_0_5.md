# 검증 기록 — LLM Gateway Slice 0.1~0.5

## Subject metadata

- 일자: 2026-06-24
- 요청자: 사용자(구현 AI가 아닌 독립 검증 요청)
- 검증자: 독립 검증 AI(Claude Code)
- 대상 slice/artifact: portable LLM Gateway contract foundation, Slice 0.1~0.5
  - payload, provider/fake, stable errors, transport/status mapping, fake-transport llama.cpp client
- canonical spec reference:
  - `docs/plans/implementation-plan.md` 상태 `Draft`, `구현 진행 상태` Slice 0.1~0.5
  - `docs/plans/llm-gateway.md` 상태 `Proposed`, `Gateway 책임`·`개발 머신 독립성`·`내부 API 초안` error literal·`테스트`
  - `docs/plans/gemma4-reuse.md` 상태 `Reviewed for planning`, `결론`·`참조 업데이트 정책`·`재사용 판정`·`검토 결과와 제한`
- source of the work being verified: commit `c87fec3 feat: add portable LLM provider foundation`(working tree clean, `git status --porcelain` 빈 출력). 단일 커밋에 20개 파일, +1310/-11.
- 구현 환경 확인: Python 3.12.3, 표준 라이브러리만 사용.

## Scope

검증 브리프(`docs/verification_briefs/2026-06-24/llm_gateway_slice_0_1_to_0_5.md`)가 지정한 canonical contract scope만 읽었고, `docs/` 루트 장문 설계(ideation)는 제외했다. 점검한 표면:

1. spec contract — `implementation-plan.md` Slice 0.1~0.5 prose + `llm-gateway.md` error literal + `gemma4-reuse.md` 재사용/독립성 조항
2. 구현 코드 — `services/llm_gateway/app/{payload,provider,errors,transport,client}.py`
3. regression tests — `tests/test_llm_{gateway_payload,provider,provider_errors,transport_mapping}.py`, `tests/test_llama_provider_client.py`
4. public envelope/schema — `ProviderError.to_envelope().to_dict()` wire shape, `ProviderErrorCode` literal
5. full test suite — `python3 -m unittest discover -s tests`
6. provenance/독립성 — 외부 `gemma4_12b` 경로/import 비의존 확인
7. 제외 범위 과대 주장 여부 — `CHANGELOG.md`, plan prose가 HTTP adapter/Agentic loop/live smoke를 구현된 것으로 서술하는지

## Methodology

1. **컨트랙트 스코핑 먼저**: 코드를 열기 전에 브리프와 세 plan 문서의 해당 섹션만 end-to-end로 읽어 boundary matrix(lock list)를 먼저 세웠다.
2. **경계 매트릭스 구축**: 브리프의 19개 contract branch + 각 slice별 prose에서 should-fire/should-NOT-fire 분기와 모든 literal(error code, retryable 방향, payload 키)을 추출했다.
3. **컨트랙트 자기 모순 점검**: plan prose(4 literal→5 literal 추가) ↔ `errors.py` ↔ `llm-gateway.md` literal ↔ 테스트 기대값을 교차 대조했다.
4. **코드 직접 검토**: 5개 모듈을 literal 단위로 1:1 대조. paraphrase를 허용하지 않았다.
5. **테스트 코드 감사(핵심)**: green bar와 별개로, 각 테스트가 (a) 실제로 public 표면을 고정하는지, (b) under-strict guard가 있는지, (c) over-strict guard가 있는지, (d) parametrize가 모든 경계값을 덮는지 확인했다.
6. **독립 재현**: 검증자가 직접 테스트/whitespace/commit/외부경로 grep을 재실행했다(아래 Reproduction).
7. 의심 방향: 양방향 회귀, spec-silent code-enforced 분기, 외부 의존, 제외 범위 과대 주장을 집중 점검했다.

사용한 정확한 명령은 Reproduction 섹션에 있다.

## Findings

### 1. spec contract — boundary matrix 추적

브리프의 19개 contract branch를 코드·테스트에 1:1 매핑했다. 빈 칸 없음.

| Contract branch | 기대 | 코드 위치 | 테스트(함수명) | 고정 여부 |
|---|---|---|---|---|
| thinking false | `enable_thinking=False` | `payload.py:61-67` | `test_thinking_false_disables_reasoning` | ✓ public payload |
| thinking true | `enable_thinking=True` | `payload.py:61-67` | `test_thinking_true_enables_reasoning` | ✓ |
| thinking omitted | configured default | `payload.py:61-65` | `test_default_thinking_applies_when_request_omits_it` | △ 기본값 False만(이슈 F1) |
| explicit template override | explicit 우선 | `payload.py:66-67`(setdefault) | `test_explicit_template_setting_overrides_thinking_flag` | ✓ |
| legacy think token | 미주입 | `payload.py:66-74` | `test_legacy_think_token_is_not_injected` | ✓ |
| stream=true | 조기 거절 | `payload.py:44-45` | `test_streaming_is_rejected_until_gateway_supports_it` | ✓ |
| fake FIFO 정상 | FIFO + request 기록 | `provider.py:55-66` | `test_results_are_fifo_and_requests_are_recorded` | ✓ |
| fake queued error | 다음 결과 보존 | `provider.py:63-65` | `test_queued_error_is_raised_without_consuming_next_result` | ✓ |
| fake exhausted | 응답 날조 금지 | `provider.py:60-61` | `test_exhaustion_fails_instead_of_fabricating_a_response` | ✓ |
| retryable envelope | boolean 보존 | `errors.py:36-60` | `test_retryable_error_envelope` | ✓ |
| non-retryable envelope | boolean 보존 | `errors.py:36-60` | `test_non_retryable_error_envelope` | ✓ |
| 내부 cause 비노출 | envelope에 미포함 | `errors.py:54-60` | `test_underlying_exception_is_not_exposed_by_envelope` | ✓ |
| 408/504 | retryable timeout | `transport.py:108-114` | `test_timeout_statuses_are_retryable` | ✓ |
| 429 | retryable overloaded | `transport.py:115-121` | `test_overload_status_is_retryable` + client `test_http_overload_maps_without_exposing_response_body` | ✓ |
| 5xx | retryable unavailable | `transport.py:129-134` | `test_server_errors_are_unavailable_and_retryable` | ✓ |
| 기타 4xx | non-retryable rejected | `transport.py:122-128` | `test_other_client_errors_are_rejected_and_not_retryable` | ✓ |
| malformed body | non-retryable invalid_response | `client.py:68-92` | `test_malformed_success_response_is_not_accepted` | ✓ |
| valid 2xx | generation+usage 파싱 | `client.py:68-102` | `test_valid_response_is_parsed_and_payload_is_recorded` | ✓ |
| 307(유효 body) | generation 거부 | `client.py:60-64` | `test_redirect_response_is_not_accepted_as_generation` | ✓ |
| usage 누락 | zero usage 허용 | `client.py:81-86` | `test_missing_usage_is_valid_and_defaults_to_zero` | ✓ |

### 2. 구현 코드 — literal 일치

- `errors.py:10-15` `ProviderErrorCode` 5 literal이 `provider_unavailable`/`provider_timeout`/`provider_overloaded`/`provider_invalid_response`/`provider_request_rejected`로 plan(`implementation-plan.md` Slice 0.3/0.4) 및 `llm-gateway.md:88-94`와 문자열 그대로 일치. paraphrase 없음. ✓
- `transport.py:77-96` transport failure 매핑: TIMEOUT→TIMEOUT(retryable), CONNECTION→UNAVAILABLE(retryable), INVALID_RESPONSE→INVALID_RESPONSE(non-retryable). ✓
- `transport.py:99-134` HTTP status 매핑 순서 점검: `<400` ValueError → `408/504` → `429` → `<500`(기타 4xx) → `else`(5xx). off-by-one 없음. 504가 408/504 분기에서 정확히 TIMEOUT으로 잡힘(`test_server_errors...`가 504를 의도적으로 제외한 것과 일치). ✓
- `client.py:43-66` provider 흐름: TransportFailure → `error_from_transport_failure`(`raise error from exc`), `>=400` → http mapper, `not 2xx`(3xx 등) → INVALID_RESPONSE. body는 mapper에 전달되지 않아 구조적으로 비노출. ✓
- `client.py:68-92` 파서: `model`/`finish_reason`은 문자열 필수, `choices`는 비어있지 않은 list, `message.content`는 문자열 필수 → `content=None`/empty choices/list body 모두 INVALID_RESPONSE. ✓
- `payload.py:61-67` `setdefault`로 explicit `chat_template_kwargs.enable_thinking`이 thinking flag보다 우선. 원본 request의 dict를 mutate하지 않음(`dict(...)` 복사). ✓

### 3. regression tests — 코드 감사

- 각 테스트는 internal helper가 아닌 public 표면(payload dict, envelope dict, `GenerationResult`, `ProviderError.code/.retryable`)을 단언한다. ✓
- 양방향 회귀:
  - thinking false/true 양쪽 각각 단언(`assertIs False`/`assertIs True`). ✓
  - retryable=True(timeout/overload/5xx/transport timeout·connection)와 retryable=False(기타 4xx/invalid_response) 양쪽 모두 단언. ✓
  - mapper misuse: `test_success_and_redirect_statuses_are_not_misclassified_as_errors`가 2xx/3xx를 ValueError로 거부(over-strict 방향). ✓
  - fake 날조 금지(`test_exhaustion...`), cause 비노출(`test_underlying_exception...`), upstream body 비노출(client `test_http_overload_maps_without_exposing_response_body`), 307 거부, malformed 거부 — 모두 should-NOT-fire 방향 고정. ✓
- `test_error_code_literals_are_stable`(`test_llm_provider_errors.py:14-24`)이 5 literal 집합을 정확히 고정. ✓
- `test_client_satisfies_provider_protocol`/`test_fake_satisfies_provider_protocol`이 구체 client/fake 모두 `LLMProvider` protocol 적합을 확인(Slice 0.2 “protocol 우선” 경계). ✓

### 4. public envelope/schema

- `ProviderError.to_envelope().to_dict()` → `{"error": {code, message, retryable, [provider]}}`. `test_retryable_error_envelope`/`test_non_retryable_error_envelope`가 wire shape을 정확히 고정. spec이 wire shape을 명시하지 않으나 테스트가 합리적 형태를 pin하므로 모순 아님. ✓
- envelope에는 `__cause__` 미포함(`errors.py:54-60`는 message만 사용). ✓

### 5. full test suite — 독립 재현

- `python3 -m unittest discover -s tests -v` → **Ran 30 tests, OK**(0 failure, 0 error). slice별 카운트 7(payload)+4(provider)+5(errors)+7(transport)+7(client) = 30이며 HANDOFF “기존 23 + client 7”과 일치. ✓(단, green bar는 보조 증거일 뿐 주 판단 근거가 아님 — 본 기록의 주 판단은 위 boundary matrix 추적과 테스트 코드 감사다.)

### 6. provenance/독립성

- `grep -rnE '/mnt/d/devel/gemma4_12b|D:\\devel\\gemma4_12b' services tests` → 경로 0건. `payload.py:3` docstring만 “gemma4_12b reference at commit 485c4e2”를 provenance로 언급(import/path 아님). `gemma4-reuse.md` “외부 경로는 runtime dependency가 아님” 정책과 일치. ✓

### 7. 제외 범위 과대 주장 여부

- `CHANGELOG.md:18`은 구현 표면만 서술(payload, provider/fake, stable errors, fake-transport client)하고 HTTP adapter/Agentic loop/live smoke를 구현된 것으로 주장하지 않음. `CHANGELOG.md:28`도 real-model smoke 보류 명시. plan 각 slice “아직 … 구현하지 않았다” 문구 일관. 브리프가 “제외 항목을 구현됐다고 주장하면 결함”으로 규정한 것에 위배 없음. ✓

## Issues / Risks

> 합격/불합격을 가르는 blocking 결함은 없다. 아래는 모두 저위험이며, F1·F2가 “조건부 합격”의 조건이다.

### F1 (low, contract branch의 parametrization gap — 조건)

경계 “thinking omitted → configured default applies”(`payload.py:61-65`)가 `test_default_thinking_applies_when_request_omits_it`에서 **`default_thinking=False` 한 값으로만** 단언된다. 대칭값 `default_thinking=True`(thinking 생략)는 어느 테스트에서도 고정되지 않았다.

- under-strict 검증: 만약 `else default_thinking`이 `else False`로 회귀하면(생략 시 기본값 무시), 현 테스트(default=False → 기대 False)는 그대로 통과해 회귀를 잡지 못한다.
- 영향: 낮음(로직이 단순하고 client 테스트는 `default_thinking=True`를 쓰되 항상 explicit thinking을 전달). 그러나 CLAUDE.md “parametrized cases cover every enumerated boundary value” 기준으로 default의 두 값 {True,False} 중 True가 미추적이므로, contract branch의 한 값을 lock하지 않은 것으로 본다.

권장: `default_thinking=True` + thinking 생략 → `enable_thinking is True`를 단언하는 1케이스 추가.

### F2 (low, spec-silent code-enforced rejection — contract gap, 조건)

코드가 contract가 명시하지 않은 입력을 거부한다. CLAUDE.md “Spec-silent-but-code-enforced is a contract gap”에 따라 계약 보강 요청으로 표출한다.

- `payload.py:46-47`: `max_tokens is not None and max_tokens < 1` → `ValueError`. (가장 호출자에게 노출될 가능성이 큼 — `max_tokens=0`이 응답 없음/프롬프트 카운트만 의미할 수 있는 API에서 문서화 없이 거부)
- `payload.py:42-43`: 빈 `messages` → `ValueError`.
- `payload.py:20-21`: 빈 message `role` → `ValueError`.
- `errors.py:47-48`: 빈 `ProviderError.message` → `ValueError`.
- `client.py:117-119`: token count가 bool/음수/비int → `ValueError` → INVALID_RESPONSE.

이 분기들에 대응하는 테스트도, plan prose 조항도 없다. 방어적 전제조건으로는 타당하지만, “코드가 거부하는 것을 계약이 다루지 않으므로” 둘 중 하나가 필요하다: (a) plan/payload contract에 precondition으로 명시 + 회귀 추가, 또는 (b) 해당 검사 완화. 위 중 `max_tokens<1`이 가장 실질적이다.

### F3 (정보, non-blocking)

`finish_reason`은 항상 존재하는 문자열이어야 하며(`client.py:79`, `GenerationResult.finish_reason: str`), 누락/null이면 INVALID_RESPONSE가 된다. 전용 negative test는 없으나 contract가 finish_reason을 파싱 대상 필수 필드로 다루므로 구조적으로 일치. low risk.

### F4 (정보, non-blocking)

`isinstance(x, LLMProvider)`(`provider.py:30-38`, runtime_checkable Protocol)는 `generate` 속성 존재만 검사하고 async 시그니처까지는 검증하지 않는다(Python 표준 제약). conformance는 구조적으로 보장되므로 현 단계에서 허용.

### F5 (정보, 비현실적)

`error_from_http_status`는 status ≥ 600(존재하지 않는 HTTP 상태)도 `else`로 UNAVAILABLE에 매핑한다. 실 HTTP에서 발생 불가하므로 영향 없음.

## Verdict

**조건부 합격(conditional pass).**

이유(load-bearing):

- 합격 측: canonical contract의 boundary matrix 19개 branch가 모두 코드와 테스트에 추적되었고(빈 칸 없음), 5개 error literal이 plan·`errors.py`·`llm-gateway.md`·테스트에서 문자열 그대로 일치하며 내부 모순이 없다. 모든 분류/거부 분기에 양방향 guard가 있고, 외부 `gemma4_12b` runtime 의존이 없으며, 제외 범위를 과대 주장하지 않는다. green bar(30/30)는 보조 증거로 이를 뒷받침한다. contract 자체는 건전하며 Slice 0.6 진행을 막는 정확성 결함이 없다.
- 조건: CLAUDE.md는 contract branch의 경계값 미추적(F1)과 spec-silent code-enforced 거부(F2)를 slice 종료 전에 해결해야 할 사안으로 본다. 아래 두 조건이 채워지면 합격으로 승격한다:
  1. **F1**: `default_thinking=True` + thinking 생략 케이스를 단언하는 회귀 1건 추가.
  2. **F2**: spec-silent 거부 분기(특히 `max_tokens<1`)의 계약 지위를 확정 — plan에 precondition 명시 + 회귀 추가, 또는 코드 완화.
- 명시적 거부: 이 두 조건을 “향후 보강 후보/후속 작업”으로 재분류하지 않는다. CLAUDE.md가 금지하는 “합격 + risk” 회피 패턴에 해당한다.

검증자는 본 slice가 contract적으로 건전하므로 F1·F2를 처리하면서 Slice 0.6(HTTP adapter)로 나아가는 것이 합리적이라 본다. 조건은 정확성 차단이 아니라 hardening이다.

## Outstanding items

- working tree: clean(commit `c87fec3` 이후 미커밋 변경 없음).
- F1/F2가 해결되면 본 기록의 verdict를 합격으로 갱신하거나 후속 검증으로 폐쇄해야 한다(소유자 결정).
- F1/F2 수정은 검증자가 임의로 반영하지 않았다 — 소유자가 방향(테스트 추가 vs 완화, 계약 명시 vs 제거)을 결정한다.
- Slice 0.6(실제 HTTP adapter)은 본 검증 범위 밖이며, 의존성/package 경계 확정이 선행 과제다(HANDOFF Next Tasks).
- real-model smoke는 여전히 GPU 실행 머신의 별도 gate이며 본 머신 완료 조건이 아니다.

## Reproduction

저장소 루트에서:

```bash
python3 --version                                          # 3.12.3 확인
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v   # Ran 30 tests, OK
git diff HEAD^ HEAD --check                                # whitespace 오류 0
git show --stat --oneline HEAD                             # c87fec3, 20 files
git status --porcelain                                     # 빈 출력(clean)

# 외부 경로 runtime 의존 부재 확인(경로 0건이 정상):
if grep -rnE '/mnt/d/devel/gemma4_12b|D:\\devel\\gemma4_12b' services tests; then exit 1; fi
# docstring provenance만 존재(import/path 아님):
grep -rnE 'gemma4_12b' services tests
```

F1 회귀 존재 여부는 휴리스틱으로 확인 가능하다 — `payload.py:61-65`의 `else default_thinking`을 `else False`로 일시 변경한 뒤 `test_default_thinking_applies_when_request_omits_it`만 실행하면 현 상태에서는 여전히 통과하는데, 이것이 곧 True 방향이 미추적됨을 보여준다(검증자는 코드를 수정하지 않고 읽기로만 확인).
