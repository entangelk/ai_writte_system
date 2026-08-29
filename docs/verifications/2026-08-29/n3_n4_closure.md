# 독립 재검증 — 혼합 versions 셀·unarchive 인용 정정(N3·N4 폐쇄 보강)

## Subject metadata

- 일자: 2026-08-29
- 요청자: 오너("재검증 해줘. 보강 완료 — 2차 재검증의 조건 2건을 전부 닫았습니다")
- 검증자: Claude Code 독립 세션(2차 재검증 [`flat_legacy_escape_path_closure.md`](flat_legacy_escape_path_closure.md)과
  본 보강 구현 세션 모두와 별개)
- 대상: 2차 재검증(조건부 합격, `8f97238`)의 조건 N3·N4 폐쇄를 주장하는 커밋
  `717ed5e`(셀·문서 3파일) + `fe7bc4e`(기록 2파일). 최종 `fe7bc4e`, working tree clean(검증 내내 유지).
- 정본 계약: [`system-contract-sot.md`](../../system-contract-sot.md) v1.8.10(본문 무변 — 변경이력 행의
  인용 출처만 정정) · [`plans/chapter-scene-hierarchy-decisions.md`](../../plans/chapter-scene-hierarchy-decisions.md) D8 follow-up.

## Scope

1. N3 — 혼합 상태 legacy draft versions 200 단정 셀(`test_mixed_hierarchy_state_version_reads_stay_open`)의
   계약 고정 여부·V6b(중간 설계 방어) 재적용 시 물림.
2. N4 — "v1.5 MVP 범위 밖" 인용 교체의 출처 정확성·정정 마커·버전 무상승 판단·세션 1 로그 무결성 방침.
3. 전수·집중 수치와 변동 귀속 주장 대조.
4. 기록물 — CHANGELOG·work_log 세션 2·셀 주석의 실측 정합.

## Methodology

환경: WSL2 · python3.12 · pytest 9.0.2. **test-mongo는 검증자가
`docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo`로 기동 후 전수
실행·`down` 원상 복구**(`.env` 중립화). mutation은 clean tree 위 적용 → `git checkout -- <path>`
복원 → `git status --short` 0건 확인. 출처 검증은 SoT 변경이력 v1.5 행 원문 대조·전체 grep.

## Findings

### 1. N3 — **폐쇄 확인**

- 신규 셀 `test_mixed_hierarchy_state_version_reads_stay_open`: 혼합 형상(챕터 먼저 → 평면 draft →
  save — 2차 재검증 재현 스크립트와 동일 순서)에서 legacy draft의 versions 3경로(목록·상세·버전
  export) 200과 본문을 단정한다. SoT v1.8.10 "versions는 혼합 상태에서도 200" 문장의 행렬 칸이
  채워졌다.
- **V6b 독립 재검증(검증자가 2차 재검증과 동일 diff로 재적용)**: `list_draft_versions` 라우트에
  "챕터가 있을 때만 `_require_migrated_scene`" 방어 삽입 → **정확히 신규 셀만 재실패**
  (1 failed, 127 passed — 평면 versions 셀 green 유지). 2차 재검증에서 무셀이던 분기가 이제
  잡히며, 중간 설계(평면은 열되 혼합만 막기)와 전면 방어(V6a — 평면 versions 셀이 물림)가
  셀 단위로 구분된다. 클래스 docstring에 해당 방향 가드 문구가 문서화돼 있다.
- 셀 주석의 조립 전제("이때 drafts가 없어 create_chapter가 막지 않는다")는 코드 사실과
  정합 — `create_chapter`는 `not chapters and list_drafts(…)`일 때만 거부한다
  (`core_sot/service.py:554-557`). 이것이 2차 재검증 부수 관찰(혼합은 "챕터만 있고 drafts
  0개" 상태에서만 조립 가능)의 구조적 근거다.

### 2. N4 — **폐쇄 확인**

- 교체된 인용의 출처 정확성 실측: SoT 변경이력 **v1.5 행은 실제 2026-06-28 확정**이며
  "상태 전이(unarchive)와 … 정책은 범위 밖"을 서술한다(`system-contract-sot.md:248`).
  decisions D8·SoT v1.8.10 행의 새 문구("SoT v1.5 archive 정책(2026-06-28 확정 …)이 범위
  밖으로 둔 축")는 이 원문과 정합한다.
- SoT v1.8.10 행에 정정 마커가 남아 있다("인용 출처 정정 2026-08-29 재검증 N4 — 초판 …은
  저장소에 출처가 없는 표현이었다"). **버전 무상승 판단은 타당** — 계층 조항 본문(`:661`)은
  무변이고 변경은 행 내 서술 근거의 정정이며, 근거가 work_log 세션 2 Decisions에 명시돼 있다.
- 전체 grep: 결함 문구 "v1.5 MVP"의 잔여는 정정 마커 자체(초판 인용)·work_log 세션 1(로그
  무결성 — 세션 2 Issues에서 정정 기록)·2건의 검증 기록(그 시점 증거)·CHANGELOG 세션 2
  행(초판 인용)뿐. 정본·decisions에는 남지 않았다.

### 3. 수치 — **주장 전부 재현**

- 집중: 신규 셀 포함 `FlatLegacyEscapePathReadsTest` 4셀 + 이웃 + docs 가드 —
  **23 passed / 271 subtests**(주장 일치).
- 전수(test-mongo ON): **2571 passed / 4 skipped / 3023 subtests — 0 failed**(235.20s).
  변동 귀속 검증: 직전 측정치 `0fb24cd` 2570/4/3022(2차 재검증 실측) 대비
  **+1 passed(신규 셀, `subTest` 0개)·+1 subtest(검증자 `8f97238`의 기록 파일 등재 → docs
  루프)** — 귀속 논리가 성립한다(2차 재검증의 직전 전수는 `0fb24cd`에서 돌린 것으로
  `8f97238` 등재분을 포함하지 않았다).

### 4. 기록물 — 정합

CHANGELOG 세션 2 행(최신순 상단)·work_log 세션 2(Decisions의 버전 무상승 근거·Issues의
세션 1 결함 정정 기록·mutation 표에 적용 diff 명시) — 실측과 일치. "남은 것" 서술(migration
dry-run 잔여·혼합 조립 전제의 조항 한 줄 후보)도 변경 없음이 확인됨.

## Issues / Risks

### Blocking

- 없음.

### Hardening recommendations (비차단)

- 혼합 상태 조립 전제("챕터만 있고 drafts 0개"에서만 `create_chapter`→평면 draft가 열림)의
  조항 문서화 — 작업자가 work_log Next steps에 이미 후보로 기록했다. 본 검증도 같은 결론.

## Verdict

**합격** — 2차 재검증의 조건 2건이 모두 폐쇄됐음을 독립 실증했다. N3은 V6b와 동일한 mutation
재적용으로 정확히 신규 셀만 물림을 확인(무셀 칸 폐쇄), N4은 교체 인용의 출처가 SoT v1.5 행
원문(2026-06-28 확정)과 정합하고 정정 마커·버전 무상승 근거가 기록됐다. 전수 2571/4/3023·
집중 23/271·변동 귀속까지 주장과 정확히 일치한다. 새 조건 없음.

## Outstanding items

- migration dry-run→apply→재실행 no-op 검증 — 배포 전 잔여(변경 없음).
- push는 되지 않았다(최종 커밋은 본 검증 기록 포함 이후).

## Reproduction

```bash
git status --short                      # clean 확인(0건)
# N3 셀
python3 -m pytest "tests/test_application_api.py::FlatLegacyEscapePathReadsTest" -q   # 4 passed
# V6b 재적용: list_draft_versions try 첫 줄에
#   draft = core_sot.get_draft(project_id=project_id, draft_id=draft_id)
#   if core_sot.list_chapters(project_id=project_id): _require_migrated_scene(draft)
# 삽입 → pytest tests/test_application_api.py -q
#   → 1 failed(test_mixed_hierarchy_state_version_reads_stay_open만) → git checkout -- 복원
# 집중
python3 -m pytest "tests/test_application_api.py::FlatLegacyEscapePathReadsTest" \
  "tests/test_application_api.py::LegacyOrderedDraftMigration503Test" tests/test_docs_indexes.py -q
# 전수
docker compose -f docker-compose.test.yml --env-file /dev/null up -d test-mongo
python3 -m pytest tests/ -q             # 2571/4/3023
docker compose -f docker-compose.test.yml --env-file /dev/null down test-mongo
# N4 출처
grep -n "^| v1\.5 " docs/system-contract-sot.md        # 2026-06-28 archive 정책 행
grep -rn "v1\.5 MVP" docs/ | grep -v "정정\|2026-08-29/work_log\|verifications"   # 잔여 0건
```
