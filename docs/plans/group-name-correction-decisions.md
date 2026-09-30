# 그룹 후보 이름 교정 결정

상태: `Resolved` — 사용자 승인 2026-09-30
관련: [`06-candidate-edit-decisions.md`](06-candidate-edit-decisions.md), [`pending-candidate-identity-grouping-decisions.md`](pending-candidate-identity-grouping-decisions.md), [`../system-contract-sot.md`](../system-contract-sot.md)

## Decision needed

기존 후보 `/edit`가 즉시 정본 승격하는 계약과 그룹 승인에서 정본 하나로 수렴하는 계약이 충돌하므로, 그룹 후보의 인물 이름을 함께 고칠 때 어떤 전이를 사용할지 결정해야 했다.

## Options

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 승인 전 이름 교정 | 검토 대기 후보마다 이름만 고친 새 버전을 만들고 그룹에 연결한다 | 관찰·사건 근거와 그룹 승인 흐름을 보존한다 | 새 API와 재시도 처리가 필요하다 |
| B. 기존 `/edit` 반복 | 멤버마다 기존 수정·승인을 실행한다 | 기존 API를 쓴다 | 여러 정본이 생겨 그룹 승인 계약과 충돌한다 |
| C. 그룹 전체 교정 보류 | 개별 수정만 제공한다 | 계약 변경이 없다 | 요청한 동시 수정이 불가능하다 |

**채택: A.** 현재 그룹 승인에서 첫 후보를 정본으로 승격하고 나머지를 같은 정본에 수렴시키는 정책과 맞는다. 사용자는 **인물 이름만 함께 변경**하고 관찰·사건 문장은 각 후보에 남기는 범위를 선택했다. 이 결정은 기존 `/edit`의 즉시 승인 의미를 바꾸지 않고 별도 승인 전 교정 경로를 연다.

## 확정 계약

- `POST /projects/{project_id}/analysis/review-inbox/groups/{group_id}/correct-name`은 project owner 동작이며 `{expected_revision, name}`을 받는다. 인물 그룹에만 적용한다. 비어 있는 이름과 인물 외 그룹은 400, 닫힌 그룹은 404, 오래된 revision과 검토가 시작된 그룹은 409다.
- 각 `needs_review` 후보의 이름만 바꾼 **새 `needs_review` 버전**을 만든다. 원본은 `superseded`로 보존하며 새 버전의 `supersedes_candidate_id`가 원본을 가리킨다. 관찰·근거·출처·provenance·confidence는 유지한다. 교정 단계에서는 canonical memory를 만들지 않는다.
- 새 버전을 같은 그룹의 멤버로 추가한다. 옛 멤버 행과 relation 행은 감사 참조로 보존하고, 검토함은 `needs_review` 교집합만 보여준다. 옛 relation 근거는 후보 버전 연결을 따라 새 후보의 그룹 설명에 계속 표시한다. 그룹 revision을 올려 이전 승인 요청을 무효화한다.
- 원본 후보는 색인 제거, 새 후보는 색인 추가를 예약하고 원본의 열린 충돌 대기열은 정리한다. 중간 저장 실패 뒤 같은 요청은 원본의 고유 `group-name:{group_id}:{candidate_id}` 후계 버전을 찾아 이어간다.
- 그룹 이름 교정은 그룹 활동 로그 한 행으로 기록한다. 이후 그룹 승인은 기존 단일 정본 수렴 경로를 사용한다.

## Follow-up considerations

- 이름이 바뀐 후보들의 자동 정체성 재판정은 이번 교정의 일부가 아니다. 그룹 멤버십은 사용자의 명시적 교정 판단을 따른다.
- 장차 사건 제목 같은 별도 필드의 동시 수정이 필요하면 후보 타입별 공통 필드와 승인 전 버전 규칙을 별도로 결정한다.

## Deferred / out of scope

- 관찰·사건·미해결 질문 문장의 일괄 수정, 이미 확정된 기억의 일괄 변경, 그룹 자동 병합·분할, 기존 `/edit`의 즉시 승인 의미 변경.
