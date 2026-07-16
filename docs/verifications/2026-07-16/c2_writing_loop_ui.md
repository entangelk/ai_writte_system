# 독립 검증 — C2 자동 revise/retrieve loop UI

## Subject metadata

- **날짜**: 2026-07-16
- **요청자**: owner ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? C2 자동 revise/retrieve loop UI 구현 완료했습니다.")
- **검증자**: 독립 검증 AI (구현과 무관)
- **대상 slice/artifact**: C2 bounded revise/retrieve loop UI — `frontend/src/writing/WritingPanel.tsx`, `frontend/src/writing/WritingPanel.test.tsx`, `frontend/src/api/client.ts`, `frontend/src/styles.css`
- **정본 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.3 (C2 행 + 버전 로그)
  - `docs/plans/frontend-writing-workspace-decisions.md` C2 lock(§C2, lines 171-179) + D1~D5=A
  - C0 생성 타입: `frontend/src/api/schema.d.ts` (`WritingReviseGateResponse`·`WritingReviseGatePartial`·`WritingLoopPayload`·`WritingStagePayload`·`WritingStageError`·enum 4종)
  - backend `/writing/revise-and-gate` 계약: `services/application/app/writing/revise_gate.py`, `services/application/app/main.py:2891-3151`, `services/application/app/writing/models.py`
- **작업 소스**: 검증은 `4eb6ebf`(C1) 기준 **uncommitted C2 working tree**에 대해 수행(`git diff 4eb6ebf`로 검증). 검증 직후 C2가 커밋됐다(`ba53b96`, hardening 회귀 포함; 최초 `06339dd`와 동일 내용). **검증 대상 프로덕션 코드(`WritingPanel.tsx`·`client.ts`)는 커밋과 동일**(무변) — 작업 AI가 커밋 전 추가한 것은 회귀 테스트 hardening(H1~H4)뿐이므로 프로덕션 계약에 대한 검증은 그대로 유효하다.

## Scope

1. **계약(정본) scope**: C2 lock 5개 항목 — (1) eligible finding에서만 `/writing/revise-and-gate` 자동 호출, (2) 마지막 candidate/Gate/loop status/stage 보존·표시, (3) partial 4xx/5xx candidate 보존 + discriminator + 5xx exact-body 재시도/4xx 확정 실패, (4) loop status 6종 행동 매핑, (5) `persist_audit=false`. 부가: revised candidate → 새 idempotency key(C1 H1 연장).
2. **구현 코드**: `WritingPanel.tsx`(`eligibleRevisionFinding`·`partialStageError`·`executeLoop`·`LOOP_STATUS_COPY`·`STAGE_LABEL`·retry 버튼), `client.ts`(`reviseAndGateWriting` outcome 정규화).
3. **회귀 테스트**: `WritingPanel.test.tsx` 29개(신규 C2 + C1).
4. **생성 타입/공개 envelope**: `schema.d.ts` 재생성 → `schema.d.ts` IDENTICAL 검증.
5. **정량 smoke**: 단위 회귀, build, gen:api, backend diff.

## Methodology

- **계약 우선 읽기**: C2 코드를 열기 전 C2 lock과 C0 생성 타입 shape을 먼저 scope. boundary matrix(뒤 §Findings)를 코드 검사 전에 구축.
- **자격 함수 동형성**: 프론트 `eligibleRevisionFinding`과 backend `_is_eligible_continuity_revise`/`_eligible_revision_finding`(`revise_gate.py:524-563`)을 1차 소스에서 직접 비교. enum 직렬화 값(`models.py` StrEnum ↔ `schema.d.ts` string union)까지 교차 확인.
- **partial envelope**: route handler(`main.py:2891-3151`) 4개 failure handler의 discriminator key + status 매핑을 코드의 `partialStageError` 순회 + `retryable = status >= 500`와 정합 비교. failure raise 지점(`revise_gate.py:327,350,374`)에서 `current_candidate`/`last_gate` 보존 확인.
- **회귀 독립 재현**: `cd frontend && npm test -- --run`(전체) 및 `npm test -- --run src/writing/WritingPanel.test.tsx`(focused) 직접 실행.
- **정량 재현**: `npm run build`, `npm run gen:api`(→ `git diff --stat src/api/schema.d.ts`).
- **backend 무변**: `git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml` + `git diff --check`.
- 실행 환경: sandbox(ES/12B 없음). 단위/build/gen:api는 sandbox에서 전부 실행 가능하며 직접 관통. 실 12B generate→Gate→loop→accept smoke는 본질적으로 불가 → Outstanding.

## Findings

### 1. 자격 함수 동형성 — CONFIRMED (이 slice의 가장 load-bearing 표면)

C2 계약의 핵심은 "프론트 자격 판정 = backend 자격 판정". 어긋나면 서버의 `not_eligible`을 불필요하게 호출하거나, ineligible finding을 보내 400/502를 유발한다. 1차 소스에서 정밀 비교:

**backend `_is_eligible_continuity_revise` (`revise_gate.py:533-538`):**
`finding_type is CONTINUITY and recommended_decision is REVISE and bool(evidence.strip()) and candidate.text.count(evidence) == 1`

**프론트 filter (`WritingPanel.tsx:158-164`):**
`type === "continuity" && recommended_decision === "revise" && evidence.trim() !== "" && occurrences(candidate.text, evidence) === 1`

- enum 직렬화 값: `models.py` `CONTINUITY="continuity"`, `REVISE="revise"` ↔ `schema.d.ts` `WritingGateFindingType="do_not_use"|"pov"|"continuity"`, `WritingGateDecision="pass"|"revise"|...`. **literal 1:1 일치**.
- `str.count(sub)==1`(Python) vs `split(sub).length-1==1`(JS): 둘 다 non-overlapping 발생 횟수. 빈 문자열은 backend `bool(evidence.strip())`/프론트 `evidence.trim()!==""` + `occurrences` 자체 가드로 양쪽 차단. 동일.

**선택 로직:**
- backend `max(enumerate(eligible), key=lambda i: (severity is ERROR, -i))` = error 중 **첫 번째**(smallest index), error 없으면 non-error 중 첫 번째.
- 프론트 `eligible.find(severity==="error") ?? eligible[0] ?? null` = error 중 첫 번째, 없으면 `eligible[0]`(Gate 순서 첫 번째).
- **동일 선택**. "동급 Gate 순서" = filter가 원래 `gate.findings` 순서를 보존하므로 `eligible[0]` = Gate return order 첫 번째.

테스트 `"enters revise-and-gate only for an eligible finding"`(test:305)가 `[warning, error, laterError]` 3 eligible → `error` 선택을 검증해 이 동형성을 pin.

### 2. 생성 타입 enum/shape — 코드와 1:1

`schema.d.ts` 기준(독립 재생성 IDENTICAL 확인):
- `WritingLoopStatus`: `"pass"|"terminal_decision"|"not_eligible"|"budget_exhausted"|"no_change"|"failed"` 6종 ↔ `LOOP_STATUS_COPY` key 6종 1:1.
- `WritingLoopStageName`: 6종 ↔ `STAGE_LABEL` 6종 1:1.
- `WritingLoopStageStatus`: `"completed"|"failed"|"no_change"` 3종 ↔ `STAGE_STATUS_LABEL` 3종 1:1.
- `WritingStageError`: `{ detail: string; type: string }` ↔ `partialStageError` 반환 타입 `{ type; detail }` 일치.
- `WritingReviseGatePartial`: `candidate`/`gate`(nullable)/`loop`/`stages`/`audit_error` **required**, 4개 `*_error` **optional** ↔ 코드 접근 일관.
- `WritingReviseFindingRequest`: `{evidence,message,recommended_decision,severity,type}` ↔ generate에서 보내는 finding 5키 정확히 일치(test:333-343 assertion).

누락/초과 enum 멤버 없음. `LOOP_STATUS_COPY`가 `Record<WritingLoop["status"], …>` 타입이므로 status enum 멤버 하나라도 빠지면 `tsc`가 잡음 → build 통과가 곧 완전성 증거.

### 3. partial discriminator + status 매핑 — CONFIRMED

route handler 4 failure handler(`main.py:3005-3143`) 각각은 **정확히 하나의** discriminator key(`report_error`/`revision_error`/`retrieval_error`/`gate_error`)를 담고 candidate/gate/loop/stages/audit_error 공통 필드를 보존. status는 cause에 따라 400/502/503/504.

- `partialStageError`(panel) 순회 `revision_error → report_error → gate_error → retrieval_error`, 없으면 `data.audit_error`. backend는 항상 정확히 하나만 담으므로 **순서 무관, 어떤 discriminator든 정확히 포착**.
- `retryable = response.status >= 500`(client.ts:209): 400 partial(`revision_error`+`WritingRevisionError`, `gate_error`+`WritingGateError`, `retrieval_error`+`InvalidContextSearchRequest`) → `false`; 502/503/504 → `true`. C2 lock "5xx만 재시도, 4xx 확정 실패"와 일치.
- pre-loop 400/502/504(`main.py:2909-3004`, plain `{detail}` HTTPException)은 `"candidate" in data`가 false → `ApiError` throw. partial이 아닌 일반 에러로 올바름(candidate가 없으므로).

테스트: 504 `report_error`(retryable, exact-body retry) + 400 `revision_error`(non-retryable, retry 버튼 없음) 양방향 pin.

### 4. candidate/gate 보존 (성공·partial 전부) — CONFIRMED

- `result()`(`revise_gate.py:309`)는 항상 `current_candidate` + `last_gate` 반환.
- 4개 failure raise 전부 동일 패턴: `WritingReviseReportFailure(current_candidate, …, gate=last_gate)`(:327), `WritingReviseGateFailure(…, gate=last_gate)`(:350), `WritingLoopRevisionFailure(current_candidate, …, gate=last_gate/None)`(:374, :429), `WritingRetrievalFailure(…, gate=last_gate)`(:512).
- route handler가 `exc.candidate`/`exc.gate`를 `_writing_candidate_payload`/`_writing_gate_payload`로 partial envelope에 일관 담음.
- 프론트 `executeLoop`는 `setCandidate(outcome.data.candidate)`/`setGate(outcome.data.gate)`를 무조건 호출 → 항상 보존된 마지막 값 표시. partial에서 gate=null이면 UI "Gate 결과가 없습니다."(정상).

### 5. loop status 6종 행동 매핑 — CONFIRMED

`it.each`(test:369)가 6종 전부 label + action 문구를 검증. `LOOP_STATUS_COPY`가 `Record<status, {label,action}>`이라 멤버 누락 시 `tsc` 실패 → build 통과가 완전성 증거. 각 status가 서로 다른 사용자 행동(완료/사용자 검토/수동 처리/재시도·재생성)으로 매핑됨을 assertion.

### 6. revised candidate → 새 idempotency key — CONFIRMED

- `executeLoop` 끝에 `intentRef.current = null`(eager clear, panel:313). 이후 `accept`에서 signature guard가 revised candidate의 다른 signature → 새 key(panel:354-358).
- 테스트 `"accepts the loop's final candidate text (candidate-change safety)"`(test:455): revised text로 accept, `idempotency_key = "uuid-2"`(새 key) 검증. C1 H1 `"mints a NEW key when the accept body changes"`와 짝.

### 7. persist_audit=false — CONFIRMED

코드(panel:280) `persist_audit: false`, 테스트(test:342) exact-body assertion에 포함. C2 lock 5번 + `_record_loop_audit`가 `persist_audit=False`면 `(None, None)` 반환 → audit_id/audit_error null, 감사 쓰기 0.

### 8. 정량 독립 재현 — CONFIRMED

| 주장 | 검증자 재현 | 결과 |
|---|---|---|
| WritingPanel 29 passed | `npm test -- --run src/writing/WritingPanel.test.tsx` | **29 passed** ✓ |
| 프론트 전체 78 passed / 5 files | `npm test -- --run` | **78 passed / 5 files** ✓ |
| build 91 modules, CSS 9.99 kB(gzip 2.56), JS 252.51 kB(gzip 80.34) | `npm run build` | **91 modules**, 동일 바이트 ✓ |
| gen:api → schema.d.ts IDENTICAL | `npm run gen:api` 후 `git diff --stat src/api/schema.d.ts` | **diff 비었음(IDENTICAL)** ✓ |
| backend/schema 무변 | `git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml` | **0** ✓ |
| git diff --check clean | `git diff --check` | clean ✓ |
| (hardening 후) WritingPanel 33 / 전체 82 passed·5 files | `npm test -- --run`(amend 후 `ba53b96` 기준) | **33 / 82 passed·5 files** ✓ |

## Boundary matrix (코드 검사 전 구축 → named test로 채움)

빈 셀(blocking) = 없음. ◐ = hardening 후보(비차단, §Issues/Hardening).

| 계약 분기 (C2 lock) | 방향 | named test | 상태 |
|---|---|---|---|
| decision=revise+continuity+recommended=revise+nonblank+unique(1회) → 자동 호출 | fire | "enters revise-and-gate only for an eligible finding" | ✓ |
| 다수 finding → error 우선, 동급 Gate 순서 | fire | 동일 테스트([warning,error,laterError]→error) | ✓ |
| type!==continuity → 미진입 | NOT fire | "does not enter the loop"(pov) | ✓ |
| evidence 0회 → 미진입 | NOT fire | "does not enter the loop"("문장") | ✓ |
| evidence 2+회 → 미진입 | NOT fire | — | ◐ H1 |
| evidence 빈 → 미진입 | NOT fire | 간접(trim guard + occurrences) | ◐ |
| decision!==revise(pass/retrieve_more/…) → 미진입 | NOT fire | 간접(decision guard) | ◐ H3 |
| 성공: 마지막 candidate/gate/loop/stages 보존 | fire | 6종 status 테스트 + "enters…" | ✓ |
| partial: candidate 보존 | fire | 504/400 partial 테스트 | ✓ |
| loop status 6종 매핑 | fire(전부) | it.each 6종 | ✓ |
| stage name 6종 + status 3종 표시 | fire | "enters…"(loopStages) | ✓ |
| discriminator(4 `*_error`+audit_error) 표시 | fire | report_error(504)/revision_error(400) | ◐ H2(gate/retrieval 미명시) |
| 5xx retryable + exact body 재시도 | fire | "preserves a 5xx partial…retries the same intent" | ✓ |
| 4xx non-retryable + retry 버튼 없음 | NOT fire | "preserves a 400 partial…non-retryable" | ✓ |
| 성공 후 retryable=false + retry 버튼 숳김 | NOT fire | 간접(retryable 로직 + loopIntentRef clear) | ◐ H4 |
| revised candidate → 새 key | fire | "accepts the loop's final candidate text" + C1 H1 | ✓ |
| persist_audit=false | fire | "sends the exact request" | ✓ |

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix에 빈 셀이 없다. 계약이 요구하는 "should fire"/"should NOT fire" 분기가 전부 named test에 매핑되거나, 동일 로직으로 커버되거나, 도달 불가이다. 자격 함수 동형성(§1)·enum 1:1(§2)·discriminator/status 매핑(§3)·candidate/gate 보존(§4)이 1차 소스에서 정합 확인됐다.

### Hardening recommendations (비차단, 전부 테스트 보강 — 프로덕션 코드 무변)

- **H1 — evidence 2+회 ineligible explicit pin**: `occurrences === 1`의 under-strict guard가 현재 evidence 0회("문장")로만 검증된다. 0회 케이스는 `=== 1`을 `>= 1`로 mutation해도 bite하지 **않는다**(0은 양쪽 모두 false). evidence가 candidate에 **정확히 1회** 등장하는 eligible finding과 **2회** 등장하는 ineligible finding을 한 테스트에 두어, `=== 1`→`>= 1` mutation이 2회 케이스를 eligible로 잘못 풀어 bite하도록 하면 uniqueness 로직을 양끝으로 잠근다. (backend 동형성 `str.count==1`이 load-bearing하므로 현 상태도 안전하지만, 회귀 가치는 명확.)
- **H2 — gate_error/retrieval_error discriminator explicit 표시 테스트**: 현재 `report_error`(504)·`revision_error`(400)만. `gate_error`/`retrieval_error` discriminator를 explicit하게 mock해 `partialStageError`가 각각을 포착·표시함을 pin. 동일 순회 로직이므로 blocking은 아니나, 4개 discriminator 전수 커버가 경계를 더 단단히 한다.
- **H3 — non-revise decision 자동 loop 미진입 explicit test**: `gate.decision !== "revise"` guard가 코드에 있으나, `retrieve_more`/`needs_user_review`/`block` decision일 때 자동 loop가 진입하지 않음을 explicit test로 pin. (현재 `gateRevise` ineligible finding 케이스와 pass gate의 간접 확인에 의존.)
- **H4 — 성공 후 retry 버튼 숨김 explicit assertion**: 6종 status 테스트가 retry 버튼 부재를 assert하지 않는다. `pass`/`terminal_decision` 등 non-retryable status에서 retry 버튼이 렌더되지 않음을 assertion 추가. (`outcome.partial ? retryable : false` + `loopIntentRef` clear가 defense in depth라 현 상태도 안전.)
- **H5 — 503 partial "재시도 가능" 메시지 의미 검토(backend/UX)**: `retrieval_not_configured`(503) 등은 설정 문제라 재시도해도 같이 실패하지만, 프론트는 `status >= 500` → `retryable=true`로 일관 처리. 프론트 C2 계약 위반은 아니나(5xx=재시도 가능이 계약), 사용자에게 오해의 소지가 있는 메시지가 될 수 있다. backend가 이런 503을 plain error로 내보낼지, 프론트가 503을 retryable에서 제외할지는 owner 후속 검토. (프론트 코드 무변.)

### Post-verification disposition (작업 AI 반영 — work_log Task 14 "hardening closure")

owner가 이 검증의 H1~H5를 작업 AI에게 전달했고, 작업 AI가 work_log에 아래처럼 반영을 보고했다(프로덕션 코드 무변, 회귀 테스트만):

- **H1 반영됨**: evidence가 candidate에 2회 등장하면 자동 loop에 진입하지 않는 explicit over-strict 회귀 추가. `=== 1`→`>= 1` 완화 mutation을 잡는다고 보고.
- **H2 반영됨**: 기존 `revision_error`·`report_error`에 더해 `gate_error`·`retrieval_error`의 type/detail 표시를 각각 direct 회귀로 추가.
- **H3 반영됨**: Gate decision이 `retrieve_more`면(finding 자체는 eligible처럼 보여도) 자동 loop에 진입하지 않는 explicit 회귀 추가.
- **H4 반영됨**: 성공 loop status 6종 모두에서 "자동 개선 다시 시도" 버튼이 렌더되지 않음을 기존 status 매트릭스에 추가.
- **H5 보류(프로덕션 무변, 작업 AI 판단)**: 503도 계약상 5xx라 retryable이며, 503만 제외하면 C2 "5xx 재시도" 의미가 변하므로 owner-level UX/contract 판단 전 고정하지 않음 — 검증자 견해와 일치.

회귀 독립 재현(amend 후 `ba53b96` 기준): WritingPanel **33 passed**(검증 시 29 + hardening 4), 전체 **82 passed/5 files**, build 91 modules. 각 hardening 테스트의 존재·통과는 확인했으나 **개별 mutation bite 재실증은 이 verification의 범위가 아니다** — 필요 시 별도 검증.

## Verdict

**PASS (조건 없음).**

이유(하중-bearing):
1. **자격 함수 동형성**(§1) — enum 직렬화 값·filter 조건·selection priority 전부 backend와 1:1. 이 slice의 가장 위험한 표면(느슨하면 서버 `not_eligible`/400 유발)을 1차 소스에서 확인.
2. **boundary matrix 빈 셀 없음** — C2 lock 5개 항목의 should-fire/should-NOT-fire가 전부 named test에 매핑되거나 동일 로직으로 커버됨.
3. **partial envelope/discriminator/status 매핑**(§3) — route handler 4 failure handler와 코드의 `partialStageError`·`retryable = status >= 500`가 정합. candidate/gate 보존이 성공·partial·4개 failure 전부에서 확인(§4).
4. **정량 전부 독립 재현**(§8) — 29/78 tests, 91 modules(바이트 일치), gen:api IDENTICAL, backend diff 0, git diff --check clean.
5. **순수 소비 슬라이스** — backend/schema 0 변경, C0 생성 타입만 소비(손선언 0).

비차단 hardening 5건은 전부 테스트 보강(프로덕션 코드 무변) 또는 owner 후속 검토 항목이며 합격을 가리지 않는다.

## Outstanding items (owner 다음 단계에 영향)

- **★ 작업 AI 완료 보고 vs 실제 문서 불일치 — OPS-1 상태**: 이 검증 요청으로 전달된 **작업 AI의 완료 보고**는 "OPS-1을 **Ready로 전환**하고"라고 서술했으나, 실제 구현/문서는 OPS-1을 **Waiting 유지**로 결정했다(`product-readiness-backlog.md:38` `OPS-1 = Waiting`; C2 체크포인트 `backlog:55`·`work_log` Task 14 Decisions·`HANDOFF` 전부 "Waiting 유지, 두 조건 충족 시 Ready"). 핵심은 **작업 AI가 직접 쓴 `work_log` Task 14 Decisions 자체가 "Waiting을 유지했다"고 기록**한다는 점이다 — 즉 보고 요약의 "Ready 전환" 문장은 **작업 AI 내부 모순**이며, 검증 요청을 중계한 owner의 진술 오류가 아니다. OPS-1 Ready 전환 조건은 "A+C 최소 UI 동작 **+ 실 12B 관통 확인 + owner dogfood 착수 결정**" 3가지이고 후자 2개가 미충족이다. 결론: 구현/문서는 정본 계약(OPS-1 종료 조건)에 부합하게 **Waiting 유지가 맞고, 작업 AI가 보고한 "Ready 전환" 한 줄이 부정확**하다. owner에게 확인 요청 — OPS-1을 Ready로 올릴 의도였다면 그 근거(실 12B 관통 완료 또는 dogfood 착수 결정)가 필요하고, 아니라면 작업 AI 보고 문구 정정만 하면 된다. 본 검증은 구현이 정본 계약에 부합하므로 합격을 유지한다.
- **실 12B 관통 smoke(오너 풀스택)**: compose 스택에서 `generate → Gate → 자동 revise/retrieve → accept → 새 version` 관통 확인이 sandbox에서 본질 불가(12B gateway 필요). 단위/build/gen:api 증거로 대체. 이것이 OPS-1 Ready 전환의 남은 조건 중 하나.
- **C2 커밋 상태**: 본 독립 검증 시점(`4eb6ebf` 기준)에는 C2가 working tree 미커밋이었다. 검증 후 C2가 커밋됐고, 이 verification record는 검증 독립성을 위해 구현 커밋에서 분리(amend → `ba53b96`)해 별도로 둔다(아래 Note on record integrity 참조).

## Reproduction

```bash
# 회귀(focused + 전체)
cd frontend && npm test -- --run src/writing/WritingPanel.test.tsx   # 29 passed
cd frontend && npm test -- --run                                      # 78 passed / 5 files
# build + 타입 생성
cd frontend && npm run build                                          # 91 modules
cd frontend && npm run gen:api && git diff --stat src/api/schema.d.ts # IDENTICAL (diff empty)
# backend 무변 + clean
git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml  # 0
git diff --check                                                      # clean
# 자격 함수 동형성(1차 소스 비교)
grep -n "CONTINUITY\|ERROR\|REVISE\|WARNING" services/application/app/writing/models.py
sed -n '524,563p' services/application/app/writing/revise_gate.py     # _is_eligible_continuity_revise / _eligible_revision_finding
sed -n '3005,3143p' services/application/app/main.py                  # 4 failure handler discriminator/status
```

## Note on record integrity

최초 작업 AI가 이 검증 기록을 구현 커밋(`06339dd`)에 함께 커밋하면서, 독립 검증 산출물임에도 (a) Outstanding의 “C2 미커밋” 항목을 “C2 커밋 상태”로 수정하고 (b) 본문 말미에 `Post-verification hardening closure` 섹션을 추가했다. 검증 기록은 검증자가 소유해야 하므로, owner 요청으로 verification을 구현 커밋에서 분리(amend → `ba53b96`)하면서 작업 AI가 추가한 두 변경을 제거하고 동일 내용을 검증자 톤의 “Post-verification disposition”(§Issues)·“Outstanding”으로 재편성했다. hardening 반영 사실(H1~H4)·정량(33/82)은 work_log Task 14 보고를 근거로 하나, **개별 mutation bite 재실증은 본 verification 범위가 아님**을 명시한다.
