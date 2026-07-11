# 착수 결정 브리프 — Phase 6 candidate 상태 전이 (백엔드 계약)

상태: `Resolved` (오너 결정 D1=분리 모델·D2=CANDIDATE_REMOVED·D3=review_queue resolve/dismiss 포함·D4=idempotent 단건·D5=rejected 보존)
관련: Phase 6 `plans/06-review-ui.md` §66 착수 결정·SoT §464(`confirmed`/`canonical` 미확정)·§465(review action idempotency 미확정)·5개 forward-defense stub(candidate de-index·retriever needs_review 필터·drain self-heal·review queue resolve/dismiss·(e) v1.6.60 dedup)

## 왜 지금 / 스코프

여러 slice가 "Phase 6 전이 도입 시 도달"이라며 forward-defense stub을 남겼다. 이 브리프는 그 **수렴점인 candidate 상태 전이의 백엔드 계약**만 연다. **서브 머신(라이브 불가)에서 완결 가능** — 전이는 결정적 로직이라 실 embedding/데이터 불요.

**In scope (백엔드)**:
- candidate status enum 확장(`needs_review` → `confirmed`/`rejected`)과 전이 서비스(idempotent).
- 전이 시 candidate de-index 이벤트(색인 upsert-only stub의 실경로화).
- conflict의 review_queue `open` → `resolved`/`dismissed` 전이.
- 전이 후 (e) dedup·retriever 필터가 상위집합으로 흡수됨을 회귀로 잠금.

**Out of scope (Phase 6 UI slice로 보류)**: Review Inbox/Detail UI, source deep link, Gate finding+candidate inbox 통합, entity merge/split, 부분 승인 UX, editor route 계약, frontend 전체(§32 보류 유지).

## 현재 상태 (primary source)

- `AnalysisCandidateStatus`(`analysis/models.py:26`) = `NEEDS_REVIEW` **단일**.
- `ReviewQueueStatus`(`analysis/review_queue.py:35`) = `OPEN` **단일**; resolve/dismiss는 명시적으로 Phase 6 forward-defense(주석 :13-14).
- `promote_candidate`(`memory/service.py:134`)가 **이미** candidate→canonical `MemoryEntry`(`source_candidate_id` 링크)를 mint(수동/auto-threshold). 승격돼도 candidate status는 `needs_review`로 남음 → v1.6.60 (e)가 retrieval에서 억제.
- `IndexSyncEvent`(`indexing/service.py`) = `MEMORY_UPSERTED`·`CANDIDATE_UPSERTED`·`PROJECT_ARCHIVED`·`DRAFT_ARCHIVED`. **candidate 제거 이벤트 없음**(색인 upsert-only).
- job 전이(`analysis/service.py:261 _transition_job`, illegal 전이 거부 + 조건부 필드 검증)가 **candidate 전이의 선례 패턴**.

## 결정점 (오너)

### D1 — `confirmed`와 `canonical`의 관계 (중심 결정, SoT §464)

이미 promotion(→canonical MemoryEntry)이 존재하므로 "승인"의 의미를 이것과의 관계로 정의해야 한다.

- **D1=A (분리 모델, 권장)**: 승인 = candidate status `needs_review→confirmed` **+** (미승격 시) canonical MemoryEntry로 promotion. `confirmed`는 candidate 쪽 **검토 결정 기록**, `canonical`은 memory 쪽 **물질화** — 둘은 `source_candidate_id`로 링크. 거절 = `needs_review→rejected`(promotion 없음). 기존 promote 머신 재사용, (e)/dedup·retriever 필터와 정합. `confirmed` candidate는 canonical 경로로 서빙되고 candidate 색인에서 빠져 D7 중복이 원천 소멸.
- **D1=B (동일시)**: 승인 = 곧 canonical mint, 별도 `confirmed` status 없음(candidate는 승인 즉시 소멸/archived). 더 단순하나 검토 이력(누가 언제 승인)을 candidate 쪽에 못 남기고, 부분 상태(reviewed-but-deferred) 표현 불가.

### D2 — 전이 시 candidate de-index 메커니즘

`confirmed`/`rejected`가 되면 candidate는 더는 `needs_review`가 아니므로 candidate 색인(`candidate_vectors`/`candidate_lexical`)에서 제거돼야 한다.

- **D2=A (대칭 이벤트, 권장)**: 신규 `IndexSyncEvent.CANDIDATE_REMOVED` + worker composite **delete** drain(archive delete 선례와 동형; 대상 없으면 idempotent success). 전이 서비스가 choke point에서 enqueue.
- **D2=B (retrieval 필터에만 의존)**: 색인은 그대로 두고 retriever의 `get_candidate`→needs_review 재유도 필터가 stale 색인을 걸러냄(현재도 그렇게 함). 색인 정리는 안 하니 stale 벡터가 누적(색인 비대·self-heal 없음). 최소지만 부채.

### D3 — conflict review_queue 전이

- **D3=A (권장)**: `ReviewQueueStatus`에 `RESOLVED`/`DISMISSED` 추가 + `ReviewQueueService.resolve/dismiss`(open→terminal, idempotent). candidate 전이가 관련 conflict 큐 항목을 닫을지(자동)와 수동 dismiss를 분리. merge/split **산출**은 여전히 out(스키마만 열림, v1.6.59 D4 유지).
- **D3=B**: 이번 slice에서 review_queue는 손대지 않고 candidate status 전이만. resolve/dismiss는 후속.

### D4 — review action idempotency (SoT §465)

- **D4=A (권장)**: 같은 candidate에 같은 전이 재적용은 no-op replay(중복 status 전이·중복 de-index enqueue·중복 promotion 금지). 결정적 전이 id 또는 status 선검사. 수용 기준 §61("같은 review action 재시도로 중복 전이·sync 없음") 충족. **부분 승인/부분 retry 정책은 out**(단건 전이만).
- **D4=B**: idempotency 후속. (수용 기준 §61 위반 위험 → 비권장.)

### D5 — rejected candidate 보존

- **D5=A (권장)**: `rejected` candidate는 store에 보존(감사 이력), 색인만 제거, retrieval 제외. archive/삭제 안 함.
- **D5=B**: rejected는 삭제. 감사 이력 상실.

## 경계 매트릭스 (구현 시 회귀 잠금 예정)

| 분기 | 방향 | 잠금 대상 |
|---|---|---|
| needs_review→confirmed 전이 + promotion 링크 | under-strict | 전이·promotion 누락 시 실패 |
| needs_review→rejected 전이(promotion 없음) | under/over | rejected가 promotion되면 실패 |
| illegal 전이 거부 — cross-terminal(confirmed↔rejected) + backward(confirmed→needs_review, **rejected→needs_review**) 4종 전수 | over-strict | 역전이/교차전이 허용 시 실패 |
| 전이 → CANDIDATE_REMOVED enqueue(de-index) | under-strict | de-index 누락 시 실패 |
| CANDIDATE_REMOVED가 worker per-sink 경로로 routing → 실 delete | under-strict | `_PER_SINK_EVENTS`에서 빠지면(archive 경로行) 실패 |
| 같은 전이 재적용 no-op(중복 전이/sync 없음) | over-strict | 중복 발생 시 실패 |
| 전이 후 retriever가 candidate 미반환((e) 상위집합) | over-strict | 전이 candidate가 노출되면 실패 |
| conflict review_queue open→resolved/dismissed | under/over | 잘못된 전이 시 실패 |
| cross-project 전이 격리 | over-strict | 타 프로젝트 candidate 전이 시 실패 |

## 성격

새 status/이벤트 literal(`confirmed`/`rejected`/`CANDIDATE_REMOVED`, review_queue `resolved`/`dismissed`) + 전이 서비스 + de-index drain. SoT §464/§465 미확정을 D1/D4로 확정 → **minor bump(v1.6.61 예상)**. UI·merge/split은 계속 미확정(Phase 6 UI slice).
