# 2026-09-02 독립 재검증 — dogfood P0·가드 보강 폐쇄 (61cd7a1·0174d8d)

## Subject metadata

- 검증일: 2026-09-02 (2차)
- 요청자: 오너 ("보강한 부분 재검증해줘")
- 검증자: Claude Code (1차 기록 [`dogfood_review_ux.md`](dogfood_review_ux.md)와 동일 검증자, 구현자와는 별도 세션)
- 대상: `61cd7a1` "Fix draft payload validation regression" + `0174d8d` "Document dogfood UX mutation checks" (main, 작업 트리 clean)
- 정본 참조: `docs/system-contract-sot.md` v1.8.15 (이번 폐쇄는 계약 무변 — 500은 v1.8.15에 근거 없는 출력이었으므로 제거가 정합 회복이다)
- 환경: 1차 기록과 동일 호스트·동일 스택(python3.12·pydantic 2.12.5·fastapi 0.127.0, test-mongo 27020 기동)

## Scope

1. 1차 차단 3건의 폐쇄 실증 — ① flat `DraftPayload` 계약 밖 필드 500 ② nested scenes 분석 상태 값 무잠금 ③ 검증 범위·보고 정확성(교착 주장 포함)
2. 1차 하드닝 2건의 폐쇄 — 첫 저장 없는 finalize 진행 라벨·event/question 렌더 잠금
3. 작업자가 "이 세션에서 멈춘다"고 기록한 TestClient 묶음의 독립 재실행(기록된 명령 문자 그대로)
4. 백엔드 전수(2차 연속 슬라이스에서 한 번도 안 돌았던 broader suite)

## Methodology

아래 Reproduction 전체. 특히 작업자가 work_log에 기록한 두 명령을 **문자 그대로** 재실행했다(교착 주장의 재현 시도). 변이는 사전 `git status --short` 0줄 게이트 → 변이 → 기명 셀 재실패 → `git checkout --` → clean 확인(매번).

## Findings

### 1차 차단 3건 폐쇄

- **차단 1(500) 폐쇄.** `routers/drafts.py` `_draft_payload`에서 `latest_snapshot_id` 출력 제거 확인(`DraftPayload`는 무변·schema.d.ts도 무변, gen:api 무차이). 1차에서 커밋한 프로브 [`repro_draft_payload_500.py`](repro_draft_payload_500.py) 재실행: **5경로 전부 200**(1차에는 4경로 500). 참고로 archive의 실제 경로는 `DELETE /drafts/{id}`(`drafts.py:400-405`)이며 1차 프로브의 `POST .../archive` 404는 프로브 경로 착오였다(같은 빌더·같은 response_model이라 폐쇄 판정에는 영향 없음).
- **차단 2(값 무잠금) 폐쇄.** 신규 셀 `ChapterHierarchyApiTest::test_flat_contract_and_nested_analysis_values`(`tests/test_chapter_hierarchy.py:483-533`)이 exact `analyze:{snapshot_id}` job의 snapshot·`running` 상태를 flat·nested 양쪽 값으로 단정하고, flat은 `DraftPayload.model_validate` + `latest_snapshot_id` 부재로 계약 폐쇄를 직접 검증한다(이 suite가 코루틴 직접 호출로 FastAPI 응답 검증을 우회한다는 1차 지적의 정확한 보완).
- **차단 3(보고) 폐쇄.** work_log에 ① 원판 "15 passed, 279 subtests"의 정확한 명령(1+13+1셀 선택) ② broader 재실행 명령 ③ faulthandler 진단 명령이 기록됐다.

### "교착" 주장 — 작업자 기록 명령 그대로 재실행 결과

| 명령(work_log 기록 문자 그대로) | 작업자 관측 | 이 호스트 실측 |
|---|---|---|
| `timeout 240s python3 -m pytest -q tests/test_scene_notes_api.py tests/test_final_save_analysis.py tests/test_analysis_apply_api.py tests/test_chapter_hierarchy.py` | 첫 project 생성 POST에서 무출력 대기로 중단 | **106 passed, 15 subtests, 40.15s** |
| `timeout 50s python3 -m pytest -vv -s -o faulthandler_timeout=20 tests/test_scene_notes_api.py` | 첫 셀 setUp `anyio.from_thread` 대기로 timeout(124) | **48 passed, 9 subtests, 21.08s** |

2차에 걸쳐 재현되지 않는다. 작업 세션의 일시적 리소스 경합(동시간대 검증 세션의 빌드·전수 등)이 가설일 뿐 입증은 못 한다 — 어느 쪽이든 **제품 결함이 아니며 기록된 명령으로 제3자 검증이 가능해졌다**는 것이 폐쇄 요건을 만족시킨다.

### 변이 검증 (검증자 독립 재적용 — 작업자 표와 셀·결과 일치 확인)

| 변이 | 적용 diff | 재실패 셀 | 결과 |
|---|---|---|---|
| M8 | `_draft_payload`에 `"latest_snapshot_id": None if latest is None else latest.snapshot_id,` 재삽입 | `test_flat_contract_and_nested_analysis_values` | **1 failed** — 물림 |
| M9 | `_scene_payload`(2번째 발현)의 `analyze:` → `analyze-broken:` | 같은 셀 | **1 failed** — 물림 (1차 M7b 무잠금 갭 폐쇄) |
| M10 | `analysisLabel`에서 `latestSnapshotId === null` 분기를 `analysisRunning`보다 앞으로 원복 | `저장본이 없는 첫 최종 저장도 요청 중에는 분석 진행으로 표시한다` | **1 failed** — 물림 |
| M11 | `PAYLOAD_FIELD_LABELS`에서 `event`·`question` 두 행 삭제 | `renders event and open-question summaries inside their list rows` | **1 failed** — 물림 |

### 재현 실행 (검증자 실측)

- 작업자 broader 명령: **106 passed, 15 subtests** (= scene_notes 48 + final_save 2 + analysis_apply 38 + chapter 18 — 1차 조건이었던 세 suite green 포함).
- **백엔드 전수 `python3 -m pytest tests/ -q`: 2672 passed / 1 skipped(live Chroma·구조적) / 3116 subtests, 실패 0건, 2113.67s.** 이 슬라이스 계열에서 전수가 돌아 green인 것은 이번이 처음이다.
- Chapter 단독 **18 passed, 4 subtests** / Chapter+문서 인덱스 **31 passed, 284 subtests** / 프런트 3파일 **88 passed** / `npx tsc --noEmit` rc=0 / `npm run build` **711 modules** 성공 / `npm run gen:api` 트리 무차이.
- 711 modules는 61cd7a1과 무관한 증가다(HANDOFF 704 기준선은 2026-08-21 관측치로 낡았고, 그 사이 장면 메모·final-save 슬라이스가 프런트 모듈을 더했다). 다음 전수 기록 시 참고.

### 문서·기록

- work_log에 보강 표·이슈 원인·결정(최소 복원 선택: flat 계약 확장이 아니라 출력 제거, `latest_snapshot_id`는 `ScenePayload` 전용)·변이 표가 기록됐고, CHANGELOG 행과 HANDOFF 착수점(①-a N2 대체)이 갱신됐다. SoT는 무변(정합). HANDOFF 분량 750줄 무변(다음 검수 트리거 783 미달).

## Issues / Risks

### Blocking (계약 의무)

- 없음.

### Hardening recommendations (비차단)

- `_scene_payload`의 장면당 `list_draft_versions` 전체 스캔 + job 조회(1차에서 지목, 이번에도 미처리). 장면·버전 수가 커지면 목록 endpoint 비용이 선형으로 자란다 — 플랫 목록의 기존 패턴과 같으므로 계약 위반은 아니다.
- 작업 세션의 TestClient 대기는 2회 재현 실패 — 재발 시 세션 동시 부하 상태(curl 아님, `ps`·부하)를 그 시점에 기록해 두면 다음에 진단 가능하다.

## Verdict

**합격** — 1차 기록의 차단 3건이 모두 실측으로 폐쇄됐다: 500은 프로브 5경로 200·관련 suite green·`DraftPayload.model_validate` 셀(M8 재실패)으로, 값 무잠금은 exact-key 셀(M9 재실패)으로, 보고 정확성은 기록된 명령의 문자 그대로 재실행 green으로. 백엔드 전수 2672/1/3116 실패 0. 하드닝 2건(첫 저장 진행 라벨·event/question 렌더)도 M10·M11로 잠금을 확인했다.

## Outstanding items

- 2번(미승인 후보 identity grouping)은 여전히 오너 결정 대기(브리프 권장 C). 구현·계약 무변.
- `_scene_payload` 버전 스캔 최적화는 유예(트리거: 장면 수·목록 응답 시간 관측).
- 이 호스트 개발 스택 다운·워커 crashloop은 무관하나 실 dogfood 육안 확인 전 재기동 필요(1차 기록 동일).

## Reproduction

```bash
git status --short        # clean
# 작업자 기록 명령 그대로 (교착 재현 시도):
timeout 240s python3 -m pytest -q tests/test_scene_notes_api.py tests/test_final_save_analysis.py tests/test_analysis_apply_api.py tests/test_chapter_hierarchy.py   # 106 passed
timeout 50s python3 -m pytest -vv -s -o faulthandler_timeout=20 tests/test_scene_notes_api.py   # 48 passed
PYTHONPATH=. python3 docs/verifications/2026-09-02/repro_draft_payload_500.py   # 5경로 전부 200
python3 -m pytest tests/ -q                                                     # 2672 passed / 1 skipped / 3116 subtests
cd frontend && npx vitest run src/drafts/DraftEditor.test.tsx src/drafts/DraftList.test.tsx src/review/ReviewInbox.test.tsx  # 88 passed
npx tsc --noEmit && npm run build && npm run gen:api && git status --short      # 무차이
# 변이 M8~M11: 본문 표의 diff 그대로 적용 → 각 기명 셀 1 failed → git checkout -- 복원 → clean 확인
```
