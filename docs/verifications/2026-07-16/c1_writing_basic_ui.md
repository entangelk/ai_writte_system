# 독립 검증 — C1 기본 Writing 작업공간 UI 구현 (SoT v1.7.2, D1=A·D2=A·D4=A)

## Subject metadata

- 날짜: 2026-07-16
- 요청자: 오너("다음 작업 검증해줘. C1 기본 Writing 작업공간 UI 구현 완료(SoT v1.7.2) … 브리프 D1=A·D2=A·D4=A … 새 오너 결정은 없었습니다 … 지난 턴과 달리 이번엔 커밋 지시가 없어 커밋하지 않았습니다(uncommitted). 검증·커밋 진행하실지 알려주세요")
- 검증자: 독립 검증 AI(Claude, 별도 세션 — 구현 미관여)
- 대상 슬라이스/산출물: C1 — editor 내 generate→별도 Gate 근거→pass accept/save 기본 루프의 프론트 소비. 신규 `frontend/src/writing/WritingPanel.tsx` + `DraftEditor.tsx` seam 배선 + `client.ts` accept 정규화. D1=A / D2=A / D4=A. 순수 프론트 소비(backend/schema 무변).
- 정본 계약 참조(canonical contract scope):
  - `docs/plans/frontend-writing-workspace-decisions.md` — §D1=A 구현 lock(L55-61, clean latest only + 4-state 설명 텍스트), §D2=A 기본 UI lock(L76-82), §D4=A accept intent lock(L117-123), §"확인된 현재 계약과 선례"(L37-38, 특히 accept 502 partial + §38 idempotency "exact accept request body 전체에 결박, `request_id`·`candidate_text`·`draft_id`·`base_version_id`가 핵심 identity"), §C1 "선택 후 첫 구현 순서"(L160-167)
  - `docs/system-contract-sot.md` v1.7.2 행(버전 로그) — C0(v1.7.1)이 낸 성공/partial 타입의 소비 지점
  - C0 계약(`docs/verifications/2026-07-16/c0_writing_http_contract.md`) — `WritingCandidatePayload`/`WritingGatePayload`/`WritingAcceptResponse`/`WritingAcceptAnalysisPartial`의 소비
- 검증 대상 작업 출처: **working tree, uncommitted**(작업자가 "커밋하지 않았다"고 명시). 본 검증은 mutation을 위해 working tree를 일시 더렵히고 매번 백업 파일로 복원했다(최종 복원 완료, `grep` 잔류 없음 확인).

## Scope

1. **계약 스코프·자기 모순** — 브리프 D1=A/D2=A/D4=A lock + SoT v1.7.2 행이 요구하는 것. C0 타입 소비의 정합성.
2. **D1=A clean-latest 게이팅** — archived/zero-version/dirty/past-version 4-state 각각 (a) generate disabled (b) why 불가 reason (c) 해소 resolution 텍스트 — "disabled control만 두지 않는다" 계약.
3. **D2=A 기본 루프** — base version id 후보 lifetime 고정, 공백-only/중복 generate 차단, 별도 Gate 호출, Gate decision + findings 5필드(type/severity/message/evidence/recommended) 표시, **pass만 accept**, `200 accepted=false`는 재-Gate 결과.
4. **D4=A read-only candidate + accept intent 결박** — 후보 read-only panel(accept 전 원문 무변), idempotency key exact body 결박, 같은 body→같은 key(5xx 재시도), candidate/base 변경→새 key.
5. **accept outcome 정규화(핵심)** — `client.acceptWriting`이 `200 accepted=true`·`502+accepted=true+saved`를 "저장됨"으로, `200 accepted=false`를 "재-Gate"로, `409 stale`/`400·404·422`/5xx를 분기 — 특히 **502 partial을 generic error로 삼켜 저장된 version을 잃지 않는다**.
6. **DraftEditor seam** — dirty/onLatest/hasVersions/readOnly 파생 + accept 후 reloadLatest.
7. **순수 소비** — backend/tests/scripts/compose diff 0, schema.d.ts 무변경(gen:api IDENTICAL), 프론트 소비 코드만.
8. **독립 실행 재현** — 프론트 64/5 · build 91 · mutation 2종(3+3 bite).

## Methodology

브리프 D1=A/D2=A/D4=A lock과 §38 idempotency identity 정의를 boundary matrix의 lock list로 전개하고 각 cell을 1차 소스에서 채웠다. 작업자 claim(work_log Task 13·HANDOFF·SoT v1.7.2 행)은 "소스"로만 읽고, 브리프·코드·테스트에서 독립 재도출했다.

- **계약 읽기**: 브리프 D1/D2/D4 lock + §37-38 + C1 절 + SoT v1.7.2 행을 end-to-end 읽어 lock list 구축. C0 검증 기록으로 소비 타입의 계약 폭을 확인.
- **코드 대조**: `WritingPanel.tsx`(availabilityOf L48-80, generate L114-165, accept L167-250, canAccept L112, candidate panel L308-360), `client.ts` diff(acceptWriting + WritingAcceptOutcome), `DraftEditor.tsx` diff(latestOf·latestVersionId/onLatest 파생·reloadLatest·WritingPanel mount). 각 분기를 브리프 lock 조항과 1:1 매핑.
- **실행 재현**(아래 Reproduction):
  - 풀 프론트 → `64 passed / 5 files`; `npm run build` → `91 modules transformed`
  - `npm run gen:api` → committed `schema.d.ts`와 `diff -q` → IDENTICAL
  - mutation 1: pass-only guard 제거(`canAccept`·accept guard에서 `decision === "pass"` 제거) → WritingPanel `3 failed | 12 passed`(백업→복원)
  - mutation 2: dirty D1 block 제거(`availabilityOf`의 dirty if-block) → WritingPanel `2 failed` + DraftEditor seam `1 failed` = `3 failed`(백업→복원)
  - `git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml` → 0
- **정적/문서**: `git diff --check`, SoT v1.7.2 행·work_log Task 13·브리프 C1 "구현 완료"·backlog OPS-1 Waiting·ARCH-1 미재발화 정합성.

## Findings

### F1. 계약 스코프·자기 모순 — 정합. C0 타입을 손선언 없이 소비.

브리프 D1=A/D2=A/D4=A lock + §37-38이 요구하는 것을 코드가 그대로 구현했고, SoT v1.7.2 행·work_log Task 13과 일치한다. `client.ts`의 타입은 전부 C0가 만든 `components["schemas"][...]`(`WritingCandidatePayload`/`WritingGatePayload`/`WritingAcceptResponse`/`WritingAcceptAnalysisPartial`)에서 직접 소비 — 손선언 응답 타입 0건. backend/schema 무변(F6)이므로 C0 계약 폭 변동 없이 소비만 추가.

### F2. D1=A clean-latest 게이팅 — 4-state 전부 reason+resolution+disabled, "disabled control만" 아님.

`availabilityOf`(`WritingPanel.tsx:48-80`) 우선순위 readOnly → !hasVersions → dirty → !onLatest. 각 blocked state는 `{blocked:true, reason, resolution}` 세 필드 모두 반환하고, blocked일 때 panel은 reason+resolution note를 렌더(L261-265, disabled textarea L279 + disabled button L286-290). parametrized 테스트(`WritingPanel.test.tsx:130-166`)가 4-state 각각 `getByText(reason)` + `getByText(resolution)` + `toBeDisabled()` + `fetch not called`를 pin. **mutation 2**(dirty block 제거) → parametrized-dirty + "keeps disabled while blocked" + DraftEditor dirty-derivation seam = **정확히 3 failed**(2 단위 + 1 seam)로 "disabled control만" 계약이 양 끝(단위·seam)에서 잠김을 실증.

### F3. D2=A 기본 루프 — base 고정·중복/공백 차단·별도 Gate·findings 5필드·pass-only.

- **base version 고정**: generate가 `baseVersionId = latestVersionId`(prop), `requestId = crypto.randomUUID()`(L133-134)를 `contextRef`(L109)에 freeze. 테스트(`:196-213`)가 generate·gate 양쪽 `current_position.version_id === "v3"`(prop latest)를 pin → 후보 lifetime 동안 base 불변.
- **공백-only/중복 차단**: `trimmed === ""`(L117) + `busyRef.current` 동기 write lock(L104,119). "enables generate"(whitespace disabled) + "prevents duplicate generate"(pending promise로 2차 submit 무시, `:223-242`)로 pin.
- **별도 Gate + candidate 보존**: `setCandidate(produced)`(L147)가 `gateWriting`(L149) **보다 먼저** → gate 5xx에도 catch가 candidate를 지우지 않아 보존. "preserves candidate when gate fails"(`:244-252`, gate 502 → candidate 표시 + alert + accept disabled)로 pin.
- **Gate findings 5필드**: `[severity] type → recommended_decision`·message·`근거: evidence`(L329-337). 테스트(`:217-220`)가 error/continuity/revise/message/evidence 전부 pin.
- **pass-only**: `canAccept = candidate !== null && gate?.decision === "pass"`(L112) + accept guard(L170). **mutation 1**(pass-only 제거) → "enables only on pass"·"accepted=false re-Gate"·"gate fails candidate" = **정확히 3 failed**로 pin.
- **200 accepted=false = 재-Gate**: `outcome.accepted === false` 분기(L221-226)가 candidate 보존 + 반환 Gate 표시 + accept disable + alert 없음. "treats 200 accepted=false as Gate result"(`:300-314`)로 pin.

### F4. D4=A read-only candidate + accept intent 결박 — read-only·exact body·같은 body 같은 key.

- **read-only**: candidate는 `<p className="candidate-text">`(L316)로 렌더, 편집 input 없음. WritingPanel은 editor textarea state에 전혀 쓰지 않으므로 accept 전 원문 무변(DraftEditor가 rawText/baseline을 단독 소유). "accepts pass candidate"(`:296`)가 성공 후 candidate UI 소거를 pin.
- **exact body 결박**: `signature = JSON.stringify(fields)`(L196, fields = idempotency_key 제외 전체 body), `intent.signature === signature ? reuse : new`(L198-200). "accepts pass candidate, binds exact body"(`:281-293`)가 accept 전체 body(request_id/draft_id/base_version_id/instruction/candidate_text/draft_excerpt/max_tokens/task_type/output_type/current_position/idempotency_key)를 exact로 pin.
- **같은 body → 같은 key(under-strict)**: "reuses same idempotency key when retrying same body after 5xx"(`:344-365`) — 500 → candidate 보존 + 재시도 → `firstKey === retryKey === "uuid-2"`. transport/5xx 분기(L241-244)가 intent를 지우지 않아 같은 body 재시도가 같은 key로 수렴.

### F5. accept outcome 정규화(핵심) — 502+accepted=true+saved를 저장 성공으로, generic 502는 error.

`client.ts` `acceptWriting`/`WritingAcceptOutcome`(diff):
- 200 `data.accepted && data.saved !== null` → `{accepted:true, savedVersionId, analysisFailed:false}`; 200 accepted=false → `{accepted:false, gate}`.
- **502**: `partial.accepted === true && partial.saved != null` → `{accepted:true, analysisFailed:true}`(저장 성공, 분석 실패). 그 외 502(saved 없는 generic error) → `throw ApiError(502, detail)`. 
- 기타 non-ok → `throw ApiError(status, detail)`.

이 분기가 브리프 §37/SoT v1.7.2 행의 load-bearing "**502 + accepted=true + saved는 저장 성공, generic error로 삼켜 version을 잃지 않는다**"를 정확히 소비. "treats 502+accepted=true+saved as saved version with failed analysis"(`WritingPanel.test.tsx:316-327`)가 onAccepted 호출 + "분석 작업은 실패해 재시도가 필요합니다" notice + candidate 소거 + **alert 없음**(저장 성공이 error로 드러나지 않음)을 pin. WritingPanel은 `outcome.analysisFailed`(L216)로 notice를 분기해 Analysis 재시도 안내까지 제공. **C0가 계약화한 partial envelope의 소비 지점이 정확히 여기다.**

409 stale(candidate 보존 + 최신 재조회 안내, `:329-342`)·5xx(candidate·intent 보존, `:344`) 분기도 브리프 D2=A UI lock(L82)과 일치.

### F6. 순수 소비 — backend/tests/scripts/compose diff 0, schema.d.ts 무변경.

`git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml .dockerignore` → **0**. `schema.d.ts`는 working tree에서 무변경 → `npm run gen:api`가 committed 파일과 **IDENTICAL**(diff -q). 변경은 프론트 소비 코드(`client.ts`·`DraftEditor.tsx`·신규 `WritingPanel.tsx`·`styles.css`) + 문서뿐. **ARCH-1 재발화 안 함**(backend route/model 무변)은 정확.

### F7. DraftEditor seam — dirty 파생 + accept 후 reload.

`latestOf`(max version_number, 순서 비의존)로 `latestVersionId`/`onLatest` 파생, `dirty`/`hasVersions`/`readOnly`와 함께 WritingPanel에 전달(`DraftEditor.tsx` diff). `reloadLatest`가 버전 재조회 → max 선택 → detail 조회 → baseline/rawText/versions/selectedVersionId 갱신, `onAccepted`에 배선. 2 seam 테스트가 (a) clean→dirty 전환 시 D1 block reason+resolution+disabled("derives the dirty block", `DraftEditor.test.tsx:675-697`)·(b) accept 후 editor가 새 latest("기존.\n\n아린은 도시로 들어섰다.", version 4)로 reload("reloads the editor to the new latest", `:699-770`)를 pin. 단위(15) + seam(2) = 17 신규, 전체 64.

### F8. 독립 실행 재현 — 정량·mutation 전부 일치.

- 프론트 `64 passed / 5 files`(47+17), `build` 91 modules
- gen:api IDENTICAL, backend/tests/scripts/compose diff 0, `git diff --check` clean
- mutation 1(pass-only) `3 failed`, mutation 2(dirty D1) `3 failed`(2 단위 + 1 seam) — 후 복원, 잔류 0
- SoT v1.7.2 행·work_log Task 13·브리프 C1 "구현 완료"·OPS-1 Waiting 유지(근거: 실 LLM 관통 미실행 + dogfood는 오너 결정) 정합

## Issues / Risks

### Blocking(계약 의무) — 없음.

C1 boundary matrix의 contract-required cell은 빈 칸 없이 채워졌다. **브리프 §38이 정의하는 idempotency 핵심 identity(`request_id`·`candidate_text`·`draft_id`·`base_version_id`)는 C1에서 전부 불변**이다(request_id·candidate_text는 generate 시 freeze, candidate는 read-only 패널, draft_id/base_version_id는 contextRef 고정). 따라서 브리프가 명시한 over-strict 분기 "candidate/base가 바뀌면 새 key다"는 **C1 흐름에서 구조적으로 도달 불가**(candidate/base가 한 후보 lifetime 안에 바뀔 수 없다)하며, 도달 가능한 contract-required 분기는 전부 pin됐다.

### Hardening recommendations(비차단 — 현 spec이 요구하지 않거나, 도달 가능하나 낮은 위험)

- **H1(idempotency over-strict pin — C2/D4=B에서 load-bearing)** — `signature`는 §38의 핵심 identity 4종 외에 **`instruction`**(비-identity 필드)까지 포함해 exact body를 잠근다. 코드는 instruction 변경 시 올바르게 새 key를 mint(L198-200). 그러나 **"body가 바뀌면 새 key" 방향을 pin하는 회귀가 없다** — signature 비교 가드(L196-200)를 제거해도 17개 테스트 전부 green. 브리프 §38 identity는 이미 4개 불변 필드로 만족되므로 **C1에서 현실적 위험은 없다**(candidate가 read-only라 저장 prose가 동일). 다만 C2(revise-and-gate) 또는 D4=B(editable candidate)에서 candidate가 가변이 되면 이 방향이 **load-bearing**이 된다(다른 candidate를 같은 key로 재시도하면 서버가 key-only replay로 원 version을 돌려 새 prose를 조용히 잃음). 그때 전에 "instruction/candidate 변경 → 새 key" 회귀를 추가해 가드를 pin하는 것을 권장.
- **H2(400/422 accept definitive 분기 미테스트 — 낮은 위험)** — `DEFINITIVE_ACCEPT_FAILURES = {400,404,422}`(L21)가 intent를 지우고 error를 표시(L235-240). 브리프 D2=A UI lock(L82 "400/404/422는 확정 거부")에 부합하나 전용 회귀가 없다. 회귀 위험은 낮다 — intent를 안 지워도 같은 body 재시도라 key만 linger하고(저장 prose 동일) 정정합 이상은 없다. 기회 될 때 400/422 accept 응답 회귀 추가 권장.
- **H3(실 LLM 관통 미실행 — 추적 항목, 결함 아님)** — compose generate→Gate→accept smoke가 12B gateway 의존이라 sandbox 불가. 작업자가 이전 프론트 슬라이스 관례대로 unit/build/gen:api 증거로 대체했고, OPS-1도 이 근거로 Waiting 유지. 오너 풀스택 환경에서의 live 관통 + dogfood 시작이 별도 단계(OPS-1 trigger)로 남아 있다.

## Verdict

**합격(조건 없음).**

이유(load-bearing):
1. **D1=A 게이팅**이 4-state 각각 disabled + reason + resolution 텍스트를 제공("disabled control만" 아님)하고, 단위 + seam 양 끝에서 dirty block 제거 mutation이 **정확히 3개**를 bite(F2, F7).
2. **accept outcome 정규화**(F5)가 C0가 계약화한 **`502 + accepted=true + saved`를 저장 성공으로** 처리해 generic error로 version을 잃지 않으며, 502 partial 소비 지점이 unit 테스트로 pin됐다. 이는 C 슬라이스의 가장 위험한 write 경계.
3. **pass-only accept**(mutation 1 → 정확히 3 bite)·**같은 body 같은 key under-strict**(5xx 재시도)·**409 stale candidate 보존**·**gate 실패 시 candidate 보존** 등 D2=A/D4=A 핵심 분기가 전부 pin(F3, F4).
4. 브리프 §38 idempotency 핵심 identity 4종이 C1에서 불변이므로, contract-required over-strict 분기("candidate/base 변경→새 key")는 구조적으로 도달 불가 — 도달 가능한 contract 분기는 빈 cell 없이 채워짐.
5. **순수 소비**(backend/schema/tests diff 0, gen:api IDENTICAL, ARCH-1 미재발화) 확인(F6).
6. 정량 64/5·91 modules·mutation 3+3 전부 독립 재현(F8).

비차단 H1(idempotency over-strict pin, C2/D4=B 전 권장)·H2(400/422 accept 회귀)·H3(실 LLM 관통, OPS-1 추적)은 hardening 후보로 합격 판정에 영향을 주지 않는다.

## Outstanding items

- **커밋 미수행**: 작업자가 "이번엔 커밋 지시가 없어 커밋하지 않았다"고 명시 → C0+C1 전체가 **working tree, uncommitted** 상태. 오너의 커밋 승인 대기(본 검증은 커밋하지 않음).
- **C0+C1 함께 커밋 권장**: C0(backend 타입 계약, v1.7.1)와 C1(프론트 소비, v1.7.2)은 계약→소비 쌍이므로 한 커밋 단위(또는 C0→C1 순서의 2커밋)로 묶는 것이 회귀 추적에 자연스럽다. 오너 결정 사항.
- **다음 = C2 자동 revise/retrieve loop UI** — `/writing/revise-and-gate` 소비, C0가 낸 `WritingReviseGateResponse`/`WritingReviseGatePartial` 타입 사용. **H1 over-strict pin을 C2 착수 전에 추가**하면 candidate 가변화 시점에 안전망이 선제된다.
- **OPS-1**: Waiting 유지(오너 풀스택 live 관통 + dogfood 시작 시 Ready).
- 검증 중 일시 mutation으로 더럽힌 `WritingPanel.tsx`는 백업 파일로 복원했고 `grep`으로 잔류 없음을 확인했다(working tree는 검증 착수 전 상태로 동일).

## Reproduction

```bash
cd frontend

# 1. 풀 프론트 회귀·빌드
npm test -- --run --reporter=dot          # → 64 passed / 5 files
npm run build                             # → 91 modules transformed

# 2. gen:api IDENTICAL (순수 소비)
cp src/api/schema.d.ts /tmp/before.dts && npm run gen:api \
  && diff -q /tmp/before.dts src/api/schema.d.ts   # → IDENTICAL

# 3. mutation 1: pass-only guard 제거 → 3 failed
cp src/writing/WritingPanel.tsx /tmp/bak
# (canAccept에서 "&& gate?.decision === \"pass\"" 제거 + accept guard에서
#  "gate?.decision !== \"pass\" ||" 제거)
npx vitest run src/writing/WritingPanel.test.tsx --reporter=dot   # → 3 failed | 12 passed
cp /tmp/bak src/writing/WritingPanel.tsx                          # 복원

# 4. mutation 2: dirty D1 block 제거 → 3 failed (2 단위 + 1 seam)
# (availabilityOf의 "if (props.dirty) {...}" 블록 제거)
npx vitest run src/writing/WritingPanel.test.tsx --reporter=dot   # → 2 failed | 13 passed
npx vitest run src/drafts/DraftEditor.test.tsx --reporter=dot     # → 1 failed | 25 passed
cp /tmp/bak src/writing/WritingPanel.tsx                          # 복원

# 5. 순수 소비 확인
cd .. && git diff --stat HEAD -- services/ tests/ scripts/ docker-compose.yml   # → (empty)
git diff --check                                                   # → clean
```

## Post-verification disposition (구현자, 2026-07-16)

원 판정 **합격(조건 없음)**은 보존한다. 오너 승인으로 비차단 hardening을 반영했다(테스트만, 프로덕션 코드 무변):

- **H1 반영** — idempotency over-strict pin. generate 후 **instruction을 바꾸면(재생성 없이) accept body가 달라지는 도달 가능 경로**로 "body 변경→새 key"를 잠갔다(`mints a NEW key when the accept body changes before retrying`). signature 가드(`intentRef.current?.signature === signature`)를 항상-재사용으로 바꾸는 mutation에서 **정확히 이 1개만** bite(uuid-3 기대 → uuid-2 재사용). 검증 §H1이 지적한 "가드 제거해도 green"인 gap을 닫고, C2/D4=B candidate 가변화 전 안전망을 선제했다.
- **H2 반영** — `it.each([400,422])`로 확정 거부 시 error 표시·candidate 보존·`onAccepted` 미호출을 잠갔다(브리프 D2=A "400/404/422 확정 거부").
- **H3 코드 무변** — 실 LLM 관통(compose smoke)은 12B 의존이라 sandbox 불가. 검증자 판정대로 결함 아님, OPS-1 추적 항목으로 유지(오너 풀스택 후속).

반영 후: WritingPanel 15→**18**, 전체 프론트 **67 passed/5 files**. signature 가드 mutation bite로 H1이 가드를 직접 잠금을 실증했다.
