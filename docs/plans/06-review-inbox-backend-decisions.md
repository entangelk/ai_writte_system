# Phase 6 Review Inbox 백엔드 착수 결정 브리프

**상태**: Resolved (오너 승인 2026-07-12)
**정본 SoT**: `docs/system-contract-sot.md` v1.6.63
**선행**: candidate 상태 전이 v1.6.61, review queue v1.6.59, merge/split v1.6.63

## 결정

- **D1 통합 단위**: 아직 canonical promotion 링크가 없는 `needs_review` candidate를 inbox의 한 행으로 삼고, 같은 candidate의 open review queue conflict를 중첩한다. conflict만 별도 중복 행으로 만들지 않는다. legacy 직접 승격 candidate는 canonical 경로로만 보이도록 억제한다(v1.6.60 dedup 계승).
- **D2 상세/diff**: candidate payload와 각 conflict가 가리키는 canonical payload를 반환하고, field별 `before`/`after` diff를 결정적으로 산출한다. matched memory가 없으면 diff는 빈 배열이다.
- **D3 source pointer**: frontend/editor route 문자열은 고정하지 않는다. source ref 정본의 `snapshot_id`, `block_id`, offsets, quote, content_hash를 반환한다. 정본에서 사라진 ref는 가짜 pointer를 만들지 않고 `status=missing`으로 명시한다.
- **D4 쓰기**: 이번 slice는 read-only inbox/list/detail만 추가한다. 기존 confirm/reject/merge/split 단건 API를 재사용한다. 부분 승인·부분 retry·candidate edit는 후속 결정이다.
- **D5 Gate finding**: 영속 Gate finding store가 아직 없으므로 이번 통합 목록에는 Analysis candidate+conflict만 포함한다. 향후 Gate store가 생기면 별도 origin literal로 additive 확장한다.

## HTTP 계약

- `GET /projects/{project_id}/analysis/review-inbox`
- `GET /projects/{project_id}/analysis/review-inbox/{candidate_id}`
- 다른 project 또는 needs_review가 아닌 candidate 상세은 404.
- 목록/상세 모두 candidate가 canonical인 것처럼 표현하지 않고 `status=needs_review`를 그대로 노출한다.

## 제외

- frontend framework, editor URL/selection scheme
- 부분 승인/부분 retry, candidate edit/version 정책
- Gate finding persistence/inbox origin
