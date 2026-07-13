# Verification — v1.6.79 Writing loop-audit opt-in delta (independent re-verification)

이 기록은 `docs/verifications/2026-07-13/writing_persisted_loop_audit.md`의 후속 verifier
대상("v1.6.79 opt-in delta independent re-verification is a follow-up verifier target",
동 기록 :158 / HANDOFF.md:94)을 수행한 **독립 검증**이다. 동일 주제의 연속이지만 SoT 버전·검증
범위·source-of-work가 다르므로 별도 파일로 남긴다.

## Subject metadata

- **Date**: 2026-07-13
- **Requester**: owner ("검증하고 의심하고 또 의심해줄래" — v1.6.79 delta 독립 재검증 요청)
- **Verifier**: Claude (session verifier, 작업자·선행 verifier와 별개 컨텍스트)
- **Target slice**: SoT v1.6.79 P2=A→B opt-in 재개정 delta — `persist_audit` request flag +
  env `WRITING_LOOP_AUDIT_DEFAULT`(기본 off) + persist try/except 격리 + `audit_error`
  additive envelope. v1.6.78의 P1/P3/P4/P5 불변식은 delta 밖이나 회귀로 재확인한다.
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.79 version-table row(line 36) + header `v1.6.79`
  - `docs/plans/05-writing-persisted-loop-audit-decisions.md` "P2 재개정"(line 5-13),
    "승인 후 첫 회귀 경계" §108-116(불변 항목)
  - 선행 검증 `docs/verifications/2026-07-13/writing_persisted_loop_audit.md`(v1.6.78 +
    B1/H1/H2 closure addendum)
  - Parent invariant: SoT v1.6.77 bounded-loop behavior(delta 불변)
- **Source of work being verified**: **commit `81f8a8a`**(working tree clean). 선행
  verifier 기록은 "working tree, uncommitted"였으나, 현재는 커밋됐다. owner 발언
  "커밋은 안 했습니다"와 실제 `git status`(clean, `81f8a8a` 존재)가 충돌하므로 검증 대상은
  해당 커밋으로 확정한다.

## Scope

1. **Contract read** — SoT v1.6.79 row, brief "P2 재개정" §5-13, "승인 후 첫 회귀 경계" 중
   delta가 건드리는 항목("모든 종료 감사"→"persist on일 때만", persist 실패 격리, `audit_error`
   taxonomy)과 유지되는 불변(P1/P3/P4/P5, side-effect 0, 감사 레코드/읽기 계약).
2. **Implementation code** — `main.py` persist 게이트(:2768-2771), `_record_loop_audit`
   try/except 격리(:2773-2794), 5 종료 사이트의 `audit_id`/`audit_error` additive
   (:2830-2972), `_writing_loop_audit_payload`/`_summary_payload`(:2389-2419),
   `_default_writing_loop_audit_service`(:368-378), `_env_bool`(:433-437),
   `WritingLoopStage` additive 필드(`revise_gate.py:112-119`), `record()` closure
   (:212-225), 종료 path들.
3. **Regression tests** — `tests/test_writing_loop_audit.py`(19 tests / 6 subtests),
   `tests/test_writing_loop_audit_mongo.py`(3 tests). opt-in 3종 신규 회귀 + 기존 잠금.
4. **Public envelope/schema** — opt-in 응답(`audit_id`/`audit_error` 5경로), detail 15-key /
   stage-row 6-key exact-set(B1, v1.6.78 closure), summary 8-key.
5. **Test suite** — focused(loop-audit), full non-Mongo.
6. **Mutation re-bite** — exact-set lock(stage/top/summary) + 성공-path `audit_error`
   nullness probe.

Out of scope(per brief): loop 행동 정책(v1.6.77 불변), 전체 artifact 본문(P1=C),
token/latency 집계(B2), retention TTL, frontend.

## Methodology

- **Scope-first**: v1.6.79 row + brief "P2 재개정"에서 boundary matrix를 먼저 그린 뒤 코드를 열었다.
- **Primary-source re-derivation**: 선행 verifier·작업자의 claim을 복사하지 않고 코드/테스트/SoT
  literal에서 재도출했다.
- **Adversarial mutation(two-directional)**: exact-set lock(stage row / top-level /
   summary 대조)에 계약 위반 필드를 주입해 bite를 확인; 별도로 성공-path `audit_error`
   nullness 셀을 probe해 빈 셀을 증명했다.
- **Smoke run 재현**: 보고 숫자(947/45/215)와 직접 비교.
- **Commands**(exact):
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`(full)
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -rs -p no:cacheprovider | grep -i skip`
  - `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py`
  - mutation harness(`/tmp/mutate_loop_audit.py` — main.py의 직렬화 3 surface + 성공-path
    nullness에 계약 위반 필드를 주입/`git checkout` revert). 본 기록의 Reproduction 참조.

## Findings

### 1. Contract read — v1.6.79 opt-in boundary matrix

"filled" = contract-required 분기가 named regression에 매핑되어 위반 시 실패; **EMPTY** =
contract-required 분기에 추적 테스트 없음.

| # | Clause(fire / NOT fire) | Tracing test | Cell |
|---|---|---|---|
| O1 | `persist_audit=true` → 종료 1 record + `audit_id` 반환 | `test_success_loop...`(persist=True 기본), `test_every_termination...`, `test_each_non_pass_200_status...`, `test_retrieval_stages...` | filled |
| O2 | flag 없음 + env 없음 → persist 안 함, `audit_id=null` **and** `audit_error=null` | `test_opt_in_default_off_persists_nothing`(persist=None) | filled |
| O3 | explicit `persist_audit=False` → persist 안 함 | `test_opt_in_default_off...`(persist=False), `test_env_default...`(disabled) | filled |
| O4 | env `WRITING_LOOP_AUDIT_DEFAULT=true` → flag 없이 persist | `test_env_default_enables_audit_without_request_flag`(enabled, persist=None) | filled |
| O5 | request flag가 env default를 override(`False` beats env `true`) | `test_env_default...`(disabled = env true + flag False → off, list에 enabled 1건만) | filled |
| O6 | persist 쓰기 실패 → loop 결과 보존(200, gate intact) + `audit_id=null` + `audit_error` | `test_persist_failure_is_isolated_from_the_loop_result`(`_RaisingRepo`) | filled |
| O7 | persist 실패 `audit_error.type == "audit_persist_error"` | `test_persist_failure...`(:342) | filled |
| O8 | persist 실패 `audit_error.detail`에 예외 메시지 포함 | `test_persist_failure...`(:343) | filled |
| O9 | **persist 성공 시 `audit_error == null`**(SoT v1.6.79 "persist 미요청/성공 시 null") | — (성공-path 응답이 `audit_error`를 assertion하지 않음) | **EMPTY — B2** |
| O10 | pre-loop 요청 거부(400)는 flag on이어도 미감사 | `test_pre_loop_rejection_is_not_audited`(persist=True 기본, duplicate anchor → 400 → list []) | filled |

delta 밖 불변(v1.6.78 잠금 유지 — 회귀로 재확인):
- **P1=B** bodyless per-stage trail + final text: `test_record_captures_bodyless_trail_and_final_text`, detail 15-key / stage-row 6-key exact-set(`test_success_loop...:271-281`) — mutation 재-bite 본 기록 §4.
- **P3=A** append-only(retry=새 id): `test_retry_appends_a_new_run_and_never_mutates`, `test_retry_appends_distinct_runs...`.
- **P4=A** list/detail + project isolation + cross-project 404: `test_list_is_project_scoped...`, `test_get_rejects_cross_project_and_missing`, `test_project_isolation_on_list_and_detail`.
- **P5=A** immutable(`frozen=True, slots=True` dataclass): `test_retry_appends_a_new_run...`(`first.loop_status="changed"` → FrozenInstanceError).
- **side-effect 0**(`_NoWriteCoreSotService.save_draft` spy): `test_audit_write_does_not_save_to_core_sot`.
- **`final_candidate_hash == stages[-1].candidate_hash`** 모든 path: `test_success_loop...`(:257-258) 명시 + 코드 추적으로 모든 path에서 by construction 성립 확인(본 기록 §3).

### 2. Implementation code(primary-source)

- **persist 게이트**(`main.py:2768-2771`): `body.persist_audit if not None else _env_bool("WRITING_LOOP_AUDIT_DEFAULT", False)`. request flag가 env default를 override — O4/O5와 정확히 일치. `_env_bool`(:433-437)는 env 미설정 시 default, 값이 `{"0","false","no"}` lower 외면 True. `"true"→True` ✓(O4).
- **`_record_loop_audit`**(:2773-2794): `if not persist_audit: return None, None`(O2/O3). try 블록에서 `writing_loop_audit.record(...)`, 실패 시 `except Exception`이 `(None, {"type":"audit_persist_error","detail":str(exc)})` 반환(O6/O7/O8). 성공 시 `(run_id, None)` 반환(:2792) — O9는 코드 구조로 `None`을 보장하지만 assertion은 없다(§4 빈 셀).
- **5 종료 사이트**: `WritingReviseReportFailure`(:2830)/`WritingLoopRevisionFailure`(:2864)/`WritingRetrievalFailure`(:2906)/`WritingReviseGateFailure`(:2937)/정상 success(:2960)가 모두 `_record_loop_audit`를 호출하고 응답에 `audit_id`+`audit_error`를 additive로 싣는다. pre-loop 거부(`WritingRevisionError`/`InvalidContextSearchRequest`→400, `InvalidWritingRevision`→502, `ContextSearchBudgetExceeded`→504, `ContextSearchFailed`→502, `ProviderError`)는 `run()`/`build_context_package()` 호출 *전*이므로 `_record_loop_audit`에 도달하지 않는다(O10). `run()` 내부 예외는 typed failure로 래핑되어 별도 except로 간다(선행 verifier 재확인).
- **직렬화 3 surface**(:2389-2419): summary 8-key, detail = summary + 7-key = **15-key**, stage-row **6-key**. `audit_error`/`audit_id`는 응답 envelope의 additive 키이지 직렬화 payload가 아니다.
- **`WritingLoopStage`**(`revise_gate.py:112-119`): `candidate_hash`/`finding_fingerprint`/`pointer_ids` additive(default). `_writing_stages_payload`(:2382-2387)는 `stage/ordinal/status` 3-key만 노출 → 감사 필드가 ephemeral 응답에 누수 없음(선행 verifier가 잠금; `test_writing_revise.py` exact-dict로 유지).

### 3. `final_candidate_hash == stages[-1].candidate_hash` — by construction(독립 추적)

선행 verifier의 "by construction" 주장을 부정하려 추적했다:
- `record()` closure(`revise_gate.py:212-225`)는 매 호출 시 `hash_text(current_candidate.text)`를 `candidate_hash`로 찍는다.
- `refresh_report`(:238-250)는 `current_candidate = await self._reporter.enrich(...)` 갱신을 시도; enrich 실패 시 **갱신 전** 예외 → record(REPORT FAILED)는 직전 `current_candidate`의 hash, raise되는 `WritingReviseReportFailure(current_candidate, ...)`도 같은 값. enrich 성공 시 갱신 후 record(REPORT COMPLETED)가 **새** hash로 찍히고, 이후 단계 실패 시에도 exc.candidate는 같은 새 값. record와 candidate 갱신 사이에 실패 틈이 없다.
- 모든 exception raise 시 `exc.candidate == current_candidate`(record 마지막 시점)이고 success path는 `result()`가 `current_candidate`를 반환(:232-235). 따라서 `final_candidate_hash = hash_text(final_candidate.text) == stages[-1].candidate_hash`가 모든 path에서 성립. **주장 확인**(반박 실패).

### 4. Mutation re-bite — exact-set lock 양방향(독립 증거)

`/tmp/mutate_loop_audit.py`로 main.py 직렬화에 계약 위반 필드를 주입하고 `tests/test_writing_loop_audit.py`를 돌렸다:

| Mutation | Surface | 잡힌 assertion | 결과 |
|---|---|---|---|
| stage row `candidate_text` leak | detail stage-row | `:278` `all(set(stage)=={6키})` | **1 failed** ✓ |
| top-level `token_usage` | detail top-level | `:271` `set(payload)=={15키}`(`'token_usage'`) | **1 failed** ✓ |
| `token_usage` summary(대조) | summary / detail spread | `:409` 8-key + `:271` | **2 failed** ✓ |
| 성공-path `audit_error` leak(probe) | `_record_loop_audit` 성공 return | (없음) | **16 passed**(빈 셀) |

stage-row mutation이 `:278`, top-level mutation이 `:271`에서 각각 독립적으로 bite → B1 exact-set의 두 부분이 서로 다른 assertion으로 잠금을 담당함이 증명됐다(선행 verifier의 "re-bite 확인" 주장 재현). 모든 mutation 후 `git checkout` revert, `git diff --stat` 빈 출력으로 clean 복귀 확인.

성공-path `audit_error` probe는 16 passed로, "persist 성공 시 `audit_error==null`" forward-defense가 없음(O9 빈 셀)을 결정적으로 보였다.

### 5. Test suite(독립 재실행)

- `tests/test_writing_loop_audit.py` + `_mongo.py` → **19 passed / 6 subtests**(선행 기록 :156 "19 passed / 6 subtests"와 일치).
- full non-Mongo → **944 passed / 48 skipped / 215 subtests**(18.28s).
  - 보고 숫자는 **947 passed / 45 skipped / 215 subtests**. 차이 3 = 제 머신의 `elasticsearch` package 미설치로 `test_context_search_memory_lexical_retrieval.py:231/243/248` 3종이 skip됨(`-rs` 출력으로 확인). **subtests 215 일치**, HANDOFF.md:21이 "이 머신은 ES Python dependency가 있어 종전 skip 3개가 실행됨"으로 명시한 환경 차이. 계약 무관, 문서화됨.
  - 관찰: CHANGELOG v1.6.78 row는 "944/45/213", v1.6.79 row는 "947/45/215"로 기록. v1.6.78 시점 ES 환경 노이즈로 보이나 핵심 아님.

### 6. append-only 방어 관찰(비계약)

`InMemoryWritingLoopAuditRepository.add`(`loop_audit.py:77`)는 `self.entries[run.id] = run` — 같은 id의 덮어쓰기를 **코드로 막지 않는다**. 다만 P3=A 불변("retry=새 id")이 `id_factory`(uuid4 hex)로 id 고유성을 보장하고, `test_retry_appends_a_new_run_and_never_mutates`가 명시적 distinct id로 잠그므로 계약상 append-only는 유지된다. Mongo adapter는 `insert_one` 전용 + 중복 `_id` raise(`_Collection` fake로 잠금). 방어적 관찰만 남긴다(코드 변경 불필요).

## Issues / Risks

### Blocking(contract obligation)

**B2 — 성공-path `audit_error` nullness forward-defense 누락(boundary O9).**

- **Clause**: SoT v1.6.79 row(line 36) "응답에 `audit_error`(성공·실패 5경로 모두, persist 미요청/성공 시 null) 추가" + brief §10 "audit_id=null + audit_error를 additive로 싣는다". "persist 성공 시 null"은 명시적 contract-required "should NOT fire"(`audit_error` should NOT be non-null on persist-success) 분기다.
- **Gap**: `test_success_loop_persists_full_trail_and_returns_audit_id`, `test_env_default_enables_audit_without_request_flag`, `test_each_non_pass_200_status...`, `test_retrieval_stages...` 등 persist-success 응답이 `audit_error`를 assertion하지 않는다. "persist 미요청 시 null"은 `test_opt_in_default_off`(:295)가, "persist 실패 시 non-null + type/detail"은 `test_persist_failure`(:342-343)가 잠그나, **"persist 성공 시 null" 셀만 비어 있다**.
- **Demonstrated**: `_record_loop_audit`의 성공 return을 `(run_id, {"type":"audit_persist_error","detail":"LEAKED"})`로 mutation → `tests/test_writing_loop_audit.py` **16 passed**(bite 없음). 코드는 정확하지만 미래 over-zealous edit(B2 usage plumbing 등)가 성공 응답에 `audit_error`를 잘못 채워도 잡히지 않는다.
- **Fix(trivial, 1 line)**: persist-success를 검증하는 아무 테스트에
  `self.assertIsNone(response.json()["audit_error"])` 추가(예: `test_success_loop...` 또는
  `test_env_default...` enabled 케이스).
- **성격**: `audit_error`는 failure 전용 additive 신호 필드이고, failure 경로(type/detail/`audit_id=null`)는 완전히 잠겨 있으며, 성공 nullness는 코드 구조(`:2792` `return run_id, None`)로 보장된다. 따라서 "오늘 동작이 틀렸다"가 아니라 "미래 regression에 대한 forward-defense 부재"다. 그럼에도 SoT가 명시한 contract-required 분기이므로 본 검증은 이를 blocking으로 분류하고, 오너가 "코드 구조 보장으로 충분, hardening으로 격하"를 선택할 수 있도록 surface한다.

### Hardening recommendations(비차단, 본 delta 범위 밖)

- 없음. v1.6.78의 H1(Mongo round-trip)/H2(4 status) hardening은 이미 채택됐고, 본 delta의 신규 회귀 3종(default-off / env default / persist-failure isolation)은 양방향으로 잠겨 있다. InMemory `add`의 덮어쓰기 미방어(§6)도 P3=A id 고유성으로 계약이 보장되므로 hardening 후보에서 제외.

## Verdict

**조건부 합격(Conditional Pass)** — load-bearing reason: **B2**(boundary O9).

v1.6.79 opt-in delta의 핵심 계약은 모두 잠겨 있다: opt-in 게이트(O1-O5, 양방향), persist 실패
격리 + `audit_error` taxonomy(O6-O8), pre-loop 미감사(O10), 그리고 delta 밖 불변 P1/P3/P4/P5/
side-effect-0/`final==last-stage` 모두 회귀로 유지된다. B1 exact-set(stage/top)은 mutation
re-bite로 두 독립 assertion에서 bite함을 증명했다. smoke 944/48/215는 ES 환경 차이로 설명되고
subtests 215 일치.

유일한 조건은 B2: "persist 성공 시 `audit_error==null`" forward-defense 1-line assertion 추가.
trivial한 test-only 변경이며, 코드는 이미 정확하다. 추가 시 본 기록은 합격으로 re-promote 가능.

오너 판단점: B2를 SoT 명시 contract-required로 보아 blocking을 유지할지, "코드 구조 보장 +
failure 경로 완전 잠금 + additive null field" 성격을 감안해 hardening(비차단)으로 격하할지.
전자를 권장(clarify CLAUDE.md "boundary matrix has no empty cells" 원칙 준수).

## Outstanding items

- **HANDOFF.md:94 "0. v1.6.79 독립 재검증 필요"**: 본 검증으로 delta를 독립 검증했다. 결과가
  conditional pass(B2)이므로, B2 closure 전까지 이 항목을 "검증 완료(조건부 합격, B2 잔존)"로
  갱신하거나, B2 1-line assertion을 추가한 뒤 제거한다. 오너가 결정.
- **커밋 상태**: 작업 트리는 clean, 변경분은 `81f8a8a`에 커밋됨(owner 발언과 상이 — 본 기록
  Subject metadata에 기록). B2 closure는 새 커밋/ amend 필요.
- 선행 검증 기록 `writing_persisted_loop_audit.md`의 verdict는 "v1.6.78 합격 + v1.6.79 follow-up"로
  남아 있다. 본 delta가 합격(promote)되면 선행 기록에 본 파일로의 링크 한 줄을 추가할지도 오너 결정.

## Reproduction

```bash
# focused(opt-in 회귀 포함)
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py
# full non-Mongo(ES 미설정 머신은 944/48/215, ES 설치 머신은 947/45/215)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# skip 차이 확인
python3 -m pytest --ignore=tests/test_memory_mongo.py -rs -p no:cacheprovider 2>&1 | grep -i skip | grep elasticsearch

# B1 exact-set re-bite(stage → :278, top → :271, summary → :409+:271)
# /tmp/mutate_loop_audit.py {stage|top|summary} → pytest tests/test_writing_loop_audit.py → git checkout services/application/app/main.py

# B2 빈 셀 증명(성공-path audit_error leak → 16 passed, bite 없음)
python3 /tmp/mutate_loop_audit.py success_nullness
python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit.py   # expect: 16 passed (closure 전)
git checkout services/application/app/main.py
```

## Closure — B2 (same commit, 2026-07-13)

오너가 "보강할 부분 네가 보강해줘"로 B2 fix를 위임했다(test-only, production 무변).

- **Fix**: `test_success_loop_persists_full_trail_and_returns_audit_id`에
  `self.assertIsNone(response.json()["audit_error"])` 추가(`tests/test_writing_loop_audit.py:250`).
  SoT v1.6.79 "persist 성공 시 `audit_error`=null" contract-required 분기(O9)의
  forward-defense.
- **Bite 확인(독립)**: 본 기록 §4의 `success_nullness` mutation을 다시 넣자 이제
  `:250`에서 **1 failed**(이전 16 passed → 1 failed/15 passed). 빈 셀이 filled됨을
  mutation이 증명한다. mutation revert 후 `git diff --stat` clean.
- **boundary matrix update**: O9 `EMPTY → filled`. 이제 본 delta의 모든
  contract-required 분기(O1-O10)가 named regression에 매핑된다(빈 셀 0).
- **focused**: `tests/test_writing_loop_audit.py` + `_mongo.py` → **19 passed / 6 subtests**.
- **full non-Mongo**: **944 passed / 48 skipped / 215 subtests**(verifier 머신, ES 미설치).
  작업자 머신 기준 947/45/215(ES 설치). B2 closure는 assertion 1줄 추가라 카운트 변화 없음.
- **diff**: `tests/test_writing_loop_audit.py` 3 insertions(production code 무변).

**Verdict update**: 조건부 합격(Conditional Pass) → **합격(Pass)**. 본 delta(v1.6.79 opt-in)의
모든 contract-required boundary가 채워졌다. 오너 판단점(blocking 유지 vs hardening 격하)은
**blocking 유지 + trivial closure**로 해소 — SoT 명시 contract-required를 존중하되 1-line
assertion으로 닫았다. HANDOFF.md "검증 필요" 항목은 제거됐고, 선행 검증
`writing_persisted_loop_audit.md`의 "v1.6.79 follow-up verifier target"도 본 기록으로 closed.
