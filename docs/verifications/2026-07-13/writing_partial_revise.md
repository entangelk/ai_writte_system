# 독립 검증 — Phase 5.6 finding evidence 기반 부분 revise (SoT v1.6.73)

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: 오너("다음작업 검증해줘. 요청한 방향을 반영해 Phase 5.6 부분 revise를 구현했습니다. … v1.6.72는 25be309로 커밋됐고, 이번 v1.6.73 변경은 독립 검증 전이라 아직 미커밋.").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박 가설로 취급 — green bar와 무관히 계약 경계를 깨보려 시도.
- **Target slice**: Phase 5.6 — 신규 `services/application/app/writing/revise.py`(`WritingRevisionService`·`_validate`·splice·TEMPLATE), `main.py`(`WritingReviseRequest`·`_build_revise_service`·`writing_revision_service` 주입·`POST /projects/{id}/writing/revise` endpoint), `tests/test_writing_revise.py`(신규). 문서: SoT v1.6.73·`plans/05-writing-partial-revise-decisions.md`·`plans/05-writing-ai.md`·CHANGELOG·HANDOFF.
- **Canonical spec reference**: `docs/plans/05-writing-partial-revise-decisions.md`(Resolved, D1=A·D2=A first→C·D3=A·D4=A first→C·D5=A→B→C·D6=C·D7=A first→C·D8=A first→C) + `docs/system-contract-sot.md` v1.6.73(L36). 브리프 §"승인 후 첫 회귀 경계" 8행이 lock list.
- **Source of work**: working tree, uncommitted(신규 파일 revise.py·test_writing_revise.py·브리프는 untracked). HEAD=25be309(v1.6.72). 이전 검증(`verifications/2026-07-13/writing_report_api.md`)의 B1·H2가 25be309에서 닫힌 것을 먼저 확인.

## Scope

1. **Spec contract** — 브리프 D1~D8·8행 매트릭스·SoT v1.6.73 changelog·"모델=호출/응답, Application=anchor/splice/validation/loop" 원칙의 내부 일관성·교차 모순.
2. **Implementation code** — endpoint 경로·요청 모델·상태코드 매핑·서버 splice 결정성·evidence 단일 발생 보장·stale report 초기화·`candidate_id=null` 비영속.
3. **splice + D8** — prefix/suffix byte-for-byte 보존, unchanged/empty replacement→502.
4. **Regression tests** — service·HTTP 양쪽 회귀가 8행 매트릭스를 채우는지, guard가 양방향으로 bite하는지, 빈 셀 점검.
5. **Live LLM smoke(독립 재현)** — 실 gemma 모델이 "평문 replacement만" 지시를 실제로 지키는지(아니면 markdown/따옴표로 감싸 strip()에 안 걸리는지), 서버 splice가 정확한지.
6. **Full/focused suite + 컴파일/whitespace** — 892/45/163·80/62·py_compile·diff --check 재도출. 이전 B1 폐쇄 확인.

## Methodology

브리프 §"승인 후 첫 회귀 경계" 8행을 lock list로 세우고 각 셀을 named test로 추적. 빈 셀은 blocking. 핵심 적대 검증 두 축: (1) splice 결정성 — `candidate.text[:start] + replacement + candidate.text[end:]`가 evidence 밖을 건드리지 않는지 exact-string assertion으로 확인; (2) 실 모델 준수 — "평문 replacement만 반환" 지시에 대해 모델이 markdown/따옴표/preamble으로 감싸면 `strip()`(whitespace만 제거)으로는 안 벗겨지고 쓰레기가 splice에 섞이는지 live로 확인. fake-provider 회귀는 ready-made 평문을 반환해 이 결함을 가림.

명령(전체 재현은 §Reproduction):
- `git --no-pager show 25be309 -- tests/test_writing.py` — 이전 B1/H2 폐쇄 확인.
- `python3 -m pytest -q ... tests/test_writing_revise.py tests/test_writing.py tests/test_writing_report.py tests/test_writing_gate.py tests/test_writing_accept.py` → 80/62.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` → 892/45/163.
- `/tmp/smoke_revise.py` — 실 모델 replacement 평문 여부 + splice + prefix/suffix 보존.

## Findings

### 1. Spec contract — 일관성 PASS

브리프 D1~D8 ↔ SoT v1.6.73 changelog ↔ 코드 모두 일치. "모델/provider 서버는 호출/응답, Application은 anchor/offset 산술·schema validation·splice·decision priority·loop/budget 제어를 소유" 원칙이 코드에 충실히 반영 — 모델은 replacement 평문만 반환(`revise.py:27-30` TEMPLATE), anchor 산술·검증·splice는 전부 Application 서버(`revise.py:111-122` splice, `_validate` `124-146`). D8 순차화(현재 A=unchanged→502, 후속 C=200 changed=false, 별도 SoT bump+migration)가 브리프·changelog·코드에 동일. HANDOFF·CHANGELOG·plan 체크리스트 v1.6.73 동기화. 정본 섹션 간 모순 없음.

### 2. Implementation code — 계약 대조 PASS

- 경로/입력: `POST /projects/{project_id}/writing/revise`(`main.py:2490`), `WritingReviseRequest`(`main.py:916-924`: request_id/instruction/candidate_text/finding + task_type 기본 continue_scene + query/current_position/max_tokens). ✓
- 상태코드 매핑(`main.py:2506-2562`): NotFound→404, enum/task_type ValueError→400, service/context 미구성→503×2, `(WritingRevisionError, InvalidContextSearchRequest)`→400, `InvalidWritingRevision`→502, `ContextSearchBudgetExceeded`→504, `ContextSearchFailed`→502, `ProviderError`→(TIMEOUT?504:502). changelog/브리프 §5와 일치. ✓
- splice 결정성(`revise.py:111-122`): `start=candidate.text.index(evidence)`(count==1 보장 받아 단일), `text=candidate.text[:start]+replacement+candidate.text[end:]` — evidence 밖 prefix/suffix 무변경. stale report 4필드 `()` 초기화, `candidate_id=None`, `generated_by_model=result.model`. ✓
- `_validate`(`revise.py:124-146`): 빈 instruction·빈 candidate(request_id/text)·cross-project·finding_type≠continuity·recommended_decision≠revise·빈 evidence·`evidence` 발생 수≠1 → 전부 `WritingRevisionError`(→400). ✓
- side-effect: endpoint 본문은 `build_context_package`·`revise`·직렬화만 — save/Gate/report/accept/Analysis 호출 부재(구조적 보장). ✓

### 3. splice + D8 — PASS (핵심)

- `test_replaces_only_unique_evidence_and_clears_stale_report`(`test_writing_revise.py:87-98`): exact assertion `revised.text == "앞 문장. 고친 문장. 뒤 문장."` — prefix/suffix byte-for-byte 보존을 문자열 동등으로 pin. `candidate_claims==()`(stale reset), `candidate_id is None`, `generated_by_model=="fake-reviser"`, `provider.calls==1`. under-strict 유효(splice 잘못하면 문자열 불일치).
- D8 unchanged(`revise.py:109-110`): `replacement == finding.evidence` → `InvalidWritingRevision`(→502). service test(`test_writing_revise.py:125-131` content="잘못된 문장.") + HTTP test(`204-212`) 양쪽 lock.
- empty/whitespace replacement(`revise.py:106-108`): `not replacement` → 502. service test(whitespace 케이스) lock.

### 4. Regression tests — 양방향 guard PASS (단 1 빈 셀, §Issues B1)

- evidence missing/dup → 400 + `provider.calls==0`(`test_missing_or_duplicate_anchor_rejected_before_provider`). non-continuity·rec≠revise → 400 + `provider.calls==0`(`test_non_revise_or_non_continuity_rejected_before_provider`). cross-project → 400 + `provider.calls==0`(`test_cross_project_rejected_before_provider`). — pre-revise-provider 보장을 service 수준에서 lock.
- HTTP: 200 splice + 명시 query/current_position 전달(`test_http_revises_inline_candidate_with_server_context`), dup→400·unchanged→502(`test_http_validation_and_unchanged_mapping`), TIMEOUT→504/UNAVAILABLE→502(`test_http_provider_timeout_and_unavailable_mapping`), 503·404(`test_http_missing_service_and_project`).
- 이전 검증 B1 폐쇄 확인: `git show 25be309 -- tests/test_writing.py`에 `test_unsupported_task_type_is_rejected_before_reporter`(task_type="revise"→400) + no-save spy(`AssertionError("writing/report must not save a draft")`) 추가 — 작업자가 이전 검증 B1·H2를 성실히 반영.

### 5. Live LLM smoke — 독립 재현 PASS

`192.168.1.22:9080`(gemma-4-12B)에 `LlamaCppProvider` 직접 연결, continuity 오류 candidate(펜을 상자에 넣고 손에도 쥔 장면)로 `revise` 호출:
- RAW 모델 출력 = `'해리는 빛나는 펜을 상자에 넣고 뚜껑을 닫은 뒤, 다시 그것을 손에 꼭 쥐고 있었다.'` — **bare 평문, markdown·JSON·따옴표·preamble 전무**(`WRAPPING_TRAPS_AT_EDGES=[]`).
- 서버 splice 후 `PREFIX_PRESERVED=True`·`SUFFIX_PRESERVED=True`. 작업자 "replacement fragment 정상 반환 및 서버 splice 통과" 클레임 재현.

### 6. Suite / 컴파일 / whitespace — 재도출 PASS

- focused: **80 passed / 62 subtests**(클레임과 정확 일치).
- full(`--ignore=tests/test_memory_mongo.py`): **892 passed / 45 skipped / 163 subtests**(정확 일치).
- `py_compile` 변경 3파일 OK; `git diff --check` clean.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — HTTP 수준 context budget 504 / backend 502 매핑에 회귀 부재(빈 셀)**: endpoint가 `ContextSearchBudgetExceeded`→504·`ContextSearchFailed`→502를 매핑(`main.py:2553-2559`)하나, 테스트 `_Context` fake(`test_writing_revise.py:143-150`)가 항상 정상 package만 반환해 두 분기 중 어떤 것도 exercise 안 함. 브리프 §5가 "context budget 504/backend 502"를 명시적 회귀 경계로 열거. **boundary matrix 빈 셀 — green bar(892 passed)와 무관하게 blocking.** 작업자가 v1.6.72 report에서는 동일 gap을 `test_report_and_context_failures_keep_public_mapping`로 닫았으나 revise endpoint에서 재발. → 조건부 합격, B1 test 2건(budget→504, backend→502) 추가 시 합격. (검증자는 §5에 따라 음서 수정하지 않음.)

### Hardening recommendations (비차단)

- **H1 — 빈 instruction / 빈 candidate(request_id/text) / 빈 evidence → 400 분기 미실행**: `revise.py:131-142`의 해당 `WritingRevisionError` 분기가 service·HTTP 어디서도 직접 exercise되지 않음(현재는 duplicate-evidence만). 브리프 §2가 "빈 request/instruction/candidate/evidence → provider 전 400"을 열거. 분기 도달 가능(instruction="" 등). 각 1건 subtest 권장.
- **H2 — context_search 후 검증(sibling report와의 일관성)**: finding 의미검증(continuity/revise/evidence count)과 빈 입력 검증이 service `_validate`에 있어, endpoint는 `build_context_package`(context-search planner LLM 호출)를 **먼저** 한다. 직전 sibling `/writing/report`는 빈 입력 검증을 endpoint에서 context_search **전**에 수행. CHANGELOG "validation pre-provider 400" 표현이 "provider = revise-replacement LLM"을 뜻하므로 계약 위반은 아님(service test가 `provider.calls==0`로 revise provider 보호를 증명). 다만 잘못된 finding/빈 입력 한 건당 context-search planner round-trip이 낭비되며 sibling과 정렬되지 않음. endpoint로 빈 입력/finding 검증을 옮기거나 현재대로 수용 권장.
- **H3 — no-save/no-side-effect spy parity**: endpoint에 save/gate/report/accept/Analysis 호출이 구조적으로 없고 revise는 save 경로 자체가 없으므로 비차단. 다만 report는 25be309에서 no-save spy를 받음; revise도 향후 확장 시 spy로 잠그는 것을 권장.
- **H4 — D7=A(1-turn, repair 없음) 수용 한계**: 모델 출력에 `strip()`(whitespace만) 외에 방어가 없어, 모델이 따옴표/markdown fence로 감싸면 그대로 splice에 섞임. 이번 live 실행에서는 모델이 bare 평문으로 준수했으나 비결정적. D7=A 결정과 연계된 알려진 한계이나, 가벼운 서버 측 sanity strip(따옴표/백틱 fence) 또는 D7=C AgentLoop 시 해소 후보.

## Verdict

**조건부 합격(conditional pass).** 조건: B1(context budget 504 / backend 502 회귀 2건 추가).

근거: splice 결정성·stale report reset·D8 unchanged/empty→502·cross-project·evidence 단일 발생·non-continuity/rec≠revise·provider 504/502·503/404 전부 독립·적대 검증 통과, live 모델에서 bare 평문 + 정확 splice 재현, suite 80/62·892/45/163·컴파일/whitespace 재도출 일치, SoT v1.6.73 원칙 충실 반영. 유일한 계약 의무 위반은 B1 한 셀 — 작업자가 report에서 닫았던 동일 gap의 revise 재발. B1만 채우면 합격.

## Outstanding items

- 변경사항 **미커밋**(working tree; revise.py·test·브리프는 untracked). 커밋 여부·시점은 오너 결정(B1 채운 뒤 커밋 권장).
- B1 test 미추가(검증자 음서 수정 금지, §5).
- H1-H4 보강은 오너 재량. H1(빈 입력 분기)·H4(D7=A wrapping 한계)는 품질에 실질 영향이 있어 우선 검토 권장.
- live smoke는 비결정적 — 모델이 bare 평문을 준수하지 않을 수 있어 H4의 서버 측 방어 가치가 있음.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# focused + full
python3 -m pytest -q -p no:cacheprovider tests/test_writing_revise.py tests/test_writing.py tests/test_writing_report.py tests/test_writing_gate.py tests/test_writing_accept.py   # 80 passed / 62 subtests
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider                                                                  # 892 passed / 45 skipped / 163 subtests
python3 -m py_compile services/application/app/main.py services/application/app/writing/revise.py tests/test_writing_revise.py
git diff --check
# B1 빈 셀 수동 확인: _Context fake가 예외를 던지지 않음 → budget/backend 매핑 미실행
sed -n '143,150p' tests/test_writing_revise.py
# 이전 B1 폐쇄 확인
git show 25be309 -- tests/test_writing.py | grep -n "unsupported_task_type\|must not save"
# live smoke(원격 가동 시)
curl -s http://192.168.1.22:9080/health
PYTHONPATH=. python3 /tmp/smoke_revise.py     # bare replacement + PREFIX/SUFFIX_PRESERVED=True
```
