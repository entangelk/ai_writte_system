# Work Log — 2026-08-29

## Session 1 — 재검증 조건 N1·H1·N2 폐쇄(오너 결정)

### Goals

- 독립 재검증 [`2026-08-29/chapter_scene_hierarchy_b1_b5_closure.md`](../../verifications/2026-08-29/chapter_scene_hierarchy_b1_b5_closure.md)(**조건부 합격**, `2c77a70`)이 남긴 조건 **N1**(평면 legacy export·versions 계약 침묵)과 비차단 **H1**(장 unarchive 부재의 D8=A 근거 모호)·**N2**(accept Archived 409 문구)를 닫고 계약·셀로 고정한다.

### Completed work

- **오너 결정 브리프** 제출(N1·H1 두 축 선택지 표) → **N1=ⓐ(대피 경로 명시)·H1=①(문구 정리)** 확정. N2는 선례로 종결(아래 Decisions).
- **SoT v1.8.10**(`docs/system-contract-sot.md`): 계층 조항에 "정합 평면(챕터 0개) 프로젝트의 전체 export와 개별 Draft의 versions 읽기는 migration 전 대피 경로로서 200 유지(versions는 ordered set을 읽지 않아 혼합 상태에서도 200), 부분 migration 상태의 export는 같은 503" 문구 추가·변경이력 행·헤더(버전·갱신일). `README.md` 절차 표 ④ 칸 v1.8.10 동기화(`test_docs_indexes` 버전 일치 가드의 요구).
- **export 라우터 주석 정정**(`services/application/app/routers/projects.py` export `except DraftOrderIntegrityError`): "unmigrated legacy data blocks it" → 혼합(부분 migration)·비정합 legacy만 차단하며 정합 평면은 대피 경로로 export된다는 실제 동작 기술(SoT v1.8.10·오너 결정 인용).
- **decisions D8 문구 정리**(`docs/plans/chapter-scene-hierarchy-decisions.md` Follow-up): 장 unarchive 공개 경로 미제공 — D8=A의 "복구 가능"은 자식 상태 보존이라는 **저장 성질**이지 공개 경로 약속이 아니며 project unarchive(v1.5 MVP 범위 밖)와 대칭.
- **신규 셀 3종** `FlatLegacyEscapePathReadsTest`(`tests/test_application_api.py`, 기존 `LegacyOrderedDraftMigration503Test` 뒤): 평면 export 200(본문 단정 포함)·평면 versions 3경로(목록/상세/버전 export) 200·혼합 export 503. 양방향 가드 문서화(under: 평면 export를 503로 바꾸면 재실패 / over: 혼합 검사 제거 시 재실패).
- **검증**: 집중 22 passed(신규 3 + legacy 이웃 + docs 가드) · 전수(test-mongo ON) 아래 Verification · mutation 2종.

### Issues found

1. **N1 계약 갭** — 문제: 순수 평면(정합 ordered unit·챕터 0개) 프로젝트는 목록 읽기가 503인데 `GET /export`·versions가 200으로 동작하고 SoT v1.8.9 계층 조항은 이 표면에 침묵했으며 export 라우터 주석은 실제 동작과 어긋났다. 원인: v1.8.9가 503 face를 "공개 CRUD·Writing accept"로만 열거 — export의 legacy 분기(평면 ordered-unit export)와 versions 읽기(ordered set 미참조)는 명세되지 않은 채 남았다. 해결: 오너 결정 ⓐ로 읽기 허용을 계약에 명시하고 주석을 실제 동작으로 정정, 셀 3종으로 고정. 결과: 재검증의 판정 조건 해소 — 코드 동작 무변경.
2. **subtest 기준선 수치 정밀화** — 재검증 기록은 전수를 2567/4/**3021** subtests로 보고했으나 본 세션 전수는 2570/4/**3022**. 작업 전 5파일을 `git checkout`으로 되돌린 기준선 트리에서 전수를 재측한 결과 **2567/4/3022** — 기준선 자체가 3022였고(1 차이는 재검증 세션의 측정 시점 조건 차이), 본 슬라이스의 영향은 **+3 passed(신규 셀), subtest ±0**(`test_application_api.py` 단독 비교 124→127 passed·544→544 subtests로도 실증). 되돌림·복원은 cp 백업 + 바이트 비교(`cmp`)로 검증.

### Decisions

- **N1=ⓐ(오너, 2026-08-29)** — 평면 legacy의 export·versions 읽기 허용을 "migration 전 대피 경로"로 SoT에 명시. 이유: 운영 Mongo가 평면(migration 미적용)이고 목록이 이미 503인 상태에서 export·versions가 사실상 유일한 데이터 대피 창구 — migration dry-run→apply(배포 전 잔여) 전까지 제거하면 운영 데이터를 잠근다. tradeoff: "목록은 막히는데 전체 내보내기는 되는" 비대칭이 계약에 명문화됨. migration apply 완료 프로젝트에서는 이 분기가 자연 소멸(향후 폐기 후보).
- **H1=①(오너, 2026-08-29)** — 장 unarchive 공개 경로는 미제공 유지, D8=A의 "복구 가능" 문구를 저장 성질로 정리. 이유: D8=A의 "복구 가능"은 D8=C(보관 전파) 대비 "자식 상태를 잃지 않는다"는 뜻이었고, project unarchive도 v1.5부터 같은 이유로 미제공이라 장만 먼저 여는 근거가 없다. 실제 복구 UI 요청은 별도 슬라이스로 열려 있음.
- **N2 종결(구현자 판단, 선례 기반 — 오너 브리프에 보고)** — accept의 Archived 409 문구(`"project, chapter, or draft is archived"`)는 SoT 반영 불필요. 근거: SoT 전문 grep으로 archived 409 문구를 리터럴로 등재한 적이 0건이며 H3 "detail 분기 금지"(로그인 403만 등재된 유일 예외) 관행이 있으므로 현행 "셀 green으로 문구 미고정" 관행 유지.

### Mutation verification

| # | 방향 | 적용 diff | 파일:줄 | 물린 셀 |
|---|---|---|---|---|
| M1 | under(대피 경로) | `export_project` legacy 분기 진입부에 `if drafts: raise DraftOrderIntegrityError("scene hierarchy migration is required")` 삽입 — 평면 export를 503화 | `core_sot/service.py:1002`(`self._require_ordered_drafts(drafts)` 직전) | `FlatLegacyEscapePathReadsTest::test_flat_legacy_project_export_is_the_migration_escape_path` (1 failed — 정확히 대상 셀만) |
| M2 | over(혼합 fail-closed) | `export_project` 혼합 검사 `if any(` → `if False and any(`(export 지점만 — `list_drafts`의 동형 검사는 무변) | `core_sot/service.py:941-946` | `FlatLegacyEscapePathReadsTest::test_mixed_hierarchy_state_export_still_fails_closed` (1 failed — 정확히 대상 셀만) |

절차: 구현 커밋(`9dead9e`) 후 적용 → `pytest tests/test_application_api.py` → `git checkout -- services/application/app/core_sot/service.py` 복원 → `git status --short` 0건 확인(각 1회).

### Verification

- 집중: `FlatLegacyEscapePathReadsTest` + `LegacyOrderedDraftMigration503Test` + `tests/test_docs_indexes.py` — **22 passed, 270 subtests**.
- 전수(test-mongo ON, `docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo` 후 `python3 -m pytest tests/ -q`, 종료 후 down): **2570 passed / 4 skipped / 3022 subtests — 0 failed**(245.89s). 기준선(작업 전 트리 재측) 2567/4/3022 대비 **+3 passed, subtest ±0**.
- 프론트·`schema.d.ts`·OpenAPI 무변(코드 동작 무변경 슬라이스 — 주석·문서·셀만 변경)으로 재생성 대상 없음.
- HANDOFF.md 갱신 불필요 실측: N1·H1·export 관련 항목 부재(grep 0건), 이번 결정으로 낡아지는 서술 없음. 해소 기록은 SoT 변경이력·본 로그·CHANGELOG에 둔다(검증 인덱스 행은 그 시점 기록 원칙 — `verifications/README.md` 서두 규칙).

### Next steps

- **migration dry-run→apply→재실행 no-op 검증은 잔여**(배포 전 과제, 세션 10~11 기록 그대로). 적용 완료 후엔 평면 대피 경로 분기가 자연 소멸 — SoT v1.8.10 조항의 폐기 검토가 그 시점 과제.
- 운영 Mongo는 평면 상태 — 평면 프로젝트의 export·versions 200 동작은 이제 **계약된** 동작이다(재검증 Outstanding 항목 해소).

## Session 2 — 2차 재검증 조건 N3·N4 폐쇄

### Goals

- 2차 독립 재검증 [`flat_legacy_escape_path_closure.md`](../../verifications/2026-08-29/flat_legacy_escape_path_closure.md)(**조건부 합격**, `8f97238`)의 조건 **N3**("versions는 혼합 상태에서도 200" 분기 무셀)·**N4**("v1.5 MVP 범위 밖" 인용 출처 부재)를 닫는다.

### Completed work

- **N3 셀**: `FlatLegacyEscapePathReadsTest::test_mixed_hierarchy_state_version_reads_stay_open` 추가 — 혼합 형상(챕터 먼저 생성 → 평면 draft → save, 재검증 재현 스크립트와 동일 순서)에서 legacy draft의 versions 3경로(목록·상세·버전 export) 200과 본문을 단정. 클래스 docstring에 해당 방향 가드 1줄("혼합 상태에서 versions만 503로 막는 중간 설계도 mixed-versions 셀이 잡는다").
- **N4 인용 정정**: decisions D8 follow-up와 SoT v1.8.10 변경이력의 "project unarchive(v1.5 MVP 범위 밖)"을 실측 출처로 교체 — SoT v1.5 archive 정책(2026-06-28 확정, `daily_logs/2026-06-28/work_log.md:207` — "unarchive/상태전이는 차단 범위 밖('archived 동안 차단'으로 한정해 향후 unarchive 여지 보존)"). SoT 행에는 인용 출처 정정 마커를 남겼다.
- **검증**: 집중 23 passed/271 subtests · V6b 재적용 mutation · 전수 아래 Verification.

### Issues found

1. **N3 무셀** — 문제: SoT v1.8.10이 명시한 "versions는 혼합 상태에서도 200"의 반대 방향(혼합만 versions 503화, 검증자 V6b)을 어떤 셀도 잡지 못했다. 원인: 세션 1 셀 3종이 평면 versions·평면 export·혼합 export만 잠그고 혼합 versions 칸을 빠뜨림. 해결: 혼합 versions 200 단정 셀 1개. 결과: V6b 재적용 시 정확히 그 셀만 재실패(1 failed — 평면 versions 셀 green 유지, 중간 설계와 전면 방어가 구분됨).
2. **N4 출처 없는 인용(세션 1 작성분 결함)** — 문제: "project unarchive(v1.5 MVP 범위 밖)"의 'v1.5 MVP 범위'를 정의하는 문서가 저장소에 없었다(재검증 전체 grep 0건). 원인: 세션 1에서 v1.5 변경이력의 archive 범위 서술과 실제 정책 기록을 짜맞춰 잘못 요약함. 해결: 실제 근거(2026-06-28 archive 정책 확정 — unarchive 상태 전이는 차단 범위 밖·여지 보존, 공개 경로 약속 없음)로 교체. 결과: decisions D8·SoT v1.8.10 행 정정 — **세션 1 로그의 같은 인용(Completed work·Decisions)도 같은 결함이 있으나 로그 무결성을 위해 본문은 그대로 두고 이 세션으로 정정을 기록한다.**

### Decisions

- 별도 오너 결정 없음 — N3·N4는 재검증 조건의 기계적 폐쇄(오너 방향 결정 N1=ⓐ·H1=①는 세션 1 그대로).
- **SoT 버전 무상승 판단**: N4는 계약 의미가 아니라 서술 근거 인용의 정정이므로(v1.8.10 행 내 정정 마커 + 본 로그 + CHANGELOG로 기록), 새 버전 행을 만들지 않았다. 계약 내용(`:661` 계층 조항)은 무변.

### Mutation verification

| # | 방향 | 적용 diff | 파일:줄 | 물린 셀 |
|---|---|---|---|---|
| V6b-r | 중간 설계(혼합만 versions 방어 — 검증자 V6b와 동일 의미) | `list_draft_versions` 라우트 try 첫 줄에 `draft = core_sot.get_draft(project_id=…, draft_id=…)` + `if core_sot.list_chapters(project_id=…): _require_migrated_scene(draft)` 삽입 — 챕터 없는 평면은 통과 | `routers/drafts.py` `list_draft_versions` | **물림** `FlatLegacyEscapePathReadsTest::test_mixed_hierarchy_state_version_reads_stay_open` (1 failed만 — 평면 versions 셀 green, 127 passed) |

절차: 구현 커밋(`717ed5e`) 후 적용 → `pytest tests/test_application_api.py` → `git checkout -- services/application/app/routers/drafts.py` 복원 → `git status --short` 0건 확인.

### Verification

- 집중: `FlatLegacyEscapePathReadsTest`(4셀) + `LegacyOrderedDraftMigration503Test` + `tests/test_docs_indexes.py` — **23 passed / 271 subtests**(+1 passed·+1 subtest는 검증자 커밋 `8f97238`의 기록 파일 등재에 따른 docs 루프).
- 전수(test-mongo ON, 종료 후 down): **2571 passed / 4 skipped / 3023 subtests — 0 failed**(234.17s). 직전 HEAD 대비 **+1 passed(신규 셀)·+1 subtest(검증자 기록 등재분 — 본 셀은 subTest 0개)**, 변동 전부 귀속 확인.
- 프론트·`schema.d.ts`·OpenAPI 무변(셀·문서만 변경).

### Next steps

- migration dry-run→apply→재실행 no-op 검증 — 배포 전 잔여(변경 없음).
- 재검증 비차단 관찰(혼합 상태 생성 경로의 전제 — "챕터만 있고 drafts 0개"에서만 조립 가능 — 을 설명하는 조항): 다음 슬라이스가 혼합 상태를 다룰 때 한 줄 후보.

---

## Session 3 — 계층화 배포·운영 migration 적용(migration 인덱스 결함 수습 포함)

### Goals

- 계층화 마감 상태(main `4cf646f`)를 배포 서버에 반영하고 운영 Mongo의 평면 데이터에
  Chapter→Scene migration을 적용한다(오너 지시: 백업 생략 — 전부 테스트 데이터).

### Completed work

- **배포(1차)**: 오너 push 후 배포 서버에서 소스를 main으로 정렬·application·gateway·frontend
  이미지 재빌드·앱 계열 교체(영속 저장소·외부 LLM/임베딩 구성 무변). 전 서비스 healthy·
  내부 health 200·프론트의 /api 프록시 정상 확인.
- **운영 migration 1차 실행 — 실패**: `DuplicateKeyError (uniq_scene_position: chapter_id=null,
  position=1)`. `replace_hierarchy`가 프로젝트마다 데이터 커밋 뒤 `(chapter_id, position)`
  unique 인덱스를 만드는데, 아직 평면인 다른 프로젝트들의 `(null, position)` 중복과 충돌한다.
  로컬 mongo migration 셀이 단일 프로젝트 형상이라 이 분기를 못 잡은 **멀티 프로젝트 무셀**이었다.
  실패 시점 상태: 첫 프로젝트 이관 커밋(1/10)·나머지 평면·unique 인덱스 소실(`_id_`만 잔존).
  앱은 계약대로 평면 프로젝트 목록만 503 fail-closed로 동작(크래시 없음·데이터 무손실).
- **수습(로컬, `9b2f1e0`)**: 회귀 우선 — 프로젝트 3개 평면 형상 셀을 추가해 수정 전
  운영과 동일한 DuplicateKeyError로 red 재현(3 서브클래스). 수정 — `uniq_scene_position`을
  partial unique(`chapter_id`가 문자열인 귀속 Scene에만 유일성)로: 중간 상태 충돌 제거·
  최종 상태 DB층 방어 유지. mutation(partial에 null 포함 복귀) 재 red 확인.
- **재배포·migration 2차**: 오너 push → 배포 서버 재정렬·application 이미지 재빌드·앱 4서비스
  교체 → migration 재실행 **성공**(`migrated=9, unchanged=1` — 1차에 이관된 프로젝트 스킵) →
  재실행 **no-op**(`migrated=0, unchanged=10`).

### Issues found

1. **멀티 프로젝트 평면 migration 무셀** — 위 Completed work. 교훈: migration 인덱스 설치는
   "전체가 계층화된 뒤"에만 유일성이 성립하는 전역 조건인데 셀이 단일 프로젝트 형상만
   검증했다. 수습 셀(`test_multi_project_flat_migration_installs_the_scene_index`)이 잠근다.
2. **배포 서버에서 `docker compose up -d`(서비스 지정)가 의존성 재검사 단계에서 10분
   대기 후에도 진행하지 않는 현상** — `--no-deps`로 개별 교체하면 즉시 성공. 원인 미상
   (dockerd 로그에 containerd session healthcheck 경계 오류 반복 관측). 재현 시 같은
   우회로 진행하고 원인 규명은 별도 과제로 남긴다.

### Decisions

- 오너 결정(2026-08-29): migration 백업 없이 이번 배포에 함께 적용 — "다 테스트라서".
- (수칙 확인) migration 스크립트 실행은 컨테이너 내 `PYTHONPATH=/app` 지정이 필요하다 —
  `python scripts/...` 실행은 스크립트 디렉터리가 `sys.path[0]`이 되어 `services` 임포트가
  실패한다.

### Verification

- 최종 운영 상태(배포 서버 실측): projects=10·drafts=10(**무손실**)·chapters=10·
  legacy_flat=0(**전면 계층화**)·인덱스 `_id_`,`uniq_scene_position`(**partial unique 설치**).
- 서비스 레이어: 전 프로젝트(10/10) `list_chapters`·`list_drafts` 정상 반환, 앱 health 200.
- 로컬 수습 검증: mongo 전수 **88/88**(+신규 3)·backend 전수 **2574 passed / 4 skipped /
  3024 subtests — 0 failed**.

### Next steps

- 오너가 공개 사이트에서 계층화 UI(장/장면 목록·생성·순서 이동·삭제 확인창)를 육안 확인한다.
- compose up 대기 현상의 원인 규명은 별도 과제(재현 시 `--no-deps` 우회 기록은 위 2).

---

## Session 7 — 장면 메모 구현 페이즈

### Goals

- 장면 메모 기능을 다음 작업자가 독립적으로 이어갈 수 있는 작은 구현 Slice로 나눈다.

### Completed work

- [`scene-note-implementation-phases.md`](../../plans/scene-note-implementation-phases.md)에 Slice 0~4를
  추가했다: 저장·파기 수명 → 읽기/검색 API → 쓰기/활동 기록 → 별도 화면 → 드로어 통합.
- 각 slice의 범위, 인가, 검증, 인계 조건과 공통 checkpoint/mutation 규칙을 적었다. 특히 Slice 0은
  HTTP/UI 없이 데이터 수명만 닫고, Slice 3~4는 API 계약을 바꾸지 않는다.

### Decisions

- 오너 지시(2026-08-29): 메모는 한 덩어리로 구현하지 않고 작은 Slice로 순차 진행하며, 다음
  작업자가 문서만 읽고 그대로 재개할 수 있어야 한다.

### Next steps

- **Slice 0**: `SceneNote` 전용 저장소와 Scene/Chapter/project purge 수명을 테스트부터 구현한다.

---

## Session 6 — 장면 메모 기능 결정 브리프

### Goals

- 다음 기능 작업인 메모에 필요한 위치·저장 단위·공개 범위 결정을 구현 전에 명확히 한다.

### Completed work

- [`scene-note-decisions.md`](../../plans/scene-note-decisions.md)를 작성해 D1~D4를 오너 결정으로
  분리했다: Scene 메모의 화면 위치, 저장 수명, access grant 열람 범위, 저장 경험.
- 권고 조합은 편집기 드로어의 Scene 메모 탭 + 서버 전용 컬렉션 + 소유자 쓰기/grant 읽기 +
  명시적 저장/최신 한 값이다. 원고 정본·export·LLM 프롬프트와 분리하는 이유와 Scene/project
  purge·활동 분류표에 연결해야 하는 후속 계약을 기록했다.
- 계획 인덱스와 HANDOFF를 `Proposed / 오너 결정 대기` 상태로 연결했다.

### Decisions

- 오너 지시(2026-08-29): 이동 링크 가시성 개선 다음에는 메모 기능을 검토한다. 구현 대신 결정
  브리프부터 작성해 위치·저장 단위·공개 범위를 선택할 수 있게 한다.

### Verification

- `docs/plans/README.md`의 링크·상태 표기와 HANDOFF의 브리프 링크를 대조했다.

### Next steps

- 오너가 D1~D4를 결정하면, 그 값을 브리프의 확정 표와 정본 계약에 반영한 뒤 최소 구현
  슬라이스를 시작한다.

### Decision update

- 오너 결정(2026-08-29): D1은 **C+A** — 별도 메모 화면을 두되 모든 Scene 메모를 편집기
  드로어에서도 확인·검색한다. D2·D3·D4는 추천 A를 채택했다: 전용 서버 저장소, 소유자 쓰기와
  access grant 읽기, 명시적 저장/최신 한 값. 검색은 프로젝트 안 제목·본문 부분 일치로 시작한다.
- 이 조합은 Chapter/프로젝트 전용 메모나 협업 모델을 만들지 않는다. 첫 구현은 Scene 메모만이다.

---

## Session 5 — 보조 이동 링크 가시성

### Goals

- 텍스트와 화살표만으로 남아 있던 보조 이동 링크를 실제 화면 기준으로 전수 분류하고 발견성을 높인다.
- 목록 행·뒤로 가기·계정 메뉴처럼 이미 문맥별 표현이 있는 링크는 유지한다.

### Completed work

- 결과 안내의 `검토함에서 확인하세요 →`, 작품 기억의 `검토 전 n개 →`, 활동 원장의 `원고 열기`,
  내 작업의 `활동`·`관측`, 관리자 승격 뒤 `프로젝트 열기`를 `inline-navigation-link`로 통일했다.
- 공통 규칙은 굵은 밑줄과 hover/focus 색 변화로 일반 본문에서 구별하되, 배경·padding은 두지 않아
  실행 버튼으로 오인되지 않게 했다.
- 관리자에서 작업장으로 이동하는 기존 `primary-link`는 accent 버튼으로 유지했다. 목록 행·뒤로
  가기·계정 메뉴는 각자의 행/방향/메뉴 문맥을 이미 표현하므로 공통 보조 링크에 넣지 않았다.
- `navigationLinks.test.ts`가 보조 이동 5개 파일의 정확한 집합과 버튼화 방지 스타일을 함께 잠근다.

### Decisions

- 오너 지시(2026-08-29): 계층화 migration 마감 다음 작업으로 이동 링크 가시성 개선을 먼저 진행하고,
  메모 기능은 그 뒤에 둔다.
- 주요 이동은 기존 accent 버튼 선례를 유지하고, 문장·메타 행 안의 이동은 일관된 보조 링크로 둔다.

### Issues found

- 첫 과도 적용 mutation은 `className="inline-navigation-link back-link"`를 넣었는데도 통과했다.
  가드가 속성 전체가 아니라 첫 클래스만 문자열로 읽은 결함이었다. 정규식으로 모든 클래스 조합을
  읽도록 보강한 뒤 같은 mutation이 재실패했다.

### Verification

- 집중 렌더 회귀: `AnalysisTrigger`·`ProjectOverview`·`ActivityTimelinePage`·`PersonalHubPage`
  **47/47**.
- 스타일 가드: `navigationLinks`·`typeScale` **6/6**.
- 이 환경의 30초 명령 수명 제한 때문에 프론트 전수와 production build는 완료 출력을 받지 못했다.

### Mutation verification

체크포인트 `c6dc865`의 clean tree 위에서 mutation을 적용하고 `apply_patch` 역편집으로 복원했다.

| # | 방향 | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|---|
| M1 | under | 작품 기억의 `검토 전 n개 →`에서 공통 클래스 제거 | `projects/ProjectOverview.tsx` | `보조 이동 링크 > gives every plain secondary navigation link the shared treatment` |
| M2 | over | not-found의 뒤로 가기에 `inline-navigation-link` 추가 | `App.tsx` | 위 셀의 정확 집합 단정 |

### Next steps

- 다음 기능 작업인 메모는 구현 전에 위치·저장 단위·공개 범위를 정하는 오너 결정 브리프를 작성한다.

---

## Session 4 — 배포 "감지 지연" 원인 조사·수습(embedding 의존)

### Goals

- 오너 지시: 저번 배포부터 반복된 "빌드는 다 됐는데 확인에 시간이 많이 걸리던" 현상의
  원인을 파라라서 수습한다. 이번 배포(세션 3)에서도 `docker compose up -d`(서비스 지정)가
  10분 넘게 무대기했던 관측이 계기다.

### Completed work

- **원인 규명 — `embedding` 의존 빌드.** base compose의 `application.depends_on`이
  `embedding: service_healthy`를 포함하는데, 임베딩을 외부 API로 쓰는 배포 서버에는
  embedding 컨테이너도 **이미지도 없다**. `up <svc>`(의존 포함)는 존재하지 않는 이미지를
  그 자리에서 **빌드**하기 시작하고(torch·sentence-transformers 설치), 끝나도 컨테이너
  기동+healthy(`start_period` 300s — 첫 기동 모델 다운로드 고려)를 기다린다. 이 대기가
  지연의 정체였다. 재현 실험: 변화 없는 `up -d application`조차 "Image
  ai_writte_system-embedding Building"로 60초 타임아웃(직접 관측).
- **부수 오류 판명.** dockerd 로그의 `healthcheck failed: only one connection allowed`
  (containerd grpc 경고 — moby/buildkit#748·moby#52721류)는 빌드 중 발생하는 경고로
  **컨테이너 헬스에는 영향이 없었다**(전 서비스 healthy 유지·현재도 간헐 발생). 범인이
  아니라 동행자였다. 디스크 42%·메모리 여유로 자원 고갈도 아님.
- **기존 external.yml이 왜 안 쓰였나.** `docker-compose.external.yml`이 정확히 이 문제의
  처방(profile 뒤로 + depends_on 교체)이지만 chroma·ES까지 끈다 — 이 서버는 LLM·임베딩만
  외부이고 chroma·ES를 in-stack으로 쓰는 **하이브리드**라 그대로는 기동 거부
  (CHROMA_HOST·ELASTICSEARCH_URL 필수값 없음). 스택 컨테이너 라벨도 base 단독으로
  만들어져 있었다(override 미적용 확인).
- **수습 — `docker-compose.external-embedding.yml` 신설(커밋 `f73e820`, 오너 결정).**
  embedding만 profile(`local-models`) 뒤로, application·worker·generation_worker의
  depends_on을 `!override`로 교체(embedding 제거·나머지 4/3/4 유지),
  `EMBEDDING_SERVICE_URL` `:?` 필수화. 배포 절차(사용법)는 파일 헤더 주석에 runbook으로
  기록했다.
- **리모트 적용·실증.** 오너 push → 배포 서버 재정렬 → 새 조합
  (`-f docker-compose.yml -f docker-compose.external-embedding.yml`)으로 스택 라벨 갱신 →
  **핵심 실증: 의존성 포함 `up -d application`이 0.741초에 완료**(mongo·gateway·chroma·
  elasticsearch healthy 확인 후 즉시 — embedding은 등장하지도 않음). 이전 10분+ 대기에서
  0.7초로 수습됐다.

### Issues found

1. **배포 지연의 정체는 docker 감지 결함이 아니라 compose 선언과 실제 구성의 불일치**였다 —
   base compose는 "embedding이 스택 안에 있다"를 기본으로 선언하고, 이 서버는 임베딩만
   외부인데 그 차이를 담는 조합 파일이 없었다(전부 외부용만 있었다).
2. 세션 3의 `--no-deps` 우회는 유효했지만 원인을 고친 게 아니었다 — 의존 확인 자체를
   건너뛰었을 뿐. 이번 override로 의존 포함 up이 정상 경로로 즉시가 됐다.
3. containerd grpc 경고("only one connection allowed")는 여전히 간헐 발생한다(idle에서도
   4건/10분 관측) — 빌드/조회와 겹칠 때의 경합 경고로 판명되어 방치 가능. 재발 시 영향은
   로그 노이즈 수준(컨테이너 healthy 무관 실측).

### Decisions

- 오너 결정(2026-08-29): 수습은 **override 신설 + runbook 기록** — `--no-deps` 우회
  고정이 아니라 조합 자체를 고치는 쪽.

### Verification

- 병합 config 검증: 기본 서비스 목록에서 embedding 제외·의존 4/3/4·
  `--profile local-models`로 복귀·`:?` 필수 동작.
- `tests/test_compose_backend_env.py` + `tests/test_docs_indexes.py` — 27 passed.
- 리모트 실증: 의존 포함 `up -d application` **0.741초**(이전 10분+), 전 서비스 healthy·
  앱 health 200·migration 상태 무변(세션 3 결과 유지).

### Next steps

- 다음 배포부터는 `-f docker-compose.yml -f docker-compose.external-embedding.yml` 조합이
  이 서버의 표준 절차다(파일 헤더 주석이 runbook). 전부 외부 구성이 필요해지만 않으면
  `docker-compose.external.yml`과 함께 쓰지 않는다(의존 교체 충돌).
