# Verification Brief — F1/F2 Closure and Direct Live Smoke

이 문서는 독립 검증자가 이전 조건부 합격의 조건 폐쇄와 direct live smoke를 재검증하기 위한 delta scope다. 구현 작성자의 verdict가 아니다.

## Prior verification

- 기록: `docs/verifications/2026-06-24/llm_gateway_slice_0_1_to_0_5.md`
- 대상 commit: `c87fec3`
- 기존 verdict: 조건부 합격
- 이번 delta 조건: F1(default thinking true 미고정), F2(spec-silent code-enforced rejection)

원 검증 기록은 수정하지 않는다. 이번 변경을 별도 working-tree/후속 commit delta로 검증한다.

## Canonical delta scope

- `docs/plans/llm-gateway.md`
  - `현재 request preconditions`
  - `현재 text-completion response preconditions`
- `docs/plans/implementation-plan.md`
  - Slice 0.1, Slice 0.5
  - `검증 조건 F1/F2 보강과 direct live smoke`
- `services/llm_gateway/app/{payload,errors,client}.py`
- `tests/test_llm_gateway_payload.py`
- `tests/test_llm_provider_errors.py`
- `tests/test_llama_provider_client.py`

## Delta boundary matrix

| Finding/branch | Required lock | Regression |
|---|---|---|
| F1 default false | omitted thinking follows false | `test_default_thinking_applies_when_request_omits_it` |
| F1 default true | omitted thinking follows true | `test_default_thinking_true_applies_when_request_omits_it` |
| messages empty | reject | `test_messages_must_not_be_empty` |
| role empty | reject | `test_message_role_must_not_be_empty` |
| max_tokens 0/-1/bool/float/string | reject | `test_max_tokens_must_be_positive_and_one_is_valid` |
| max_tokens 1 | accept and forward | same test, over-strict guard |
| default model empty | reject | `test_default_model_must_not_be_empty` |
| public error message empty | reject | `test_public_error_message_must_not_be_empty` |
| missing usage | accept as zero | `test_missing_usage_is_valid_and_defaults_to_zero` |
| token count negative/bool | invalid response | malformed response parametrized cases |
| token count string/float | invalid response | malformed response parametrized cases |
| model/content/finish not string | invalid response | malformed response parametrized cases |
| fake transport exhausted | no fabricated response | `test_exhaustion_fails_instead_of_fabricating_a_response` in transport tests |

The verifier should confirm the plan prose says exactly what the code rejects and that no code-enforced rejection in these surfaces remains spec-silent.

## Unit reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
git diff --check
```

Expected author-side baseline: 37 tests passing. Rerun independently.

## Direct live smoke target

Temporary local endpoint supplied by the owner:

```text
http://192.168.1.29:9080
```

Commands:

```bash
curl -sS --max-time 10 http://192.168.1.29:9080/health
curl -sS --max-time 10 http://192.168.1.29:9080/v1/models
curl -sS --max-time 120 http://192.168.1.29:9080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0","messages":[{"role":"user","content":"다음 문장을 그대로 답하세요: 연결 확인 완료"}],"chat_template_kwargs":{"enable_thinking":false},"temperature":0,"max_tokens":32,"stream":false}'
```

Author-observed result on 2026-06-24:

- health: `{"status":"ok"}`
- model: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, format GGUF, context 8192
- completion content: `연결 확인 완료`
- finish reason: `stop`
- usage: prompt 23, completion 5, total 28
- `reasoning_content`: absent with thinking disabled

The verifier must rerun rather than trust these observations.

## Explicit limitation

This is a direct llama.cpp curl smoke. Slice 0.6 actual HTTP adapter does not exist yet, so this does not verify `LlamaCppProvider` through a real network transport. Do not upgrade that deferred surface to implemented.
