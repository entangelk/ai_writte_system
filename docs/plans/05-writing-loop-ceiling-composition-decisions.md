# 착수 결정 브리프 — Phase 5.10 B2b aggregate ceiling per-stage 합성 (Option A)

상태: `In progress — 2026-07-14 (오너 Option A 선택; 합성 코어 구현, 측정 메커니즘 확정 대기)`

관련 정본: `docs/system-contract-sot.md` v1.6.86, `05-writing-loop-benchmark-decisions.md`(B1~B4), `05-writing-loop-budget-decisions.md`(M1~M6), `flat-loop-gate.md` §Budget, `revise_gate.py`(loop 구조·metering), `docs/benchmarks/2026-07-14/writing_loop_b2b_q4_post_fence_fix.json`(재측정)

## 배경 — 조사 결론(work_log 2026-07-14 "Task 2 조사")

B2b 재측정(fence fix 후) 12 run 중 terminal_pass 1건만 success. 나머지 `unexpected_loop_trace`의 근본 원인:

1. **Writing Gate는 side-effect-free 독립 평가자(D3=A)** — loop routing은 오직 `last_gate.decision`(`revise_gate.py:387-512`). `request.instruction`은 reviser에만 전달되고(`:365,:410`) Gate에는 `original_request.instruction`으로 payload에만 들어가나 Gate 템플릿(`gate_prompt.py:18-29`)이 "Check only do_not_use/POV/continuity … Do not execute the recommendation"로 객관 평가를 강제한다. **prose로 Gate 경로를 steer할 수 없다** → 12 run 전체에서 `retrieve_more` **0회**.
2. fixture 3종 후보 텍스트가 context seed와 거의 동일 → Gate가 근거 부족을 못 찾아 pass 지향.
3. 12B Gate 노이즈: pass 대신 revise 과다(terminal_pass 2/3), 그 finding이 `_eligible_revision_finding` strict 조건 미달로 `not_eligible`.

즉 `unexpected_loop_trace`는 harness 버그가 아니라(`benchmark_writing_loop.py:86-87` 의도된 기록), **다단계 case를 실 12B로 prose steer한다는 B2b 전제**가 성립하지 않는 것이다. terminal_pass(3-stage 최저비용)만 재현 가능하나 이는 최악경로(10-stage max_structural) ceiling을 bound하지 못한다.

## Decision needed

production `WRITING_LOOP_MAX_TOTAL_TOKENS|MAX_WALL_CLOCK_MS` 기본값(현재 `None`/off)의 근거가 될 **최악경로 ceiling을 어떻게 도출하는가.** 실 loop 전체 경로를 모델이 걷지 못하므로 loop-level 직접 측정이 불가하다.

## Resolution (오너 결정 2026-07-14)

- **Option A 선택**: aggregate 예산은 각 stage provider usage의 **합**이고(`revise_gate.py:264` `add_usage`), 구조 상한이 stage 횟수를 bound한다. 따라서 **각 stage 비용을 개별 측정해 구조 상한만큼 최악경로를 해석적으로 합성**한다. 모델이 전체 loop를 걷게 만들 필요가 없어 Gate 독립성을 우회하고, 안전한 worst-case를 준다.
- 각하: **C**(terminal_pass만 = 최악경로 과소 bound, unsafe), **B**(fixture 재설계 = Gate 노이즈로 여전히 비결정적·고비용), **D**(결정적 Gate stub 강제 = A와 목적 동일하나 deployed HTTP 경계를 벗어남).

## 합성 공식 (코드 = 정본)

loop `metered()`가 합산하는 token 기여 stage = **revise, report, gate, retrieve_plan**. `context_search`는 `metered()` 밖 직접 호출(`revise_gate.py:474`)이라 aggregate **token에 미포함**(자체 ContextBudget 소유). `merge`는 in-process(0). wall-clock은 모든 실 호출 stage가 기여(context_search 포함, merge≈0).

`WritingLoopPolicy(max_revision_rounds=R, max_retrieval_rounds=T, max_gate_evaluations=G)`에서 최악경로 stage 횟수:

- `n_revise = R`, `n_report = R` (report는 매 revise 뒤 1회)
- `n_retrieve_plan = T`, `n_context_search = T`
- `n_gate = min(G, 1 + (R-1) + T)` — 초기 1 + 추가 revise마다 1 + retrieve마다 1, G로 cap

기본 정책(R=2,T=1,G=3): n_revise=2, n_report=2, n_gate=min(3,1+1+1)=3, n_retrieve_plan=1, n_context_search=1 → `max_structural_path` expected_stages(`benchmark_writing_loop.py:134`)와 정확히 일치.

- `ceiling_tokens = n_revise·revise_tok + n_report·report_tok + n_gate·gate_tok + n_retrieve_plan·retrieve_plan_tok`
- `ceiling_ms = n_revise·revise_ms + n_report·report_ms + n_gate·gate_ms + n_retrieve_plan·retrieve_plan_ms + n_context_search·context_search_ms`

per-stage 입력은 **보수적으로 관측 최댓값(또는 p95)**을 쓴다(각 stage의 repair 발생 case 포함). 이렇게 합성한 값은 raw 최악경로이며, 오너 B4에 따라 여기에 **여유율**을 얹어 default-on을 승인한다.

## 측정 메커니즘 sub-decision (확정 대기 — 작업자 추천 M-i)

per-stage 실 12B 비용(revise/report/gate/retrieve_plan/context_search token·ms)을 어떻게 얻는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **M-i. in-process per-stage 측정 script (추천)** | `diagnose_writing_gate.py`/`report.py` 선례대로 각 stage service를 production seam(`_default_*`)으로 instantiate, 실 gateway로 1회씩 호출해 `TokenUsage` + `perf_counter` 지연 기록. Mongo/audit/file write 0. | 선례 존재, audit 계약 무변, stage 격리가 명확, 합성 함수에 바로 투입. | 새 script + 5 stage fixture 배선 필요. deployed HTTP full-stack 지연은 미포함(순수 provider+orchestration 비용). |
| M-ii. persisted audit에 per-stage token/ms 노출 | 현 bodyless per-stage(P1=B: hash/fingerprint/pointer)에 token/ms 추가 후 deployed terminal_pass 1 run에서 개별 stage 비용 read. | full-stack 경계 유지, 기존 harness 재사용. | audit 계약/schema 변경(P1=B "bodyless" 결정 수정), SoT·회귀 확장. retrieve_plan/context_search는 terminal_pass에 없어 별도 retrieve-triggering run 필요(다시 Gate 독립성 문제). |

M-i 추천 이유: 로컬 1인 프로젝트 단계에서 audit 계약을 건드리지 않고(정본 보존) 선례 패턴을 재사용하며, Gate 독립성 문제(retrieve 경로를 실제로 유발해야 함)를 원천 회피한다. full-stack HTTP 지연은 wall-clock 여유율(B4)로 흡수한다.

## 이번 slice 범위 / Deferred

- **이번 slice(결정적, sandbox 내 검증 가능)**: 합성 코어 — `worst_case_stage_counts(policy)` + `compose_worst_case_ceiling(...)` 순수 함수 + 회귀. 측정 메커니즘과 무관하게 per-stage 비용 dict를 입력받아 ceiling을 산출.
- **Deferred(측정 메커니즘 확정 후)**: M-i per-stage 측정 script 구현(live 실행은 sandbox 밖 full-stack 필요). 실 수치 수집 → 합성 → B4 여유율/ default-on 오너 승인.
- **별도 트랙**: 12B Gate 과민 revise / not_eligible finding은 **Gate 프롬프트 판별 튜닝**(compare judge J1 튜닝의 Gate 판) — 이 ceiling slice와 독립. 신호만 기록.

## Follow-up considerations

- 합성 함수는 `WritingLoopPolicy` 상한 변경 시 자동으로 최악경로 카운트를 재도출해야 한다(상한이 env로 조정 가능하므로).
- `context_search`의 token은 aggregate에 미포함이나 wall-clock에는 포함 — 두 dimension을 분리해 합성.
- **불변식 lock 완료(검증 hardening#1)**: context_search token 제외는 순수 합성 함수 밖 `revise_gate.py`의 직접 호출 구조에 의존한다. 이를 (a) 호출 지점 교차참조 주석 + (b) loop 레벨 tripwire 테스트(`test_writing_loop_budget::test_context_search_usage_excluded_from_aggregate_tokens` — metered() 경유 mutation 시 total_tokens 22→1021로 bite)로 잠갔다. M-i script는 이 경계를 전제로 per-stage를 측정한다.
