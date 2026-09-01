# final-save 재검증 조건 폐쇄(67e8609) 3차 재검증

## Subject metadata

- 날짜: 2026-09-01
- 요청자: 오너("다시 한번 검증해줘" — 재검증 조건 R1·R2·B4 보강 커밋 `67e8609`의 폐쇄 확인)
- 검증자: Claude Code 세션(1·2차 재검증과 같은 세션 — 구현은 별도 세션)
- 대상: `67e8609` — [`final_save_hardening_recheck.md`](final_save_hardening_recheck.md)의 잔여 조건 R1(semantic 토큰)·R2(수동 분석 후 상태 갱신)·B4(프로브의 suite 편입) 폐쇄 주장
- 정본: [`docs/plans/final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)(D1~D4 Resolved · **D5 대기**)
- 검증 소스: HEAD `67e8609`, 트리 clean(변이 전·후 `git status --short` 확인)
- 환경: 동일. 구현자 세션은 30초 상한으로 vitest/전수 종료값을 못 잼(work_log 세션 7) — 이 기록이 그 실측을 제공

## Scope

1. R1·R2·B4 폐쇄 실측(코드 + 해당 suite + 변이 3종)
2. reloadLatest 변경의 파급(채택 흐름 등 인접 셀)·토큰 정합성 위성 표
3. D5 대기 상태 확인(502 선언 유지 여부)
4. 백엔드·프런트 전수

## Methodology

- 프로토콜 동일(요약 count 줄 판독, 변이마다 복원 확인). 변이는 이번 라운드의 새 잠금이 각자 물리는지를 기준으로 선택.

## Findings

### 1. R1·B4 폐쇄 — 실측·변이 확인

- **R1 ✓** — `:root` 상태 그룹에 `--status-danger: var(--danger-600)` semantic 토큰을 정의하고 `.status-attention`이 그것을 탄다. `designTokens.test.ts` **5 passed**(semantic 라우팅 셀 포함). 변이(사용처를 `--danger-600`으로 되돌림) → semantic 셀 **1 failed 재현**.
- **B4 ✓** — `tests/test_final_save_analysis.py`가 프로브(docs/verifications 경유 importlib)를 pytest 셀로 편입, **1 passed**(S1~S13 41단정 내장). 검증 문서의 프로브 경로·링크는 그대로(기존 기록 Reproduction 불변). 변이(H1 재조회 제거) → 셀 **FAILED 재실패** — 수집 배선까지 실제로 물린다. 프로브가 suite 안으로 들어왔으므로 전수 green bar가 이제 finalize 계약 위반을 안다.

### 2. R2 — 계약 시나리오는 폐쇄, 대신 인접 3셀 파열(신규 조건 R3)

- **계약 시나리오 ✓** — 수동 분석 `complete` 시 `reloadLatest()`가 `getDraft`까지 다시 읽어 `draft.analysis_*`를 갱신(`DraftEditor.tsx` reloadLatest·onStatusChange). 상태 바 pin 셀("필요"→저장·분석→"완료" 2단) green. 변이(reload-on-complete 제거) → 해당 셀 **재실패**.
- 구조 안전성 2건 확인: ①분석 **실패** 경로는 catch로 흘러 reload가 없다 → "분석 필요" 유지(계약 부합). ②분석 뒤 **일반 저장**은 `latestSnapshotId`(로컬 versions)만 갱신돼도 `analysis_snapshot_id !== latestSnapshotId` 비교가 attention을 참으로 만든다 → stale draft 필드로도 "분석 필요"로 전환된다.
- **R3(신규 조건, 차단) — 채택 흐름 3셀 red.** `reloadLatest`가 **모든** reload에서 `getDraft`를 추가로 부르게 되면서, 채택(Writing·PAD·discard-proceed) 3셀의 fetch 목 순서가 어긋나 **3 failed / 84 passed**(파열 관측: 채택 후 본문이 "기존."에 머무름). 실제 동작 변경(요청 1건 추가)에 따른 목 미갱신이다. 폐쇄는 두 방향 다 가능하다 — 3셀의 목에 `getDraft` 응답 추가, 또는 draft 재조회를 수동 분석 완료 경로에만 국한. 구현자 환경이 vitest를 못 돌려 미발견이었고(work_log 세션 7 명시), 이 기록이 첫 실측이다.

### 3. R4(신규 조건) — R1의 semantic 토큰이 브리프 정합성 가드를 깨뜨린다

`--status-danger`를 `:root`에 정의했지만 디자인 시스템 브리프의 semantic 표
(`docs/plans/10-frontend-design-system-decisions.md` ~217-232)에는 행이 없다.
`PaletteProvenanceTest::test_the_brief_semantic_table_matches_the_stylesheet`(브리프 표 ↔
`:root` 1:1 가드)가 **red — 단독 재실행에서도 실패**. 폐쇄는 브리프 표에 행 1개 추가
(예: `--status-danger | danger-600 | 상태 바 주의 문구`). R1과 같은 결함 계열(위성 표 갱신
누락)이 구현자 환경 제약(30초 상한)으로 또 놓친 것 — 백엔드 전수가 잡았다.

### 4. D5 — 미확정·의도적 보류 확인

finalize 스펙에 502 선언이 **유지**돼 있다(직독). 구현자가 "오너 선택 전에는 제거하지 않는다"고 명시한 것과 일치 — 보류는 의도적이다. A 확정 시 502 제거가 D5 폐쇄 슬라이스에 포함되어야 한다.

## Issues / Risks

### Blocking (조건)

1. **R3** — reloadLatest의 `getDraft` 추가로 채택 흐름 3셀 red(목 갱신 또는 호출 국한으로 폐쇄).
2. **R4** — `--status-danger`가 브리프 semantic 표에 미등재(`PaletteProvenanceTest` red, 단독 재현). 브리프 표에 행 추가로 폐쇄.
3. **D5 미확정** — A(200+`analysis_error`, 권고) / B(502 partial). 확정 시 HTTP 계약·셀 고정 + (A면) 502 선언 제거.

### Hardening (비차단)

- `reloadLatest`가 매 reload마다 요청 1건을 더 보낸다(채택·수동 분석 완료 등). 로컬 1인 단계에서 감수 가능하나 호출 국한이 요청 수를 줄인다(R3 폐쇄 방향과 동일선상).
- SoT v1.8.13 변경이력·CHANGELOG 반영은 여전히 잔여(1·2차 기록에서 동일 지적).

## 전수 (이 세션 실측)

- 프런트 전수: **3 failed / 382 passed (385), exit 1, 실패 파일 1개** — 전부 `DraftEditor.test.tsx`의 채택 흐름 3셀(R3). designTokens green(R1 폐쇄 전수 확인), App 등 나머지 green(2차의 부하 플레이크도 이번엔 없음). 슬라이스 귀속 실패는 R3 정확히 3셀.
- 백엔드 전수: **9 failed / 2666 passed / 1 skipped / 3083 subtests**(37:49) — 내역: `test_docs_indexes` 7(이 기록 미등재 — 등재 후 green) + **`PaletteProvenanceTest` 1(R4, 단독 재실행에서도 실패)** + `AdmissionSerialisationLiveMongoTest` 1(단독 재실행 3 passed — 프런트 전수 동시실행 부하 플레이크, 비귀속). 제품 셀 슬라이스 귀속 실패는 R4 1건.

## Verdict

**조건부 합격** — 조건: R3(채택 흐름 3셀 red — reloadLatest의 getDraft 추가 후속)·R4(브리프 semantic 표에 `--status-danger` 미등재) 폐쇄 + D5 확정(502 선언 정리 포함). B4는 실측 폐쇄, R1·R2는 계약 시나리오 폐쇄(변이 잠금)이되 각각의 구현 변경이 위성 표·인접 셀을 하나씩 깨뜨린 것이 잔여 전부다.

## Outstanding items

- D5 오너 결정 → A 채택 시 502 선언 제거·HTTP 계약 고정·회귀 셀 문구 확정.
- R3·R4 폐쇄 후 4차(최종) 재검증 — 새 pytest 셀·프런트 전수·백엔드 전수 기대치 재계산.
- SoT v1.8.13·CHANGELOG 문서 정합성.

## Reproduction

```bash
docker compose -f docker-compose.test.yml up -d
# 1) B4 셀(41단정 내장)
python3 -m pytest tests/test_final_save_analysis.py -q
# 2) R1·R2-R3 프런트 (exit code까지 — 파이프 주의)
cd frontend && npx vitest run src/designTokens.test.ts src/drafts/DraftEditor.test.tsx
# 2b) R4 브리프 정합성
python3 -m pytest tests/test_design_token_provenance.py -q
# 3) 502 선언 직독(D5 대기 확인)
python3 -c "import json; s=json.load(open('frontend/openapi.json')); \
print('502' in s['paths']['/projects/{project_id}/drafts/{draft_id}/finalize']['post']['responses'])"
```
