# Verification Record — 테스트베드 사용가능화 슬라이스 A+B+C (독립 검증)

## Subject metadata

- **날짜**: 2026-07-18
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? ... UI적용 부분이니까 실제 구동에 있어서도 새로운 예외 처리가 필요하거나, 요청과 llm의 분석이 너무 묶여있어서 불필요한 단계, 첫 글 쓸 때 분석 비교 비효율 ... 효율적인 측면도 함께")
- **검증자**: 독립 검증 AI(본 세션, 작업 AI와 별개)
- **대상 슬라이스**: 2026-07-18 Task 2 — 테스트베드 사용가능화 A+B+C (오너 dogfood 발견 3건 대응). SoT `v1.7.6`.
  - **A**: report 2차 repair (`MAX_REPORT_REPAIRS` 1→2, 계약 D4=A 개정).
  - **B**: `AnalysisTrigger` + 집필↔검토 연결 (`analyzeVersion`, `ensureSourceRefCatalog`).
  - **C**: `WritingPanel` 관측성(progress 단계 표시 + candidate summary + `describeWritingError`).
- **정본 계약 참조**: `docs/system-contract-sot.md:36`(v1.7.6 행), `docs/plans/05-writing-accept-decisions.md`(D5=A), `docs/plans/product-readiness-backlog.md`.
- **검증 소스**: 작업 트리(미커밋). `git status` — modified: `report.py`, `client.ts`, `WritingPanel.tsx`, `DraftEditor.tsx`, `styles.css`, `WritingPanel.test.tsx`, `report_live_diag.py`, `tests/test_writing_report*.py`, SoT/CHANGELOG/HANDOFF. untracked: `AnalysisTrigger.tsx`, `AnalysisTrigger.test.tsx`. (HEAD `2e02b9a` 기준 working tree.)

## Scope

1. **A 계약·코드·테스트 일관성** — D4=A "strict + 최대 2 repair"가 코드·회귀 테스트와 일치하는지(양방향 잠금).
2. **B 계약·코드·테스트 일관성** — `AnalysisTrigger`/`analyzeVersion`/`ensureSourceRefCatalog`의 계약 일관성·blocked 상태·catalog 자동 빌드·job create→run.
3. **C 계약·코드·테스트 일관성** — progress 단계 렌더·candidate summary·에러 매핑의 계약 일관성·회귀 잠금.
4. **(사용자 질문 1) UI 실제 구동 시 새 예외처리 필요 여부** — `ensureSourceRefCatalog` 부분실패, 직렬 단계 중간실패, 동시성/더블클릭, 재시도 복구.
5. **(사용자 질문 2) 요청↔LLM 분석 결합도/불필요 단계** — accept가 만드는 analysis job, `analyzeVersion` 매번 새 job, create+run 분리.
6. **(사용자 질문 3) 첫 글 분석/비교 비효율** — accept 자동 분석, 같은 snapshot 재분석 중복, full-span catalog 정밀도, compare 단계.
7. **독립 재현** — work_log 주장 테스트 카운트(백엔드 1118, 프론트 116)의 직접 재실행.

## Methodology

- **계약 범위화 후 코드**: 각 surface의 boundary matrix를 SoT v1.7.6 행 + 해당 plan(`05-writing-accept-decisions.md` D5=A/D4=A)에서 먼저 빌드한 뒤, 코드·테스트에서 cell을 채움.
- **독립 검증 워크플로우**: 6개 분석 에이전트(A/B/C 계약 + Q1/Q2/Q3 효율성) × 각 finding마다 adversarial verify 에이전트 = 39 에이전트, 738 tool call. verify는 "틀렸다고 전제하고 깨뜨리려 시도" 태도. 결과 중 38 done / 1 safety-classifier 일시적 error(해당 finding은 검증자가 직접 코드로 대체 확증).
- **테스트 독립 재실행**(검증자 로컬):
  - 백엔드: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` — `services` 패키지 resolve를 위해 `python -m` 필수(`pytest` 직접 호출 시 `ModuleNotFoundError: No module named 'services'`, collection error 86건).
  - 프론트: `cd frontend && npm test -- --run`.
- **file:line 재도출**: 작업 AI work_log 주장을 신뢰하지 않고 코드에서 재도출. 모든 인용은 실제 읽은 라인.
- **mutation testing**(워크플로우): `MAX_REPORT_REPAIRS` 1/3으로 변형 시 실패하는 테스트 집합으로 양방향 잠금 확인.

## Findings

### 0. 독립 재현 — work_log 테스트 카운트 정확 (PASS)

- 백엔드 `python3 -m pytest --ignore=tests/test_memory_mongo.py` → **1118 passed / 48 skipped / 273 subtests passed** in 20.50s. work_log 주장과 정확히 일치([by1198p7x.output](../../../tmp) 재실행).
- 프론트 `vitest run` → **8 files / 116 passed**. work_log 주장과 일치. `AnalysisTrigger` 7 tests, `WritingPanel` 34 tests 포함.
- **주의**: 백엔드는 `python -m pytest`여야 함. 평소 `pytest` 직접 호출 시 collect 실패. CI/워크플로우가 어떤 방식을 쓰는지 별도 확인 권장(재현성 함정).

### A — report 2차 repair: 계약·코드·테스트 일관 (PASS, info)

- `report.py:72` `MAX_REPORT_REPAIRS = 2`; `:117` `while report is None and repairs < MAX_REPORT_REPAIRS:` — bounded repair loop, "최대 2 repair"(총 시도 1 초기 + 2 repair = 3회)을 정확히 구현. SoT v1.7.6 D4=A "strict + 최대 2 repair"와 무모순.
- strict 무변: `parse_report`(`:147-196`)의 배열/필드/포인터 allowlist/literal 검사가 repair에도 동일 적용. null→[] 관대화 없음.
- usage 누적: `:127` `usage = add_usage(usage, retry.usage)` — 각 repair usage가 aggregate budget(B2)에 합산. 전부 실패 시 `:133-135` `MeteredCallError(InvalidCandidateReport, usage)` raise.
- **boundary matrix full**: 0-repair OK / 1-repair OK / 2-repair OK(신규 분기) / all-fail 각각 named test(`test_writing_report.py:78-139`). mutation test — `MAX→1` 시 신규 3개 test 실패(under-strict), `MAX→3` 시 2개 test 실패(IndexError→wrong cause, over-strict). 빈 cell 없음.
- 진단 collateral: `report_live_diag`가 production `enrich_metered` 재사용 → `caps[-1]`(최종 repair raw) 노출. 진단 테스트 3 출력 큐잉.
- OpenAPI immutability: `gen:api` schema diff 0 (`schema.d.ts` 무변) — 백엔드가 내부 repair 횟수만 바꿨으므로 공개 literal 무변.

### B — AnalysisTrigger + 연결: 기능 동작, 효율/예외처리 측면에 다수 개선점 (CONDITIONAL)

- `AnalysisTrigger.tsx` blocked 상태(readOnly/dirty/noVersion) 매핑 정확. `analyzeVersion` catalog 자동 빌드 → create → run 직렬 동작 라이브 관통(work_log 3 candidate → 검토함 3, 독립 재현은 스택 의존이라 본 검증은 코드 경로로 확증).
- **계약 일관성 확인**: 분석 추출이 snapshot의 source_ref catalog를 선행 요구(`prompt_builder.py:26` "source_ref catalog is required" 400)하는 것은 맞음. `ensureSourceRefCatalog`가 catalog 비어 있으면 block별 full-span source_ref 생성(`client.ts:519-529`) → 400 해소 로직 정상.
- **degenerate block skip은 결함 아님**(`client.ts:520` `if (block.end_offset <= block.start_offset) continue;`): 서버 `core_sot/service.py:386`가 동일 조건을 `InvalidSourceRef` 400으로 거부하므로, 클라이언트 skip이 없으면 degenerate block 첫 POST에서 throw함. 방어 로직.

### C — WritingPanel 관측성: 코드 구현은 정확, **렌더 회귀 잠금 부재 (BLOCKING)**

- `WritingPanel.tsx:252,265,313` `setProgress`("근거 검색…/Gate 평가…/자동 개선…")가 각 호출 직전 설정, `finally`(`:300,339`)에서 복구. `:513-519` "근거 주장 N개 · 기억 후보 · 위험 지적" candidate summary 정확.
- **그러나** SoT v1.7.6 C가 이 표시를 슬라이스 계약 의무로 규정했음에도, 이 렌더를 잠그는 회귀 테스트가 프론트 전 스위트에 **없음**. `WritingPanel.test.tsx`에서 `progress`/`setProgress`/"근거 주장"/`candidate-summary` 매처 0건(`:37`은 fixture `candidate_claims: []`만). `:368-369`("자동 개선 완료"/"자동 개선 단계" list)는 `LOOP_STATUS_COPY` 결과이지 `setProgress` coarse 단계가 아님.
- `describeWritingError`의 `invalid_writing_revision`/`invalid_gate_result` 매처(`client.ts:456-467`)가 정상 경로에서 도달 불가(사실상 dead branch) — 백엔드가 해당 literal을 emit하는 엔드포인트가 generate/gate/revise 경로에 없음.

### (사용자 질문 1) 예외처리 — ensureSourceRefCatalog 부분실패 자가복구 불가 (**BLOCKING**)

- `ensureSourceRefCatalog`(`client.ts:519-529`)가 N개 block을 순차 `POST /source-refs`로 생성. **롤백/배치 없음**.
- **핵심 결함**: k번째 POST가 실패(네트워크/5xx)하면 이미 생성된 k-1개 source_ref가 잔존. 사용자가 "다시 분석"을 누르면 `:516` `if (existing.source_refs.length > 0) return 0;`가 catalog 재구축을 **스킵** → 누락된 block들의 anchor 없이 `run`이 진행.
- 결과: (a) extractor(`extractor.py:115-149`)가 catalog에 있는 span만 anchor로 받으므로 후보가 조용히 누락(silent partial extraction)되거나, (b) catalog 밖 anchor를 잡으면 job이 `FAILED`. **사용자에게 catalog가 불완전하다는 신호가 전혀 없고, UI상 복구 불가** — 영속적인 부분 추출로 수렴.
- 직렬 단계 부분실패: `analyzeVersion`(`:539-558`) catalog → create → run. create 성공 후 run 실패 시 `jobId`가 호출자로 반환되지 않음(`request()` throw로 `:559-563` 미도달). PENDING orphan job 적체, 새 `randomUUID` 재시도로 절대 정리 안 됨.
- 동시성: `AnalysisTrigger.run()`(`:39-42,84`)은 `busy` state만 체크, `busyRef`(useRef) 없음. `WritingPanel`(`:207` `busyRef.current`)과 일관성 부족. 빠른 더블클릭/React 동시 모드에서 같은 snapshot에 2개 job 경합 가능(=아래 중복 후보와 결합). AnalysisTrigger.test.tsx에 동시클릭 회귀 없음(double/concurrent 매처 0건).

### (사용자 질문 2) 결합도/불필요 단계 — accept orphan + 매번 새 job (HARDENING + EFFICIENCY)

- **accept orphan**: `accept.py:99-105` `_create_job`이 `analysis.create_job(...)`만 호출 → PENDING job. run의 유일 HTTP 호출자는 `main.py:1762` `run_analysis_job` 엔드포인트(`:1783` `runner.run_job`) 단 한 곳. 이를 호출하는 프론트는 `analyzeVersion`(`client.ts:555-558`) 단 한 곳. **accept가 만든 `writing-accept:{key}` job을 run하는 경로 없음** — orphan 누적.
- **그러나 이 PENDING-then-no-run 자체는 D5=A 오너 결정**(`05-writing-accept-decisions.md:65` "사용자가 별도 run 호출을 해야 후보가 생긴다", `:118` "run은 호출하지 않음"). 결함 아님.
- **의도 위반 부분**: D5=A 본문(`:69`, `:104` 주석)은 "후속 background run이 **같은 job**을 소비"하도록 job identity를 응답에 싣는다고 명시. 그런데 `WritingPanel.accept`(`:345-430`)는 accept 응답의 `analysis_job`을 폐기(`acceptWriting`은 `analysisFailed` 플래그만 반환)하고, `AnalysisTrigger`는 accept job_id를 모른 채 매번 **새 job**(`client.ts:551` `idempotency_key: crypto.randomUUID()`)을 만들어 run. → D5=A의 "같은 job 소비" 의도 미실현.
- **중복 candidate(EFFICIENCY, plausible)**: 같은 snapshot에 "이원고 분석" 2회 → 서로 다른 idempotency_key → 서로 다른 job → 각각 run. candidate dedup는 `(project_id, task_id, logical_key)`(`service.py:420`) task-scope라 **job이 다르면 같은 candidate도 별도 저장**. review inbox에 동일 인물/사건 후보가 누적 적산.
- catalog 매번 GET(EFFICIENCY): `ensureSourceRefCatalog`가 매 호출마다 `GET /source-refs`(`:513-516`). 이미 cataloging된 snapshot도 매번 왕복(POST만 스킵).
- create+run 분리 자체는 D5=A 의도적(info, 비결함).

### (사용자 질문 3) 첫 글 분석 비교 — test-bed 후킹 + full-span 정밀도 (EFFICIENCY)

- **full-span catalog가 anchor 정밀도를 block 단위로 뭉뚱그림(EFFICIENCY)**: `ensureSourceRefCatalog`가 모든 block을 `start_offset~end_offset` full-span(`client.ts:521-527`)으로 cataloging. candidate의 근거 위치 해상도가 block(장면/단락) 단위로 coarse → 비교/검토 정확도 저하 가능. "test-bed trigger"로 명시(`:503-506`).
- **이어쓰기마다 catalog 재빌드 + candidate 재추출(EFFICIENCY)**: 매 accept가 새 snapshot(`core_sot/service.py` `next_snapshot_id`)을 만들고 source_ref가 없으므로, 매 AnalysisTrigger가 catalog를 처음부터 빌드. 같은 snapshot 재클릭 시에도 candidate 매번 재추출(위 중복).
- accept가 심어둔 `writing_candidate_report`(`accept.py:104`)는 `runner.run_job`(`runner.py:133-136`)이 소비하지만, accept job이 run되지 않아 **report는 accept 경로에서 사장**. 단 이것도 D5=A 맥락(명목상 job identity 전달)이므로 "결함" 프레이밍은 부적절(Q3 verify reject).
- compare 엔드포인트(`main.py:2039`)는 `AnalysisTrigger`가 호출하지 않음 → **첫 글에 비교 단계가 불필요하게 끼어있지 않음**(info, 비결함).

## Issues / Risks

### Blocking (계약 의무 / boundary 빈 칸)

1. **C progress coarse 단계 렌더에 회귀 없음** — SoT v1.7.6 C가 슬라이스 계약 의무로 규정한 "근거 검색·초안 생성 → Gate 평가 → 자동 개선" coarse 단계 표시가 코드는 구현됐으나, 이 렌더를 잠그는 회귀 테스트가 없음. `setProgress` 호출/문구를 지워도 테스트가 깨지지 않음 → boundary matrix 빈 칸. `WritingPanel.tsx:252,265,313,477-482` / `WritingPanel.test.tsx`(전체).
2. **C candidate summary("근거 주장 N개") 렌더에 회귀 없음** — 동일하게 계약 의무 표시이나 회귀 잠금 없음. `WritingPanel.tsx:513-519` / `WritingPanel.test.tsx`.
3. **Q1 `ensureSourceRefCatalog` 부분실패 → silent partial extraction(자가복구 불가)** — k번째 block POST 실패 시 잔존 → 재시도 스킵 → 누락 block anchor 없이 run → 조용한 부분 추출 또는 FAILED. 사용자 신호·복구 없음. `client.ts:516,519-529` / `extractor.py:115-149`.

### Hardening recommendations (non-blocking)

4. **accept 502 partial → 별개 job 우회** — `main.py:3241-3247` partial 시 `WritingPanel`이 accept job을 재사용하지 않고 AnalysisTrigger로 별도 job run. D5=A "같은 job 소회" 정신과 어긋남.
5. **create 성공 후 run 실패 → orphan PENDING job 적체, jobId 미반환** — `client.ts:539-558`. AnalysisTrigger catch가 `describeApiError`만 표시, jobId 추적/정리 없음.
6. **AnalysisTrigger 동시성 가드 `busy` state뿐, `busyRef` 없음** — `AnalysisTrigger.tsx:25,39-42`. WritingPanel(`:207` busyRef)과 일관성 부족 + 빠른 더블클릭 race. 동시클릭 회귀 테스트도 없음.
7. **같은 snapshot 재분석 → job-간 candidate 중복** — `client.ts:551`(매번 새 uuid) + `service.py:420`(task-scope dedup). review inbox 중복 적산.
8. **`describeWritingError` invalid_writing_revision/invalid_gate_result 매처가 dead branch** — `client.ts:456-467`. 백엔드가 해당 literal을 emit 안 함. 매핑은 무해하나 도달 불가.
9. **degenerate block "전부 degenerate → run 400" 엣지 미검증** — `client.ts:520` skip이 전부 skip이면 catalog 0개 → run이 여전히 400. 회귀 없음.
10. **`report.py:125-126` provider-exception-during-repair wrapping에 전용 테스트 없음** — pre-existing이나 repair loop 확장과 인접.
11. **DraftEditor 헤더 "검토함 →" 링크에 회귀 없음** — `DraftEditor.tsx:287-289`. nit.

### Efficiency (오너 판단 영역)

12. **full-span catalog가 candidate anchor 정밀도 저하** — `client.ts:521-527`. block 단위 coarse anchor. 분석 품질 영향.
13. **이어쓰기마다 catalog 재빌드 + 매 분석 GET source-refs** — `client.ts:513-516,539`. 이미 cataloging돼도 매번 GET.
14. **accept의 writing_candidate_report가 run 경로 부재로 사장** — D5=A 맥락이나, report 심는 비용 대비 효용 재검토 권장.

## Verdict

**조건부 합격(Conditional Pass).** 기능은 의도대로 동작하고 work_log의 테스트 카운트(백엔드 1118 / 프론트 116)·라이브 관통 보고는 독립 재현·코드 경로로 정확히 확인했다. A(report repair)는 boundary matrix가 양방향으로 완전히 잠겨 있어 합격.

그러나 **3개 blocking**이 슬라이스 계약 의무의 잠금 부족이다:
- C의 progress/summary 렌더는 SoT v1.7.6 C가 명시한 슬라이스 계약 표시임에도 회귀 테스트가 없다(boundary 빈 칸). 이 둘은 테스트 2건 추가로 즉시 닫을 수 있다.
- Q1의 `ensureSourceRefCatalog` 부분실패 → silent partial extraction은 **실제 구동에서 발생 가능한 새 예외처리 gap**으로, 부분 실패를 감지·복구(또는 catalog를 트랜잭션/멱등 빌드)하는 처리가 없다. 사용자가 "실제 구동 시 새 예외처리 필요 여부"를 직접 물은 질문에 대한 답이 **"예, 있다"**인 셈이다.

효율성 측면(사용자 질문 2·3)은 오너 판단 영역이지만, **D5=A의 "같은 job 소비" 의도가 AnalysisTrigger에 의해 미실현**되고 있음(accept 응답의 `analysis_job` 폐기 + 매번 새 job → orphan 적체 + 같은 snapshot 재클릭 시 candidate 중복 적산)을 확증했다. 이는 결함이라기보다 D5=A 의도와 현 구현의 정렬 문제이므로 오너 결정이 필요하다(같은 job 재사용으로 전환할지, orphan 적체를 수용할지).

## Outstanding items

- **미커밋 변경**: 작업 AI가 커밋 보류 중(오너 요청 대기). 본 검증은 작업 트리 기준.
- **라이브 재현**: B 라이브 관통(analyzeVersion catalog 3 → candidate 3)은 스택 의존이라 검증자가 직접 재현하지 않고 코드 경로 + work_log로 확증. 스택이 실행 중이므로 오너 브라우저 확인 가능.
- **blocking 3개 해소 전 커밋 지양**: C 2건은 회귀 테스트 추가로 즉시 닫힘. Q1은 catalog 빌드를 부분실패 안전하게(트랜잭션/재시도 시 잔존 무시하지 않기) 개선 필요.
- **D5=A 정렬 결정**: accept 응답의 `analysis_job`을 `AnalysisTrigger`가 재사용(같은 job run)하도록 바꿀지, 아니면 orphan 적재를 수용할지 오너 결정. 전자가 D5=A 본문·주석 의도에 부합.
- **백엔드 테스트 실행 방식**: `python -m pytest` 필수. CI/스크립트가 이 방식인지 확인 권장(재현성).

## Reproduction

```bash
# 1) 백엔드 전체(PYTHONPATH 주의: python -m 필수)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider 2>&1 | tail -3
#   기대: 1118 passed, 48 skipped, 273 subtests passed

# 2) report repair 회귀(양방향)
python3 -m pytest tests/test_writing_report.py tests/test_writing_report_live_diag.py -q

# 3) 프론트 전체
cd frontend && npm test -- --run 2>&1 | tail -5
#   기대: Test Files 8 passed / Tests 116 passed

# 4) C blocking 재현(회귀 부재 확인)
grep -nE "progress|setProgress|근거 주장|candidate-summary" frontend/src/writing/WritingPanel.test.tsx
#   기대: candidate_claims: [] (fixture) 1건만, progress/summary 렌더 검증 0건

# 5) Q1 blocking 재현(코드 경로)
sed -n '513,531p' frontend/src/api/client.ts   # ensureSourceRefCatalog: skip 516, 순차 POST 519-529

# 6) D5=A 의도 대조
sed -n '61,70p;104p;117,118p' docs/plans/05-writing-accept-decisions.md
```

---

## Post-verification closure (SoT v1.7.7, 2026-07-18)

오너가 본 검증의 blocking 3건을 즉시 닫고, hardening/efficiency 중 핵심(D5=A 정렬)까지 함께 처리했다. 이 섹션은 위 v1.7.6 audit 결과가 **어떻게 닫혔는지**를 추적한다(본 audit 본문은 그 시점 스냅샷으로 보존).

- **C-1/C-2 (progress coarse 단계·candidate summary 렌더 회귀 부재) → CLOSED**: `WritingPanel.test.tsx`에 under-strict 회귀 2건 추가. (a) deferred fetch로 generate/Gate 단계의 in-flight progress 문구를 관찰, (b) claims가 있는 후보의 "근거 주장 N개" 표시 검증. 각 렌더 제거 시 해당 테스트만 단독 실패(mutation bite) 실증.
- **Q1 (`ensureSourceRefCatalog` 부분실패 자가복구 불가) → CLOSED**: `ensureSourceRefCatalog`를 **coverage 기반 멱등 빌드**로 재작성 — 기존 source_ref의 offset을 Set으로 추적해 **누락 블록만 생성**, 부분 실패 후 재시도가 자가복구(잔존 스킵이 아니라 누락만 채움), mid-loop 실패는 throw해 partial catalog로 run하지 않음, anchorable 블록 0이면 friendly 422로 조기 차단. `AnalysisTrigger`에 **busyRef**(useRef) 더블클릭 가드 추가(WritingPanel 패턴과 일치). 회귀 3건(self-heal·전부-degenerate·더블클릭), self-heal mutation bite 실증.
- **D5=A 완전 정렬 (오너 결정) → CLOSED**: 검증이 확증한 "accept의 pending job orphan + 같은 snapshot 재분석 시 candidate 중복 적산"을 닫기 위해 **analysis job 멱등 key를 snapshot 유도(`analyze:{snapshot_id}`)로 개정**. `accept.py::analysis_job_key`와 프론트 `client.ts::analyzeVersion`이 동일 literal을 파생 → `create_job`의 `(project, snapshot, key)` 멱등이 **snapshot당 한 job**으로 수렴(orphan 0·재클릭 중복 후보 0·이미 SUCCEEDED면 재추출 없이 기존 후보 반환·accept가 심은 `writing_candidate_report`도 run에서 소비). **save key는 `writing-accept:{idempotency_key}` 무변**(정본 version replay 보존). 원 D4=A `writing-accept:{key}` analysis literal 개정. 회귀 `test_writing_accept.py::test_analysis_job_key_is_snapshot_scoped_and_shared_with_trigger`, 프론트 deterministic-key pin 단언(`analyze:s1`).

### Closure 재검증 (검증자 직접, 2026-07-18)

- 백엔드 `python3 -m pytest --ignore=tests/test_memory_mongo.py` → **1119 passed / 48 skipped / 273 subtests** (v1.7.6의 1118 + snapshot-scoped 회귀 1). 작업 AI 예상치 일치.
- 프론트 `vitest run` → **8 files / 121 passed** (AnalysisTrigger 10 = 7+3 회귀, WritingPanel +2 C 회귀). 작업 AI 예상치 일치.
- 3개 blocking 각 under-strict 회귀 존재 확인(self-heal·progress 렌더·summary 렌더), accept↔trigger 동일 literal(`analyze:{snapshot_id}`) 코드 직조회(`accept.py:21`, `client.ts` analyzeVersion).

### Closure 후 Verdict

**합격(Pass)** — v1.7.6의 3개 blocking이 v1.7.7에서 모두 닫혔고(under-strict 회귀 + mutation bite), D5=A "같은 job 소비" 의도가 실현됐다. 남은 hardening(degenerate 전부 skip→422 엣지, describeWritingError dead-branch 매처, 헤더 링크 회귀)과 efficiency(full-span catalog 정밀도, catalog 매번 GET)는 non-blocking 후보로 추적만 유지한다.

### 미배포 (outstanding)

- application 이미지가 `accept.py` 변경 전 빌드라 실행 중 스택은 구 accept 동작. D5=A 재클릭 dedup은 application 재빌드 후 브라우저에서 관측 가능. (독립 검증은 코드 + 단위/회귀 테스트로 확증했고, 라이브 재확인은 오너/작업 AI가 스택 재빌드 시 수행.)

