# 2026-09-02 독립 검증 — start-next intent 보존 + 후보 그룹 C 확정 기록 (d4a207a)

## Subject metadata

- 검증일: 2026-09-02
- 요청자: 오너 ("다음 작업 검증해줘")
- 검증자: Claude Code (구현자와 별도 세션)
- 대상: `d4a207a` "Preserve start-next writing intent through scratch" (main, 작업 트리 clean)
- 정본 참조: `docs/system-contract-sot.md` **v1.8.16**(후보 identity group C 확정 + start-next 보존 계약), `docs/plans/pending-candidate-identity-grouping-decisions.md`(확정 — C 채택)
- 환경: 동일 호스트(python3.12·pydantic 2.12.5·fastapi 0.127.0, test-mongo 27020 기동)

## Scope

1. Writing start-next 결함 폐쇄 — generate 요청 `intent`/`next_unit`이 sync scratch·async job·worker 결과·scratch API·복구 패드 accept까지 보존되는가 (동작 + 잠금)
2. generate 400 검증 4분기(append+next_unit·start 무 next_unit·빈 title·빈 goal)의 동작과 잠금
3. 몽고 어댑터 2종(scratch·generation_job)의 신규 필드 round-trip 잠금
4. 결정 기록 — C 확정의 브리프·SoT·README·work_log 반영
5. 생성물 — schema.d.ts(gen:api 무차이), 빌드, docs 인덱스 가드

## Methodology

아래 Reproduction. 변이는 사전 `git status --short` 0줄 게이트 → 변이 → 재실행 → `git checkout --` → clean 확인(매번, 루트 상대경로로 — `frontend/` CWD에서 복원하면 pathspec 미스로 변이가 남는 사고를 이번에 두 번 냈다). 400 동작은 `_generate_app` 재조립 프로브로 직접 확인.

## Findings

### 동작 (전부 정상)

- **보존 사슬**: HTTP generate가 `intent`/`next_unit`을 받아(`routers/writing.py:317-337` 검증 후) sync scratch 저장(`:503-504`)·async enqueue(`:400-401`)에 실고, job 도메인·몽고 `_doc`/`_entry`가 보존하며, worker가 `WritingRequest` 재구성(`generation_worker.py:137-143`)과 scratch 결과(`:164-165`)에 흘려보내고, scratch API 목록이 `next_unit`을 내보내며(`routers/writing.py:1362`), `ScratchRecovery` accept가 저장된 `next_unit`을 재전송한다(`ScratchRecovery.tsx:180`). 결함 경로(이전 Scene에 append)는 닫혔다.
- **400 검증 4분기 실태**: 프로브로 전부 발화 확인 — `append_current must not carry next_unit` / `start_next_unit requires next_unit` / `next_unit.title must not be blank` / `next_unit.goal must be a nonblank string or null`. 검증 위치는 output-length 해석·provider 호출 이전(SoT v1.8.16 문언과 일치).
- **클라이언트 게이팅**: `WritingPanel` 생성 가드·버튼 비활성 모두 `!nextUnitReady`(`WritingPanel.tsx:320,777`), start-next 생성 body가 intent/next_unit를 실는다.
- **WritingCandidatePayload 신규 필수 필드 2개의 생산자는 generate 라우트 유일**(`routers/writing.py:304`) — 지난판 P0 부류(두 번째 생산자 ResponseValidationError) 위험 없음.
- **결정 기록**: work_log Decisions에 "사용자가 C안을 채택한다고 확정했다"가 §5 관례대로 기록됐고 브리프 상태·plans README·SoT v1.8.16 행·CHANGELOG·HANDOFF 착수점(다음 작업=구현 슬라이스)이 일관된다. 결정 자체의 독립 검증(오너 발화 확인)은 검증자 범위 밖 — 기록 위임 사항으로 남긴다.

### 재현 실행 (검증자 실측)

- 작업자 명령 그대로: `python3 -m unittest tests.test_writing_scratch tests.test_writing_generation_job tests.test_writing_generation_worker tests.test_writing tests.test_writing_revise` → **191 OK**(66.0s). 몽고 2파일 → **24 passed**. 프론트 2파일 → **72 passed**. `tsc --noEmit` rc=0·`npm run build` **711 modules** 성공.
- **전수**: 백그라운드 실행이 95% 지점에서 인프라 추정 원인으로 kill됨(요약 라인 소실). 진행점 문자열 분석으로 중단 시점까지 **2590 passed·1 failed·1 skipped**(실패 위치 [41]~[46]% = 알파벳 순서상 docs 인덱스 파일) — 단독 재현한 `test_the_readme_names_the_current_contract_version` 1 failed와 일치. 잔여 꼬리(알파벳 마지막 블록 test_writing* 20파일)를 별도 실행해 **220 passed·75 subtests** — 전수 전체가 "docs 가드 1 실패 외 전부 green"으로 폐쇄된다(구간 합: 2590+220, skip 1 = live Chroma 구조적).

### 변이 검증 (검증자 독립 적용)

| 변이 | 적용 diff | 결과 |
|---|---|---|
| FA | generate의 400 검증 블록(4분기) 통째로 삭제 | `test_writing_scratch`+`test_writing` **96 passed — 아무도 안 물음(무잠금 입증)** |
| FB | `generation_job_mongo._doc`에서 `"intent"`·`"next_unit"` 두 줄 삭제 | job몽고+worker **31 passed — 아무도 안 물음(무잠금 입증)**. `test_round_trip_preserves_all_fields_...`의 `_job` 헬퍼가 신규 필드를 값으로 안 넣으므로 None↔None으로 통과 — scratch몽고는 값을 넣어 잠근 것과 대조 |
| FC1 | sync scratch 저장에서 `intent`/`next_unit` 인자 제거 | `test_writing_scratch` **2 failed** — 물림 |
| FC2 | worker scratch 결과에서 `intent`/`next_unit` 제거 | `test_writing_generation_worker` **1 failed** — 물림 |
| FC3 | `ScratchRecovery` accept를 `next_unit: null`로 원복 | **1 failed** — 물림 |
| FC4 | `WritingPanel`의 `!nextUnitReady` 방어 2곳(가드+버튼) 제거 | **1 failed** — 물림 |

## Issues / Risks

### Blocking (조건으로 전환 — 판정 참조)

1. **README 정본 표기 미갱신**: SoT가 v1.8.16인데 최상위 README가 v1.8.15를 말한다 → `test_docs_indexes.py::test_the_readme_names_the_current_contract_version` **red at HEAD**(전수의 유일한 실패).
2. **schema.d.ts 손편집 불일치**: 커밋된 schema.d.ts는 gen:api 재생성과 3곳이 다르다 — `NextUnitPayload` 컴포넌트 미등재, 응답 `next_unit`를 `NextUnitBody | null` **선택**으로 표기(실제 OpenAPI는 `NextUnitPayload | null` **필수·nullable**), 요청 `intent`의 `@default append_current` 주석 누락. 공개 계약 생성물이 정본 OpenAPI와 어긋난다(H3 생성물 검증 계약).
3. **400 경계 4분기 무셀**: SoT v1.8.16이 요구하는 검증이 FA 변이로도 green — 계약 요구 분기의 잠금 부재.
4. **job 몽고 어댑터 신규 필드 무셀**: FB 변이로도 green. production 저장소(몽고)에서 이 필드들이 유실되면 워커가 `append_current`로 폴백해 **이 슬라이스가 고치는 바로 그 결함이 배포에서만 재발**한다(in-memory 경로는 잠겨 있어 suite는 green).

### Hardening recommendations (비차단)

- 400 셀을 만들 때 `detail` 리터럴까지 핀(진단 메시지 계약) — 선택사양.
- 검증자 교훈(기록용): 변이 복원을 `frontend/` CWD에서 root 상대 pathspec으로 시도하면 실패하고 변이가 남는다 — 이번 검증에서 2회 발생, 즉시 재복원으로 무사. CWD를 확인하고 복원할 것.

## Verdict

**조건부 합격** — 조건 4: ① README 정본 표기 v1.8.16 갱신(docs 가드 green) ② schema.d.ts를 gen:api로 재생성해 커밋(불일치 3곳 해소) ③ generate 400 경계 4분기의 기명 회귀 셀 추가 ④ `test_writing_generation_job_mongo` round-trip에 `intent`/`next_unit` 실값 추가. 근거: 제품 동작 자체는 전 축에서 정상(프로브·191/24/72·전수 재구성)이고 보존 사슬의 도메인 잠금(FC1~FC4)은 작동하나, 계약 요구 분기 2곳이 무잠금(FA·FB 입증)이고 계약 생성물 2종(README 버전·schema.d.ts)이 정본과 어긋난 채 red 가드가 HEAD에 남는다.

## Outstanding items

- 조건 ①~④ 폐쇄 후 이 기록의 조건 닫힘을 다음 검증에서 확인한다(관례대로 별도 폐쇄 기록).
- identity group **구현** 슬라이스가 다음 작업(HANDOFF 착수점) — 본 검증은 결정 기록의 정합성만 봤다.
- 전수 백그라운드 kill의 원인(리소스 추정)은 미상 — 재발 시 동일 방법(진행점 분석+꼬리 단독 실행)으로 재구성 가능.

## Reproduction

```bash
git status --short        # clean
python3 -m unittest tests.test_writing_scratch tests.test_writing_generation_job tests.test_writing_generation_worker tests.test_writing tests.test_writing_revise   # 191 OK
python3 -m pytest tests/test_writing_scratch_mongo.py tests/test_writing_generation_job_mongo.py -q   # 24 passed
python3 -m pytest tests/test_docs_indexes.py -q   # 1 failed (README v1.8.15) — 조건 ①
cd frontend && npm run gen:api && git status --short   # schema.d.ts 차이 3곳 — 조건 ②
# 400 프로브: tests.test_writing_scratch._generate_app 재조립 → 4케이스 모두 400 + detail 리터럴
# 변이 FA·FB(무잠금 입증)·FC1~FC4(기명 셀 재실패): 본문 표의 diff 그대로 — 복원은 루트 CWD에서
python3 -m pytest tests/ -q                            # 95% kill까지 2590·1F·1s, 꼬리 220 passed
```
