# Decision brief — 장→장면 계층화

상태: `Resolved — D1=A · D2=A · D3=A · D4=A · D5=A · D6=A · D7=B · D8=A (오너 2026-08-28)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md),
[`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md)
목적: 오너가 확정한 **“장은 장면의 집합”** 방향을 기존 평면 ordered-unit 계약과
데이터를 손상하지 않는 실행 계약으로 좁힌다.

## 이미 확정된 방향 — 2026-08-28

- `unit_kind`를 단순 라벨로 유지하거나 제거하지 않는다.
- 장과 장면 사이에 실제 부모-자식 관계를 둔다.
- **장은 장면의 집합**이다.

장 자체가 별도 본문을 가질 수 있는지는 이 문장에서 유도하지 않는다. 아래 D2에서 별도로
결정한다.

이 방향은 W0의 `chapter→scene nesting은 열지 않는다`와 SoT v1.7.9 D2=A(평면
ordered unit)를 폐기하는 계약 변경이다.

## Owner decisions — 2026-08-28

- **D1=A** — Chapter를 별도 정본 엔티티로 둔다.
- **D2=A** — Chapter는 metadata-only이고 실제 산문 정본은 Scene(Draft)이 소유한다.
- **D3=A** — 기존 Draft ID·version·snapshot·본문을 보존하는 결정적 one-shot 이관을 한다.
  오너는 테스트 단계라 데이터 삭제도 허용했지만, D3=C는 삭제가 아니라 legacy 이중 계약이라
  더 복잡하다. 오너가 “A가 편하면 A”를 허용했으므로 무손실·단일 계약인 A를 채택한다.
- **D4=A** — `other` 예외 축을 제거하고 migration에서 Scene으로 통합한다.
- **D5=A** — Chapter와 Scene이 각 parent 범위의 연속 순열을 소유한다.
- **D6=A** — Writing AI는 같은 Chapter의 다음 Scene만 만든다. 새 Chapter 생성은 사용자
  명시 동작이다. 오너 근거는 일반적으로 장 마지막 장면의 이어쓰기가 다음 장을 자동 생성하지
  않는다는 저작 흐름이다.
- **D7=B** — Chapter purge는 모든 자식 Scene을 포함한다. 안전 가드는 장 보관 선행·정확한
  장 제목 확인·자식 중 active 생성 잡 존재 시 409·503 uncertain 잠금·404 재파기 성공 처리다.
- **D8=A** — export에 Chapter→Scene heading 계층을 반영하고 Chapter 보관은 자식 상태를
  덮어쓰지 않는 파생 가시성으로 처리한다.

## Decision needed

**장을 어떤 정본 엔티티로 저장하고, 기존 평면 원고를 어떤 장·장면 트리로 무손실
이관할지 결정해야 한다** — 현재 스펙은 계층을 명시적으로 금지하고 부모 필드·계층 순서·
장 삭제 의미가 없으므로 오너의 방향만으로는 공개 API와 마이그레이션을 유도할 수 없다.

## D1. 장의 저장 모델

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 `Chapter` 엔티티 | `chapters`가 장 메타데이터를 소유하고, `Draft`는 `chapter_id`로 장을 가리킨다 | 장과 장면의 identity·불변식이 모델에 그대로 드러남 | repository·Mongo collection·API를 새로 추가해야 함 |
| B. `Draft` 단일 컬렉션의 typed tree | 장과 장면을 모두 `drafts`에 두고 장면만 `parent_chapter_id`를 가진다 | 기존 목록·ID·저장소를 많이 재사용 | 모든 Draft 경로가 “장인가, 본문 원고인가”를 반복 검사해야 함 |
| C. 순서 기반 암묵 그룹 | 부모 ID 없이 chapter 행 다음 scene들을 다음 chapter 전까지 자식으로 해석한다 | 스키마 변경이 가장 작음 | reorder 한 번으로 귀속이 조용히 바뀌고 참조·삭제·동시 수정에서 부모를 안정적으로 식별할 수 없음 |

### Recommendation + reason

**A. 별도 `Chapter` 엔티티를 추천한다.** 현재 `Draft`는 version·snapshot·분석·Writing
accept의 본문 정본이라는 의미가 이미 넓게 잠겨 있다. 로컬 1인 프로젝트 단계에서도 그
의미를 “본문일 수도 있고 컨테이너일 수도 있음”으로 흐리는 것보다, 작은 새 엔티티 하나로
불가능 상태를 없애는 편이 이후 삭제·내보내기·AI 생성 계약을 단순하게 만든다.

## D2. 장 자체 본문 허용 여부

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 장은 metadata-only | 제목·순서·보관 상태만 소유하고 모든 실제 산문은 Scene의 version/snapshot에 둔다 | “장=장면의 집합”이 가장 명확하고 저장·분석·이어쓰기 단위가 하나로 닫힘 | 장 서문·요약을 본문처럼 직접 쓰는 흐름은 제공하지 않음 |
| B. 장 요약을 별도 필드로 허용 | 장은 scene 본문과 다른 짧은 synopsis/goal 필드를 가질 수 있다 | 장 기획 정보를 보존하면서 산문 정본과 구분 | 길이·버전·AI 주입 여부를 별도 계약해야 함 |
| C. 장도 versioned 본문을 가짐 | 장과 Scene이 모두 DraftVersion/Snapshot 본문을 가진다 | 기존 chapter Draft의 의미를 가장 그대로 보존 | export 순서와 이어쓰기에서 장 본문과 장면 본문의 관계가 모호하고 본문 단위가 다시 둘이 됨 |

### Recommendation + reason

**A. 장은 metadata-only를 추천한다.** 장 요약/목표는 실제 요구가 생기면 산문 정본과 구분된
필드로 여는 편이 낫다. 지금 장에 versioned 본문까지 허용하면 기존 평면 모델 위에 parent만
얹는 결과가 되어, 장면 단위 분석과 4000자 상한의 의미가 다시 갈린다.

## D3. 기존 데이터 이관

현재 `chapter` Draft도 실제 본문과 version/snapshot을 가질 수 있다. 그 ID 연결을 끊으면
분석·활동·accept receipt·generation job 등 이미 저장된 참조가 함께 흔들린다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 Draft ID 보존 | 기존 `chapter` Draft마다 같은 제목의 Chapter를 만들고, 원 Draft는 그 장의 첫 Scene으로 재분류한다. 장면 제목은 고정값 `본문`으로 둔다. 뒤따르는 `scene|other`는 다음 chapter 전까지 같은 장에 귀속하고, 선행 chapter 없는 원고는 `미분류` 장에 둔다 | 모든 본문·version·snapshot·참조 ID를 그대로 보존. 결정적 one-shot 가능 | 기존 chapter 제목이 Chapter로 이동하고 첫 장면 제목은 새로 정해야 함. 잘못 분류된 평면 순서를 그대로 그룹화할 수 있음 |
| B. Chapter ID 보존·본문 복제 | 기존 chapter Draft를 Chapter로 전환하고 본문/version/snapshot을 새 Scene ID로 복제·재연결한다 | 기존 chapter ID가 장 ID로 남음 | 참조 컬렉션 전수 재작성 또는 중복이 필요해 가장 위험하고 rollback이 큼 |
| C. 자동 이관 없음 | 기존 원고는 legacy 상태로 두고 사용자가 장·장면을 수동 배정해야 새 기능을 사용하게 한다 | 잘못된 자동 귀속 없음 | 배포 직후 기존 프로젝트가 두 계약 사이에 머물며, 읽기·쓰기 경로가 legacy와 hierarchy를 동시에 지원해야 함 |

### Recommendation + reason

**A. 기존 Draft ID 보존을 추천한다.** 이 저장소의 정본 보존 정책과 가장 잘 맞고,
본문 데이터나 외부 참조를 이동하지 않는다. 자동 귀속 결과는 migration dry-run에서
프로젝트별 트리로 먼저 출력하고, 실제 쓰기는 maintenance window의 project 단위
transaction으로 시행한다.

## D4. `other`의 처리

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 장면으로 통합 | migration에서 `other`를 Scene으로 바꾸고 신규 생성 enum에서는 제거한다 | 런타임 모델이 Chapter→Scene 두 종류로 닫힘 | 프롤로그·메모 같은 독립 본문도 장에 넣어야 함 |
| B. 독립 본문으로 유지 | `other`는 chapter_id 없는 top-level Draft로 유지한다 | 기존 용도를 가장 넓게 보존 | 계층 목록·정렬·export가 Chapter와 Other를 함께 다루는 세 번째 축을 계속 가짐 |
| C. 분류를 강제하지 않고 legacy 전용 | 기존 `other`는 읽기만 허용하고 수정·신규 생성 전에 Chapter/Scene 배정을 요구한다 | 새 데이터는 깨끗함 | legacy 상태 전이 UI와 오류 계약이 추가됨 |

### Recommendation + reason

**A. 장면으로 통합을 추천한다.** 현재 `other`도 종류에 따른 동작이 전혀 없고 기본 생성
라벨 역할만 한다. 계층화를 하면서 세 번째 예외 축을 계속 보존하면 “장은 장면의 집합”이라는
새 모델이 다시 흐려진다. 선행 장이 없으면 합성 `미분류` 장이 무손실 수용한다.

## D5. 계층 순서와 재정렬 계약

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 2단계 연속 순열 | Chapter는 project 안 `position=1..C`, Scene은 chapter 안 `position=1..S`. reorder는 전체 tree를 한 번에 보낸다 | 불변식과 UI가 실제 계층과 일치하며 장 이동 시 자식이 함께 움직임 | 기존 전역 `(project_id, position)` 인덱스와 reorder API를 교체해야 함 |
| B. 전역 preorder + parent | 모든 노드는 전역 `position=1..N`을 유지하고 parent만 추가한다 | 기존 position을 재사용 | 부모의 장면이 연속이어야 한다는 두 번째 불변식이 필요하고 장 이동이 여러 행 shift가 됨 |
| C. fractional position | 장·장면에 간격/fractional key를 둔다 | 부분 이동 write가 작음 | 현 규모에 불필요한 정렬 복잡도와 compaction 규칙이 생김 |

### Recommendation + reason

**A. 2단계 연속 순열을 추천한다.** 기존 전역 순열은 평면 모델의 산물이다. 계층을 도입하면서
그 제약까지 억지로 보존하면 parent와 position이 서로 다른 진실을 말할 수 있다. 전체 tree
reorder는 현재 완전 순열·단일 사용자·원자 교체 선례도 그대로 이어받는다.

## D6. 생성과 `start_next_unit`

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 다음 장면만 자동 생성 | current Scene의 같은 Chapter에 다음 Scene을 만든다. 새 Chapter와 첫 Scene은 사용자가 먼저 만든다 | accept transaction 변경이 가장 작음 | “다음 장 시작” AI 흐름이 두 단계가 되고 현재 next kind 선택을 잃음 |
| B. target을 두 동작으로 명시 | `next_scene`은 같은 Chapter의 다음 Scene, `new_chapter`는 새 Chapter+첫 Scene을 한 transaction에서 만든다 | 사용자 의도와 저장 결과가 정확히 대응하고 현재 `start_next_unit`의 새 장 흐름을 보존 | candidate/request/receipt/partial response 계약과 원자 write set이 넓어짐 |
| C. 현재 kind와 위치로 추론 | current/next kind 조합으로 같은 장 또는 새 장을 서버가 추론한다 | request 필드가 작음 | 같은 입력의 의미가 현재 트리에 따라 달라지고 prompt가 저장 target을 재결정하게 됨 |

### Recommendation + reason

**확정 결과는 A다.** 이어쓰기는 현재 Chapter 안의 다음 Scene 생성으로만 좁히고, 새 Chapter는
사용자가 명시적으로 만든다. 장의 마지막 Scene에서 이어쓰기를 눌렀다는 사실만으로 다음 장까지
추론하는 것은 일반적인 저작 흐름과 맞지 않고 원자 write set도 불필요하게 넓힌다.

## D7. 장 삭제

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 빈 장만 삭제 | active·archived Scene이 하나도 없는 Chapter만 삭제한다. 장면 삭제는 현재 draft purge 계약을 쓴다 | 우발적 연쇄 파기를 구조적으로 막고 첫 슬라이스가 작음 | 장 전체 삭제는 장면을 하나씩 정리해야 함 |
| B. 명시적 cascade purge | 장 보관 후 이름 확인으로 모든 자식 Scene과 Chapter를 한 transaction/reconciler 흐름에서 파기한다 | 사용자가 기대하는 장 단위 삭제를 제공 | 현재 draft purge보다 파기 그래프·503 uncertain 범위가 크게 넓어짐 |
| C. 자식 재귀속 | 장 삭제 시 Scene을 인접 장이나 `미분류`로 옮긴다 | 본문 손실 없음 | 삭제가 사실상 이동이 되어 사용자 의도가 모호하고 순서가 예상 밖으로 바뀜 |

### Recommendation + reason

**확정 결과는 B다.** 장 삭제는 사용자가 기대하는 대로 모든 자식 Scene을 포함하되, 장 보관
선행·정확한 제목 확인·active 생성 잡 write 0/409·503 uncertain·재파기 404 성공 처리로 기존
draft purge보다 넓어진 파괴 범위를 잠근다.

## D8. 내보내기와 보관

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 계층을 출력에 반영 | Markdown은 `# 장`·`## 장면`, TXT는 장/장면 제목 줄을 순서대로 출력한다. 보관된 장은 기본 export에서 자식 전체를 숨기되 자식 상태를 덮어쓰지 않는다 | 저장 계층과 결과물이 일치하고 장 보관 복구가 가능 | 기존 “kind별 heading mapping 없음” 계약 변경 |
| B. 저장만 계층화 | 목록 UI만 그룹화하고 export는 현재 Scene 평면 제목을 유지한다 | export 변경이 작음 | 사용자가 받은 원고에서 장 경계가 사라짐 |
| C. 보관을 자식에 전파 | 장 보관/복원 시 모든 Scene의 archived 상태도 함께 쓴다 | 조회 필터가 단순 | 장 보관 전 개별 Scene 상태를 잃고 대량 write/rollback이 필요 |

### Recommendation + reason

**A. 계층을 출력에 반영하되 보관은 파생 가시성으로 처리하는 것을 추천한다.** 장 보관은
자식 정본을 다시 쓰지 않고 조회·export에서만 숨겨야 복원 시 이전 장면 상태를 정확히 보존한다.

## Follow-up considerations

- `Chapter`에는 처음부터 일반적인 `id/project_id/title/position/archived`만 둔다. synopsis,
  목표, AI 요약은 요구가 생길 때 별도 versioned 계약으로 연다.
- Scene은 `chapter_id`를 필수로 두고 `(chapter_id, position)` unique index를 둔다.
- migration은 dry-run 결과, project 단위 transaction, 재실행 no-op, 부분 상태 fail-closed,
  archived 포함, 기존 ID·version·snapshot·본문 byte 보존을 양방향 회귀로 잠근다.
- 장 보관과 장면 보관은 별도 상태다. 유효 가시성은 `chapter.archived OR scene.archived`로
  계산하되 자식 필드를 자동 변경하지 않는다.
- 장 unarchive 공개 경로는 제공하지 않는다. D8=A의 "장 보관 복구 가능"은 자식 Scene
  상태를 보존한다는 **저장 성질**이지 공개 경로 약속이 아니며, unarchive 상태 전이는
  SoT v1.5 archive 정책(2026-06-28 확정 — "archived인 동안 차단"으로 한정해 unarchive
  여지를 보존, 공개 경로를 약속한 적 없음)이 범위 밖으로 둔 축이라 project·장 모두
  미제공이다(오너 결정 2026-08-29, 재검증 H1).
- 활동 로그에는 장 생성·개명·재정렬·보관·삭제 action을 분류표에 명시적으로 등재한다.
- 공개 API·OpenAPI·`schema.d.ts`·export manifest·WritingCandidate/receipt가 모두 영향권이다.
- 계층화 구현은 `모델/마이그레이션 → 읽기/API → UI/reorder → Writing intent → export → 삭제`
  순으로 작게 나누고 각 슬라이스를 독립 검증한다.

## 확정 구현 계약

### 데이터

- `Chapter = {id, project_id, title, archived, position}`.
- `Draft`는 Scene 정본이며 `{id, project_id, chapter_id, title, archived, position}`을 가진다.
  신규 runtime shape에서 `unit_kind`는 제거한다.
- Chapter position은 project 안 archived 포함 `1..C`, Scene position은 chapter 안 archived 포함
  `1..S`의 연속 순열이다.
- migration은 기존 `chapter` Draft 앞에 같은 제목의 Chapter를 만들고 그 Draft를 제목 `본문`인
  첫 Scene으로 바꾼다. 뒤따르는 `scene|other` Draft는 다음 `chapter` Draft 전까지 같은 Chapter에
  귀속한다. 선행 chapter 없는 묶음은 합성 Chapter `미분류`에 둔다. Draft와 하위 정본 ID·본문은
  byte-identical하게 보존한다.

### 공개 API

- `GET /projects/{pid}/chapters` → position 순 Chapter와 각 Chapter의 position 순 Scene을 반환한다.
- `POST /projects/{pid}/chapters` request `{title}` → 빈 Chapter를 마지막 position에 만든다.
- `PUT /projects/{pid}/chapter-order` request `{ordered_chapter_ids}` → archived 포함 완전 순열.
- `PUT /projects/{pid}/chapters/{cid}/scene-order` request `{ordered_draft_ids}` → 해당 Chapter의
  archived 포함 Scene 완전 순열.
- 기존 `POST /projects/{pid}/drafts`는 `{title, chapter_id}`를 받고 해당 Chapter 끝에 Scene을 만든다.
- 기존 `GET /projects/{pid}/drafts`는 호환용 flat Scene 목록을 Chapter position→Scene position
  순으로 반환하되 payload는 `chapter_id`를 싣고 `unit_kind`를 제거한다.
- 기존 project-wide `PUT /projects/{pid}/draft-order`는 제거한다.

### Writing·export·삭제

- `intent=start_next_unit` 리터럴은 호환을 위해 유지하되 의미는 **같은 Chapter의 다음 Scene**으로
  좁힌다. `next_unit={title,goal}`이며 `unit_kind`는 제거한다.
- 빈 Chapter의 첫 Scene은 일반 Scene 생성으로 명시적으로 만든다. AI가 새 Chapter를 추론하거나
  빈 Chapter를 자동 채우지 않는다.
- Markdown export는 `# {chapter.title}` 뒤 각 Scene을 `## {scene.title}`로, TXT는 장 제목 뒤
  장면 제목과 본문을 순서대로 출력한다. 기본 export는 archived Chapter 또는 Scene을 제외한다.
- `POST /projects/{pid}/chapters/{cid}/archive`가 Chapter만 archived 처리한다. 자식 Scene의
  `archived` 필드는 바꾸지 않는다.
- `POST /projects/{pid}/chapters/{cid}/purge`는 Chapter archived 선행을 요구하고 모든 자식 Scene의
  기존 draft purge graph와 Chapter를 함께 제거한다. 자식 중 active generation job이 있으면
  write 0·409다. UI는 exact Chapter title 확인 뒤 호출하고 파기 단계 503을 uncertain으로 잠근다.

## Deferred / out of scope

- 장보다 위의 부/권(volume/part) 계층
- Scene 아래의 beat/문단 트리
- 장 공동 편집·부분 순서 CRDT·fractional ordering
- Chapter synopsis 자동 생성과 canonical memory 승격
- 기존 분석 결과를 장 단위로 재집계하는 기능
