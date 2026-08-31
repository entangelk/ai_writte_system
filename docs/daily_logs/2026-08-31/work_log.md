# Work Log — 2026-08-31

## Session 1 — 장면 메모 Slice 0(저장·파기 수명)

### Goals

- [`scene-note-implementation-phases.md`](../../plans/scene-note-implementation-phases.md)
  **Slice 0**만 연다: `SceneNote` 모델·repository/service·in-memory/Mongo 구현과
  `scene_notes` 인덱스, Scene/Chapter/project 파기 연결. HTTP route·프론트·활동 기록은
  만들지 않는다.
- 페이즈 문서가 "기존 정본으로 유도되지 않으면 멈추고 브리프"라고 지정한 **본문 상한
  literal**을 오너 결정으로 확정하고 정본·모델·테스트에 같은 값으로 박는다.

### Completed work

- **`SceneNote` 모델**(`core_sot/models.py`): `{project_id, draft_id, body, updated_at}`.
  정체성은 `(project_id, draft_id)` — 원고 정본이 아니므로 `draft_versions`·snapshot·
  export·LLM 프롬프트에 섞이지 않는다(D2=A).
- **repository 계약**(`core_sot/repository.py`): `get_scene_note`/`put_scene_note` 2종 추가.
  파기 3종은 기존 메서드에 얹었다(계약 표면 증가 없음).
- **in-memory 어댑터**(`core_sot/service.py`): `scene_notes: dict[(project_id, draft_id)]`와
  `purge_project`/`purge_draft` 연결(`purge_chapter`는 `purge_draft` 경유 cascade).
- **service**(`core_sot/service.py`): `get_scene_note`/`put_scene_note`,
  `SceneNoteTooLong(CoreSotError)`, `SCENE_NOTE_MAX_CHARS = 12000`. 읽기는
  `_require_project`+`_require_draft`(archive 무관), 쓰기는 원고 저장과 **같은 축**
  `_require_active_project_and_draft`. `updated_at` 을 위해 `clock` 주입 추가
  (`writing/scratch.py` 관례 — 기본값 `datetime.now(UTC)`, 기존 호출부 무변).
- **Mongo 어댑터**(`core_sot/mongo_repository.py`): `scene_notes` 컬렉션, unique
  `uniq_scene_note(project_id, draft_id)`, upsert 기반 `put_scene_note`,
  `_purge_project`/`_purge_draft` 삭제 연결, BSON naive 날짜를 UTC 로 되돌리는 `_aware`
  (auth·activity·quota 어댑터와 같은 경계 정규화).
- **정본**: SoT **v1.8.11**(변경이력 행 + Phase 1 조항 + project 파기 그래프 **18→19컬렉션**),
  `README.md` ④칸 버전 동기화(`test_docs_indexes` 가드 요구), `test_purge_project_coverage.py`
  docstring 수치(core_sot 8→9 / 18→19 컬렉션), `routers/admin.py::execute_project_purge`
  docstring 수치. 결정 브리프·페이즈 문서에 확정값과 Slice 0 완료를 반영.
- **회귀**: `tests/test_scene_notes.py` 신규 15셀(in-memory) · `tests/test_core_sot_mongo.py`
  신규 6셀(`_MongoContractMixin` → fallback/transaction/WritingIntent 3 경로에서 실행) ·
  `tests/test_core_sot_mongo_indexes.py` 에 `uniq_scene_note` 요구 단정.

### Issues found

1. **파기 가드가 고아를 못 봤다 — 변이 M1이 아무 셀도 깨지 않았다.** 문제: in-memory
   `purge_draft`에서 메모 삭제 한 줄을 지워도 15셀이 전부 통과했다. 원인: 파기 셀이
   `service.get_scene_note`로 부재를 단정했는데, draft가 사라지면 `_require_draft`가 **메모
   행의 생사와 무관하게** NotFound를 던진다 — D5가 말하는 "조용한 고아"가 서비스 API 뒤에
   완전히 가려진다. 해결: Scene/Chapter/project 파기 셀이 `repo.scene_notes`를 직접
   단정하도록 고쳤다(커밋 `7a63d7a`). 결과: 같은 변이가 이제 2셀을 깨뜨린다(아래 표 M1).
   **교훈**: 부모가 함께 사라지는 자식 데이터의 파기 가드는 서비스 조회로 재면 안 된다.
   **패턴 sweep(§4)**: 같은 뿌리 — "`draft_id`로 묶인 자식의 부재를 부모를 요구하는 서비스
   메서드로 단정" — 를 기존 파기 회귀에서 훑었다. `test_draft_purge.py`는 `repo.version_count`
   와 `(project_id, idempotency_key)` 키인 `get_writing_accept_receipt`로, `test_core_sot.py`·
   `test_core_sot_mongo.py`의 파기 셀은 전부 `repo.*` 직접 단정으로 재고 있어 **재발 0건**.
   이 결함은 이번 신규 셀에만 있었다.
2. **`mongo_collections.md`에 최근 컬렉션이 빠져 있다**(선존 부채, 이번 변경 아님):
   `chapters`(v1.8.9)·`writing_drafts_scratch`도 등재돼 있지 않다. 이 문서는
   `ideation / architecture draft` 상태(문서 우선순위 5)이고 신규 컬렉션의 정본이 아니어서
   이번 slice에서 건드리지 않았다. 정리하려면 별도 작업이다.

### Decisions

- **본문 상한 = 12000자(오너, 2026-08-31).** 오너 논리: 메모는 AI에 들어가지 않으므로 실제
  경계는 Mongo 16MB이지만 그건 너무 크고, "길게 쓴 메모가 나중에 원고로 옮겨 간다"는 쓰임을
  보면 **장면 3개 분량**이 적절하다. 구현자 검산: 4000(원고 본문 상한)×3 = 12000이라 새 숫자를
  발명하지 않고 기존 상한의 배수로 정본에 쓸 수 있고, 장면당 1건이라 장면 200개 프로젝트도
  최악 2.4MB로 16MB 문서 한계와 두 자릿수 떨어져 있다. tradeoff: 4000의 원래 근거(이어쓰기
  예산)는 **옮겨오지 않는다** — 메모는 프롬프트에 실리지 않기 때문이며, 상한의 역할이
  "창 안전"에서 "저장 폭주 방지 + UI가 기댈 명확한 경계"로 바뀐다. 후속: Slice 1 목록 API는
  본문을 통째로 싣지 말고 **미리보기 절단**을 둔다(HANDOFF에 기록).
- **env override는 두지 않았다.** `DRAFT_RAW_TEXT_MAX_CHARS`처럼 env 노브를 만들 수도 있었으나
  오너가 값만 정했고 지금 조정 요구가 없다(§2 Simplicity First). 필요해지면 Slice 2에서
  `writing/scratch.py`의 관례(도메인 상수 + 조립부에서 env 읽기)로 추가한다.
- **저장 위치는 Core SOT 내부**(2026-08-29 인계 메모의 지시를 그대로 따름). 별도 서비스로
  빼면 Scene/Chapter 파기를 **라우터 두 곳**에서 각각 불러야 해 D5 부분 삭제 위험이 늘고,
  project 파기 경로도 두 벌이 된다. 현재 구조에서는 Scene/Chapter는 Core SOT 안에서,
  project는 공유 `execute_project_purge` → `core_sot.purge_project` **한 경로**로만 지운다.
- **archive 정책은 기존 정본에서 유도**(브리프가 "구현 시 확정"으로 남긴 항목): 읽기는 막지
  않고(SoT 전역 "archive는 read를 막지 않는다"), 쓰기는 원고 저장과 같은
  `_require_active_project_and_draft`. archive가 메모를 파기하지 않는다는 브리프 문언과
  일치한다.

### Mutation verification

구현 커밋(`cab1a7d`, 가드 보강 후 재실행분 포함) 뒤 적용 → 실행 → `git checkout -- <파일>`
복원 → `git status --short`로 해당 파일 0건 확인(각 1회).

| # | 방향 | 적용 diff | 파일 | 물린 셀 |
|---|---|---|---|---|
| M1 | under(파기 고아) | in-memory `purge_draft`의 `self.scene_notes.pop((project_id, draft_id), None)` 삭제 | `core_sot/service.py:309` | **최초에는 0셀(가드 결함 — Issues #1)**. 가드 보강 후 재실행: `SceneNotePurgeTest::test_scene_purge_removes_its_note_and_keeps_the_sibling_scene_note` · `::test_chapter_purge_cascades_to_child_scene_notes_only` (2 failed) |
| M2 | under(파기 고아) | in-memory `purge_project`의 `scene_notes` 필터 블록 삭제 | `core_sot/service.py:249-255` | `SceneNotePurgeTest::test_purge_leaves_no_residue_in_the_repository` (1 failed) |
| M3 | over(경계 과잉) | `if len(body) > SCENE_NOTE_MAX_CHARS` → `>=` | `core_sot/service.py:1348` | `SceneNoteBoundaryTest::test_body_at_the_limit_is_accepted` (1 failed) |
| M4 | under(상한 부재) | 상한 검사 블록 전체 삭제 | `core_sot/service.py:1348-1352` | `SceneNoteBoundaryTest::test_body_over_the_limit_is_rejected_and_leaves_the_current_note` (1 failed) |
| M5 | over(빈 본문=삭제) | `put_scene_note` 저장을 `if body:` 로 감쌈 | `core_sot/service.py:1360` | `SceneNoteStorageTest::test_empty_body_is_stored_as_an_empty_current_value_not_a_deletion` (1 failed) |
| M6 | under(archive 무시) | 쓰기의 `_require_active_project_and_draft` → `_require_project`+`_require_draft` | `core_sot/service.py:1353` | `SceneNoteArchiveTest::test_archived_scene_...` · `::test_archived_chapter_and_project_block_writes` (2 failed) |
| M7 | over(읽기 차단) | 읽기를 `_require_active_project_and_draft` 로 교체 | `core_sot/service.py:1340-1341` | `SceneNoteArchiveTest::test_archived_scene_keeps_the_note_readable_but_blocks_writes` (1 failed) |
| MM1 | under(Mongo 파기 고아) | `_purge_draft`의 `self._scene_notes.delete_many({project_id, draft_id})` 삭제 | `core_sot/mongo_repository.py` | `test_scene_purge_removes_the_note_and_keeps_the_sibling_note` · `test_chapter_purge_cascades_to_child_scene_notes_only` × Fallback/Transaction/WritingIntent 3경로 (**6 failed**) |
| MM2 | under(Mongo 파기 고아) | `_purge_project`의 `self._scene_notes.delete_many({project_id})` 삭제 | `core_sot/mongo_repository.py` | `test_project_purge_removes_scene_notes_and_keeps_other_project` × 3경로 (**3 failed**) |
| MM3 | under(저장소 경계 부재) | `ensure_indexes`의 `uniq_scene_note` 생성 블록 삭제 | `core_sot/mongo_repository.py` | `test_unique_index_blocks_a_second_note_row_for_one_scene` × 3경로 + `MongoIndexSetupTests::test_ensure_indexes_creates_required_absent_indexes` (**4 failed**) |

### Verification

- 집중(in-memory): `tests/test_scene_notes.py` **15 passed**.
- 집중(비-Mongo 이웃): `test_core_sot.py` · `test_core_sot_fixture.py` ·
  `test_core_sot_mongo_indexes.py` · `test_draft_purge.py` · `test_purge_project_coverage.py` ·
  `test_owner_project_purge.py` · `test_chapter_hierarchy.py` · `test_app_import_paths.py`
  합계 **105 passed / 17 subtests**.
- 문서 가드: `tests/test_docs_indexes.py` **13 passed / 272 subtests**(README ↔ SoT 버전 일치).
- Mongo 실측: `docker compose -f docker-compose.test.yml up -d`(rs-test, 27020) 기동 후
  `pytest tests/test_core_sot_mongo.py -k note` **15 passed**(신규 6셀 × 실행 경로).
- **전수**(test-mongo ON, rs-test 27020): **2610 passed / 1 skipped / 3024 subtests**
  (32분 55초). 신규 셀은 실측 **33개** — in-memory 15 + Mongo 6셀 × `_MongoContractMixin`
  3 서브클래스(Fallback·Transaction·WritingIntent) 18(`--collect-only`로 확인).
  **이 세션에서 변경 전 기준선을 재측하지는 않았다** — 따라서 위 수치는 변경 후 실측값이고
  "+N" 형태의 증분은 주장하지 않는다(08-29 기록의 2570/4/3022는 다른 세션의 측정치다).

## Session 2 — 독립 검증 지적 반영(보강)

검증 기록: [`2026-08-31/scene_note_slice_0.md`](../../verifications/2026-08-31/scene_note_slice_0.md)
(**합격**, 커밋 `6641462`). 차단 결함 0건, hardening 6건 중 코드/기록에 반영할 5건을 닫았다.

### Completed work

- **hardening #1 — 읽기-아카이브 축 파라미터화**: 직접 셀로 잠긴 것이 scene 보관뿐이었다.
  `SceneNoteArchiveTest::test_archived_project_and_chapter_do_not_block_reads` 신규(16셀).
  읽기 헬퍼를 `_require_active_project_and_draft`로 치환하는 회귀에서 재실패한다(변이 V6).
- **hardening #2 — 검사 순서 선언**: `put_scene_note`가 길이 검사를 아카이브 검사보다 먼저
  하는 것은 **선례에서 유도된다** — 원고 상한이 `SaveDraftRequest.enforce_raw_text_limit`
  (pydantic `field_validator`)이라 HTTP에서 422가 handler 진입 **전에** 나고 아카이브 409는
  그 뒤다. 따라서 Slice 2가 같은 관례를 쓰면 서비스 순서와 HTTP 순서가 일치한다. 결정
  브리프 Follow-up과 HANDOFF에 "순서는 유지, **상태 코드 literal(422 vs 413)만** 오너 확인"
  으로 남겼다. 오너 결정이 필요한 것은 순서가 아니라 코드 값이다.
- **hardening #3 — HANDOFF 용량 산정**: "장면 200개 = 최악 2.4MB"는 1바이트/자 가정이었다.
  240만 자 · 한국어 UTF-8 3바이트/자 → **≈7.2MB**(JSON 이스케이프 별도)로 정정하고 산정
  단위를 바이트로 명시. 절단 필요라는 결론은 그대로다.
- **hardening #4 — work_log 인용 오류**: `ae2fc9d`는 존재하지 않는 해시였다(가드 보강 커밋을
  기록할 때 확인 없이 적었다). 실제 커밋 `7a63d7a`로 정정.
- **hardening #5 — SoT 회귀 기술 과소**: v1.8.11 행의 "Mongo 6셀 × transaction/fallback 양
  경로" → **3 실행 경로**(Fallback·Transaction·WritingIntent = 18셀), in-memory 15→16셀.
- **hardening #6**(`mongo_collections.md` 미등재): 검증자도 "별도 작업" 판단에 동의 —
  이번에도 건드리지 않았다. Session 1 Issues #2에 부채로 남아 있다.

### Issues found

1. **존재하지 않는 커밋 해시를 기록에 남겼다**(hardening #4). 원인: 가드 보강 커밋을
   work_log에 적을 때 `git log`로 확인하지 않고 추정 해시를 썼다. 해결: 정정 + 앞으로 기록에
   해시를 넣을 때는 `git log --oneline`의 출력에서 복사한다. **이 결함은 검증자가 잡았다** —
   내 자체 검증에는 해시 실존 확인이 없었다.

### Mutation verification (Session 2)

| # | 방향 | 적용 diff | 파일 | 물린 셀 |
|---|---|---|---|---|
| V6 | over(읽기 차단) | `get_scene_note`의 `_require_project`+`_require_draft` → `_require_active_project_and_draft` | `core_sot/service.py:1390` | `SceneNoteArchiveTest::test_archived_project_and_chapter_do_not_block_reads` (**신규 셀 — 이 방향은 지금까지 이 셀만 잡는다**) · `::test_archived_scene_keeps_the_note_readable_but_blocks_writes` (2 failed) |

### Verification (Session 2)

- `tests/test_scene_notes.py` **16 passed**(신규 1셀 포함).
- `tests/test_scene_notes.py` + `tests/test_docs_indexes.py` **29 passed / 273 subtests**.
- 변이 V6 적용 → 2셀 재실패 → `git checkout` 복원 → `git status --short` 0건 확인.
- Session 1의 전수(2610/1/3024)는 재실행하지 않았다 — 이번 증분은 셀 1개 추가와 문서
  정정뿐이고, 검증자가 같은 트리에서 전수를 독립 재현했다(32:41).

## Session 3 — 장면 메모 Slice 1(읽기 API와 검색)

### Goals

- `GET /projects/{pid}/notes?query=` 와 `GET /projects/{pid}/drafts/{did}/note` 를 연다.
  쓰기 route·활동 기록은 만들지 않는다(Slice 2).
- 오너가 제기한 두 축(미리보기·페이지네이션)을 선례와 대조해 결정하고 정본에 남긴다.

### Completed work

- **Core SOT**: `SceneNoteListItem(note, scene, chapter)` 모델 — 필드를 평면화하지 않고 기존
  모델을 그대로 싣는다(두 번째 필드 목록은 `Draft`/`Chapter` 가 자라는 순간 어긋난다).
  repository `list_scene_notes(project_id)`(in-memory·Mongo), service
  `list_scene_notes(project_id, query=None)`.
- **순서**는 `list_drafts` 에서 가져온다 — 장 position→장면 position 이 이미 거기 있고,
  평면 legacy 의 `DraftOrderIntegrityError`(503) 얼굴도 함께 온다.
- **검색**은 서버 적용: 장면 제목 또는 본문 부분 일치, `casefold()` 로 대소문자 무관,
  **공백뿐인 query 는 필터 없음**.
- **`routers/notes.py` 신규**(`register_notes(app, *, core_sot)`): 협력자가 `core_sot`
  하나뿐인 것은 의도다 — 읽기 전용 slice 라 `activity` 를 받지 않는다.
  `build_note_preview(body, query)` + `SCENE_NOTE_PREVIEW_MAX_CHARS = 200`.
- **인가는 새 축이 없다**: `_REQUIRE_PROJECT_OWNER` 재사용. grant 읽기와 access-log 기록이
  기존 choke point(`api/dependencies.py::require_project_owner`) 한 곳에서 그대로 성립한다 —
  라우터에서 다시 기록하면 두 벌이 된다.
- **정본**: SoT **v1.8.12**(변경이력 + Phase 1 조항), README ④칸, 결정 브리프 Follow-up,
  페이즈 문서 Slice 1 완료. operation tier **70/96 → 72/98**(`test_auth_api.py`).
- **`schema.d.ts` 재생성**(`npm run gen:api`) — `SceneNotePayload`·
  `SceneNoteListItemPayload`·`SceneNoteListResponse` 및 2 operation 추가(+228줄).
- **회귀**: `tests/test_scene_notes.py` +8셀(목록·검색, 총 24) ·
  `tests/test_scene_notes_api.py` **신규 19셀**(응답 모양·미리보기 경계·401/403/404·
  grant 읽기 + access-log 2행).

### Issues found

1. **순서 가드가 순서를 안 잠갔다 — 변이 S1이 대상 셀을 못 잡았다.** 문제: 순서 계산을
   `service.list_drafts` → `repo.list_drafts` 로 강등해도 순서 셀이 통과했다. 원인:
   in-memory repo 도 `(chapter_id or "", position)` 으로 정렬하는데, 픽스처의 chapter id 가
   `chapter-1`·`chapter-2` 라 **사전순이 position 순과 우연히 일치**했다. 해결: 셀이
   `reorder_chapters` 로 장을 뒤집어 두 순서가 갈라지게 했다(커밋 `440c811`). 결과: 같은
   변이가 이제 순서 셀을 깨뜨린다. **Slice 0의 M1과 같은 계열** — "가드가 통과하는 이유가
   내가 생각한 이유인가"를 변이로 물어야 잡힌다. 자체 변이가 없었으면 둘 다 못 잡았다.

### Decisions

- **미리보기 = 검색 연계(오너 2026-08-31)**: query 가 본문에서 잡히면 매치 중심 스니펫,
  아니면 머리 200자. 길이 200은 활동 로그의 `ACTIVITY_VALUE_MAX_CHARS` 와 같은 값 —
  같은 성격(목록에 싣는 텍스트 조각)에 두 번째 숫자를 만들지 않는다. tradeoff: 스니펫
  계산이 라우터에 들어가지만, 절단·창 계산은 표현 계층 관심사라 도메인에 두지 않았다.
- **페이지네이션 없음(오너 2026-08-31)**: 활동 타임라인의 `limit=100` 선례는 **최신 순
  타임라인**이라 성립하는 상한이고, **검색 결과에 상한을 걸면 조용한 누락**("분명히 쓴
  메모가 안 나온다")이 된다. 미리보기 절단으로 크기 문제는 이미 사라진다(장면 200개
  ≈40KB). 나중에 `limit`/`offset` 추가는 가산적이라 계약을 깨지 않는다.
- **보관 장면 포함 + 보관 표시(오너 2026-08-31)**: 결정 브리프가 "구현 시 확정"으로 남긴
  항목. `list_drafts` 가 archived 를 걸러내지 않는 선례와 "archive 는 read 를 막지 않는다"
  전역 계약을 따른다. `scene_archived`·`chapter_archived` **두 축**을 싣는 이유는 장 보관이
  자식 Scene 의 `archived` 를 바꾸지 않기 때문이다 — 한 축만 실으면 화면이 읽기 전용을
  잘못 표시한다.
- **메모 없음 = `body=null`, 404 아님**: 404 로 답하면 장면 없음(404)과 뒤섞여 드로어가
  메모 없는 장면을 열 때마다 오류를 받는다. `body=""` 는 빈 메모 저장됨(저장 계약이 그
  둘을 구분하므로 읽기 표면도 구분한다).

### Mutation verification (Session 3)

구현 커밋(`c861bc0`, 순서 가드 보강 `440c811` 후 S1 재실행) 뒤 적용 → 실행 → `git checkout`
복원 → `git status --short` 0건 확인(각 1회). 실행 대상은
`tests/test_scene_notes.py` + `tests/test_scene_notes_api.py`.

| # | 방향 | 적용 diff | 파일 | 물린 셀 |
|---|---|---|---|---|
| S1 | under(순서 상실) | `list_scene_notes` 의 `self.list_drafts(...)` → `self._repo.list_drafts(...)` | `core_sot/service.py` | **최초 0셀(가드 결함 — Issues #1)**. 보강 후: `SceneNoteListTest::test_list_is_ordered_by_chapter_then_scene_position` · `::test_unknown_project_is_not_found` (2 failed) |
| S2 | under(서버측 필터 제거) | query 필터 블록 삭제 | `core_sot/service.py` | service 2셀 + API 2셀 (4 failed) |
| S3 | under(제목 검색 상실) | 필터에서 `scene.title` 항 삭제 | `core_sot/service.py` | `::test_query_matches_scene_title_and_body_case_insensitively` (1 failed) |
| S4 | over(공백 query 를 필터로) | `(query or "").strip().casefold()` → `.strip()` 제거 | `core_sot/service.py` | `::test_blank_query_lists_everything` subtest `query='   '` (1 failed) |
| S5 | over(보관 장면 제외) | 목록 루프에 `or scene.archived` 추가 | `core_sot/service.py` | service 1셀 + API 1셀 (2 failed) |
| S6 | under(미리보기 절단 제거) | `build_note_preview` 의 길이 분기를 `if True` 로 | `routers/notes.py` | API 1셀 + preview 3셀 (5 failed) |
| S7 | under(검색 연계 상실) | 매치 중심 분기를 `if False and query` 로 | `routers/notes.py` | `::test_preview_centers_on_the_match_...` · `::test_a_match_near_the_end_...` (2 failed) |
| S8 | over(메모 없음을 404 로) | 단건 GET 에 `note is None → 404` 추가 | `routers/notes.py` | `::test_a_scene_without_a_note_reads_as_null_body_not_404` (1 failed) |
| S9 | under(두 archive 축 혼동) | `chapter_archived` 를 `item.scene.archived` 로 | `routers/notes.py` | `::test_archived_scene_and_chapter_stay_listed_with_their_flags` (1 failed) |

### Verification (Session 3)

- 집중: `test_scene_notes.py`(24) + `test_scene_notes_api.py`(19) + `test_core_sot.py` +
  `test_activity_actions.py` + `test_billable_actions.py` + `test_app_import_paths.py` +
  `test_docs_indexes.py` + `test_application_api.py` = **248 passed / 1024 subtests**.
- 전수 route 가드: `test_auth_api.py` **132 passed / 977 subtests**(tier 행렬은 무수정
  통과했고 **카운트만** 72/98 로 갱신 — 새 경로가 이미 401/403 전수 가드 안에 있다는 뜻).
- **전수 backend**(test-mongo ON, rs-test 27020): **2638 passed / 1 skipped / 3065 subtests**
  (34분 29초). Session 1 기준선 2610/1/3024 대비 **+28 passed**(신규 27셀 = service 8 +
  HTTP 19, 그리고 tier 행렬이 새 경로 2개를 집어 subtests 가 +41).
- **전수 frontend**: `npx vitest run` **35 files / 385 passed**(10분 3초).
  ※ 처음 실행에서 `productName.test.ts` 1건이 실패했는데 **backend 전수와 동시에 돌린
  탓의 5초 타임아웃**이었다(단독 재실행 204ms 통과, 부하 없는 전수에서도 385/385).
  교훈: 이 머신에서 두 전수를 겹쳐 돌리지 않는다.

## Session 4 — Slice 1 독립 검증 조건 폐쇄

검증 기록: [`2026-08-31/scene_note_slice_1.md`](../../verifications/2026-08-31/scene_note_slice_1.md)
(**조건부 합격**, 커밋 `ab76b3e`). 차단 1건 + 보강 1건 + 기록 3건을 닫았다.

### Completed work

- **차단 폐쇄 — 평면 legacy 503 face 행동 셀**: SoT v1.8.12가 "평면 legacy의 503 얼굴도 함께
  온다"를 명문화했는데 그 분기가 **무셀**이었다(검증자 변이 W5: 라우터의
  `DraftOrderIntegrityError → 503` 핸들러를 통째로 지워도 60 passed / 0 failed). 그 상태의
  실제 동작은 **500**이고, 처방이 `migrate_chapter_scene_hierarchy.py`라는 사실이 응답에서
  사라진다. `SceneNoteLegacyMigrationFaceTest` 3셀 — 정합 평면 503 · 혼합(부분 migration)
  503 · **정상 계층 200**(과잉 교정 가드).
- **W2 보강 — strip 대칭**: 서비스 필터(`(query or "").strip()`)와 라우터 스니펫 탐색
  (`query.strip()`)이 둘 다 strip하는데 **한쪽만 없애는 비대칭을 아무 셀도 못 잡았다**.
  공백이 붙은 검색어에서 목록에는 뜨는데 미리보기는 머리 200자가 된다 — 검색 연계가 조용히
  꺼진 상태다. `test_a_padded_query_still_centers_the_snippet` 1셀.
- **기록 3건**: work_log의 미존재 해시 `6c05e73` → `440c811`(이번엔 `git log --format=%h %s`
  출력에서 **스크립트로 직접 읽어** 채웠다) · Session 3의 낡은 "Next steps"(완료된 Slice 1을
  다음 순서로 적고 있었다)를 Slice 2로 교체 · `HANDOFF.md:35`의 "현재 96 operation 합집합"
  → 98.

### Issues found

1. **같은 날 해시를 두 번 틀렸다.** Session 2에서 "해시는 `git log`에서 복사한다"고 적은
   직후 Session 3에서 재발했다(`ae2fc9d` → `6c05e73`). 원인은 같다 — 기록 시점에 확인하지
   않고 추정했다. **다짐으로는 못 고친다**는 것이 이번 재발의 결론이라, 이번 정정은 손으로
   적지 않고 subject로 커밋을 찾아 해시를 채우는 스크립트로 했다. 다음 세션도 같은 방식을
   쓴다(work log에 해시를 넣을 때 `git log --format=%h %s`의 출력에서 프로그램으로 뽑는다).
2. **"선언은 있고 셀은 없는" 분기**가 이번에도 검증자 변이로만 드러났다 — OpenAPI에 503이
   선언돼 있어 계약 문서만 보면 닫혀 보인다. Slice 0의 M1, Slice 1의 S1과 같은 계열이고,
   셋 다 **변이 없이는 green으로 보였다**.

### Mutation verification (Session 4)

구현 커밋(`7bd83fc`) 뒤 적용 → 실행 → `git checkout` 복원 → `git status --short` 0건 확인
(각 1회). 실행 대상은 `test_scene_notes.py` + `test_scene_notes_api.py` +
`test_chapter_hierarchy.py`.

| # | 방향 | 적용 diff | 파일 | 물린 셀 |
|---|---|---|---|---|
| W5 | under(503 face 상실) | `list_scene_notes` route의 `except DraftOrderIntegrityError → 503` 블록 삭제 | `routers/notes.py` | `SceneNoteLegacyMigrationFaceTest::test_flat_legacy_project_note_list_is_503_not_500` · `::test_mixed_hierarchy_state_note_list_is_503_not_500` (2 failed — **검증자가 0셀로 뚫었던 자리**) |
| W5b | over(정상까지 503) | route가 항상 `DraftOrderIntegrityError` 를 올리게 | `routers/notes.py` | `::test_a_migrated_project_is_not_swept_into_the_503` 포함 8 failed |
| W2 | under(스니펫 strip 비대칭) | `query.strip().casefold()` → `query.casefold()` | `routers/notes.py` | `NotePreviewTest::test_a_padded_query_still_centers_the_snippet` (1 failed) |
| W2b | under(필터 strip 제거, 반대쪽) | `(query or "").strip().casefold()` → strip 제거 | `core_sot/service.py` | `SceneNoteListTest::test_blank_query_lists_everything` subtest `query='   '` (1 failed) |

### Verification (Session 4)

- 집중: `test_scene_notes_api.py` **23 passed**(신규 4셀 포함, 총 19→23).
- broader suite: `test_scene_notes.py` + `test_scene_notes_api.py` +
  `test_chapter_hierarchy.py` + `test_application_api.py` + `test_auth_api.py` +
  `test_docs_indexes.py` + `test_activity_actions.py` = **344 passed / 1887 subtests**
  (2분 35초).
- 전수는 재실행하지 않았다 — 이번 증분은 **셀 4개 추가와 문서 정정뿐**이고 제품 코드는
  무변(변이 4종은 적용 후 전부 복원, `git status` 0건)이다. Session 3의 전수
  (backend 2638/1/3065 · frontend 385)는 검증자가 같은 트리에서 독립 재현했다.

### Next steps

- **Slice 2(명시적 저장 API와 활동 기록)** → 세션 5에서 구현 완료. 아래.

## Session 5 — 장면 메모 Slice 2(명시적 저장 API와 활동 기록)

### Goals

- `PUT /projects/{pid}/drafts/{did}/note` 하나를 연다. 소유자만 쓰고 grant는 403.
- 성공 뒤 `scene_note_saved` 한 행을 남긴다(분류표 전수 가드가 물리는 자리).
- 착수 전 남아 있던 오너 확인 2건(상한 초과의 상태 코드 · 같은 값 재저장의 활동 의미)을
  먼저 닫는다 — 페이즈 문서 §"공통 작업 규칙"이 요구하는 자리다.

### Completed work

- **`api/models.py::PutSceneNoteRequest`** — 필드는 `body` 하나. `enforce_body_limit`이
  `core_sot.service.SCENE_NOTE_MAX_CHARS`(12000)를 재는 pydantic `field_validator`라
  **검사가 handler 진입 전**이다. `idempotency_key`는 두지 않았다 — 값을 통째로 교체하는
  upsert라 재전송이 저장 결과를 바꾸지 않는다(바뀌는 것은 활동 행뿐이고 그것은 아래 창이
  접는다).
- **`routers/notes.py`** — PUT 하나 추가(`register_notes(app, *, core_sot, activity)`).
  응답 모델은 단건 GET과 **같은 `SceneNotePayload`**다. route는 두 GET **뒤**에 등재했다 —
  합집합 앱의 route 순서가 OpenAPI `paths` 순서이고 그것이 `schema.d.ts`의 입력이라, 앞에
  끼우면 기존 2 operation의 자리가 밀린다.
- **연타 창** `SCENE_NOTE_DOUBLE_SUBMIT_WINDOW = 5초` + `_is_double_submit(previous, saved)`.
  handler가 쓰기 전에 직전 값을 한 번 읽어 **본문이 같고 창 안**이면 활동 행만 생략한다.
  저장과 200 응답은 억제되지 않는다.
- **`activity/actions.py`** — `scene_note_saved`(PUT `/projects/{project_id}/drafts/
  {draft_id}/note`, target_type `scene_note`) 등재. logged **25→26**.
  `before`/`after`는 비운다(A3=B의 짧은 라벨 자리에 12000자 본문이 들어갈 수 없다).
- **프론트 라벨표** `activityActions.ts` — `scene_note_saved: "장면 메모 저장"` +
  `NON_LINKABLE_TARGET_TYPES.scene_note`(사유: 메모 전용 route가 Slice 3에서 생긴다).
  `test_activity_ui_labels.py`가 두 표를 전수 대조하므로 백엔드만 고치면 즉시 물린다.
- **인가에 새 축이 없다** — `_REQUIRE_PROJECT_OWNER` 그대로. `_GRANTED_METHODS`가
  GET/HEAD뿐이라 grant는 PUT에서 403이고, D3=A가 코드 없이 성립한다(변이 M8이 실증).
- **정본**: SoT **v1.8.13**(변경이력 + Phase 1 조항), README ④칸, 결정 브리프 D4·검사 순서
  항목, 페이즈 문서 Slice 2 완료, `docs/plans/README.md` 상태.
  operation tier **72/98 → 73/99**, `schema.d.ts` 재생성(+95줄, 순수 가산).
- **회귀**: `tests/test_scene_notes_api.py` **23 → 46셀**(+23).

### Decisions

- **상한 초과의 얼굴은 422(오너 확정 2026-08-31)**. 요청 모델 `field_validator`라 원고 본문
  상한(`SaveDraftRequest.enforce_raw_text_limit`)과 **같은 관례**이고, 검사가 handler 앞에
  서므로 독립 검증 hardening #2가 요구한 순서(보관된 장면 + 초과 본문 → `Archived`가 아니라
  길이 오류)가 **저절로** 성립한다. 413을 고르면 handler 안에서 잡아야 해 순서를 사람이
  지켜야 하고, `api/errors.py`가 "422는 모든 곳에서 의도적으로 선언 밖"으로 둔 관례와도
  갈라진다. tradeoff: 오류 본문 모양이 다른 4xx와 다르다(`{"detail": [...]}`) — 이미 원고
  저장이 같은 모양이라 프론트가 새로 배울 것은 없다.
- **같은 값 재저장은 행을 남기고, 연타는 접는다(오너 확정 2026-08-31)**. 오너 문언:
  *"남기되, 같은 값을 동시에 여러번 저장하는건 막는 로직이 필요하겠어. 저장버튼 여러번
  누르는거 말야."* 가르는 축이 **값이 아니라 시간**이라는 것이 요점이다 — 나중에 같은 본문을
  다시 저장하는 것은 두 번째 저장 행위지만, 응답이 오기 전의 재클릭은 한 번의 행위다.
  구현 자리로 셋(활동 행만 억제 · 429 차단 · 프론트 버튼 잠금)을 제시했고 오너가 **활동 행만
  억제**를 골랐다: PUT은 항상 200이고 계약이 안 바뀐다. `quota/lock.py`의 429 중복 잠금은
  과금되는 동기 AI 요청(23~91초)용이라 무료 저장에 걸면 저장마다 Mongo 잠금 쓰기가 붙는다.
- **연타 창 상수는 따로 둔다.** `quota/lock.py::DEFAULT_MINIMUM_WINDOW_SECONDS`와 값이
  5로 같지만 다른 상수다 — 그쪽은 과금 요청의 냉각 창(제품 정책)이고 여기는 무료 저장의
  타임라인 접기다. 합치면 quota 정책을 손볼 때 메모 타임라인이 조용히 따라 바뀐다
  (그 모듈 docstring이 "두 상수는 서로 다른 것이며 합치면 둘 다 틀린다"고 적은 것과 같은 형태).
- **`target_type`은 `scene_note`, `target_id`는 `draft_id`**. `draft`를 재사용하면 링크가
  당장 편집 화면으로 걸리지만, target_type의 의미가 "무엇을 **바꿨는가**의 종류"라 메모
  저장이 원고 변경으로 보인다. 비링크 등재의 사유에 **트리거를 함께** 적었다 —
  "Slice 3의 `/projects/:id/notes`가 생기면 그때 연다".

### Mutation verification (Session 5)

구현 커밋(`edec884`) 뒤 적용 → 실행 → **원본 복원 → `git status --short` 0건 확인**(각 1회,
스크립트가 `finally`에서 원문을 되쓰고 매 회 clean을 출력했다). 실행 대상은
`test_scene_notes_api.py` + `test_activity_actions.py` + `test_auth_api.py`.
읽기는 `FAILED|SUBFAILED` + 요약 count 줄로 했다(HANDOFF 함정: `grep FAILED`는 subtest
실패를 통째로 놓친다).

| # | 방향 | 적용 diff | 파일 | 물린 셀 |
|---|---|---|---|---|
| M1 | under(활동 기록 상실) | 기록 블록 전체를 `pass` 로 | `routers/notes.py` | 활동 7셀 + 전수 가드 2 SUBFAILED(`test_every_logged_route_actually_records`·`test_the_recorded_action_literal_matches_the_table`) = **9 failed** |
| M2 | under(연타 억제 상실) | `if not _is_double_submit(...)` → `if True` | `routers/notes.py` | `::test_a_double_submit_of_the_same_body_records_once` (1) |
| M3 | over(값 비교 상실 — 시간만 봄) | `_is_double_submit` 에서 `previous.body == saved.body` 항 삭제 | `routers/notes.py` | `::test_a_changed_body_inside_the_window_still_records` (1) |
| M4 | over(창 상실 — 값만 봄) | 창 비교 항 삭제(같은 값이면 영구 억제) | `routers/notes.py` | `::test_a_deliberate_re_save_of_the_same_body_records_again` (1) |
| M5 | off-by-one | 창 비교 `<` → `<=`(정확히 5초가 억제됨) | `routers/notes.py` | `::test_a_deliberate_re_save_of_the_same_body_records_again` (1) |
| M6 | under(상한 검증 무력화) | `enforce_body_limit` 의 `if len(...) >` → `if False` | `api/models.py` | 422 2셀 + `::test_a_rejected_save_records_nothing` = **3 failed** |
| M7 | under(쓰기 아카이브 경계 상실) | `put_scene_note` 의 `_require_active_project_and_draft` → `_require_draft` | `core_sot/service.py` | 409 3셀 + `::test_a_rejected_save_records_nothing`(SUBFAILED status=409) = **5 failed** |
| M8 | under(grant 쓰기 개방) | `_GRANTED_METHODS` 에 `"PUT"` 추가 | `api/dependencies.py` | `::test_a_live_grant_does_not_open_the_write` (1) |
| M9 | over(실패에도 기록) | `activity.record` 를 `try` **앞**으로 이동 | `routers/notes.py` | `::test_a_rejected_save_records_nothing` 포함 **6 failed** |

**M5가 따로 필요한 이유**: M4(창 항 삭제)와 물리는 셀이 같지만 방향이 다르다 — M4는 창을
없앤 것이고 M5는 경계를 한 칸 옮긴 것이다. 경계 셀이 정확히 5초를 쓰기 때문에 둘 다 문다.

### Verification (Session 5)

- 집중: `test_scene_notes_api.py` **46 passed / 9 subtests**(23 → 46, +23셀).
- 가드 4파일(`test_activity_actions`·`test_activity_ui_labels`·`test_auth_api`·
  `test_scene_notes_api`): **191 passed / 1116 subtests**. 착수 직전 같은 4파일을 `HEAD~1`
  워크트리에서 실측한 값이 **168 / 1098** — **셀 +23(전부 신규) · subtest +18**이고, 그 18은
  새 operation 하나가 tier·분류·라벨 전수 셀을 도는 **기계적 증가**다(전수 가드가 operation
  집합을 글롭으로 읽는 그 자리).
- **전수 backend**(test-mongo ON, rs-test 27020): **2664 passed / 1 failed / 1 skipped /
  3088 subtests**(29분 35초). 유일한 실패는 `test_docs_indexes.py::VerificationCountClaims
  Test::test_the_readme_names_the_current_contract_version` — SoT 헤더만 v1.8.13으로 올리고
  README ④칸을 안 고친 자리이며, **그 셀이 존재하는 이유 그대로 물었다**. 정정(`a0257d9`)
  뒤 `test_docs_indexes.py` 13 passed / 274 subtests 단독 green.
  **→ 다음 전수 기대값은 `2665 / 1 / 3088`**(정정은 문서 리터럴 한 줄이라 셀·subtest를 안
  건드린다). collect-only 실측 **2666**(= 2665 + skip 1)이고 착수 전은 **2643**이다.
- **전수 frontend는 돌리지 않았다** — 이번 증분에서 프론트 변경은 `activityActions.ts`의
  라벨 1행·비링크 1행과 생성물 `schema.d.ts`뿐이고, 그 두 표의 정합은
  `test_activity_ui_labels.py`(pytest)가 전수로 잠근다. **다음 사람이 프론트를 만질 때
  전수를 함께 잰다.**
- **주의(전수 실행 규칙)**: 이 머신에서 backend·frontend 전수를 겹쳐 돌리지 않는다
  (Session 3에서 `productName.test.ts`가 과부하 타임아웃으로 오탐).

### Next steps

- **독립 검증부터 이어간다** — 아래 HANDOFF "다음 순서" 참조. Slice 3(별도 메모 화면)은
  검증 뒤에 착수한다.
