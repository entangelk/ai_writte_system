# Verification — (e) canonical↔candidate 승격 dedup (SoT v1.6.60)

## Subject metadata

- **Date**: 2026-07-11
- **Requester**: owner ("검증 기록 확인하고 보강할 부분 보강해줘")
- **Verifier**: 오너가 수행한 독립 검토(별도 감사 리포트) + 본 후속 보강(작업자). 독립 검토는 본 변경을 구현한 작업자와 상이한 세션에서 수행됐고, 그 findings(I1~I3)를 본 기록이 재도출·closure 한다.
- **Target slice/artifact**: working tree(uncommitted) — SoT v1.6.60 "(e) canonical↔candidate 승격 dedup". 변경 파일: `services/application/app/memory/service.py`(`is_candidate_promoted`), `services/application/app/context_search/service.py`(`PromotedCandidateResolver` + `_run_candidate_memory_step` 억제), `services/application/app/main.py`(배선), `tests/test_context_search_candidate_memory.py`, `tests/test_memory_phase2b.py`.
- **Canonical spec reference**: 정본 계약 SoT `docs/system-contract-sot.md` **v1.6.60** (Approved, 2026-07-11) changelog + 본문 §Phase 4 ⑤(line ~416) + 착수 결정 브리프 `docs/plans/04-canonical-candidate-dedup-decisions.md` (Resolved, 오너 결정 D1/D2). 상위 계약: SoT v1.6.50 changelog(D7 no-dedup 수용)·`context_search/service.py:349` D5=A·SoT §Phase 6(candidate 상태 전이 미확정).
- **Source of work being verified**: working tree, **uncommitted**(최신 commit은 `a141974` v1.6.59). 본 기록 시점 미커밋.

## Scope

계약 chain(브리프 → SoT changelog/본문 → 선행 D7/D5 계약 → 코드/테스트)을 좁혀 읽고 아래 표면을 검증:
1. 브리프 D1/D2 ↔ 구현 literal 정합.
2. boundary matrix 5셀(브리프) + 독립 검토가 제기한 미커버 경계(N>1 승격·project scope 배선).
3. 회귀 test 자체 감사(under/over-strict 양방향, mutation bite).
4. resolver 예외 경로(backend_error degrade)와 하위호환(미주입 = 종전 D7).
5. 보고 카운트 독립 재현.

## Methodology

```bash
# (M1) 구현 원문 정독
sed -n '823,882p' services/application/app/context_search/service.py   # 억제 루프
sed -n '345,362p' services/application/app/context_search/service.py   # PromotedCandidateResolver Protocol
grep -n "is_candidate_promoted" services/application/app/memory/service.py
grep -n "promoted_candidate_resolver" services/application/app/main.py

# (M2) 카운트 재현
python3 -m pytest -q --ignore=tests/test_memory_mongo.py            # 726 passed / 48 skipped
python3 -m pytest tests/test_context_search_candidate_memory.py::CanonicalCandidateDedupTest -q   # 7 passed

# (M3) mutation 재실증(억제 무력화 → under-strict/behavior bite → 정확 복원)
sha256sum services/application/app/context_search/service.py         # pre: dadbe553…
sed -i 's/self._promoted_candidate_resolver is not None$/& and False/' <file>
python3 -m pytest …::CanonicalCandidateDedupTest -q                  # 5 failed / 2 passed
sed -i 's/ and False$//' <file>; sha256sum <file>                    # post == pre (정확 복원)
```

## Findings

### F1. 브리프 D1/D2 ↔ 구현 정합 — PASS

- **D1(승격 시 항상 억제, store 권위)**: `_run_candidate_memory_step`(`service.py:837-846`)이 retrieve 후 각 candidate에 대해 `promoted_candidate_resolver.is_candidate_promoted(request.project_id, candidate.id)`로 판정 — canonical이 같은 package에 retrieval됐는지 **참조하지 않음**(store 권위, merge-only 아님). `MemoryService.is_candidate_promoted`(`memory/service.py:134`)는 `repo.find_memory_by_candidate(...) is not None` 위임 — `source_candidate_id` identity 링크. D1 정합.
- **D2(retrieval-time interim, additive)**: 억제는 조립 단계(step)에서만 발생, 상태 모델·색인·Gate 무변경. resolver 미주입 시 억제 없음(`service.py:839` `is not None` 가드) = 종전 D7 하위호환. D2 정합.

### F2. boundary matrix — 전 셀 회귀 매핑(빈 셀 없음)

| 분기 | 방향 | 테스트 | 상태 |
|---|---|---|---|
| 승격 candidate → 억제 + trace(candidate_promoted) | under-strict | `test_promoted_candidate_suppressed_and_traced` | PASS |
| 비승격 needs_review → 유지 | over-strict | `test_no_candidate_promoted_keeps_all` | PASS |
| resolver 미주입 → 억제 없음(D7 하위호환) | over-strict | `test_no_resolver_is_prior_d7_behavior` | PASS |
| 혼합(c1 승격·c2 비승격) → 부분 억제 | 양방향 | `test_mixed_only_suppresses_promoted` | PASS |
| resolver 예외 → backend_error degrade | 안전 | `test_resolver_failure_degrades_to_backend_error` | PASS |
| **N>1 전부 승격 → 전부 억제(no early-stop)** | under-strict | `test_all_candidates_promoted_all_suppressed` (**I1 closure**) | PASS |
| **resolver가 request.project_id로 질의됨** | 배선 | `test_resolver_is_queried_with_request_project_id` (**I2 closure**) | PASS |
| 승격 링크 존재 판정 + project/candidate scope | 양방향 | `test_memory_phase2b.py::IsCandidatePromotedTest` | PASS |

### F3. mutation 재실증(I3 closure) — CONFIRMED

- pre-mutation sha256 = `dadbe55336cec68c0c4fdacab6987cecdd311dc43ad30a3a43b59f1aacc48ade`.
- 억제 조건 `self._promoted_candidate_resolver is not None` → `... and False`(억제 완전 무력화) 후 `CanonicalCandidateDedupTest` → **5 failed / 2 passed**:
  - FAILED(억제·행동 bite): `test_promoted_candidate_suppressed_and_traced`, `test_mixed_only_suppresses_promoted`, `test_all_candidates_promoted_all_suppressed`(I1), `test_resolver_is_queried_with_request_project_id`(I2 — 억제 무력화 시 resolver 미호출 → `seen_projects` 공집합으로 bite), `test_resolver_failure_degrades_to_backend_error`(short-circuit로 resolver 미호출 → raise 없음 → degrade 소멸).
  - PASSED(over-strict, 억제 없음 기대): `test_no_candidate_promoted_keeps_all`, `test_no_resolver_is_prior_d7_behavior`.
- revert 후 sha256 = pre와 **정확 일치**(`and False` residue 0), `CanonicalCandidateDedupTest` 7 passed 재확인. → under-strict guard가 실제로 물고, 정확 복원됨을 실증.

### F4. 카운트 독립 재현 — PASS

- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **726 passed / 48 skipped**(v1.6.60 dedup +6 + 검증 후속 보강 +2 = 종전 718 + 8). `git diff --check` clean.

## Issues / Risks

- **독립 검토가 제기한 I1~I3는 본 보강으로 closure**: I1(N>1 승격 미커버)·I2(project scope 배선 미커버) → 회귀 +2, I3(mutation 증거 부족) → F3에 재실증·해시 기록.
- **잔여(비차단, forward-defense)**: candidate de-index 실경로·resolve/dismiss 전이는 Phase 6에서 이 억제를 상위집합으로 흡수. `main.py` 실 배선(`promoted_candidate_resolver=memory`)의 실 Mongo `find_memory_by_candidate` round-trip은 sandbox 밖(InMemory repo 대칭 검증만; 프로젝트 mongo repo 검증 관례와 동일).

## Verdict

**합격(PASS)** — 구현이 브리프 D1/D2와 정합하고, boundary matrix 전 셀(독립 검토 I1/I2 추가 포함)이 양방향 회귀로 잠겼으며, mutation이 under-strict 방향으로 물고 정확 복원됨을 실증했다. 종전 독립 검토의 "조건부 합격" 조건 중 **테스트/기록 관련 조건(I1~I3)은 충족**.

## Outstanding items

- **미커밋**: working tree uncommitted. 커밋은 오너 지시 대기(작업자는 오너 요청 없이 커밋하지 않음).
- 실 배포 live 관통(실 Mongo 승격 dedup)은 sandbox 밖 후속.

## Reproduction

```bash
python3 -m pytest tests/test_context_search_candidate_memory.py::CanonicalCandidateDedupTest \
  tests/test_memory_phase2b.py::IsCandidatePromotedTest -q          # 8 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py            # 726 passed / 48 skipped
# mutation: F3 절차(sha256 → and False → 5 failed/2 passed → revert → sha256 일치)
```
