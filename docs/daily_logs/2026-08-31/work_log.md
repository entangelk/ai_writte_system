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
   단정하도록 고쳤다(커밋 `ae2fc9d` 계열). 결과: 같은 변이가 이제 2셀을 깨뜨린다(아래 표 M1).
   **교훈**: 부모가 함께 사라지는 자식 데이터의 파기 가드는 서비스 조회로 재면 안 된다.
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
- 전수: 아래 "전수 회귀" 절.

### Next steps

- **Slice 1(읽기 API·검색)**: `GET /projects/{pid}/notes?query=` + `GET
  /projects/{pid}/drafts/{did}/note`. Core SOT public 메서드만 쓰고 컬렉션을 직접 읽지 않는다.
  목록은 Chapter position→Scene position 순, query는 서버 적용, **본문 미리보기 절단** 필요.
- Slice 2 착수 전에 페이즈 문서의 남은 확정 항목(같은 값 재저장이 활동 행을 남기는가)을 정본
  문언과 맞춘다.
