# 장면 메모 기능 — 구현 페이즈

상태: `Active — Slice 0·1·2 완료(SoT v1.8.11·v1.8.12·v1.8.13, 2026-08-31) · Slice 3부터 진행`
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

## Slice 0 — 계약과 저장 수명 · **완료(2026-08-31, SoT v1.8.11)**

확정된 값: 본문 상한 **12000자**(`core_sot.service.SCENE_NOTE_MAX_CHARS`, 오너 2026-08-31).
저장 위치는 Core SOT 내부 `scene_notes`이며, Scene/Chapter 파기는 Core SOT 안에서,
project 파기는 공유 `execute_project_purge` → `core_sot.purge_project` 한 경로로만 지운다.
읽기는 archive를 막지 않고 쓰기는 `_require_active_project_and_draft`를 쓴다.

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

## Slice 1 — 읽기 API와 검색 · **완료(2026-08-31, SoT v1.8.12)**

오너 확정(2026-08-31): 미리보기는 **검색과 연계**(매치 중심 스니펫, 200자) ·
**페이지네이션 없음** · **보관 장면 포함 + 보관 표시**. 메모 없는 장면은 `body=null`.

**범위:** `GET /projects/{pid}/notes?query=`(전체 목록·제목/본문 부분 일치)와
`GET /projects/{pid}/drafts/{did}/note`를 추가한다. 목록은 Chapter position→Scene position 순이고
query는 서버에서 적용한다. 쓰기 route와 활동 기록은 아직 없다.

**인가:** 소유자와 유효한 access grant가 읽을 수 있다. `owner_id=None`, 타 프로젝트 Scene, grant
없음은 기존 project 경계 규칙을 그대로 따른다.

**검증:** OpenAPI/`schema.d.ts`, 401·403·404, grant read 성공과 목록 검색의 제목·본문·빈 결과를
확인한다. grant read가 access-log 한 행을 남기는 기존 choke point도 유지한다.

**완료 후 인계:** 프론트는 이 두 GET만으로 화면·드로어를 만들 수 있지만 저장 UI는 아직 내지 않는다.

## Slice 2 — 명시적 저장 API와 활동 기록 · **완료(2026-08-31, SoT v1.8.13)**

오너 확정(2026-08-31): 본문 상한 초과의 얼굴은 **422**(요청 모델 `field_validator`, 원고 본문
상한과 같은 관례) · 같은 값을 다시 저장해도 활동 행을 **남기되**, 저장 버튼 연타(직전 저장과
본문이 같고 **5초** 안)는 **활동 행만** 접는다.

**범위:** `PUT /projects/{pid}/drafts/{did}/note`를 추가했다. 소유자만 쓰고 grant는 403이다
(`_GRANTED_METHODS`가 GET/HEAD뿐이라 자동으로 성립한다). 성공 뒤 handler에서
`scene_note_saved`를 한 행 기록한다 — `target_type=scene_note` · `target_id=draft_id` ·
`before`/`after`는 비운다(A3=B의 짧은 라벨 자리에 12000자 본문이 들어갈 수 없다).

**검증:** owner 저장·갱신·빈 본문, grant write 403, 401, archived 3축 409, 타 프로젝트/없는
장면 404, 상한 경계 200/422, **상한 검사가 아카이브 검사보다 먼저**, 실패 셋(404·409·422)에
활동 행 0, 동일값 재저장 2행, 연타 1행, 창 안 값 변경 2행, 창은 장면별, 억제돼도 저장은 됨.
분류표 logged 26 · tier 행렬 73/99 · `schema.d.ts` 재생성.

**완료 후 인계:** API가 완결됐다. 프론트 작업은 백엔드 계약을 바꾸지 않는다. 화면은
저장 요청 중 버튼을 비활성화한다 — 연타 창은 활동 로그만 접고 요청 자체는 막지 않는다.

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
- Slice 0의 본문 상한과 Slice 2의 같은 값 재저장 활동 의미는 **오너 확인으로 닫혔다**
  (2026-08-31). 남은 Slice에서 같은 종류의 미확정이 나오면 구현을 멈추고 작은 오너 결정
  브리프를 추가한다.

## Deferred

Chapter/프로젝트 메모, 메모 버전·자동 저장, 태그/검색 색인, export·LLM 주입, 협업/공개 공유는
이 페이즈 밖이다. 새 요구가 이 중 하나를 열면 Slice 4에 얹지 말고 별도 브리프와 Slice를 만든다.
