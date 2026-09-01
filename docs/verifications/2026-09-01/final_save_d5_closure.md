# final-save D5=A 폐쇄(0f26f22) 4차 재검증 — 최종 판정

## Subject metadata

- 날짜: 2026-09-01
- 요청자: 오너("핸드오프 읽고 검증 작업 진행해줘. 검증하고 의심하고 또 의심해줘" — HANDOFF ①-a "4차 재검증 대기")
- 검증자: Claude Code 세션(1~3차 재검증과 별개 세션 — 구현·보강은 다른 세션)
- 대상: `0f26f22`(D5=A 폐쇄 본체 — R3·R4·502 선언 제거·D5 셀·SoT v1.8.14·CHANGELOG)·`6a2c32f`(D5=A 확정·브리프 Resolved)·`3b18a1b`(work_log 종료 기록). 3차 재검증 [`final_save_conditions_closure.md`](final_save_conditions_closure.md)의 조건 R3·R4·D5 폐쇄 주장
- 정본: [`docs/plans/final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md) **Resolved**(D1=B·D2=B·D3=B·D4=A·**D5=A**) §확정 계약 + §D5 오너 결정. 상위 `docs/system-contract-sot.md` **v1.8.14**
- 검증 소스: HEAD `3b18a1b`, 트리 clean(변이 전·후 매번 `git status --porcelain | wc -l` = 0 확인)
- 환경: **알파**(WSL2, RTX 3060 12GB, `/mnt/f`). 호스트 `python3`(3.12.3)·pytest·fastapi·pymongo 설치, `elasticsearch` 패키지 **부재** → 백엔드 skip 4 관례(Chroma 1 + ES 3). test-mongo 컨테이너 up(`127.0.0.1:27020` healthy). frontend `npx vitest`·`npx tsc` node_modules 완비. 주 스택 대부분 4일 전 Exited·worker/admin만 재기동 중이나 호스트 회귀에 무관. **이 세션은 종료값까지 제한 없이 실행** — 구현자 세션의 "약 30초 상한" 제약(work_log 세션 5·7·9)이 이번 실측의 존재 이유다

## Scope

1. 3차 조건 R3(채택 흐름 fetch 계약 복원)·R4(브리프 semantic 표 등재)·D5=A(200+`analysis_error` 고정·502 선언 제거)의 폐쇄 실측
2. 새 pytest 셀(`tests/test_final_save_analysis.py` 2셀)·프런트 관련 suite·tsc·생성물 동기(`schema.d.ts` byte 대조)
3. 변이 5종(under/over-strict 짝 포함 — D5 셀 양방향·프로브 행동 잠금·R3·R4)
4. 제한 없는 환경의 백엔드·프런트 전수 종료값
5. 독자 스윕(구현자·선행 검증이 안 짚은 방향): 재전송 봉투·활동 원장·프런트 finality 표시 축의 잠금

## Methodology

- 프로토콜은 1~3차와 동일: 요약 count 줄 판독(`grep FAILED` 아님 — M2에서 SUBFAILED가 기명 확인), 변이마다 diff를 그대로 적용하고 복원 뒤 트리 clean 확인.
- 502 도달 불가능 주장은 두 층으로 검증: 선언 직독(`route.responses` 키 집합) + 앱 전체 502 생산지 스캔(`routers/*.py`·`api/*.py`의 `status_code=502`·전역 핸들러).
- 전수 순서 주의: **기록 파일을 쓰기 전에** 백엔드 전수를 돌렸다(선행 3회는 기록 미등재로 docs 가드 7 failed를 감수하고 돌린 뒤 등재했다). 이 순서면 docs 가드는 green이고, 등재 뒤 `test_docs_indexes` 단독 재실행으로 판정 열 +1을 확인한다.

## Findings

### 1. D5=A 폐쇄 — 선언·행동·생성물·문서 전 층 실측

- **선언 ✓** — finalize route `responses=_owned(_BILLABLE_400_404_409)`(`routers/drafts.py:668`). 키 집합 직독: `{400, 401, 402, 403, 404, 409, 429, 503}` — **502 부재·quota face 402/429 유지**. `_BILLABLE_400_404_409`는 이 슬라이스가 `errors.py:341`에 신설한 상수(무료 face `_ERRORS_400_404_409` + `_billable`의 402/429).
- **행동 ✓** — 프로브 S6(runner 예외)·S7(runner 미구성) 모두 **200 + `analysis_error` + 실패/pending job**으로 관측. route 본문 직독: 분석 단계(source-ref 준비·job 확보·runner)는 전부 `except Exception` → `analysis_error`에 흡수, 저장·marker는 앞서 확정(D2=B).
- **502 도달 불가능 ✓(구조)** — 앱 전체 스캔에서 502 생산지는 `analysis.py`·`context_search.py`·`source_refs.py`·`writing.py`(accept 계열)뿐이고 `drafts.py`에는 없다. 전역 핸들러는 503만 생산(`main.py:1705`·`1714`). finalize가 내부적으로 `HTTPException(502)`를 받아도 `except Exception`이 잡아 `analysis_error`로 바뀐다.
- **생성물 ✓** — `npm run gen:api` 재생성 뒤 `git status --porcelain` **0줄** — `schema.d.ts` byte-identical(손편집 없음). 502 타입 제거·503 설명문이 무료 face 것으로 바뀐 것까지 커밋본과 일치.
- **셀 ✓(양방향, 변이 M1·M2·M3)** — `test_d5_a_keeps_analysis_failure_inside_a_200_payload`는 502 부활(M1)과 quota face 제거(M2) **모두**에서 재실패. M2에서는 `BillableRouteWiringTest`가 finalize 자리로 SUBFAILED(요약 줄 판독으로 확인 — `grep FAILED`였다면 놓침). 프로브 S6도 502 raise 변이(M3)에 기명 재실패 — **선언이 아니라 행동을 잠근다**.
- **문서 ✓** — SoT **v1.8.14**(2026-09-01 행 + 본문 조항 "502는 이 endpoint에 없다")·CHANGELOG 2026-09-01 행·README ④ v1.8.13→v1.8.14·브리프 상태 Resolved(D5=A)·`docs/plans/README.md` 행 — 전부 직독 일치. SoT "operation 99→100"은 실측과 일치(`create_app()` route 열거 = **100**, finalize POST 1건).

### 2. R3 폐쇄 — 채택 흐름 fetch 계약 복원·갱신 국한

- `reloadLatest`가 `listDraftVersions`(+detail)만으로 복원(`DraftEditor.tsx:598-616`, `getDraft`·`setDraft` 제거 확인). 수동 분석 `complete`에서만 `refreshAnalysisStatus()`가 `getDraft`를 읽는다(`:621-631`, `AnalysisTrigger onStatusChange`에서 호출 `:949`). 주석이 "글쓰기 채택 흐름은 version/history 재조회만 필요하다"는 분리 이유를 못 박는다.
- 3차에서 red였던 채택 3셀의 mock(`versions`·`detail` 2행)이 테스트에서 복원됨(`DraftEditor.test.tsx` 0f26f22 diff — 2행 삭제). 상태 바 핀 셀은 `분석 필요` → 수동 분석 성공 → `분석 완료` 2단을 그대로 잠근다(수동 분석 응답 목에 `getDraft` 갱신본 유지).
- **변이 M4 ✓** — `if (status === "complete") void refreshAnalysisStatus();`를 무력화하면 상태 바 핀 셀만 정확히 재실패(1 failed / 53 passed).

### 3. R4 폐쇄 — 브리프 semantic 표 등재

- `--status-danger | danger-600 | 주의가 필요한 작업 상태 문구` 행이 `10-frontend-design-system-decisions.md` semantic 표에 추가됨. `PaletteProvenanceTest` green(집중 5/5·전수 green).
- **변이 M5 ✓** — 표에서 해당 행을 지우면 `test_the_brief_semantic_table_matches_the_stylesheet`이 재실패.

### 4. 집중 suite·프런트 관련 suite(전부 이 세션 실측)

| 표면 | 실측 |
|---|---|
| 프로브 S1~S13(41단정) | **전부 PASS, rc=0** |
| `tests/test_final_save_analysis.py` | **2 passed**(S1~S13 계약 + D5 셀) |
| quota wiring·palette·activity 라벨·분류표·과금표 | **67 passed / 553 subtests** |
| mypy 가드 `test_typecheck.py` | **8 passed / 3 subtests**(B2의 정적 증거 자리가 green 유지) |
| designTokens + DraftEditor vitest | **59 passed** |
| `npx tsc --noEmit` | rc=0 |

### 5. 독자 스윕 — 이번에 새로 연 것(구현자·선행 검증 어느 쪽도 짚지 않은 방향)

- **★N1(조건) — 프런트 finality 표시 축에 셀이 하나도 없다.** `find frontend -name "*.test.*"` 전 파일에서 `finalize`·`최종 저장` 언급이 **0건**. 확정 계약 제3조의 상태 계산(초안/`최종 저장됨`/`최종 저장 후 수정됨`, `DraftEditor.tsx:665`의 3항 연산)과 D3=B의 final 버튼(비활성 사유 title `:722-725`)·finalize 흐름(`:365-402`, 성공/부분 성공 안내 문구 2종)·`미실행`(`:215-216`, 2차 기록 하드닝 잔여)·`진행 중` 라벨은 **기명 셀 없이 코드로만 존재**한다. 동작 자체는 이번 코드 대조에서 계약과 일치(제5조 라벨 우선순위 `:209-221`은 snapshot 동일성·실패·null 분기까지 문언 그대로) — 빠진 것은 잠금이다. 1차 검증이 이 축을 "코드 대조 합격"으로 넘긴 것이 이 갭의 근원이다("코드 확인"은 가드가 아니라 관찰이다).
- **N2(오너 판단) — Scene 목록이 finality·분석 상태를 읽지 않는다.** 확정 계약 제7조는 "Scene 목록·편집기·작업실 화면은 상태를 보여 줄 수 있도록 … 읽는다"고 못 박고 D3=B도 "작업실에서도 `분석 필요`를 상기시킨다"는데, `finalized_snapshot_id`·`analysis_status`를 소비하는 파일은 **DraftEditor.tsx 하나**다(`DraftList.tsx`는 장/장면 순서·보관 배지만 표시). 1차 검증이 "'작업실 입장'이 앱 전체 진입이므로 편집기 배지로 충족"이라는 해석을 기록한 채 지나쳤다 — 해석이 감사 추적 위에 서 있으므로 오너 확인(현행 유지=계약 문언 수정, 또는 DraftList 배지 구현)이 필요하다.
- **N3(계약 amendment 요청) — 같은 키 재전송이 활동 행을 중복으로 남긴다(실측 2행).** 성공 final + 같은 키 재전송(confirm 헤더) 뒤 `draft_finalized` 행이 2건이다(`activity.record`가 `idempotent_replay` 분기 없이 무조건 실행 — `routers/drafts.py` route 본문). accept의 "기록 조건은 정본이 바뀌었는가"(replay는 안 남김)와 scene-note의 "행위를 센다"(같은 값 재저장도 남긴다)가 갈리는 자리인데 확정 계약·SoT v1.8.14 어느 쪽도 재전송을 못 박지 않는다. UI는 매 클릭 `crypto.randomUUID()` 키를 만들고 성공 뒤 버튼이 비활성이라 **도달 불가 경로**(의도적 API 클라이언트만 가능) — 그래서 차단 아님. 어느 선례를 따를지 오너 확정 후 셀 1줄이면 잠긴다.
- **N4(하드닝) — 실패 뒤 같은 키 재전송의 봉투 비대칭(실측).** 1회차 200+`analysis_error="provider exploded"`+job failed → 같은 키 재전송 200+**`analysis_error=None`**+job failed(저장 상태·runner 무재실행·200 얼굴은 수렴). "동일 결과로 수렴"의 저장 해석은 지키지만 안내 문자열만 떨어진다. 프런트는 `analysis_job.status`만 읽으므로 표시 영향 0.
- **관찰** — 최상위 README ② 카운터("2,316 passed / 2,654 subtests")가 2026-08-22(`2d43a38`) 이후 낡았다(현 실측 2668/3114·베타 기록 2666). 이 슬라이스 유래가 아닌 문서 드리프트로 기록만 남긴다.

## Issues / Risks

### Blocking (조건)

1. **N1** — 프런트 finality·분석 상태 표시 축의 기명 셀 부재: ①finality 배지 3상태(초안/최종 저장됨/최종 저장 후 수정됨) ②final 버튼(활성/비활성+사유)·finalize 흐름(성공/부분 성공 안내 포함) ③`미실행`·`진행 중` 라벨 분기. 계약 요구 분기(제3조·D3=B)에 잠금이 없으므로 가드 규칙상 합격으로 닫을 수 없다.

### Hardening (비차단)

- **N2** — Scene 목록(DraftList)의 상태 표시 미실현 여부 — 계약 제7조 문언과의 긴장, 오너 판단(현행 유지 시 계약 문언 수정 필요).
- **N3** — 같은 키 재전송의 활동 행 중복 — 계약 무침, 오너 amendment(accept 선례=생략 권장) 후 셀 가능.
- **N4** — 재전송 봉투의 `analysis_error=None` 비대칭.
- README ② 카운터 낡음(이 슬라이스 밖).
- 1차 기록 §8 관찰(다른 장면 final의 429·`X-Confirm-Duplicate` 미송부로 재시도가 일반 오류로 보임)은 여전히 열려 있음(UI 안내 검토 가치).

## 전수 (이 세션 실측 — 제한 없는 실행, 종료값까지)

- **백엔드**(test-mongo ON, 알파): **2668 passed / 4 skipped / 3114 subtests, 0 failed, rc=0, 289.86초**. skip 4 = 알파 관례(Chroma 1 + ES 3 — 이 호스트 `elasticsearch` 패키지 부재 실측). 수집 2672셀(`--collect-only` 일치). **docs 가드가 green인 이유는 순서다** — 기록 파일을 쓰기 전에 돌렸으므로 미등재분이 없다(선행 3회와 다른 점). 셀 귀속: 3차(베타) 대비 +1 = D5 셀 신설, 나머지 차이(skip 1↔4·총셀 2676↔2672·subtest 3083↔3114)는 머신·패키지 환경 차이(베타↔알파 수집 차)로, 이 저장소 규칙("skip 수는 머신마다 다르다")대로 환경 라벨과 함께 기록한다.
- **프런트**: **385 passed / 35 files, 0 failed, rc=0, 90.43초** — 3차에서 R3로 깨졌던 3셀 전부 회복, 부하 플레이크도 없음(전수를 백엔드와 **순차** 실행 — 동시 실행 플레이크를 유발하지 않았다).
- **다음 전수 기대값**: 이 기록 등재 뒤 `test_docs_indexes` 판정 열 **subtest +1** → 백엔드 **2668 / 4 / 3115**(환경 동일 시). N1 폐쇄 셀 신설 시 그 수만큼 가산.

## Verdict

**조건부 합격** — 조건: 프런트 finality·분석 상태 표시 축의 기명 셀 부재(N1) 폐쇄. 3차의 named 조건 R3·R4·D5는 **전부 실측 폐쇄**(변이 5종 양방향 포함)이고 양쪽 전수가 제한 없는 환경에서 종료값까지 0 failed다. 그러나 확정 계약 제3조·D3=B가 요구하는 표시 분기(배지 3상태·final 버튼·finalize 흐름·미실행/진행 중)에 프런트 셀이 하나도 없어, "계약 요구 분기마다 기명 셀" 규칙상 합격으로 닫을 수 없다 — 동작은 코드 대조상 계약과 일치하므로 결함은 아니고, 잠금을 추가하는 셀 묶음이 조건의 전부다.

## Outstanding items

- **N1 폐쇄 슬라이스**: DraftEditor finality 배지 3상태·final 버튼·finalize 흐름(성공/부분 성공 안내)·`미실행`·`진행 중` 기명 셀(under/over-strict 짝). 폐쇄 후 5차(승격) 재검증은 집중 셀+변이로 충분하다.
- **N2·N3 오너 판정 대기**: Scene 목록 상태 표시(제7조 문언)·재전송 활동 행(accept 선례 여부). 결정 없이 구현하지 않는다.
- 다음 전수 기대값 2668/4/3115(등재분 +1 subtest).

## Reproduction

```bash
docker compose -f docker-compose.test.yml up -d
# 1) 프로브 S1~S13 + 새 pytest 셀(D5 포함)
python3 docs/verifications/2026-09-01/repro_final_save_flow.py   # rc=0, 41 PASS
python3 -m pytest tests/test_final_save_analysis.py -q           # 2 passed
# 2) 관련 suite·tsc·생성물
python3 -m pytest tests/test_quota_enforcement_api.py tests/test_design_token_provenance.py \
  tests/test_activity_ui_labels.py tests/test_activity_actions.py \
  tests/test_billable_actions.py tests/test_typecheck.py -q
cd frontend && npm run gen:api && git status --porcelain | wc -l  # 0 = schema byte-identical
npx tsc --noEmit && npx vitest run
# 3) 전수(순차 — 동시 실행은 부하 플레이크)
cd .. && python3 -m pytest -q    # 2668 / 4 / 3114 (알파, 기록 작성 전 기준)
# 4) 재전송 관찰(N3·N4) — docs/verifications/2026-09-01/ 프로브 모듈 재사용:
#    make_client(ExplodingRunner()) 후 같은 키 2회 POST(2회차 X-Confirm-Duplicate: 1)
```
