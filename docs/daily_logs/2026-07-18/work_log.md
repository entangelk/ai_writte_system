# Work Log — 2026-07-18

## Goals

- HANDOFF·2026-07-17 로그가 지정한 다음 작업 중 오너가 선택한 트랙(**gate finding 라이브 유발**)을 진행한다.
- 2026-07-17 Review Inbox dogfood가 라이브로 못 채운 유일한 표면 — gate finding **resolve/dismiss**(7 write action 중 2개) — 을 실 스택·실 12B로 관통한다.
- 프로덕션 코드는 무변으로 둔다(라이브 스모크는 기존 엔드포인트 경로 소비).

## User Decisions and Rationale

- **다음 트랙 = gate finding 라이브 유발**: UX-1 기본 루프(A+C+B)가 코드·라이브로 사실상 닫힌 상태에서 남은 세 트랙(OPS-1 Ready+dogfood 착수 / gate finding 라이브 유발 / Phase 6 UI 잔여) 중 오너가 gate finding 라이브 유발을 택했다. 근거: 2026-07-17 dogfood가 7 write action 중 5개만 라이브 관통했고, resolve/dismiss는 엔드포인트·어포던스·유닛 커버로 뒷받침되나 **라이브 gate reject 유발이 상류 검색/인덱싱(빈 package) 의존**이라 미실행으로 남았다. 나머지 두 트랙(OPS-1 Ready 승격, Phase 6 UI 일반화)은 오너 결정/추측 구현 금지 영역이라 이 트랙이 즉시 실행 가능한 유일한 관통 마무리다.

## Completed work

### gate finding 라이브 유발 + resolve/dismiss 관통 (라이브 스모크)

**착수 전 계약 범위화 (코드 재도출로 확정한 것)**

- gate finding은 `POST /projects/{id}/context-search`가 Context Gate `reject` 시에만 `persist_rejection`으로 영속화된다([main.py:2477-2490](../../../services/application/app/main.py#L2477)). reject를 유발하려면 package에 아이템이 최소 1개 있어야 한다.
- **`budget_exceeded`는 이 엔드포인트에서 도달 불가**(2026-07-17 max_tokens=1 시도 실패의 근본 원인): `_apply_budget`이 예산 초과 아이템을 package에 넣기 전에 잘라내므로 included total은 항상 budget 이하 → gate의 `total > max_tokens`는 build/gate가 같은 request budget을 쓰는 한 참이 될 수 없다.
- **도달 가능한 결정적 reject = `stale_item`(archived draft)**: `_gate_stale_findings`가 `draft.archived`를 재유도. 기존 회귀 [tests/test_context_search.py:750](../../../tests/test_context_search.py#L750)이 `evaluate_context_gate`+archive→`stale_item` reject를 이미 잠근다.
- **`current_scene`(Mongo-direct)를 써야 아이템이 gate까지 도달**: source-block **vector** hit은 retrieval-time stale 가드로 archived를 package에서 배제([test_context_search_shared_index.py:212](../../../tests/test_context_search_shared_index.py#L212)) → 빈 package → pass(어제 시나리오). `current_scene`은 `_run_mongo_step`이 배제 가드 없이 서빙 → archived draft scene이 package에 남아 gate `stale_item` reject.

**신규 파일**

- `scripts/phase6_gate_finding_live_smoke.py` — 다른 `phaseX_..._live_smoke.py`와 동형의 HTTP-only 라이브 스모크. project→draft→version(단일 단락)→draft archive→서로 다른 idempotency_key로 `context-search` 2회(각 `stale_item` reject 유발, planner 변동 흡수 재시도)→review-inbox 어포던스 확인→detail read→첫 finding **resolve**·둘째 **dismiss**→open list 서버 재조회. `smoke_succeeded`가 draft archived·두 reject·open≥2·resolve `resolved`·dismiss `dismissed`·`after==before−2`를 exit code로 검사.

**라이브 실행 (실 스택 + 실 12B)**

- 풀스택 기동: base + llama override + scratchpad `-m` 캐시 blob override(2026-07-17 `-hf` 재다운로드 정체 우회, snapshot `f6e7774e`). application/frontend는 07-17 재빌드본 재사용(프로덕션 무변→재빌드 불요). 전 서비스 healthy(llama 44s), gateway ready, llama가 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` 서빙 확인.
- **application 직접(`:8000`)**: exit 0 — 두 search `stale_item` reject·2 gate finding 영속·어포던스 `{resolve:true,dismiss:true}`·detail `stale_item`·resolve 200/`resolved`·dismiss 200/`dismissed`·after 0.
- **브라우저 동등(프론트 nginx `/api` 프록시, `:5173/api`)**: exit 0 — 동일 결과. 실제 브라우저 경로 그대로 관통.
- 상세 기록: `docs/verifications/2026-07-18/gate_finding_live_trigger.md`.

**성과**: Review Inbox **7/7 write action 전부 라이브 검증 완료**(07-17의 5/7 + 오늘의 resolve/dismiss 2/7).

## Issues found

### 첫 실행 판정식이 finding 수를 과소 가정 (수정 완료)

- 문제: 초기 RAW_TEXT가 3개 단락이라 각 search가 단락/블록당 `stale_item` 1개씩 총 3개(ordinal 0/1/2)를 내 2 search=6 findings가 됐다. "정확히 2개" 가정 판정식이 exit 1(기능은 이미 resolve/dismiss 200 성공).
- 해결: RAW_TEXT를 단일 단락으로(search당 1 finding) + 판정식을 `inbox_open_findings_after == before − 2`로 견고화 → 클린 exit 0. 블록 수가 늘어도 올바르게 동작.

## Decisions

- **프로덕션/저장소 코드 무변, 스모크 스크립트만 추가**: gate finding 유발은 기존 엔드포인트(`context-search`/gate-findings 라이프사이클) 경로를 소비할 뿐 새 백엔드 동작이 아니다. `budget_exceeded` dead-branch도 관찰로만 기록(방어적 코드 유지, 변경 아님).
- **`current_scene`+archived draft를 결정적 reject 레버로 선택**: vector 경로는 retrieval-time에 archived를 배제해 빈 package→pass가 되므로 gate까지 도달하는 Mongo-direct scene을 썼다. 기존 회귀가 이미 이 gate 분기를 잠그고 있어 sandbox에서 레시피를 사전 검증할 수 있었다.
- **스택 유지**: 2026-07-17 선례대로 오너 브라우저 확인을 위해 실행 상태로 둔다(종료 명령은 검증 기록 Outstanding에 명시).

## Verification

- **라이브 스모크 2경로 exit 0**: application 직접·브라우저 동등 프록시 모두 gate finding 유발→resolve/dismiss→open 0 관통. 상세: `docs/verifications/2026-07-18/gate_finding_live_trigger.md`.
- **레시피 사전 검증(sandbox)**: `test_gate_rejects_stale_item_when_project_archived_after_build`([test_context_search.py:750](../../../tests/test_context_search.py#L750))가 엔드포인트가 호출하는 `evaluate_context_gate`+archive→`stale_item` reject를 이미 잠금. `current_scene` Mongo-direct 무배제 경로도 기존 코드로 확인. 스크립트 `py_compile` PASS.
- **프로덕션/scope diff 0**: 변경은 신규 `scripts/phase6_gate_finding_live_smoke.py` 1개뿐. `services/`·`tests/`·`schemas/`·`docker-compose*.yml` 무변.

## Next steps

- **`OPS-1` Ready 승격 + dogfood 착수(오너 결정)**: 실 12B 관통이 gate finding 표면까지 완결됐으므로 OPS-1의 "실 12B 관통 확인" 조건은 충족. Ready 승격·본격 dogfood 착수는 오너 결정.
- **남은 Phase 6 UI**: memory card·미회수 foreshadowing view(별도 화면), 부분 승인/retry·merge/split의 event/open_question 일반화(오너 결정 대기).
- **스택 회수**: 브라우저 확인 후 `docker compose ... down`(Mongo volume 유지).

---

## Task 2 — 테스트베드 사용가능화 슬라이스 A+B+C (오너 dogfood 발견)

### Goals

- 오너가 실 브라우저 dogfood에서 발견한 3건을 해결해 테스트베드를 실제로 관측·조작 가능하게 만든다: (A) 이어쓰기 502 "report field must be an array", (B) 검토 트리거 버튼 부재·집필↔검토 분리, (C) 진행/판정/에러가 안 보이는 블랙박스.
- 차후(오너 명시 보류): 멀티턴 대화, 스트리밍 모드, 2중 탭 작업공간 세분화.

### User Decisions and Rationale

- **범위 = A+B+C 통합**(오너 선택): 세 문제가 "테스트를 위해 먼저 충족돼야 할 것"으로 묶여 한 슬라이스로 처리.
- **502 처리 = UI 재시도 + 백엔드 2차 repair**(오너 선택): 세 후보(파서 관대화 null→[] / UI 재시도만 / UI+2차 repair) 중. 근거로 제시·수용: 502가 **간헐적·입력 의존**(새 장면 generate 4/4 성공)이라 결정적 버그가 아니며, report가 간헐 실패이므로 repair를 1→2회로 늘려 실패율을 낮추되 strict 계약(엄격 스키마)은 건드리지 않고, UI에서 사람이 읽을 안내+재시도로 dead-end를 없앤다. 파서 관대화(null→[])는 계약 완화라 이번엔 보류.

### Completed work

**착수 전 진단(코드 재도출 + 라이브)**

- 502 원인 = `report.py:parse_report`의 strict 배열 검사([report.py](../../../services/application/app/writing/report.py))를 12B가 가끔 위반(배열 필드를 null/객체로) + 1회 repair도 실패. generate가 report를 내부 호출하므로 실패 시 후보 전체 폐기. **간헐성 실측**: 새 장면 generate 4/4 성공(claims 3/4/4/3).
- 검토 트리거 = accept는 pending job만 만들고 추출은 별도 `run_job`. 집필 화면에 분석 실행 버튼·검토함 링크 부재.
- **B 라이브 관통에서 결정적 400 발견**: 분석 run이 4/4 `400 "source_ref catalog is required"` — 추출은 snapshot에 source_ref가 선행돼야 하는데(candidate를 source_ref에 anchor) 내 첫 `analyzeSnapshot`이 이 단계를 건너뜀. source_ref 생성은 **offset만** 필요(서버가 quote/hash 도출)하고 블록이 offset을 노출하므로 클라이언트에서 블록별 생성이 가능.

**A — 502 견고화**

- 백엔드 [report.py](../../../services/application/app/writing/report.py): report enrich를 `first→1 repair→502`에서 **bounded repair loop(`MAX_REPORT_REPAIRS=2`)**로. 각 repair usage 누적(aggregate budget 회계 무변), strict schema/literal 검증 무변. 계약 D4=A "strict+1 repair"→"strict+최대 2 repair"로 개정(SoT v1.7.6).
- 진단 [report_live_diag.py](../../../services/application/app/writing/report_live_diag.py): production `enrich_metered` 재사용이라 2 repair를 반영 — 최종 repair raw 노출(`caps[1]`→`caps[-1]`).
- 프론트 [client.ts](../../../frontend/src/api/client.ts) `describeWritingError`: invalid_candidate_report/revision/gate·503/504/5xx를 사람이 읽을 안내+`retryable`로 매핑. WritingPanel이 실패 시 "다시 생성" 버튼 노출(instruction 보존 재호출).

**B — 검토 트리거 + 진입**

- 신규 [AnalysisTrigger.tsx](../../../frontend/src/review/AnalysisTrigger.tsx): 집필 화면 "이 원고 분석" → 최신 version 분석 → candidate → "검토함에서 확인" 링크. blocked 상태(보관/미저장 변경/version 없음) 명시.
- [client.ts](../../../frontend/src/api/client.ts) `analyzeVersion`: catalog가 비면 version detail의 **블록별 full-span source_ref를 먼저 생성**한 뒤 job create→run(catalog 400 해소). 이미 있으면 build 생략.
- [DraftEditor.tsx](../../../frontend/src/drafts/DraftEditor.tsx): 헤더에 "검토함 →" 링크 + AnalysisTrigger 렌더.

**C — 관측성**

- [WritingPanel.tsx](../../../frontend/src/writing/WritingPanel.tsx): 서버측 파이프라인을 coarse 단계로 표시(`progress`: 근거 검색·초안 생성 → Gate 평가 → 자동 개선, spinner) + 후보에 "근거 주장 N개 · 기억 후보 · 위험 지적" 요약. friendly 에러+재시도(A와 공유).

### Issues found

- **결정적 400 "source_ref catalog is required"**(위 진단): 첫 `analyzeSnapshot`이 source_ref 선행 생성을 누락. `analyzeVersion`으로 블록별 catalog 자동 생성해 해소. 라이브에서 3 블록→3 source_ref→run 200→candidate 3 확인.
- report 진단이 production `enrich_metered`를 재사용하므로 2차 repair로 호출 수가 3이 돼 진단 테스트 2건이 2 출력만 큐잉해 깨짐 → 3 출력로 갱신(내 변경의 collateral).

### Decisions

- **report repair 1→2, strict 계약 무변**: 간헐 실패율만 낮춤. 파서 관대화(null→[])는 계약 완화라 보류.
- **source_ref catalog는 클라이언트에서 자동 빌드(새 백엔드 표면 없이)**: 생성은 offset만 필요하고 블록이 offset을 노출하므로 기존 프리미티브 소비로 충분. 재실행 시 catalog가 있으면 재생성 생략(중복 회피).
- **프로덕션 코드 최소 변경**: 백엔드는 report repair 횟수 1곳만. 나머지는 프론트(소비) + 테스트.

### Verification

- **백엔드**: `pytest --ignore=tests/test_memory_mongo.py` → **1118 passed / 48 skipped / 273 subtests**(report 2차 repair 양방향 회귀 포함). `gen:api` schema diff **0**(OpenAPI 무변).
- **프론트**: `npm test -- --run` → **116 passed / 8 files**(AnalysisTrigger 7·WritingPanel report retry 1 추가). `npm run build` → 94 modules.
- **라이브(실 12B, 브라우저 동등 `:5173/api` + 직접 `:8000`)**: generate 2/2 성공(claims 3), `analyzeVersion` catalog 3 생성→run 200→candidate 3→검토함 items 3(어제 400 해소). 이미지 application+frontend 재빌드·재배포, 번들에 새 UI 문자열 확인.

### 독립 검증 조건부 합격 → blocking 3건 closure

오너가 독립 검증을 요청·완료했다(39-에이전트 adversarial + 테스트 재실행 + 코드 재도출, `docs/verifications/2026-07-18/testbed_abc_slice.md`). **판정 조건부 합격** — 기능·work_log 주장(백엔드 1118·프론트 116)은 정확히 재현됐고 A(report 2차 repair)는 boundary 완전 잠금으로 합격. blocking 3건을 오너 지시로 닫았다:

- **C-1/C-2(계약 의무 렌더 회귀 부재)**: SoT v1.7.6 C가 슬라이스 계약으로 규정한 progress coarse 단계·candidate summary 표시에 회귀가 없었다(boundary 빈 칸). WritingPanel에 under-strict 회귀 2건 추가 — (1) deferred fetch로 generate/Gate 단계 progress 문구를 in-flight 관찰, (2) claims 있는 후보로 "근거 주장 N개" 표시. **mutation bite**: 각 setProgress/summary 렌더 제거 시 해당 테스트만 단독 실패 실증.
- **Q1(`ensureSourceRefCatalog` 부분실패 자가복구 불가)**: "refs 존재하면 스킵"이 부분 빌드 후 재시도에서 catalog를 영구 불완전하게 두는 gap이었다. **coverage 기반 멱등 빌드**로 재작성 — 블록 offset 매칭으로 **누락 블록만 생성**해 부분 실패가 재시도로 자가복구되고, mid-loop 실패는 그대로 throw돼 partial catalog로 run하지 않는다. 전부-degenerate(anchorable 블록 0)면 friendly 422로 조기 차단. AnalysisTrigger에 **busyRef**(더블클릭 가드, WritingPanel과 일관) 추가. 회귀 3건(self-heal·전부-degenerate·더블클릭) 추가, self-heal **mutation bite**(구 skip 로직으로 되돌리면 단독 실패) 실증.

프론트 회귀 116→**121**(AnalysisTrigger 7→10·WritingPanel 34→36), build·gen:api diff 0. 프론트 재빌드·재배포, happy-path 라이브 재확인(catalog 3→candidate 3, 회귀 없음).

### D5=A 정렬 — 오너 결정=완전 정렬, 구현 완료

검증자가 확증한 "accept의 pending job orphan + 같은 snapshot 재분석 시 candidate 중복 적산"을 오너 결정(완전 D5=A 정렬)으로 닫았다.

- **결정**: analysis job 멱등 key를 **snapshot 유도(`analyze:{snapshot_id}`)**로 개정 — 원 D4=A `writing-accept:{key}` analysis literal 개정(save key는 무변). accept([accept.py `analysis_job_key`](../../../services/application/app/writing/accept.py))와 프론트([client.ts `analyzeVersion`](../../../frontend/src/api/client.ts))가 동일 literal을 파생.
- **효과**: `create_job` `(project,snapshot,key)` 멱등이 **snapshot당 한 job**으로 수렴 — accept가 심은 job을 trigger가 재사용(orphan 0), 재클릭도 같은 job(중복 후보 0; 이미 SUCCEEDED면 재추출 없이 기존 후보 반환), accept가 job에 실은 `writing_candidate_report`도 run에서 소비(효율성 #14 부수 해소). accept-replay 멱등 보존(같은 accept→같은 snapshot→같은 job).
- **회귀**: 백엔드 `test_writing_accept.py::test_analysis_job_key_is_snapshot_scoped_and_shared_with_trigger`(snapshot-scope key·trigger create_job 재사용·job 1개). 프론트 AnalysisTrigger 첫 테스트에 deterministic key(`analyze:s1`) pin(random uuid 회귀 bite). 기존 accept replay 회귀 무영향. 계약 개정 기록: `docs/plans/05-writing-accept-decisions.md`(2026-07-18 amendment) + SoT v1.7.7.

### 남은 비차단/효율성 소견 (오너 판단, 미구현)

- full-span catalog anchor 정밀도(#12), 이어쓰기마다 catalog 재빌드(#13 — 단, 재클릭 재추출은 D5=A 정렬로 해소), `describeWritingError` dead 매처(#8), DraftEditor 검토함 링크 회귀(#11 nit) 등은 오너 판단 영역으로 남긴다.

### Next steps
- 오너 브라우저 dogfood로 A/B/C 체감 확인 → 남은 UX(멀티턴·스트리밍·2중 탭)는 별도 슬라이스.
- gate finding 라이브 유발(Task 1)과 함께 `OPS-1` Ready·dogfood 착수 오너 결정.
- 스택 실행 중(오너 종료 미선택).
