# Verification Record — LLM Gateway Slice 0.6 (httpx JSON adapter)

## Subject metadata

- date: 2026-06-24
- requester: project owner (“작업 AI가 작업한 분에 대해서 검증하고 의심해줄래?”)
- verifier: Claude (independent verifier, distinct from the implementing worker)
- target slice: Slice 0.6 — httpx JSON adapter (`HttpxJsonTransport`)
- canonical spec reference:
  - `docs/plans/implementation-plan.md` § “구현 완료·live 검증 대기: Slice 0.6 — httpx JSON adapter” (lines 119–129)
  - `docs/plans/llm-gateway.md` “현재 text-completion response preconditions” (lines 95–117) 및 local endpoint proxy 정책 (line 45)
  - cross-ref: `docs/plans/implementation-plan.md` Slice 0.4 body 비노출 원칙 (lines 87–94) — line 124가 의존
- source of work being verified: working tree, uncommitted. 이전 보강분은 commit `4b4129b` (test: close LLM provider verification gaps)이며 본 검증은 그 이후의 Slice 0.6 변경에 한정한다.
- worker input brief: `docs/verification_briefs/2026-06-24/llm_gateway_slice_0_6_httpx.md` (이 파일은 검증 *입력*이며, 본 파일은 독립 *검증 기록*이다.)

## Scope

독립 검증 대상 표면:

1. 구현 코드 — `services/llm_gateway/app/httpx_transport.py`
2. 의존성 선언 — `services/llm_gateway/requirements.txt`
3. 회귀 테스트 — `tests/test_httpx_transport.py`
4. live smoke 모듈 — `scripts/smoke_llm_provider.py` (및 `scripts/__init__.py`)
5. 계약 wiring — `services/llm_gateway/app/transport.py`, `client.py`, `errors.py` (adapter가 연결되는 안정 계약)
6. 계약 문서 — implementation-plan.md Slice 0.6, llm-gateway.md response preconditions / adapter 상태
7. 전체 테스트 스위트 (회색 막대와 계약 위반을 구분)
8. live adapter smoke — 실제 endpoint `http://192.168.1.29:9080` 경유

## Methodology

각 표면에 대한 검증 방법과 정확한 명령. 이 섹션만으로 재현 가능해야 한다.

- 계약 스코프 핀: implementation-plan.md:119–129 와 llm-gateway.md:95–117 을 end-to-end로 읽고 경계 매트릭스(should-fire / should-NOT-fire + literal)를 먼저 구축한 뒤 코드를 열었다.
- 계약 자기 모순 점검: trust_env 기본값·`httpx>=0.28,<1`·2xx 범위·non-JSON 처리가 plan ↔ llm-gateway 양쪽에서 일치하는지 교차 확인.
- 예외 계층 가정 독립 검증: `python3` 인터프리터에서 `issubclass(httpx.TimeoutException, httpx.RequestError)` 등 4가지를 직접 평가 (`except` 순서가 올바른지의 load-bearing 사실).
- 테스트 감사: 각 신규 테스트를 읽고 (a) assertion이 계약을 pin 하는지 (b) under-strict/over-strict 양방향 가드 존재 여부 (c) subtest가 열거 경계를 모두覆盖 하는지 확인. 회색 막대와 분리.
- 정적 실행:
  ```bash
  python3 -c 'import httpx; print(httpx.__version__)'          # → 0.28.1
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_httpx_transport -v
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
  git diff --check
  ```
- live adapter smoke (brief가 미완료로 남긴 항목을 본 검증자가 이 환경에서 재실행):
  ```bash
  timeout 8 curl -s --max-time 5 http://192.168.1.29:9080/health
  # httpx 직접 GET /health (trust_env=False, timeout=5)
  PYTHONDONTWRITEBYTECODE=1 timeout 90 python3 -m scripts.smoke_llm_provider \
    --base-url http://192.168.1.29:9080 --timeout 30
  ```
- pattern sweep: `grep -rn "httpx\|HttpxJsonTransport\|trust_env" services tests scripts` 로 adapter 결합이 새 파일 밖으로 누수됐는지 점검.

## Findings

### F1. 구현 코드 (`httpx_transport.py`) — 계약 대비 정합

- 의존성 literal: `httpx>=0.28,<1` (`requirements.txt:1`) ≡ plan:121, llm-gateway:117. 설치 버전 0.28.1로 범위 만족.
- async POST + JSON decode + close/context manager: `httpx_transport.py:37-61` (post_json), `:28-35` (`__aenter__`/`__aexit__`/`aclose`). plan:122 부합.
- timeout/connection 매핑 (`httpx_transport.py:44-47`): `httpx.TimeoutException`을 먼저, `httpx.RequestError`를 다음으로 잡는다. 순서가 유효하려면 `TimeoutException ⊂ RequestError` 여야 하고, 이를 독립 검증했다(F4).
- non-JSON 처리 (`httpx_transport.py:49-56`): 2xx면 `INVALID_RESPONSE` raise, 그 외(4xx/5xx 포함)는 `body=None` 후 status 보존. plan:124 부합.
- trust_env 기본값 False (`httpx_transport.py:18`, `:24`). plan:125, llm-gateway:45 부합.
- smoke 모듈이 URL을 인자로 받는다 (`scripts/smoke_llm_provider.py:55-61`, `--base-url` required). plan:127 부합.

### F2. 경계 매트릭스 — 양방향 lock 현황

| # | 분기 | 방향 | 코드 | 회귀 테스트 | 양방향 |
|---|---|---|---|---|---|
| 1 | valid JSON 2xx → JsonResponse | should-fire(반환) | `httpx_transport.py:43-50,58-61` | `test_success_posts_json_and_decodes_response` | 예(raise 안 함 검증) |
| 2 | httpx timeout → TIMEOUT | should-fire | `:44-45` | `test_timeout_and_connection...` ReadTimeout subtest | 예(+CONNECTION 아님) |
| 3 | httpx conn err → CONNECTION | should-fire | `:46-47` | 동 테스트 ConnectError subtest | 예(+TIMEOUT 아님) |
| 4 | 2xx non-JSON → INVALID_RESPONSE | should-fire | `:49-55` | `test_non_json_success_is_invalid_response` | 예 |
| 5 | non-JSON 5xx → transport는 INVALID raise 금지 | should-NOT-fire | `:52-56`(else→None) | `test_non_json_http_error_keeps_status_for_provider_mapping` (UNAVAILABLE 기대) | 예(아래 주석) |
| 6 | trust_env 기본 False | should-fire | `:18,24` | proxy subtest(None→False) | 예 |
| 7 | trust_env 명시 True opt-in | should-fire | `:24` | proxy subtest(True→True) | 예 |
| 8 | context-manager close | lifecycle | `:28-35` | `test_context_manager_closes_the_httpx_client`(검증 후 보강) | 예(I2 해결) |

분기 #5 over-strict 가드: transport가 5xx non-JSON을 잘못 `INVALID_RESPONSE`로 raise하면 `client.py:48-53`이 이를 잡아 `provider_invalid_response`로 변환한다. 테스트는 `ProviderErrorCode.UNAVAILABLE`을 기대(`test_httpx_transport.py:126`)하므로, 잘못된 분류가 들어가면 테스트가 실패한다. 즉 양방향이 살아 있다.

분기 #2/#3 over-strict 가드(`except` 순서): 누군가 `RequestError`를 먼저 잡거나 `TimeoutException` 분기를 제거하면 ReadTimeout이 CONNECTION으로 빠진다. 테스트는 TIMEOUT을 기대(`:60-61,83`)하므로 실패. 순서 경계가 lock 돼 있다.

### F3. 테스트 스위트 — 독립 재실행

- HTTPX 테스트: 검증 시점 5개 메서드 전부 ok. 검증에서 발견한 I2(close lifecycle 미테스트)를 보강해 6번째 양방향 회귀를 추가했고 6개 전부 ok.
- 전체 discover: 검증 시점 **42 tests OK**; I2 보강 후 **43 tests OK**. worker의 “42개 통과” 클레임은 회색 막대가 아닌 재실행으로 재도출.
- `git diff --check` clean.

### F4. httpx 예외 계층 가정 — load-bearing 사실 독립 검증

`except` 순서(`:44-47`)가 올바르려면 다음이 모두 참이어야 한다. 인터프리터에서 직접 평가:

```
TimeoutException is RequestError subclass: True
ReadTimeout is TimeoutException subclass: True
ConnectError is RequestError subclass: True
ConnectError is TimeoutException subclass: False
Response.json raises: JSONDecodeError | is ValueError: True
```

- `TimeoutException ⊂ RequestError` 이므로 timeout을 먼저 잡는 순서가 필수이며 정확하다.
- `ConnectError ⊄ TimeoutException` 이므로 CONNECTION으로 낙하가 정확하다.
- `Response.json()`이 `ValueError` subclass를 raise하므로 `except ValueError`(`:51`)가 non-JSON을 정확히 포착한다.

이 네 가지는 계약 분기 #2/#3/#4가 회색 막대가 아니라 진짜로 계약을 지키고 있음을 보장하는 load-bearing 사실이다.

### F5. live adapter smoke — 본 검증자가 완료 (brief의 미완료 항목 해소)

worker brief(line 48-55)는 “현재 실행 환경에서 Python httpx/urllib socket이 대기해 actual adapter live smoke는 미완료”라고 기록하고, 검증자에게 “다른 Python 환경에서 재검증하라”고 요청했다. **본 검증 환경에서는 httpx live 호출이 정상 동작한다.**

- `curl /health` → `200 {"status":"ok"}` (exit 0)
- httpx `AsyncClient(trust_env=False, timeout=5)` GET `/health` → `200 {"status":"ok"}` (exit 0). 대기 현상 없음.
- 실제 adapter 경유 smoke:
  ```
  PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.smoke_llm_provider \
    --base-url http://192.168.1.29:9080 --timeout 30
  → {"model":"google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0",
     "content":"연결 확인 완료","finish_reason":"stop",
     "usage":{"prompt_tokens":23,"completion_tokens":5,"total_tokens":28}}
  ```
- brief가 예측한 성공 content(`연결 확인 완료`, `finish_reason=stop`)과 정확히 일치한다.

이로써 `HttpxJsonTransport`의 실제 네트워크 순회(async POST → JSON decode → provider parse → GenerationResult)가 end-to-end로 검증됐다. llm-gateway.md:210 “httpx JSON adapter와 mock HTTP contract — 구현 완료, **live adapter smoke 대기**” 의 “대기” 상태는 본 환경 기준으로 해소됐다.

### F6. surgical / 결합 누수 점검

`grep httpx|HttpxJsonTransport|trust_env` 결과 새 코드 3개 파일(`httpx_transport.py`, `test_httpx_transport.py`, `smoke_llm_provider.py`) 외에 httpx 참조가 없다. adapter가 기존 안정 계약(`JsonTransport` protocol, `TransportFailure`, `error_from_*`) 밖으로 새 의존성을 누출하지 않는다.

## Issues / Risks

- **I1 [상태 정정 — 중요, 코드 결함 아님]**: brief·plan·HANDOFF 가 live adapter smoke를 미완료로 표기했으나(impl-plan.md:129, llm-gateway.md:117/210/226), 본 검증 환경에서는 httpx live 호출이 성공했고 실제 adapter smoke를 완료했다(F5). 코드 결함이 아니라 worker 실행 환경의 제약이었으며, 소유자가 이 환경의 결과를 canonical로 받아들이면 관련 문서의 “live 대기/미완료” 표기를 “완료”로 갱신해야 한다. 이 결정은 소유자에게 달렸다(Outstanding 참조).
- **I2 [경미 → 해결]**: context-manager close lifecycle(`httpx_transport.py:28-35`)에 대한 회귀 테스트가 없었다(검증 시점). 이는 should/should-NOT-fire 조건 분기가 아니라 순수 위임이라 본 가이드의 양방향 가드 결격(차단 사유)에는 해당하지 않았다. **해결**: `async with` 종료 전후 `is_closed`를 검증하는 양방향 회귀 `test_context_manager_closes_the_httpx_client`를 추가했고 43 tests green.
- **I3 [양성, finding 아님]**: transport는 모든 non-2xx에 대해 body를 버린다(`:52` `if 200 <= response.status_code < 300`). plan:124 는 “4xx/5xx”라고만 쓴다. 3xx의 경우 client.py가 자체적으로 거부하며 Slice 0.5 `test_redirect_response_is_not_accepted_as_generation`이 이를 lock하므로 관측 가능한 계약 차이가 없다. 문서가 좁게 쓴 것뿐, 코드의 일반화는 무해하다.

## Verdict

**합격(PASS).**

사유(load-bearing):
- Slice 0.6 계약 deliverable 7항 전부 코드와 일치(F1).
- 조건 분기 경계 #1–#7 이 양방향으로 lock 됐고, 단 하나의 비조건 lifecycle(close)만 테스트 누락(I2, 비차단).
- `except` 순서 등 load-bearing httpx 예외 계층 가정을 인터프리터에서 독립 검증(F4) — 회색 막대가 아님.
- 검증 시점 42/42 + 5/5, I2 보강 후 43/43 + 6/6 테스트 통과(F3).
- **brief가 미완료로 남긴 live adapter smoke를 본 환경에서 완료(F5)**, 예측 성공 content와 정확히 일치.

I2(close lifecycle 테스트)는 비차단 권고이고, I1·I3은 코드 결함이 아닌 상태/문서 표기 문제이므로 합격을 흔들지 않는다.

## Outstanding items

- (검증 후 해소) Slice 0.6 코드는 커밋됐고 plan/HANDOFF/CHANGELOG/brief의 “live 대기/미완료” 표기를 “완료”로 갱신했다(소유자가 본 검증 환경 결과를 canonical로 채택). I2 close lifecycle 회귀도 보강 완료.
- 남은 Slice 0 영역: tool-call response parsing 미구현, 전체 model evaluation은 GPU/Python 실행 환경의 배포 전 gate.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
python3 -c 'import httpx; print(httpx.__version__)'                               # 0.28.1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_httpx_transport -v       # 6 ok
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v                # 43 ok
git diff --check                                                                  # clean

# httpx 예외 계층 가정 (F4)
python3 - <<'PY'
import httpx
print(issubclass(httpx.TimeoutException, httpx.RequestError))
print(issubclass(httpx.ReadTimeout, httpx.TimeoutException))
print(issubclass(httpx.ConnectError, httpx.RequestError))
print(issubclass(httpx.ConnectError, httpx.TimeoutException))
PY

# live adapter smoke (F5) — Python socket이 동작하는 환경에서만
timeout 8 curl -s --max-time 5 http://192.168.1.29:9080/health
PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.smoke_llm_provider \
  --base-url http://192.168.1.29:9080 --timeout 30
# 기대: content="연결 확인 완료", finish_reason="stop"
```
