# 독립 검증 — Phase 6 candidate edit 백엔드 (SoT v1.6.66)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?")
- **Verifier**: 독립 세션(검증자). 구현 작업자와 다른 컨텍스트.
- **Target slice**: Phase 6 candidate edit 백엔드 계약 — `AnalysisCandidateStatus.SUPERSEDED` + `supersedes_candidate_id` + `AnalysisService.edit_candidate` + `CandidateReviewService.edit` + `POST .../candidates/{cid}/edit`.
- **Canonical spec reference**: `docs/system-contract-sot.md` v1.6.66 (changelog line 36 · 본문 §443 Phase 6 · §473 미확정 경계) + 착수 결정 브리프 `docs/plans/06-candidate-edit-decisions.md` (Resolved, D1~D6 + 경계 매트릭스 13행) + `docs/plans/06-review-ui.md` 수용 기준 §60 / 착수 결정 §69.
- **Source of work being verified**: working tree, uncommitted (`git diff HEAD` 기준 12파일 + untracked 브리프 1). HEAD = `0a3dba3` (SoT v1.6.65) 위에 v1.6.66 변경을 얹은 상태.

## Scope

1. **Spec contract** — 브리프 D1~D6, 경계 매트릭스 13행, SoT changelog/본문/§473, plan §60/§69 사이의 내부 일관성(cross-check the contract against itself).
2. **Implementation code** — `models.py`(`SUPERSEDED`, `supersedes_candidate_id`), `service.py`(`edit_candidate`, `_ALLOWED_CANDIDATE_TRANSITIONS`), `candidate_review.py`(`edit`), `mongo_repository.py`(직렬화 + unique index 동시성), `main.py`(HTTP 매핑 + envelope).
3. **Regression tests** — `tests/test_candidate_review.py::EditTest` 9 + `TransitionStateMachineTest::test_superseded_is_not_a_transition_target` 1 + `tests/test_analysis_apply_api.py::EditCandidateApiTest` 5 (작업자 클레임 +15).
4. **Boundary matrix lock list** — 매트릭스 13행 각 분기(should fire / should NOT fire)가 named test로 매핑되는지 추적.
5. **Full suite** — 전체 회귀 통과 및 클레임(798/48/101) 재도출.
6. **Mutation testing** — 6개 변형으로 guard가 실제로 bite하는지 적대적 증명.

라이브 Mongo round-trip(successor insert + 원본 supersede 원자성, unique index 동시성)은 **명시적으로 sandbox 밖 후속**으로 scope에서 제외(work_log/HANDOFF/SoT changelog가 전부 acknowledged).

## Methodology

계약을 먼저 스코핑하고(브리프 D1~D6 + 매트릭스 13행 → SoT 본문 → plan §60/§69 순), 그 매트릭스를 lock list로 코드·테스트에 대입. 테스트 통과 여부와 별개로 (a) 각 guard가 under-strict·over-strict 양방향에서 실제로 bite하는지 mutation으로 증명, (b) 코드가 스펙 리터럴과 불일치·누락 없는지 정적 독해.

정확한 명령(재현은 §Reproduction):
- `git diff HEAD -- services/.../models.py service.py candidate_review.py mongo_repository.py main.py` — 프로덕션 diff.
- `git diff HEAD -- tests/test_candidate_review.py tests/test_analysis_apply_api.py` — 테스트 diff.
- `python3 -m pytest tests/test_candidate_review.py tests/test_analysis_apply_api.py -q -p no:cacheprovider` — focused (53 passed).
- `python3 -m pytest --ignore=tests/test_memory_mgo.py -q -p no:cacheprovider` — 전체 (798/48/101).
- mutation: `cp` 백업 → 정확한 문자열 replace로 1개 변형 → focused pytest → `cp` 복구. 6회(M1~M6). 변형 후 `git diff --stat HEAD`로 원상복구 무결성 확인.

## Findings

### 1. Spec contract — 내부 일관성

- 브리프 D1~D6 ↔ SoT changelog(line 36) ↔ SoT 본문 §443 ↔ §473 ↔ plan §69가 전부 동일한 계약을 서술(`docs/system-contract-sot.md:36`, `:443`, `:473`; `docs/plans/06-review-ui.md:69`). D3 "`superseded`는 edit 전용, `transition_candidate`의 legal target이 아님"과 D6 "원본 conflict는 resolve(dismiss 아님)"가 양쪽에 동일하게 명시.
- 미확정 경계(source deep link·merge/split·부분 승인/부분 retry·frontend)가 §473와 브리프 "Out of scope"에서 일치하게 명시됨 — 스펙이 해소한 범위와 남겨둔 범위가 충돌 없음.
- 내부 모순(규칙 prose vs 매트릭스 vs changelog literal 불일치) **없음**.

### 2. Implementation code — 스펙 리터럴 대 일치

- `models.py:33-39` — `SUPERSEDED = "superseded"` 리터럴, docstring이 "edit path 전용, confirm/reject 전이 채널 아님"을 명시(D3와 일치).
- `models.py:89-92` — `supersedes_candidate_id: str | None = None`(default None → 기존 생성부 전부 유효, surgical). 브리프 "성격"과 일치.
- `service.py:548-620` `edit_candidate` —
  - replay 우선순위: `find_candidate_request(project_id, original.task_id, "edit:{id}")`(service.py:571-580) → status 체크(581-584) → `_validate_payload`(585-587). 순서가 D4(원본 1회 edit)와 일치: 이미 edit된 원본은 status 무관 replay.
  - append-only: successor insert(605-606) 먼저, 원본 `superseded`(617-619) 나중. memory `_versioned_upsert` 선례 미러. 동시성 경쟁은 `except DuplicateAnalysisCandidateRequest`(607-616)가 승자 재조회.
  - D5 근거 보존: `provenance=original.provenance`, `confidence=original.confidence`, `source_ref_ids=original.source_ref_ids`(596-598), payload만 교정. `candidate_type`/`action`/`task_id`/`job_id` 승계.
- `service.py:95-101` `_ALLOWED_CANDIDATE_TRANSITIONS` = `{(NEEDS_REVIEW, CONFIRMED), (NEEDS_REVIEW, REJECTED)}` **only**. SUPERSEDED가 target으로 없음 → `transition_candidate`(526-546)가 `(status, SUPERSEDED)`를 거부(D3 강제). 명시적 거부가 아닌 map 부재지만 deterministic하게 강제.
- `candidate_review.py:127-163` `edit` — confirm 선례 미러: `edit_candidate` → `promote_candidate(successor, MANUAL)` → `if not edit.idempotent_replay: _enqueue_removed(original) + resolve_for_candidate(original)`(144-156). promote 링크=successor id, de-index 대상=원본 id(D6와 일치).
- `mongo_repository.py:340` `_candidate_doc` / `:357` `_to_candidate` — `supersedes_candidate_id` 직렬화(`.get()` 하위호환). `:237-250` `_put_candidates_transactional`이 `insert_many`를 transaction으로 감싸고 `DuplicateKeyError`→`DuplicateAnalysisCandidateRequest` raise → unique index 동시성 잠금 유효.
- `main.py:1374-1441` — `EditCandidateRequest{payload}` + `POST /projects/{id}/analysis/candidates/{cid}/edit`, 에러 매핑 `(AnalysisNotFound, MemoryNotFound, NotFound)→404`, `InvalidCandidateStateTransition→409`, `InvalidAnalysisCandidate→400`. 응답 envelope `original_candidate_id`/`candidate_id`/`status`/`memory_id`/`idempotent_replay`(1374-1382) — SoT changelog와 문자열 단위 일치.
- `service.py:703-708` `_require_candidate`가 `candidate.project_id != project_id`로 cross-project 거부 → 404 근거 유효. `service.py:780-787` `_validate_payload`가 `InvalidAnalysisPayload`→`InvalidAnalysisCandidate`로 변환 → 400 근거 유효.

### 3. Boundary matrix — lock 추적 (13행)

| # | 분기 | 방향 | 잠근 테스트 | 상태 |
|---|---|---|---|---|
| 1 | edit→새 version(confirmed)+원본 superseded | under-strict | `EditTest.test_edit_mints_confirmed_version_supersedes_and_promotes` | 잠김 |
| 2 | 새 version confirmed+promote(링크=successor) | under-strict | 동상(`is_candidate_promoted(successor)` True, 원본 False) | 잠김 |
| 3 | 원본 superseded→needs_review set 배제 | over-strict | `test_edit_drops_original_and_successor_from_needs_review_set` | 잠김 |
| 4 | 새 version(confirmed)도 needs_review 미노출 | over-strict | 동상(`assertNotIn(successor)`) | 잠김 |
| 5 | payload·근거/provenance/confidence 보존 | under/over | `test_edit_preserves_source_provenance_confidence` | 잠김 |
| 6 | CANDIDATE_REMOVED enqueue(원본) | under-strict | `test_edit_mints...`(`outbox.removed==[("p1","c1")]`) | 잠김 |
| 7 | 원본 open conflict **resolve(dismiss 아님)** | under/over | `list_open("p1")==()` **only** | **over-strict 미잠금** (B1) |
| 8 | replay=no-op(중복 version/promote/de-index 없음) | over-strict | `test_edit_replay_is_idempotent_without_duplicate_side_effects` | 잠김 |
| 9 | invalid payload→400, 원본 불변 | under/over | `test_edit_invalid_payload_rejected_original_unchanged` | 잠김 |
| 10 | terminal 후보 edit→409 | over-strict | `test_edit_non_needs_review_candidate_raises` | 잠김 |
| 11 | transition target=superseded 거부 | over-strict | `test_superseded_is_not_a_transition_target` | 잠김 |
| 12 | cross-project/missing→404 | over-strict | `test_missing_or_cross_project_edit_raises` | 잠김 |
| 13 | HTTP 200/404/409/400 매핑 | under/over | `EditCandidateApiTest` 5 | 잠김 |

12/13 행이 named test로 추적됨. 빈 cell = 행 7의 "dismiss 아님" 방향. 근거는 §4 mutation M3.

### 4. Mutation testing — guard bite 실증

각 변형은 백업→1개 교체→focused pytest→복구. 복구 후 `git diff --stat HEAD` 무변 확인.

| 변형 | 기대 | 결과 |
|---|---|---|
| M1: `_ALLOWED_CANDIDATE_TRANSITIONS`에 `(NEEDS_REVIEW, SUPERSEDED)` 추가 | 행 11 FAIL | `test_superseded_is_not_a_transition_target` FAIL ✅ |
| M2: `edit`에서 `_enqueue_removed` 비활성화(`and False`) | 행 6 FAIL | `test_edit_mints...` + `test_edit_replay...` 2 FAIL ✅ |
| **M3: `edit`의 `resolve_for_candidate`→`dismiss_for_candidate`** | **행 7 FAIL이어야 함** | **22 passed, FAIL 없음 ❌** |
| M4: `edit`의 status 체크 무효화(`if False and ...`) | 행 10 FAIL | `test_edit_non_needs_review_candidate_raises` FAIL ✅ |
| M5: `edit`의 `_validate_payload`→`payload` 통과 | 행 9 FAIL | `test_edit_invalid_payload_rejected...` FAIL ✅ |
| M6: successor 생성에서 `supersedes_candidate_id` 누락 | 행 1/2 FAIL | `test_edit_mints...` FAIL ✅ |

**M3만 bite하지 않음** — `edit`이 실수로 `dismiss_for_candidate`를 호출해도 회귀가 통과한다. 행 7의 "dismiss 아님" over-strict lock이 빈 cell임을 적대적으로 증명.

### 5. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **798 passed / 48 skipped / 101 subtests passed**. work_log/HANDOFF 클레임과 정확히 일치(독립 재도출). `git diff --stat HEAD`로 mutation 복구 무결성 확인(50+89 insertions, 원상복구).

## Issues / Risks

### Blocking (contract obligations)

- **B1 — 경계 매트릭스 행 7 "dismiss 아님" over-strict 방향이 named test로 잠기지 않음**(`candidate_review.py:153-156` vs `tests/test_candidate_review.py:304`).
  - 매트릭스 행 7은 브리프가 명시적으로 연 행이다: "원본 open conflict **resolve(dismiss 아님)** — 잘못된 큐 전이 시 실패". under-strict(resolve 발생)는 `queue.list_open("p1")==()`로 잠겨 있으나, over-strict(dismiss로 잘못 전이 시 실패)는 잠기지 않았다. `list_open`은 RESOLVED·DISMISSED 모두에서 빈 튜플을 반환하므로, M3 변형이 dismiss를 써도 테스트가 통과한다.
  - **구현 자체는 correct**(`resolve_for_candidate` 호출, dismiss 아님). 결함은 테스트 coverage에 있음.
  - 완화: `ReviewQueueService`가 `list_open`만 노출하고 resolved/dismissed를 나열하는 public 헬퍼가 없어, 구별 assertion을 추가하려면 (a) `ReviewQueueEntry.status`를 직접 조회하거나 (b) `list_resolved`/`list_dismissed` 헬퍼 추가가 필요하다.
  - 추가 완화: 기존 `confirm`/`reject` 테스트(`tests/test_candidate_review.py:197-198`, `:251-252`)도 동일하게 `list_open==()`만 검사한다 — edit만의 신규 gap이 아니라 기존 패턴의 연속. 단, 행 7은 **edit 브리프가 명시적으로 추가한** 경계이므로 edit slice가 lock을 가져갈 책임이 있다.
  - 조건: 행 7의 over-strict lock을 추가(예: edit 후 conflict entry의 `status is ReviewQueueStatus.RESOLVED` assertion)하면 합격으로 승격.

### Hardening recommendations (non-blocking)

- **H1 — edit 2-연산 원자성, sandbox 밖 live 검증 pending**(acknowledged). `edit_candidate`가 `put_candidate(successor)`(별도 mongo transaction, `mongo_repository.py:237-250`) 후 `update_candidate(original→superseded)`(transaction 없는 `$set`, `:252-259`)를 호출한다 — 두 write가 동일 transaction으로 묶이지 않는다. successor insert commit + 원본 supersede 직전 crash window가 존재(이때 successor는 confirmed로 존재, 원본은 아직 needs_review). `confirm`/`reject`는 단일 `update_candidate`이라 all-or-nothing인 점과 대비. work_log/SoT changelog가 "실 Mongo edit round-trip 원자성·unique index 동시성은 sandbox 밖 후속"으로 명시적으로 acknowledged하였으므로 결함이 아니다. live round-trip 시 transaction 또는 보상 로직으로 원자성을 재확인할 것.
- **H2 — status 체크 vs payload validation 순서가 명시 안 됨**(`service.py:581-587`). terminal 후보에 invalid payload edit 시도 → `InvalidCandidateStateTransition`(409)가 `InvalidAnalysisCandidate`(400)보다 우선. 매트릭스가 두 행(10·9)을 별도로 두어 어느 쪽이 우선인지 명시 안 함. 현재 우선순위(status 409 우선)가 합리적이므로 결함이 아니다. 계약이 순서를 고정하지 않아 향후 해석 여지가 남음 — 명시하면 경계가 더 또렷해짐.
- **H3 — in-memory `put_candidates`가 duplicate logical_key를 감지하지 않음**(`service.py:193-204`, dict overwrite). `edit_candidate`의 `except DuplicateAnalysisCandidateRequest`(607-616) 동시성 경쟁 브랜치가 in-memory에서는 dead code — mongo unique index에서만 발생. 이것은 `record_candidates` 기존 경로도 동일한 기존 구조이며 edit이 새로 도입한 것이 아님. in-memory는 single-threaded test용이므로 비결함이나, 동시성 잠금은 mongo에서만 검증됨(H1과 함께 sandbox 밖 live에서 재확인 대상).

## Verdict

**조건부 합격(Conditional pass).**

이유(load-bearing):
- 구현이 스펙 D1~D6 리터럴과 일치하고, 계약 자체(changelog ↔ 본문 §443/§473 ↔ 매트릭스 ↔ 브리프)에 내부 모순이 없다.
- 매트릭스 13행 중 12행이 named test로 잠겨 있고, 5개 mutation(M1·M2·M4·M5·M6)이 guard의 bite를 적대적으로 실증했다.
- 전체 suite 798/48/101이 작업자 클레임과 정확히 일치한다.
- **차단 조건 B1**: 유일한 빈 cell인 매트릭스 행 7의 "dismiss 아님" over-strict lock이 named test로 잠기지 않았다(M3 변형이 bite하지 않음). 행 7은 edit 브리프가 명시한 경계이므로, 이 방향을 assert하는 테스트를 추가하면 합격으로 승격한다.

## Outstanding items

- 작업 미커밋(working tree, uncommitted). 프로젝트 관례상 커밋은 오너 지시 대기.
- B1 보강(edit 후 `ReviewQueueEntry.status is RESOLVED` assertion) 또는 `list_resolved` 헬퍼 추가 후 재검증 대기 — 오너/구현자 결정.
- H1 실 Mongo edit round-trip(successor insert + 원본 supersede 원자성, unique index 동시성) live 검증 — sandbox 밖 풀스택 머신에서 후속.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# focused (53 passed)
python3 -m pytest tests/test_candidate_review.py tests/test_analysis_apply_api.py -q -p no:cacheprovider

# full suite (798 passed / 48 skipped / 101 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# mutation M3 (the failing-lock probe) — resolve→dismiss must NOT silently pass
cp services/application/app/analysis/candidate_review.py /tmp/crv.bak
python3 - <<'PY'
p="services/application/app/analysis/candidate_review.py"
s=open(p,encoding="utf-8").read()
s=s.replace(
'                self._review_queue.resolve_for_candidate(\n                    project_id=project_id, candidate_id=candidate_id\n                )',
'                self._review_queue.dismiss_for_candidate(\n                    project_id=project_id, candidate_id=candidate_id\n                )')
open(p,"w",encoding="utf-8").write(s)
PY
python3 -m pytest tests/test_candidate_review.py -q -p no:cacheprovider | tail -3   # expect: 22 passed (the gap)
cp /tmp/crv.bak services/application/app/analysis/candidate_review.py

# integrity after mutation restore
git diff --stat HEAD -- services/application/app/analysis/candidate_review.py services/application/app/analysis/service.py
```
