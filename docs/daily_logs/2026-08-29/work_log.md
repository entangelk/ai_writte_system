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
