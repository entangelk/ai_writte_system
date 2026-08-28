# 독립 재검증 — 평면 legacy 대피 경로 계약화(N1·H1·N2 폐쇄 보강)

## Subject metadata

- 일자: 2026-08-29
- 요청자: 오너("보강 부분 검증해줘. 보강 완료 — 재검증의 남은 조건을 전부 닫았습니다")
- 검증자: Claude Code 독립 세션(재검증 [`chapter_scene_hierarchy_b1_b5_closure.md`](chapter_scene_hierarchy_b1_b5_closure.md)과
  본 보강 구현 세션 모두와 별개)
- 대상: 재검증(조건부 합격, `2c77a70`)의 조건 N1·비차단 H1·N2 폐쪄를 주장하는 커밋
  `9dead9e`(구현 5파일) + `0fb24cd`(기록 2파일). 최종 `0fb24cd`, working tree clean(검증 내내 유지).
- 정본 계약: [`system-contract-sot.md`](../../system-contract-sot.md) **v1.8.10**(평면 legacy
  export·versions 읽기 = migration 전 대피 경로 200·부분 migration export 503) ·
  [`plans/chapter-scene-hierarchy-decisions.md`](../../plans/chapter-scene-hierarchy-decisions.md)
  D8 follow-up(unarchive 미제공).

## Scope

1. N1 폐쇄 — SoT v1.8.10 조항·변경이력 명시 내용, export 라우터 주석 정정, 신규 셀 3종
   (`FlatLegacyEscapePathReadsTest`)의 계약 고정 여부.
2. N1 잔여 분기 — 조항이 명시한 "versions는 **혼합 상태에서도** 200"의 행렬 칸 탐색.
3. H1 — decisions D8 문구(저장 성질 vs 공개 경로)와 "project unarchive(v1.5 MVP 범위 밖)"
   인용의 출처.
4. N2 — "SoT에 archived 409 문구 리터럴 0건" 종결 근거.
5. 전수·subtest 기준선 정밀화 주장 — 현재 HEAD 전수 + 작업 전 트리(`2c77a70`) 기준선 전수 재측.
6. 기록물 — CHANGELOG·work_log·README v1.8.10 동기화·검증 인덱스 무변경 원칙.

## Methodology

환경: WSL2 · python3.12 · pytest 9.0.2. **test-mongo는 검증자가
`docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo`로 기동 후
전수를 돌리고 `down`으로 원상 복구**했다(`.env` 중립화). mutation은 clean tree 위 적용 →
`git checkout -- <path>` 복원 → 매번 `git status --short` 0건 확인(4회). 기준선 전수는
detached HEAD `2c77a70`에서 실행 후 `git checkout main` 복귀·clean 확인.

- 라이브 재현: 인메모리 저장소에 혼합 상태(챕터 1 + 평면 draft, 신규 셀과 동일한 생성 순서)를
  만들어 ASGI transport로 제품 엔드포인트 호출.
- mutation 셀-페어링: 아래 표에 실제 적용 diff 기록.

## Findings

### 1. N1 폐쇄 — **유효 확인**

- SoT v1.8.10: 계층 조항(v1.8.9)에 "정합 평면(챕터 0개) 프로젝트의 전체 export와 개별 Draft의
  versions 읽기는 migration 전 대피 경로로서 **200을 유지**한다(… 부분 migration 상태의 export는
  같은 503로 fail-closed)" 문장·변경이력 행(재검증 §7·N1 인용)·헤더 버전·갱신일·README ④ 칸
  동기화 — 내 재검증이 지목한 침묵·주석-동작 불일치를 정확히 닫는 방향(오너 ⓐ).
- export 라우터 주석이 "Mixed (partially migrated) or malformed legacy data blocks the
  export … A well-formed flat legacy project still exports"(routers/projects.py)로 실제 동작과
  일치하게 정정됐다.
- 신규 셀 3종: 평면 export 200(제목·본문 단정)·평면 versions 3경로(목록/상세/단일 export) 200
  (본문 단정)·혼합 export 503(detail 문구 단정). docstring에 under/over 양방향 문서화.
- mutation M1·M2(작업자 표) 재검증 — **둘 다 정확히 대상 셀만** 물림(각 1 failed, 126 passed).
- 라이브 재현: 혼합 상태에서 legacy draft의 versions 3경로 전부 200·export 503·`GET /drafts`
  503 — 조항·셀·동작 삼자 일치. 부수 관찰: 챕터+장면이 이미 있는 프로젝트에 대한
  `create_draft`(평면)는 서비스가 거부한다 — 혼합 형상은 "챕터만 있고 drafts 0개" 상태에서만
  만들 수 있고, 이는 migration이 챕터를 만들다 만 실제 부분 상태와 같다.

### 2. N1 잔여 분기 — "versions는 혼합 상태에서도 200" **무셀 (N3)**

SoT v1.8.10 조항·변경이력·셀 docstring은 "versions는 ordered set을 읽지 않아 **혼합 상태에서도
200**"이라고 명시한다. 그러나 셀 3종은 평면 versions·평면 export·혼합 export만 잠그고
**혼합 상태 versions 200을 잠그는 셀이 없다.** mutation으로 실증:

- V6a(현실적 과잉 방어 — versions 목록에 `_require_migrated_scene` 전면 적용): 평면 versions
  셀이 물림. 전면 확장은 감지된다.
- **V6b(혼합만 방어 — 챕터가 있을 때만 legacy draft 거부): `test_application_api.py` 127 passed
  ·인접 4파일(chapter_hierarchy·writing_accept·ordered_units·core_sot_mongo)도 green — 물리는
  셀이 없다.** SoT가 "혼합에서도 200"이라고 못박은 반대 방향(혼합 versions 503화)이 계약
  위반이라는 사실을 아무 셀도 알리지 않는다.

이 문장은 괄호 안 설명이지만 계약 서술이고, 실제 유인도 있다 — "평면은 계약상 대피 경로니
열어두되 혼합은 불완전 상태니 막는다"는 중간 설계가 SoT v1.8.10 문구를 읽은 구현자에게
자연스럽게 떠오른다. 셀 1개(혼합 상태 legacy draft versions 200 단정)로 닫힌다.

### 3. H1 — 결정 유효, **인용 출처 결함 (N4)**

- decisions D8 follow-up 3행 추가·오너 결정(2026-08-29) 기록 — 방향(미제공 유지·저장 성질
  구분)은 D8=A 원문("장 보관 복구 가능" = D8=C 대비 자식 상태 보존)과 정합하고 코드 사실
  (unarchive 엔드포인트 전 repo 0건)과 일치한다.
- **그러나 "project unarchive(v1.5 MVP 범위 밖)"의 'v1.5 MVP 범위'는 저장소 어디에도 정의돼
  있지 않다.** `docs/plans`·daily_logs·SoT 전체에서 "v1.5 MVP" 표현은 이번 추가분 외 0건.
  실제 근거는 다른 곳에 있다: 2026-06-28 work_log §115 — archive 정책 확정 시
  *"unarchive/상태전이는 차단 범위 밖('archived 동안 차단'으로 한정해 향후 unarchive 여지
  보존)"*. 이 인용이 decisions·SoT v1.8.10 변경이력에 그대로 복사돼 있다. 근거 없는 범위
  인용은 제거하거나 §115 실측 근거로 교체해야 한다(문구 1줄).

### 4. N2 — 종결 근거 사실 확인

SoT 전문에서 "is archived" 계열 문구 리터럴 등재 0건(grep 실측 재현). "detail 분기 금지" 관행과
함께 문구 미고정 종결은 선례 정합 — 재검증 N2도 "반영 필요 여부 검토" 수준의 비차단 제안이었으므로
종결 처리 자체는 문제없다.

### 5. 전수·subtest 기준선 정밀화 — **주장 전부 재현**

- 현재 HEAD(`0fb24cd`): **2570 passed / 4 skipped / 3022 subtests — 0 failed**(235.65s).
- 기준선(작업 전 `2c77a70`, 검증자가 detached HEAD 재측): **2567 passed / 4 skipped /
  3022 subtests** — 작업자의 기준선 3022 주장을 그대로 재현. 슬라이스 영향 **+3 passed·
  subtest ±0** 확정(신규 셀 3종은 `subTest` 호출 0개 — 코드 구조상 자명).
- 나의 1차 재검증(같은 `2c77a70`)이 본 3021은 재현되지 않았다 — 동일 커밋·동일 절차에서도
  subtest 총계가 1 차이로 변동하는 측정치였다. 작업자의 "재검증 세션의 측정 시점 조건 차이"
  판단이 옳았고, 작업 전 트리 재측으로 슬라이스 영향을 분리한 방법도 정확했다. 원인 규명
  (어떤 셀의 조건부 subTest가 변동을 만드는가)은 본 검증 범위 밖으로 둔다 — 변동 폭 1,
  재현 불가.
- 집중 재실행: 신규 셀 + 이웃 + docs 가드 **22 passed / 270 subtests**(주장 일치).

### 6. 기록물 — 정합

CHANGELOG 2026-08-29 행(최신순 상단)·work_log Session 1(결정 근거·mutation 표·Issues에
subtest 정밀화 과정) — 실측과 일치. 검증 인덱스는 "그 시점 기록 원칙"에 따라 무변경(탈락 없음,
본 검증 기록 등재분은 아래 카운터에 반영). HANDOFF 무갱신 판단 검증: grep 매치 11건은 전부
타 슬라이스의 H1/H2 관측 번호·과거 마감 메모 맥락으로 이번 결정과 무관 — 판단 유지.

### Mutation 표 (검증자 4종)

| # | 방향 | 적용 diff | 파일:줄 | 결과 |
|---|---|---|---|---|
| M1r | under(작업자 M1 재검증) | `export_project` legacy 분기 진입부에 `if drafts: raise DraftOrderIntegrityError("scene hierarchy migration is required")` 삽입 | `core_sot/service.py:1002`(`_require_ordered_drafts` 직전) | **물림** `test_flat_legacy_project_export_is_the_migration_escape_path`(1 failed만) |
| M2r | over(작업자 M2 재검증) | export 혼합 검사 `if any(` → `if False and any(`(export 지점만 — `list_drafts` 동형 검사 무변) | `core_sot/service.py:942` | **물림** `test_mixed_hierarchy_state_export_still_fails_closed`(1 failed만) |
| V6a | over(전면 방어 확장) | `list_draft_versions` 첫 줄에 `_require_migrated_scene(core_sot.get_draft(…))` 삽입 | `routers/drafts.py:480` | **물림** `test_flat_legacy_draft_version_reads_stay_open`(전면 확장은 감지) |
| V6b | over(혼합만 방어) | `list_draft_versions`에서 `if core_sot.list_chapters(…): _require_migrated_scene(draft)` — 챕터 없는 평면은 통과 | `routers/drafts.py:480` | **무셀** — `test_application_api.py` 127 passed·인접 4파일 green. "혼합 versions 200" 분기 빈 칸 실증(N3) |

## Issues / Risks

### Blocking

- 없음.

### 조건 (판정 행 참조)

- **N3 — "versions는 혼합 상태에서도 200" 분기 무셀.** SoT v1.8.10이 명시한 문장의 반대
  방향(혼합 상태 legacy draft의 versions 503화)이 어떤 셀도 잡지 못한다(V6b 실증). 혼합
  형상에서 legacy draft의 versions 읽기 200을 단정하는 셀 1개로 닫힌다.
- **N4 — "v1.5 MVP 범위 밖" 인용의 출처 부재.** "project unarchive(v1.5 MVP 범위 밖)"이
  decisions D8·SoT v1.8.10 변경이력에 실려 있으나 해당 범위를 정의하는 문서가 저장소에
  없다(전체 grep 0건). 실제 근거는 2026-06-28 work_log §115("unarchive 여지 보존")이므로
  문구를 교체하거나 삭제하는 정정 1줄로 닫힌다.

### Hardening recommendations (비차단)

- 부수 관찰: 혼합 상태 생성 경로가 "챕터만 있고 drafts 0개"일 때만 열려 있는데, 이 전제를
  설명하는 문서는 없다(셀 주석에만 암시). 다음 슬라이스가 혼합 상태를 다룬다면 조항 한 줄
  후보.

## Verdict

**조건부 합격** — N1의 계약 명시·주석 정정·셀 3종은 폐쇄됐음을 실증했다(mutation M1·M2 재검증
모두 정확히 대상 셀만 물림, 전수 2570/4/3022·기준선 3022 재현, subtest 정밀화 주장도 재측으로
확정). 남은 조건: ① SoT v1.8.10이 명시한 "versions는 혼합 상태에서도 200" 분기에 셀이 없다(N3,
V6b 무셀 실증) ② "v1.5 MVP 범위 밖" 인용의 근거가 저장소에 없다(N4). 둘 다 셀 1개·문구 1줄
수준이다.

## Outstanding items

- migration dry-run→apply→재실행 no-op 검증 — 배포 전 잔여(변경 없음, 세션 10~11 기록 그대로).
- migration apply 완료 후 평면 대피 경로 분기 자연 소멸 — SoT v1.8.10 조항 폐기 검토는 그
  시점 과제(작업자 기록과 동일).
- push는 되지 않았다(최종 커밋은 본 검증 기록 포함 `2c77a70..` 이후).

## Reproduction

```bash
git status --short                      # clean 확인(0건)
# 혼합 상태 라이브 재현(신규 셀과 동일 생성 순서)
python3 - <<'PY'
import asyncio, httpx, sys
sys.path.insert(0, '.'); sys.path.insert(0, 'services')
from services.application.app.main import create_app
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from tests.auth_support import authenticate
core = CoreSotService(InMemoryCoreSotRepository())
p = core.create_project(name='혼합')
core.create_chapter(project_id=p.id, title='1장')      # 챕터만 먼저
legacy = core.create_draft(project_id=p.id, title='고아 평면')
core.save_draft(project_id=p.id, draft_id=legacy.id, raw_text='본문.', idempotency_key='k1')
app = create_app(service=core); authenticate(app)
async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
        r = await c.get(f'/projects/{p.id}/drafts/{legacy.id}/versions'); print('혼합 versions ->', r.status_code)  # 200(N3 미잠금 분기)
        r = await c.get(f'/projects/{p.id}/export'); print('혼합 export ->', r.status_code)                        # 503
asyncio.run(main())
PY
# 집중
python3 -m pytest "tests/test_application_api.py::FlatLegacyEscapePathReadsTest" \
  "tests/test_application_api.py::LegacyOrderedDraftMigration503Test" tests/test_docs_indexes.py -q
# 전수·기준선(test-mongo ON)
docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo
python3 -m pytest tests/ -q        # HEAD(0fb24cd): 2570/4/3022
git checkout 2c77a70 && python3 -m pytest tests/ -q   # 기준선: 2567/4/3022
git checkout main
docker compose -f docker-compose.test.yml --env-file /dev/null down test-mongo
# mutation(M1r·M2r·V6a·V6b): clean tree에서 Edit → pytest → git checkout -- <path> → status 0건
#   V6b는 "물리는 셀 없음(127 passed)"이 올바른 판독 — SUBFAILED 아님을 summary 행으로 확인
```
