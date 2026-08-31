# 장면 메모 Slice 1(읽기 API·검색) 독립 검증

## Subject metadata

- 날짜: 2026-08-31
- 요청자: 오너("다음작업 검증해줘")
- 검증자: Claude Code 세션(구현자와 다른 세션 — 구현은 Claude Opus 5 커밋 `bf8de93`~`aafab21`)
- 대상: 장면 메모 Slice 1 — `GET /projects/{pid}/notes?query=`·`GET /projects/{pid}/drafts/{did}/note` 2 operation, service 목록·검색, `schema.d.ts` 재생성. 쓰기 route·활동 기록은 Slice 2
- 정본: `docs/system-contract-sot.md` **v1.8.12**(변경이력 행 + Phase 1 "장면 메모 읽기" 조항), `docs/plans/scene-note-decisions.md` Follow-up(오너 결정 3건: 미리보기 검색 연계·페이지네이션 없음·보관 포함), `scene-note-implementation-phases.md` Slice 1
- 검증 소스: 커밋 `c861bc0`(구현)·`440c811`(순서 가드 보강)·`4e6fbe3`(정본)·`aafab21`(실측), 직전 `bf8de93`·`67992f8`(Slice 0 검증 지적 반영 — 함께 감사), HEAD `aafab21`, 트리 clean
- 환경: Slice 0 검증과 동일(WSL2, `PYTHONPATH=.`, test-mongo rs-test 27020 가동)

## Scope

1. ★경계 행렬 — v1.8.12 조항 전 분기의 셀 대응(특히: 503 face·미리보기 경계·body=null·보관 두 축·인가)
2. 구현자 보고 결함(S1 순서 가드)의 사후 재현
3. 검증자 독자 변이 W계열 5종 — 구현자 S1~S9가 안 덮은 방향(정규화 상실·윈도우 과잉·인가 제거·**503 핸들러 제거**)
4. Slice 0 검증 지적 반영 커밋(`bf8de93`·`67992f8`)의 충실성
5. 전수 backend(test-mongo ON)·frontend(단독) 수치 재현, schema.d.ts·tier 카운트·문서 가드
6. 기록 정합성 — 커밋 해시 인용·Next steps·운용 수치

## Methodology

Slice 0 검증과 동일한 프로토콜(계약 먼저 읽고 행렬 → 코드 → 셀 → 변이; 사전 `git status --short` empty → 변이 → 요약 행 읽기 → `git checkout --` 복원 → clean 확인). 전수는 backend(30:29) 종료 뒤 frontend를 **단독** 실행(구현자 work_log의 "두 전수를 겹쳐 돌리지 않는다" 교훈 준수).

## Findings

### 1. 경계 행렬 — 1개 빈 칸 발견 (→ 차단)

| v1.8.12 조항 | 구현 | 셀 | 변이 |
|---|---|---|---|
| 2 route·읽기 전용(활동 없음) | `routers/notes.py:69-127`(activity 협력자 부재) | 구조적 + API 19셀 | — |
| 순서 = `list_drafts`에서(장→장면 position, 단일 정의) | `service.py` `list_scene_notes`가 `self.list_drafts` 사용, repo는 무정렬 | service 순서 셀(장 뒤집기+저장 순서 반대) | S1 재실행 **2셀 물림**(보고와 동일) |
| 검색 서버 적용·제목/본문 부분일치·대소문자 무관 | `service.py` `needle = (query or "").strip().casefold()` | 제목/본문·case 셀 | W1(casefold 제거): **1셀 물림** |
| 공백 query = 필터 없음 | 동일 `needle` 경로 | `test_blank_query_lists_everything`(None·""·"   ") | 구현자 S4 |
| 미리보기 검색 연계(매치 중심·머리 200·`truncated`·전문은 단건) | `build_note_preview`(`notes.py:39-66`), `SCENE_NOTE_PREVIEW_MAX_CHARS = 200` = `ACTIVITY_VALUE_MAX_CHARS`(`activity/log.py:22`, **같은 값 실측**) | preview 6셀 + API 2셀 | W3(윈도우 off-by-one): **2셀 물림**, 구현자 S6·S7 |
| 페이지네이션 없음 | route 파라미터 `query` 하나뿐(limit/offset 부재) | 구조적 | — |
| 보관 포함 + `scene_archived`·`chapter_archived` 두 축 | 필터에 archived 없음, 행에 두 축 | service 플래그 셀 + API 혼합 플래그 셀 | 구현자 S5·S9 |
| 메모 없음 = `body=null`(404 아님), `body=""`는 빈 메모 | `notes.py:122-127` | 정확한 payload 동등 셀 + 빈 메모 구분 셀 | 구현자 S8 |
| 단건: 타 프로젝트·없는 project = 404 | `_require_*` NotFound → 404 | 2셀 | — |
| 인가 `_REQUIRE_PROJECT_OWNER` 재사용(401/403/grant+access-log) | `dependencies` 재사용, 라우터 재기록 없음 | 401·403·grant+로그 2행 셀 | W4(deps 제거): **6셀 물림** — "새 경로가 이미 401/403 전수 가드 안에 있다"는 주장을 실증 |
| **평면 legacy의 503 face** | `notes.py:85-88` 핸들러 + OpenAPI 선언(`_ERRORS_404_MIGRATION`) | **셀 없음** | W5(핸들러 제거): **0셀 — 가드 부재 실증**(60 passed) |

**W5 상세**: `except DraftOrderIntegrityError → 503` 분기를 통째로 지우고 notes 2파일+`test_chapter_hierarchy.py`를 돌려도 **아무 셀도 실패하지 않았다**(60 passed). 이 상태의 실제 동작은 평면 legacy 프로젝트에서 500(미처리 예외)이다. 503 face는 v1.8.12 행에 명문화된 should-fire 분기이고 OpenAPI에도 선언돼 있으나 행동 셀이 없다 — drafts 쪽 503 셀(`test_chapter_hierarchy.py:480` 등)은 notes 라우터를 거치지 않는다. **안내서 기준 무추적 계약 분기 = 차단.** 폐쇄는 셀 1개(평면 legacy project에 GET /notes → 503; 혼합 상태도 포함하면 v1.8.10 대피 경로 축과 대칭).

### 2. 구현자 보고 결함(S1)의 진위 — 사실로 확인

"순서 계산을 `service.list_drafts` → `repo.list_drafts`로 강등해도 순서 셀이 통과했다(chapter-1/chapter-2 사전순이 position 순과 우연히 일치)" — 검증자가 동일 변이를 재적용해 **정확히 보고된 2셀**(순서 셀·`test_unknown_project_is_not_found`)이 재실패. 보강(장 뒤집기, 커밋 `440c811`)이 실제로 물림. 단, work_log가 인용한 해시 `6c05e73`은 **존재하지 않는다**(§5-1).

### 3. 검증자 독자 변이 5종 요약

| # | 방향 | 적용 diff | 결과 |
|---|---|---|---|
| W1 | under(대소문자 구분 복원) | service 필터의 `scene.title.casefold()`·`note.body.casefold()` → 원문 | **1셀** 물림 |
| W2 | under(정규화 비대칭) | 라우터 `find(query.strip().casefold())` → `find(query.casefold())` | **0셀** — 서비스는 strip, 라우터는 안 하는 비대칭(공백 padding query가 본문 매치로 목록에 오르되 미리보기는 머리 200)을 아무 셀이 못 잡음 → 보강 후보 |
| W3 | over(윈도우 off-by-one) | `body[start:start+MAX]` → `MAX-1` | **2셀** 물림(예산 상한·끝 창) |
| W4 | under(인가 제거) | 단건 GET `dependencies=_REQUIRE_PROJECT_OWNER` → `[]` | **6셀** 물림(tier 행렬 3종+401 전수 등) — tier 무수정 통과 주장 실증 |
| W5 | under(503 face 제거) | 목록의 `DraftOrderIntegrityError` 핸들러 삭제 | **0셀** — 차단(§1) |

### 4. Slice 0 검증 지적 반영(`bf8de93`·`67992f8`) — 충실

6건 중 5건 폐쇄: 읽기-아카이브 셀(신규 16째, 변이 V6로 물림 기록)·검사 순서의 선례 유도(SaveDraftRequest 422-먼저 관례와 정합, Slice 2는 코드값 literal만 남김)·바이트 산정 정정·해시 정정·SoT 3경로 정정. #6(`mongo_collections.md`)은 합의 하에 유예. 반영 자체는 정확하다.

### 5. 기록 정합성 — 3건 오류

1. **`work_log.md` Session 3이 미존재 해시 `6c05e73`을 인용**(실제 `440c811`). Session 2에서 "해시는 `git log --oneline` 출력에서 복사한다"고 같은 날 다짐한 직후의 **재발** — ae2fc9d에 이은 두 번째. 정정 필요.
2. **Session 3 "Next steps"가 낡음** — 완료된 Slice 1을 다음 순서로 적고 있음(Session 1 텍스트 복사 잔류). HANDOFF는 바르게 Slice 2를 가리켜 work_log만 오방향.
3. **`HANDOFF.md:35` "현재 96 operation 합집합"이 낡음** — Slice 1 이후 98. (SoT의 "v1.8.9, 총 96"은 버전 스코프 기술이라 무관.)

### 6. 수치 재현

- 신규 셀 실측: `test_scene_notes.py` 24(8 신규 + Slice 0의 16) + `test_scene_notes_api.py` 19 = 43. Slice 0 검증 후 신규 = 8 + 1(보강) + 19 = **+28** — 전수 증분 주장(2610→2638)과 정확히 일치.
- **backend 전수 재현: 2638 passed / 1 skipped / 3065 subtests, 30:29, exit 0**(구현자 34:29, 수치 동일).
- **frontend 단독 전수: 35 files / 385 passed, 595s, exit 0** — 겹침 없이 실행(구현자의 겹침 실패 보고와 단독 통과 주장 모두와 정합).
- `schema.d.ts` +228줄 실측, `SceneNotePayload`·`SceneNoteListItemPayload`·`SceneNoteListResponse`·2 operation 경로 확인.
- tier 카운트 70/96→72/98(`test_auth_api.py` diff) — 행렬 무수정, 카운트만 갱신. W4로 흡수력 실증.
- 문서 가드: `test_docs_indexes.py` 13 passed / 273 subtests(README↔SoT v1.8.12), 파기 로스터 4 passed.

## Issues / Risks

### Blocking (contract obligations)

1. **`GET /projects/{pid}/notes`의 평면 legacy 503 face 행동 셀 부재**(W5로 실증 — 핸들러 제거에 0셀). v1.8.12 행에 명문화된 should-fire 분기가 무셀이다. 셀 1개(평면 legacy → 503; 혼합 상태 포함 권장)로 폐쇄.

### Hardening recommendations (non-blocking)

1. **W2 — 서비스↔라우터 query 정규화 대칭 무가드**: 공백 padding query(`" 열쇠 "`)가 본문 매치로 목록에 오르고 미리보기만 머리로 떨어지는 조합을 잡는 HTTP 셀 1개 권장. 참고: `casefold()`는 길이가 변하는 글자(ß·İ 계열)에서 매치 인덱스가 원문과 어긋날 수 있으나 한국어·라틴 기본 범위에서는 무해 — 셀을 붙일 때 이 노트를 함께 남길 것.
2. **`list_scene_notes`의 Mongo 어댑터 셀 부재**: repo `find({"project_id": ...})`의 프로젝트 스코프가 Mongo측에서 무셀(Slice 0은 get/put에 mixin 6셀을 둔 선례). mixin 셀 1개(타 프로젝트 메모 제외·다중 행) 권장.
3. work_log 해시 재발(§5-1)의 처방: 기록 검수 시 `git cat-file -t <hash>` 확인을 세션 종료 체크리스트에 넣거나, 해시를 기록에 남기는 시점에만이라도 확인 절차를 둘 것.

## Verdict

**조건부 합격** — `/notes` 평면 legacy 503 face의 행동 셀 부재(W5 변이로 실증, 핸들러 제거에 0셀) — 셀 1개 추가로 폐쇄

- 코드 자체는 정본과 어긋나지 않는다: 3개 오너 결정(200=ACTIVITY_VALUE_MAX_CHARS 같은 값 실측·페이지네이션 없음·보관 두 축)·순서 단일 정의·body=null·인가 재사용 모두 구현·셀·변이로 확인.
- 구현자 변이 9종 중 핵심 주장(S1 순서·tier 무수정 흡수)은 검증자 재실행으로 사실 확인. 독자 변이 5종 중 4종 물림.
- 전수 backend 2638/1/3065 재현, frontend 단독 재현, schema +228·tier 카운트 실측 일치.
- 남는 것은 무셀 계약 분기 1개(차단 조건)와 기록 정합성 3건(비차단)이다.

## Outstanding items

- **차단 조건 폐쇄**(503 셀)는 구현자 세션에서 수행 — 검증자는 임의로 고치지 않는다(가이드).
- 기록 정정 3건(§5)도 오너 승인 시 1줄씩.
- CHANGELOG 미기록 유지(기능 Slice 2~4 진행 중 — Slice 0 검증 때와 같은 판단, 오너 재량).
- test-mongo 컨테이너(rs-test 27020) 계속 가동 중.
- 구현자가 보고한 frontend 겹침 실행 실수(productName 5s 타임아웃)는 재현하지 않았고, 본 검증의 단독 실행이 정상 결과를 확인한다.

## Reproduction

```bash
# 환경: 저장소 루트, test-mongo 기동
docker compose -f docker-compose.test.yml up -d

# 집중
PYTHONPATH=. pytest tests/test_scene_notes.py tests/test_scene_notes_api.py -q        # 43 passed
PYTHONPATH=. pytest tests/test_auth_api.py -q                                        # tier 행렬
PYTHONPATH=. pytest tests/test_docs_indexes.py tests/test_purge_project_coverage.py -q

# W5(차단 근거) — 사전 git status --short empty 확인
# routers/notes.py 의 except DraftOrderIntegrityError 블록(85-88) 삭제 후
PYTHONPATH=. pytest tests/test_scene_notes_api.py tests/test_scene_notes.py tests/test_chapter_hierarchy.py -q
# → 60 passed, 0 failed (가드 부재 실증)
git checkout -- services/application/app/routers/notes.py && git status --short      # empty

# 전수(순차 — 겹치지 않는다)
PYTHONPATH=. pytest -q                                    # 2638 passed / 1 skipped / 3065 subtests
cd frontend && npx vitest run                             # 385 passed(단독, ~10분)
```
