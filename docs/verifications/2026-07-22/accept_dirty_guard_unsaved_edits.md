# 검증 기록 — accept 후 미저장 편집 소실 결손 수정 (reloadLatest 덮어쓰기, 프론트 전용)

## Subject metadata

- **날짜**: 2026-07-22
- **요청자**: 오너 ("작업 AI 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? 결손 수정 완료했습니다." — 명시적 검증 트리거, CLAUDE.md §5 "Verification Records")
- **검증자**: 독립 AI 감사자 (작업자와 다른 세션, CLAUDE.md §5 기준)
- **대상 슬라이스/아티펙트**: accept 후 미저장 편집 소실 결손 수정(프론트 전용). `frontend/src/writing/WritingPanel.{tsx,test.tsx}` · `frontend/src/drafts/DraftEditor.test.tsx` · 문서 4건(`CHANGELOG.md`·`HANDOFF.md`·`docs/daily_logs/2026-07-22/work_log.md`·`docs/plans/async-generation-pad-decisions.md`)
- **정본 계약 참조**: [`docs/plans/async-generation-pad-decisions.md`](../../plans/async-generation-pad-decisions.md) **Deferred / out of scope** 절("편집기 미저장 입력이 accept 후 `reloadLatest()`로 덮이는 문제 — 비동기와 무관하게 존재하는 별개 결손 … 별도로 다룬다"). 본 결손은 async-pad 슬라이스 밖의 독립 결손이므로 SoT bump 없음. [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.7.27 (본 수정은 SoT 무관여).
- **작업 출처**: working tree, **uncommitted** (`git status`로 확인 — 7개 파일 modified, 커밋 미수행). HEAD = `600834c` (비동기 생성 증분 3).

## Scope

정본 계약 읽기 **전**에 스코핑한 계약 표면(이 결손을 govern하는 근원만):

1. **결손 선언 리터럴** — decisions brief Deferred 절: "편집기 미저장 입력이 accept 후 `reloadLatest()`로 덮이는 문제 — 비동기와 무관하게 존재하는 별개 결손" (이것이 본 슬라이스의 유일한 계약 근원; 별도 형식 spec clause는 없고 앱의 dirty-가드 관용구가 계약 역할).
2. **선례 관용구(암묵 계약)** — `DraftEditor.tsx`의 dirty 상태 파괴적 동작 전부 `dirty && !window.confirm(msg)` → abort/return 패턴 (페이지 이동·version 전환·근거 열기). 작업자는 이 관용구를 accept에 적용한다고 주장 → 각 사이트가 실존 + 동일 패턴인지 독립 확인.
3. **결손 인과 사슬(코드)** — `accept()` 성공 → `onAccepted` → `reloadLatest()` → `setRawText(nextText)`+`setBaseline(nextText)` 가 편집기를 새 latest로 덮어쓴다는 사슬. 이것이 "소실"의 물리적 기전.
4. **`dirty` prop 의미** — `dirty = rawText !== baseline` 이 편집기 입력을 정확히 반영하는지(가드 효과의 전제).
5. **구현 코드(`WritingPanel.accept()` 가드 위치·형태)** + **회귀 테스트 4건** (WritingPanel 3 + DraftEditor 통합 1).
6. **수치 주장** — 187 passed/13 files · `tsc` clean · build 103 modules/JS 398.16 kB · 백엔드/OpenAPI 무변.

## Methodology

독립 재도출 — 작업자의 work_log/CHANGELOG/HANDOFF 주장을 그대로 믿지 않고 일차 소스에서 재검증.

1. **결손 인과 사슬 코드 추적**: `WritingPanel.tsx` accept() 전문 + `DraftEditor.tsx` 의 `onAccepted` 핸들러·`reloadLatest()`·`dirty` 정의·setRawText 전 사이트를 읽어 "accept → reloadLatest → setRawText+setBaseline 덮어쓰기" 사슬이 실재하는지, 그리고 미저장 입력이 소실되는지 확인.
2. **관용구 일치 검증**: `DraftEditor.tsx` :163·:278·:347 의 기존 dirty-confirm 사이트와 신규 accept 가드의 패턴(`dirty && !window.confirm(msg)` → return)을 대조.
3. **가드 위치 정확성**: 가드가 `busyRef.current = true`(busy 진입)·네트워크 호출(`acceptWriting`)·idempotency 키 민팅(`crypto.randomUUID`) **전**에 있는지, 그리고 `dirty`가 accept의 다른 분기(availability helper)와 충돌하지 않는지.
4. **테스트 코드 감사(audit subject)**: 신규 4건의 각 단정이 (a) 계약을 실제로 고정하는지 (b) under-strict(가드 제거 시 re-fail) (c) over-strict(clean 정상 케이스) 양방향 잠금인지. 특히 DraftEditor 통합 테스트가 `dirty` prop 실전 전파(reactive rerender)를 관통하는지, 아니면 rerender 조작으로 우회하는지.
5. **pattern sweep(fix 완료 선언 전)**: `setRawText` 전 사이트를 grep해 동일 근본 원인(편집기 조용한 덮어쓰기)이 다른 경로에 무가드로 남아있는지. `git blame`은 해당 라인들이 본 슬라이스 외 기존 코드이므로 생략.
6. **재실행(정확한 명령)**:
   - `cd frontend && npx vitest run` (전체 스위트)
   - `cd frontend && npx tsc --noEmit`
   - `cd frontend && npm run build` (= `tsc --noEmit && vite build`)
   - `git status` 로 백엔드/OpenAPI 무변 + 7개 파일만 modified 확인

## Findings

### 1. 결손 인과 사슬 — 실재 확인 (코드 1차 소스)

작업자 주장의 기반인 "accept 후 미저장 편집이 조용히 소실된다"를 코드로 재추적:

- `DraftEditor.tsx:156` `const dirty = rawText !== baseline;` → 편집기 본문 입력(rawText 변화)이 dirty를 참으로 만든다. **dirty는 편집기 입력을 정확히 반영** (가드 효과의 전제 성립).
- `WritingPanel.tsx:744` `onClick={() => void accept()}` → accept는 단일 진입점(버튼 onClick만). 다른 호출처 없음.
- `DraftEditor.tsx:649-652` `onAccepted={() => { setScratchRefresh((n) => n + 1); void reloadLatest(); }}` → accept 성공 시 reloadLatest 호출.
- `DraftEditor.tsx:459-470` `reloadLatest()` → `setRawText(nextText)` (468) + `setBaseline(nextText)` (469) → **편집기 본문을 새 latest로 덮어쓰고 baseline까지 같은 값으로 리셋**하므로 미저장 입력이 완전히 소실(dirty도 다시 false). **결손 실재 확인.**

`WritingPanel.tsx:445` accept 성공 분기는 `candidate_text: candidate.text`(:423)를 저장하며 **편집기 rawText를 전혀 반영하지 않는다** — 따라서 저장되는 version은 base+후보이고, reloadLatest는 그 version을 편집기에 올려 소실이 확정된다.

### 2. 가드 형태·위치 — 관용구 정확히 일치

- `WritingPanel.tsx:38-40` `dirty: boolean;` (필수 prop) + destructure(`:196`) → `dirty`는 **이미 인터페이스에 있던 prop**(availability helper에서만 쓰이던 것을 accept에도 소비). 작업자 "이미 부모가 전달 중" 주장 일치.
- `WritingPanel.tsx:393-405` 신규 가드:
  ```
  if (dirty && !window.confirm("저장하지 않은 편집 내용이 있습니다. 채택하면 그 내용은 사라지고, 채택된 후보가 새 version으로 저장됩니다. 계속할까요?")) {
    return;
  }
  ```
  - **위치**: 기존 early-return(`:384-391`: candidate/gate/nextUnit/busy/context 널체크) **직후**, `busyRef.current = true`(`:406`)·`setBusy("accepting")`(`:407`)·네트워크 호출(`:441` `acceptWriting`)·키 민팅(`:436` `crypto.randomUUID`) **전**. → 취소 시 busy 미진입, 네트워크 미발화, 후보/게이트/context 미소거. 작업자 "네트워크·키 민팅 전" 주장 일치.
- **관용구 일치**: `DraftEditor.tsx:163`(페이지 이동)·`:278`(version 전환, → return)·`:347`(근거-타 원고, → return)·`:360`(근거 version) 모두 `dirty && !window.confirm(msg)` → abort 패턴. 신규 accept 가드는 동일 패턴. **선례 관용구 정확 적용.**
- **"confirm이지 차단이 아니다" 결정의 정합성**: `WritingPanel.tsx:62-91` availability helper는 generate를 dirty에서 *차단*(`:84` "저장하지 않은 변경 사항이 있습니다") — generate는 깨끗한 base가 정합적 후보 생성에 필요하기 때문. 반면 accept의 후보 base는 generate 시점에 이미 frozen이므로 accept 자체는 dirty와 무관하게 유효 → 차단이 아닌 confirm(경고 후 진행/취소)이 정합. 작업자 결정 근거 일치.

### 3. Boundary matrix — 전 cell 매핑, 빈 cell 없음

| 계약 분기 | 방향 | 회귀 테스트 | 결과 |
|---|---|---|---|
| dirty → confirm 표시 (should fire) | — | WritingPanel "aborts...cancelled" (`confirmSpy` 1x) + DraftEditor 통합 (`confirmSpy` 1x) | ✓ |
| clean → confirm 미표시 (should NOT fire, **over-strict**) | over-strict | WritingPanel "does not prompt when clean" (`confirmSpy` not called) | ✓ |
| dirty + confirm=true → accept 진행 | — | WritingPanel "proceeds once confirmed" (fetch→accept 엔드포인트, `onAccepted` 1x) | ✓ |
| dirty + confirm=false → accept 중단 + 편집 보존 (**under-strict = 결손 자체**) | under-strict | WritingPanel "aborts" (`onAccepted` not called, fetch=2) + DraftEditor 통합 (편집 값 보존 + fetch=6 + 후보 잔존) | ✓ |

- **under-strict 잠금 검증**: 가드 제거 시 cancel 클릭에도 accept가 진행 → `confirmSpy` 미호출(또는 fetch 증가)로 양 테스트 re-fail. ✓
- **over-strict 잠금 검증**: 가드가 clean에서도 발화하면 "does not prompt when clean"의 `confirmSpy.not.toHaveBeenCalled()` re-fail. ✓
- **DraftEditor 통합 테스트 유효성**: rerender로 dirty를 조작하지 **않음** — 실제 `fireEvent.change(screen.getByLabelText("원고 본문"), { target: { value: kept } })`로 rawText를 바꿔 reactive하게 dirty=true를 전파. 즉 `dirty` prop 실전 배선을 관통하는 진짜 통합 테스트 (prop이 끊기면 `confirmSpy` 1x 단정이 fail). 단, instruction 필드 입력은 별도 state이므로 dirty에 영향 안 줌 → generate는 clean에서 허용(availability 통과)이라는 결손 전제도 테스트 구조와 일치.

### 4. pattern sweep — accept가 유일한 무가드 덮어쓰기 경로

`setRawText` 전 사이트(`DraftEditor.tsx`):

| 라인 | 사이트 | 가드 | 비고 |
|---|---|---|---|
| 135 | 초기 로드(effect) | 불필요 | 로드 시 rawText==baseline 동일 소스 → 비파괴, dirty=false |
| 288 | version 전환 | :278 dirty-confirm ✓ | 관용구 |
| 384 | 근거 열기 | :347/:360 dirty-confirm ✓ | 관용구 |
| 468 | reloadLatest(accept 후) | **본 수정 가드** ✓ | 결손 경로 |
| 535 | textarea onChange | 불필요 | 사용자 입력 자체 |

`ScratchRecovery.tsx`·`GenerationPad.tsx`는 편집기를 덮어쓰지 않음(D1=A 수동 복사, 읽기 전용 패드). → **accept가 유일한 무가드 경로였고 본 수정이 유일한 갭을 폐쇄**. 다른 경로는 이미 관용구로 가드됨. 작업자 "accept만 이 관용구가 빠져 있었다" 주장 일치.

### 5. 수치 주장 — 전항 정확 일치 (재실행)

| 항목 | 작업자 주장 | 독립 재실행 | 일치 |
|---|---|---|---|
| 테스트 | 187 passed / 13 files | **Test Files 13 passed · Tests 187 passed** (exit 0, WritingPanel 47=44+3 / DraftEditor 38=37+1) | ✓ |
| 타입 | `tsc` clean | `npx tsc --noEmit` exit 0, 출력 없음 | ✓ |
| 빌드 | 103 modules / JS 398.16 kB | `✓ 103 modules transformed` · `dist/assets/index-CirRm1P1.js 398.16 kB │ gzip: 122.75 kB` | ✓ |
| 백엔드/OpenAPI | 무변 | `git status` — modified 7개 파일 전부 frontend/src + docs, services/scripts 무변 | ✓ |

### 6. 계약 자기모순·spec-silent gap — 없음

- brief Deferred 항목이 "✅ 2026-07-22 별도 수정 완료"로 갱신됐고, CHANGELOG/HANDOFF/work_log의 서술과 상호 모순 없음. "비동기와 무관한 별개 결손"이라는 본질 기술이 코드(accept 동기 경로, async는 scratch 수동 복사)와 일치.
- spec-silent-but-code-enforced: 없음. 가드 메시지는 한국어 하드코딩이나 availability helper 주석("The Korean copy is localizable display text, not a machine contract")과 동일 관행 → 기계 계약 아님, 이슈 아님.

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix 전 cell 매핑, 양방향 잠금 확보, 결손 인과 사슬 코드로 실재 확인, 가드 위치·관용구 일치, 수치 주장 전항 재실행 일치. 차단 사유 없음.

### Hardening recommendations (비차단, 본 슬라이스 범위 밖 보강 후보)

1. **proceed(진행) 경로의 통합 테스트 부재**: DraftEditor 통합 테스트는 cancel 경로만 관통. confirm=true(진행) 시 `onAccepted → reloadLatest → setRawText` 사슬 전체(편집기가 새 latest로 실제 교체됨)를 끝까지 관통하는 통합 테스트는 현재 없음 — "proceeds once confirmed"는 WritingPanel **유닛** 테스트로 `onAccepted` 호출까지만 확인(실제 편집기 재로드 미검증). 계약(미저장시 confirm) 자체는 기존 4건으로 완전 잠금되어 있으므로 **비차단**이나, 가드가 보호하는 인과 사슬의 통합 단위 깊이를 보강하려면 proceed-path 통합 단정 1건이 유의미.

## Verdict

**합격 (PASS)**.

- 결손(accept 후 `reloadLatest()`가 편집기를 덮어써 미저장 입력 소실)을 코드 1차 소스로 실재 확인.
- 수정은 앱의 확립된 dirty-confirm 관용구(`dirty && !window.confirm(msg)` → return)를 accept 초입(busy/네트워크/키 민팅 전)에 정확히 적용. "confirm이지 차단 아님" 결정은 generate(차단)와 accept(base 이미 frozen → 유효)의 정합성 차이에 기반해 타당.
- boundary matrix 4 분기 전 cell 매핑, under-strict(결손 재도입 방지)+over-strict(clean 과잉 nag 방지) 양방향 잠금.
- pattern sweep: accept가 유일한 무가드 편집기 덮어쓰기 경로였고 본 수정이 갭 폐쇄. 다른 경로는 이미 관용구 가드.
- 수치 주장 4종(187/13, tsc clean, 103 modules/398.16 kB, 백엔드 무변) 전항 독립 재실행으로 정확 일치.
- 비차단 hardening 1건(proceed-path 통합 테스트)만 보강 후보로 명시.

## Outstanding items

- **커밋 미수행**: 7개 파일 modified(스테이징 안 됨, `git status` 확인). 작업자는 "이번 턴은 작업 진행만 지시받아 커밋 대기 중"이라 보고. 오너의 커밋 승인 대기 — 결함이 아님.
- 백엔드/OpenAPI 무변이므로 게시/배포 영향 없음.
- 본 결손(미저장 편집 소실)은 폐쇄. async-pad 슬라이스 잔여 후속(재시도 UI D4 deferred · per-draft 상한 dogfood 관찰 · 실 12B 풀스택 e2e)은 본 검증 범위 밖.

## Reproduction

```bash
# 전체 스위트 (187 passed / 13 files)
cd frontend && npx vitest run

# 타입 체크 (exit 0, 출력 없음)
cd frontend && npx tsc --noEmit

# 빌드 (103 modules, JS 398.16 kB)
cd frontend && npm run build

# 백엔드/OpenAPI 무변 + 변경 범위 확인
git status --short
git diff HEAD -- frontend/src/writing/WritingPanel.tsx
```

결손 인과 사슬 추적(읽기 전용): `frontend/src/writing/WritingPanel.tsx:383-405`(accept 가드) · `frontend/src/drafts/DraftEditor.tsx:156`(dirty 정의) · `:459-470`(reloadLatest 덮어쓰기) · `:649-652`(onAccepted→reloadLatest) · `:163/:278/:347`(선례 관용구).
