# Verification Brief — LLM Gateway Slice 0.1~0.5

이 문서는 독립 검증자가 검증 범위를 잡기 위한 입력이다. 구현 작성자의 verdict나 verification record가 아니다.

## Subject

- 대상: portable LLM Gateway contract foundation, Slice 0.1~0.5
- source: 이 파일을 포함하는 Git commit
- 구현 환경: Python 3.12, 표준 라이브러리만 사용
- 외부 참조 provenance: `/mnt/d/devel/gemma4_12b` commit `485c4e2fe78323c408fcb64d08c2cdc9ec94f9e3`
- 외부 참조 repo 필요 여부: 필요 없음

## Canonical contract scope

다음 위치만 이번 slice의 canonical planning scope로 읽는다.

1. `docs/plans/implementation-plan.md`
   - `구현 진행 상태`
   - Slice 0.1~0.5
   - `테스트 계층`
2. `docs/plans/llm-gateway.md`
   - `Gateway 책임`
   - `개발 머신 독립성`
   - `내부 API 초안`의 현재 error literal
   - `테스트`
3. `docs/plans/gemma4-reuse.md`
   - `결론`
   - `참조 업데이트 정책`
   - `재사용 판정`
   - `검토 결과와 제한`

`docs/` 루트의 장문 설계는 ideation이며 이번 구현의 canonical contract가 아니다.

## Implementation scope

| Surface | Files |
|---|---|
| request/payload | `services/llm_gateway/app/payload.py` |
| provider protocol/fake | `services/llm_gateway/app/provider.py` |
| stable errors | `services/llm_gateway/app/errors.py` |
| transport/fake/status mapping | `services/llm_gateway/app/transport.py` |
| llama.cpp provider orchestration | `services/llm_gateway/app/client.py` |
| package boundary | `services/**/__init__.py` |
| regression tests | `tests/test_llm_*.py`, `tests/test_llama_provider_client.py` |

## Boundary matrix

| Contract branch | Expected behavior | Named regression surface |
|---|---|---|
| thinking false | `enable_thinking=false` | `test_thinking_false_disables_reasoning` |
| thinking true | `enable_thinking=true` | `test_thinking_true_enables_reasoning` |
| thinking omitted | configured default applies | `test_default_thinking_applies_when_request_omits_it` |
| explicit template override | explicit value wins | `test_explicit_template_setting_overrides_thinking_flag` |
| legacy think token | never injected | `test_legacy_think_token_is_not_injected` |
| streaming requested | rejected before transport | `test_streaming_is_rejected_until_gateway_supports_it` |
| fake normal calls | FIFO results and recorded requests | `test_results_are_fifo_and_requests_are_recorded` |
| fake provider error | exact queued error raised | `test_queued_error_is_raised_without_consuming_next_result` |
| fake exhausted | no fabricated response | `test_exhaustion_fails_instead_of_fabricating_a_response` |
| retryable/non-retryable errors | boolean preserved both ways | `test_retryable_error_envelope`, `test_non_retryable_error_envelope` |
| internal exception | cause not serialized | `test_underlying_exception_is_not_exposed_by_envelope` |
| timeout transport / 408 / 504 | retryable `provider_timeout` | transport mapping tests |
| connection / 5xx | retryable `provider_unavailable` | transport mapping tests |
| 429 | retryable `provider_overloaded` | transport/client tests |
| other 4xx | non-retryable `provider_request_rejected` | transport mapping tests |
| malformed provider body | non-retryable `provider_invalid_response` | `test_malformed_success_response_is_not_accepted` |
| valid 2xx completion | parsed generation and usage | `test_valid_response_is_parsed_and_payload_is_recorded` |
| valid body with 307 | not accepted as generation | `test_redirect_response_is_not_accepted_as_generation` |
| missing usage | valid, zero usage | `test_missing_usage_is_valid_and_defaults_to_zero` |

The verifier should confirm each assertion pins the public result/error surface rather than only an internal helper.

## Reproduction

Run from repository root:

```bash
python3 --version
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
git diff HEAD^ HEAD --check
git show --stat --oneline HEAD
```

Confirm no runtime/build dependency on the optional local reference checkout:

```bash
if rg -n '/mnt/d/devel/gemma4_12b|D:\\devel\\gemma4_12b' services tests; then
  exit 1
fi
```

Expected author-side baseline before commit: 30 tests passing. The independent verifier must rerun rather than trust this count.

## Required inspection questions

- Do `ProviderErrorCode` literals match all tests and plan text exactly?
- Can raw upstream body, transport exception, or local server address enter the public envelope?
- Does the provider accept only 2xx text-completion responses?
- Can malformed/empty/null response data be mistaken for success?
- Do fake provider/transport fail loudly when outcomes are exhausted?
- Does any production module import or open the external `gemma4_12b` path?
- Is the implementation still flat provider infrastructure, with no sub-agent/spawn behavior?

## Explicitly deferred / out of scope

- real HTTP library adapter
- FastAPI endpoint
- Docker/Compose and model weight
- live server/model smoke
- streaming
- tool-call response parsing and Agentic loop
- retry/backoff execution
- structured JSON schema generation
- MongoDB, ChromaDB, Elasticsearch

Absence of these items is not a defect in Slice 0.1~0.5. Claiming any of them is implemented would be a defect.
