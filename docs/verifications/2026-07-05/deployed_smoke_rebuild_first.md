# Verification — Phase 4 deployed context-search smoke 2-step 확장 (commit 5389f51)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("다음작업 검증해줘. 커밋 완료. ... 2. 다음 작업 — deployed smoke의 공유 index 관통 검증 확장 (5389f51) ...")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; 직전 shared vector index slice 검증(`docs/verifications/2026-07-05/shared_vector_index_slice.md`)도 동일 세션)
- 대상 slice/artifact: commit `5389f51` "Extend Phase 4 deployed context-search smoke to rebuild first" — `scripts/phase4_context_search_deployed_smoke.py`(rebuild 호출 추가 + `smoke_succeeded` exit 규칙 + summary 필드), `tests/test_phase4_context_search_deployed_smoke_script.py`(회귀 4→5개 + CLI 3-way). 동일 세션의 선행 커밋 `7356259`(shared vector index slice + 검증 기록 포함)도 범위에 포함(재검증 대상인지 확인).
- 정본 계약 참조:
  - `docs/plans/04-shared-vector-index-decisions.md`(상태 `Approved (2026-07-05)`) — 수용기준 A1(rebuild → context-search 같은 app 인스턴스에서 vector hit), "후속 (이 slice 범위 밖)" 단락은 아니지만 HANDOFF Next Tasks 1이 동일 gap 지적.
  - `docs/system-contract-sot.md` v1.6.35 — §Phase 3A rebuild HTTP API(367행, 공유 index write), §Phase 4(378행).
  - 직전 검증 `docs/verifications/2026-07-05/shared_vector_index_slice.md` — 이 slice가 in-process 단위로 잠근 rebuild→context-search hit을 deployed HTTP 경로로 확장하는 후속.
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`5389f51`), working tree clean(2 커밋, origin 미푸시).

## Scope

1. 커밋 범위 확인 — `7356259`(shared index slice)와 `5389f51`(smoke 확장)의 분리, `7356259`가 직전 검증 합격 working tree + 검증 기록(156행)을 그대로 커밋한 것인지 재확인.
2. 계약 스코핑 — 직전 브리프 수용기준 A1 + HANDOFF Next Tasks 1 지적(deployed smoke가 rebuild를 호출하지 않아 배포 경로 vector hit 미검증)이 이 slice의 계약 근거. 별도 브리프 없는 "브리프 불필요한 후속"이라는 작업자 주장이 타당한지.
3. smoke script 2-step 흐름 — save version → snapshot_id 추출 → rebuild POST → search POST 순서, rebuild가 search보다 먼저 호출되는지.
4. exit 규칙 boundary matrix — `smoke_succeeded = rebuild 200 AND search 200`의 should-fire/should-NOT-fire/under-strict cell을 회귀에 매핑; **rebuild 실패 + search 200 → 실패** 핵심 boundary의 under-strict guard 존재.
5. summary 필드 전파 — `snapshot_id`/`rebuild_http_status`/`rebuild_records_written`/`rebuild_backend`가 200일 때만 채워지는 조건부 전파.
6. **exit 규칙 mutation**(핵심) — `smoke_succeeded`를 이전 `search_succeeded`(search-only)로 되돌려 re-fail 실증.
7. MockTransport 한계 인식 — 회귀가 rebuild가 실제 shared index를 채우는지(in-process hit)를 검증하는지, 아니면 HTTP orchestration + exit 규칙만 검증하는지 구분. worker의 "real in-process app... micro_count=6" 실증이 회귀인지 수동 실행인지.
8. suite 카운트 독립 재현(474 OK / pytest 430).

## Methodology

- 커밋 분리 확인: `git show --stat 7356259 5389f51`로 두 커밋이 독립적이고 `7356259`가 직전 검증 대상(working tree) + 검증 기록을 커밋한 것인지 확인.
- 계약 스코프: 직전 브리프 수용기준 A1 + HANDOFF Next Tasks 1만 종단 독해. real Chroma/prior-memory/tool-call planner는 스코프 밖.
- boundary matrix 구축 후 exit 규칙 각 cell을 5개 회귀에 수동 매핑.
- **경험적 mutation testing**(핵심): `scripts/phase4_context_search_deployed_smoke.py`를 `/tmp`에 cp 백업 → `smoke_succeeded`를 `summary.get("search_http_status") == 200` 단일 조건으로 치환(rebuild gate 제거) → `python3 -m unittest tests.test_phase4_context_search_deployed_smoke_script -v` 재실행 → re-fail 수/메시지 기록 → 백업에서 cp 복원 → `diff -q`로 byte-identical 확인.
- 테스트 실행: smoke 회귀 단독, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `git diff --check`.
- MockTransport 한계: test handler가 `micro_evidence`/`records_written`을 하드코딩하는지 직접 읽어 확인 — 회귀가 실제 shared index 관통을 검증하는지 아니면 mock 응답 파싱만 하는지 구분.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. 커밋 범위 — 부합 (7356259 재검증 불필요, 5389f51이 이번 주 대상)

- `7356259` "Add Phase 4 shared in-process vector index (SoT v1.6.35)": 직전 검증(`shared_vector_index_slice.md`)에서 합격 판정한 working tree(service.py/main.py/test_context_search_shared_index.py/브리프/SoT v1.6.35/work_log)을 그대로 커밋 + 검증 기록(156행) 포함. 추가 회귀나 코드 변경 없음(`git show --stat`로 파일 목록이 직전 검증 대상과 동일). commit message "Both new guards proven non-vacuous by mutation (shared wiring removal AND snapshot-scope filter removal)"은 직전 검증 기록의 Mutation A+B(verifier 보강 포함)를 반영. **재검증 불필요** — 직전 검증 합격 그대로.
- `5389f51` "Extend Phase 4 deployed context-search smoke to rebuild first": smoke script(+42) + test(+105) + CHANGELOG/HANDOFF/work_log(+14). 이것이 이번 검증의 주 대상.

### 2. 계약 자기 일관성 + "브리프 불필요" 타당성 — 부합

- 직전 브리프 수용기준 A1 "같은 app 인스턴스에서 snapshot rebuild → 그 draft 위치로 context search → vector need가 stale guard + SOT 재조회 통과한 실제 hit"은 in-process 단위로 잠겨 있었고(`test_context_search_shared_index.py`, 직전 검증 합격). 이 slice는 그것을 **deployed HTTP 경로로 확장**하는 후속.
- HANDOFF Next Tasks 1(직전 검증 당시)이 "deployed smoke가 현재 rebuild를 호출하지 않아, 배포 환경에서 공유 index의 실제 vector hit을 관통 검증하려면 rebuild → context-search 2-step으로 확장하거나 수동 실행이 필요"라고 지적 — 이 slice가 정확히 그 gap을 닫음.
- 작업자 주장 "브리프 불필요한 후속" 타당: 새 계약/리터럴/상태 전이를 도입하지 않고 기존 수용기준 A1의 검증 표면(smoke)을 확장만 하므로 SoT 변경 없이 진행 가능. SoT v1.6.35에 deployed smoke 세부는 본래 기술 대상이 아님(smoke는 운영 검증 산물).

### 3. smoke script 2-step 흐름 — 부합

- `run_deployed_context_search_smoke`(`phase4_context_search_deployed_smoke.py:70-137`): project/draft/version 생성 → `snapshot_id = saved["snapshot"]["id"]`(91행) → rebuild POST(96-99행) → `_safe_json(rebuild_response)`(100행) → search POST(102-110행). rebuild가 search보다 **먼저** 호출됨.
- 순서 보장 lock: test handler가 search 도달 시 `assert ("POST", ".../rebuild") in calls`(test:69-73행)로 rebuild가 선행했는지 검증 + `summary_step_order_rebuild_before_search(calls)`(test:260-264행)가 `paths.index(rebuild) < paths.index(search)`로 실제 호출 순서 검증. 이중 lock.
- summary 조건부 필드 전파: rebuild 200 + dict인 경우만 `rebuild_records_written`/`rebuild_backend` 채움(script:123-125행); search 200 + dict인 경우만 package 필드 채움(126-136행). rebuild 실패 시 rebuild 필드 누락, search 실패 시 package 필드 누락 — `test_error_status_is_captured_without_package_fields`(test:122-154행)가 search 502일 때 `gate_decision not in summary`로 검증.

### 4. exit 규칙 boundary matrix — 모든 cell lock, 빈 cell 없음

| cell | 계약 | 방향 | lock 회귀 | 비고 |
|---|---|---|---|---|
| rebuild 200 + search 200 → 성공 | exit 규칙 | should-fire | `test_run_smoke_...`(test:120 `smoke_succeeded(summary)` True) + CLI `ok_run`→0 | ✓ |
| search 실패(502) → 실패 | exit 규칙 | should-NOT-fire | `test_error_status...`(test:154 `assertFalse`) + CLI `search_err_run`→1 | ✓ |
| **rebuild 실패(404) + search 200 → 실패** | exit 규칙 **핵심** | should-NOT-fire | **`test_rebuild_failure_fails_the_smoke_before_search`(test:156-189, 신규)** + CLI `rebuild_err_run`→1 | ✓ 핵심 |
| rebuild 선행 순서 | 수용기준 A1 | should-fire | handler 내 assert + `summary_step_order_rebuild_before_search` | ✓ |
| rebuild summary 필드 전파 | exit/summary | literal | `test_run_smoke_...`(rebuild_records_written=2, rebuild_backend=in_memory_fake) | ✓ |
| search 실패 시 package 필드 누락 | summary 안전 | should-fire | `test_error_status...`(`gate_decision not in summary`) | ✓ |
| rebuild 후 vector hit(micro) | SoT v1.6.35 관통 | should-fire | `test_run_smoke_...`(micro_count 0→1) | ✓ 단, mock 응답 기반(§6) |

`test_rebuild_failure_fails_the_smoke_before_search`(test:156-189)와 CLI 3-way(test:208-234)가 rebuild 게이트를 양방향으로 lock. docstring(test:185-186) "A search 200 is not enough: a failed rebuild fails the smoke, so the exit rule genuinely gates on both statuses"가 boundary 의도를 명시 — 회귀 품질 우수.

### 5. exit 규칙 mutation — re-fail 실증 (핵심 boundary under-strict)

| mutation | 무력화 | 결과 | 의미 |
|---|---|---|---|
| `smoke_succeeded` rebuild gate 제거 | `return summary.get("search_http_status") == 200` 단일 조건(이전 `search_succeeded`로 회귀) | **2 re-fail**: `test_rebuild_failure_fails_the_smoke_before_search`(`AssertionError: True is not false`) + CLI `test_main_exit_rule_is_two_directional`(`AssertionError: 0 != 1`) | under-strict guard ✓ — rebuild 실패 시 smoke가 통과로 위장하는 회귀 도입 시 test 3 + CLI rebuild_err가 즉시 잡음 |

- 복원: `/tmp` 백업에서 cp 복원 후 `diff -q`로 byte-identical 확인, smoke 회귀 5개 재통과.
- 작업자 commit message "the exit rule is now smoke_succeeded (rebuild 200 AND search 200), so a failed rebuild fails the smoke even if the search would return 200" — mutation으로 검증된 그대로 정확.

### 6. MockTransport 한계 인식 — 회귀는 orchestration/exit 규칙 lock, 실제 shared index 관통은 별도 표면

- 회귀 5개는 전부 `httpx.MockTransport(handler)` 기반(test:101, 145, 179). handler가 rebuild 응답을 `{"backend": "in_memory_fake", "records_written": 2}`(test:54)로, search 응답의 `micro_evidence`를 `[{"need": "source_quote"}]`(test:80)로 **하드코딩**. 즉 회귀는 smoke script의 HTTP 호출 순서·summary 파싱·exit 규칙을 검증하지, **rebuild가 실제로 shared index를 채워 search가 실제 hit하는지(in-process vector 관통)는 검증하지 않음**.
- 작업자 주장 "Driven against a real in-process app (real endpoints + shared index, fake planner) via ASGITransport: rebuild_records_written=6, micro_count=6, gate pass" — 이것은 commit message에 기술된 **수동 실행 결과**이지, `tests/test_phase4_context_search_deployed_smoke_script.py`의 회귀가 아님. 회귀 파일에 ASGITransport 기반 real-app 경로 테스트는 없음(grep 확인: 전부 MockTransport).
- 다만 이것은 **결함이 아니다**: in-process 단위의 "rebuild가 shared index를 채우면 context-search가 hit"은 직전 slice(`test_context_search_shared_index.py`, 직전 검증 합격)가 이미 실제 app 기반으로 lock. 이 slice는 그것의 **deployed HTTP orchestration + exit 규칙** 표면을 lock하며, 실제 배포 관통(12B + compose)은 live 실행에 의존 — 작업자도 "compose stack + 실제 12B 관통 live 실행만 sandbox 밖 승인 네트워크로 남았습니다"로 명시. 역할 분담 타당.
- 비차단 관찰: worker의 commit message "real in-process app... via ASGITransport" 문구가 회귀가 아닌 수동 실증을 가리키지만, 회귀가 MockTransport라는 점과 혼동의 여지가 있다. 회귀로 real-app 경로를 하나 더 두면 이 표면도 lock 가능하나, 직전 slice 회귀가 이미 in-process hit을 lock하므로 중복이 됨. 비차단.

### 7. suite 카운트 + envelope 주장 독립 재현 — 부합

- smoke 회귀 단독 `python3 -m unittest tests.test_phase4_context_search_deployed_smoke_script -v` → Ran 5, OK(회귀 4→5 주장 재현: 신규 `test_rebuild_failure_fails_the_smoke_before_search` 추가, 기존 happy path의 micro_count 0→1·rebuild 필드·순서 검증 보강, CLI 2-way→3-way).
- `python3 -m unittest discover tests` → **Ran 474, OK (skipped=44)** — 작업자 주장(474 OK/44 skip) 재현(직전 473에서 +1).
- `python3 -m pytest -q` → **430 passed, 44 skipped** — 작업자 주장(pytest 430) 재현(직전 429에서 +1).
- `git diff --check` → 통과(working tree clean, 2 커밋).

## Issues / Risks

1. **(비차단, 표면 분담) 회귀는 MockTransport 기반** — §6에서 상술. 회귀가 smoke script의 HTTP orchestration·exit 규칙·summary 파싱은 lock하지만, rebuild가 실제 shared index를 채워 vector hit이 발생하는 in-process 관통 자체는 lock하지 않는다. 이것은 직전 slice 회귀(`test_context_search_shared_index.py`)가 담당하므로 역할 분담이 타당하고, 결함이 아니다. 다만 worker의 "real in-process app via ASGITransport" 실증이 commit message에는 있으나 회귀로는 commit되지 않았으므로, 향후 이 표면을 회귀로 굳히려면 ASGITransport + fake planner + shared index 기반 단위 테스트를 smoke script test에 추가하면 된다(직전 slice와 중복이므로 우선순위 낮음).

2. **(out of scope, not a defect) live/deployed 관통 미실행** — compose stack + 실제 12B planner로 rebuild → context-search를 관통하는 live smoke는 sandbox 밖 승인 네트워크가 필요해 미실행. HANDOFF Next Tasks 1에 후속으로 기록되어 있고, 본 검증(코드/회귀 단위)의 합격 여부와 무관.

3. **(정보) 직전 검증의 mutation 범위 불완전이 7356259 commit message로 반영** — 직전 검증에서 지적한 "작업자 mutation 증명이 snapshot-scope 필터를 누락"이 7356259 commit message "Both new guards proven non-vacuous by mutation (shared wiring removal AND snapshot-scope filter removal)"로 반영됨(verifier 보강 결과가 commit message에 정확히 전파). 단 work_log 본문은 여전히 worker 자체 mutation(shared wiring)만 서술하므로, work_log↔commit message 간 mutation 범위 서술에 약간의 비대칭이 있으나 둘 다 사실이고 계약 위반 아님.

## Verdict

**합격.**

load-bearing 이유:
- 커밋 분리 명확: `7356259`는 직전 검증 합격 working tree + 검증 기록을 그대로 커밋(재검증 불필요), `5389f51`이 이번 검증 주 대상.
- "브리프 불필요한 후속" 타당: 기존 수용기준 A1의 검증 표면 확장만 하고 새 계약/리터럴 도입 없음.
- exit 규칙 boundary matrix의 모든 cell이 5개 회귀에 매핑되고 빈 cell 없음. 특히 핵심 boundary **"rebuild 실패 + search 200 → smoke 실패"**가 신규 `test_rebuild_failure_fails_the_smoke_before_search` + CLI 3-way로 양방향 lock.
- exit 규칙 mutation(`smoke_succeeded` rebuild gate 제거)으로 2개 re-fail 실증 → 핵심 boundary가 under-strict로 잠겨 있음을 직접 증명.
- 2-step 순서(rebuild 선행)가 handler assert + helper로 이중 lock.
- suite 카운트(474 OK/44 skip, pytest 430/44 skip) 독립 재현.

조건 사유: 없음. 비차단 관찰(MockTransport 한계→역할 분담 타당, live 실행 미실행→sandbox 밖, work_log↔commit message 비대칭→둘 다 사실)은 합격을 뒤집지 않는다.

## Outstanding items

- **origin 미푸시**: branch `phase4-slice-4-2-planner`가 origin 대비 2커밋 ahead. owner 요청 시 push.
- **live/deployed 관통 smoke**: compose stack + 실제 12B로 rebuild → context-search 2-step을 관통하는 live 실행이 sandbox 밖 승인 네트워크에서 필요. HANDOFF Next Tasks 1에 기록됨. 본 검증과 무관.
- **큰 방향 결정**: B(real Chroma/ES persistent backend) / C(prior-memory purpose) / D(tool-call planner 전환) 중 어느 것을 진행할지 owner 우선순위 결정 필요(HANDOFF Next Tasks 1). 본 검증과 무관.

## Reproduction

```bash
# 1. smoke 회귀 단독 (5개)
python3 -m unittest tests.test_phase4_context_search_deployed_smoke_script -v   # Ran 5, OK

# 2. 전체 suite (474 OK / 44 skip, pytest 430 / 44 skip)
python3 -m unittest discover tests                                                # Ran 474, OK (skipped=44)
python3 -m pytest -q                                                              # 430 passed, 44 skipped

# 3. whitespace 검사
git diff --check                                                                  # clean (working tree clean)

# 4. exit 규칙 mutation — smoke_succeeded rebuild gate 제거 → 2 re-fail
cp scripts/phase4_context_search_deployed_smoke.py /tmp/smoke.py.bak
# Edit smoke_succeeded 본문을 "return summary.get("search_http_status") == 200" 단일 조건으로 치환
python3 -m unittest tests.test_phase4_context_search_deployed_smoke_script -v
#   → 2 failures:
#     test_rebuild_failure_fails_the_smoke_before_search (AssertionError: True is not false)
#     test_main_exit_rule_is_two_directional (AssertionError: 0 != 1)
cp /tmp/smoke.py.bak scripts/phase4_context_search_deployed_smoke.py             # 복원
diff -q /tmp/smoke.py.bak scripts/phase4_context_search_deployed_smoke.py        # identical
python3 -m unittest tests.test_phase4_context_search_deployed_smoke_script        # Ran 5, OK

# 5. 커밋 분리 확인
git show --stat 7356259 | tail -5        # shared index slice + 검증 기록(156행) 포함
git show --stat 5389f51 | tail -5        # smoke script(+42) + test(+105)
```
