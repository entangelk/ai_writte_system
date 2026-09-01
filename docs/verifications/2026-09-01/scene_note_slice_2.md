# 장면 메모 Slice 2(명시적 저장 API와 활동 기록) 독립 검증

## Subject metadata

- 날짜: 2026-09-01
- 요청자: 오너("이전 작업자가 진행했던 작업에 대해 검증하고 의심하고 또 의심해줄래" — HANDOFF "다음 작업은 Slice 2 독립 검증")
- 검증자: Claude Code 세션(구현자와 다른 세션 — 구현은 Claude Opus 5 커밋 `edec884`·`a0257d9`)
- 대상: 장면 메모 Slice 2 — `PUT /projects/{pid}/drafts/{did}/note`(저장 API)·`scene_note_saved` 활동 기록·연타 창·분류표 logged 26·tier 73/99·`schema.d.ts` 재생성·프론트 라벨표. Slice 3~4(화면)는 범위 밖
- 정본: `docs/system-contract-sot.md` **v1.8.13**(변경이력 행 + Phase 1 "장면 메모 저장" 조항), `docs/plans/scene-note-decisions.md`(D4 추가 확정·검사 순서 항목), `docs/plans/scene-note-implementation-phases.md` §Slice 2(완료 기준 16항)
- 검증 소스: 커밋 `edec884`(본체)·`a0257d9`(README 버전 핀 정정)·`46aadb6`(기록), HEAD `46aadb6`, 트리 clean(변이 전·후 매번 `git status --short` 확인)
- 환경: **베타**(WSL2, `nvidia-smi` GTX 1060 3GB), 저장소 루트에서 호스트 `python3 -m pytest`(pytest 9.0.2, mypy 설치됨), test-mongo = `docker compose -f docker-compose.test.yml`(rs-test, `127.0.0.1:27020`, 실행 직전 `healthy` 실측). `.env` 무관(URI 기본값 27020). frontend 전수는 핸드오프 지시대로 **돌리지 않았다**(프론트 변경은 라벨표 2행 + 생성물뿐)

## Scope

1. ★정본 계약 대비 구현(경계 행렬: 발생해야 할 분기·발생하지 말아야 할 분기·리터럴 전량 — SoT v1.8.13 행·Phase 1 조항·페이즈 문서 §Slice 2 검증 16항·결정 브리프 D4 추가 확정에서 추출)
2. 회귀 셀의 실채움(`tests/test_scene_notes_api.py` 46셀 전수 — test code is part of the audit subject)
3. 구현자 변이표(M1~M9) 중 핸드오프 지정 4종(M3·M4·M8·M9) + M5 재실행과 **검증자 독자 변이 5종**(구현자가 안 덮은 방향)
4. 표면 동기화: OpenAPI 선언 얼굴(`_owned(_ERRORS_404_409)`)·`schema.d.ts` 재생성·분류표 logged 26·tier 73/99·프론트 라벨표 2행
5. 전수 회귀(test-mongo ON) 수치 재현 — 기대값 `2665 / 1 / 3088`

## Methodology

- 경계 행렬은 SoT v1.8.13 조항 문언에서 먼저 세운 뒤 코드를 읽어 대응시켰다(계약→코드, 코드→계약 아님).
- 변이 프로토콜: 사전 `git status --short` empty 확인 → 변이 적용(문자 그대로의 diff — 아래 표) → 집중 셀 실행(**요약 count 줄 + `FAILED|SUBFAILED`**, `grep FAILED` 아님) → `git checkout -- <path>` 복원 → `git status --short` 재확인. 매번 실시, 13회 전부 clean 복원 확인(첫 변이 후부터는 검증자 자신의 미커밋 기록 디렉터리 `docs/verifications/2026-09-01/`만 untracked로 존재 — 변이 대상 파일은 전부 복원됨).
- 전수: `python3 -m pytest -q`(test-mongo healthy 확인 후 기동). collect-only로 수집 수도 직접 재 measurements.
- 셀 수 실측: `git show edec884~1:tests/test_scene_notes_api.py | grep -c "def test_"` = 23, HEAD = 46.

## Findings

### 1. 경계 행렬 — 계약 조항 ↔ 셀 대응

페이즈 문서 §Slice 2 "검증" 16항 + SoT v1.8.13 행의 문언을 전량 전개한 대응표. **빈 칸 없음**(1건의 리터럴 무핀은 §Issues B1).

| 계약 조항 | 구현 | 잠금 셀 | 변이 증명 |
|---|---|---|---|
| `PUT …/note` 소유자 저장 200, 응답 = 단건 GET 과 같은 `SceneNotePayload` | `routers/notes.py:170-176`(`response_model=SceneNotePayload` 재사용) | `test_a_saved_note_comes_back_and_reads_back_the_same` | — (응답 모델 공유는 선언 동일성) |
| 요청은 `{body}` 뿐, `idempotency_key` 없음 | `api/models.py::PutSceneNoteRequest`(필드 1개) | `schema.d.ts` `PutSceneNoteRequest.body` 단일 필드 + 모델 docstring | — |
| D4=A 값 통째 교체·버전 없음 | `put_scene_note` upsert(`service.py:1405-1424`) | `test_a_second_save_replaces_the_value_without_leaving_a_version` | Slice 0 V2(선례) |
| 빈 본문 = 빈 현재값 | 빈 본문 특례 없음 | `test_an_empty_body_saves_an_empty_note_rather_than_deleting_the_row` | Slice 0 M5 |
| 상한 경계: 정확히 12000 → 200 | 모델 `field_validator` `enforce_body_limit` | `test_a_body_exactly_at_the_limit_is_accepted` | **V-C(모델 `>`→`>=`): 1셀** |
| 상한 초과 → **422**(handler 앞), 저장 안 됨 | pydantic 검증이 handler 진입 전 | `test_a_body_over_the_limit_is_422_and_stores_nothing` | 구현자 M6 |
| **길이 검사가 아카이브 검사보다 먼저**(보관+초과 → 409 아님) | 모델 검증이 dependency·handler 전 | `test_the_length_check_runs_before_the_archive_check` | V-C가 같은 방향으로 문듦 |
| archived project/chapter/scene → 409(3축) | `put_scene_note` → `_require_active_project_and_draft` | 409 3셀 | 구현자 M7(서비스측) |
| 타 프로젝트 장면·없는 장면·없는 프로젝트 → 404 | `get_scene_note`(핸들러 선행 읽기)·`put_scene_note`의 `_require_*` | 404 3셀 | — |
| 실패 셋(404·409·422)에 활동 행 0 | 기록은 성공 뒤에만 | `test_a_rejected_save_records_nothing`(subTest 3 + rows==[]) | **M9-삽입·M9-이동 재실행** |
| 성공 시 `scene_note_saved` 정확히 1행, target_type `scene_note`·target_id=draft_id | `routers/notes.py:196-203` | `test_a_successful_save_records_exactly_one_row` | M9-삽입 |
| 행위자 = 세션 사용자 | `actor_user_id=current.id` | `test_the_row_names_the_actor_not_the_owner_field` | **V-E 참조 — 이 셀의 주장 범위는 §Issues H2** |
| `before`/`after` 비움(A3=B 라벨 자리) | record 호출이 두 파라미터 생략(기본 None) | `test_the_note_body_never_rides_into_the_activity_row` | — |
| 동일값 재저장(창 밖) → 2행 | 창 비교 `<` | `test_a_deliberate_re_save_of_the_same_body_records_again` | **M4·M5 재실행: 1셀씩** |
| 연타(같은 값+창 안) → 활동 행만 1행 | `_is_double_submit` 두 항(값·시간) | `test_a_double_submit_of_the_same_body_records_once` | **M3 재실행**(값 항)·**V-B**(읽기 순서): 7셀 |
| 창 안 값 변경 → 2행 | 값 항 | `test_a_changed_body_inside_the_window_still_records` | M3 |
| 창은 장면별 | 상태가 `(project_id, draft_id)` 행 자체 | `test_the_window_is_measured_per_scene` | — |
| 억제돼도 저장·200은 그대로 | 억제는 `if not …record` 분기뿐 | `test_the_suppressed_save_still_persists_the_value`(200 + `updated_at` 갱신 단정) | — |
| 세션 없음 → 401 | `_REQUIRE_PROJECT_OWNER`(+handler `require_authenticated_user`) | `test_a_sessionless_write_is_401` | — |
| **grant 는 PUT 에서 403**(D3=A, GET/HEAD 만 grant) | `_GRANTED_METHODS`가 `api/dependencies.py:73` 전역 | `test_a_live_grant_does_not_open_the_write`(GET 200·PUT 403·미저장 3단정) | **M8 재실행: 1셀** + V-D |
| 소유권 dependency 선언·403 선언·tier 일치 | `dependencies=_REQUIRE_PROJECT_OWNER` + `_owned(_ERRORS_404_409)` | `test_auth_api.py` tier 행렬(재유도) | **V-D: 2파일 6 fail** |
| 얼굴 401·403·404·409·503 선언(422는 관례상 선언 밖) | `_owned(_ERRORS_404_409)` = 401·403·404·409·503(`errors.py:225-227`) | 선언 전수 가드 + `schema.d.ts` 재생성물 | V-D에서 stack 일치 셀이 물림 |
| 503 저장소 얼굴 | 앱 전역 핸들러(`main.py:1702-1705`, v1.7.38)가 route 탈출 예외를 503으로 | 앱 전역 계약(v1.7.38 슬라이스 가드) — 이 경로 고유 셀 불요 | — |
| 분류표 logged 25→26 | `activity/actions.py` `scene_note_saved` 등재 | `test_activity_actions.py` 개수핀 3단정 + 전수 가드 | M1(구현자)이 2 SUBFAILED |
| 라벨표 26행·비링크 사유(트리거 포함) | `activityActions.ts` 라벨 1행 + `NON_LINKABLE_TARGET_TYPES.scene_note`(Slice 3 트리거 명시) | `test_activity_ui_labels.py` 전수 대조 | — |
| tier 72/98 → 73/99 | `test_auth_api.py:1886-1894` 개수핀 | 동일 | V-D(73→72 로 떨어짐) |
| 연타 창은 quota 냉각창과 **다른 상수** | `routers/notes.py:64`(값만 같은 별도 상수, docstring에 사유) | — (문서화된 의도) | — |
| route 는 두 GET **뒤** 등재(OpenAPI 순서) | `register_notes` 내 세 번째 등재(`notes.py:167-175`) | `schema.d.ts` paths 순서(재생성물) | — |

### 2. 구현·선언·생성물 대조

- `routers/notes.py` PUT handler: 직전 값 읽기(`get_scene_note` — 쓰기 경계 검사 안 함)→`put_scene_note`→성공 후 조건부 기록. NotFound→404·Archived→409 매핑. 서비스의 검사 순서(길이→아카이브, `service.py:1411-1416`)와 HTTP 순서(모델 검증→409)가 같은 방향인 것을 코드와 셀 양쪽에서 확인.
- Mongo 경계: `get_scene_note`가 `_to_scene_note`에서 `_aware(doc["updated_at"])`로 되돌린다(`mongo_repository.py:895-900`) — 연타 창의 `saved.updated_at - previous.updated_at` 뺄셈이 naive/aware 혼합으로 죽지 않는 구조. 왕복 자체는 Slice 0 Mongo 계약 셀(6셀 × 3경로)이 잠근다.
- `schema.d.ts` +95/-1(순수 가산 — -1은 paths 블록 끝줄 재배치): `put` operation·`PutSceneNoteRequest`(필드 `body` 단일)·200/401/403/404/409/503 선언 확인. `idempotency_key` 없음.
- 집중 재현: 가드 4파일(`test_scene_notes_api`·`test_activity_actions`·`test_activity_ui_labels`·`test_auth_api`) = **191 passed / 1116 subtests**(구현자 주장과 동일). collect-only 전수 = **2666**(주장 2665+skip 1과 동일).

### 3. 변이 검증 (13종 — 구현자 M1·M3·M4·M5·M7·M8·M9 재실행 + 독자 5종 + M9 두 구성)

구현자 표의 9종 중 7종을 재실행해 **전부 기록된 셀 수와 일치**함을 확인했다(아래 표). M2(`if True`, 연타 무조건 기록)·M6(모델 검증 무력화)는 재실행하지 않았으나 같은 방향을 독자 변이 V-B(접기 구조)·V-C(모델 경계)가 덮는다.

| # | 방향 | 적용 diff(문자 그대로) | 파일 | 물린 셀(실측) |
|---|---|---|---|---|
| M1(재) | under(기록 상실) | `if not _is_double_submit(...)` 블록 본체를 `pass`로 | `routers/notes.py:196-203` | 활동 7셀 + 전수 가드 2 SUBFAILED(`test_every_logged_route_actually_records`·`test_the_recorded_action_literal_matches_the_table`) = **9 failed**(구현자 표와 동일) |
| M7(재) | under(쓰기 아카이브 경계 상실) | `put_scene_note`의 `self._require_active_project_and_draft(project_id, draft_id)` → `self._require_project(project_id)`+`self._require_draft(project_id, draft_id)` | `core_sot/service.py:1416` | 409 3셀 + `test_a_rejected_save_records_nothing`(FAILED+SUBFAILED status=409) = **5 failed**(동일) |
| **B1-A** | 리터럴 드리프트 | `SCENE_NOTE_DOUBLE_SUBMIT_WINDOW = timedelta(seconds=5)` → `timedelta(seconds=6)` | `routers/notes.py:64` | **46 passed — 아무 셀도 안 물음(§Issues B1)** |
| V-B | under(읽기 순서) | `previous = core_sot.get_scene_note(...)` 블록을 `put_scene_note` 호출 **뒤로** 이동 | `routers/notes.py:183-191` | 활동 7셀(`test_a_successful_save…`·`test_the_row_names…`·`test_the_note_body…`·`test_a_double_submit…`·`test_a_changed_body…`·`test_a_deliberate…`·`test_the_window_is_measured…`) = **7 failed** |
| V-C | over(모델 경계) | `if len(value) > SCENE_NOTE_MAX_CHARS:` → `>=` | `api/models.py` | `test_a_body_exactly_at_the_limit_is_accepted` = **1 failed** |
| V-D | under(소유권 해제) | PUT decorator에서 `dependencies=_REQUIRE_PROJECT_OWNER,` 줄 삭제 | `routers/notes.py:174` | scene API: `test_a_live_grant_does_not_open_the_write` = 1 + `test_auth_api`: `test_every_operation_lands_in_exactly_one_named_tier`(FAILED) + foreign-project·ownership-match·protected-exemption·consistent-stack(SUBFAILED) = **합 6 failed** |
| **B1-E** | under(행위자 출처) | `actor_user_id=current.id` → `actor_user_id=(core_sot.get_project(project_id=project_id).owner_id or current.id)` | `routers/notes.py:200` | **46 passed — 안 물음(§Issues H2; 이 경로는 구조적으로 소유자==행위자)** |
| M3(재) | over(값 항 상실) | `and previous.body == saved.body` 줄 삭제 | `routers/notes.py:72` | `test_a_changed_body_inside_the_window_still_records` = **1 failed**(구현자 표와 동일) |
| M4(재) | under(창 항 상실) | `and saved.updated_at - previous.updated_at < SCENE_NOTE_DOUBLE_SUBMIT_WINDOW` 줄 삭제 | `routers/notes.py:73` | `test_a_deliberate_re_save_of_the_same_body_records_again` = **1 failed**(동일) |
| M5(재) | off-by-one | `< SCENE_NOTE_DOUBLE_SUBMIT_WINDOW` → `<=` | `routers/notes.py:73` | `test_a_deliberate_re_save_of_the_same_body_records_again` = **1 failed**(동일 — 경계 셀이 정확히 창값을 씀) |
| M8(재) | under(grant 쓰기 개방) | `_GRANTED_METHODS = frozenset({"GET", "HEAD"})` → `frozenset({"GET", "HEAD", "PUT"})` | `api/dependencies.py:73` | `test_a_live_grant_does_not_open_the_write` = **1 failed**(동일 — 403이 dependency에서 옴을 실증) |
| M9-삽입(재) | under(실패에도 기록) | `try:` 앞에 동일 `activity.record(...)` 호출 **추가**(가드 블록 유지) | `routers/notes.py:183` | `test_a_rejected_save_records_nothing` 포함 **6 failed** — **구현자 표의 "6 failed"는 이 구성**(work_log는 "이동"으로 표기했으나 실제로는 삽입) |
| M9-이동 | under(기록 전진) | `activity.record(...)` 블록(가드 포함)을 `try:` 앞으로 **이동**(원자리 삭제) | `routers/notes.py:183-203` | `test_a_rejected_save_records_nothing`·`test_a_double_submit…` = **2 failed** — "이동"으로 읽은 구성에서도 계약-핵심 셀이 문다 |

두 M9 구성을 모두 잰 이유: 검증 가이드의 실측 교훈(2026-08-09)대로 "이동"과 "삽입"은 다른 변이여서 다른 셀을 물는다. 구현자 기록의 6 failed는 삽입 구성으로 재현됐고, 이동 구성(2 failed)도 계약 핵심(실패 무기록)을 잠근다 — 어느 독법으로도 가드는 유효.

### 4. 회귀 셀 실채움

- 셀 수 실측: `edec884~1` = **23**, HEAD = **46**(+23). **work_log 세션 5의 "23 → 46셀(+23)"이 맞고, SoT v1.8.13 행·커밋 메시지의 "27→46"은 오기다**(§Issues H1).
- 23신규 셀 전수 낭독: 전 셀이 공개 표면(상태코드·응답 json·활동 행)을 단정하고, 내부 헬퍼를 직접 재는 것은 미리보기 헬퍼뿐(선례 유지). 시계 주입(`clock=lambda: self.now`)으로 연타 창이 결정적이다.
- `SceneNoteWriteActivityTest`의 3연속 PUT 연타 셀·per-scene 셀·억제-저장 셀은 각각 다른 실패 모드를 격리한다(한 broad 셀이 전부 흡수하는 모양 아님 — 변이 표의 셀 분리가 그 증거).

## Issues / Risks

### Blocking (contract obligations)

**B1 — 연타 창 리터럴 "5초"가 무핀(변이 B1-A 실측).** SoT v1.8.13 행·결정 브리프 D4 추가 확정·페이즈 문서 세 곳이 모두 `SCENE_NOTE_DOUBLE_SUBMIT_WINDOW`**(5초)**를 오너 확정값으로 명시한다. 그러나 회귀는 전부 상수를 **상징적으로** 참조한다(`test_scene_notes_api.py:633`의 `self.now += SCENE_NOTE_DOUBLE_SUBMIT_WINDOW`, 연타 셀의 고정 200ms). 실측: `seconds=5` → `seconds=6`으로 바꾸면 **46셀 전부 green** — 창이 위로 자라는 방향은 완전히 무신호다(아래로는 200ms 연타 셀이 하한을 느슨하게 잡는다). 이 저장소의 경계 행렬 규칙은 "모든 리터럴이 named regression test에 대응할 것"을 요구하고, 같은 커밋에서 개수 리터럴(분류표 26·tier 73/99)은 핀 셀을 받았으며 SoT 버전 리터럴도 `test_docs_indexes`가 핀한다. 값 드리프트가 계약 문언과 조용히 갈라지는 것을 막으려면 `assertEqual(SCENE_NOTE_DOUBLE_SUBMIT_WINDOW, timedelta(seconds=5))` 형태의 핀 셀(SoT v1.8.13·오너 2026-08-31 근거를 docstring에)이 필요하다. **폐쇄 조건 = 이 핀 셀의 추가.**

### Hardening recommendations (non-blocking)

**H1 — SoT v1.8.13 행의 회귀 수치 오기 "27→46".** 실측 23→46(+23). work_log 세션 5는 바르게 적었다. 정본 변경이력 행의 사실 오기이므로 해당 행의 회귀 문언을 정정할 것(선례: 2026-08-31 세션 2 hardening #5가 v1.8.11 행의 회귀 기술을 in-place 정정). 커밋 메시지(`edec884`)의 같은 오기는 불변이므로 기록만 남긴다.

**H2 — 행위자 셀 docstring이 잠그는 것보다 많이 주장(변이 B1-E 실측).** `test_the_row_names_the_actor_not_the_owner_field`의 docstring("소유자와 우연히 같아도 출처가 달라야 한다")은 세션 사용자 vs 프로젝트 소유자 구분을 잠근다고 읽히지만, 이 경로는 grant가 GET/HEAD뿐이라 **소유자만 쓸 수 있어 두 출처가 구조적으로 항상 같다**. 실측: `actor_user_id`를 소유자 조회로 바꿔도 46셀 green. 셀 자체는 "행위자가 alice(세션)다"를 실제로 잠그므로 결함이 아니다 — docstring의 주장 범위를 구조적 동일성을 언급하도록 줄이면 다음 검증자가 같은 오독을 하지 않는다(Slice 0 M1·Slice 1 S1과 같은 "가드가 통과하는 이유" 계열).

**H3 — 같은 계열 리터럴 12000·200도 무핀(Slice 0·1 유래, 이 슬라이스 밖).** `SCENE_NOTE_MAX_CHARS = 12000`(SoT v1.8.11)과 `SCENE_NOTE_PREVIEW_MAX_CHARS = 200`(SoT v1.8.12)의 경계 셀도 상수를 상징적으로 쓴다 — 12000→13000, 200→300 드리프트가 무신호다. Slice 0 검증이 12000을 경계값 2셀에 매핑했으나 그 셀들은 값이 아니라 경계 *동작*을 잠근다. B1 핀 셀을 만들 때 같은 형태 셋(5초·12000·200)으로 한 번에 닫기를 권한다(전부 오너 확정 리터럴).

### 5. 전수 회귀 (test-mongo ON, 38분 34초)

- collect-only **2666**(구현자 주장 2665+skip 1과 동일), 착수 전 2643 주장은 2666−23(신규 셀)과 산술적으로 일치.
- 실측 **2663 passed / 9 failed / 1 skipped / 3082 subtests passed + 7 SUBFAILED**. **9 failed는 전부 `test_docs_indexes`이고, 전부 이 검증자가 실행 중 만든 미등록 기록 파일(`docs/verifications/2026-09-01/`)을 잡은 것** — 인덱스 미등재(2)·건수 주장 4곳(264↔265)·일수(60↔61)·분포 합. 즉 **제품 코드·장면 메모 셀은 전부 green이고, 유일한 실패 원인은 검증자 자신의 기록 등재 전 실행이었다.** 검증 가이드의 "환경이 측정의 일부" 규칙대로 이 사실을 남긴다 — 이 우발 실측은 기록 가드(건수·판정 열·분포)가 등재 없는 기록 하나를 즉시 잡는다는 것의 부산물 증명이기도 하다.
- 등재(인덱스 행 + 건수 4곳 + 분포 갱신) 뒤 `test_docs_indexes.py` 단독 재실행 = **13 passed / 275 subtests**(구현자의 정정 직후 274에서 이 기록 판정 열 +1 — 문서화된 "기록 한 건당 +1" 규칙과 일치).
- **다음 전수 기대값 = `2665 passed / 1 skipped / 3089 subtests`** — 구현자 예고 2665/1/3088에 이 기록의 판정 열 subtest +1. 측정 환경: 베타, test-mongo healthy, `.env` 무관(기본 URI 27020), mypy 설치.

## Verdict

**조건부 합격** — 연타 창 리터럴 "5초"(SoT v1.8.13, 오너 확정 2026-08-31)에 대한 핀 셀이 없다(Blocking B1 — 변이 실측으로 무핀 확인). 나머지 전 축은 구현·선언·생성물·회귀가 정본과 일치하고 검증자 독자 변이 4종이 전부 물렸다.

## Outstanding items

- **B1 폐쇄(핀 셀 추가) 전에 Slice 3 착수하지 않는다** — 폐쇄는 다음 세션(또는 오너 지시 시 이 세션)에서 셀 1개 + SoT v1.8.13 행 회귀 문언 정정(H1)으로 닫는다. 폐쇄 후 전수 기대값은 **셀 +1**(`2666 passed / 1 skipped / 3089 subtests`, collect 2667)이다.
- H2·H3은 권고 — H3은 B1 폐쇄 때 함께 닫으면 비용이 거의 0이다.
- frontend 전수는 이번에 측정하지 않았다(핸드오프 지시 — 프론트를 만지는 다음 세션이 함께 잰다).

## Reproduction

```bash
# 전제: 베타, test-mongo 기동·healthy 확인
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 집중(가드 4파일) — 191 passed / 1116 subtests
python3 -m pytest -q tests/test_scene_notes_api.py tests/test_activity_actions.py \
  tests/test_activity_ui_labels.py tests/test_auth_api.py

# 전수 — 2666 collected. 실측: 2663 passed / 9 failed / 1 skipped / 3082 subtests passed
# (+7 SUBFAILED) in 38분 34초. 9 failed 전부 test_docs_indexes — 아래 주석 참조.
python3 -m pytest --collect-only -q | tail -1
python3 -m pytest -q 2>&1 | tail -3

# 변이(B1-A: 리터럴 무핀 재현) — 46 passed가 나오면 무핀 입증
git status --short   # empty여야 함
sed -i 's/SCENE_NOTE_DOUBLE_SUBMIT_WINDOW = timedelta(seconds=5)/SCENE_NOTE_DOUBLE_SUBMIT_WINDOW = timedelta(seconds=6)/' \
  services/application/app/routers/notes.py
python3 -m pytest -q tests/test_scene_notes_api.py   # → 46 passed (변이가 안 물림)
git checkout -- services/application/app/routers/notes.py && git status --short  # empty
```
