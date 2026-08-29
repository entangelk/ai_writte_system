# 장면 메모 기능 — 구현 페이즈

상태: `Active — Slice 0부터 순차 진행`
작성: 2026-08-29
결정 정본: [`scene-note-decisions.md`](scene-note-decisions.md) D1=C+A · D2=A · D3=A · D4=A

## 목적과 완료 기준

프로젝트의 모든 Scene 메모를 별도 화면과 편집기 드로어에서 같은 검색 결과로 확인하고,
소유자는 명시적으로 저장하며 유효한 관리자 grant는 읽기만 할 수 있게 한다. 메모는 원고 본문,
버전, export, LLM 프롬프트에 섞이지 않고 Scene·project purge와 함께 사라져야 한다.

완료는 다음 네 가지가 동시에 참일 때다.

1. `/projects/:id/notes`와 편집기 드로어가 같은 검색 결과를 읽는다.
2. 소유자만 PUT하며 grant는 GET만 가능하고, 모든 경계가 401/403으로 잠긴다.
3. Scene purge·Chapter cascade purge·project purge에 메모 고아가 없다.
4. `scene_note_saved`는 성공한 명시적 저장에만 활동 로그 한 행을 남긴다.

## Slice 0 — 계약과 저장 수명

**범위:** `SceneNote` 모델·repository/service·in-memory/Mongo 구현과 `scene_notes` 인덱스,
Scene/Chapter/project purge 연결만 만든다. HTTP·프론트·활동 기록은 만들지 않는다.

**계약:** `{project_id, draft_id, body, updated_at}` 한 행이며 `(project_id, draft_id)` unique다.
빈 본문은 행 삭제가 아니라 빈 현재값으로 저장한다. `draft_id`가 다른 프로젝트에 속하면 읽기·쓰기는
NotFound다. 본문 상한 literal은 이 slice에서 정본/모델/테스트에 함께 정한다.

**검증:** in-memory와 Mongo에서 upsert·프로젝트 격리·unique·Scene purge·Chapter cascade·project
purge를 양방향으로 검증한다. 파기 그래프에 새 서비스를 넣을 때 `execute_project_purge`의 공유 경로를
쓴다.

**완료 후 인계:** 다음 작업자는 repository/service의 public 메서드만 사용하며 Mongo 컬렉션을
직접 읽지 않는다.

## Slice 1 — 읽기 API와 검색

**범위:** `GET /projects/{pid}/notes?query=`(전체 목록·제목/본문 부분 일치)와
`GET /projects/{pid}/drafts/{did}/note`를 추가한다. 목록은 Chapter position→Scene position 순이고
query는 서버에서 적용한다. 쓰기 route와 활동 기록은 아직 없다.

**인가:** 소유자와 유효한 access grant가 읽을 수 있다. `owner_id=None`, 타 프로젝트 Scene, grant
없음은 기존 project 경계 규칙을 그대로 따른다.

**검증:** OpenAPI/`schema.d.ts`, 401·403·404, grant read 성공과 목록 검색의 제목·본문·빈 결과를
확인한다. grant read가 access-log 한 행을 남기는 기존 choke point도 유지한다.

**완료 후 인계:** 프론트는 이 두 GET만으로 화면·드로어를 만들 수 있지만 저장 UI는 아직 내지 않는다.

## Slice 2 — 명시적 저장 API와 활동 기록

**범위:** `PUT /projects/{pid}/drafts/{did}/note`를 추가한다. 소유자만 쓰고 grant는 403이다.
성공 뒤 handler에서 `scene_note_saved`를 한 행 기록한다.

**검증:** owner 저장·갱신, grant write 거부, 실패/404에는 활동 행 없음, activity 분류표·operation
전수 가드·OpenAPI 선언을 잠근다. 같은 값을 다시 저장할 때도 D4의 명시적 저장으로 한 행을 남길지
확정 문언과 테스트를 맞춘다.

**완료 후 인계:** API가 완결된다. 프론트 작업은 백엔드 계약을 바꾸지 않는다.

## Slice 3 — 별도 메모 화면

**범위:** `/projects/:id/notes` route와 `SceneNotesPage`를 추가한다. 전체 목록·검색 입력·Scene 제목/
Chapter 제목·본문 미리보기·해당 Scene 편집기 이동만 제공한다. 저장 편집 UI는 Slice 4와 함께 둔다.

**검증:** 검색 query 전달, 빈 결과, 보관/404/403 오류 표현, 편집기 링크, route가 AuthGate 안에 있는지를
프론트 회귀로 검증한다.

**완료 후 인계:** 화면의 목록 컴포넌트는 Slice 4 드로어가 재사용하되, route를 다시 만들지 않는다.

## Slice 4 — 편집기 드로어 통합과 저장 UI

**범위:** 기존 우측 도구 독/드로어에 `메모` 탭을 추가하고, 전체 메모 검색·선택·현재 Scene 메모의
textarea와 저장 버튼을 제공한다. 별도 화면도 같은 목록/검색 컴포넌트를 쓰며, 소유자가 아니면
읽기 전용으로 표시한다.

**검증:** 드로어와 페이지의 검색·선택이 같은 API 계약을 쓰는지, 현재 Scene 전환, 저장 성공/실패,
grant 읽기 전용, drawer close 뒤 선택 상태를 확인한다. 기존 writing/analysis/review 탭을 과도하게
바꾸지 않는 회귀도 추가한다.

## 공통 작업 규칙

- 각 Slice는 **테스트 먼저 → 구현 → focused + relevant broader suite → checkpoint commit → mutation
  → 복원** 순서다. 다음 Slice로 넘어가기 전 work log/HANDOFF의 현재 상태를 갱신한다.
- 계약을 추가하는 Slice 0~2는 `docs/system-contract-sot.md`, OpenAPI 생성물, 활동 분류표를 해당
  변경과 같은 커밋 계열에서 갱신한다. UI Slice 3~4는 API 계약을 바꾸지 않는다.
- Slice 0의 본문 상한 또는 Slice 2의 같은 값 재저장 활동 의미가 기존 정본으로 유도되지 않으면,
  구현을 멈추고 작은 오너 결정 브리프를 추가한다.

## Deferred

Chapter/프로젝트 메모, 메모 버전·자동 저장, 태그/검색 색인, export·LLM 주입, 협업/공개 공유는
이 페이즈 밖이다. 새 요구가 이 중 하나를 열면 Slice 4에 얹지 말고 별도 브리프와 Slice를 만든다.
