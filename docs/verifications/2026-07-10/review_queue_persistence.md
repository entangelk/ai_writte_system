# Verification — (2B.4 후속) conflict review queue 영속화 (SoT v1.6.59)

## Subject metadata

- **Date**: 2026-07-10
- **Requester**: owner ("작업 AI가 작업한거 확인하고 검증하고 의심하고 또 의심해줘. 커밋 2에 대한것만 해줘.")
- **Verifier**: Claude (독립 검증 — 본 변경을 구현한 작업자와 상이)
- **Target slice/artifact**: commit `25e4869` "SoT v1.6.59: (2B.4 후속) conflict review queue 영속화". 신규 `analysis/review_queue.py`·`analysis/review_queue_mongo_repository.py`, `analysis/apply.py` optional `review_queue` 주입, `main.py` `_default_review_queue_service` 배선 + `GET /projects/{id}/analysis/review-queue`, 회귀 +13(`tests/test_review_queue.py`·`tests/test_memory_apply.py::ApplyReviewQueuePersistenceTest`·`tests/test_analysis_apply_api.py::ReviewQueueApiTest`).
- **Canonical spec reference**: 정본 계약 SoT `docs/system-contract-sot.md` **v1.6.59** (Approved, 2026-07-10) changelog 항목 + 착수 결정 브리프 `docs/plans/02b-4-review-queue-persistence-decisions.md` (Resolved, 오너 결정 D1~D4). 상위 계약: SoT §2B.4(v1.6.44 D7 conflict review-only)·§Analysis Gate(line 316 action literal)·§Phase 2B(line 378~380 미확정 목록).
- **Source of work being verified**: commit `25e4869` (HEAD). `git diff --check` clean (작업자 주장, 본 검증에서 재확인).

## Scope

계약 scope를 먼저 좁혀 읽었다(CLAUDE.md Verification §"scope the contract read before opening"). 본 slice를 지배하는 정본 계약 chain:
1. 브리프 `docs/plans/02b-4-review-queue-persistence-decisions.md` — D1~D4 결정·scope·out-of-scope.
2. SoT v1.6.59 changelog(`docs/system-contract-sot.md:36`) — 정본 delta.
3. SoT 본문 §2B(line 316 Analysis Gate action literal, 378~380 Phase 2B 미확정 목록, 467 public envelope).
4. SoT v1.6.44 changelog(:51) — 원 2B.4 apply 계약(D7 conflict review-only, D6 candidate 부재 거절).
5. `analysis/compare.py` — `CompareAction` enum 실제 membership(merge/split 부재 확인).
6. HANDOFF Active Decisions(review queue 영속화 항목).

검증 표면:
1. **브리프 D1~D4 ↔ 구현 정합성** — `review_queue.py`·`review_queue_mongo_repository.py`·`apply.py`·`main.py` 의 모든 literal·분기.
2. **boundary matrix** — should-fire / should-NOT-fire 전 분기의 회귀 test 매핑(빈 셀 탐지).
3. **회귀 test code 자체 감사** — 각 test가 계약을 실제로 pin 하는지(under-strict + over-strict 양방향, mutation 재실증).
4. **계약 자기 모순** — 브리프·SoT changelog·SoT 본문·code 사이 literal 불일치.
5. **보고된 카운트 독립 재현** — 717 passed / 48 skipped.
6. **out-of-scope 경계 준수** — resolve/dismiss 전이·merge/split 산출·재조정 write 가 도입되지 않았는지(forward-defense stub 검증).

## Methodology

본 검증의 모든 관찰은 아래에서 도출됨(독립 재도출, 작업자 주장 무비판 전재 안 함).

```bash
# (M1) commit diff 전량
git show --stat 25e4869
git show 25e4869 -- docs/system-contract-sot.md CHANGELOG.md HANDOFF.md
git show 25e4869 -- services/application/app/analysis/apply.py services/application/app/main.py

# (M2) 구현·계약 원문 정독
# (Read 도구) review_queue.py, review_queue_mongo_repository.py, apply.py,
#   compare.py, main.py (endpoint·_require_project_exists),
#   docs/plans/02b-4-review-queue-persistence-decisions.md, SoT 본문 §2B

# (M3) enum membership 확인 (D4 schema-only 주장)
grep -n "class CompareAction\|class AnalysisCandidateType" ...
python3 --version  # StrEnum str() 의미 확인용

# (M4) focused 회귀 (신규 13)
python3 -m pytest tests/test_review_queue.py tests/test_memory_apply.py \
  tests/test_analysis_apply_api.py -q

# (M5) 전체 스위트 (프로젝트 검증 관례)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py

# (M6) mutation 재실증 (양방향 guard bite) — 각 후 revert
#   1) derive_review_queue_id 비결정화 → test_reenqueue_same_conflict_upserts_not_duplicates FAIL
#   2) apply conflict 분기 enqueue 제거 → test_conflict_persists_open_review_entry FAIL
#   3) CREATE에 잘못 enqueue → test_safe_actions_do_not_enqueue FAIL
```

## Findings

### F1. 브리프 D1~D4 ↔ 구현 정합성 — 모든 literal 일치

| 결정 | 계약 literal | 구현 file:line | 일치 |
|---|---|---|---|
| **D1** status=`open` 단일 | resolve/dismiss 미도입 | `review_queue.py:35-38` `ReviewQueueStatus(StrEnum)` 는 `OPEN="open"` **단일 member**. enum 자체가 전이 상태를 가질 수 없음. | ✓ |
| **D1** conflict → durable store upsert | review-only만 | `apply.py:101-121` `CONFLICT` 분기에서만 enqueue; `apply.py:99-100` `NO_CHANGE`·`apply.py:129-170` CREATE/UPDATE/ADD_EVIDENCE는 review_queue 미접촉 | ✓ |
| **D2** `GET /projects/{id}/analysis/review-queue` | open 항목 조회, missing project 404 | `main.py:1506-1519` 엔드포인트; `_require_project_exists`(`main.py:870-871`) → `core_sot.get_project` NotFound → `HTTPException(404)`; `review_queue.list_open(project_id)` | ✓ |
| **D3** id = `(project_id,job_id,candidate_id,action)` canonical-JSON SHA-256 | 멱등 upsert | `review_queue.py:54-68` `derive_review_queue_id` — `json.dumps(canonical, ensure_ascii=False, sort_keys=True)` + `hashlib.sha256`. `sort_keys=True`로 key 순서 고정. mongo `replace_one({"_id": entry.id}, ..., upsert=True)`(`review_queue_mongo_repository.py:59-62`)·in-memory `self._entries[entry.id] = entry`(`:85-86`) 둘 다 id 기반 upsert | ✓ |
| **D4** action generic 저장(CompareAction) | merge/split 미발화, 스키마만 | `ReviewQueueEntry.action: CompareAction`(`:48`). 단 `compare.py:36-41` `CompareAction` 은 CREATE/UPDATE/ADD_EVIDENCE/NO_CHANGE/CONFLICT 5종 **만** — merge/split은 enum member 자체가 아님. API는 `CompareAction(body.action)`(`main.py:1474`)로 "merge" → ValueError → 400(`test_analysis_apply_api.py:209-219` test_unknown_action_returns_400 확인). 즉 D4 "스키마만 열어둠"은 정확히 달성됨(action field는 generic이나, 오늘 day 발화 가능한 review-only action은 conflict 단일) | ✓ |
| **scope** `ReviewQueueEntry` 필드 | entry/status/repo/service/derive_id | `review_queue.py:41-51` `ReviewQueueEntry`(frozen dataclass, slots): id/project_id/job_id/candidate_id/candidate_type/action/matched_memory_id/rationale/status — 브리프 scope 전량 | ✓ |
| **scope** Mongo collection `review_queue` + project+status index | deterministic `_id` upsert | `review_queue_mongo_repository.py:39` `self._db["review_queue"]`; `:48-57` `create_index([("project_id",ASCENDING),("status",ASCENDING)])` name `review_queue_by_project_status` | ✓ |
| **scope** `MemoryApplyService` optional `review_queue`, 미주입 시 불변 | 하위호환 | `apply.py:63-73` `review_queue: ReviewQueueService | None = None`; `:106` `if self._review_queue is not None:` 가드 → 미주입 시 enqueue 분기 진입 안 함 | ✓ |
| **scope** `create_app` `_default_review_queue_service` (Mongo 구성 시 Mongo) | 배선 | `main.py:254-270` `CORE_SOT_MONGO_URI` 시 `MongoReviewQueueRepository.from_uri`, else `InMemoryReviewQueueRepository`; `main.py:687,717-720` apply_service 주입 | ✓ |

### F2. Boundary matrix — 16 셀, 모두 추적됨 (빈 셀 없음)

should-fire / should-NOT-fire 전 분기를 회귀 test로 trace.

| # | 분기 | 방향 | 회귀 test (file:test) | 추적 |
|---|---|---|---|---|
| B1 | conflict + queue configured → enqueue | fire | `test_memory_apply.py::test_conflict_persists_open_review_entry` | ✓ |
| B2 | conflict → outcome=SKIPPED_REVIEW + canonical write 0 | fire (D7 유지) | 동상 test(`outcome`·`len(memory.list_memories)==0` 검증) | ✓ |
| B3 | entry 필드(action/cand/job/matched_mem/status) | fire | 동상 test | ✓ |
| B4 | id = derive_review_queue_id(...) | fire (D3) | `test_review_queue.py::test_id_is_deterministic_from_project_job_candidate_action` | ✓ |
| B5 | 재enqueue → upsert(중복 X, latest wins) | fire (D3 멱등) | `test_review_queue.py::test_reenqueue_same_conflict_upserts_not_duplicates` | ✓ |
| B6 | 상이 candidate → 별도 entry | NOT-fire(over-strict) | `test_review_queue.py::test_distinct_candidates_are_separate_entries` | ✓ |
| B7 | list_open project-scoped | fire+NOT-fire | `test_review_queue.py::test_list_open_is_project_scoped`(p1=1, p2=1, p3=0) | ✓ |
| B8 | safe action(CREATE) → enqueue X | NOT-fire(over-strict) | `test_memory_apply.py::test_safe_actions_do_not_enqueue` | ✓* |
| B9 | safe action(NO_CHANGE) → enqueue X | NOT-fire(over-strict) | 동상 test | ✓ |
| B10 | apply 재적용 conflict → queue 중복 X | fire (D3 apply-level) | `test_memory_apply.py::test_reapplying_same_conflict_does_not_duplicate` | ✓ |
| B11 | queue 미주입 conflict → 동작 불변·no raise | NOT-fire(하위호환) | `test_memory_apply.py::test_conflict_without_queue_is_still_review_only` | ✓ |
| B12 | GET → conflict apply 후 open entry 관통 | fire (D2 e2e) | `test_analysis_apply_api.py::test_conflict_apply_surfaces_in_review_queue` | ✓ |
| B13 | GET → 재적용 미중복 | fire (D3 e2e) | `test_analysis_apply_api.py::test_reapplying_conflict_does_not_duplicate` | ✓ |
| B14 | GET empty project → [] | fire (D2) | `test_analysis_apply_api.py::test_empty_queue_returns_empty_list` | ✓ |
| B15 | GET missing project → 404 | fire | `test_analysis_apply_api.py::test_missing_project_returns_404` | ✓ |
| B16 | status=OPEN 단일(전이 X) | NOT-fire(구조적) | `ReviewQueueStatus` 단일-member enum — 전이 상태를 코딩할 수 없음(구조적 lock) | ✓(코드 구조) |

\* **B8/B9 partial coverage** — over-strict guard `test_safe_actions_do_not_enqueue`는 safe action 4종 중 **CREATE + NO_CHANGE 2종**만 covers. **UPDATE + ADD_EVIDENCE 2종은 미covered**. → Issues §I1 참조.

추가 trace(코드 구조적 확인):
- **B17** matched_memory_id=None 허용: compare `_compare_candidate` 다수매칭 conflict 경로가 `matched_memory_id=None`(`compare.py:152-161`) 산출. `ReviewQueueEntry.matched_memory_id: str | None`(`:49`)가 None 허용. 타입으로 lock.
- **B18** conflict + queue configured + ghost candidate → `UnknownCandidate`(`apply.py:106-111`): 코드가 raise 강제하나, 회귀 test 부재(기존 `test_proposal_for_missing_candidate_raises`는 CREATE-only). → Issues §I2 참조.

### F3. 회귀 test code 자체 감사 — 양방향 guard 실제로 bite 함 (mutation 재실증)

세 가지 mutation으로 guard가 양방향으로 발화함을 독립 확인(각 후 `git diff --stat` empty로 revert 확인):

1. **D3 under-strict(M1)**: `derive_review_queue_id`를 `os.urandom` 비결정화 → `test_reenqueue_same_conflict_upserts_not_duplicates` **FAIL**(`'rq:6a76...' != 'rq:b132...'`). 결정적 id가 깨지면 멱등 upsert 회귀가 잡는다. ✓
2. **B1 under-strict(M2)**: apply conflict 분기의 `self._review_queue.enqueue(...)` 블록을 `pass`로 제거 → `test_conflict_persists_open_review_entry` **FAIL**(`ValueError: not enough values to unpack`, queue empty). enqueue가 빠지면 under-strict guard 발화. ✓
3. **B8 over-strict(M3)**: CREATE 분기에 잘못 enqueue 추가 → `test_safe_actions_do_not_enqueue` **FAIL**(`AssertionError: 1 != 0`). safe action이 queue에 들어가면 over-strict guard 발화. ✓

신규 13 test 분해(store 5 + apply 통합 4 + API 4)가 changelog 주장과 정확 부합. 각 test는 internal helper가 아닌 public surface(`ReviewQueueService.enqueue`/`list_open`, `MemoryApplyService.apply_proposals`의 `AppliedProposal.outcome`, HTTP envelope `entries[].action/status`)에 assert.

### F4. 보고된 카운트 독립 재현 — 정확

```
# focused (신규 13 포함 36)
python3 -m pytest tests/test_review_queue.py tests/test_memory_apply.py \
  tests/test_analysis_apply_api.py -q  →  36 passed
# 전체 스위트
python3 -m pytest -q --ignore=tests/test_memory_mongo.py  →  717 passed, 48 skipped
```

작업자 주장(717/48)과 **정확 일치**. skip 48은 종전(b-5 skip guard 도입 45→48)과 동일.

### F5. 계약 자기 모순 — 차단 모순 없음, 비차단 stale 1건

- **브리프 D1~D4 ↔ SoT v1.6.59 changelog**: 정합. changelog가 D1~D4·scope·회귀 분해·out-of-scope를 충실히 반영.
- **changelog ↔ 코드**: 정합(literal 전량 일치, F1).
- **SoT 본문 §380(line 380) ↔ v1.6.59**: 비차단 stale. 본문 "미확정으로 남은 것" 목록이 여전히 "conflict/merge/split review queue 영속화"를 나열하며, peer 항목들(`⑧ scope는 v1.6.42...` 식 괄호)과 달리 **v1.6.59로 conflict 부분이 닫혔다는 추적 괄호가 없음**. changelog가 정본 delta로 canonical하므로 모순 아님(차단 아님)이나, 본문 prose가 stale. → Issues §I3.
- **§316 Analysis Gate literal**(`create/update/add_evidence/no_change/conflict`) ↔ `compare.py` `CompareAction`: 정합(5종). merge/split은 §378~380이 "review-only(미발화)"로 명시, 코드도 enum에 없음 — D4와 정합.

### F6. out-of-scope 경계 준수 — forward-defense stub 확인

- `ReviewQueueStatus`에 RESOLVED/DISMISSED member 부재(D1 준수).
- `CompareAction`에 MERGE/SPLIT member 부재 → emission 경로 자체 불가(D4 준수).
- queue 항목 기반 canonical 재조정 write 코드 부재(apply는 여전히 enqueue만, write X).
- `ReviewQueueService`에 resolve/dismiss/reconcile method 부재.
전부 out-of-scope(Phase 6)로 명시된 대로 미도입. forward-defense stub 체계 유지.

## Issues / Risks

### I1. (비차단 관찰) over-strict guard B8/B9 partial parametrization
**현상**: `test_safe_actions_do_not_enqueue`가 "safe action은 queue에 들어가면 안 된다"는 over-strict guard이나, safe action 4종(create/update/add_evidence/no_change) 중 **create + no_change 2종만** parametrize. **update + add_evidence 2종 미covered**.
**risk**: 누군가 `_apply_one`의 update/add_evidence 분기에 review_queue enqueue를 잘못 추가해도, 현재 regression이 잡지 못함(코드 구조상 동 분기는 review_queue에서 물리적으로 멀어 발생 확률은 낮음).
**CLAUDE.md 기준**: "parametrized cases cover every enumerated boundary value, not just one sample" — 경계값 4종 중 2종 누락. 다만 guard 자체는 존재하며(missing guard 아님), mutation(M3)으로 create 방향이 bite함은 실증됨.
**권고**: 4종 전부 parametrize 권고. 차단 사유 아님(guard 존재 + 구조적 거리 + create 방향 bite 실증).

### I2. (비차단 관찰) conflict + ghost candidate + queue configured 경로 회귀 부재
**현상**: `apply.py:106-111`은 review_queue configured일 때 conflict 분기에서 `by_id.get(proposal.candidate_id)` 후 None이면 `UnknownCandidate` raise. 이는 queue 미주입 시(미검사·skip)와 **동일 input에 대한 behavior 차이**를 만듦. 기존 `test_proposal_for_missing_candidate_raises`는 CREATE-only라 이 분기를 잡지 않음.
**spec-silent 여부**: 브리프는 "미주입 시 동작 불변"만 약속(configured일 때 ghost 처분은 명시 X). 다만 SoT v1.6.44 D6 "candidate 부재는 거절"의 일반 불변이 conflict 분기로 확장된 것으로 해석 가능 — 완전히 spec-silent는 아님.
**risk**: HTTP layer에서 ghost candidate는 이미 상류에서 400(`main.py:1467-1472`)으로 차단되므로, service 직접 호출자에게만 의미. 낮음.
**권고**: `test_conflict_with_queue_and_ghost_candidate_raises` 1건 보강 권고. 차단 아님.

### I3. (비차단 관찰) SoT 본문 §380 stale prose
**현상**: `docs/system-contract-sot.md:380` "미확정으로 남은 것" 목록이 "conflict/merge/split review queue 영속화"를 나열하나, v1.6.59로 **conflict 영속화 부분이 닫혔다는 추적 괄호 누락**(peer 항목은 모두 괄호로 해소 추적 중).
**risk**: 향후 독자가 본문만 읽으면 conflict 영속화가 미구현으로 오인. changelog가 canonical이라 차단 아님.
**권고**: §380 해당 항목을 "conflict review queue 영속화는 v1.6.59로 닫힘(merge/split 산출·전이는 Phase 6 잔여)" 식으로 정정 권고.

### Risks (경계)
- **Mongo round-trip 미검증**: `MongoReviewQueueRepository`는 in-memory repo와 대칭 구조로 작성되었으나 live Mongo round-trip은 sandbox-밖(프로젝트 검증 관례). `str(StrEnum_member)` → value round-trip은 Python 3.12.3 + `AnalysisCandidateType(StrEnum)`/`CompareAction(StrEnum)`로 정합 확인하였으나, live `replace_one`/`find`/index 생성은 미실증. out-of-scope(명시).
- **deterministic id에 `job_id` source**: apply는 `candidate.job_id`(`apply.py:114`)를 id에 사용. HTTP에서는 candidates가 URL job_id로 load되어 `candidate.job_id == url_job_id`이나, service 직접 호출 시 caller가 넘긴 candidates tuple의 job_id가 id를 결정. 브리프 D3의 "(project_id,job_id,...)"에서 job_id의 출처가 명시적이지 않음(코드는 candidate.job_id로 일관). 차단 아님.

## Verdict

**합격 (pass).**

load-bearing reasons:
1. 브리프 D1~D4 ↔ 구현 literal이 전량 일치(F1) — 빈 셀 없음.
2. boundary matrix 16셀 전수 추적(F2) — should-fire/should-NOT-fire 양쪽. 단일 빈 셀 없음.
3. 회귀 13건이 계약을 실제로 pin 함을 mutation 3종으로 독립 실증(F3) — under-strict(M1·M2) + over-strict(M3) 양방향 bite.
4. 보고 카운트 717/48 독립 재현(F4).
5. 계약 자기 모순(차단 급) 부재(F5).
6. out-of-scope(forward-defense stub) 준수(F6).

비차단 관찰 3건(I1~I3)은 보강 권고이며 합격 판정을 뒤집지 않음 — guard가 존재하고(I1은 create 방향 bite 실증, I2는 상류 400으로 차단, I3은 changelog canonical로 상쇄). CLAUDE.md "빈 셀 = 차단" 기준에서 이 slice의 핵심 경계(conflict→enqueue·D3 멱등·safe action 배제·D2 read surface·missing 404)는 전부 lock됨.

## Outstanding items

- **MongoReviewQueueRepository live round-trip 미검증**(sandbox-밖, 설계상 out-of-scope). 프로젝트 검증 관례대로 배포 sandbox에서 별도 실증 필요. 본 검증은 구조 정합(str round-trip 포함)만 확인.
- **비차단 보강 후보 3건**(I1 over-strict 4종 parametrize·I2 conflict+ghost 회귀·I3 SoT §380 stale 정정) — owner 판단으로 후속 보강 가능. 어느 것도 본 slice 차단 아님.
- 본 slice의 sandbox-밖 잔여(Mongo round-trip)와 Phase 6 forward-defense(resolve/dismiss·merge/split 산출·재조정 write)는 HANDOFF Next Tasks #1/(d) 완료 상태와 일관.

## Reproduction

```bash
# 전체 검증 재실행 (sandbox, sandbox-밖 의존 없이)
git checkout 25e4869  # HEAD
python3 -m pytest tests/test_review_queue.py tests/test_memory_apply.py \
  tests/test_analysis_apply_api.py -q        # → 36 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # → 717 passed, 48 skipped

# mutation 재실증 (각 후 cp backup → revert, git diff --stat empty 확인)
# M1: review_queue.py derive_id 를 os.urandom 비결정화
#     → test_review_queue.py::ReviewQueueIdempotencyTest::test_reenqueue_same_conflict_upserts_not_duplicates FAIL
# M2: apply.py conflict 분기 enqueue 블록 → pass
#     → test_memory_apply.py::ApplyReviewQueuePersistenceTest::test_conflict_persists_open_review_entry FAIL
# M3: apply.py CREATE 분기에 잘못 enqueue 추가
#     → test_memory_apply.py::ApplyReviewQueuePersistenceTest::test_safe_actions_do_not_enqueue FAIL
```
