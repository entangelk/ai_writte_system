# Verification Brief — LLM Gateway Slice 0.6 HTTPX Adapter

이 문서는 독립 검증자가 Slice 0.6의 mock HTTP 계약과 미완료 live 경계를 확인하기 위한 입력이다. 구현 작성자의 verdict가 아니다.

## Scope

- `services/llm_gateway/app/httpx_transport.py`
- `services/llm_gateway/requirements.txt`
- `tests/test_httpx_transport.py`
- `scripts/smoke_llm_provider.py`
- 기존 `client.py`, `transport.py`, `errors.py` 연결
- `docs/plans/implementation-plan.md` Slice 0.6
- `docs/plans/llm-gateway.md` HTTP adapter 상태

## Boundary matrix

| Branch | Expected | Regression |
|---|---|---|
| JSON POST success | path/payload 전달, decoded body 반환 | `test_success_posts_json_and_decodes_response` |
| httpx timeout | `TransportFailureKind.TIMEOUT` | `test_timeout_and_connection_errors_are_classified` |
| httpx connection error | `TransportFailureKind.CONNECTION` | same parametrized test |
| 2xx non-JSON | `INVALID_RESPONSE` | `test_non_json_success_is_invalid_response` |
| non-JSON 503 | status 보존, public body 비노출, `UNAVAILABLE` | `test_non_json_http_error_keeps_status_for_provider_mapping` |
| host proxy environment | default false, explicit true opt-in | `test_environment_proxy_policy_defaults_off_and_allows_opt_in` |
| client close | async context exit calls `aclose` | code inspection; httpx MockTransport tests complete without resource warning |

## Reproduction

```bash
python3 -c 'import httpx; print(httpx.__version__)'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_httpx_transport.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
git diff --check
```

Expected author-side baseline: HTTPX tests 5, full suite 42.

## Live command

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.smoke_llm_provider \
  --base-url http://192.168.1.29:9080 \
  --timeout 30
```

Expected successful content is `연결 확인 완료` with `finish_reason=stop`.

## Known observed limitation

- direct curl to `/health` and `/v1/chat/completions` succeeds.
- in the current Codex execution environment, Python `httpx` and stdlib `urllib` live calls both remained pending and were terminated.
- MockTransport tests pass.
- Therefore actual network traversal through `HttpxJsonTransport` is not yet verified.

The verifier should retry the module command from a normal shell or another Python execution environment. Do not mark live adapter verification complete based only on curl or mock tests.

→ 2026-06-24 독립 검증자가 별도 환경에서 actual adapter live smoke를 완료했다(응답 content `연결 확인 완료`, `finish_reason=stop`, usage 23/5/28). close-lifecycle 회귀까지 포함해 Mock 회귀는 5→6개로 보강됐다. 결과 기록: `docs/verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`.

## Out of scope

- retry/backoff
- streaming
- tool-call parsing
- FastAPI gateway endpoint
- Agentic loop
