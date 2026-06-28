# Gemma benchmark harness (Slice 0 benchmark matrix) 검증

## Subject metadata

- 날짜: 2026-06-28
- 요청자: entangelk(사용자) — “다음작업 검증해줘”(commit `04950d4`)
- 검증자: Claude(독립 검증 세션, 작업 AI와 별개)
- 검증 대상 slice/artifact: commit `04950d4` “Add Gemma benchmark harness”
  - `scripts/benchmark_llm_provider.py`(신규, 278 lines)
  - `tests/test_llm_benchmark_script.py`(신규, fake-provider 단위 테스트 5건)
  - `docs/plans/llm-gateway.md`(benchmark 섹션 +7 lines), `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-06-28/work_log.md`
- canonical spec reference: `docs/plans/llm-gateway.md` §151 “Slice 0 benchmark matrix” / §166 “output tokens/sec와 전체 latency” / §174-177 “`scripts/benchmark_llm_provider.py`가 있다 … latency/token/error summary를 JSON으로 출력한다. 실제 budget/retry production 기본값은 이 report를 live Gemma/llama.cpp endpoint에서 생성한…” / §139 “정확한 sampling 값은 모델 benchmark로 확정하며 문서에서 미리 고정하지 않는다”; `HANDOFF.md:46` “budget/retry production 숫자 기본값은 Gemma Q4 benchmark 뒤에 확정”, Next Tasks #6 동일.
- 작업 출처: commit `04950d4`(branch `main`, committed). 작업 트리 clean(사용자 보고 + `git show --stat` 단일 커밋 확인).

## Scope

1. **계약(스펙)** — plan §151/§166/§174-177/§139와 HANDOFF가 이 harness를 요구하고 “production 숫자는 benchmark report 뒤”로 규정하는지.
2. **측정 로직** — `run_benchmark`의 latency / token usage / output tokens-per-sec / percentile / validation 산출이 first-principles로 정확한지.
3. **provider error 매핑** — `error_code`(`exc.code.value`)/`error_retryable`(`exc.retryable`)이 gateway 5종 literal(`errors.py`)과 일치하는지.
4. **회귀 테스트** — fake-provider 5건이 측정 로직을 under/over-strict로 고정하는지.
5. **public envelope** — 전체 discovery 카운트(221 통과 / 27 skip) 직접 재실행.

scope 밖(명시적): **live benchmark 실행** — 환경에 `LLAMA_BASE_URL`이 없어 live endpoint에서 harness를 돌리지 않았음(사용자 명시). 따라서 `_run_live`/`main`(CLI + HttpxJsonTransport + LlamaCppProvider 조립)은 이 slice에서 실행 검증 대상이 아님 → 비차단 O1. budget/retry production 숫자 결정은 다음 slice(Outstanding items).

## Methodology

- **스펙 스코핑**: `docs/plans/llm-gateway.md`에서 benchmark/token/latency/budget 키워드 grep, §139/§151/§166/§174-177/§191-194 확인.
- **gateway 일관성**: `services/llm_gateway/app/errors.py`의 `ProviderErrorCode` 값과 `provider.py`의 `TokenUsage.total_tokens`(property)·`FakeLLMProvider` 계약을 직독, benchmark가 의존하는 표면과 대조.
- **독립 재계산(first-principles)**: `_FakeClock`을 주입해 `run_benchmark`를 직접 호출, test 1/2 시나리오의 모든 측정값(latency·total·tps·prompt/comp·output_chars·finish·error_code·retryable)을 손계산 예상치와 비교. summary/percentile/validation 극단 케이스까지.
- **mutation 증명**: 같은 프로세스에서 `tests.test_llm_benchmark_script.run_benchmark` 심볼을 변이된 async 구현(`error_code`를 umbrella `provider_error`로 hardcode)으로 교체해 5건 전체 unittest를 구동, 어느 test가 FAIL하는지 확인 후 원상복구. **소스 파일 수정 없음**.
- **envelope 재실행**: `timeout 90 python3 -m unittest discover -s tests`.

정확한 명령은 **Reproduction**에 기록.

## Findings

### 1. 측정 로직 — first-principles 독립 재계산 일치

| 시나리오 | 측정값(독립 재계산) | 코드 출처 |
|---|---|---|
| success(test 1): clock[10,12], usage prompt4/comp6 | latency=2000.0, total=10, **tps=3.0(=6/2.0)**, prompt/comp=4/6, output_chars=2(`len("ok")`), finish=stop | `benchmark_llm_provider.py:147-163` |
| provider error(test 2): clock[1,1.25], TIMEOUT retryable | success=False, latency=250.0, **error_code=`provider_timeout`**(=`ProviderErrorCode.TIMEOUT.value`), retryable=True | `:132-144` |
| summary(2 succ + 1 fail) | runs/succ/fail=3/2/1, **p50=100·p95=300**, max_total=12, avg_tps=6.0, error_codes=[`provider_timeout`] | `:168-204` |
| percentile edge | empty→`None`, single[42.0] p95→42.0 | `:229-236` |
| validation | repeats=0→ValueError, warmups=-1→ValueError | `:118-121` |

- `tokens_per_second = completion_tokens / max(elapsed_ms/1000, 1e-9)`(`:158-160`) — 0-division 방지 포함, 정확.
- `total_tokens`는 `TokenUsage.total_tokens` property(prompt+completion, `provider.py:18`)에서 — benchmark가 재계산하지 않고 provider 표면을 신뢰. 일관.

### 2. gateway error literal 일관성 — 핵심 명세 충족

- benchmark가 `error_code = exc.code.value`(`:140`), `error_retryable = exc.retryable`(`:141`)로 매핑.
- `ProviderErrorCode`(`errors.py:10-15`) 5종 literal(`provider_unavailable`/`provider_timeout`/`provider_overloaded`/`provider_invalid_response`/`provider_request_rejected`)이 HANDOFF `:42` “Gateway 5 literal은 trace 보존”과 일치.
- 즉 benchmark report의 error_code가 gateway envelope과 동일 문자열 → trace 추적 일관. 이 slice 명세 “provider error literal/retryable 여부” 충족.

### 3. mutation 증명(양방향 guard)

`error_code`를 umbrella `provider_error`로 hardcode한 변이 구동 결과:

- **BASELINE**: 5건 통과.
- **MUTATION(error_code hardcode)**: `test_run_benchmark_records_provider_error_without_retrying` **FAIL**(`AssertionError: 'provider_error' != 'provider_timeout'`).
- → gateway literal 매핑(`exc.code.value`)이 test로 lock됨(under-strict 방향). restored.

(`tokens_per_second`/`total_tokens`/validation은 위 §1 독립 재계산 + test 1/3/4의 hardcoded assertion(3.0/10/ValueError)으로 cover되어 별도 mutation은 생략; 공식 변이 시 해당 assertion이 반드시 FAIL함은 자명.)

### 4. Envelope 재실행

`timeout 90 python3 -m unittest discover -s tests` → **Ran 221 tests … OK (skipped=27)**. HANDOFF·work_log 보고와 정확히 일치(이전 216 + 신규 5 = 221).

### 5. 계약(스펙) 일관성

- plan §174-177이 `scripts/benchmark_llm_provider.py`를 명시하고 “latency/token/error summary를 JSON으로 출력… production 기본값은 이 report를 live endpoint에서 생성한 뒤”로 규정 → 이 slice(harness)는 요구된 범위, production 숫자 미확정은 plan/HANDOFF가 명시한 다음 단계. **추측 금지 준수**.
- `DEFAULT_MODEL = "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"`(`:20`) ↔ HANDOFF `:36` QAT GGUF Q4_0 일치.

## Boundary matrix(lock list)

| 경계 | should-fire / should-NOT-fire | 회귀/검증 | 확인 |
|---|---|---|---|
| tokens_per_second = completion/elapsed | 6/2=3.0 | test 1 `:58` + 독립 A1 | 일치 |
| total_tokens = prompt+completion | 4+6=10 | test 1 `:57` + A1 | 일치 |
| latency = (now-started)*1000 | 2000 / 250 | test 1/2 + A1/A2 | 일치 |
| error_code = exc.code.value (gateway literal) | `provider_timeout` | test 2 `:93` + A2 + mutation B | lock됨 |
| error_retryable = exc.retryable | True | test 2 `:94` + A2 | 일치 |
| repeats/warmup validation | <1 / <0 거절 | test 3 `:96-120` + A5 | 일치 |
| summary p50/p95/max/avg_tps/error_codes | 100/300/12/6.0/[timeout] | test 4 `:124-145` + A3 | 일치 |
| build_report metadata+summary+runs | base_url/model/created_at | test 5 `:147-162` | 일치 |
| percentile empty/single | None / 42.0 | (직접) A4 | 일치 |

**빈 칸(blocking) 없음.** 단, 아래 O5(report 전체 run field 직렬화 중 output_chars/finish_reason/prompt/completion이 test에 **직접** assertion 없음 — total/tps는 간접 cover)는 비차단.

## Issues / Risks

비차단 관찰:

- **O1(live path `_run_live`/`main` untested)**: 테스트는 `run_benchmark`/`summarize_runs`/`build_report`만 cover. 실제 live 실행 경로(HttpxJsonTransport + LlamaCppProvider 조립 `:239-262`, argparse `:265-274`, asyncio.run + JSON 출력)는 이 slice에서 실행 검증 안 됨. `LLAMA_BASE_URL` 부재로 live 미실행은 사용자 명시이며 다음 slice의 검증 대상. `py_compile`은 통과했으나 **import/wiring bug 가능성이 live 실행 전까지 미확인**. 비차단(다음 slice에서 live report로 폐쇄 예정).
- **O2(warmup error handling)**: warmup 루프(`:126-127`)가 `try` 없이 `await provider.generate(request)`. warmup 중 `ProviderError` 발생 시 `run_benchmark` 전체가 crash(예외 전파). 테스트는 `warmups=0`만 사용해 이 경로 cover 안 됨. 의도적(warmup 실패 = benchmark 불가 → 중단)일 수 있으나, reproducible report 관점에서 warmup transient error가 전체 run을 깨뜨리는 것이 명시되지 않음. 비차단(정책 결정 권고: warmup 실패 시 skip/기록 여부).
- **O3(percentile 방식)**: `_percentile`(`:229-236`)이 `int(round((p/100)*(n-1)))` nearest-rank + Python banker's rounding. 2개 값에서 p50이 `values[0]`(`round(0.5)=0`). deterministic하나 표준 median 정의와 미세 차이. budget/retry 대략 통계용이므로 비차단(테스트가 p50=100·p95=300으로 의도 lock).
- **O4(report 스키마가 spec-silent)**: `build_report`의 정확한 field 구조(`created_at`/`base_url`/`latency_ms_p50`/`avg_output_tokens_per_second` 등)는 plan에 명시적 스키마가 아니라 code-enforced. plan §174-177은 “latency/token/error summary를 JSON”이라는 요구만. 다음 slice에서 이 report가 budget/retry 결정의 근거가 되므로, “어떤 측정 항목이 결정에 필요한가”를 plan에 한 줄 명시하면 future verifier가 guess하지 않음. 비차단 amendment 권고.
- **O5(run field 일부 미-assertion)**: `BenchmarkRun`의 `output_chars`/`finish_reason`/`prompt_tokens`/`completion_tokens`가 report(`to_dict`)에 직렬화되지만 5건 test 중 어느 것도 이 값을 **직접** assertion하지 않음(`prompt/completion`은 `total` assertion으로, `output_chars/finish_reason`은 어떤 test도 안 함). report fidelity 관점 gap이나, 이 필드들은 budget/retry 결정에 직접 쓰이지 않으므로 비차단. 보강(선택): report 직렬화 snapshot 테스트로 field 존재/값 lock.

정당(issue 아님): production budget/retry 숫자 미확정 — plan/HANDOFF가 “benchmark report 뒤 확정”으로 명시, 이 slice는 harness만 제공. 추측 금지 준수.

## Verdict

**합격.** plan §151/§166/§174-177이 요구한 benchmark harness가 측정 로직(latency·token usage·output tokens/sec·percentile·validation)을 first-principles 독립 재계산으로 정확히 산출하고, provider error 매핑(`exc.code.value`/`exc.retryable`)이 gateway 5종 literal과 일관하며, mutation 증명으로 error literal 매핑이 양방향 lock됨; envelope 221/27 재실행 일치. boundary matrix에 blocking 빈 칸 없음 — O1~O5는 모두 비차단(live path는 다음 slice / warmup 정책·percentile·report 스키마는 권고 / run field 미-assertion은 선택 보강). live benchmark report로 budget/retry production 기본값을 정하는 것은 다음 slice의 과제(Outstanding items).

## Outstanding items

- commit `04950d4`는 `main`에 이미 committed(작업 트리 clean). 추가 게시(push) 권한은 별도.
- **다음 slice(핵심)**: live Gemma/llama.cpp endpoint에서 `scripts/benchmark_llm_provider.py`를 실행해 report를 생성하고, 그 report를 근거로 budget/retry production 숫자 기본 한도 확정(HANDOFF Next Tasks #6 / plan §177·§191-194). 이때 O1(live path 실행 검증)도 자연 폐쇄.
- O2(warmup error 정책)·O4(report 스키마 plan 명시)는 소유자 판단 권고.

## Reproduction

```bash
# 1. 단위 테스트 + py_compile (작업 AI 보고 재현)
python3 -m unittest tests.test_llm_benchmark_script -v        # 5 통과
python3 -m py_compile scripts/benchmark_llm_provider.py tests/test_llm_benchmark_script.py

# 2. gateway literal 일관성 확인
grep -nE "TIMEOUT|provider_timeout|ProviderErrorCode" services/llm_gateway/app/errors.py

# 3. 측정 로직 독립 재계산 + error_code mutation 증명
python3 - <<'PY'
import asyncio, unittest
import scripts.benchmark_llm_provider as bench
import tests.test_llm_benchmark_script as testmod
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from services.llm_gateway.app.provider import FakeLLMProvider, GenerationResult, TokenUsage
class FC:
    def __init__(s,v): s._v=iter(v)
    def __call__(s): return next(s._v)
case = bench.BenchmarkCase(name="s",prompt="hi",max_tokens=32,temperature=0.0)
# success
p=FakeLLMProvider([GenerationResult(model="gemma",content="ok",finish_reason="stop",usage=TokenUsage(4,6))])
r=asyncio.run(bench.run_benchmark(p,model="gemma",cases=(case,),repeats=1,warmups=0,now=FC([10.0,12.0])))[0]
assert (r.latency_ms,r.total_tokens,r.tokens_per_second,r.output_chars,r.finish_reason)==(2000.0,10,3.0,2,"stop")
# error + literal consistency
p=FakeLLMProvider([ProviderError(code=ProviderErrorCode.TIMEOUT,message="x",retryable=True,provider="g")])
r=asyncio.run(bench.run_benchmark(p,model="gemma",cases=(case,),repeats=1,warmups=0,now=FC([1.0,1.25])))[0]
assert r.error_code==ProviderErrorCode.TIMEOUT.value=="provider_timeout" and not r.success and r.latency_ms==250.0
# percentile edge
assert bench._percentile([],50) is None and bench._percentile([42.0],95)==42.0
# mutation: error_code -> umbrella
ORIG=bench.run_benchmark
async def m(pr,*,model,cases=bench.BENCHMARK_CASES,repeats,warmups,now=bench.perf_counter):
    if repeats<1: raise ValueError("repeats must be >= 1")
    if warmups<0: raise ValueError("warmups must be >= 0")
    out=[]
    for c in cases:
        rq=c.to_request(model=model)
        for _ in range(warmups): await pr.generate(rq)
        for it in range(1,repeats+1):
            st=now()
            try: res=await pr.generate(rq)
            except bench.ProviderError as e:
                out.append(bench.BenchmarkRun(case=c.name,iteration=it,success=False,latency_ms=(now()-st)*1000,
                    error_code="provider_error",error_retryable=e.retryable,error_message=str(e))); continue
            em=(now()-st)*1000; es=max(em/1000,1e-9)
            out.append(bench.BenchmarkRun(case=c.name,iteration=it,success=True,latency_ms=em,
                prompt_tokens=res.usage.prompt_tokens,completion_tokens=res.usage.completion_tokens,
                total_tokens=res.usage.total_tokens,tokens_per_second=res.usage.completion_tokens/es,
                finish_reason=res.finish_reason,output_chars=len(res.content)))
    return out
def failed():
    r=unittest.TextTestRunner(verbosity=0).run(unittest.TestLoader().loadTestsFromModule(testmod))
    return [t.id().split('.')[-1] for t,_ in r.failures+r.errors]
print("baseline", failed())
testmod.run_benchmark=m; print("mutation", failed()); testmod.run_benchmark=ORIG
print("restored", testmod.run_benchmark is ORIG)
PY

# 4. envelope 재실행
timeout 90 python3 -m unittest discover -s tests   # 221 통과, 27 skip
```
