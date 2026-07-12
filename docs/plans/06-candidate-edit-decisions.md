# 착수 결정 브리프 — Phase 6 candidate edit (백엔드 계약)

상태: `Resolved` (오너 결정 D1=원 후보의 새 version. D2~D6은 D1이 강제하는 파생 계약 — 기존 패턴 재사용, 아래 명시)
관련: Phase 6 `plans/06-review-ui.md` §69 착수 결정("후보 수정이 원 후보의 새 version인지 별도 사용자 기억인지")·SoT §434 Phase 6·`06-candidate-state-transition-decisions.md`(confirm/reject 선례)·memory append-only version 모델(`memory/service.py:_versioned_upsert`)

## 왜 지금 / 스코프

Phase 6 review action 3종 중 approve(confirm)/reject는 v1.6.61로 백엔드 계약이 열렸다. 남은 하나가 **edit**이다(수용 기준 §60 "approve/reject/**edit**가 권한과 상태 전이 규칙을 따른다"). 이 브리프는 candidate **edit의 백엔드 계약**만 연다. **서브 머신(라이브 불가)에서 완결 가능** — 편집·전이·promotion은 전부 결정적 로직이라 실 embedding/데이터 불요.

**In scope (백엔드)**:
- candidate `edit` action = 편집값으로 **새 candidate version(append-only)** 생성 → confirm→canonical 승격까지 한 액션으로 orchestrate.
- 원 후보의 terminal 표현(`superseded`)과 version 링크(`supersedes_candidate_id`).
- 편집 payload의 schema 재검증, 원 후보의 근거(source_ref_ids)·provenance·confidence 보존.
- edit의 idempotency, de-index, conflict queue 정리, inbox/retrieval 배제를 회귀로 잠금.

**Out of scope (Phase 6 UI slice로 계속 보류)**: 부분 승인/부분 retry, candidate 이외 대상(canonical memory) 직접 edit, action별(create/update/add_evidence/conflict) 세분 승인 UX, entity merge/split 노출(별도 slice), editor route/frontend(§미확정 유지). confidence/provenance 편집(payload만 편집 대상).

## 현재 상태 (primary source)

- `AnalysisCandidateStatus`(`analysis/models.py:26`) = `needs_review`/`confirmed`/`rejected`(v1.6.61). **`superseded` 없음**.
- `AnalysisCandidate`(`analysis/models.py:69`)는 `payload` immutable, version 개념 없음. status는 in-place `update_candidate`로 전이.
- `transition_candidate`(`analysis/service.py:513`) = `needs_review→confirmed/rejected`만 legal, idempotent, cross-terminal/backward 거부.
- `CandidateReviewService`(`analysis/candidate_review.py`) = confirm(전이+promote+de-index+queue resolve)/reject(전이+de-index+queue dismiss) orchestration.
- `promote_candidate`(`memory/service.py:148`)는 status를 검사하지 않고 `candidate.id`를 `source_candidate_id`로 canonical MemoryEntry에 링크(idempotent).
- candidate 요청 dedup unique index = `(project_id, task_id, logical_key)`(`mongo_repository.py:116 uniq_analysis_candidate_request`).

## 결정점

### D1 — edit 결과의 반영 위치 (중심 결정, 오너 확정)

- **D1=원 후보의 새 version (오너 선택)**: 사용자가 후보를 수정 승인하면 편집값으로 candidate의 **새 version(append-only, 새 id)** 을 만들고, 그 version을 confirm→canonical로 승격한다. 원 후보는 `superseded`로 보존(감사 이력), 근거·이전 version·출처 추적이 그대로 남는다. memory append-only 모델(`_versioned_upsert`)과 대칭.
- (기각) 별도 사용자 canonical 기억: 원 후보와 분리된 canonical entry 직접 생성. 출처가 AI 후보와 끊김.
- (기각) 둘 다(분리 모델): 계약 범위 최대. MVP 과잉.

### D2 — edit = edit-and-confirm 단일 액션 (D1이 함의)

D1의 "생성 후 confirm→canonical 승격"에 따라 edit은 **하나의 terminal 검토 액션**이다: 편집값으로 새 version 생성 + 그 version을 `confirmed`로 mint + canonical promote. 편집 주체가 곧 검토자이므로 별도 재confirm 단계를 두지 않는다(needs_review 중간 version을 두면 색인·retrieval에 candidate로 노출되고 흐름이 늘어남). 후속 재편집은 out(원 후보는 superseded terminal).

### D3 — 원 후보 terminal 상태 = `superseded`

새 version이 원 후보를 대체하므로 원 후보는 `needs_review`를 떠나야 한다(inbox/retrieval 배제·de-index). `confirmed`(그 자체가 승격됨을 의미)나 `rejected`(거절 아님)로 오염하지 않도록 신규 terminal `superseded`를 도입한다(memory `SUPERSEDED`와 동형). `superseded`는 **edit 경로 전용**이며 `transition_candidate`(confirm/reject 채널)의 legal target이 아니다 — edit orchestration이 원 후보를 직접 `superseded`로 기록한다.

### D4 — idempotency (기존 unique index 재사용, 새 key 불요)

원 후보는 **최대 한 번** edit된다(edit 후 `superseded` terminal). 새 version의 `logical_key = f"edit:{원본_id}"`, task = 원본 task이므로 기존 `(project, task, logical_key)` unique index가 replay·동시성을 모두 잠근다: replay는 `find_candidate_request`로 기존 successor를 반환(no-op), 동시 2회는 두 번째가 `DuplicateAnalysisCandidateRequest`→successor 재조회(승자 replay, promote 선례와 동형). **클라이언트 idempotency_key 불요.** 같은 원본에 다른 payload로 재-edit해도 첫 successor를 idempotent replay로 반환(원본이 이미 superseded).

### D5 — 근거·provenance·confidence 보존

edit은 **payload(내용) 교정**이다. source_ref_ids·provenance·confidence는 원 후보에서 보존한다(출처 grounding 불변, 검토자가 값만 정정). payload는 candidate_type schema로 재검증(`validate_candidate_payload`, 실패 시 `InvalidAnalysisCandidate`→400). confidence/provenance 편집은 후속. 새 version은 record_candidates validation(source anchor)을 우회하고 서비스가 직접 구성 — anchor는 candidate에 저장되지 않고 원 후보 grounding을 승계하므로 재검증 대상 아님.

### D6 — de-index / queue / promotion 정리 (confirm 선례 재사용)

- 원 후보(색인돼 있던 needs_review)는 `CANDIDATE_REMOVED` enqueue → worker 재유도가 not-needs_review면 delete(self-heal). 새 `confirmed` version은 record 경로를 안 타므로 애초에 색인 안 됨(제거 대상 없음).
- 원 후보의 open conflict는 **resolve**(edit은 승인 계열, reject의 dismiss와 대비).
- 새 version을 `promote_candidate(MANUAL)`로 canonical mint(`source_candidate_id`=새 version id). 원 후보는 promote되지 않음.

## 경계 매트릭스 (구현 시 회귀 잠금 예정)

| 분기 | 방향 | 잠금 대상 |
|---|---|---|
| edit → 새 version 생성(confirmed) + 원본 superseded | under-strict | version 미생성/원본 상태 미전이 시 실패 |
| 새 version confirmed + canonical promote(링크=새 id) | under-strict | promote 누락/원본에 링크 시 실패 |
| 원본 superseded → needs_review set·inbox·retrieval에서 배제 | over-strict | 원본이 계속 노출되면 실패 |
| 새 version(confirmed)도 needs_review set·inbox 미노출 | over-strict | 새 version이 candidate로 노출되면 실패 |
| 새 version이 편집 payload·원본 근거/provenance/confidence 보존 | under/over | 값 소실 또는 근거 미승계 시 실패 |
| edit → CANDIDATE_REMOVED enqueue(원본 de-index) | under-strict | de-index 누락 시 실패 |
| 원본 open conflict resolve(dismiss 아님) | under/over | 잘못된 큐 전이 시 실패 |
| 같은 원본 edit replay = no-op(중복 version/promote/de-index 없음) | over-strict | 중복 발생 시 실패 |
| 편집 payload schema 위반 → 400, 원본 상태 불변 | under/over | invalid payload가 통과하거나 원본을 오염하면 실패 |
| needs_review 아닌 후보(confirmed/rejected/superseded) edit → 409 | over-strict | terminal 후보 edit 허용 시 실패 |
| `transition_candidate`의 target=superseded 거부(confirm/reject 채널 아님) | over-strict | superseded가 generic 전이로 도달 가능하면 실패 |
| cross-project / missing 후보 edit → 404 | over-strict | 격리 실패 시 실패 |
| HTTP `/edit` 200/404/409/400 매핑 | under/over | 상태코드 오매핑 시 실패 |

## 성격

신규 status literal `superseded` + candidate version 링크 필드 `supersedes_candidate_id` + `AnalysisService.edit_candidate` + `CandidateReviewService.edit` + HTTP `POST .../candidates/{id}/edit`. 기존 promote/transition/de-index/queue 머신 재사용, 신규 repo 메서드 없음(기존 index 재사용). SoT §434 Phase 6 확장 + §미확정에서 edit 정책 해소 → **minor bump(v1.6.66)**. 부분 승인·merge/split·frontend는 계속 미확정(Phase 6 UI slice).
