# 2B.4 후속 — conflict review queue 영속화 착수 결정 브리프

상태: **Resolved**(오너 결정 완료) — 검토 큐 영속화 브리프  

> 상위 계획: `plans/02b-analysis-compare-kickoff-decisions.md`, `plans/02b-3-analysis-compare-action-decisions.md`(D7 review-only), `plans/06-review-ui.md`(Phase 6 소비자).
> HANDOFF Next Tasks #1 후보 (d). 상태: **Resolved**(오너 결정 2026-07-10).

## 배경 / 문제

- 2B.3 compare가 `conflict` `ActionProposal`을 산출하고(merge/split은 미발화), 2B.4 apply(`analysis/apply.py`)는 D7에 따라 conflict를 `SKIPPED_REVIEW`로 처리한다 — **자동 write 금지**.
- 그러나 그 conflict는 **어디에도 영속화되지 않는다**. apply HTTP 응답(`/analysis/jobs/{job_id}/apply`)에 한 번 실릴 뿐, 이후 "조정(reconcile) 대기 중인 conflict"를 조회·추적할 durable store가 없다. 검토자가 응답을 놓치면 conflict는 사라진다.
- 이 슬라이스는 review-only proposal을 durable review queue에 **영속화**하고 조회 read surface를 연다. Phase 6(review UI)와 2B.4 merge/split reconciliation이 이 큐를 소비한다.
- (c)/(e)와 달리 embedding/semantic/Phase 6 상태전이 상류 의존이 **없는** 순수 additive 영속화라 fake로 완전 테스트 가능 — Next Tasks #1 후보 중 최소.

## 결정

| ID | 결정 | 근거 |
|----|------|------|
| **D1 = 최소 영속화만** | apply가 review-only(conflict) proposal을 durable `review_queue` store(in-memory + Mongo, 프로젝트 store 패턴)에 upsert. `status=open` **단일 상태**. resolve/dismiss/reconcile 전이는 도입하지 않는다. | resolve/dismiss 전이는 Phase 6 review 상태 전이 영역(HANDOFF:75 "Phase 6 상태 전이와 함께 검토"). candidate `needs_review`-only(v1.6.50)와 동형으로, 전이는 Phase 6 도입 시 도달하는 forward-defense. 최소·자족 유지. |
| **D2 = GET list 엔드포인트 추가** | `GET /projects/{project_id}/analysis/review-queue` — 프로젝트의 open 항목 조회. memory list 엔드포인트와 동형의 최소 read surface. | read surface가 없으면 영속화가 write-only라 관측·계약 테스트가 불가. 큐가 실제로 채워지는지 검증하려면 read 경로가 필수. |
| **D3 = 결정적 id → 멱등 upsert** | queue entry id = `(project_id, job_id, candidate_id, action)`의 canonical JSON SHA-256. apply 재실행(idempotent replay) 시 같은 conflict가 중복 적재되지 않고 upsert된다. | apply는 재적용 가능(2B.4 idempotent_replay). 같은 job의 같은 conflict를 두 번 apply해도 큐 항목은 하나. 2A `logical_key` 결정적 id 선례와 동형. |
| **D4 = action generic 저장** | entry의 `action`은 `CompareAction`으로 저장. 오늘은 `conflict`만 발화되지만 merge/split이 2B.3에 추가되면 스키마 변경 없이 같은 큐로 흐른다. | 미발화 값을 추측 구현하지 않되(§2), 미래 review-only action이 슬롯인되도록 타입만 열어 둔다. |

## 스코프 (이 슬라이스)

- 신규 `analysis/review_queue.py`: `ReviewQueueEntry` · `ReviewQueueStatus(OPEN)` · `ReviewQueueRepository` Protocol · `InMemoryReviewQueueRepository` · `ReviewQueueService`(enqueue + list_open) · `derive_review_queue_id`.
- 신규 `analysis/review_queue_mongo_repository.py`: `MongoReviewQueueRepository`(collection `review_queue`, deterministic `_id` upsert, project+status index).
- `analysis/apply.py`: `MemoryApplyService`에 optional `review_queue` 주입. conflict 분기에서 enqueue(미주입 시 동작 불변).
- `main.py`: review_queue service 기본 wiring(Mongo 구성 시 Mongo repo) + apply_service 주입 + `GET .../review-queue` 엔드포인트.
- 회귀: `tests/test_review_queue.py`(store/service enqueue·멱등·list), `tests/test_memory_apply.py` 보강(conflict→enqueue 양방향), API 테스트(GET list).

## 스코프 밖 (후속)

- **resolve/dismiss/reconcile 상태 전이**(Phase 6 review 상태 전이와 공동). open→resolved 전이·감사 추적은 Phase 6.
- **merge/split proposal 산출**(2B.3 미발화 — 별칭 자동 판정 안 함, review-only 후속).
- **큐 항목 기반 실제 canonical 재조정 write**(2B.4 merge/split reconciliation).
