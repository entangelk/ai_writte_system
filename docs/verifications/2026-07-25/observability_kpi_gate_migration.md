# 독립 검증 — 관측 KPI 증분 B: writing_gate를 seam C로 이행 (SoT v1.7.45)

## Subject metadata

- **날짜**: 2026-07-25
- **요청자**: 오너 ("다음작업 검증해줘" — 커밋 `5e6eeeb`, SoT v1.7.45)
- **검증자**: Claude (독립 검증, 구현자와 무관)
- **대상 슬라이스**: v1.7.42의 endpoint 레벨 gate 계측(`_record_gate_call`)을 걷어내고 gate provider를 `ObservedProvider`로 이행 — 계측 seam을 하나로 수렴. SoT v1.7.44 → v1.7.45. 커밋 `5e6eeeb`(직전 `56e34f4` = v1.7.44 문서 정정, 그 직전 `fac5676` = v1.7.43 seam 도입).
- **정본(계약) 참조**: `docs/system-contract-sot.md` v1.7.45 — 본문 §"LLM 파이프라인 관측(KPI)". `L367` 격리 시행 지점 `_flush` 한 곳으로 수렴(v1.7.45) + finally 예외 덮어쓰기 이유 · `L374-377` 계측된 호출부 하위 항목 분리(gate seam C 이행 완료, `*_metered` 우회 제거 명시). 변경이력 `v1.7.45` 행. (사이 커밋 `56e34f4`가 직전 독립검증 B1/H1/H3/H4를 본문·변경이력에 반영 — 본 검증에서 그 정정도 함께 확인.)
- **검증 대상 작업 출처**: 커밋 `5e6eeeb`(working tree clean). HEAD = `5e6eeeb`. 브리프 `docs/plans/observability-instrumentation-seam-decisions.md`(C안, Follow-up #1 "gate 이행"의 실행).

## Scope (정본 계약 범위 — 열기 전에 확정)

1. **SoT 본문 §"LLM 파이프라인 관측(KPI)"** 갱신 조항(`L367`·`L370`·`L374-377`). 특히 격리 수렴·gate 이행·`*_metered` 제거·parse_error 재분류 범위.
2. **SoT 변경이력** `v1.7.45` 행 + `v1.7.44`(`56e34f4`의 직전 검증 반영 — B1 자기모순 해소·parse_error 범위 명문화·H1 격리 둘 명시·H3 20 vs 10 구분).
3. **브리프** `observability-instrumentation-seam-decisions.md` Follow-up #1(gate 이행 형태).
4. **구현**: `services/application/app/main.py` — gate provider `ObservedProvider` 조립(`L729`)·`_default_analysis_runner` 조립(`L600`)·gate endpoint 이행(`with llm_call_scope` + `annotate_last`·`evaluate` 복귀·`InvalidWritingGateResult`/`WritingGateError`/`ProviderError` 매핑)·orphan 정리(`_record_llm_call`·`_record_gate_call`·`import time`·`MeteredCallError`·`TokenUsage` 제거). `services/application/app/writing/gate.py`(`evaluate`/`evaluate_metered` — 도메인 *_metered 존치). `services/application/app/observability/llm_call_scope.py`(무변, 이번엔 조립 가드만).
5. **회귀**: `tests/test_llm_call_scope.py::DefaultAssemblyIsInstrumentedTest`(신규 2 — gate 행위·extractor 구조) + 기존 `WritingGateObservabilityTest` 7건(이행 전후 동일 단정) + `RunEndpointOpensAScopeTest`.
6. **공개 envelope**: `frontend/src/api/schema.d.ts`.

범위 밖: compare/planner/generation 계측(증분 C)·집계 API(증분 5) — 후속.

## 경계 매트릭스 (정본이 요구하는 분기 — 코드/테스트가 채워야 할 lock list)

이행 슬라이스의 핵심은 **"이행 전후 gate 레코드 필드 동일"**. gate 회귀 7건(v1.7.42 endpoint 계측 검증)이 seam C 경로로도 동일 값을 생산하는지가 무손실의 증거다.

| # | 분기 | 유형 | 코드(file:line) | 회귀 테스트 | 가드 방향 |
|---|---|---|---|---|---|
| 1 | success 레코드(model·tokens·decision·score) | FIRE | `main.py:729` ObservedProvider + endpoint `annotate_last(decision, score)` | `test_successful_gate_call…` | under-strict |
| 2 | decision 5종 → score 전수 매핑 | FIRE | endpoint `annotate_last(gate_quality_score=…)` | `test_every_gate_decision…` (5 subtest + enum 전수) | over-strict |
| 3 | parse_error + **실소비 토큰 2 보존** | FIRE | ObservedProvider.add(SUCCESS, tokens) + `annotate_last(PARSE_ERROR)` | `test_parse_failure_records_the_tokens_that_were_really_spent` | under-strict(outcome) |
| 4 | provider_error + taxonomy + tokens=0 | FIRE | ObservedProvider.add(PROVIDER_ERROR) | `test_provider_failure…` | under-strict |
| 5 | pre-call 거부 미기록 | NOT FIRE | scope 안 `evaluate`만 | `test_rejections…` | over-strict |
| 6 | gate 실 조립 = ObservedProvider | FIRE(조립) | `main.py:729` | `test_gate_assembly_instruments_the_provider_it_builds` (행위) | under-strict |
| 7 | extractor 실 조립 = ObservedProvider | FIRE(조립) | `main.py:600` | `test_extractor_assembly_instruments_the_provider_it_builds` (구조) | under-strict |
| 8 | 격리 — audit write 실패해도 응답 무변 | ISOLATION | `llm_call_scope.py:122-137` `_flush` | `test_audit_failure_does_not_break_the_workflow` | under-strict |

**빈 cell 없음.** 이행으로 endpoint 레벨 계측이 사라졌으나, 동일 레코드를 seam이 생산함을 7건 gate 회귀가 잠근다.

## Methodology

정적 + 동적. 작업 AI 서술을 받아쓰지 않고 재도출.

- **정적 — 이행 무손실 추적**: endpoint(v1.7.42)가 만들던 레코드 필드(model·tokens·decision·score·parse_error 토큰)를 seam 경로(ObservedProvider.add + annotate_last)가 동일하게 생산하는지 코드 대조. 특히 parse 경로 — ObservedProvider가 SUCCESS로 tokens를 담고 annotate가 outcome만 바꾸는지.
- **동적 — focused**: `pytest tests/test_writing_gate.py tests/test_llm_call_scope.py -q` → `58 passed, 41 subtests`(gate 44 + scope 14).
- **동적 — 전체 suite**: `pytest -q` → `1423 passed, 80 skipped, 593 subtests`(이 머신, test-mongo 미기동).
- **동적 — mutation 4종**: 각각 Edit 적용 → focused → 역방향 원복. `diff /tmp/main45.after` 로 잔재 없음 확인.
- **동적 — gen:api no diff**: `git diff fac5676 5e6eeeb -- frontend/src/api/schema.d.ts` 및 `56e34f4..5e6eeeb` → 동일.
- **증분 검증**: 직전 독립검증 측정(v1.7.43 `fac5676`, 동일 머신) `1421/80/593` ↔ 현재 `1423/80/593` = **+2 passed**(조립 가드 2건). `56e34f4`(v1.7.44 문서 정정, 코드 무변)은 suite 무영향. 작업 AI `1497→1499`(+2, test-mongo 기동)과 증분 일치.
- **환경**: pymongo 4.13.2 present. elasticsearch 파이썬 패키지 부재. `CORE_SOT_MONGO_URI` unset.

## Findings (표면별 — file:line)

### F1. 이행 무손실 — gate 회귀 44건 이행 전후 완전 동일
- 이행 전(v1.7.42): endpoint가 `_record_gate_call`로 model·tokens·decision·score·parse_error 직접 기록.
- 이행 후(v1.7.45): `ObservedProvider`가 `generate()`에서 `add(SUCCESS, model, total_tokens=result.usage.total_tokens)`(`llm_call_scope.py:165-171`). endpoint는 도메인 판정만 `annotate_last`로 얹음 — `scope.annotate_last(decision=…, gate_quality_score=…)`(성공)·`scope.annotate_last(outcome=PARSE_ERROR, error_type=…)`(parse 실패).
- **7건 gate 회귀가 한 건도 수정 없이 통과**(focused 58 passed에 포함). 데코레이터가 endpoint 계측과 같은 값을 만든다는 작업 AI 주장 실증. ✓

### F2. parse_error의 실소비 토큰 2 보존 — 이행의 가장 미묘한 점
- v1.7.42: `MeteredCallError.usage`에서 토큰을 직접 읽어 `total_tokens`에 싣고 outcome=PARSE_ERROR.
- v1.7.45: provider가 응답했으므로 `ObservedProvider`가 이미 SUCCESS 레코드에 `total_tokens=result.usage.total_tokens`(=2)를 담음. 이후 `evaluate()`가 parse 실패를 `InvalidWritingGateResult`로 raise → endpoint가 `except InvalidWritingGateResult: scope.annotate_last(outcome=PARSE_ERROR)`(`main.py` gate endpoint). **annotate는 outcome만 바꾸고 tokens는 건드리지 않음** → 토큰 2 보존.
- mutation-3(annotate 제거)로 실증: `test_parse_failure`의 `outcome` 단정만 fail(`success != parse_error`), `total_tokens==2` 단정은 green. annotate가 토큰에서 독립임을 증명. ✓

### F3. evaluate_metered 우회 제거 — 도메인 *_metered는 존치
- v1.7.42 endpoint는 토큰을 직접 읽기 위해 `evaluate_metered` + `MeteredCallError` unwrap을 썼다. 이행 후 데코레이터가 provider 응답 usage를 읽으므로 endpoint는 `evaluate()`로 복귀(`main.py` gate endpoint). `gate.py:54-62` `evaluate`는 여전히 `evaluate_metered`를 감싸 `_usage` 폐기 — **도메인 *_metered API는 writing loop 예산용으로 존치**(브리프/작업 AI 주장 정합). ✓
- orphan 정리: `import time`·`MeteredCallError` import·`TokenUsage` import 제거(`main.py` diff). §3 surgical.

### F4. 격리 시행 지점 _flush 한 곳으로 수렴 (직전 검증 H1 코드 반영)
- v1.7.42: 격리 헬퍼 `_record_llm_call`(`main.py`, gate용) + seam C `_flush`(`llm_call_scope.py`, extractor용) — **둘**.
- v1.7.45: `_record_llm_call`·`_record_gate_call` 제거. 격리는 `_flush`(`llm_call_scope.py:122-137`) **한 곳**. SoT `L367` "시행 지점은 `llm_call_scope`의 `_flush` 한 곳이다(v1.7.45)" 정합. finally 안이라 예외가 요청의 원래 예외를 덮어쓴다는 이유도 `L367`에 추가(직전 검증 H1). ✓

### F5. 조립 가드 2건 — 회귀가 못 잡던 갭 해소 (이 슬라이스의 발견)
- **갭**: 모든 회귀가 하네스에서 `ObservedProvider`를 직접 생성하므로, 실 `_default_*` 팩토리가 감싸기를 빠뜨려도 suite가 green. 작업 AI 실측 "gate 조립에서 wrapper 벗기면 56 passed" — 배포에서만 계측이 통째로 사라지는 결함.
- **해결**: `DefaultAssemblyIsInstrumentedTest` 2건.
  - `test_gate_assembly…`(`test_llm_call_scope.py:382`): **행위** — 실 `_default_writing_gate_service(provider=fake)` 팩토리로 서비스 빌드 → `evaluate` → audit에 call_site=WRITING_GATE 레코드 1건. 팩토리에 provider 주입 seam이 있어 가능.
  - `test_extractor_assembly…`(`:410`): **구조** — `_default_analysis_runner`로 runner 빌드 후 `runner._extractor._provider`가 `ObservedProvider`인지 `assertIsInstance`. extractor 팩토리는 provider 주입 seam이 없어 사적 속성으로 구조 검증(테스트에 이유 명시).
- mutation-1/2 로 각각 정확히 해당 가드만 물림을 실증(아래). ✓

### F6. parse_error 재분류 — gate가 annotate_last 첫 사용처, extractor는 안 함 (직전 검증 H4 결론)
- gate endpoint가 `scope.annotate_last(outcome=PARSE_ERROR)`로 SUCCESS→PARSE_ERROR 재분류 — annotate_last의 첫 실사용처.
- **analysis_extractor는 재분류하지 않는다** — repair를 유발한 첫 응답은 "실패"가 아니라 "repair로 회수된 호출"이고, 오너 관심은 실패율이 아니라 **repair 빈도(correlation_id당 레코드 2건)**. 재분류하면 회수된 호출이 실패로 집계돼 성공률이 실제보다 낮아진다. 변경이력 `v1.7.44` 행에 명문화, SoT `L374-375`에 반영. (직전 검증 H4 "gate 이행에서 함께 정하라"를 이렇게 결론지음.) ✓

### F7. 공개 계약 무변
- `git diff fac5676 5e6eeeb -- frontend/src/api/schema.d.ts` → 동일. `56e34f4..5e6eeeb`도 동일. v1.7.43/44/45 세 커밋 schema.d.ts 동일. 도메인·endpoint 응답 무변(응답 계약 37건 무수정 통과)과 정합. ✓

### F8. 증분 +2 = 조립 가드 2건
- after `1423/80/593` ↔ 직전(v1.7.43) `1421/80/593` = **+2 passed**, skip·subtests 동일. `56e34f4`(v1.7.44 문서 정정)은 코드 무변이라 suite 무영향. 신규 2 = 조립 가드. 작업 AI `1497→1499`(+2)와 일치. ✓

### F9. mutation 4종 실증

| 변이 | 코드 변경 | 실측 |
|---|---|---|
| **gate 조립 제거** | `main.py:729` `ObservedProvider` wrapper 벗기기 | `test_gate_assembly` **1 fail**(0≠1), 57 green(WritingGateObservabilityTest 7건은 _client 자체 ObservedProvider라 green — 갭 실증) ✓ |
| **extractor 조립 제거** | `main.py:600` wrapper 벗기기 | `test_extractor_assembly` **1 fail**(구조 `is not ObservedProvider`), 57 green ✓ |
| **parse_error 재분류 제거** | endpoint `except InvalidWritingGateResult: annotate_last(PARSE_ERROR)` 제거 | `test_parse_failure` **1 fail**(outcome만, 토큰 2는 보존→green) ✓ |
| **decision/score annotate 제거** | `annotate_last(decision, gate_quality_score)` 제거 | decision/score군 **6 fail**(`test_successful` 1 + `test_every_gate_decision` 5 subtest), 57 green |

mutation 1/2/3은 각각 해당 회귀만 정밀 물림. mutation 4는 decision/score가 success 레코드 핵심 필드라 decision/score 회귀군(6건)을 동시에 물림 — 약한 게 아니라 **핵심 필드의 중복 보호**. 작업 AI "각각 해당 회귀만"을 decision/score군으로 묶으면 정합(H4 참고).

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 직전 검증의 유일한 blocking이었던 B1(SoT `L372` 자기 모순)이 사이 커밋 `56e34f4`(v1.7.44)에서 해소됐음을 본 검증에서 확인 — `L374-377`이 하위 항목으로 분리돼 `analysis_extractor`를 계측됨/후속으로 동시 서술하던 모순이 사라졌고, `*_metered` 서술의 범위 오류(gate endpoint 전용)도 정정됐다. 본 슬라이스(`5e6eeeb`)는 이행·조립 가드·격리 수렴·mutation·no-diff 전부 합격.

### Hardening (non-blocking)
1. **extractor outcome=success-only가 본문에 직접 명시로는 약함.** 변경이력 `v1.7.44` 행에 "seam C site의 parse_error=0은 결손이 아니라 이 범위의 결과"로 명시됐으나, 본문 `L374-375`의 extractor 항목은 "본 호출과 repair 재시도가 함께 묶인다" 정도로 outcome success-only를 암시만. 증분 5(집계 API)가 이 범위를 읽을 때 본문에 outcome=success-only가 명시적이면 집계 분모 해석이 단단해진다.
2. **mutation 4(decision/score)가 6건을 물림** — 작업 AI "각각 해당 회귀만"의 엄격한 1:1 해석과는 다름. 단 decision/score가 success 레코드 핵심 필드라 중복 보호는 강점이지 약점이 아님. 보고의 정확성을 위해 명시.

## Verdict

**합격 (조건 없음).**

하중 이유:
1. **이행 무손실 확정** — gate 회귀 44건(관측 7 + 응답 37)이 이행 전후 한 건도 수정 없이 통과. 데코레이터가 endpoint 계측과 같은 값(model·tokens·decision·파생점수)을 생산.
2. **parse 토큰 2 보존 메커니즘 확인** — ObservedProvider.add(SUCCESS, tokens) + annotate(outcome)의 분리. mutation-3이 outcome만 fail시키고 토큰은 green으로 증명.
3. 경계 매트릭스 8 cell 전부 명명 회귀로 lock — 빈 cell 없음.
4. mutation 4종 — 조립 가드 2·parse 재분류 1이 정밀, decision/score군 6이 중복 보호.
5. 조립 가드 2건이 "배포에서만 계측이 사라지는" 갭을 잠금 — 회귀가 못 잡던 결함의 해소.
6. 격리 `_flush` 한 곳 수렴(직전 검증 H1 코드 반영).
7. 공개 계약 무변(schema.d.ts v1.7.43/44/45 동일).
8. 증분 +2 양쪽 일치.
9. **직전 검증 B1(조건부 합격 조건)이 `56e34f4`에서 해소됐음을 확인** — 검증-피드백 루프 정상(B1·H1·H3·H4 전부 반영).

hardening 2건은 non-blocking(본문 명시 보강·mutation 보고 정확성).

## Outstanding items (오너 다음 단계에 영향)

- **작업 AI가 제안한 다음 순서**: 증분 C — `compare_judge`(candidate당 1회→N레코드)·`query_planner`(revise loop 내부)·`writing_generation`(reporter 붙으면 2회, `generate_metered` 부재). 각각 **조립 가드를 함께 넣는다**(이 슬라이스가 입증한 패턴). 그 다음 증분 5(집계 API) — 집계 규칙 2개(토큰은 `success`+`parse_error`만, repair 빈도는 correlation_id당 레코드 수)가 이미 계약에 고정. "계속 갈까요?"로 오너에게 물음 — 오너 결정.
- **hardening #1**: 증분 5 착수 전 본문에 extractor outcome=success-only 명시 권장.
- 라이브 확증: gate·extractor seam C가 배포 경로에서 실제 레코드를 생산하는지 라이브 12B로 확인하면 완전(스택 기동은 오너 몫). 본 검증은 더블 경로 + 조립 가드로 정확성 확보.

## Reproduction

```bash
# focused (gate 44 + scope 14, 이행 무손실 + 조립 가드)
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB \
  python3 -m pytest tests/test_writing_gate.py tests/test_llm_call_scope.py -q
# → 58 passed, 41 subtests

# 전체 after (이 머신, 2026-07-25, test-mongo 미기동)
env -u CORE_SOT_MONGO_URI -u CORE_SOT_MONGO_DB -u ELASTICSEARCH_URL \
  python3 -m pytest -q -p no:cacheprovider
# → 1423 passed, 80 skipped, 593 subtests
# (작업 AI 환경 test-mongo 기동: 1499 / 593 — 증분 +2 양쪽 일치)

# 증분 +2 — 직전 독립검증 측정(v1.7.43 동일 머신) 1421/80/593 와 비교
# (56e34f4 v1.7.44 문서 정정은 코드 무변; before fc5676/fac5676 suite 재측정은
#  git checkout classifier 제약으로 생략 — focused 58 + 증분 +2 로 확정)

# gen:api no diff (세 커밋 schema.d.ts 비교)
git diff fac5676 5e6eeeb -- frontend/src/api/schema.d.ts      # 동일
git diff 56e34f4 5e6eeeb -- frontend/src/api/schema.d.ts      # 동일

# mutation 4종 — 각각 Edit 적용 → focused pytest → 역방향 Edit 원복
#   gate 조립:      main.py:729 의 ObservedProvider(...) wrapper 벗기기
#   extractor 조립: main.py:600 의 ObservedProvider(...) wrapper 벗기기
#   parse 재분류:   gate endpoint except InvalidWritingGateResult 의 annotate_last(PARSE_ERROR) 제거
#   decision/score: gate endpoint 끝 annotate_last(decision, gate_quality_score) 제거
#   각 후: env -u CORE_SOT_MONGO_URI python3 -m pytest tests/test_writing_gate.py tests/test_llm_call_scope.py -q
#   역방향 원복 후 diff /tmp/main45.after services/application/app/main.py  (no diff)
```
