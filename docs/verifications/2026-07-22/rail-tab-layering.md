# 검증 기록 — 우측 레일 탭 레이어화 (dogfood 결손 수정)

## Subject metadata
- 날짜: 2026-07-22
- 요청자: 오너 (kdtyohan)
- 검증자: Claude (독립 감사)
- 대상 슬라이스: 우측 레일 3탭 항상 마운트 + 비활성 hidden 레이어화, WorkspaceReviewPanel `tabActive` fetch 게이트
- 소스: commit `eb304ed` (working tree clean)
- 정본 참조: 별도 spec-contract 문서 없음 — dogfood UI 결손 수정. 판정 기준은 CLAUDE.md §3(외과적 변경) / §4(테스트로 재현 후 통과) / §5.

## Scope
1. 커밋 diff (DraftEditor.tsx / WorkspaceReviewPanel.tsx / styles.css / DraftEditor.test.tsx)
2. 결손 (a) — WritingPanel 로컬 입력 state가 탭 전환에 유지되는가
3. 결손 (b) — 백그라운드 통로(GenerationPad/ScratchRecovery) 유지
4. `tabActive` fetch 게이트의 정확성·부작용·비대칭성
5. `.hidden` 전역 클래스 충돌
6. 회귀 테스트가 결손을 실제로 잠그는지
7. green-bar 주장 독립 재현 (tsc / vitest)
8. 이슈 1(잔재 500 → mongo 볼륨 초기화) 근본 원인 여부

## Methodology
- `git show eb304ed` — 전체 diff 정독
- WritingPanel.tsx:200-236 — 입력 필드가 로컬 `useState`인지 확인
- AnalysisTrigger.tsx — 마운트 시 useEffect/fetch/폴링 존재 여부
- `git grep 'hidden' -- src/` — 클래스명 충돌
- DraftEditor.test.tsx 정독 (탭 전환·ordered-mock 정렬)
- `npx tsc --noEmit` (exit code)
- `npx vitest run` (파일/테스트 카운트)

## Findings

### 결손 (a) — 입력값 유지 [코드상 수정 확인]
WritingPanel의 `instruction`/`writingIntent`/`nextTitle`/`nextKind`/`nextGoal`/`candidate`/`gate`/`loopResult`는 모두 컴포넌트 로컬 `useState` (WritingPanel.tsx:200-217). 수정 전 `activePanel === "writing" && (...)` 조건부 렌더 → 비활성 탭에서 언마운트 → 소실. 수정 후 3탭 항상 마운트 + `.hidden`(display:none) 레이어 (DraftEditor.tsx:634-693). 코드상 state 유지 성립.

### 결손 (b) — 백그라운드 통로 [코드상 수정 확인]
GenerationPad/ScratchRecovery는 writing 레이어 안에 위치하며, 활성 job은 DraftEditor 소유 state(`generationJobs`)라 원래도 유지. 수정으로 통로 패드 자체가 언마운트되지 않아 통로 유지. 완료 배지 흐름은 기존 테스트(DraftEditor.test.tsx:1038)로 커버.

### `tabActive` 게이트 [정확·간접 잠금됨]
WorkspaceReviewPanel은 항상 마운트하되 `if (tabActive === false) return;`로 inbox/detail fetch 스킵 (WorkspaceReviewPanel.tsx:76, 102). `tabActive?: boolean` 기본 undefined는 `=== false` 비교로 "활성" 취급 → 독립 유닛 렌더 무해. 테스트 1149(분석→검토 전환)는 review-inbox 응답이 탭 활성 시에만 소비되도록 ordered-mock 정렬에 의존 → 게이트 제거 시 mock 인덱스 붕괴로 실패. **게이트 방향은 잠겨 있음(간접).**

### AnalysisTrigger 비대칭 [정당]
AnalysisTrigger.tsx에 useEffect/마운트 fetch/폴링 없음 — 클릭 구동뿐. 항상 마운트해도 낭비 fetch 없음 → 게이트 불필요. ReviewPanel만 게이트한 비대칭은 오설계 아님.

### `.hidden` 전역 클래스 [충돌 없음]
`git grep hidden -- src/` 결과 다른 컴포넌트는 `aria-hidden` 속성만 사용, `className="...hidden..."` 미사용. `.rail-layer.hidden` 특이도는 소스 순서로 해소(styles.css에서 `.hidden` 후위), `!important`는 중복이나 무해.

### 방어 렌더링 [저위험]
`detail?.actions?.find`, `data?.items?.length ?? 0` 등 옵셔널 체이닝 추가 (WorkspaceReviewPanel.tsx:62-63, 175-177) — 불완전 응답 크래시 가드. 해당 경로 테스트는 없으나 결손 범위 밖 저위험.

### green-bar 독립 재현 [확인]
- `npx tsc --noEmit` → exit 0
- `npx vitest run` → **Test Files 13 passed / Tests 193 passed** (작업 AI 주장과 일치)
- build는 재실행 안 함(tsc clean + 전 테스트 green으로 충분 근거)

## Issues / Risks

### Blocking (CLAUDE.md §4)
- **핵심 수정에 회귀 테스트 부재.** 이 커밋의 중심 행위 — WritingPanel 로컬 입력 state가 탭 전환에 유지 — 를 잠그는 테스트가 없다. 테스트 파일 변경은 코멘트 2줄뿐(신규 테스트 0). 조건부 렌더(`activePanel === "writing" && ...`)로 되돌려도 193 테스트 전부 green으로 남는다. 테스트 1140이 타이핑하는 "원고 본문"은 DraftEditor 소유 state라 원래도 소실되지 않았고, 실제로 소실되던 패널-로컬 state는 어떤 테스트도 검증하지 않는다. CLAUDE.md §4("버그 수정 → 재현 테스트 먼저 작성 후 통과")·양방향 가드 요구의 정확한 미충족.
  - 권장 테스트: `이어쓰기 지시` 필드에 입력 → `분석` 탭 클릭 → `이어쓰기` 탭 복귀 → 필드 값 유지 assert (under-strict: 조건부 렌더 복귀 시 실패해야 함).

### Hardening recommendations (비차단)
- 방어 옵셔널 체이닝 경로(불완전 review 응답)에 대한 테스트는 없음 — 결손 범위 밖, 선택적 보강.

## Outstanding items
- **이슈 1(잔재 500) 근본 원인 미규명.** mongo dev 볼륨 초기화로 pre-`ordered` 레거시 draft 데이터를 제거해 해소 — `list_drafts` 읽기 경로가 레거시 데이터에서 왜 500을 내는지 진단하지 않음. `scripts/migrate_ordered_units.py` 마이그레이션 경로는 존재. 로컬 1인 dogfood·폐기 가능 데이터 환경에선 수용 가능하나, 읽기 경로의 레거시 데이터 견고성은 미검증. 커밋 diff 밖(인프라 조치).
- pending-count 배지가 review 탭 방문 전엔 갱신 안 되는 점은 수정 전과 동일 — 회귀 아님.

## Verdict
**합격 (조건 해소됨).** 초기 판정은 "조건부 합격"이었다 — 두 결손의 코드 수정은 타당하고 부작용 감사(게이트 정확성·비대칭 정당성·클래스 충돌·green-bar)를 모두 통과했으나, CLAUDE.md §4가 요구하는 핵심 수정(입력 state 유지)의 회귀 테스트가 부재했다.

**조치(검증자가 보강)**: DraftEditor.test.tsx에 회귀 테스트 추가 —
"preserves the Writing panel instruction input across a tab switch (탭 전환 state 유지)".
- under-strict 가드 **증명 완료**: writing 레이어를 조건부 렌더(`activePanel === "writing" && …`)로 임시 되돌려 실행 → `이어쓰기 지시` 필드가 `""`로 실패(Received: 빈 값). 원복 후 통과. 즉 되돌리면 재실패한다.
- over-strict 방향: 탭 전환 중 "이 원고 분석" 버튼 존재를 assert → no-op 전환으로는 통과 불가.
- 전체 스위트 194 passed / 13 files, tsc clean.

이슈 1(잔재 500)은 근본 원인 미규명이나 로컬 dogfood 폐기가능 데이터 환경 특성상 비차단으로 유지.

## Reproduction
```
cd frontend
npx tsc --noEmit          # exit 0
npx vitest run            # 13 files / 193 tests passed
git show eb304ed          # diff 정독
```
