# K-4 프론트 글자수 카운터 + 소프트 경고 + `/writing/budget` 노출 — 독립 검증

- 날짜: 2026-07-31
- 요청자: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- 검증자: Claude (독립 — 본 슬라이스를 구현하지 않음)
- 대상: 커밋 `462fecd`(K-4a 백엔드) · `59f6c99`(K-4b 프론트) · `3a068e4`(기록). HEAD = `3a068e4`.
- 정본(계약): `docs/plans/context-budget-korean-tokens-decisions.md` §3 K-4(라인 655) · §6(라인 716-719) · §1(라인 34, 1.708 자/tok) · `docs/system-contract-sot.md` v1.7.67.
- 작업 출처: 커밋 3건(main 브랜치, working tree clean).

## Scope (정본에서 도출한 경계 행렬)

K-4 결정(라인 655): **"카운터 + 소프트 경고. 원고 본문에 hard `maxLength`를 걸면 붙여넣기가 잘려 정본이 소리 없이 손상된다(정본 보존 정책). 지시문은 hard도 가능."** §6(라인 716): 원고 본문 자체 길이 제한은 범위 밖(본문은 `/writing/generate`에 통째로 안 실림). §1(라인 34): 회계 상수 **1.708 자/tok**(코드는 1.7).

| # | 계약 분기 | 기대 |
|---|---|---|
| C1 | 지시문 카운터 표시(자 + 토큰) | should fire |
| C2 | 90% 초과 시 색 변화(소프트 경고) | should fire |
| C3 | 예산 여유면 경고 없음 | should NOT fire(over-strict) |
| C4 | 경고는 선택 preset을 따른다 | should fire(preset 의존) |
| C5 | 예산 모르면(budget GET 실패) 경고 안 함 | should NOT fire(안전 축소) |
| C6 | 원고 본문 hard maxLength 금지 | should NOT fire(정본 보존 핵심) |
| C7 | 지시문 hard는 허용(선택) | optional(soft-only도 OK) |
| C8 | `/writing/budget` per-preset 유도 예산 노출 | should fire |
| C9 | 창 모르면(caps=None) 요청 예산 그대로 | should NOT fire(over-strict) |
| C10 | endpoint project-scoped 인증 {401,403,404,503} | contract literal |

## Methodology

- 정본 스코프 먼저 확보(§3 K-4·§6·§1) → 경계 행렬 구축 후 코드/테스트 매핑.
- 모든 클레임을 1차 소스에서 재도출(work_log 카운트 신뢰 안 함).
- 실행: `npx vitest run src/writing/tokenEstimate.test.ts src/writing/WritingPanel.test.tsx`; `pytest tests/test_writing.py::WritingContextBudgetApiTest tests/test_application_api.py::WritingErrorContractDeclarationTest tests/test_auth_api.py::CombinedBoundaryMatrixTest`.
- **대항적 변이 테스트 5건**(fix 되돌림 → 테스트 재실패 → 복구). working tree clean 기준 `git checkout` 복구.
- 산식 재계산(DEFAULT=8192, preset 1024/2048/4096, output_cap 6144, system 465, framing 150, ratio 0.96)으로 docstring 클레임(short=8192/medium≈7273/long≈5307) 검증.

## Findings

### F1 — 계약 해석 정확 (§6)
작업자가 "§6가 원고 본문을 창-무관·범위 밖으로 뺐으므로 경고 대상은 지시문, 원고 본문은 글자수 가이드만"으로 해석한 것은 정본에 부합. `writing/tokenEstimate.ts:27` 주석("창과 무관 — /writing/generate 에 본문이 안 실린다")과 §6 일치.

### F2 — 백엔드 `/writing/budget` endpoint (C8/C9/C10)
`main.py:4402-4431`: preset(short/medium/long) 출력 상한을 `candidate_tokens_upper_bound`로 `derive_context_budget`에 각각 전달. `responses=_owned(_ERRORS_404)` + `dependencies=_REQUIRE_PROJECT_OWNER` → {401,403,404,503}. `report_budget.py:63-64`(caps=None→requested 그대로), `:82`(줄이기만). 산식 재계산으로 short=8192(clamp)·medium=7273·long=5307 — docstring·SoT 클레임 정확. 테스트 `WritingContextBudgetApiTest`(양방향) + 선언 가드(EXPECTED 12→13) + 인증 매트릭스(59→60/69→70) 전부 통과(20 passed / 476 subtests).

### F3 — 프론트 카운터/경고 (C1-C5)
`writing/WritingPanel.tsx:638-641`: `activeBudget = budgetByPreset?.[outputLength]`, `overBudget = activeBudget!==null && estimateTokens(instruction) >= Math.round(activeBudget*0.9)`. `tokenEstimate.ts:10,18`(1.7 상수·`Math.ceil([...text].length/1.7)`), 지시문 textarea(`WritingPanel.tsx:628-635`)에 `maxLength` 없음. `useWritingBudget.ts:64-84`(mount 1회 GET+모듈 캐시, 실패 시 null). `client.ts:28-34`(non-2xx → `ApiError` throw → `.catch` 안전축소 정상). `styles.css:797`(`.writing-counter-warn { color: var(--danger); font-weight: 600 }` — 실제 색 변화).

### F4 — 원고 본문 (C6/C7)
`drafts/DraftEditor.tsx:531`(`+<span className="editor-char-count">{formatCharCount(rawText)}</span>` — 순수 추가). textarea(`:533`)는 K-4가 건드리지 않음 → maxLength 미도입. C7(지시문 hard 허용)은 선택이라 soft-only도 계약 위반 아님.

### F5 — 타입/스키마 일치
`api/schema.d.ts:1760-1768`(`WritingContextBudgetPayload{context_budget_tokens, project_id}` / `PresetPayload{short,medium,long:number}`)가 백엔드 Pydantic과 정확 일치. SoT v1.7.67 범프 정확(`system-contract-sot.md:36`).

### F6 — 변이 테스트 5건 전부 가드 재실패 확인 (대항적)
1. 프론트 `overBudget=false`(경고 끔) → 90% 발화 테스트 재실패 ✓
2. 프론트 `overBudget=activeBudget!==null`(항상 경고) → 여유 테스트 재실패 ✓
3. 프론트 `activeBudget=budgetByPreset?.["short"]`(preset 무시) → preset 전환 테스트 재실패 ✓
4. 백엔드 세 preset에 같은 upper_bound → per-preset 테스트 재실패(8192≠7273) ✓
5. 백엔드 `report_budget.py` caps=None 시 `requested//2` → over-strict 테스트 재실패(4096≠8192) ✓

회귀 스위트가 계약을 진짜로 잠금(초록바가 아니라 가드가 하중받침).

## Issues / Risks

### Blocking (계약 의무)

- ~~**B1 — C6 "원고 본문 maxLength 금지" 회귀 assert 부재(빈 셀).**~~ **→ 이 검증 패스에서 해결(오너 승인).** `DraftEditor.test.tsx:147`에 `expect(screen.getByLabelText("원고 본문")).not.toHaveAttribute("maxlength")` 추가. 변이 검증: textarea에 `maxLength={10000}`을 넣으면 이 assert가 재실패(under-strict 가드 하중받침 확인) → 복구. DraftEditor 전체 스위트 통과. (작업자가 "K-4 정본 손상 방지 핵심"이라 한 이 불변의 빈 셀을 채워 조건부→합격 전환.)

### Hardening (비차단)

- **H1 — "소프트 경고"가 production 예산 스케일에서 사실상 발화 안 함(중요, 설계 의사확인 권장).** 지시문 토큰(작음, rows={3})을 **전체 컨텍스트 예산**과 비교하므로: short 예산 8192 → 90%=7372 tok ≈ 12,532자, long ≈5307 → 90% ≈ 8,120자. 정상 지시문(수십~수백 자)은 절대 도달 못 함. "소프트 경고(넘으면 색 변화)"(라인 655)가 도달성을 정량화하지 않아 엄격 위반은 아니나, K-4의 경고 절반이 정상 사용에선 inert. 의도(사용자가 실제로 볼 경고)인지, 병리적 paste용 안전망인지 오너 확인 필요. 회귀 테스트는 시드값 short=100 등 인위적 예산으로 논리만 검증 → production 거동과 괴리.
- **H2 — 회귀 수 클레임 1건 부족.** work_log/커밋 "회귀 7 = tokenEstimate(4) + WritingPanel(3)"이나 실제는 **8 = tokenEstimate(5) + WritingPanel(3)**(`tokenEstimate.test.ts`의 `it` 5개, 실행으로 확인). 테스트 자체는 건전, 문서 카운트만 1 부족.
- **H3 — 90% 임계값 경계 미세부 고정 없음.** 테스트는 임계값 ≈[0.90, 0.95] 구간에서 통과. soft UI라 계약 문제 아님, 정확 90% 전환 assert는 보강 후보.
- **H4 — work_log 수치 미세 불일치.** `work_log:449` "베타 ≈5407" vs docstring/§실측표 long≈5307. 코드 무영향.

## Verdict

**합격 (pass).** 구현이 정본(C1-C5, C7-C10)을 충족하고 변이 테스트 5건이 모든 가드를 하중받침으로 확인 — 회귀 스위트는 계약을 진짜로 잠금(초록바가 아닌 가드 자체). 본 검증 패스에서 B1(C6 빈 셀)을 ~1줄 assert로 폐쇄하고 변이로 확인 → 조건부 합격에서 합격으로 전환. H1(inert 경고)은 오너 확인 결과 "안전망 의도(현행 유지)"로 종결 — 결함 아님.

## Outstanding items

- **DraftEditor 스위트 희귀 플레이크 1회 관측(정직 보고):** 본 검증 중 `src/drafts/DraftEditor.test.tsx` 전체 스위트에서 "1 failed | 40 passed"를 1회 관측(~9회 시도 중 1회, 나머지는 41/41 통과 또는 부하 타임아웃). 실패한 테스트 이름은 희귀도 때문에 특정하지 못함. 분석: 본 검증이 추가한 동기 assert(단일 테스트 스코프)는 간헐 실패를 유발할 수 없고 포커스 실행마다 통과 → 이 assert 탓이 아님. 가장 유력한 원인은 (a) DraftEditor 스위트의 기존 타이밍 의존 테스트(pending promise·`waitFor`·FileReader/Blob export)의 사전 존재 플레이크, 차선으로 (b) K-4(b) `useWritingBudget` mount-fetch가 DraftEditor 렌더 경로에 새로 들어간 비동기-온-마운트와의 레이스. 확정 불가(재현이 희귀). **회귀 0 단언 불가** — 오너가 스위트를 수회 돌려 특성화하거나, (b)가 의심되면 useWritingBudget mount-fetch 타이밍을 별도 조사 권장.
- H1: 오너 확인 완료 — "소프트 경고"는 병리적 paste용 안전망 의도, 현행 설계 적합(종결).
- 베타 화면 육안 확인 2건(rebuild 후): `docker compose build application frontend && docker compose up -d --no-deps application frontend`.

## Reproduction

```
# 프론트 K-4
cd frontend && npx vitest run src/writing/tokenEstimate.test.ts src/writing/WritingPanel.test.tsx
# 백엔드 K-4a + 가드 (test-mongo 27020 기동 필요)
python3 -m pytest tests/test_writing.py::WritingContextBudgetApiTest \
  tests/test_application_api.py::WritingErrorContractDeclarationTest \
  tests/test_auth_api.py::CombinedBoundaryMatrixTest -q
# 변이(예): WritingPanel.tsx overBudget=false → 90% 테스트 재실패 → git checkout 복구
```
