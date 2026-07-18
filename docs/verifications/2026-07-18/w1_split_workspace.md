# Verification — Writing Workspace V2 W1 split workspace

## Subject metadata

- 날짜: 2026-07-18
- 요청자: 오너(독립 검증 요청 — “다음 작업 검증해줘. W1 split workspace 구현과 커밋까지 완료”).
- 검증자: Claude(독립 adversarial 검증, `ultracode` session).
- 검증 대상 slice/artifact: W1 split workspace — `frontend/src/drafts/DraftEditor.tsx`(+280), `frontend/src/review/WorkspaceReviewPanel.tsx`(신규 +234), `frontend/src/review/AnalysisTrigger.tsx`(+15), `frontend/src/styles.css`(+189), 테스트 +262행, SoT v1.7.11·HANDOFF 등 문서 6개.
- 정본 계약 참조: `docs/live_review_briefs/2026-07-18/writing_workspace_ux_restructure.md`(“Slice W1” + “수용 기준” + “추가로 권장하는 UX 보강”), `docs/plans/writing-workspace-v2-w0-contract.md`(W0 anchor), `docs/system-contract-sot.md` v1.7.11.
- 작업 소스: 커밋 `b0d9203` (feat: Writing Workspace V2 W1 split workspace). working tree clean.
- 방법론 스케일: 검증자 직접 정량·코드 검증 + 46-agent 다차원 adversarial 워크플로우(4 dimension × review→적대적 verify + completeness critic).

## Scope

1. **코드 정확성·race·edge case** — DraftEditor.tsx(openSource·codePointSpan·submit·selectVersion·selectPanel·reloadLatest·상태 전이), WorkspaceReviewPanel.tsx(runAction·load·source 복원·exactSource)의 모든 분기 추적.
2. **테스트 품질·boundary coverage** — 130 passed가 W1 수용기준과 코드 분기를 실제로 lock하는지, 양방향 가드, mock 현실성, 빈 칸.
3. **UX/계약 정합** — W1 수용기준(editor 떠나지 않고 분석/검토/근거 대조, source exact version/offset, stale/latest 숨기지 않음, query 복원, 반응형, 상태줄) 대 실제 구현.
4. **통합 호환·보안** — 기존 C0/C1/C2/B·WritingPanel/AnalysisTrigger 재사용, backend/OpenAPI/W0 schema 무변, build/타입, XSS/URL injection/memory leak.

## Methodology

- **검증자 직접 정량 검증**: `npm run test`(130 passed/9 files 재실행), `npm run build`(`tsc --noEmit && vite build` 95 modules 재실행), `git show --stat b0d9203`(backend·openapi·schemas 파일 부재 확인), `git diff --check`(exit 0), backend `splitter.py`/`service.py`/`accept.py` 직독으로 offset 기준·accept literal 재확인, source_ref offset이 Python code point 기준(`splitter.py:54-57` `offset+=len(line)`, `:41`/`service.py:400` code point slicing)임을 교차 증명.
- **46-agent adversarial 워크플로우**: code-correctness / test-quality / ux-contract / integration-security 4 dimension. 각 dimension review→각 finding마다 독립 verifier가 refute 시도. completeness critic이 4 dimension이 놓친 빈 칸 탐지. 45 done, 1 일시적 에러.
- 재현 명령은 하단 “Reproduction”.

## Findings

### Surface 1 — 코드 정확성·race·edge case

- **(B1) `frontend/src/drafts/DraftEditor.tsx:309-317` openSource cross-draft navigate가 dirty confirm을 건너뜀** — source의 `snapshot_id`가 다른 draft에 있을 때, `navigate()`로 전환하며 `return`하는데 **dirty 검사·`window.confirm`이 없다**. 같은-draft 다른-version 분기(`:319-323`)는 `dirty && target.id !== selectedVersionId && !window.confirm(...)`로 gate한다. 비대칭. `beforeunload`(`:145-152`)는 SPA `navigate()`에 발화하지 않아 이 경로를 잡지 못한다. 결과: 사용자가 d1에서 타이핑하다가 WorkspaceReviewPanel의 source pointer(프로젝트 단위 `listReviewInbox`라 어떤 draft의 snapshot이든 올 수 있음)를 클릭하면, d1의 미저장 편집이 d2 로드(`:90-132`가 `setRawText`/`setBaseline` 덮어쓰기)로 **silently 손실**된다. `submit()`이 유일한 persist 경로이므로 복구 불가. workflow probe가 `window.confirm` 호출 0회 + heading이 d2로 바뀜을 실증. selectVersion(`:242-247`)·same-draft 분기(`:319-323`)가 확립한 “dirty 전환 시 confirm” 규칙의 **빈 칸**이자 실제 데이터 손실 bug.
- **(H-CC-02) `WorkspaceReviewPanel.tsx:136-150` runAction 뒤 load() 실패 시 stale** — confirm/reject 성공 후 `await load()`가 throw하면 `setData`/`onPendingCountChange` 미실행(외부 catch는 error만 set). list·pending count가 stale. 사용자가 완료한 action 재시도 → 혼란 에러(409 등). 빈도 낮지만 real.
- **(positive CC-04~08) 정확한 분기들** — render guard(`:457`)가 cross-draft 직후 versions-not-loaded race를 차단; `codePointSpan` code point→UTF-16 변환 정확; `intentRef` reuse가 모든 save outcome에서 정확 clear; `savingRef/selectingRef/exportingRef/intentRef`가 finally에서 일관 reset; `openSource` `useCallback` dep array 완전(stale-closure 없음). 모두 confirmed.

### Surface 2 — 테스트 품질·boundary coverage

130 passed/9 files, DraftEditor 29 tests. 핵심 boundary는 충실히 잠겼다(emoji code point 변환, latest-vs-과거 양방향, cross-draft jump navigation+selection, in-flight 경쟁, optimistic patch 없는 서버 재조회). **하지만 W1이 claim하는 기능/가드 중 회귀가 없는 빈 칸이 있다.**

- **(B2) 상태줄 렌더링 회귀 부재(W1-04, confirmed)** — DraftEditor가 렌더하는 상태줄(“저장 안 됨/저장됨·분석 상태·검토 대기 N건”, `:461-465`)을 assert하는 테스트가 없다. 이것은 W1의 명시적 deliverable(“저장·분석·검토 대기 상태줄”)인데 lock이 없다.
- **(B3) reject action 회귀 부재(W1-05, confirmed, blocking 승격)** — `WorkspaceReviewPanel.test.tsx`는 confirm만 실행(`:91-110`). `runAction("reject")` 경로에 테스트 없다. confirm/reject가 같은 `runAction`을 쓰지만 별도 endpoint·의미이므로 양쪽 회귀 필요.
- **(B4) same-draft dirty-confirm guard 회귀 부재(W1-03, confirmed, blocking 승격)** — `openSource`의 같은-draft 다른-version 분기(`:319-323`) confirm guard가 테스트 안 됨(test 751은 confirm 없이 historical source를 연다). CC-01 fix와 함께 양쪽을 lock해야 한다.
- **(B5) cross-draft “snapshot not found” error 회귀 부재(W1-02, confirmed)** — `target===undefined`일 때 “이 근거가 가리키는 원고 version을 찾을 수 없습니다.”(`:304-307`) 분기에 테스트 없다.
- **(B6) quote/content_hash mismatch error 회귀 부재(W1-01, NO-VERDICT이나 검증자 확인)** — `:333-341`의 근거 무결성 검증 실패 분기(“근거의 offset 또는 내용이 저장된 version과 일치하지 않습니다.”)에 테스트 없다. 이것은 stale 근거를 잡는 핵심 가드인데 lock이 없다.
- **(H-W1-06/07)** `codePointSpan` null-return guard(`start<0`/`end<=start`/`end>length`) 미테스트; rail tablist(이어쓰기/분석/검토) presence/switch 미테스트.
- **(positive W1-09/10/11)** latest-vs-stale 라벨 진성 양방향; cross-draft jump가 navigation AND selection restore 양쪽 assert; Unicode offset이 shift/no-shift 양방향 + query restore lock.

### Surface 3 — UX/계약 정합

- **(C1) `selectPanel`이 writing/analysis 전환 시 `?candidate`·`?source` 삭제(`:166-169`)** — ux CC-02/GAP-07(confirmed blocking → 해석 의존). review→writing→review 복귀 시 in-review source 컨텍스트가 유실된다. 브리프의 “candidate/detail query 복원”(Slice W1)·“패널 상태 보존”(추가 권장)과 긴장. 의도적 컨텍스트 정리로 볼 수도 있어 owner 결정 사항이나, 사용자가 실수로 탭을 눌렀다 돌아오면 source 점프가 사라지는 footgun.
- **(C2) sourceNotice가 Writing accept/save/version switch 후에도 잔류(GAP-01, critic 발견, 검증자 확인)** — `sourceNotice`는 `openSource`에서만 설정(`:352`/`:355`)되고 `selectVersion`/`submit`에서 clear되지 않는다. version 전환 후 “현재 version N 근거”가 실제 선택 version과 안 맞을 수 있다(stale notice). 데이터 손실은 아니나 잘못된 정보 표시.
- **(H-ux-04/05/06/07/08/09)** ARIA tab pattern 불완전(tab에 id+aria-controls, tabpanel에 id+aria-labelledby 부재); 모바일 source jump가 scroll-into-view 안 함; AnalysisTrigger 성공 메시지·“검토함 →” 링크가 editor에서 벗어남(`/projects/:id/review`); “검토 대기 N건”이 rail이 처리 못 하는 gate_findings 포함(=GAP-05, 과대 계수); sourceNotice가 code-point offset을 표시하지만 editor 선택은 UTF-16 offset이라 숫자가 다름; confirm/reject 후 다음 pending으로 advance 안 함.
- **(H-CC-13/ideation)** analyze→review 루프 자급화: accept/analysis 완료 시 rail 자동 갱신으로 editor를 떠나지 않는 루프(별도 owner 결정).
- **(positive ux CC-10/11/12)** openSource가 snapshot_id+version+quote match+content_hash match를 모두 검증 후 표시; sourceNotice가 색이 아닌 한국어 텍스트로 latest/stale 구분(브리프 권위 배지 기준 충족); dirty-state guard(beforeunload·version-switch confirm·source-jump confirm)가 CC-01 제외하고는 강함.

### Surface 4 — 통합 호환·보안

- **(positive POS-01~07, 모두 confirmed)** 커밋이 순수 frontend — backend·OpenAPI·W0 schema 무변 주장 TRUE(`git show --stat`로 services/·openapi·schemas 부재 확인); WritingPanel·AnalysisTrigger·WorkspaceReviewPanel prop type이 정확 일치; Review Inbox route(`/projects/:id/review`, `/review/:candidateId`) 유지·등록; WritingPanel은 W1 미변경·AnalysisTrigger 변경은 additive(onStatusChange optional)라 standalone consumer 깨짐 0; build 95 modules + test 130/130 검증자 재도출; XSS sink 없음(React auto-escape, URL param은 API id로만 사용); memory cleanup(beforeunload listener·blob URL·active-flag effect) 정확.
- **(H-HARD-01)** `crypto.randomUUID()`가 3곳(DraftEditor submit, WritingPanel, 기타)에서 unguarded. non-secure context(non-localhost HTTP)에서 `TypeError`. 로컬 도구라 당장 영향 낮으나 hardening 후보.
- **(H-HARD-02/GAP-06)** 409 stale-base accept가 editor를 stale versions/latestVersionId 상태로 둬도 reload affordance 없음.

## Issues / Risks

### Blocking(correctness bug + contract-required test empty cells)

- **B1 — `DraftEditor.tsx:309-317` cross-draft navigate dirty-confirm 누락(데이터 손실 bug)**: CC-01 confirmed. fix = 같은-draft 분기(`:319-323`)의 `dirty && !window.confirm(...)` guard를 cross-draft 분기(`:309-317`)의 `navigate()` 앞에도 적용. 이것만으로도 W1은 합격이 아니다(사용자 미저장 편집 silently 손실).
- **B2 — 상태줄 렌더링 회귀 부재(W1-04)**: W1 명시 deliverable. dirty/분석상태/검토대기 count 렌더를 assert하는 회귀 추가.
- **B3 — reject action 회귀 부재(W1-05)**: `runAction("reject")` 경로 회귀 추가(confirm와 별도 endpoint).
- **B4 — same-draft dirty-confirm guard 회귀 부재(W1-03)**: `openSource` `:319-323` confirm guard 회귀 추가. B1 fix와 함께 양쪽 lock.
- **B5 — cross-draft “snapshot not found” error 회귀 부재(W1-02)**: `:304-307` 분기 회귀 추가.
- **B6 — quote/content_hash mismatch error 회귀 부재(W1-01)**: `:333-341` 근거 무결성 검증 실패 분기 회귀 추가. stale 근거를 잡는 핵심 가드.

B2~B6은 모두 “W1이 claim하는 기능/가드에 named 회귀가 없는” empty cell로, CLAUDE.md “boundary matrix has no empty cells”에 해당. 단, 기존 29 test가 핵심 경로를 잘 잡고 있어 fix는 회귀 추가로 국한된다.

### Owner 결정 사항(해석 의존)

- **C1 — selectPanel candidate/source 삭제(`:166-169`)**: 의도적 컨텍스트 정리 vs query 복원/패널 상태 보존 위반. owner가 어느 쪽인지 결정(삭제 유지 시 문서화, 복원 시 fix).
- **C2 — sourceNotice 잔류(GAP-01)**: version/accept/save 시 `setSourceNotice(null)` 추가로 해결. 미세 정확성 bug.
- **GAP-03 reloadLatest race / GAP-04 status bar non-active-tab stale**: critic 발견(verify 미경유). GAP-03은 WritingPanel의 dirty guard가 대부분 방지하므로 약한 blocking; GAP-04는 hardening 수준.

### Hardening recommendations(non-blocking)

- H-CC-02(runAction load() 실패 시 stale list/count), H-W1-06/07(codePointSpan null guard·rail tablist 미테스트), H-ux-04(ARIA tab id/controls), H-ux-05(모바일 scroll-into-view), H-ux-06(analysis 성공/review 링크 editor 이탈), H-ux-07/GAP-05(gate_findings count 과대), H-ux-08(offset 숫자 불일치), H-ux-09(다음 pending advance), H-HARD-01(crypto.randomUUID guard), H-HARD-02/GAP-06(409 stale-base reload).

### Positive strengths(verified)

W1 핵심 7 deliverable(editor+docked rail, 모바일 단일 열 tab, query 복원 라우팅, 같은/다른 원고 exact version/source 이동, Unicode offset 변환, 최신/과거 근거 표시, Review rail 서버 재조회)은 정확히 동작하고 대부분 adversarial verify에서 confirmed. 특히 codePointSpan 변환·cross-draft jump·latest/stale 라벨·backend 무변·prop 일치·build/test 재도출은 강점.

## Verdict

**조건부 합격(conditional pass)**.

하중 이유:
1. W1의 핵심 deliverable은 정확히 동작하고 다수의 adversarial verify에서 confirmed. 정량 주장(130 passed/9 files, build 95 modules, backend·OpenAPI·W0 schema 무변, git diff --check, working tree clean, 커밋 b0d9203)은 검증자가 전부 재실행·재도출해 사실 확인. Unicode offset 변환·cross-draft jump·latest/stale 라벨 등 미묘한 기술 축도 정확.
2. **그러나 B1 — cross-draft navigate dirty-confirm 누락은 실제 데이터 손실 bug다.** 사용자 미저장 편집이 silently 손실되며, 같은 코드의 인접 분기가 확립한 guard 규칙의 빈 칸이다. 이것만으로 W1을 무조건 합격 처리할 수 없다.
3. B2~B6은 W1이 claim하는 기능(상태줄)·가드(reject, dirty-confirm, not-found, quote/hash mismatch)에 named 회귀가 없는 empty cell로, CLAUDE.md “boundary matrix has no empty cells”에 해당.
4. 모든 blocking 항목은 fix가 작다(B1은 guard 1줄 추가; B2~B6은 회귀 추가). 따라서 “불합격(근본 결함)”이 아니라 “조건부 합격(fix 조건)”이 공정하다.

**합격으로 올리기 위한 조건**:
- **필수**: B1 cross-draft dirty-confirm guard 추가(데이터 손실 차단). B4 same-draft guard 회귀와 함께 양쪽 lock.
- **필수(회귀 빈 칸)**: B2(상태줄 렌더), B3(reject), B5(cross-draft not-found), B6(quote/hash mismatch) 회귀 추가.
- **권장**: C1 selectPanel 동작 owner 결정·문서화, C2 sourceNotice clear.
- 위 조건 충 시 합격(PASS).

이 검증은 owner 요청 독립 검증이며 검증자는 defect를 silent하게 fix하지 않는다(CLAUDE.md). B1은 작은 fix이므로, owner가 원하면 검증자가 fix + 회귀 추가를 수행할 수 있다.

## Outstanding items

- W1은 커밋 `b0d9203`으로 이미 확정. B1 데이터 손실 bug가 포함되어 있으므로, owner는 후속 커밋으로 B1 fix + B2~B6 회귀를 추가하는 것을 권장. fix 없이 W2로 넘어가면 데이터 손실 경로가 정본에 남는다.
- 검증 중 1개 agent가 일시적 에러(W1-01 verify rate-limit). B6로 전환, 검증자 직독으로 보충.
- runtime 코드(frontend)이므로, fix 시 `npm run test` + `npm run build` 재실행 필요.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. 정량 주장 재실행
(cd frontend && npm run test)   # expect 130 passed / 9 files
(cd frontend && npm run build)  # expect tsc PASS + vite 95 modules transformed

# 2. backend/OpenAPI/W0 schema 무변 + whitespace
git show --stat b0d9203 | grep -E "services/|openapi|schemas/" && echo CHANGED || echo UNCHANGED
git diff --check b0d9203~1 b0d9203   # exit 0

# 3. B1 데이터 손실 bug 직접 확인 — cross-draft 분기(309-317)에 dirty 확인이 없고
#    같은-draft 분기(319-323)에는 있다 (비대칭 = bug)
sed -n '309,323p' frontend/src/drafts/DraftEditor.tsx

# 4. offset 기준 교차 증명 — backend는 Python code point 기준
sed -n '54,59p' services/application/app/core_sot/splitter.py        # offset += len(line)
sed -n '39,47p' frontend/src/drafts/DraftEditor.tsx                  # Array.from (code point) → UTF-16

# 5. 테스트 빈 칸 확인 (B2~B6): 아래 분기/기능에 해당 test가 있는지 grep
grep -nE "검토 대기|분석 .*대기|status.*bar|상태줄" frontend/src/drafts/DraftEditor.test.tsx   # B2: expect none
grep -n "reject" frontend/src/review/WorkspaceReviewPanel.test.tsx                            # B3: expect none
grep -n "버리고 근거 version" frontend/src/drafts/DraftEditor.test.tsx                         # B4: expect none
grep -n "가리키는 원고 version을 찾을 수 없" frontend/src/drafts/DraftEditor.test.tsx           # B5: expect none
grep -n "offset 또는 내용이 저장된 version과 일치하지 않" frontend/src/drafts/DraftEditor.test.tsx  # B6: expect none
```
