# 독립 검증 — Phase 5.1 Writing 생성 (SoT v1.6.68)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("다음작업 검증해줘. … Phase 5.1 Writing 생성 (SoT v1.6.68)").
- **Verifier**: 독립 세션(검증자).
- **Target slice**: Phase 5 첫 slice — 신규 `writing/` 패키지(`models`·`prompt`·`service`) + `POST /projects/{id}/writing/generate` 오케스트레이션(context_search→generate).
- **Canonical spec reference**: `docs/plans/05-writing-generation-decisions.md`(Resolved, Q1=생성만·Q2=평문 프로즈, D3~D7 파생, 매트릭스 10행) + `docs/plans/05-writing-ai.md` §74 + `docs/system-contract-sot.md` v1.6.68.
- **Source of work**: working tree, uncommitted(`git diff HEAD` 6파일 + untracked `writing/`·`tests/test_writing.py`·브리프). HEAD = `6e15798`(v1.6.66).

## Scope

1. **Spec contract** — 브리프 Q1/Q2/D3~D7, 매트릭스 10행, "성격"(신규 패키지·minor bump)의 내부 일관성.
2. **Implementation code** — `writing/models.py`(계약 리터럴), `writing/service.py`(1-turn 직접 호출·ProviderError 전파·검증), `writing/prompt.py`(컴팩트 포맷·라벨), `main.py`(오케스트레이션·에러 매핑).
3. **계약 일관성 검증** — "평문이라 JSON parse/repair 불요"(compare_judge와의 차이), ProviderError 전파(성공 위장 금지), status 항상 candidate, self-report 필드의 forward-defense 정당성.
4. **Regression tests** — 회귀 +17(prompt 4·generate 7·HTTP 6) 양방향 guard.
5. **Boundary matrix** — 매트릭스 10행 각 분기가 named test로 매핑되는지 추적.
6. **Full suite + mutation** — 822/48/101 재도출 + 6종 변형으로 bite 증명.

라이브 실 Gateway 관통(평문 반환 실증)은 read-time 로직이 결정적이므로 scope에서 제외; 브리프가 "결정적 백엔드 로직"으로 범위 한정.

## Methodology

브리프 매트릭스 10행을 lock list로 세우고 코드·테스트·스펙에 대입. under-strict(side effect 미발생 시 실패)·over-strict(잘못된 입력 통과 시 실패) 양방향을 mutation으로 증명. 의존 인터페이스(`ChatCompletionRequest.thinking`, `ContextPackage` 필드, `PromptTemplateService`) 존재를 정적 확인.

명령(재현은 §Reproduction):
- `git diff HEAD -- services/application/app/main.py` — 오케스트레이션 diff.
- `cat services/application/app/writing/{models,prompt,service}.py tests/test_writing.py` — 신규 패키지/테스트(untracked).
- `python3 -m pytest tests/test_writing.py -q -p no:cacheprovider` — focused(17).
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` — 전체(822/48/101).
- mutation: `cp` 백업 → 정확한 문자열 replace → focused pytest → 복구(MW1~MW6 6종).

## Findings

### 1. Spec contract — 내부 일관성

브리프 Q1/Q2 ↔ D3~D7 ↔ 매트릭스 10행 ↔ "성격"이 전부 일관. 핵심 정직성 포인트: "의미 있는 Writing Gate(do_not_use/POV 위반 탐지)는 결정적 문자열 매칭 불가·LLM 기반이라 독립 slice"(Q1 채택 근거) — 이 slice가 **의미 검증을 결정적 매칭으로 흉내내지 않고** 명시적으로 Gate slice로 분리한 것은 정확한 범위 설정. 내부 모순 없음.

### 2. Implementation code — 스펙 리터럴 대 일치

- `models.py:18` `WRITING_CANDIDATE_STATUS="candidate"` 상수. `WritingCandidate.status` default가 이 상수(행 8). `WritingTaskType.CONTINUE_SCENE` 단일(D3), `WritingOutputType.DRAFT_PATCH`(D5). `self_reported_constraints=()`·`candidate_id=None`(save slice)·`generated_by_model=""` — 브리프 "WritingCandidate 계약(slice 1)"과 문자열 단위 일치.
- `service.py:99-108` — `result = await self._provider.generate(chat_request)`를 **try/except 없이** 호출 → ProviderError가 그대로 전파. 이후 `WritingCandidate(text=result.content.strip(), status=WRITING_CANDIDATE_STATUS, ...)`. "평문이라 JSON parse/repair 불요" 주장이 코드와 일치(compare_judge는 terminal-JSON parse·repair 단계가 있으나 writing은 `.content.strip()`만).
- `service.py:110-125` `_validate` — task_type 체크(행 5) → instruction 공란(행 6) → `package.project_id != request.project_id`(행 4) → brief project_id. D6 결정적 안전선과 일치.
- `service.py:80-86` — `get_template` 실패 → `PromptTemplateError`→`WritingError`. template 부재가 silent empty prompt로 이어지지 않음.
- `prompt.py:47-76` `format_context_package` — do_not_use → constraints → macro_items → micro_evidence 순서(행 3 hard priority). 빈 package면 `"(no project memory retrieved)"`(자명하지 않은 명시).
- `prompt.py:79-87` `_format_item` — `item.status is ContextItemStatus.CANDIDATE`면 `"candidate (uncertain)"`, 아니면 `"canonical"`(행 10).
- `prompt.py:103-142` `build_writing_request` — `[INSTRUCTION]`·`[CONTEXT PACKAGE]`·`[CURRENT DRAFT EXCERPT]`(있을 때)·`[FINAL INSTRUCTION]` 포함(행 1). `thinking=False` 명시(`payload.py:38` 필드 존재 확인).
- `main.py` 엔드포인트 — `_require_project_exists`→404, `WritingTaskType(body.task_type)` ValueError→400, writing None→503, context_search None→503, `WritingError`→400, `InvalidContextSearchRequest`→400, `ContextSearchBudgetExceeded`→504, `ContextSearchFailed`→502, `ProviderError`→502. context_search→generate 오케스트레이션(행 9).

### 3. 계약 일관성 검증 — 핵심 클레임

- **"평문이라 JSON parse/repair 불요"**: `service.py`가 `result.content.strip()`만으로 WritingCandidate를 조립. compare_judge(`analysis/compare_judge.py`)는 terminal-JSON parse·repair 단계를 가지나, writing은 master prompt의 "Output the continuation prose only. No JSON..." 지시(`prompt.py:44`)로 평문을 강제하고 서비스는 파싱 없이 래핑. 주장과 일치. (실제 provider가 평문을 반환하는지 실증은 live Gateway 영역 — 비차단 H3.)
- **ProviderError 전파(성공 위장 금지)**: `service.py:99`에 try/except 없음 → ProviderError가 엔드포인트로 전파 → `main.py` `except ProviderError → 502`. MW2 변형(삼키기)이 2개 테스트를 FAIL시켜 이 가드가 load-bearing임을 증명.
- **status 항상 candidate**: `WritingCandidate.status=WRITING_CANDIDATE_STATUS`(상수). MW1 변형("final")이 2개 테스트 FAIL.
- **self-report 필드 forward-defense**: `self_reported_constraints=()`가 slice 1에서 항상 빈 튜플. 브리프 Q2 근거가 "Gate slice가 채움, slice 1엔 소비자 없음"으로 명시적이고, 오너 결정(Q2)에 근거. CLAUDE.md "Nothing speculative" 관점에서는 소비자 없는 필드지만, 브리프가 계약선행(forward-defense)으로 정당화하고 후속 Gate slice가 곧 채울 예정 — 비차단(H1).

### 4. Boundary matrix — lock 추적 (10행)

| # | 분기 | 방향 | 잠근 테스트 | mutation |
|---|---|---|---|---|
| 1 | prompt에 instruction/draft_excerpt/macro/constraints/do_not_use 포함 | under-strict | `test_build_request_carries_instruction_excerpt_and_context` | MW5 |
| 2 | 평문→WritingCandidate(text, status=candidate) | under-strict | `test_plain_prose_is_wrapped_into_candidate` + `test_generate_returns_candidate` | MW1 |
| 3 | do_not_use/constraints hard-priority 순서 | under-strict | `test_context_format_orders_do_not_use_and_labels_candidate` | MW5 |
| 4 | project isolation 불일치→WritingError(400) | over-strict | `test_cross_project_package_rejected` + `test_cross_project_brief_rejected` | MW3 |
| 5 | task_type≠continue_scene→WritingError | over-strict | `test_non_continue_scene_task_rejected` + `test_unsupported_task_type_returns_400` | MW4 |
| 6 | 빈 instruction→WritingError | over-strict | `test_empty_instruction_rejected` | — |
| 7 | ProviderError 전파→502 | under-strict | `test_provider_error_is_not_swallowed` + `test_provider_error_returns_502` | MW2 |
| 8 | status 항상 "candidate" | over-strict | `test_plain_prose_is_wrapped_into_candidate` | MW1 |
| 9 | HTTP context_search→generate·미구성 503 | under/over | `test_generate_returns_candidate` + `test_writing_not_configured_returns_503` + `test_context_search_not_configured_returns_503` | — |
| 10 | candidate memory candidate 라벨 | under-strict | `test_context_format_orders_do_not_use_and_labels_candidate` | MW6 |

10행 전부 named test로 잠김. 빈 cell 없음. 행 6(빈 instruction)은 named test로 잠겨 있으나 mutation은 생략(행 5/4와 동일 `_validate` 패턴, MW3/MW4가 이미 `_validate` guard 구조를 bite).

### 5. Mutation testing — guard bite 실증

| 변형 | 기대 | 결과 |
|---|---|---|
| MW1: `status="candidate"`→`"final"` | 행 8 붕괴 | `test_plain_prose...` + `test_generate_returns_candidate` FAIL ✅ |
| MW2: ProviderError를 try/except로 삼키고 가짜 결과 반환 | 행 7 붕괴 | `test_provider_error_is_not_swallowed` + `test_provider_error_returns_502` FAIL ✅ |
| MW3: `package.project_id != request.project_id` 체크 무효화 | 행 4 붕괴 | `test_cross_project_package_rejected` FAIL ✅ |
| MW4: task_type 체크 무효화 | 행 5 붕괴 | `test_non_continue_scene_task_rejected` FAIL ✅ |
| MW5: do_not_use↔constraints 순서 뒤바꿈 | 행 3 붕괴 | `test_build_request...` + `test_context_format_orders...` FAIL ✅ |
| MW6: candidate item을 "canonical"로 오라벨 | 행 10 붕괴 | `test_context_format_orders...` FAIL ✅ |

6/6 bite. mutation 복구 후 `service.py`·`prompt.py`가 pre-mutation과 identical(`diff -q` 확인).

### 6. 테스트 셋업 버그 수정 검증

작업자 보고 "fake context가 고정 project_id 반환→isolation 검증 충돌 잡음". `tests/test_writing.py:268-272` `_FakeContextSearch.build_context_package`가 `replace(self._package, project_id=request.project_id)`로 실제 context_search 동작(요청 project_id로 package 생성)을 미러. 이로 HTTP 정상경로 테스트(`WritingGenerateApiTest`)는 isolation이 자연 통과하고, isolation 위반은 별도 단위 테스트(`GenerateTest.test_cross_project_package_rejected`가 package.project_id를 직접 "p2"로 주어)가 잡음 — 정상경로와 위반경로가 깔끔히 분리. 수정 정확.

### 7. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **822 passed / 48 skipped / 101 subtests passed**. 작업자 클레임과 정확히 일치(805 → +17).

## Issues / Risks

### Blocking (contract obligations)

- 없음. 매트릭스 10행이 전부 named test로 잠겨 있고, 6종 mutation이 모두 bite하며, ProviderError 전파·project isolation·status 상수·평문 래핑이 코드-스펙-테스트 삼관에서 일치한다.

### Hardening recommendations (non-blocking)

- **H1 — `self_reported_constraints` 필드가 slice 1에서 소비자 없음**. 항상 `()`. 브리프 Q2가 "Gate slice가 채움"으로 forward-defense 정당화하고 오너 결정에 근거하므로 speculative라기보다 계약선행이나, CLAUDE.md "Nothing speculative" 관점에서 후속 Gate slice가 곧 채울 것이라는 전제가 깨지면 dead field가 됨 — Gate slice 착수 시 이 필드를 실제로 채우는지 추적 권장.
- **H2 — 작업자 보고에 `ContextSearchBudgetExceeded→504` 매핑이 누락**. 코드(`main.py` 엔드포인트)는 504도 매핑하지만, 보고("503×2·400·404·502")와 매트릭스 행 9("미구성 503")에 504가 명시되지 않음. 결함이 아니라 보고 정확성 이슈 — 향후 보고/SoT에 504 경로도 명시하면 경계가 더 또렷.
- **H3 — "평문" 보장이 master prompt 지시에 의존**. `prompt.py:44` "No JSON, no headings..."로 평문을 강제하지만, 실제 provider가 지시를 따르는지(드물게 JSON을 뱉는지)는 실 Gateway live에서만 검증 가능. 이 slice는 결정적 로직으로 범위 한정이므로 비결함 — live 관통 시 평문 반환을 한 번 확인 권장.
- **H4 — budget 5차원 중 max_tokens만 적용**. `WritingService` 기본 `max_tokens=1024`(env `WRITING_GENERATE_MAX_TOKENS`)는 벤치마크값이나, budget의 iteration/wall-clock/total-token/repeated-call 차원은 이 slice에서 적용 안 됨(1-turn·tool 없음이라). 브리프가 "첫 모델 budget/timeout은 벤치마크값 사용"으로 명시했고 agent_loop runner가 보류(HANDOFF Active Decisions) 상태이므로 비결함 — runner 활성화 시 5차원 budget가 이 경로에도 적용되는지 추적.

## Verdict

**합격(Pass, 조건 없음).**

이유(load-bearing):
- 코드가 브리프 Q1/Q2·D3~D7·매트릭스 10행과 정확히 일치하고, 계약 내부(브리프 ↔ 매트릭스 ↔ "성격")에 모순이 없다.
- 매트릭스 10행이 전부 named test로 잠겨 있고, 6종 mutation이 guard의 bite를 실증했다.
- 핵심 클레임 3개가 모두 코드로 확인됐다: "평문이라 JSON parse 불요"(`.content.strip()`만), ProviderError 전파(try/except 없음→502), status 항상 candidate(상수).
- 의미 검증(do_not_use/POV)을 결정적 매칭으로 흉내내지 않고 Gate slice로 명시 분리한 범위 설정이 정확하다.
- 전체 suite 822/48/101이 작업자 클레임과 정확히 일치. mutation 후 무결성 확인.
- 비차단 H1~H4는 향후 보강/추적 후보.

## Outstanding items

- 작업 미커밋(working tree, untracked `writing/`·`tests/test_writing.py`·브리프 포함). 커밋 여부는 오너 결정 대기 — 검증상 이견 없음.
- H3 실 Gateway 평문 반환 live 확인 — sandbox 밖 후속(선택).
- 후속 Phase 5 slice: Writing Gate(LLM 기반 do_not_use/POV) → accept→save→analysis 재진입 → 구조적 self-report → revise/outline/critique task.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# focused (17)
python3 -m pytest tests/test_writing.py -q -p no:cacheprovider

# full suite (822 passed / 48 skipped / 101 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# mutation MW2 (ProviderError swallowed) — must FAIL rows 7
cp services/application/app/writing/service.py /tmp/svc.bak
python3 - <<'PY'
p="services/application/app/writing/service.py"
s=open(p,encoding="utf-8").read()
old='''        # A provider fault (ProviderError) is not swallowed — it propagates so the
        # HTTP layer maps it to 502 (never a success disguising a failure).
        result = await self._provider.generate(chat_request)'''
new='''        try:
            result = await self._provider.generate(chat_request)
        except Exception:
            result = type("R",(),{"content":"(silent)","model":"fake"})()'''
assert s.count(old)==1
open(p,"w",encoding="utf-8").write(s.replace(old,new,1))
PY
python3 -m pytest tests/test_writing.py -q -p no:cacheprovider | tail -3   # expect 2 FAIL
cp /tmp/svc.bak services/application/app/writing/service.py
diff -q /tmp/svc.bak services/application/app/writing/service.py            # identical
```
