# Verification — Phase 4 Slice 4.3 follow-ups: empty-shell closure + deployed smoke

## Subject metadata

- 검증일: 2026-07-04
- 요청자: owner ("다음작업 검증해줘. S-1 완료했습니다. Phase 4 context-search deployed smoke 스크립트 ...")
- 검증자: 독립 검증 AI(Claude, 직전 Slice 4.3 검증(`context_search_slice_4_3.md`)과 동일 세션)
- 대상: 브랜치 `phase4-slice-4-2-planner`의 후속 2커밋.
  - `f8699a7` "Close Slice 4.3 conditional-pass empty shells (wall-clock 504, async seam)" — 직전 4.3 검증 차단 조건(E1/S1) 폐쇄. test_context_search.py +30, test_context_search_api.py +30, 본 검증 기록(4_3) +179, work_log/HANDOFF/브리프.
  - `ef0e334` "Add Phase 4 context search deployed smoke script" — `scripts/phase4_context_search_deployed_smoke.py`(신규 166) + `tests/test_phase4_context_search_deployed_smoke_script.py`(신규 189) + CHANGELOG/HANDOFF/work_log.
- 정본 계약 참조:
  - `docs/plans/04-agentic-search-kickoff-decisions.md` §9.3(item 4 오류 매핑 — wall-clock 504).
  - 직전 검증 `docs/verifications/2026-07-04/context_search_slice_4_3.md`(차단 조건 E1/S1 정의 + mutation repro).
  - 기존 관례 `scripts/phase2a_deployed_e2e_smoke.py`, `scripts/phase3a_deployed_rebuild_smoke.py`(deployed smoke 패턴 기준).
- 검증 대상 작업 출처: branch HEAD(`ef0e334`), working tree clean.

## Scope

1. **직전 4.3 검증 차단 조건 폐쇄 재실증** — E1(wall-clock 504 HTTP 매핑), S1(async planner→service seam) 회귀가 실제로 boundary를 pin하는지 mutation으로 확인. "테스트 추가" ≠ "boundary 잠김".
2. deployed smoke 스크립트 — exit rule, payload 구성, run_live/main seam, _safe_json, 기존 phase2a/3a smoke 관례 일관성.
3. self-regression 4개 — 정상 200 / 502 캡처 / CLI exit 양방향 / file-path import의 boundary coverage 및 mutation guard.
4. suite 카운트 독립 재현 + "확정 계약 미건드림(순수 추가)" 주장 확인.
5. live/deployed 12B 검증 주장(코드가 아닌 관찰 기록) 회계.

## Methodology

- 직전 4.3 검증의 mutation repro(E1: endpoint `504→500`, S1: `isawaitable→False`, S2: `isawaitable→True`)을 **동일 문자열 치환**으로 재적용하고, 이번에 추가된 회귀가 re-fail하는지 확인. 폐쇄의 결정적 증거 = 이전엔 OK(빈 셸)이던 mutation이 이제 re-fail.
- deployed smoke 스크립트 mutation: exit rule 반전(D1), payload needs 변경(D2) → self-regression re-fail 확인.
- 테스트 실행: `python3 -m unittest discover tests`, `python3 -m pytest -q`, `git diff --check main...HEAD`, `git show --stat`로 두 커밋의 코드-vs-문서 변경 분리.
- 기존 smoke 관례: `phase3a_deployed_rebuild_smoke.py`의 `run_live`/`main(run_live_fn=)`/`return 0 if <status> else 1` 구조와 대조.
- 본 검증은 결함을 silently fix하지 않음.

## Findings

### 1. 직전 4.3 차단 조건 폐쇄 — 부합 (mutation으로 양방향 재실증)

직전 검증(`context_search_slice_4_3.md` Issues 1·2)이 빈 셸로 지적한 E1/S1이 회귀로 폐쇄됐고, 동일 mutation이 이제 re-fail함을 확인:

| 셸 | 보강 회귀 | mutation(직전 4.3과 동일) | 직전 결과 | 이번 결과 |
|---|---|---|---|---|
| **E1** wall-clock 504 매핑 | `test_wall_clock_budget_exceeded_is_504`(test_context_search_api.py: `_AdvancingClock([0.0,100.0])` + `wall_clock_seconds=0.01` → 504) | endpoint `504→500` | **OK(빈 셸)** | **FAILED(failures=1)** ✓ |
| **S1** async planner→service seam | `test_async_planner_is_awaited_by_service`(test_context_search.py: `_AsyncStaticPlanner` async def 주입) | `isawaitable→False` | **OK(빈 셸)** | **FAILED(errors=1)** ✓ |
| S2 sync-side guard(참고) | 기존 sync fake 회귀 | `isawaitable→True` | FAILED(24) | FAILED(test_context_search.py만 22 = 21 errors+1 fail) ✓ |

E1: `_AdvancingClock`이 `started=0.0` 직후 `100.0`을 반환해 첫 `_check_wall_clock`에서 `ContextSearchBudgetExceeded` → endpoint 504 매핑을 정확히 trigger. S1: `_AsyncStaticPlanner.build_plan`(async def)의 coroutine을 service가 await하지 않으면 `_validate_plan`이 coroutine을 받아 실패 — async seam의 async 방향을 pin. 두 보강 테스트 모두 docstring에 "E1/S1 should-fire ... re-fails this"로 mutation 의존성과 직전 검증 기록을 역참조 — 회귀 품질 우수. async seam 양방향(S1+S2) 균형 잠금 완료.

### 2. deployed smoke 스크립트 — 부합 (관례 미러링 + seam)

`scripts/phase4_context_search_deployed_smoke.py`:
- `run_deployed_context_search_smoke(client, ...)`: POST /projects → /drafts → /versions(snapshot 준비) → POST /context-search → summary(status/gate/degraded/macro/micro/plan_steps). exit 0 iff `search_http_status==200`(`search_succeeded`, line 132-133).
- `main(run_live_fn=run_live, stdout=None)` seam(line 136-146) — self-regression이 MockTransport `run_live_fn`을 주입해 라이브 서버 없이 HTTP orchestration을 검증. `return 0 if search_succeeded(summary) else 1`.
- `_safe_json`(line 158-162): 200이 아니면 `response.text` 반환 → 502 응답 body도 summary에 캡처(오류 경로 가시성).
- payload(line 88-93): `needs=["current_scene","source_quote"]`, `current_position`, `max_tokens=6000`.
- 관례 비교: `phase3a_deployed_rebuild_smoke.py`가 동일 `run_live`/`main(run_live_fn=)`/`return 0 if <status>(summary) else 1` 구조. "phase2a/3a deployed smoke 관례 미러링" 주장 부합.

### 3. self-regression 4개 — 부합 (양방향 + mutation guard)

`tests/test_phase4_context_search_deployed_smoke_script.py`:

| 테스트 | 방향 | mutation guard |
|---|---|---|
| `test_run_smoke_creates_snapshot_and_reads_package_and_gate` | 정상 200: snapshot 생성 순서, package/gate/plan_steps 읽기, **payload(current_position/needs) assert** | D2(needs 변경) re-fail ✓ |
| `test_error_status_is_captured_without_package_fields` | 502: `gate_decision` 필드 없음, `search_succeeded=False` | — |
| `test_main_exit_rule_is_two_directional` | CLI exit 양방향(200→0, 502→1) | D1(exit rule 반전) re-fail ✓ |
| `test_script_file_path_invocation_can_import_repo_packages` | `subprocess --help`로 file-path import + `--application-base-url` 노출 | — |

MockTransport 기반(라이브 서버 불필요), HTTP orchestration의 핵심 분기(정상/오류/exit)를 cover. payload assert가 smoke가 계약 필드(current_position, needs)를 실제로 보내는지 pin.

### 4. suite 카운트 + 순수 추가 주장 — 부합

- `python3 -m unittest discover tests`: **Ran 470, OK, skipped=44** (직전 464 + E1 + S1 + self-regression 4 = +6).
- `python3 -m pytest -q`: **426 passed, 44 skipped** — 작업자 주장("426 passed / 44 skipped") 정확(470−44=426).
- `git diff --check main...HEAD`: clean.
- **순수 추가 주장 확인**: `f8699a7`은 test 2개 파일(+test infra: `_AdvancingClock`/`_AsyncStaticPlanner`/`_fixture(**service_kwargs)`) + 문서만. production 코드(service.py/main.py/planner.py) 변경 0. `ef0e334`는 scripts/+테스트+문서. SoT 미변경(사용자 주장대로). 확정 계약 미건드림 부합.

### 5. live/deployed 12B 검증 주장 — 관찰 기록(코드 아님), 회계만

- 검색 결과 search_http_status=200 / gate=pass / degraded=False / macro=2 / micro=0 / plan_steps=[(current_scene,[mongo]),(source_quote,[vector])] / exit=0 주장은 work_log/HANDOFF의 관찰 기록. 검증자는 sandbox TCP 제약으로 재실행 불가 — 기록에 의존. self-regression(MockTransport)이 HTTP orchestration의 형태를, live 실행이 실제 12B 결과를 담당하는 분업은 기존 phase2a/3a smoke와 동일 패턴.

## Issues / Risks

**차단 이슈 없음.**

비차단 관찰:
- live/deployed 12B 결과(특히 "current_scene 2개 Mongo 서빙, vector need empty")는 sandbox 외부 실행에 의존. self-regression은 이 값을 검증하지 않음(의도 — MockTransport). 운영상 회귀가 우려되면 live smoke를 CI 밖 주기 실행으로 보강 가능하나 본 slice 범위 아님.
- S2 mutation의 세 모듈 합산 fail 수가 직전 4.3 기록의 "24"와 표현 차이가 있으나(test_context_search.py만 22, api 포함 시 더 많음), sync seam guard 건재성에는 영향 없음 — 본 검증에서 정확 수(22)로 정정.

## Verdict

**합격 (pass)**

이유:
- 직전 4.3 검증 차단 조건 2종(E1 wall-clock 504 매핑, S1 async planner→service seam)이 회귀로 폐쇄됐고, 동일 mutation이 이제 re-fail함을 경험적 실증(E1: failures=1, S1: errors=1). async seam 양방향(S1+S2) 균형 잠금 완료.
- deployed smoke 스크립트가 기존 phase2a/3a 관례(run_live/main seam, exit rule)를 미러링하고, self-regression 4개가 정상/오류/CLI-exit-양방향/import를 cover하며, 핵심 분기의 mutation guard(D1/D2)가 확인됨.
- suite green 독립 재현(426 passed/44 skipped — 주장 정확), diff clean, production 코드/SoT 미변경(순수 추가 주장 부합).
- 문서 갱신(work_log/HANDOFF/CHANGELOG/브리프 + 본 검증 기록 4_3에 폐쇄 노트) 적절.

차단 조건 없음. 이것이 Phase 4 Slice 4.3 계열(4.2 → 4.3 → 본 폐쇄)에서 첫 비조건부 합격.

## Outstanding items

- live/deployed 12B smoke 재실행은 sandbox 외부(owner)에서 필요 시 수행. 결과는 work_log/HANDOFF에 이미 기록됨.
- main 미푸시, 브랜치 `phase4-slice-4-2-planner` 9커밋 — PR 가능 상태(본 검증 합격).
- S-2(create_app 공유 in-process vector index)는 rebuild non-persistence 확정 계약 변경이므로 착수 전 브리프 + 오너 승인 필요 — 작업자가 이미 인지하고 owner 결정을 대기 중.
- 본 검증은 결함을 silently fix하지 않음.

## Reproduction

```bash
# 1. suite + 정밀 카운트
python3 -m unittest discover tests        # Ran 470 OK skipped=44
python3 -m pytest -q                       # 426 passed, 44 skipped
git diff --check main...HEAD

# 2. 빈 셸 폐쇄 재실증 (직전 4.3 검증과 동일 mutation; 이제 re-fail해야 함)
#    E1: main.py 의 ContextSearchBudgetExceeded 매핑 504->500  => test_wall_clock_budget_exceeded_is_504 re-fail
#    S1: service.py 의 `if inspect.isawaitable(result):` -> `if False:` => test_async_planner_is_awaited_by_service re-fail
#    S2(참고): -> `if True:` => test_context_search.py 22 re-fail (sync seam guard)

# 3. deployed smoke guard
#    D1: smoke `return 0 if search_succeeded(summary) else 1` 반전 => test_main_exit_rule re-fail
#    D2: smoke needs를 ["recent_scenes"] 등으로 변경 => test_run_smoke 의 payload assert re-fail
#    (백업→문자열 치환→unittest→복원; 상세 스크립트는 본 검증 세션 bash 기록)
```
