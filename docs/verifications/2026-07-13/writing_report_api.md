# 독립 검증 — Phase 5.5 Writing report 재평가 API (SoT v1.6.72)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: 오너("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? A 방향으로 구현 완료… 변경사항은 아직 커밋하지 않았습니다.").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박용 가설로 취급 — green bar와 상관없이 계약 경계를 깨보려 시도.
- **Target slice**: Phase 5.5 — `services/application/app/main.py`(`WritingReportRequest`·`writing_report_service` 주입·`POST /projects/{id}/writing/report`), `services/application/app/writing/report.py`(TEMPLATE schema 보강), `tests/test_writing.py`(`WritingReportApiTest` +4), `tests/test_writing_report.py`(prompt-schema assertion). 문서: SoT v1.6.72·`plans/05-writing-report-api-decisions.md`·`plans/05-writing-ai.md`·CHANGELOG·HANDOFF.
- **Canonical spec reference**: `docs/plans/05-writing-report-api-decisions.md`(Resolved — A inline now / B additive later) + `docs/system-contract-sot.md` v1.6.72(L36). 입력 계약은 정본에서 하나로 도출됨(브리프가 해당 충돌을 오너 결정으로 폐쇄).
- **Source of work**: working tree, uncommitted. `git status` — 8 modified(main.py·report.py·test_writing.py·test_writing_report.py·SoT·CHANGELOG·HANDOFF·plan) + 2 untracked(브리프·오늘 로그). HEAD=a1de026(v1.6.71).

## Scope

1. **Spec contract** — 브리프(A/B/follow-up/deferred)·SoT v1.6.72 changelog·구현 코드의 삼자 일관성과 정본 내부 교차 모순.
2. **Implementation code** — endpoint 경로·입력 필드·상태코드 매핑·서버 ContextPackage 재구성·strict extractor 재사용·envelope 재사용·`candidate_id=null` 비영속 표시.
3. **Prompt schema 보강(핵심)** — report.py TEMPLATE의 enum literal이 Python enum(`CandidateClaimType`/`MemoryHintType`/`RiskNoteType`/`RiskSeverity`)과 **정확히** 일치하는지 셀별 대조. 이것이 구현자의 핵심 클레임이자 fake-provider 회귀가 가리는 결함 클래스.
4. **Regression tests** — `WritingReportApiTest` 4개 + `test_writing_report.py` prompt assertion이 매트릭스를 채우는지, guard가 양방향으로 bite하는지.
5. **Live LLM smoke(독립 재현)** — `192.168.1.22:9080` 실 gemma 모델에서 (a) 강화 prompt로 strict parse 통과, (b) 구버전 prompt로 repair 후에도 실패 → 결함/fix의 필연성 증명.
6. **Full/focused suite + 컴파일/whitespace** — 880/45/154·68/53·py_compile·diff --check 재도출.

## Methodology

정본 스코프를 먼저 세운 뒤(sourcing): SoT v1.6.72 changelog 1줄이 본 slice의 계약 본문(별도 prose section 없음 — `grep`로 확인)이므로, 이것과 브리프·상속 계약(report extractor v1.6.71·WritingCandidate envelope v1.6.68)에서 **boundary matrix(lock list)** 를 세우고 각 셀을 named test로 추적. 빈 셀은 blocking. 구현자의 "880/68 passed", "live status=ok", "prompt schema 누락 보강" 클레임을 1차 원천에서 재도출.

특히 보강 클레임은 두 단계로 적대 검증: (1) prompt enum ↔ Python enum 셀별 문자열 대조(불일치 시 실 모델은 parse 불가, fake는 가림), (2) 실 llama.cpp 서버에서 `enrich`(initial+1회 repair)를 OLD/NEW TEMPLATE로 각각 돌려 OLD만 실패하는지 확인(monkeypatch로 repair 경로의 module 상수까지 교체해 구버전 코드 동작 충실히 재현).

명령(전체 재현은 §Reproduction):
- `git --no-pager diff services/application/app/main.py services/application/app/writing/report.py` — 관통 diff.
- `grep -n class ...Type services/application/app/writing/models.py` ↔ TEMPLATE literal 수동 대조.
- `python3 -m pytest -q ... tests/test_writing_report.py tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py` → 68/53.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` → 880/45/154.
- `/tmp/smoke_report.py`·`/tmp/smoke_old_enrich.py` — 실 모델 NEW/OLD enrich 비교.

## Findings

### 1. Spec contract — 일관성 PASS

브리프(A=inline+서버 ContextPackage 재구성, B=persisted 감사 이력/id API additive, side-effect-free, strict parse+1회 repair+provider/timeout mapping 재사용) ↔ SoT v1.6.72 changelog ↔ 코드 모두 일치. `plans/05-writing-ai.md:83` 체크리스트·HANDOFF v1.6.72 전환·CHANGELOG 엔트리 모두 동일 방향. 정본 섹션 간 모순 없음. 입력 계약 충돌(D3 필수 후속 vs Follow-up/Deferred 제한)은 브리프로 오너 결정(A) 폐쇄 — 구현자가 "추측 구현하지 않고 브리프로 전환"한 판단은 정본 우선순위 규칙에 부합.

### 2. Implementation code — 계약 대조 PASS

- 경로/입력/재구성: `POST /projects/{project_id}/writing/report`(`main.py:2374`), `WritingReportRequest`(`main.py:876-884`: request_id/instruction/candidate_text + task_type 기본 continue_scene), 서버가 `ContextSearchRequest`(`main.py:2401-2410`, query=`body.query or body.instruction`)로 `build_context_package` 재구성 — client가 context를 제출하지 않음(브리프 파생 결정). ✓
- strict extractor 재사용: `writing_report.enrich(candidate, package)`(`main.py:2430-2431`) = 기존 `WritingCandidateReportService.enrich`. ✓
- envelope 재사용 + 비영속 표시: `_writing_candidate_payload(enriched)`(`main.py:2441`, 정의 `2192-2215`), inline `WritingCandidate`는 `candidate_id=None`(`models.py:150` 기본값) → 응답 `candidate_id=null`. ✓
- 상태코드 매핑(`main.py:2376-2439`): empty request_id/instruction/candidate_text→400, `WritingTaskType(body.task_type)` ValueError→400, NotFound→404, service/context 미구성→503×2, `InvalidCandidateReport`→502, `ContextSearchBudgetExceeded`→504, `ContextSearchFailed`→502, `ProviderError`→(TIMEOUT?504:502). changelog "빈 입력/unsupported task=400, missing project=404, dependency=503, malformed/일반 backend=502, timeout/budget=504"와 일치. ✓
- side-effect 부재: endpoint 본문은 `build_context_package`·`enrich`·직렬화만 호출 — save/Gate/accept/Analysis 호출 부재(구조적 보장). ✓
- candidate identity 불일치 사전 거부(브리프 follow-up): inline candidate는 path `project_id` + `body.request_id`로 서버가 생성하므로 불일치가 구조적으로 불가능. 별도 분기 없이 조건 충족. (별도 test 불필요 — 분기 자체가 없음.)

### 3. Prompt schema 보강 — enum 정확성 PASS (핵심 적대 검증)

구현자의 "실 LLM에서 발견한 schema prompt 누락 보강" 클레임을 가장 의심. report.py TEMPLATE(`report.py:22-51`)의 pipe-separated enum을 Python enum(`models.py:53-88`)과 셀별 대조:

| enum | TEMPLATE literal 수 | Python enum 수 | 결과 |
|---|---|---|---|
| CandidateClaimType | 8 | 8 (narrative_event…interpretation) | **전부 정확 일치** |
| MemoryHintType | 7 | 7 (event…style_signal) | **전부 정확 일치** |
| RiskNoteType | 7 | 7 (pov…factuality) | **전부 정확 일치** |
| RiskSeverity | 4 | 4 (low/medium/high/critical) | **정확 일치** |

item shape(`text`/`type`/`requires_gate_check`, `type`/`text`/`confidence`/`should_analyze_after_save`, `type`/`severity`/`message`)도 `parse_report`(`report.py:95-127`)의 `_exact` 키 집합과 일치. 보강 클레임 사실 확인. 회귀 `test_writing_report.py:65-72`가 initial==repair system prompt + schema literal 존재를 잠가 regression 방어.

### 4. Regression tests — 양방향 guard PASS (단 1 빈 셀, §Issues B1)

`WritingReportApiTest`(`test_writing.py:469-547`):
- `test_inline_candidate_is_re_evaluated_with_server_context`: 200, `reporter.calls==1`, `context.last_request.query==instruction`(서버 재구성 증명), candidate text·package project_id, `type` 직렬화·`claim_type` 부재·`candidate_id is None`. under-strict 유효(재구성 안 하면 query 불일치, persist하면 id not None).
- `test_invalid_inline_input_is_rejected_before_reporter`: 3 subtests(empty request_id/instruction/candidate_text → 400) + `reporter.calls==0`(over-strict — LLM 전송 차단).
- `test_report_dependencies_and_project_scope_are_enforced`: 503(context 미구성)·503(report 미구성)·404(ghost project).
- `test_report_and_context_failures_keep_public_mapping`: 5 subtests — InvalidCandidateReport→502, ProviderError TIMEOUT→504, UNAVAILABLE→502, ContextSearchBudgetExceeded→504, ContextSearchFailed→502. mapping을 바꾸면 bite(실 guard).

`test_writing_report.py:65-72`: initial system prompt에 `"requires_gate_check": true`·`narrative_event|character_state`·`low|medium|high|critical` 존재 + repair prompt==initial. prompt를 one-liner로 환원하면 bite.

### 5. Live LLM smoke — 독립 재현 PASS, 결함/fix 필연성 증명

`192.168.1.22:9080`(llama.cpp, `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`)에 `LlamaCppProvider` 직접 연결.
- NEW TEMPLATE, 전체 `enrich`(initial+1회 repair): **`status=ok`**, claims=4/hints=2/risks=0, 모든 enum 유효. (구현자 보고 claims=2/hints=1과 개수 차이 — 입력 prose·비결정성 때문. 핵심 클레임 "strict parse 통과"는 재현.)
- OLD one-liner TEMPLATE(`report.py` HEAD판)로 module 상수+seed를 monkeypatch해 동일 `enrich`: **repair 후 FAIL → `InvalidCandidateReport`**(json parse error). 구현자 "initial·repair 모두 실패" 클레임 사실 확인.
- → 결함은 진짜, fix는 필요·효과 있음. fake-provider 회귀는 ready-made JSON을 반환해 이 결함을 가림(구현자 보고와 일치).

### 6. Suite / 컴파일 / whitespace — 재도출 PASS

- focused: **68 passed / 53 subtests**(구현자 클레임과 정확 일치).
- full(`--ignore=tests/test_memory_mongo.py`): **880 passed / 45 skipped / 154 subtests**(정확 일치).
- `python3 -m py_compile` 변경 4파일 OK; `git diff --check` clean.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — report endpoint `unsupported task_type → 400` 브랜치에 전용 회귀 부재(빈 셀)**: changelog v1.6.72가 report-API 상태맵에 "unsupported task=400"을 명시하고, endpoint도 해당 분기를 구현(`main.py:2378-2384`, `WritingTaskType(body.task_type)` ValueError→400)하나, 이를 exercise하는 report-API 회귀가 없음. 유일한 task_type-400 테스트(`test_writing.py:414-420`)는 `/writing/generate` 대상. 도달 가능(task_type="revise" 등 non-continue_scene). **boundary matrix 빈 셀 — green bar(880 passed)와 무관하게 blocking.** → 조건부 합격, B1 test 추가 시 합격. (검증자는 §5에 따라 음서 수정하지 않음 — 오너/구현자 판단.)

### Hardening recommendations (비차단)

- **H1 — `InvalidContextSearchRequest → 400` code-enforced but spec-silent**: endpoint가 `InvalidContextSearchRequest`를 400으로 매핑(`main.py:2418-2419`)하나 changelog 상태맵이 이를 명시하지 않고 test도 없음. 양성 입력검증 확장이므로 비차단이나, SoT v1.6.72 엔트리에 명시(또는 "빈 입력=400"으로 covering 확인) + 회귀 1건 권장.
- **H2 — "side effect 없음" 직접 guard 부재**: no-persistence는 구조적 보장 + `candidate_id is None` 약한 proxy. 브리프 step 2가 "side effect 없음" 회귀를 약속했으나 직접 no-save spy는 없음. core_sot repo save-count spy로 under-strict guard 추가 권장.
- **H3 — explicit `query` override 미실행**: `body.query or body.instruction`(`main.py:2403`)의 fallback(instruction)만 test. explicit query 전달 케이스 권장.
- **H4 — `current_position` wiring 미실행**: `main.py:2408-2415` 분기 test 없음. contract-critical은 아니나 1개 케이스 권장.

## Verdict

**조건부 합격(conditional pass).** 조건: B1(report-API `unsupported task_type → 400` 회귀 1건 추가).

근거: 정본 일관성·상태맵·enum 정확성(셀별)·envelope/재구성·live LLM 결함/fix 재현·suite 재도출 전부 독립·적대 검증 통과. 보강 클레임은 실 모델에서 OLD 실패/NEW 성공으로 필연성까지 증명. 유일한 계약 의무 위반은 B1 단 한 셀 — green bar가 숨긴 untraced boundary. B1만 채우면 합격.

## Outstanding items

- 변경사항 **미커밋**(working tree). 커밋 여부·시점은 오너 결정.
- B1 test 미추가(검증자 음서 수정 금지, §5).
- H1-H4 보강은 오너 재량. H1(spec-silent 400 매핑)은 문서 명시라도 권장.
- 원격 live smoke는 비결정적 — 재현 시 개수는 달라질 수 있으나 "OLD fail / NEW ok" 패턴은 견고.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# focused + full
python3 -m pytest -q -p no:cacheprovider tests/test_writing_report.py tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py   # 68 passed / 53 subtests
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider                                                                # 880 passed / 45 skipped / 154 subtests
python3 -m py_compile services/application/app/main.py services/application/app/writing/report.py tests/test_writing.py tests/test_writing_report.py
git diff --check
# B1 빈 셀 수동 확인: report-API task_type=400 test 부재
grep -n "task_type" tests/test_writing.py          # 414 라인은 /writing/generate 대상
# enum 정확성 수동 대조
grep -n "class CandidateClaimType\|class MemoryHintType\|class RiskNoteType\|class RiskSeverity" services/application/app/writing/models.py
# live smoke(원격 가동 시)
curl -s http://192.168.1.22:9080/health                              # {"status":"ok"}
PYTHONPATH=. python3 /tmp/smoke_report.py                            # NEW: status=ok
PYTHONPATH=. python3 /tmp/smoke_old_enrich.py                        # OLD: FAIL after repair / NEW: OK
```
