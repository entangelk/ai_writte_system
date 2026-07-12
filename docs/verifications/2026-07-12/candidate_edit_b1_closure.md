# 독립 검증 후속 — candidate edit B1 closure (SoT v1.6.66, 6e15798)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("다음작업 검증해줘. … candidate edit … B1 closure …").
- **Verifier**: 독립 세션(검증자). 이전 `candidate_edit_backend.md`의 conditional-pass 사유 B1의 closure를 확인.
- **Target slice**: B1 = candidate edit 매트릭스 행 7 "conflict resolve(**dismiss 아님**)" over-strict lock. 이전 검증에서 M3 변형(edit의 `resolve_for_candidate`→`dismiss_for_candidate`)이 22 passed로 bite하지 않아 조건부 합격 사유였음.
- **Canonical spec reference**: `docs/plans/06-candidate-edit-decisions.md` 매트릭스 행 7 + `docs/verifications/2026-07-12/candidate_edit_backend.md` B1.
- **Source of work**: commit `6e15798`(`tests/test_candidate_review.py`에 RESOLVED assertion 추가, 구현 무변).

## Scope

1. 6e15798이 매트릭스 행 7의 over-strict 방향을 실제로 잠갔는지.
2. edit 경로의 resolve→dismiss 변형이 이제 회귀를 FAIL시키는지(결정적 증거).

## Methodology

- `git show 6e15798:tests/test_candidate_review.py`로 RESOLVED assertion 추가 확인.
- 정확한 edit-경로 mutation: `if not edit.idempotent_replay:` 컨텍스트로 edit 블록만 disambiguate하여 `resolve_for_candidate`→`dismiss_for_candidate` 교체 → focused pytest → 복구.

## Findings

- `tests/test_candidate_review.py:305-310`(6e15798)에 명시적 assertion 추가:
  ```python
  # over-strict (matrix row 7): the entry must be RESOLVED, not DISMISSED —
  queue.get(project_id="p1", entry_id=entry.id).status, ReviewQueueStatus.RESOLVED
  ```
  `_enqueue_conflict`가 entry를 반환하도록 변경(`return queue.enqueue(...)`)하여 assertion이 entry id를 잡음.
- **edit-경로 M3 변형 → `test_edit_mints_confirmed_version_supersedes_and_promotes` FAIL(line 308)**. 행 7 over-strict lock이 bite함을 결정적 증명.

### 이전 검증 repro 정정

`candidate_edit_backend.md`의 §Reproduction M3 스크립트는 `replace(..., 1)`로 `resolve_for_candidate` 첫 매치를 바꾸는데, candidate_review.py에 동일 들여쓰기 호출이 2곳(confirm 96행·edit 154행)이라 **confirm 경로를 바꿨다**(edit가 아님). 당시(6e15798 이전) edit 테스트에도 assertion이 없어 edit을 바꿔도 PASS했을 것이므로 결론(행 7 미잠금)은 우연히 유효했지만, repro 자체는 부정확했다. 본 후속에서 edit 블록을 컨텍스트로 고유 식별해 정정한다.

## Issues / Risks

### Blocking

- 없음. B1 조건(edit 행 7 over-strict lock)이 충족됐다.

### Hardening recommendations (non-blocking)

- **H1 — confirm/reject의 동일한 over-strict gap이 여전히 열려 있음**(`tests/test_candidate_review.py:197-198`, `:251-252`는 `list_open("p1")==()`만 검사). edit slice가 B1을 closed했을 뿐 confirm/reject(이전 슬라이스) 범위의 기존 부채는 그대로다. 동일한 `queue.get(...).status is RESOLVED/DISMISSED` assertion을 confirm/reject에도 적용하면 3개 리뷰 액션의 resolve/dismiss 구별이 일관하게 잠김.

## Verdict

**합격(Pass).** B1 조건(edit 매트릭스 행 7 over-strict lock)이 6e15798에서 충족됐고, edit-경로 resolve→dismiss 변형이 `test_edit_mints...:308`을 FAIL시킴을 직접 증명했다. 이전 `candidate_edit_backend.md`의 **조건부 합격 → 합격으로 승격**.

## Outstanding items

- H1(confirm/reject over-strict 구별 보강)은 오너/구현자 재량.
- 실 Mongo edit round-trip 원자성(sandbox 밖)은 여전히 후속(이전 검증 H1과 동일).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
cp services/application/app/analysis/candidate_review.py /tmp/crv.bak
python3 - <<'PY'
p="services/application/app/analysis/candidate_review.py"
s=open(p,encoding="utf-8").read()
old='''        if not edit.idempotent_replay:
            # De-index the original (it was indexed as needs_review); the new
            # confirmed successor never entered the candidate index.
            self._enqueue_removed(project_id, candidate_id)
            if self._review_queue is not None:
                self._review_queue.resolve_for_candidate(
                    project_id=project_id, candidate_id=candidate_id
                )'''
assert s.count(old)==1
open(p,"w",encoding="utf-8").write(s.replace(old, old.replace("resolve_for_candidate","dismiss_for_candidate"),1))
PY
python3 -m pytest tests/test_candidate_review.py -q -p no:cacheprovider | tail -4   # expect: FAIL at :308
cp /tmp/crv.bak services/application/app/analysis/candidate_review.py
git diff --stat HEAD -- services/application/app/analysis/candidate_review.py       # empty
```
