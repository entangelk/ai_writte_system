# Work Log — 2026-07-18

## Task — W1 독립 검증 blocking closure

### Goals

- 독립 검증 `docs/verifications/2026-07-18/w1_split_workspace.md`의 blocking B1~B6을 모두 닫는다.
- 데이터 손실 수정은 red-first 양방향 회귀로 잠그고 backend/OpenAPI/W0 schema를 건드리지 않는다.

### User Decisions and Rationale

- **옵션 A 진행**: 오너가 검증 기록 확인 후 blocking 수정·회귀 보강·커밋을 지시했다. owner 해석이 필요한 C1(tab 전환 시 candidate/source query 삭제)은 현 의미를 유지하고, 단순 표시 정확성 결함 C2(source notice 잔류)는 함께 보강했다.

### Completed work

- **B1 데이터 손실 폐쇄**: cross-Draft source `navigate()` 앞에 dirty confirm을 추가했다. 취소는 현재 draft/본문/query 이동을 보존하고 승인 후에만 target Draft로 이동한다.
- **동일 root pattern sweep**: SPA Link는 `beforeunload`를 우회하므로 editor 목록 링크와 Analysis/Review rail의 검토함·detail 링크에도 parent의 공통 `allowNavigationAway` guard를 전달했다.
- **B2~B6 named 회귀**: 상태줄의 저장/analysis/pending 전이, reject 전용 endpoint+서버 재조회, same-Draft dirty cancel→confirm, project 어디에도 없는 snapshot error, quote mismatch와 content-hash mismatch를 각각 잠갔다.
- **C2 표시 정확성**: text edit, save 성공, 수동 version switch, Writing accept reload, route Draft reload에서 `sourceNotice`를 clear해 이전 version의 근거 문구가 남지 않게 했다.
- 검증 기록은 `b0d9203`에 대한 독립 감사 원문/conditional verdict 그대로 보존하고 closure 결과는 SoT v1.7.12·HANDOFF·이 로그에 분리 기록했다.

### Issues found

- 원 결함은 source cross-Draft 한 분기만의 문제가 아니라 SPA navigation이 `beforeunload`를 우회하는 공통 패턴이었다. `rg '<Link|navigate\('` + `git blame`으로 W1 신규 Review rail 링크와 기존 editor back link까지 확인해 공통 guard로 닫았다.
- 최초 상태줄 fixture가 실제 ReviewInbox item 필수 필드 없이 count만 흉내 내 rail 렌더에서 실패했다. production shape(confidence/type/actions 포함)로 고쳐 public consumer와 동형으로 만들었다.

### Decisions

- **C1 유지**: writing/analysis tab으로 떠날 때 candidate/source query를 지우는 현 동작은 “숨은 source 자동 재점프 방지”와 “review 컨텍스트 보존” 사이 owner fork다. 이번 blocking closure에서 의미를 바꾸지 않았다.
- **기타 hardening 보류**: ARIA tab controls, 모바일 scroll, gate finding count 정의, action 후 reload 실패 UX, randomUUID guard는 현재 정본 의무가 아니므로 별도 후속 후보로 유지한다.

### Verification

- red-first: 원 `b0d9203` 코드에서 cross-Draft dirty source가 confirm **0회**로 이동해 회귀 실패; source notice도 version 전환 뒤 잔류해 실패. 수정 후 green.
- focused: DraftEditor 35 + WorkspaceReviewPanel 5 = **40 passed/2 files**.
- W1 관련: DraftEditor 35 + WorkspaceReviewPanel 5 + AnalysisTrigger 14 = **54 passed/3 files**.
- full frontend: **139 passed/9 files**.
- build: TypeScript/Vite PASS, **95 modules**.
- backend/OpenAPI/W0 schema diff 0, `git diff --check` PASS.

### Next steps

- 추가 승인 없이 W2 ProjectBrief onboarding+canonical overview 착수. 독립 재검증 전까지 W1 verification의 원 conditional verdict은 역사적 상태로 읽는다.

---

## Task — Writing Workspace V2 W1 split workspace

### Goals

- W0가 지정한 기존 DraftEditor route 안에서 editor+docked right rail(`이어쓰기|분석|검토`)을 구현한다.
- tab/candidate/source 상태를 URL로 복원하고 source quote를 exact version/offset으로 선택하며 stale/latest를 숨기지 않는다.
- 기존 backend API/action을 재사용하고 W2 ProjectBrief·W3 ordered unit runtime을 선행 구현하지 않는다.

### User Decisions and Rationale

- **W1 추가 승인 없이 진행**: 오너가 W0 인계의 고정 순서에 따라 W1 착수를 승인했다. 이미 확정된 D4=A와 W1 수용 기준을 구현했으며 새 architecture/public backend fork는 만들지 않았다.

### Completed work

- `DraftEditor.tsx`: 넓은 화면 2열 editor+sticky rail, 42rem 이하 같은 tab 정보구조의 단일 열. 상태줄은 저장 상태, analysis `idle|running|failed|complete`, 검토 탭에서 서버 재조회한 project pending count를 구분한다.
- `WorkspaceReviewPanel.tsx`: 기존 review-inbox list/detail API를 rail에서 소비하고 `panel/candidate/source` query를 갱신·복원한다. candidate confirm/reject는 서버 `{action,eligible,reason}`을 재계산 없이 사용하고 성공 후 inbox를 재조회한다. edit/merge/split 전체 표면은 기존 detail route 링크로 유지한다.
- source jump: pointer `snapshot_id`를 현재 Draft versions에 먼저 대조하고 없으면 project의 다른 Draft version 목록에서 찾는다. exact version의 `quote`와 `content_hash`가 pointer와 다르면 이동하지 않는다. 서버 raw offset(Unicode code point)을 브라우저 textarea selection(UTF-16 code unit)으로 변환해 이모지 앞 근거도 정확히 선택한다. latest와 historical version 문구를 분리한다.
- `AnalysisTrigger.tsx`: 실행 상태 callback을 추가해 rail이 unmount돼도 parent status가 유지되며 snapshot이 바뀔 때만 idle로 초기화한다.
- `styles.css`: docked rail/tab/status/source notice와 mobile 단일 열을 추가했다. backend, OpenAPI 생성물, W0 schema는 변경하지 않았다.

### Issues found

- **offset 단위 차이**: Core SOT offset은 raw Unicode code point지만 textarea `selectionStart/End`는 UTF-16 code unit이다. 단순 숫자 대입은 선행 astral 문자(emoji) 뒤에서 한 칸씩 어긋난다. code-point span을 quote 검증한 뒤 UTF-16 길이로 변환하고 선행 emoji 회귀로 잠갔다.
- **다른 Draft source query 유실 가능성**: source 버튼이 query 갱신과 route 이동을 같은 event에서 수행하면 이전 query snapshot을 읽을 수 있다. 이동 URL에서 `panel=review`와 `source`를 명시하고 target Draft에서 review panel을 remount해 detail/source 복원을 다시 실행한다.

### Decisions

- **backend envelope 확장 없음**: review source pointer에 draft/version을 추가하지 않고 기존 `listDrafts`+`listDraftVersions`의 `snapshot_id`로 target을 찾는다. W1의 기존 API 재사용 경계를 지키며 source authority는 immutable snapshot에 둔다.
- **URL이 복원 정본**: component-only tab state 대신 `panel`, candidate detail은 `candidate`, exact source는 `source` query로 둔다. 미해결 pointer나 quote/hash mismatch는 selection을 만들지 않는다.
- **좁은 화면도 같은 정보구조**: 별도 mobile 기능 축소 없이 rail tab을 editor 위로 이동한다.

### Verification

- focused: `npx vitest run src/drafts/DraftEditor.test.tsx src/review/WorkspaceReviewPanel.test.tsx --reporter=verbose` → **32 passed/2 files**.
- full frontend: `npm test` → **130 passed/9 files**.
- build: `npm run build` → TypeScript + Vite PASS, **95 modules**.
- contract/scope: backend·OpenAPI·schema diff 0, `git diff --check` PASS.
- routine self-verification이므로 별도 `docs/verifications/` 기록은 만들지 않았다.

### Next steps

- W2: W0 §1의 ProjectBrief append-only version/API를 runtime+OpenAPI+양방향 회귀로 구현하고 onboarding+canonical overview를 연결한다. clear는 “이력 보존”으로 설명한다.
- 이후 고정 순서: W3 ordered unit/intent → W4 project export. W3 의미를 W2에서 미리 구현하지 않는다.

---

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
- 독립 검증과 커밋이 끝난 D5=A snapshot-scoped analysis job 변경을 application/frontend에 재배포하고, 같은 snapshot 재호출이 job 1개·candidate 중복 0으로 수렴하는지 라이브에서 닫는다.
- 독립 검증이 non-blocking으로 남긴 accept `writing_candidate_report` 소비 축을 실 12B 라이브로 보강한 뒤 검증 기록·HANDOFF와 함께 커밋한다.
- 차후(오너 명시 보류): 멀티턴 대화, 스트리밍 모드, 2중 탭 작업공간 세분화.

### User Decisions and Rationale

- **범위 = A+B+C 통합**(오너 선택): 세 문제가 "테스트를 위해 먼저 충족돼야 할 것"으로 묶여 한 슬라이스로 처리.
- **502 처리 = UI 재시도 + 백엔드 2차 repair**(오너 선택): 세 후보(파서 관대화 null→[] / UI 재시도만 / UI+2차 repair) 중. 근거로 제시·수용: 502가 **간헐적·입력 의존**(새 장면 generate 4/4 성공)이라 결정적 버그가 아니며, report가 간헐 실패이므로 repair를 1→2회로 늘려 실패율을 낮추되 strict 계약(엄격 스키마)은 건드리지 않고, UI에서 사람이 읽을 안내+재시도로 dead-end를 없앤다. 파서 관대화(null→[])는 계약 완화라 이번엔 보류.
- **D5=A 검증 hardening까지 보강 후 커밋**(오너 요청): 독립 검증의 핵심 판정은 합격이지만 accept report 소비가 코드 추론으로만 남았으므로, 문구만 낮추지 않고 accept→동일 job trigger→run 라이브 1회로 마지막 축을 닫아 문서 3개를 함께 커밋한다.

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

### D5=A 재배포·라이브 closure

- **배포**: 실행 컨테이너 label에서 기존 compose 조합(base + llama + cached-GGUF scratchpad override)을 재도출했다. Compose 2.40.2 Bake 경로가 `doBuildBake` slice-bounds panic으로 즉시 실패해 실행 컨테이너는 건드리지 않은 채, 저장소 선례대로 `COMPOSE_BAKE=false`로 application/frontend를 재빌드했다(application `sha256:b40e529a...`, frontend `sha256:02e9314d...`, Vite 94 modules). 동일 조합으로 두 서비스만 재생성했고 application healthy, frontend와 application HTTP 200을 확인했다.
- **브라우저 동등 라이브**: `http://127.0.0.1:5173/api` 경로에서 별도 프로젝트/원고/snapshot(`6a5ae7f6b339f88750c0a92c`)을 만들고 저장 block offset으로 source_ref catalog를 구성했다. `analyze:{snapshot_id}` create→run을 반복한 뒤 추가 replay로 공개 응답을 고정했다: job ID `6a5ae7f6b339f88750c0a92f` 동일, create/run `idempotent_replay=true`, candidate **2→2**, candidate ID 집합 불변·유일. Mongo 정본 대조도 해당 snapshot **analysis_jobs=1**, 해당 job **analysis_candidates=2**, candidate ID 중복 0. 따라서 같은 snapshot 재클릭의 job/candidate 적산이 라이브에서 발생하지 않았다.
- **검증 수치 인계 확인**: 직전 독립 검증자가 `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` **1119 passed / 48 skipped / 273 subtests**, 프론트 Vitest **121 passed / 8 files**, build·schema diff 0을 재현하고 커밋 `965e34e`에 반영했다. 이번 작업은 그 clean commit을 배포하고 live D5를 닫는 범위라 전체 스위트를 중복 실행하지 않았다.
- **운영 이슈(비차단)**: frontend nginx는 `127.0.0.1:80`/호스트 `:5173`에서 200이나 healthcheck `http://localhost/`가 Alpine 컨테이너에서 `::1`로 해석되어 connection refused, compose status만 `unhealthy`인 false-negative다. D5 동작과 무관하고 기존 설정이라 이번 범위에서는 수정하지 않았으며, 후속 운영 소수정으로 `127.0.0.1` 고정을 남긴다.

### D5=A 독립 검증 hardening — accept report 소비 라이브 closure

- 독립 검증 `docs/verifications/2026-07-18/d5a_live_deploy.md`는 배포·snapshot 재클릭 dedup을 **합격**시켰지만, 당시 Mongo 22개 job 중 `writing_candidate_report` 보유가 0이라 accept report 소비를 non-blocking 미실증으로 남겼다. 오너 요청에 따라 별도 프로젝트에서 해당 축을 추가 관통했다.
- 브라우저 동등 `:5173/api` + 실 12B: base 원고→`POST /writing/accept`가 Gate `pass`, snapshot `6a5aeb6ab339f88750c0a947`과 pending job `6a5aeb6ab339f88750c0a948` 생성. 저장 block offset으로 source_ref catalog를 만든 뒤 동일 `analyze:{snapshot_id}` create는 같은 job + `idempotent_replay=true`; 첫 run은 `false`(실제 소비), 둘째 run은 `true`.
- Mongo 정본: 해당 snapshot job **1**, job status `succeeded`, `writing_candidate_report` 존재. report claim `민아는 탁자 위에서 은빛 열쇠를 발견했다.`/event hint가 저장됐고, run candidate **1**의 payload도 같은 사건, ID 중복 0. accept report 저장→동일 job 재사용→runner 소비 전 축이 라이브로 닫혔다.

### 남은 비차단/효율성 소견 (오너 판단, 미구현)

- full-span catalog anchor 정밀도(#12), 이어쓰기마다 catalog 재빌드(#13 — 단, 재클릭 재추출은 D5=A 정렬로 해소), `describeWritingError` dead 매처(#8), DraftEditor 검토함 링크 회귀(#11 nit) 등은 오너 판단 영역으로 남긴다.

### Next steps
- 오너 브라우저 dogfood로 A/B/C 체감 확인 → 남은 UX(멀티턴·스트리밍·2중 탭)는 별도 슬라이스.
- gate finding 라이브 유발(Task 1)과 함께 `OPS-1` Ready·dogfood 착수 오너 결정.
- frontend healthcheck false-negative(`localhost`→`::1`)를 별도 운영 소수정으로 처리할지 결정.
- 스택 실행 중(오너 종료 미선택).

---

## Task 3 — 이어쓰기 후 재분석 `400 source_ref not found` 진단·보수

### Goals

- 오너 dogfood 재현(첫 분석 후보 미채택 → AI 이어쓰기 accept → 확장 snapshot 재분석)의 400 원인을 라이브 로그·Mongo 정본·코드 계약에서 재도출한다.
- 예방과 실패 복구에 필요한 오너 결정 경계를 분리하고, 승인안 C를 양방향 회귀·재배포·동일 job 라이브로 닫는다.

### Completed work

- application 로그에서 실제 실패를 프로젝트 `6a59899206eb78cecda6d4a6`, snapshot `6a5aeba0b339f88750c0a94f`, job `6a5aeba1b339f88750c0a950`으로 식별했다. 새 snapshot source_ref 생성 9건과 deterministic create는 모두 200이고 run만 400이었다.
- Mongo 정본 대조: 새 snapshot catalog는 9개 block span/quote/hash에 정확히 결박돼 있어 catalog 누락·부분 빌드가 아니다. job은 `failed/source_invalid`, detail `source_ref not found`.
- accept가 job에 저장한 `writing_candidate_report`는 생성 당시 구 snapshot `6a59899206eb78cecda6d4a9`의 `source_blocks` pointer 2개(block 3/4, 구 version/hash)를 보유한다. runner가 report를 새 snapshot에 붙이고(`runner.py:133-136`), prompt builder가 새 `source_ref_catalog`와 report를 나란히 직렬화한다(`prompt_builder.py:45-48`).
- strict extraction은 catalog 밖 anchor를 1회 repair한 뒤에도 invalid면 downstream resolver가 거절한다(`extractor.py:139-149`, `service.py:751-756`; SoT v1.6.19/§ Phase 2A의 의도된 fail-closed). raw provider output은 저장되지 않아 모델이 구 block pointer ID를 source_ref_id로 직접 복사했는지는 확정할 수 없지만, 성공한 accept-report 라이브(related pointer 비어 있음)와 달리 이번 실패 report만 구 source pointer를 함께 노출해 namespace 혼동이 강한 유발 요인이다.
- 재클릭 복구도 공개 API로 재현했다. deterministic create는 같은 failed job을 `idempotent_replay=true`로 반환하고, run은 HTTP 200 + `status=failed` + candidates `[]`로 재추출하지 않는다. `analyzeVersion`은 run job status를 검사하지 않고 candidate 수만 반환해 UI가 “새 후보 없음” 성공으로 오인한다.
- pattern sweep + blame: failed terminal/no re-run은 `tests/test_analysis_job_state.py::test_failed_is_terminal`의 **Fork B**와 runner replay 회귀로 의도적으로 잠겼다. 따라서 조용히 reset/retry를 구현하면 기존 owner-level 상태 계약과 충돌한다.

### Issues found

- **P1 — prompt namespace 충돌 가능성**: advisory report의 stable `related_context_pointers.document_id`(구 snapshot source block)와 현재 snapshot의 authoritative `source_ref_catalog.source_ref_id`가 같은 prompt에 들어가 12B가 anchor identity를 혼동할 수 있다. strict validator는 오염 저장을 막지만 사용자는 400 dead-end를 만난다.
- **P2 — D5=A와 FAILED terminal의 조합**: snapshot당 job 1개는 중복을 막지만, 한 번 실패한 job을 같은 snapshot에서 다시 실행할 수 없다. 현재 “다시 분석” 버튼은 실질 retry가 아니다.
- **P3 — terminal failure 응답 오판**: 첫 실패는 HTTP 400이라 보이지만 다음 클릭은 HTTP 200 failed envelope를 클라이언트가 성공/0 candidates로 처리한다.
- 첫 분석 후보를 승인·저장하지 않은 상태는 직접 원인이 아니다. 실패 job의 입력 충돌은 accept report의 구 snapshot source pointer와 새 catalog 사이에서 발생했다.

### User Decisions and Rationale

- 오너는 실검수 브리프의 **C(prompt 예방 + same-job 명시 retry + failed UX)**를 선택했다. strict source validation, 자동 remap 금지, repair 1회 상한, snapshot당 job 1개와 succeeded replay는 유지한다.
- 브리프는 새 기록 분류 `docs/live_review_briefs/2026-07-18/analysis_retry_after_accept.md`에 보존하고 `docs/README.md`에 역할을 등록했다.

### Completed implementation

- prompt: v1 보존 + 초기 `analysis_extract_v2`를 seed했으나 동일 실패 job 라이브에서 주의 문구만으로 `source_invalid`가 재발했다. 이미 seed된 v2를 덮어쓰지 않고 보존하고, exact candidate taxonomy/payload/full-anchor shape, advisory report→authoritative catalog 직렬화 순서, report identifier를 제외한 repair payload를 구조화한 **`analysis_extract_v3`**를 새 기본값으로 승격했다.
- backend: 상태 전이에 명시적 `FAILED→PENDING`만 추가하고 `retry_failed_job` + `POST /projects/{project_id}/analysis/jobs/{job_id}/retry`를 배선했다. failure fields clear, 다른 상태 409, cross-project/unknown 404. 일반 create/run replay는 failed를 자동 실행하지 않는다.
- frontend: create가 failed면 같은 job retry 후 run하며 run 응답이 HTTP 200이어도 `job.status !== succeeded`면 오류로 표시한다. succeeded replay는 retry하지 않는다. OpenAPI schema를 재생성했다.
- 양방향 회귀: prompt v1/v2/v3 불변 보존, report-before-catalog, repair catalog 격리, strict invalid anchor, failed same-ID reset/필드 clear, pending/running/succeeded retry 409, project 격리, frontend failed→retry→run, 200 failed 오판 방지, succeeded no-retry를 잠갔다.

### Live reinspection

- application/frontend 재빌드·재배포. 초기 v2 반례 뒤 v3로 application 재배포했다. v2 template 변경 시 startup `PromptTemplateConflict`가 발생해 immutable 보호가 작동함을 확인했고 v3 추가로 정상화했다.
- 원 실패 job `6a5aeba1b339f88750c0a950`: retry가 같은 ID로 pending/failure clear. 첫 v3 실제 run은 원 source_ref 오류 대신 비결정적 malformed JSON으로 1회 실패했으나, 진단 first output은 현재 catalog ID와 full anchor를 사용함을 확인했다. 다음 명시 retry/run이 **succeeded**, candidate **5개** 저장. 재클릭 run은 `idempotent_replay=true`, candidate ID 5개 불변·중복 0.
- health: application 200/healthy, frontend HTTP 200(기존 localhost→::1 healthcheck false-negative는 별도 비차단).

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1126 passed / 48 skipped / 276 subtests**.
- frontend: `npm test -- --run` → **8 files / 124 passed**; `npm run build` PASS(94 modules); `npm run gen:api` PASS.
- `git diff --check` PASS.
- 독립 검증 `docs/verifications/2026-07-18/analysis_retry_v3_live.md` 최종 **합격**. Mongo에서 원 job succeeded/failure null/report present/candidate 5 unique/snapshot job 1을 재도출했다. 커밋 전 재검토에서 repair payload key는 `authoritative_source_ref_catalog`인데 system prompt가 구 `original_user_payload`를 지칭하는 내부 literal 드리프트를 추가 발견해 교정했다. 구 report pointer fixture가 old ID 미노출·authoritative ID 노출·실제 payload key 지칭을 함께 잠그도록 회귀를 강화했다.

### Next steps

- 오너 브라우저에서 동일 원고의 “다시 분석” UX를 체감 확인한다. 비결정적 provider JSON 실패가 반복 관측되면 raw Analysis output 관측/품질은 별도 실검수 브리프로 연다.

---

## Task 4 — Writing Workspace UX 구조 개편 분석

### Goals

- 오너 dogfood에서 제기된 작품 시작 정보 부재, 이어쓰기 대상 모호성, editor↔review 왕복, 작품 overview·전체 export 부재를 개별 UI 불편이 아닌 정보구조/정본 경계 문제로 분석한다.
- 프롬프트 지시가 아니라 구조화 정본·명시 intent·validator·작업공간 layout으로 해결할 범위를 나누고 구현 전 decision brief를 남긴다.

### Completed work

- 현 정본/API/UI를 대조했다. `Project`는 name, `Draft`는 title만 있고 작품 brief·unit kind/order/parent가 없다. Writing은 `continue_scene + draft_patch`와 same-draft accept만 지원해 “현재 append”와 “다음 장 시작”을 구조적으로 구분하지 못한다.
- editor와 Review Inbox가 별도 route이고 source pointer의 editor selection/highlight 계약이 없다. Writing candidate는 component state라 route 이동/새로고침에서 미채택 산출을 잃을 수 있다.
- canonical memory list API는 존재하지만 frontend overview가 없다. 프로젝트 export는 ordered draft/version 선택 계약이 없어 현재 단일 version export를 안전하게 확장할 수 없다.
- 추가 UX 후보로 상태 바, 근거 점프, 이전/다음 원고 이동, pane/query 복원, responsive fallback, canonical/pending 권위 배지, 다음 미처리 candidate 이동, progressive onboarding을 도출했다.
- 신규 실검수 브리프 `docs/live_review_briefs/2026-07-18/writing_workspace_ux_restructure.md`에 D1~D6와 전체 접근 옵션, 추천, W0~W4 실행 순서와 수용 기준을 기록했다.

### Issues found

- UI-only split pane을 먼저 꾸미면 project brief, draft order, generation target authority가 없어 의미를 다시 뜯을 위험이 있다.
- 반대로 ProjectBrief·chapter tree·generation intent·overview·export를 한 번에 설계하면 dogfood feedback이 늦고 migration 표면이 과도하다.
- 작품 종합 화면에서 `needs_review`와 canonical을 혼합하면 승인 전 후보가 정본처럼 보이는 기존 권위 계약을 위반한다.
- 전체 export는 제목/생성 순서를 서사 순서로 추정해서는 안 되며 backend ordered-unit 계약이 선행돼야 한다.

### Decisions

- 오너가 작업자 권장 조합을 전부 확정했다: `D1=A(ProjectBrief 별도 정본), D2=A(최소 ordered unit), D3=C(append_current/start_next_unit 명시 intent), D4=A(editor+docked right rail), D5=A(canonical-only overview), D6=A(ordered latest export), 전체 접근=C(구조 세로 슬라이스)`.
- 결정 이유: prompt/UI 문구가 작품 권위·원고 순서·저장 target을 추론하게 두지 않고 정본과 명시 discriminator로 강제하되, big-bang 대신 dogfood 가능한 W0~W4 행동 단위로 검증한다.
- 프롬프트는 구조화 intent/authority를 반복 설명하는 defense-in-depth로 유지하고, 저장 target이나 권위 결정을 맡기지 않는다.
- SoT를 v1.7.9로 올리고 Product Shell·Writing 결정 계획·제품화 백로그를 같은 방향으로 정렬했다. runtime code/schema/API는 아직 v1.7.8과 동일하다.

### Next steps

- 다음 작업자는 추가 owner 승인 없이 W0 계약/migration slice를 시작한다.
- W0에서 ProjectBrief exact schema/API/version, ordered unit position/reorder/migration, `append_current|start_next_unit` request/accept/idempotency/원자성, 양방향 boundary matrix를 먼저 잠근다.
- W0 완료 뒤 W1(editor+right rail+analysis/review/source jump)을 착수한다. W2~W4는 승인된 순서를 유지한다.

---

## Task 5 — Writing Workspace V2 W0 계약/migration

### Goals

- 오너가 확정한 D1=A/D2=A/D3=C를 W2/W3가 구현할 수 있는 exact public/data contract로 내린다.
- ProjectBrief version/API, ordered unit reorder/legacy migration, 두 Writing intent accept의 멱등·원자성 경계를 정본과 기계 판독 schema에 잠근다.
- should-fire/should-NOT-fire branch마다 named 양방향 회귀 계획을 만들고 W1 착수 금지 경계를 해제한다.

### Completed work

- 신규 정본 계획 `docs/plans/writing-workspace-v2-w0-contract.md`를 추가했다.
  - ProjectBrief는 project 1:1 논리 정본/append-only version으로 확정했다. public content는 `premise/genre/tone/pov` nullable scalar와 ordered unique `constraints`; GET current null, optimistic-base+idempotent PUT, versions list/detail의 exact envelope을 정의했다.
  - Draft에 required `unit_kind=chapter|scene|other`, archived 포함 project-wide contiguous `position=1..N`을 정의했다. reorder는 현재 전체 Draft id의 완전 순열 PUT이며 부분 move/fractional position은 열지 않았다.
  - legacy migration은 기존 repository list order(ObjectId/삽입 순서 선례)를 보존해 `other`/`1..N`으로 부여한다. all-missing만 migration, all-valid no-op, mixed/invalid는 project 단위 fail-closed다.
  - `intent=append_current|start_next_unit`을 request/candidate/accept identity에 결박했다. legacy intent 생략은 append로 호환하고, start는 current 뒤 position shift+Draft+v1+snapshot+blocks+accept receipt를 한 Core SOT transaction으로 commit한다. Analysis job은 기존 저장소 경계대로 commit 뒤 `analyze:{snapshot_id}`로 생성한다.
  - 최초 ProjectBrief 11행, ordered unit 10행, Writing intent 16행으로 37행 named bidirectional regression matrix를 만들었고, 아래 독립 검증 closure에서 PB12+OU14+WI22+SC2의 총 50행으로 확장했다.
- `schemas/writing-workspace-v2-w0.schema.json`에 ProjectBrief/Draft/reorder/next-unit/accept request-response의 Draft 2020-12 exact schema catalog를 추가했다.
- SoT를 v1.7.10으로 올리고 CHANGELOG, Product Shell, Writing 계획, UX 브리프, 제품화 백로그, 계획 README, HANDOFF를 W0 완료/W1 next로 정렬했다.
- runtime code, Mongo collection/index, OpenAPI, frontend는 변경하지 않았다. W0의 문서/schema-only 경계를 지켰다.

### Issues found

- 기존 Draft 순서는 정본 spec에 없었지만 두 repository와 `test_lists_preserve_creation_order`가 생성 순서를 deterministic하게 잠그고 있었다. 새 owner fork 없이 이 선례를 legacy migration authority로 승격했다.
- next-unit accept는 Core SOT와 Analysis를 한 transaction으로 묶을 수 없다. 기존 accept partial-success 경계를 유지해 Draft/첫 version 원자성은 Core SOT transaction이 소유하고 Analysis는 snapshot-derived key로 사후 수렴하도록 분리했다.
- ProjectBrief의 별도 hard delete는 append-only audit·optional onboarding과 충돌한다. all-null/empty version을 clear로 정의하고 hard delete를 열지 않았다.

### Decisions

- 오너의 기존 결정(별도 ProjectBrief, 최소 ordered unit, 명시 두 intent, W0→W4 세로 순서)을 그대로 구현 기준으로 사용했다.
- ProjectBrief update는 mutable overwrite가 아니라 current base를 요구하는 append-only replacement다. 이유는 작품 정보의 변경 이력/권위 경계를 보존하면서 stale overwrite를 막기 위해서다.
- position은 archived 포함 전체 Draft의 연속 정수 순열이다. archive 뒤 복원/삽입/export에서 collision이나 제목 추론을 만들지 않고 full reorder를 원자 검증할 수 있기 때문이다.
- legacy Writing client는 intent 생략 시 `append_current`로 유지한다. W0가 기존 single-draft edit/save/history/export와 `continue_scene` 흐름을 깨지 않는다는 수용 기준을 따른다.

### Verification

- `python3 -m json.tool schemas/writing-workspace-v2-w0.schema.json` — PASS.
- `jsonschema.Draft202012Validator.check_schema` — PASS.
- append/start valid sample과 start+`next_unit=null` invalid sample — 양방향 schema validation PASS.
- 연결 문서의 W0/v1.7.9 stale 상태와 v1.7.10 링크를 repo-wide 검색해 정렬했다.
- `git diff --check` — PASS.

### Next steps

- W1: 기존 DraftEditor route에 editor+docked right rail(`이어쓰기/분석/검토`)을 만들고 좁은 화면은 같은 정보구조의 tab/drawer로 전환한다.
- analysis status/pending count, query 기반 candidate/detail 복원, source quote→exact version/offset highlight와 stale/latest 표시를 함께 잠근다.
- W1은 기존 API/action만 소비한다. ProjectBrief runtime(W2), ordered unit/intent runtime(W3), project export(W4)를 미리 구현하거나 UI에서 추정하지 않는다.

### Independent verification blocking closure

- 독립 기록 `docs/verifications/2026-07-18/w0_contract_migration.md`의 조건부 합격과 blocking B1~B4/C1~C3를 모두 재대조했다. 오너가 검증 기록을 바탕으로 보강과 커밋을 지시했다.
- 포괄 행/framework routing으로 분류하지 않고 7개 empty cell을 전부 독립 named 행으로 추가했다: current brief missing/cross-project 404, reorder archived 409/missing 404, non-transaction fallback failure recovery, legacy append save-only read-through, replay precedence, append partial 502/convergence.
- 두 방향을 함께 잠그기 위해 fallback 정상 성공·append different-key 정상 version도 추가하고, hardening H-502/H-analyze-key를 exact literal 행으로 승격했다. schema catalog fragment-only 소비/whole-root 금지 2행까지 추가해 최종 matrix는 **50행(PB 12+OU 14+WI 22+SC 2; fire 22/not-fire 28)**이다.
- hardening 반영: raw `uniqueItems`와 trim 후 runtime 중복 검증의 역할 분리, ObjectId가 아닌 repository list behavior가 선례라는 한계, migration maintenance window/단일 runner/모든 project 성공 뒤 index 설치, W3 신규 6-surface atomicity 표현, archived slot visible ordinal, ProjectBrief clear 문구, legacy `other` 재분류 안내, delivery manifest와 saved publication manifest 구분.
- ProjectBrief→Draft provenance는 새 persistence field를 요구하므로 조용히 결정하지 않고 Deferred로 명시했다.
- verification record는 closure 전 working tree에 대한 독립 감사 결과이므로 수정하지 않고 역사적으로 보존했다. 독립 재판정은 수행하지 않았다.

#### Closure verification

- JSON Schema: `python3 -m json.tool` + `Draft202012Validator.check_schema` PASS. 19 `$defs` fragment에서 append/start 정상·교차 discriminator 거부, duplicate/unknown/version 0 거부를 재확인했다. `["a"," a"]`는 raw schema 통과 후 HTTP trim validator가 422를 소유한다는 역할 분리도 의도대로 확인했다.
- Matrix: PB 12 + OU 14 + WI 22 + SC 2 = 50, fire 22/not-fire 28, named test 50개 중복 0 PASS.
- 문서/schema trailing whitespace 0, `git diff --check` PASS.
- runtime scope: `services/`·`frontend/` 변경 0. W0 문서/schema slice 경계를 유지했다.
