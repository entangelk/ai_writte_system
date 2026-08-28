# 독립 검증 — 장→장면 계층화 슬라이스

## Subject metadata

- 일자: 2026-08-28
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: Claude Code 독립 세션(구현 세션과 별개)
- 대상: 커밋 `2094483..258c719` 중 구현 4커밋(`65348ab` 정본·migration → `5419267` Chapter API →
  `e735caa` 공개 계약·UI → `dca18f6` purge 404 성공 처리)과 그 기록물. 최종 `258c719`, working tree clean.
- 정본 계약: [`plans/chapter-scene-hierarchy-decisions.md`](../../plans/chapter-scene-hierarchy-decisions.md)
  "확정 구현 계약" 절(D1=A·D2=A·D3=A·D4=A·D5=A·D6=A·D7=B·D8=A) ·
  [`system-contract-sot.md`](../../system-contract-sot.md) v1.8.9(단, 본문 미갱신 — B4) ·
  [`plans/writing-workspace-v2-w0-contract.md`](../../plans/writing-workspace-v2-w0-contract.md) 상단
  supersession 배너(2026-08-28).

## Scope

1. 계약 문서 자기 정합성 — SoT 본문 vs 변경이력 vs 브리프 vs W0.
2. 공개 API·Core SOT 서비스·저장소 구현의 계약 대조(chapter CRUD·reorder·scene 생성·flat 목록).
3. migration 결정성·no-op·fail-closed·무손실.
4. export 계층(MD/TXT/ZIP)과 파생 보관 가시성.
5. Writing `start_next_unit` 같은 장 다음 Scene 제한.
6. Chapter cascade purge 가드 순서(보관 선행 409 → active 잡 write-0/409 → 파생물 → core).
7. 프론트 UI 계약(정확한 제목 확인·purge-stage 404 성공/보관 단계 404 거부·503 취급).
8. 회귀 셀 심사 — 테스트 코드 자체가 계약을 고정하는지(경계 행렬 빈 칸 탐색).
9. 파생물 신선도 — `frontend/src/api/schema.d.ts` 재생성 대조.
10. 기록물 정합(CHANGELOG·HANDOFF·work_log·검증 주장 수치).

## Methodology

환경: WSL2, python3.12 · pytest 9.0.2 · fastapi `~/.local`(로컬 설치) · docker 스택 기동 중(app·admin·worker·frontend; **test-mongo 무구동** — mongo 셀은 미실행). mutation은 clean tree 위 적용 → `git checkout -- <path>` 복원 → `git status --short` 0건 확인(3회 모두). 계층화 이전 비교는 throwaway worktree(`e735caa^`)에서 실행 후 제거.

- 테스트 재실행: `python3 -m pytest <files> -q`(아래 Reproduction 전량).
- OpenAPI 실측: `create_app().openapi()`로 operation 수 직접 집계.
- schema 신선도: `scripts/dump_openapi.py` + `openapi-typescript` 재생성 → `diff`(공백 제외 0줄).
- 무셀 탐침(mutation): 아래 표. 셀-페어링과 실제 적용 diff를 함께 기록.
- 라이브 재현: 인메모리 저장소에 평면 legacy 프로젝트(`create_draft` = 현재 운영 데이터 형상)를
  만들어 ASGI transport로 제품 엔드포인트 직접 호출.

## Findings

### 1. 계약 문서 자기 정합성 — **모순 존재(B4)**

- SoT Product Shell 본문(`system-contract-sot.md:660`)이 아직
  **"draft/chapter/scene 계층은 미확정이다"**라고 말한다. 같은 문서 변경이력 v1.8.9(`:36`)는
  확정·시행을 말한다. 정본이 자기모순 상태다.
- v1.8.9 행이 "(구현 진행)"으로 끝나 있는데 구현은 완료됐고(세션 9~10), SoT 본문에는 v1.8.9
  계층 조항·운용 수 갱신이 전혀 없다(Product Shell의 운용 수는 v1.8.8의 "총 91" 그대로).
  실측 operation 수는 **96**(아래 2)이고 HANDOFF(`HANDOFF.md:34`)는 "96 … 실측"으로 이미 갱신돼
  있다 — SoT만 낡았다. W0는 supersession 배너로 정상 처리됐다(대조적).
- 브리프 자체(선택지·확정 계약)는 내부 정합. `docs/plans` 인덱스 등재·문서 인덱스 테스트 13/268도 재현.

### 2. 공개 API·서비스 — 계약 부합(운용 수 주장과 실측 불일치만)

- 엔드포인트 전형 대조: `GET/POST /chapters`·`archive`·`purge`·`chapter-order`·`scene-order` 전부
  존재, project-wide `draft-order`는 앱 전역에서 제거 확인. `POST /drafts`는
  `create_scene(chapter_id=…)`(`routers/drafts.py:552`)로 전환, `CreateDraftRequest{title,chapter_id}`
  extra 금지(`api/models.py:688-693`). OpenAPI 실측 **96 operation**(v1.8.8 91 → 96, HANDOFF 주장과
  일치 · SoT 본문 91은 불일치).
- 순서 불변식: 장 `1..C`·장면 `1..S` 연속 순열 검증, 교차 장 reorder 거부(완전 순열 검증),
  `list_drafts` flat 결과가 장 position→장면 position 순(`core_sot/service.py:726-751`) — 계약 대로.
- `start_next_unit`: 현재 장면과 같은 장에서만 시프트·생성, legacy draft는
  `DraftOrderIntegrityError`(`service.py:1116-1141`) — D6=A 부합. `NextUnit{title,goal}`에서
  `unit_kind` 제거 확인.
- activity 분류표에 chapter 5종 action 등재(`activity/actions.py:70-82`) — 전수 가드 통과 재현.
- `schema.d.ts` 재생성 대조 **0줄 차**. `unit_kind` 잔존: 내부 legacy 축(migration 입력·몽고 문서)만.

### 3. migration — 논리는 계약 부합, 회귀 잠금 불완전(B2)

- `ChapterSceneHierarchyMigration`(`core_sot/chapter_scene_migration.py`): 결정성(평면 순서대로
  Chapter 오픈, chapter Draft→동일 제목 Chapter+`본문` 첫 장면, 선행 장면 없는 묶음→`미분류`),
  재실행 no-op(계층 있으면 `_validate_hierarchy`만), 부분 상태 ValueError fail-closed,
  `replace_hierarchy` 원자 교체(인메모리 롤백·mongo transaction) — 브리프 확정 계약과 일치.
- **그러나 무손실 축이 무셀이다.** 브리프 follow-up은 "기존 ID·version·snapshot·본문 byte 보존을
  **양방향 회귀로 잠근다**"고 못박았는데, `test_chapter_hierarchy.py`의 migration fixture는
  version/snapshot이 아예 없는 draft만 만들고 ID·제목·그룹만 단정한다. archived 포함 이관·부분
  상태 fail-closed도 셀이 없다(ID·no-op·결정적 그룹화만 잠김).
- Mongo 저장소의 chapter 경로(`replace_hierarchy` 트랜잭션·index 교체·`purge_chapter` 등
  `mongo_repository.py` +146줄)는 `test_core_sot_mongo.py`에 **chapter 참조 0건** — 인메모리↔mongo
  대칭 셀 없음(구현자가 disposable Mongo 수작업 검증을 배포 전 과제로 남긴 것은 사실이나, 그
  수작업은 migration 경로만 부분 커버하고 저장소 대칭 회귀를 대신하지 못한다).

### 4. export — MD/ZIP는 잠김, **TXT는 무셀(B2)**

- MD `# 장`/`## 장면`, 보관 장 기본 제외·`include_archived` 포함, 자식 `archived` 불변
  (`service.py:946-988` + `test_export_uses_chapter_then_scene_headings_and_derived_archive`) — D8=A 부합.
- ZIP 파일명 두 position 프리픽스(`01-01-1장.md`) 충돌 방지 — `ProjectExportPanel.test.tsx:210-213` 잠김.
- **TXT 계층 heading은 어떤 셀도 안 잠근다.** mutation M3(계층 branch의 TXT heading을
  `[{제목}]`으로 변형)에 `test_chapter_hierarchy`+`test_ordered_units` 전부 통과(24 passed).
  브리프 확정 계약 "TXT는 장 제목 뒤 장면 제목과 본문을 순서대로" 분기의 빈 행렬 칸.

### 5·6. purge·UI — 가드 순서 계약 부합, 503 취급은 용어와 불일치(B5)

- 라우터 가드 순서(`routers/drafts.py:207-257`): 존재 404 → 보관 선행 409 → 자식 active
  (PENDING/RUNNING) 잡 write-0/409 → 자식별 scratch·종료 잡 정리 → `purge_chapter` 원자 파기 →
  activity 행. D7=B 그대로. 종료 잡 정리·404 write-0 셀도 재실행 통과.
- 프론트: 정확한 제목 확인(`DraftList.tsx:149,223`)·purge 요청 이후 404만 성공(`:152-161`, 보관
  단계 404는 거부 — 양방향 셀 존재·통과) — dca18f6 주장 그대로.
- **503 취급이 용어 정의와 어긋난다.** SoT v1.8.8은 "uncertain 잠금"을 오너 결정 ⓐ로
  정의했다 — *"파기 단계 503은 uncertain 잠금(재시도 금지·reconciler 안내)… 보관 단계 실패만
  재시도 허용"*. v1.8.9와 브리프 D7가 Chapter purge에 같은 리터럴("503 uncertain 잠금")을 쓰는데,
  구현은 확인창 유지 + 안내문 **"목록을 새로 확인한 뒤 다시 시도하세요"** + 재시도 버튼 그대로
  활성(`DraftList.tsx:160-172`)이다. 503 셀(`keeps the confirmation open…`)은 안내문 존재만 단정하고
  잠금을 단정하지 않는다. 같은 앱의 프로젝트 purge(관리자·소유자 면)는 재시도 제거·입력 잠금이다.
  약한 해석이 의도면 SoT/브리프 문구 수정이, 강한 해석이 의도면 UI 수정이 필요하다 — **오너 판단 거리**.

### 7. 회귀 기준선 — **HEAD에서 red(B1·B3)**

구현자가 **수정한 파일을 스스로 실행하지 않았다**:

- `tests/test_writing_accept.py`(e735caa에서 ±74줄 수정) — **6셀 실패**. 원인: legacy
  draft(`chapter_id=None`)의 append_current accept에서 응답 봉투 `saved.chapter_id`가 `None`인데
  `AcceptedSavePayload.chapter_id: str`(`writing/http_models.py:156`)이 필수 문자열이라
  `ResponseValidationError` → 500. worktree `e735caa^`에서는 53 passed — **이 슬라이스가 만든 회귀**.
- 프론트 전수 — **4셀 실패**(`App.test.tsx` 3, `ProjectSettingsPage.test.tsx` 1). 원인: 컴포넌트가
  `/chapters`를 읽는데 mock이 평면 `/drafts` 읽는 목만 제공(테스트측 미갱신; 제품 결함은 아님).
  다만 세션 7 기준선 "프론트 388/388"이 깨진 채며, 전수를 돌리지 않아 놓쳤다.
- 보고된 "backend 집중 60 passed"는 실존한다 — 단 묶음 구성이
  chapter_hierarchy(13)+activity_actions(7)+activity_api(18)+admin_surface(11)+ordered_units(11)=60으로,
  **수정한 writing_accept가 빠진 선택 조합**이었다. "generation/Chapter 51"의 인메모리 분(38)도
  재현(mongo 14분은 test-mongo 무구동으로 미실행).

### 8. 라이브 재현 — **migration 전 상태(현 운영 데이터 형상)에서 제품 경로 500(B1)**

운영 Mongo는 아직 평면(ordered-unit) 상태다(migration 미적용 — 구현자 기록과 동일). 그 상태의
프로젝트를 인메모리로 만들어 호출하면:

- `GET /projects/{pid}/drafts` → `_draft_payload`의 `assert draft.chapter_id is not None`
  (`routers/drafts.py:70`) **AssertionError → 500**. `GET/PATCH/DELETE /drafts/{did}`도 같은 payload
  함수를 쓰므로 모두 500.
- `POST /writing/accept`(append_current) → 위 7의 `ResponseValidationError` → 500.

엔드포인트는 이 상태를 위해 503 "migration" 응답을 **선언**해 두었다(`_ERRORS_404_MIGRATION`,
`DraftOrderIntegrityError` → 503 매핑) — 즉 계약상 얼굴은 503인데, 서비스가 평면 데이터를
정상 반환하는 바람에(`service.py:750-751` legacy branch) 직렬화 층에서 500으로 터진다.
migration이 성공하는 배포 순서라면 평면 상태는 잠시지만, **migration이 실패한 프로젝트는
영구히 500**(503이 아님)이고 배포-적용 사이 창구에 모든 기존 프로젝트가 500이다.

### 9·10. 파생물·기록물

- `schema.d.ts` 재생성 일치, `unit_kind` 0건, `/draft-order` 부재 — 주장 재현.
- CHANGELOG 세션 8~10 행·HANDOFF ⓪-b(293-298)·work_log 세션 9~10 — 수치·서술 실측과 일치
  (HANDOFF op 96 실측 포함). mutation 표 4종 중 M1(chapter_id optional) 재검증 — 주장 셀 그대로
  재실패. 나머지 3종은 셀 존재 확인(실행 미반복). mypy "154 files" 주장은 미재검(저위험).
- 정직 기록 확인: migration dry-run 미실행·ASGI 전수 재실행 남음·push 안 함·최종 `258c719` —
  전부 사실. 단 "TestClient 시작 단계 대기" 주장은 이 머신에서 재현되지 않았다(accept 파일은
  8.4초 만에 실행·6실패) — 환경 의존 주장으로 기록 필요.

### Mutation 표 (검증자 3종)

| # | 방향 | 적용 diff | 파일:줄 | 결과 |
|---|---|---|---|---|
| V1 | under(구현자 주장 재검증) | `chapter_id: NonBlankName` → `NonBlankName \| None = None` | `api/models.py:693` | **물림** `ChapterHierarchyApiTest.test_scene_create_contract_requires_parent_and_rejects_unit_kind`(주장 셀 동일) |
| V2 | under(무셀 탐침) | `open_chapter("미분류")` → `open_chapter("기타")` | `chapter_scene_migration.py:68` | **물림** `ChapterHierarchyMigrationTest.test_migration_preserves_draft_ids_and_builds_deterministic_groups` |
| V3 | under(무셀 탐침) | TXT heading `scene.title` → `f"[{scene.title}]"`(계층 branch만) | `core_sot/service.py:978-981` | **무셀** — 24 passed. TXT 계약 분기가 빈 행렬 칸임을 입증 |

## Issues / Risks

### Blocking

1. **B1 — fail-closed 503 계약 위반(라이브 500).** migration 전 평면 상태(현 운영 데이터)에서
   `GET /drafts`·`GET/PATCH/DELETE /drafts/{did}`·`POST /writing/accept`가 500
   (`routers/drafts.py:70,93` assert · `writing/http_models.py:156` 필수 str). 엔드포인트가 선언한
   503 "migration" 얼굴과 모순. 수정 방향(계약 정합): 서비스/라우터에서 `chapter_id is None`
   draft를 만나면 `DraftOrderIntegrityError`로 503 face(legacy 반환 분기 제거 또는 accept 경로
   사전 검사) — `start_next_unit`이 이미 그렇게 한다(`service.py:1140-1141`).
2. **B2 — 계약 요구 회귀 부재(빈 행렬 칸).** ① TXT 계층 export heading(V3 무셀 실증).
   ② migration 무손실 축(version/snapshot/본문 byte·archived 포함·부분 상태 fail-closed — 브리프
   follow-up이 "양방향 회귀로 잠근다" 명시).
3. **B3 — 슬라이스 회귀 기준선 red.** `test_writing_accept.py` 6셀(e735caa 회귀, 이전 커밋
   green 실증)·프론트 전수 4셀(mock 미갱신). 수정한 파일을 실행하지 않은 채 "집중 회귀"로
   마감했고 전수를 돌리지 않아 파손이 기록되지 않았다.
4. **B4 — SoT 정본 자기모순·미갱신.** 본문 "draft/chapter/scene 계층은 미확정이다"(`:660`) vs
   v1.8.9 확정·구현, 운용 수 91(실측 96), "(구현 진행)" 잔존. 변경 규칙 2("조용히 선택하지
   않는다")·문서 우선순위 위반 상태.
5. **B5 — "503 uncertain 잠금" 용어와 구현 불일치.** v1.8.8 정의(재시도 금지, 오너 ⓐ) 대비
   장 purge UI의 "다시 시도하세요"+재시도 버튼 활성. 어느 쪽이든 SoT/브리프 또는 UI 중 하나를
   고쳐 정합시켜야 한다(오너 판단).

### Hardening recommendations (비차단)

- H1 — 장 unarchive 경로 부재. D8=A의 존립 근거("장 보관 복구가 가능")가 공개 API로 도달
  불가능하다(프론트에도 없음). 데이터는 보존되므로 후속 엔드포인트로 열 수 있으나, 없다면
  "보관=파기 전 단계"가 되므로 브리프 근거 문구 정리 권고.
- H2 — mongo chapter 저장소 경로 무셀(위 3). disposable Mongo 검증과 별개로 대칭 회귀 권고.
- H3 — `scripts/report_budget_measure.py:223`이 legacy `create_draft`로 chapter 없는 draft를
  만든다. 계층화 런타임에서 이 스크립트가 만든 데이터는 B1의 500 형상이다(씨드 후 accept는
  안 하지만 목록 읽기가 깨진다).
- H4 — 보관된 장의 scene reorder가 409로 거부된다(`service.py:808-809`). 유추 가능한 설계지만
  명세 문구가 없다(spec-silent-but-enforced) — SoT 갱신 시 한 줄 등재 권고.
- H5 — "이 머신 TestClient 대기" 주장은 본 검증 환경에서 재현되지 않았다(accept 전체 8.4초
  실행). 환경 의존 주장이므로 work_log에 환경 조건을 함께 기록할 것.

## Verdict

**불합격** — migration 전 저장 상태(현 운영 데이터 형상)에서 제품 읽기·쓰기 경로가 500으로
실패해 엔드포인트가 선언한 fail-closed 503 계약을 위반했고(B1), 브리프가 "양방향 회귀로
잠근다" 못박은 migration 무손실 축과 TXT 계층 export에 셀이 없으며(B2), 슬라이스가 수정한
회귀 파일이 red인 채 마감됐다(B3). 배포(migration 적용 포함)는 B1~B3 폐쇄 전 불가.

정확히 한 줄 덧붙인다: 슬라이스의 대부분(모델·API·순서 불변식·purge 가드·UI 404/제목 확인·
schema 파생·정직한 잔여 과제 기록)은 검증을 통과했고, V1 재검증으로 구현자 mutation 주장도
사실이었다. 결함은 "평면 상태 잔여 기간"과 "실행하지 않은 파일"에 집중돼 있다 — 폐쇄 난이도는
낮다(B1은 503 매핑 수준, B2는 셀 2~3개, B3는 mock·셀 수습).

## Outstanding items

- disposable Mongo migration dry-run→apply→no-op 검증 미실행(구현자 기록 그대로, B2와 함께 셀화 권고).
- ASGI/TestClient 전수 재실행 — 본 검증 환경에서는 accept 파일이 실행돼 6실패가 그대로 재검증됨.
- B5(503 취급)·H1(unarchive 부재)은 오너 판단 필요.
- push는 되지 않았다(최종 커밋 `258c719`, 본 검증 기록 커밋 제외).

## Reproduction

```bash
git status --short                      # clean 확인(0건)
# B1 라이브 재현(평면 legacy 프로젝트 → 제품 엔드포인트)
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
        r = await c.get(f'/projects/{p.id}/drafts'); print('GET /drafts ->', r.status_code)
asyncio.run(main())                     # → AssertionError(drafts.py:70) = 500
PY
# B1·B3 회귀 red
python3 -m pytest tests/test_writing_accept.py -q                # 6 failed
git worktree add /tmp/pre e735caa^ && cd /tmp/pre && \
python3 -m pytest tests/test_writing_accept.py -q                # 53 passed(회귀 입증)
cd - && git worktree remove /tmp/pre
cd frontend && npx vitest run                                    # 4 failed(App 3·Settings 1)
cd .. && python3 -m pytest tests/test_docs_indexes.py -q         # 13 passed(재현)
# B4 실측
python3 -c "from services.application.app.main import create_app; \
print(len([m for p,ms in create_app().openapi()['paths'].items() for m in ms \
if m in ('get','post','put','patch','delete')]))"                # 96(SoT 본문 91)
# mutation(V1~V3): clean tree에서 Edit → pytest → git checkout -- <path> → status 0건
```
