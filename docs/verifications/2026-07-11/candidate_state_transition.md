# Verification — Phase 6 candidate 상태 전이 (백엔드 계약, SoT v1.6.61)

## Subject metadata

- **Date**: 2026-07-11
- **Requester**: owner ("검증 결과 확인하고 보강할 부분 보강해줘")
- **Verifier**: 오너 독립 검토(별도 감사) + 본 후속 보강(작업자). 독립 검토가 CONDITIONAL PASS + 비차단 관찰 2건을 제기했고 본 기록이 재도출·closure 한다.
- **Target slice/artifact**: working tree(uncommitted) — SoT v1.6.61 "Phase 6 candidate 상태 전이 백엔드". 신설 `analysis/candidate_review.py`; 확장 `analysis/service.py`(`transition_candidate`)·`analysis/models.py`(status)·`indexing/`(CANDIDATE_REMOVED)·`analysis/review_queue.py`(resolve/dismiss)·`main.py`(confirm/reject).
- **Canonical spec reference**: 브리프 `docs/plans/06-candidate-state-transition-decisions.md`(Resolved, D1~D5) + SoT v1.6.61 changelog·§Phase 6 body·§464/§465.
- **Source of work being verified**: working tree, **uncommitted**(최신 commit `1cd1799` v1.6.60).

## Scope

1. 브리프 D1~D5 ↔ 구현 literal.
2. boundary matrix(브리프) + 독립 검토가 제기한 미커버 경계(rejected→needs_review·CANDIDATE_REMOVED routing).
3. mutation bite(M1 불법 전이·M2 idempotency·M3 routing).
4. 카운트 재현.

## Findings

### F1. 브리프 D1~D5 ↔ 구현 — PASS

- D1 분리 모델: `CandidateReviewService.confirm`(`candidate_review.py`)이 `transition_candidate(CONFIRMED)` + `promote_candidate`(idempotent); `reject`는 `transition_candidate(REJECTED)` promotion 없음. D5 rejected 보존(store update만, 삭제 없음).
- D2 CANDIDATE_REMOVED: `indexing/models.py` 신규 literal + `enqueue_candidate_removed` + `_PER_SINK_EVENTS` 포함; worker `index_candidate` 재유도가 not-needs_review면 delete.
- D3 review_queue: `RESOLVED`/`DISMISSED` + `resolve_for_candidate`(confirm)/`dismiss_for_candidate`(reject).
- D4 idempotent: 부작용을 `transition.changed`에 게이트, `transition_candidate`가 same-status를 no-op replay.

### F2. boundary matrix — 전 셀 회귀(빈 셀 없음, 독립 검토 관찰 2건 포함)

| 분기 | 테스트 | 상태 |
|---|---|---|
| needs_review→confirmed + promotion | `ConfirmTest::test_confirm_transitions_promotes_deindexes_and_resolves` | PASS |
| needs_review→rejected(무promotion, 보존) | `RejectTest::test_reject_transitions_deindexes_dismisses_without_promotion` | PASS |
| illegal 4종: confirmed↔rejected·confirmed→needs_review·**rejected→needs_review** | `TransitionStateMachineTest::test_cross_terminal_and_backward_edges_are_rejected` (**Obs1 closure**: rejected→needs_review 추가) | PASS |
| 전이 → CANDIDATE_REMOVED enqueue | `ConfirmTest`/`RejectTest`(recording outbox) | PASS |
| **CANDIDATE_REMOVED worker routing → 실 delete** | `WorkerDispatchTest::test_candidate_removed_routes_to_candidate_adapter_and_deletes` (**Obs2 closure**: 신규) | PASS |
| same-status idempotent replay(부작용 무중복) | `Confirm/RejectTest::test_*_replay_is_idempotent*` | PASS |
| 전이 후 retriever 미반환 | `test_confirmed_candidate_leaves_the_retrievable_needs_review_set` | PASS |
| review_queue open→resolved/dismissed·scope·idempotent | `test_review_queue.py::ReviewQueueTransitionTest` (+4) | PASS |
| cross-project 전이 격리 | `test_missing_or_cross_project_candidate_raises` | PASS |
| HTTP confirm/reject/idempotent/409/404 | `test_memory_api.py::CandidateReviewApiTest` (+6) | PASS |

### F3. mutation bite — CONFIRMED

- **M1** 불법 전이 검증 무력화(`not in _ALLOWED` → `False and ...`) → 상태머신·orchestration·API 409 **3 test FAIL**.
- **M2** idempotency 게이트 제거(`if transition.changed:` → `if True:`) → replay **2 test FAIL**.
- **M3** `CANDIDATE_REMOVED`를 `_PER_SINK_EVENTS`에서 제거 → routing 테스트 **1 FAIL**(archive 경로로 오라우팅).
- 3종 모두 cp 백업으로 sha 정확 복원(`git checkout` 미사용 — 이전 사고 교훈, work_log 기록).

### F4. 카운트 재현 — PASS

- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **749 passed / 48 skipped**(v1.6.61 +22 + 검증 후속 보강 routing +1 = 종전 726 + 23). `git diff --check` clean.

## Issues / Risks

- 독립 검토 비차단 관찰 2건 closure: **Obs1**(rejected→needs_review 미명시/미테스트) → 브리프 matrix 명시 + 테스트 4번째 edge 추가; **Obs2**(CANDIDATE_REMOVED/UPSERTED 경로 공유 미문서·routing 무테스트) → `candidate_index.py` docstring 재작성(reconcile 단일 경로 명시) + worker routing 테스트 신규 + 브리프 matrix 행 추가.
- **잔여(비차단)**: 실 Mongo `update_candidate` round-trip·live de-index 관통은 sandbox 밖(InMemory 대칭 검증만). Phase 6 UI(merge/split·부분 승인·deep link)는 미확정 유지.

## Verdict

**합격(PASS)** — 브리프 D1~D5 정합, boundary matrix 전 셀(독립 검토 Obs1/Obs2 포함) 양방향 회귀 잠금, mutation 3종 bite + 정확 복원. 종전 CONDITIONAL PASS의 비차단 관찰이 모두 closure됨.

## Reproduction

```bash
python3 -m pytest tests/test_candidate_review.py tests/test_review_queue.py \
  tests/test_memory_api.py::CandidateReviewApiTest tests/test_candidate_index.py -q
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 749 passed / 48 skipped
# mutation: M1/M2(service·candidate_review), M3(_PER_SINK_EVENTS) — cp 백업/복원
```
