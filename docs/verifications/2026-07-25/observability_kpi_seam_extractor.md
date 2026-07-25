# 독립 검증 — 관측 KPI seam(provider 데코레이터) 도입 + analysis_extractor 계측 (SoT v1.7.43)

## Subject metadata

- **날짜**: 2026-07-25
- **요청자**: 오너 ("다음작업 검증해줘" — 커밋 `fac5676`, SoT v1.7.43)
- **검증자**: Claude (독립 검증, 구현자와 무관)
- **대상 슬라이스**: 관측 KPI 페이즈 — 잔여 호출부 계측을 위해 seam을 endpoint 레벨에서 **provider 데코레이터**(`ObservedProvider`)로 이동, 첫 적용 `analysis_extractor`. SoT v1.7.42 → v1.7.43. 커밋 `fac5676`(직전 `fc56ea6` = v1.7.42).
- **정본(계약) 참조**: `docs/system-contract-sot.md` v1.7.43 — 본문 §"LLM 파이프라인 관측(KPI)" 신규 조항(`L367` 계측 seam=provider 데코레이터 · `L368` contextvar 귀속 · `L369` scope 밖 미기록 · `L370` flush finally/append-only · `L371` 실패 토큰 의미론). 변경이력 `v1.7.43`(`L36`). 동 커밋이 `v1.7.42` 변경이력(`L37`)에 직전 독립검증 반영(H1 token 의미론·H2 브리프 drift 노트·**H3 dead branch 2개 제거**)도 함께 기록.
- **검증 대상 작업 출처**: 커밋 `fac5676`(working tree clean). HEAD = `fac5676`, 직전 = `fc56ea6`. 브리프 `docs/plans/observability-instrumentation-seam-decisions.md`(추천 C안, 오너 채택 2026-07-25).

## Scope (정본 계약 범위 — 열기 전에 확정)

1. **SoT 본문 §"LLM 파이프라인 관측(KPI)"** 신규/갱신 조항(`L365-L372`). 특히 v1.7.43이 추가한 seam·scope·flush 조항과, v1.7.42 잔재와의 정합.
2. **SoT 변경이력** `v1.7.43`(`L36`) + `v1.7.42`의 검증반영 확장(`L37`).
3. **브리프** `docs/plans/observability-instrumentation-seam-decisions.md` 전문(Decision needed · Options A/B/C/D · Recommendation C · Follow-up).
4. **구현**: `services/application/app/observability/llm_call_scope.py`(신규 — `PendingLlmCall`·`LlmCallScope`·`_SCOPE` contextvar·`llm_call_scope` CM·`_flush`·`ObservedProvider`). `services/application/app/main.py` — import(`L142-144`)·analysis runner 조립(`L599-607`)·`/analysis/jobs/{id}/run` 배선(`L2609-2618`)·gate endpoint dead branch 제거(`L3804-3833`). `services/application/app/analysis/extractor.py`(`L129` 본 호출·`L158` `_repair_once` = 2회 `generate`).
5. **회귀**: `tests/test_llm_call_scope.py`(신규 12 — `ScopeCaptureTest` 8·`ExtractorRepairIsRecordedTest` 2·`RunEndpointOpensAScopeTest` 2).
6. **공개 envelope**: `frontend/openapi.json`·`frontend/src/api/schema.d.ts`(`gen:api` 결정적 생성).

범위 밖: gate의 seam C 이행(증분 B)·compare/planner/generation 계측(증분 C)·집계 API(증분 5) — 모두 후속. Mongo 어댑터 field round-trip(v1.7.41 lock, 무변).

## 경계 매트릭스 (정본이 요구하는 분기 — 코드/테스트가 채워야 할 lock list)

| # | 분기 | 유형 | 코드(file:line) | 회귀 테스트 | 가드 방향 |
|---|---|---|---|---|---|
| 1 | `generate()` 1회 = 레코드 1건 (N호출 N레코드, per-call model/tokens) | FIRE | `llm_call_scope.py:165-171` `scope.add(SUCCESS)` | `test_each_provider_call_leaves_its_own_record` (3→3, tokens[2,4,6]) | under-strict |
| 2 | provider_error 기록 + raise 유지 + tokens=0 + error_type=code.value | FIRE | `llm_call_scope.py:157-164` | `test_provider_failure_is_recorded_and_still_raises` | under-strict |
| 3 | 요청 중간 실패해도 flush(finally) | FIRE | `llm_call_scope.py:108-112` `_flush` in `finally` | `test_calls_are_flushed_even_when_the_request_fails` | under-strict |
| 4 | scope 밖 호출 미기록 (구조적 보장) | NOT FIRE | `llm_call_scope.py:148-153` `if scope is None: return` | `test_calls_outside_any_scope_are_not_recorded` | over-strict |
| 5 | annotation은 마지막 call에만 (도메인 판정 얹기) | FIRE | `llm_call_scope.py:73-84` `annotate_last` | `test_annotation_lands_on_the_call_it_describes` | over-strict |
| 6 | annotate no-op when no call (pre-call 실패) | NOT FIRE | `llm_call_scope.py:80-81` | `test_annotating_with_no_call_made_is_a_no_op` | over-strict |
| 7 | 격리 — audit write 실패해도 workflow 완료 | ISOLATION | `llm_call_scope.py:122-137` `_flush` `except Exception` | `test_audit_failure_does_not_break_the_workflow` | under-strict |
| 8 | 동시 scope 비혼선 (contextvar 격리) | FIRE | `llm_call_scope.py:87-89` `_SCOPE` | `test_concurrent_scopes_do_not_mix_their_calls` (10개) | under-strict(누출) |
| 9 | 진짜 extractor의 repair = 2레코드 (둘 다 SUCCESS) | FIRE | `extractor.py:129`+`:158` | `test_a_repaired_extraction_leaves_two_records_not_one` | under-strict(핵심) |
| 10 | repair 없으면 정확히 1레코드 | NOT FIRE | — | `test_a_clean_extraction_leaves_exactly_one_record` | over-strict |
| 11 | endpoint 배선 — `correlation_id`=job_id, call_site=extractor | FIRE | `main.py:2613-2618` `with llm_call_scope(...)` | `test_run_endpoint_records_the_calls_its_runner_makes` | under-strict(배선) |
| 12 | idempotent replay = 추가 레코드 없음 | NOT FIRE | — | `test_replayed_run_makes_no_call_and_records_none` | over-strict |

**빈 cell 없음.** 정본이 요구하는 분기 전부 명명 회귀로 lock. `parse_error` outcome은 이 site(extractor)에서 도메인이 아직 annotate하지 않으므로 회귀가 다루지 않음 — 레코드 모양(outcome enum)엔 정의되나 이번 계측 범위 밖(도메인 훅은 gate 이행 증분 B에서). lock 누락 아님.

## Methodology

정적 도출 + 동적 실행. 작업 AI 서술을 받아쓰지 않고 primary source에서 재도출.

- **정적 — 계약/리터럴 교차검증**: 본문 v1.7.43 조항(`L367-372`) ↔ 변경이력 ↔ 브리프 C안. seam의 "도메인 무변" 주장을 `extractor.py`가 `self._provider.generate`를 그대로 호출하는지로 확인(ObservedProvider 주입 지점만 `main.py`에서 바뀜). dead branch 제거(H3)를 gate endpoint 코드 대조.
- **동적 — focused**: `env -u CORE_SOT_MONGO_URI python3 -m pytest tests/test_llm_call_scope.py -q` → `12 passed`.
- **동적 — 전체 suite(after)**: `pytest -q` → `1421 passed, 80 skipped, 593 subtests`(이 머신, test-mongo 미기동).
- **동적 — mutation 4종**: 각각 Edit 적용 → focused `pytest` → 역방향 Edit 원복. `diff /tmp/scope.after`·`/tmp/main43.after` 로 잔재 없음 확인.
- **동적 — gen:api no diff**: (a) after `gen:api` 후 `schema.d.ts` tracked·`git status` clean; (b) `git diff fc56ea6 fac5676 -- frontend/src/api/schema.d.ts` 로 두 커밋 동일 실증(`git checkout`은 classifier 제약으로 대체).
- **증분 검증**: 직전 독립검증 측정(v1.7.42, 동일 머신 test-mongo 미기동) `1409/80/593` ↔ 현재 `1421/80/593` = **+12 passed**, skip·subtests 동일. 작업 AI 보고 `1485→1497`(+12, test-mongo 기동)과 증분 일치.
- **환경**: pymongo 4.13.2 present. elasticsearch 파이썬 패키지 부재(lexical 3 skip). `CORE_SOT_MONGO_URI` unset → in-memory.

## Findings (표면별 — file:line)

### F1. seam C 구현 정확 — provider 경계가 레코드 경계
- `ObservedProvider.generate`(`llm_call_scope.py:147-172`): scope None이면 `return await self._inner.generate(request)`(미기록, `:152`), 아니면 `started` 측정 후 inner 호출. 성공 → `scope.add(PendingLlmCall(SUCCESS, model, total_tokens=result.usage.total_tokens))`(`:165-171`). `ProviderError` → `scope.add(PROVIDER_ERROR, error_type=exc.code.value)` + `raise`(`:157-164`).
- **호출 1회 = 레코드 1건이 구조적** — `generate()` 본체가 add를 호출하므로, 호출하지 않고 레코드가 생길 수 없다. SoT `L366`(레코드 조건 = provider 실호출) "v1.7.43부터 구조적으로 참" 정합. ✓
- **도메인 무변**: `extractor.py:129`(`result = await self._provider.generate(request)`)·`:158`(`repair = await self._provider.generate(...)`)는 provider 교체 없이 동일 호출. `main.py:602-607`이 `ObservedProvider(GatewayGenerateProvider(...), call_site=ANALYSIS_EXTRACTOR)`로 조립만 바꿈. ✓

### F2. 지연 flush + annotation = 호출당 1건·append-only 유지
- `PendingLlmCall`(`llm_call_scope.py:47-59`)은 scope에 모였다가 `_flush`(`:115-137`)가 scope 종료 시 `audit.record`로 순회 write. annotation(`annotate_last :73-84`)은 write **전**에 마지막 call의 필드만 `setattr`로 얹음 → 레코드는 여전히 호출당 1건, append-only. SoT `L370` 정합. ✓
- #5 `test_annotation_lands_on_the_call_it_describes` 가 annotation이 첫 call을 건드리지 않고 마지막 call에만 적용됨을 단정(over-strict). ✓
- parse_error 재분류(outcome SUCCESS→PARSE_ERROR)도 `annotate_last(outcome=PARSE_ERROR)`로 같은 창에서 가능 — 브리프 Follow-up #3(parse_error 위치)의 해법. 단, extractor는 이번에 annotate하지 않으므로 extractor 레코드의 outcome은 SUCCESS만(#9 단정). gate 이행(증분 B)에서 decision/parse_error annotate 적용 예정.

### F3. 격리 — `_flush`의 `except Exception` (전역 handler 안쪽 유지)
- `_flush`(`:122-137`): `try: for call in scope.calls: audit.record(...) except Exception: return`. pymongo 예외 포함 모두 삼킴. `finally` 안에서 실행되므로, audit 예외가 요청의 원래 예외를 덮어쓰지 않음(`:116-119` 주석). SoT `L365`(격리) 정합. ✓
- mutation 없이 코드 리딩으로 격리 확인 + #7 `test_audit_failure_does_not_break_the_workflow`(_FailingRepo RuntimeError)가 단정.

### F4. endpoint 배선 — `with llm_call_scope`가 없으면 seam이 죽는다
- `main.py:2613-2618`가 `/analysis/jobs/{id}/run` 본체를 `with llm_call_scope(llm_call_audit, project_id=project_id, correlation_id=job_id)`로 감쌈. **이게 없으면** ObservedProvider는 scope를 못 보고(scope=None) 미기록 — seam이 무용해진다.
- **작업 AI가 발견한 gap**: scope 단위 테스트(#1-#10)는 자체 `with`를 쓰므로 endpoint 배선 누락을 못 잡는다. 별도 회귀 #11/#12(`RunEndpointOpensAScopeTest`)가 endpoint 경로를 잠금. mutation-2(with 제거)로 #11/#12만 fail함을 실증(아래). ✓

### F5. 진짜 extractor의 repair = 2레코드 (stand-in 아님)
- #9 `test_a_repaired_extraction_leaves_two_records_not_one`(`test_llm_call_scope.py:266-280`)가 `VersionedPromptAnalysisExtractionAdapter`(`extractor.py`의 진짜 adapter) + `_observed(provider)`로 `"not json at all"` → `_repair_once` → 2 provider calls → **2 레코드**, 둘 다 `SUCCESS`(provider 관점; 첫 호출의 content 불량은 도메인 판정). 브리프가 지목한 dogfood 관측 대상(repair 횟수)이 endpoint 레벨이 아닌 seam에서만 얻을 수 있음의 실증. ✓

### F6. 다른 site 미감싸 — 중복 레코드 없음
- `grep "ObservedProvider("` → `main.py:602`(analysis runner) **단 한 곳**. gate(L731 `gate_provider`)·compare·planner(L1884)·generation(L1833/1839)은 전부 `GatewayGenerateProvider` 직접. 작업 AI "gate provider는 아직 감싸지 않아 중복 레코드 없음, 두 계층 공존" 정합. gate는 여전히 endpoint 레벨(`_record_gate_call`, `main.py:3795`). ✓

### F7. H3 dead branch 제거 — 코드에 실제 반영 (직전 검증 hardening 수용)
- 직전(v1.7.42) gate endpoint: `except (WritingGateError, InvalidContextSearchRequest)`(build try — WritingGateError는 dead) + `except InvalidWritingGateResult→502`(evaluate_metered가 감싸서 dead).
- 현재(`main.py:3804-3833`): build try는 `except InvalidContextSearchRequest`만(WritingGateError 제거), evaluate_metered try에 `except WritingGateError`(의미 있는 위치 — `_validate`가 evaluate_metered 안에서 호출), `InvalidWritingGateResult` 절 제거됨. SoT v1.7.42 변경이력 `L37` H3 기록과 코드 정합. 직전 독립검증 hardening #3이 정확히 반영됨. ✓

### F8. contextvar 격리 — 동시 scope 비혼선
- #8 `test_concurrent_scopes_do_not_mix_their_calls`(`test_llm_call_scope.py:181-200`): 10개 `asyncio.gather`, 각 scope가 자기 project에 1레코드, `correlation_id` 개별. contextvar 누출 0 실증. 작업 AI "동시 20요청 20/20" 주장의 본질(동시 비혼선)을 10개로 재현(수 차이 — hardening #4). ✓

### F9. 공개 계약 무변
- after `gen:api` 후 `schema.d.ts` tracked·`git status` clean(after dump == `fac5676` HEAD). `git diff fc56ea6 fac5676 -- frontend/src/api/schema.d.ts` → **두 커밋 동일**. 도메인 무변 + 조립 지점만 변경이므로 공개 스키마 무변은 자명하나, 실측으로 확정. ✓

### F10. mutation 4종 실증

| 변이 | 코드 변경 | 실측 |
|---|---|---|
| **endpoint 배선** | `main.py:2613` `with llm_call_scope` 제거 | #11·#12 **2 fail**(0≠1), 나머지 10 green ✓ |
| **scope 밖 가드** | `llm_call_scope.py:149-153` `if scope is None: return` 제거 | #4 **1 fail**(`AttributeError: NoneType.add`), 11 green ✓ |
| **flush finally** | `_flush`를 `finally`→`try`(yield 직후)로 | #3 **1 fail**(0≠1), 11 green ✓ |
| **success 레코드 생성** | `:165-171` `scope.add(SUCCESS)` 제거 | **8 fail**(#1/#3/#5/#8/#9/#10/#11/#12), green 4(#2 provider_error·#4·#6·#7) |

세 mutation(with/가드/flush)은 각각 해당 회귀만 정밀하게 물린다 — 작업 AI "mutation 4종이 각각 해당 회귀만 물림"과 정합. 넷째(success add 제거)는 seam 핵심(per-call 정확도) 자체를 깨므로 success 의존 8개를 동시에 물림 — 이는 약한 게 아니라 **seam 핵심이 다수 회귀로 중복 보호됨**을 보여준다(작업 AI의 정밀 mutation 4종이 이 넷째를 포함하지 않았을 가능성이 높음).

## Issues / Risks

### Blocking (계약 의무 위반)

**B1. SoT `L372` 자기 모순 — `analysis_extractor`를 같은 문단에서 '계측됨'과 '후속'으로 동시 서술.**

`L372` 인용(한 문단):
> 계측된 호출부: `writing_gate`(… v1.7.42 …) · **`analysis_extractor`(`POST …/analysis/jobs/{job_id}/run`, v1.7.43 — seam C, `correlation_id`=job_id)**. 나머지(`compare_judge`·`query_planner`·`writing_generation`)와 read-out(집계 API)은 후속 증분. 토큰은 도메인 서비스의 `*_metered` 변형에서 얻는다 — …. **나머지 호출부(generation·planner·compare·extractor)와 read-out(집계 API)은 후속 증분.**

앞에서는 `analysis_extractor`를 **v1.7.43 계측됨**으로, 같은 문단 끝에서는 **"나머지 호출부(…extractor) 후속"**으로 서술. 이는 v1.7.42 문장이 v1.7.43 갱신에서 앞부분만 고치고 끝의 잔재 문장을 못 지운 결과다. CLAUDE.md §5 "Internal contract inconsistency is a blocking finding — the contract itself is defective"에 해당. 구현/회귀는 정확하나(코드 + #9 lock), **계약 문서가 스스로와 충돌**하므로 다음 증분(집계 API)이 이 모순된 문단을 읽고 잘못된 범위 가정을 할 수 있다. 해결은 자명(끝의 잔재 문장 + `*_metered` gate-특화 서술 정리).

### Hardening (non-blocking)

**H1. SoT `L365` "_record_llm_call 한 곳"이 stale.** v1.7.42 격리 조항이 "시행 지점은 `_record_llm_call` 한 곳"이라 못박았으나, v1.7.43 seam 도입으로 격리 시행 지점이 **둘**이 됐다 — gate는 `_record_llm_call`(`main.py:1798`), extractor는 `_flush`(`llm_call_scope.py:122`). 작업 AI가 "두 계층 공존"을 명시적 인지하나, `L365` 문장은 갱신 안 됨. 격리 원칙 자체(감사 write 실패가 응답을 못 깨게)는 양쪽 동일·유지. 문장 명확화 권장(gate 한 곳 + seam flush 한 곳으로).

**H2. 브리프 상태 "Pending owner decision" 미갱신.** `observability-instrumentation-seam-decisions.md:3`이 여전히 `Pending`이나, 오너가 C안 채택·커밋 완료. 결정 기록은 SoT 변경이력 `L36`에 있으나 브리프 헤더가 안 따라감. 사소한 문서 정합.

**H3. 동시성 주장 20 vs 테스트 10.** 커밋 메시지·SoT `L368`·`llm_call_scope.py:21`이 "동시 20요청 전파 20/20"이라 하나, 회귀 #8은 10개 `asyncio.gather`. 본질(contextvar 격리)은 10으로도 증명되나, 주장(20)과 테스트(10) 수 불일치. 사소.

**H4. `parse_error` outcome의 extractor 적용 누락은 의도적이나 계약에 명시 없음.** extractor의 repair 첫 호출(content 불량)은 도메인이 `parse_error`로 재분류할 수 있는 후보임에도, 이번엔 annotate하지 않아 둘 다 `SUCCESS`로 기록(#9). 이는 "gate 이행(증분 B)에서 decision/parse_error annotate를 추가" 범위로 미뤄진 것이나, SoT 본문이 extractor의 outcome이 SUCCESS-only임을 명시하지 않아 독자 오해 가능. gate 이행 증분에서 outcome annotate 범위를 본문에 못박으면 hardening.

## Verdict

**조건부 합격.** 조건 = **B1(SoT `L372` 자기 모순 정정)**.

합격 근거(구현/회귀/공개계약/mutation 전부):
1. 경계 매트릭스 12 cell 전부 명명 회귀로 lock — 빈 cell 없음.
2. mutation 4종 — 3종(with 제거·가드 제거·flush finally)이 각각 해당 회귀만 정밀 물림; success add 제거는 seam 핵심 8개 중복 보호.
3. seam C 핵심 주장(`generate()` 1회=레코드 1건, 도메인 무변, 진짜 extractor repair 2레코드) 회귀 #1/#9로 lock.
4. 공개 계약 무변(schema.d.ts 두 커밋 동일).
5. 다른 site 미감싸로 중복 레코드 없음.
6. 증분 +12 양쪽(본 1409→1421 / 작업 AI 1485→1497)에서 일치.
7. 직전 검증 hardening 3건(H1/H2/H3)이 이번 커밋에 코드·문서로 수용됨 — 검증-피드백 루프 정상.

조건(B1): `L372` 끝의 잔재 문장("나머지 호출부(…extractor) 후속" + `*_metered` gate-특화 서술) 정정 전까지는 계약 문서가 자기 모순 상태. 구현 영향 없으나 다음 증분 전 정정 권장. 정정은 자명(잔래 제거).

## Outstanding items (오너 다음 단계에 영향)

- **작업 AI가 제안한 다음 순서**: 증분 B(gate를 seam C로 이행 — endpoint `_record_gate_call` 제거 + ObservedProvider 조립 + decision/parse_error annotate 훅) → 증분 C(compare·planner·generation) → 증분 5(집계 API). HANDOFF Next Tasks 1번. "이어서 증분 B를 진행할까요?"로 오너에게 물음 — 오너 결정 사항.
- **B1 정정**: 다음 슬라이스(또는 별도 문서 정정)에서 SoT `L372` 잔래 제거 + `L365` 명확화 권장.
- 라이브 확증: 여전히 in-memory 더블 기반. gate 이행·집계 API 이후 라이브 12B로 end-to-end 레코드 확인 가치(스택 기동은 오너 몫).

## Reproduction

```bash
# focused (신규 12건)
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB \
  python3 -m pytest tests/test_llm_call_scope.py -q
# → 12 passed

# 전체 after (이 머신, 2026-07-25, test-mongo 미기동)
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB -u ELASTICSEARCH_URL \
  python3 -m pytest -q -p no:cacheprovider
# → 1421 passed, 80 skipped, 593 subtests
# (작업 AI 환경 test-mongo 기동: 1497 passed / 4 skipped / 593 subtests — 증분 +12 양쪽 일치)

# 증분 +12 검증 — 직전 독립검증 측정(v1.7.42 동일 머신) 1409/80/593 와 비교
# (before fc56ea6 suite 재측정은 git checkout classifier 제약으로 생략;
#  focused 12 passed 가 신규 12건, subtests 593 양쪾 동일로 증분 확정)

# gen:api no diff (두 커밋 schema.d.ts 비교)
(cd frontend && npm run gen:api)                                      # schema.d.ts clean 확인
git diff fc56ea6 fac5676 -- frontend/src/api/schema.d.ts              # 빈 출력 = 동일

# mutation 4종 — 각각 Edit 적용 → focused pytest → 역방향 Edit 원복
#   endpoint 배선: main.py:2613-2618 의 with llm_call_scope(...) 블록 제거
#   scope 가드:    llm_call_scope.py:149-153 의 if scope is None: return 제거
#   flush finally: llm_call_scope.py:108-112 의 _flush(audit,scope) 를 finally→try(yield 직후)로
#   success add:   llm_call_scope.py:165-171 의 scope.add(PendingLlmCall(SUCCESS,...)) 제거
#   각 후: env -u CORE_SOT_MONGO_URI python3 -m pytest tests/test_llm_call_scope.py -q
#   역방향 원복 후 diff /tmp/scope.after services/application/app/observability/llm_call_scope.py  (no diff)
```
