# 독립 재검증 — 장→장면 계층화 Blocking 5건 폐쇄 확인

## Subject metadata

- 일자: 2026-08-29
- 요청자: 오너("작업 AI가 작업했던 부분 확인해서 검증하고 의심하고 또 의심해줄래? … 독립 재검증")
- 검증자: Claude Code 독립 세션(세션 9~11 구현·보강과 별개)
- 대상: 1차 검증 [`2026-08-28/chapter_scene_hierarchy.md`](../2026-08-28/chapter_scene_hierarchy.md)(판정
  **불합격**)의 Blocking 5건(B1~B5) 폐쇄를 주장하는 세션 11 보강 — 커밋 `c911f03..aafd337`
  7커밋. 최종 `aafd337`, working tree clean(검증 내내 유지).
- 정본 계약: [`plans/chapter-scene-hierarchy-decisions.md`](../../plans/chapter-scene-hierarchy-decisions.md)
  "확정 구현 계약" 절(D1=A·D2=A·D3=A·D4=A·D5=A·D6=A·D7=B·D8=A) ·
  [`system-contract-sot.md`](../../system-contract-sot.md) v1.8.9(본문 갱신 완료 상태) ·
  [`schemas/writing-workspace-v2-w0.schema.json`](../../schemas/writing-workspace-v2-w0.schema.json)
  v1.8.9 카탈로그.

## Scope

1. B1 — migration 전 평면 legacy Draft의 503 fail-closed 2층 방어(서비스 `list_drafts` 경계 +
   라우터 `_require_migrated_scene`)·Writing accept 사전 검사.
2. B2 — ① TXT 계층 export heading 셀 ② migration 무손실 축(version/snapshot/본문 byte·archived·
   부분 상태 fail-closed) 셀.
3. B3 — 1차 검증에서 red였던 회귀 기준선(`test_writing_accept.py`·프론트 전수)과 전수 재개에서
   발견된 잔여 이관 10건(mongo 4·OU-10·scratch 4·라벨표·mock).
4. B4 — SoT v1.8.9 본문 정합("미확정" 제거·"(구현 완료)"·총 96·계층 조항·활동 수) 실측 대조.
5. B5 — Chapter purge 503의 오너 ⓐ uncertain 잠금(재시도 버튼 제거·입력·취소 잠금)과
   보관 단계 재시도 부활의 양방향.
6. 전수 재실행(test-mongo ON)·파생물 신선도(schema.d.ts·build)·기록물 수치 대조.
7. 신규 탐침 — 평면 legacy 상태의 읽기 표면 중 1차 검증 범위 밖이던 export·versions 경로.

## Methodology

환경: WSL2 · python3.12 · pytest 9.0.2 · node 22.17.0 · docker 스택 기동 중(운영 app·admin·
worker·frontend) — **test-mongo는 검증 시작 시 무구동이었으므로 본 검증이
`docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo`로 기동 후
전수를 돌리고, 끝나고 `down`으로 원상 복구**했다(`--env-file /dev/null` — `.env` 중립화).
mutation은 clean tree 위 적용 → `git checkout -- <path>` 복원 → 매번 `git status --short`
0건 확인(총 8회). subtest 실패는 `SUBFAILED`로 찍히므로 요약 행 기준으로 판독했다.

- 라이브 재현: 인메모리 저장소에 평면 legacy(`create_draft`)·혼합(챕터+평면 잔존) 프로젝트를
  만들어 ASGI transport로 제품 엔드포인트 직접 호출(1차 검증 §8 절차 재사용).
- 테스트 재실행: 아래 Reproduction 전량. 수치는 세션 11 주장과 직접 대조.
- OpenAPI 실측: `create_app().openapi()` 집계. 활동 분류표: `actions.py` 레지스트리 직접 집계.
- schema 신선도: `scripts/dump_openapi.py`(stdout) → `openapi-typescript` 7.13.0 재생성 → diff.
- mutation 셀-페어링: 아래 표에 실제 적용 diff와 함께 기록.

## Findings

### 1. B1 — 503 fail-closed 2층 방어 — **폐쇄 확인**

- 코드: 서비스 `list_drafts`는 챕터 없이 평면 Draft가 남으면 `DraftOrderIntegrityError`
  (`core_sot/service.py:750-754`), 챕터가 있는 혼합 상태는 `any(draft.chapter_id not in
  chapter_ids or draft.unit_kind is not None …)`(`:732-737`)로 같은 예외. 라우터
  `_require_migrated_scene`(`routers/drafts.py:69-86`)가 `_draft_payload`의 옛 `assert`를
  대체하고 PATCH(rename)·DELETE(archive)·GET 단일이 쓰기 전에 검사한다. Writing accept는
  enrich 앞에서 장 귀속·보관을 검사한다(`writing/accept.py:112-128`).
- 라이브 재현(1차 검증에서 500이던 경로): 평면 legacy 프로젝트에서 `GET /drafts`·
  `GET/PATCH/DELETE /drafts/{did}` 전부 **503 `scene hierarchy migration is required`**.
  혼합 상태(챕터 1+평면 잔존)도 목록·legacy 단일 503, `/chapters`는 정상 200. scene 생성의
  없는 chapter_id는 404.
- 서비스 경계 셀(`test_legacy_drafts_fail_closed_at_the_service_boundary`)은 빈 프로젝트가
  `()` 정상 반환임도 같이 잠근다(over-strict 방지).
- mutation M-C/M-D/M-E(세션 11 표) 3종 재검증 — 전부 물림. M-D는 `SUBFAILED(endpoint='get_draft')`
  로 단일 읽기 subtest만 물고 목록 subtest는 서비스층이 흡수(2층 방어가 설계대로 각층 분리돼
  있음을 재실증).
- 2층 각층 셀·양방향 모두 확인. **B1 폐쇄.**

### 2. B2 — 무셀 축 셀 — **폐쇄 확인**

- TXT 계층 export: `test_export_uses_chapter_then_scene_headings_and_derived_archive`에 TXT
  단정(`"1장\n\n첫 장면\n\n첫 본문\n\n2장\n\n숨은 장면\n\n숨은 본문"`)이 추가됐고, 브리프
  계약("장 제목 뒤 장면 제목과 본문을 순서대로")을 그대로 고정한다.
- migration 무손실: `test_migration_preserves_versions_snapshots_body_bytes_and_archive`는
  CRLF·trailing 공백 포함 raw_text(`"첫 줄\r\n\r\n둘째 줄.  \n"`)의 byte 보존과
  versions·snapshot·blocks 동일·archived 유지를 단정.
- 부분 상태 fail-closed: `test_partial_hierarchy_fails_closed_without_changing_any_row`는
  "이미 생긴 장 + 고아 평면 원고" 형상에서 `ValueError("partial or invalid")`와 함께
  chapters·drafts·chapter·legacy 전부 무변경임을 단정.
- mutation — 1차 검증 무셀 V3(TXT heading `[{제목}]` 변형)이 이제 물림. 신규 V4
  (이관 `replace()`에 `archived=False` 추가)·V5(부분 상태 검사 조건 `False`화)도 각각
  무손실·fail-closed 셀을 물림. over-strict 방향(정상 이관 거부)은 기존 결정적 그룹화 셀이
  이관 성공을 단정해 커버한다. mongo 대칭 셀 2종(§3) 포함. **B2 폐쇄.**

### 3. B3 — 회귀 기준선·잔여 이관 — **폐쇄 확인**

- `tests/test_writing_accept.py`: **54 passed + 19 subtests**(1차 검증에서 6 failed였던 파일).
- 프론트 전수: **383/383, exit 0**(1차 검증에서 4 failed). App·ProjectSettingsPage mock이
  `/chapters` 형상으로 이관됐다.
- 잔여 이관 10건 실재·수습: mongo round-trip 3클래스와 start_next_unit rollback의 죽은
  `unit_kind=` 인자(`test_core_sot_mongo.py`)·`ordered_units` OU-10(`service.list_drafts` →
  `repo.list_drafts` — W3 archive-비compact 계약은 저장 원문 축에서 계속 잠금, 주석으로 사유
  명시)·`writing_scratch` `_setup` 2곳·활동 라벨표(장 5종 라벨·`draft_order_changed` 제거·
  chapter 비링크·25행 전수 주석)·auth tier 행렬 70/96·llm_call_sites·analysis·context_shared·
  phase4 smoke.
- mongo 신규 대칭 셀: `test_chapter_scene_migration_preserves_graph_and_is_a_noop_on_rerun`(mongo
  무손실+no-op)·`test_chapter_purge_keeps_sibling_chapter_and_scene`(purge victim/sibling).
- 1차 검증 H5("TestClient 시작 단계 대기" 미재현) — 본 검증 환경에서도 ASGI/TestClient 셀이
  대기 없이 정상 실행됐다(전수 4분 45초 완주). 세션 11의 정정과 일치. **B3 폐쇄.**

### 4. B4 — SoT v1.8.9 본문 정합 — **폐쇄 확인**

- Product Shell에서 "draft/chapter/scene 계층은 미확정이다" 제거 확인. grep 잔여
  "미확정이다"(`:733`)는 `analysis_completed` sync wiring 관련으로 무관.
- v1.8.9 변경이력 행: "(구현 진행)"→"(구현 완료)", "총 operation은 **96**이다" 추가,
  근거에 세션 8~10 명시. v1.8.8 행·조항의 "91"은 그 버전 당시 수치의 역사 기록으로 남음 —
  정합.
- 계층 조항 신설(`:660` 직후): metadata-only Chapter·`chapter_id` 필수·parent 범위 연속
  순열·`unit_kind`/project-wide reorder 제거·**"migration 전·부분 migration 상태의 legacy
  Draft를 공개 CRUD·Writing accept가 만나면 쓰기 전에 503"**·export(Markdown `#`/`##`·TXT
  Chapter→Scene 제목 순서)·`start_next_unit` 같은 Chapter만·활동 canonical 25·EXCLUDED 29.
- 실측 대조: OpenAPI **96 operation**(일치) · `ACTIVITY_ACTIONS` **25**·`EXCLUDED_OPERATIONS`
  **29**(일치). W0 카탈로그도 v1.8.9로 실제 갱신(unit_kind 제거·chapter_id 필수·
  chapter/scene order 쌍). **B4 폐쇄.**

### 5. B5 — 503 uncertain 잠금 — **폐쇄 확인**

- `deleteChapter`이 2단계 try로 구조 분리: 보관 단계 실패(파괴 없음)는 `purgeBusy` 해제+
  오류 표시로 재시도 유지, 파기 단계 503은 `chapterPurgeUncertain` 잠금 — 안내문
  **"다시 시도하지 말고 목록을 새로고침해 장이 남았는지 확인하세요"**·삭제 버튼 렌더
  자체 제거·제목 입력 `disabled`·취소 `disabled`·`deleteChapter` 진입 가드
  (`frontend/src/drafts/DraftList.tsx:149-189`).
- 셀 양방향: `locks the chapter purge behind uncertain on a 503`(버튼 부재·입력·취소 잠금
  단정) + `revives the chapter purge retry when only the archive step failed`(버튼·입력
  enabled 단정). "보관 단계 404는 성공 착각 금지" 셀(`does not mistake an archive-stage
  404 …`)도 구조 분리 후에도 유효하게 존재.
- 문구는 프로젝트 purge 면("다시 시도하지 말고 purge reconciler로…")과 같은 임계·구조 —
  reconciler가 없는 소유자 장 면에서 "목록 새로고침" 안내는 대칭 논리에 맞다. v1.8.8이
  정의한 "503 uncertain = 재시도 금지"(오너 ⓐ)와 정합.
- mutation M-A(uncertain 설정 제거→잠금 셀 재실패)·M-B(보관 단계에도 uncertain→재시도
  부활 셀 재실패) 모두 물림. **B5 폐쇄.**

### 6. 전수·파생물·기록물 — **주장 전부 실측 일치**

- backend 전수(test-mongo ON): **2567 passed / 4 skipped / 3021 subtests — 0 failed**
  (285.28s). 세션 11 주장과 수치 일치.
- mongo 집중: `test_core_sot_mongo` **85/85**(+신규 6 포함) ·
  `test_writing_generation_job_mongo` **14/14**.
- frontend 전수 **383/383** · `npm run build` 진입 **442.34 kB**(주장 일치).
- `schema.d.ts` 재생성 대조 **0줄 차**(openapi-typescript 7.13.0).
- `tests/test_docs_indexes.py` 13 passed · `test_activity_ui_labels` 6 passed — 검증 README
  258→259건·판정 분포 갱신이 인덱스 가드를 통과. CHANGELOG 세션 11 행·work_log 세션 11의
  수치·mutation 표가 실측과 일치.
- H3: `report_budget_measure.py`·`phase4_context_search_deployed_smoke.py` 씨드가
  chapter+scene 형상으로 갱신 — legacy 평면 draft 생성 제거 확인.

### 7. 신규 탐침 — 평면 legacy의 **export·versions 읽기 허용(200)** — 계약 침묵 (N1)

1차 검증 B1의 라이브 재현 범위(목록·단일·PATCH·DELETE·accept) 밖의 읽기 표면을 같은 방식으로
탐침한 결과:

- 순수 평면(챕터 0개) 프로젝트: `GET /export?format=txt` → **200**(평면 본문을 legacy
  heading으로 내보냄, `service.py:1001` `self._require_ordered_drafts(drafts)` legacy 분기) ·
  `GET /drafts/{did}/versions` → **200**.
- 혼합 상태(챕터 있음+평면 잔존): `GET /export` → **503**(계층 분기의 혼합 검사).
- `routers/projects.py`의 export는 503 MIGRATION face를 선언하고 주석은 *"unmigrated legacy
  data blocks it"*라고 말하지만, 실제로 막는 것은 혼합 상태뿐이고 순수 평면은 내보낸다.
- SoT v1.8.9 계층 조항은 503 대상을 "공개 CRUD·Writing accept"로 열거하며 export·versions의
  legacy 취급에 침묵한다. 즉 **목록 읽기는 막히는데 전체 내보내기는 되는 비대칭**이 계약
  미정의 상태로 존재한다.

이것은 결함이라기보다 계약 갭이다 — 어느 쪽이든 정당한 설계가 될 수 있다(평면 창구의 대피
경로 확보 vs 읽기 전면 503). 해소는 오너 판단이며 아래 조건으로 승격했다.

### Mutation 표 (검증자 8종)

| # | 방향 | 적용 diff | 파일:줄 | 결과 |
|---|---|---|---|---|
| V1r | under(B1·세션 M-C 재검증) | `if drafts: raise DraftOrderIntegrityError(…)` → `self._require_ordered_drafts(drafts)`+`return drafts` | `core_sot/service.py:750-754` | **물림** `test_legacy_drafts_fail_closed_at_the_service_boundary` |
| V2r | under(B1·세션 M-D 재검증) | `_draft_payload` 본문 첫 줄 `_require_migrated_scene(draft)` 제거 | `routers/drafts.py:89` | **물림** `SUBFAILED(endpoint='get_draft')` — 목록 subtest는 서비스층 흡수(2층 확인) |
| V3r | under(B1·세션 M-E 재검증) | accept 가드 `chapter is None or position is None or unit_kind is not None` → `and` 연결 | `writing/accept.py:118-122` | **물림** `StartNextUnitLegacyDataTest::test_append_current_targeting_legacy_draft_is_503` |
| V3 | under(B2·1차 무셀 재검증) | TXT heading `scene.title` → `f"[{scene.title}]"`(계층 분기만) | `core_sot/service.py:981` | **물림** `test_export_uses_chapter_then_scene_headings_and_derived_archive` |
| V4 | under(B2 무손실) | 이관 `replace(…)` 인자에 `archived=False` 추가 | `chapter_scene_migration.py:71-77` | **물림** `test_migration_preserves_versions_snapshots_body_bytes_and_archive` |
| V5 | under(B2 fail-closed) | `_validate_hierarchy`의 partial 검사 조건부를 `False`로 | `chapter_scene_migration.py:108-112` | **물림** `test_partial_hierarchy_fails_closed_without_changing_any_row` |
| M-A | under(B5·세션 재검증) | 파기 단계 503 catch에서 `setChapterPurgeUncertain(true)` 제거 | `DraftList.tsx:179` | **물림** `locks the chapter purge behind uncertain on a 503` |
| M-B | over(B5·세션 재검증) | 보관 단계 catch에 `setChapterPurgeUncertain(true)` 삽입 | `DraftList.tsx:160` | **물림** `revives the chapter purge retry when only the archive step failed`(외 7셀 파급) |

## Issues / Risks

### Blocking

- 없음. 1차 검증 B1~B5 전부 폐쇄를 확인했다(코드·셀·mutation·라이브 재현·문서 실측 양쪽).

### 조건 (판정 행 참조)

- **N1 — 평면 legacy 상태의 export·versions 읽기 허용이 계약에 정의돼 있지 않다.**
  순수 평면 프로젝트는 목록 읽기는 503인데 `GET /export`는 200으로 평면 본문을 내보내고
  versions도 200이다. SoT v1.8.9 계층 조항("공개 CRUD·Writing accept… 503")은 이 두 표면에
  침묵하고, export 라우터 주석("unmigrated legacy data blocks it")은 순수 평면에서 실제
  동작과 어긋난다. 오너 결정이 필요하다: (a) migration 전 대피 경로로서 읽기 허용을 SoT에
  명시 + 주석 정정, 또는 (b) export·versions도 CRUD와 같은 503 face로 정합. 어느 쪽이든
  조항 한 줄 수준에서 닫힌다.

### Hardening recommendations (비차단)

- H1(1차 검증에서 이관) — 장 unarchive 공개 경로 부재는 여전히 열려 있다(grep 0건 재확인).
  D8=A의 존립 근거 문구 정리 또는 엔드포인트 추가 여부는 오너 판단.
- N2 — accept의 `Archived` 메시지가 `"project, chapter, or draft is archived"`로 바뀌었다.
  409 detail 문구를 계약 리터럴로 취급하는 표면이라면 SoT 반영 검토(현행 관행은 셀 green으로
  문구 미고정).

## Verdict

**조건부 합격** — 1차 검증의 Blocking 5건(B1 503 fail-closed·B2 무셀 축 셀·B3 회귀 기준선
red·B4 SoT 자기모순·B5 503 uncertain 용어 불일치)은 전부 폐쇄됐음을 독립 실증했다(라이브
재현 4경로 503·mutation 8종 전부 물림·전수 수치 주장과 정확히 일치). 남은 조건: 순수 평면
legacy 상태에서 `GET /export`·versions가 200으로 동작하는 것이 SoT v1.8.9에 정의돼 있지
않다(N1) — 오너가 읽기 허용을 명시하거나 503으로 정합할 때까지. 슬라이스의 마감 조건
자체는 이 조건과 독립적으로 B1~B5 전부 닫혔다.

## Outstanding items

- disposable Mongo migration dry-run→apply→재실행 no-op 검증은 여전히 잔여다(세션 10~11
  기록 그대로 — 배포 전 과제. mongo 대칭 셀은 본 검증에서 85/85로 재실행 확인).
- 운영 Mongo는 평면 상태(migration 미적용)다 — N1 결정 전까지 평면 프로젝트의 export는
  200으로 동작한다.
- push는 되지 않았다(최종 `aafd337`).
- test-mongo는 본 검증이 기동·down으로 원상 복구했다(검증 환경 조건은 Methodology 참조).

## Reproduction

```bash
git status --short                      # clean 확인(0건)
# B1 라이브 재현(평면 legacy → 제품 엔드포인트)
python3 - <<'PY'
import asyncio, httpx, sys
sys.path.insert(0, '.'); sys.path.insert(0, 'services')
from services.application.app.main import create_app
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from tests.auth_support import authenticate
core = CoreSotService(InMemoryCoreSotRepository())
p = core.create_project(name='Legacy')
d = core.create_draft(project_id=p.id, title='평면 원고')   # chapter_id=None 형상
core.save_draft(project_id=p.id, draft_id=d.id, raw_text='본문.', idempotency_key='k1')
app = create_app(service=core); authenticate(app)
async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
        for method in ('get','patch','delete'):
            r = await getattr(c, method)(f'/projects/{p.id}/drafts' + ('' if method=='get' else f'/{d.id}'),
                                         **({'json':{"title":"x"}} if method=='patch' else {}))
            print(method, '->', r.status_code)
        r = await c.get(f'/projects/{p.id}/export', params={'format':'txt'})
        print('export ->', r.status_code)   # N1: 200(평면) — 목록은 503
asyncio.run(main())
PY
# B3·전수
docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo
python3 -m pytest tests/ -q                     # 2567 passed / 4 skipped / 3021 subtests
python3 -m pytest tests/test_core_sot_mongo.py -q                    # 85/85
python3 -m pytest tests/test_writing_accept.py -q                    # 54 passed + 19 subtests
docker compose -f docker-compose.test.yml --env-file /dev/null down test-mongo
cd frontend && npx vitest run                   # 383/383
npm run build                                   # 진입 442.34 kB
# B4 실측
python3 -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'services'); \
from services.application.app.main import create_app; \
print(len([m for p,ms in create_app().openapi()['paths'].items() for m in ms \
if m in ('get','post','put','patch','delete')]))"                  # 96
python3 -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'services'); \
from services.application.app.activity.actions import ACTIVITY_ACTIONS, EXCLUDED_OPERATIONS; \
print(len(ACTIVITY_ACTIONS), len(EXCLUDED_OPERATIONS))"            # 25 29
# schema 신선도
python3 scripts/dump_openapi.py > /tmp/openapi.json
npx openapi-typescript /tmp/openapi.json --output /tmp/schema.d.ts
diff /tmp/schema.d.ts src/api/schema.d.ts       # 0줄(공백 제외)
# mutation(V1r~M-B): clean tree에서 Edit → pytest/vitest → git checkout -- <path> → status 0건
# subtest 실패 판독은 SUBFAILED 포함/요약 행 기준
```
