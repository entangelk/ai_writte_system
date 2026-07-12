# Decision brief — Phase 6 Gate finding persistence and Review Inbox integration

상태: `Approved for Phase 6 Gate finding persistence first slice`  
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`06-review-ui.md`](06-review-ui.md), [`06-review-inbox-backend-decisions.md`](06-review-inbox-backend-decisions.md)  
목적: transient Context Gate finding을 영속화하고 Review Inbox에 추가할 때 저장 범위, identity, lifecycle, public API를 추측하지 않도록 첫 구현 slice를 좁힌다.

## 현재 확정된 경계

- Context Gate의 `GateDecision` literal은 `pass|reject`이며 `GateFinding`은 현재 `check`와 `detail`만 가진 transient 응답 값이다.
- `/context-search` 응답이 끝나면 finding은 사라진다. Gate finding repository, request/run identity, lifecycle status는 아직 없다.
- Review Inbox v1.6.64는 미승격 `needs_review` candidate를 한 행으로 하고 open conflict를 중첩한다.
- Gate finding은 영속 store가 생기면 Review Inbox에 additive origin으로 확장한다.
- 기존 candidate confirm/reject와 merge/split은 단건·명시 action이며 Gate finding과의 관계는 계약되지 않았다.
- 이 slice는 Gate 판정 규칙, threshold, LLM prompt 품질 튜닝을 변경하지 않는다.

## 구현을 막는 미확정 항목

1. 영속화 대상: reject finding만, pass/reject 모두
2. persistence 실패가 `/context-search` 응답을 실패시킬지
3. finding identity와 client retry idempotency
4. lifecycle: open 단일, resolved/dismissed terminal 전이
5. candidate action과 Gate finding 상태를 자동 연동할지
6. 저장 payload: 최소 재현 envelope, ContextPackage 전체 snapshot
7. Review Inbox 표현: additive section, 공통 union item
8. 첫 public API 범위

## 1. 영속화 대상

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. reject finding only | `GateDecision=reject`의 finding만 저장한다 | 실제 검토 대상만 남고 store가 작다 | pass 실행 감사 이력은 남지 않음 |
| B. pass + reject | 모든 Gate 결과를 저장한다 | 실행 감사 이력이 풍부하다 | Review store가 실행 로그 역할까지 떠안음 |

추천: **A**. Review Inbox의 목적은 사용자가 조치할 항목을 보여주는 것이며 pass 결과는 검토 lifecycle이 필요하지 않다.

## 2. Persistence 실패와 context-search 응답

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. persistence 강제 | reject finding 저장 실패를 502로 반환한다 | reject가 inbox에 남는다는 계약을 보장 | ContextPackage/Gate 계산이 끝났어도 요청 실패 |
| B. best-effort | 저장 실패와 무관하게 원 Gate 응답을 반환한다 | 검색 가용성 우선 | 사용자가 본 reject가 inbox에서 유실 가능 |

추천: **A**. 영속화를 public workflow로 약속한다면 응답 성공과 inbox 유실이 갈라져서는 안 된다. Context search는 같은 idempotency key로 안전하게 재시도하도록 D3과 묶는다.

## 3. Finding identity와 idempotency

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. client idempotency key | `/context-search`에 `idempotency_key`를 추가하고 `(project_id, key, ordinal, check)` canonical JSON SHA-256으로 id를 만든다 | retry 중복 방지, project 격리 명확 | 기존 request public contract 확장 |
| B. server run id | 매 실행 새 run id를 만든다 | client 변경 없음 | client retry마다 중복 finding 생성 |
| C. content-derived id | query/check/detail 내용만으로 id를 만든다 | 별도 key 불필요 | 독립 실행의 같은 finding까지 하나로 합쳐 provenance 손실 |

추천: **A**. Review action이 재시도 가능하려면 finding 생성부터 identity가 결정적이어야 한다. `idempotency_key`는 non-empty string 필수로 두고 project scope 밖에서는 재사용 가능하게 한다.

## 4. Lifecycle

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. open → resolved/dismissed | resolved=조치 완료, dismissed=검토 후 미조치. terminal replay는 idempotent, cross-terminal은 409 | inbox를 운영 가능, 기존 review queue 패턴과 일치 | 상태 전이 API 필요 |
| B. open only | 최초 저장과 조회만 구현한다 | 첫 slice 최소 | 처리한 finding을 inbox에서 제거 불가 |

추천: **A**. v1.6.61 review queue lifecycle과 같은 패턴을 재사용하고, terminal 상태에서 backward transition은 금지한다.

## 5. Candidate action 자동 연동

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 자동 연동 없음 | Gate finding은 별도 resolve/dismiss action으로만 닫는다 | 잘못된 관계 추론으로 finding을 닫지 않음 | 사용자가 별도 action 수행 |
| B. candidate action에 연동 | confirm/reject/merge/split 시 관련 finding도 닫는다 | 사용자 action 수 감소 | finding↔candidate relation 계약이 없어 오종료 위험 |

추천: **A**. 현재 GateFinding은 candidate id조차 필수로 갖지 않으므로 자동 연동 근거가 없다.

## 6. 저장 payload

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최소 재현 envelope | id/project/key/ordinal/check/detail/status, query/purpose/needs, trace에 존재하는 안정 pointer id만 저장 | stale canonical 사본과 중복 최소화 | 당시 ContextPackage 전체를 그대로 재현하지 못함 |
| B. ContextPackage snapshot | Gate 입력 package 전체를 저장한다 | 당시 판정 입력 재현이 쉬움 | payload 중복, stale canonical/candidate 사본 보존 위험 |

추천: **A**. Mongo SOT가 정본이므로 source_ref/candidate/memory/snapshot의 안정 id만 저장하고 상세은 조회 시 정본 재유도한다. `created_at`/terminal timestamp는 repository clock 주입값으로 둔다.

## 7. Review Inbox 표현

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. additive section | 기존 `items`는 유지하고 `gate_findings`를 추가한다. 각 finding은 `origin=context_gate` | v1.6.64 consumer 하위호환, origin별 필드 명확 | candidate와 단일 정렬하려면 client 조합 필요 |
| B. common union items | candidate와 finding을 하나의 item 배열로 합친다 | 단일 정렬/필터 쉬움 | nullable 필드 증가, 기존 envelope breaking change |

추천: **A**. 기존 Review Inbox 계약을 깨지 않고 Gate origin을 추가한다.

## 8. 첫 public API

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. inbox + detail + transitions | inbox `gate_findings` 추가, finding detail, resolve/dismiss API를 함께 구현 | 저장부터 처리까지 한 slice에서 닫힘 | 첫 slice가 repository-only보다 큼 |
| B. Gate finding list only | Gate 전용 list API만 추가하고 inbox/transition은 후속 | 첫 구현 작음 | Phase 6 사용자 흐름이 계속 끊김 |

추천: **A**. 첫 API는 다음으로 고정한다.

- `GET /projects/{project_id}/analysis/review-inbox`에 `gate_findings` additive
- `GET /projects/{project_id}/analysis/gate-findings/{finding_id}`
- `POST /projects/{project_id}/analysis/gate-findings/{finding_id}/resolve`
- `POST /projects/{project_id}/analysis/gate-findings/{finding_id}/dismiss`
- missing/cross-project project 또는 finding은 404, illegal cross-terminal transition은 409.

## 9. 첫 구현 slice 제안

추천안이 승인되면 다음 코드 slice로 제한한다.

1. Gate finding domain/store
   - `GateFindingStatus.OPEN|RESOLVED|DISMISSED`
   - deterministic finding id
   - in-memory + Mongo repository
2. `/context-search` request에 필수 `idempotency_key` 추가
3. reject finding만 persistence하고 pass는 저장하지 않음
4. Review Inbox 응답에 `gate_findings` additive
5. finding detail + resolve/dismiss endpoint
6. 회귀
   - pass 저장 없음 / reject N개 저장
   - same-key replay 무중복 / cross-project 격리
   - persistence 실패 → 502
   - same-terminal replay 멱등 / cross-terminal 409
   - candidate action이 finding 상태를 바꾸지 않음
   - 기존 inbox `items` envelope 불변
   - Gate list/detail/transition missing scope/id → 404
   - Mongo compound index + upsert/get/open-only 정렬 round-trip

## 제외 범위

- Gate check 종류, 정확도, threshold, prompt 튜닝
- Writing Gate persistence(Phase 5 계약 후 별도 origin 후보)
- frontend, bulk action, notification
- candidate와 Gate finding 관계 자동 추론
- ContextPackage 전체 snapshot 저장

## 승인 결과

2026-07-12 오너가 추천안을 승인하되 확장 경계를 함께 요청했다.

- persistence target: **D1=A**. reject-only로 시작하되 repository/model은 향후 pass 감사 이력 저장을 추가할 수 있게 Gate result origin과 fingerprint를 보존한다.
- persistence failure: **D2=A**. 저장 실패는 502.
- identity/idempotency: **D3=A**. `/context-search`에 필수 `idempotency_key` 추가.
- lifecycle: **D4=A**. open→resolved/dismissed, same terminal replay 멱등, cross-terminal 409.
- candidate action linkage: **D5=A**. 자동 연동 없음.
- stored payload: **D6=A**. 최소 재현 envelope + request/result SHA-256 fingerprint + 안정 pointer ids를 저장한다.
- inbox representation: **D7=A**. 기존 `items` 불변 + `gate_findings` additive. 클라이언트 독립 조합을 위해 Gate 전용 list/detail API도 연다.
- public API: **D8=A**. inbox 통합, Gate list/detail, resolve/dismiss를 같은 slice에서 구현한다.

### D6 후속 메모 — 완전 재현 가능성

이번 slice의 fingerprint는 같은 request/result envelope 여부를 검증하고 pointer를 정본 재조회할 수 있게 하지만, 시간이 지난 뒤 당시 ContextPackage를 byte-for-byte 재생성하지는 못한다. 완전 재현이 필요해지면 별도 immutable `GateRunManifest`를 검토한다.

- finding들과 별도 run identity로 1:N 연결
- 각 pointer의 collection/document/version/content_hash 기록
- planner/prompt/model/version 및 retrieval backend 설정 기록
- ContextPackage 전체 payload 대신 canonical manifest + 선택적 archived blob
- 보존 기간과 개인정보/원문 중복 비용을 서비스 운영 요구와 함께 결정

이 후속은 서비스화 시 감사·검증 이력 접근 요구가 생기는 시점에 별도 결정 브리프로 연다.
