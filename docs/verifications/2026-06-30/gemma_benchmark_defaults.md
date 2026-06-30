# Gemma Q4 benchmark defaults 독립 검증

## Subject metadata

- 검증일: 2026-06-30
- 요청자: entangelk(사용자, "다음작업 검증해줘" — 2개 커밋 중 `d4c2438`)
- 검증자: Claude(독립 검증)
- 검증 대상 slice/artifact: commit `d4c2438` "Record Gemma benchmark defaults" — live benchmark report, SoT v1.6.13, flat-loop-gate.md production budget/retry 기본값, benchmark script 직접 실행 import 보강
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.13(changelog `docs/system-contract-sot.md:36`, 추적표 `:375`)
  - `docs/plans/flat-loop-gate.md` §Budget "production 기본값"(`:113-123`)
  - `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`
- 검증 대상 작업 출처: commit `d4c2438`(HEAD). worktree clean, `git diff --check` clean.

## Scope

1. **benchmark script 직접 실행 보강**: `sys.path` import fix 정확성 + 회귀(subprocess `--help`).
2. **benchmark report 진정성**: JSON summary ↔ runs 배열 내부 일치, 그리고 summary가 스크립트 산출 방식(percentile)과 일치하는지(위조/수동 편집 여부).
3. **계약 측정치 grounding**: flat-loop-gate.md에 적힌 p95/max token이 JSON에서 재도출한 값과 일치하는지(재계산, not trust).
4. **budget 기본값 합리성**: 3 profile 기본값이 measured 수치에 근거하는지, §line-89 검증 규칙을 만족하는지.
5. **default 소유권**: 숫자 기본값이 code에 wiring됐는지 vs doc 소유(slice 범위 부합성).

## Methodology

1. `git show d4c2438`로 script/test/계약 변경분 독해.
2. JSON의 9개 run(3 case × 3 repeat)에서 p50/p95/max token/avg tok/s를 **직접 재계산**해 JSON summary 및 계약 문장과 대조.
3. 스크립트 `_percentile`(`scripts/benchmark_llm_provider.py:249-254`) 산출식을 읽어 summary가 스크립트 출력과 일치하는지(=보고서가 스크립트 산물인지) 확인.
4. `python3 scripts/benchmark_llm_provider.py --help` 직접 실행으로 import fix 검증.
5. `grep`으로 task profile 이름·숫자 기본값이 code에 wiring됐는지(`registry.py`, `budget.py`) 확인.
6. 재실행: `tests.test_llm_benchmark_script`(8), `unittest discover tests`(314, skip 35).

## Findings

### F0. 재실행 — 작업자 주장과 일치

- `python3 scripts/benchmark_llm_provider.py --help` → returncode 0, `--base-url` 옵션 표시. import fix 정상.
- `tests.test_llm_benchmark_script`: **8 passed**(7→+1).
- `unittest discover tests`: **314 passed, skipped=35**.
- `git diff --check` clean, worktree clean.

### F1. benchmark script 직접 실행 import fix — 정확

`scripts/benchmark_llm_provider.py:14-15` 추가: `if __package__ in {None, ""}: sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`. 직접 `python3 scripts/...` 실행 시 `__package__`가 빈 문자열/None이어서 repo root가 sys.path에 없던 문제를 보정한다. 회귀 `test_script_file_path_invocation_can_import_repo_packages`(`tests/test_llm_benchmark_script.py`)가 subprocess로 `--help`를 돌려 `returncode==0`·`--base-url` 포함을 lock. under-strict(import 실패 시 회귀 붉어짐) 확인.

### F2. benchmark report 진정성 — 내부 일치 + 스크립트 산출 방식과 일치(위조 아님)

9개 run을 재계산(검증자 직접):

| case | latencies(ms) | 정렬 | p50=sorted[1] | p95=sorted[2]=max | max token | avg tok/s |
|---|---|---|---|---|---|---|
| short_smoke | 1476.055, 1558.563, 1470.646 | 1470.646, 1476.055, 1558.563 | 1476.055 ✓ | 1558.563 ✓ | 28 ✓ | (3.387+3.208+3.4)/3=3.332 ✓ |
| json_extraction | 8463.877, 8700.207, 8440.801 | 8440.801, 8463.877, 8700.207 | 8463.877 ✓ | 8700.207 ✓ | 125 ✓ | (6.026+5.862+6.042)/3=5.977 ✓ |
| continue_scene | 54534.971, 49307.981, 57155.953 | 49307.981, 54534.971, 57155.953 | 54534.971 ✓ | 57155.953 ✓ | max(392,361,407)=407 ✓ | (6.198+6.226+6.176)/3=6.2 ✓ |

JSON `summary`의 p50/p95/max_total_tokens/avg_output_tokens_per_second가 runs 배열에서 재도출한 값과 한 치 오차 없이 일치. 또한 `_percentile`(`:249-254`)이 `int(round((p/100)*(n-1)))` 인덱스 방식이라 n=3일 때 p95=sorted[2]=max, p50=sorted[1]=median이 되는데, summary가 정확히 이를 따른다. 즉 report는 수동 날조가 아니라 스크립트 산출 결과와 일치. failures=0(9/9 success)도 확인.

### F3. 계약 측정치 grounding — flat-loop-gate.md 문장이 JSON과 정확히 부합

flat-loop-gate.md `:113-123`의 측정 요약 vs JSON:
- `short_smoke` p95 1.56s / max 28 → 1558.563ms=**1.56s** ✓ / 28 ✓
- `json_extraction` p95 8.70s / max 125 → 8700.207ms=**8.70s** ✓ / 125 ✓
- `continue_scene` p95 57.16s / max 407 → 57155.953ms=**57.16s** ✓ / 407 ✓
- 전체 failure 0 → 9/9 success ✓

"보고된 숫자를 아무도 재계산하지 않았다" 함정 없음. 계약 문장이 실제 report에 근거.

### F4. budget 기본값 합리성 — writing 2배 검증 가능, §line-89 규칙 만족

flat-loop-gate.md `:119-121` 표:

| profile | iter | wall_ms | tokens | tool_calls | rep_calls | prov_retry | tool_retry |
|---|---|---|---|---|---|---|---|
| analysis_compare | 2 | 45000 | 1024 | 5 | 2 | 1 | 1 |
| context_search | 3 | 60000 | 1536 | 8 | 2 | 1 | 1 |
| writing_generate | 1 | 120000 | 1024 | 0 | 0 | 1 | 0 |

- **writing_generate "약 2배 wall-clock" 검증**: continue_scene p95 57.16s × 2 ≈ 114.3s → ceiling 120000ms(120s). 부합. tool-free(tool_calls=0, tool_retry=0)도 writing 계약과 일치.
- **§line-89 검증 규칙 만족**: max_iterations/wall_ms/tokens 모두 ≥1; tool profile(analysis/context)의 tool_calls·repeated_calls ≥1; writing만 0 허용. 전부 부합.
- **analysis_compare**: json_extraction p95 8.70s/125 tokens 기준 provider 2회(×8.70≈17.4s)+read-only tool 여유 → 45s/1024 ceiling 합리적.
- 근거 문장에 명시된 measured 수치(8.70s/125, 57.16s/407)는 F3에서 검증한 값과 동일.

### F5. 숫자 기본값 소유권 — doc 소유, slice 범위 부합

- task profile **이름**은 code에 있음(`registry.py:35-37` ANALYSIS_COMPARE/CONTEXT_SEARCH/WRITING_GENERATE).
- **숫자 기본값**은 `BudgetPolicy`(`budget.py:69`)가 생성자에서 명시적 주입만 받고 기본 상수로 wiring하지 않음. 즉 flat-loop-gate.md가 기본값을 "소유"(SoT `:36`, `:375`). 이는 slice가 "Record ... defaults"인 점, 그리고 domain tool-call branch 미구현 상태와 일치. 결함 아님.

## Issues / Risks

- **[비차단] context_search 근거 문장의 수치 비일관**: `flat-loop-gate.md:120` 근거 "measured extraction보다 작은 token ceiling 유지". 그러나 context_search token ceiling=1536은 measured extraction(json_extraction) max=125는 물론, 다른 두 profile(1024)보다도 **크다**. "measured extraction보다 작다"는 어떤 해석으로도 성립하지 않는다. 숫자 1536 자체(multi-step search용 token 여유)는 합리적이나, 근거 문장만 수치와 모순. 권고: 문장 정정(예 "measured extraction에 multi-step 조회 여유를 둔 token ceiling"). boundary/rule/값 정합성에는 영향 없으므로 비차단.
- **[비차단] `resolution.py:76` 주석 신선도**: "numeric defaults deferred to the Gemma Q4 benchmark" — benchmark는 이번에 완료됐고 기본값은 flat-loop-gate.md에 확정됨. 주석의 논점(이 함수는 숫자 기본값과 무관)은 유효하나 "deferred" 시제가 stale. 권고: "deferred to" → "owned by flat-loop-gate.md after the ... benchmark" 등으로 정정. 동작 영향 없음.
- **[정보] context_search·analysis_compare의 tool latency는 미측정**: benchmark 3 case에 search/extraction-with-tools가 없고, flat-loop-gate.md `:123`이 이를 명시적으로 인정("tool latency가 들어온 뒤 별도 benchmark로 조정"). honest한 한계 표기이므로 결함 아님.

## Verdict

**합격(pass)** — script import fix와 회귀가 적절하고, benchmark report가 스크립트 산출 방식과 일치(위조 아님)하며 내부 수치가 정합하고, flat-loop-gate.md의 측정치가 JSON에서 재도출한 값과 정확히 부합하고, writing_generate 2배 wall-clock 등 기본값이 측정에 근거하며 §line-89 규칙을 만족한다. 숫자 기본값의 doc 소유는 slice 범위에 부합. 2건의 비차단 문구/주석 정정 권고(context_search 근거 문장, resolution.py stale 주석)가 있으나 값/동작/계약 정합성에 영향 없다.

## Outstanding items

- 없음(본 slice 한정). 실제 budget 기본값 code wiring과 domain tool-call branch는 후속 slice.
- 비차단 권고 2건(F5 Issues)은 후속 문서 정리 시 반영 권장.

## Reproduction

```bash
git show d4c2438 -- scripts/benchmark_llm_provider.py tests/test_llm_benchmark_script.py docs/plans/flat-loop-gate.md
python3 scripts/benchmark_llm_provider.py --help                    # returncode 0, --base-url
python3 -m unittest tests.test_llm_benchmark_script                 # 8 passed
python3 -m unittest discover tests                                  # 314, skip 35
# report 진정성 재계산(JSON summary ↔ runs)
python3 -c "import json,statistics as s; d=json.load(open('docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json')); [print(c, sorted(r['latency_ms'] for r in d['runs'] if r['case']==c), max(r['total_tokens'] for r in d['runs'] if r['case']==c)) for c in ('short_smoke','json_extraction','continue_scene')]"
```
