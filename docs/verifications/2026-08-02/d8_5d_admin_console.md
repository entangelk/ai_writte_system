# D8-5d — 관리자 화면 (첫 프론트 슬라이스)

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. D8-5d 관리자 화면")
- **검증자**: Claude Code(구현자와 다른 세션, 적대적 검증)
- **대상**: 커밋 `6f0d521`(구현) + `4dc1129`(정본·기록)
- **정규 스펙**: `plans/auth-d8-5-admin-decisions.md` §4(5-d), `system-contract-sot.md` v1.7.80(C-6 공백의 원처)
- **검증 소스**: 커밋 `4dc1129`(HEAD). 검증자는 프론트 코드·테스트·정본을 코드에서 재도출.
- **특이**: D8-5 트랙의 첫 프론트 슬라이스. 백엔드(pytest)가 아니라 프론트(vitest·빌드)가 검증 주표면.

## Scope

관리자 전용 `/admin` 화면과 그에 딸린 프론트 경계. 작업 AI가 나열한 8항목 중 보안/계약 하중을 지는 것을 본다.

1. **/admin guard** — 비관리자 직접 URL 접근 차단(`AdminRoute`).
2. **C-6 공백 해소** ★ — C-6이 남긴 "관리자 계정 브라우저 로그인 불가"를 new_password 교체 UI로 닫는지.
3. **12자 경계** — 새 비밀번호 12자 + 확인 일치(양방향).
4. **무소유 project 승격 차단** — D8-5e owner_id=None Blocking의 프론트 UX 대응.
5. **lazy loading + 플레이크** — 관리 화면 lazy; 이전 K-4가 잡은 ~1/9 프론트 플레이크 재현 가능성.

## Methodology

- 프론트: `npm run test`(vitest run)·`npm run build`(tsc --noEmit + vite build). 백엔드: `pytest -q`(D8-5d 무변 확인).
- 프론트 뮤테이션 4종 + 플레이크 관찰(3회 연속)은 독립 에이전트가 `Edit` → `npm run test` → 원복 → `git status` clean으로 재현(커밋 0건).
- 코드 경로 직접 추적. 모든 단언에 `file:line` 근거.

## Findings

### 회귀·빌드 — 정확히 재현
- 프론트 `npm run test`: **234 passed / 17 files / 51.68s**, exit 0.
- 프론트 `npm run build`: exit 0. `AdminConsole-PV8U6OpQ.js`(5.50 kB)가 별도 chunk로 분리 → lazy loading 확인.
- 백엔드 `pytest -q`: **1900 passed / 4 skipped / 1608 subtests**, exit 0. D8-5d는 백엔드 무변(`tests/` 미변경). 1900 = C-6(1898) + `4eb4aa2`(C-6 hardening +2셀) 기준선.

### 뮤테이션 4개 가드 — 전부 작동 (에이전트 독립 재현)
| 가드 | 변이 | 실패 셀 |
|---|---|---|
| 관리자 가드(`AdminRoute` `if (!user.is_admin)`) | `if (false)` | `App.test.tsx:285`("does not expose the admin route…for a non-admin") |
| 12자 under-strict(`< 12`) | `< 1` | `App.test.tsx:253`(10자가 disabled 안 됨) |
| 12자 over-strict(`!== confirmation`) | `false` | `App.test.tsx:259`(불일치가 disabled 안 됨) |
| C-6 409 분기(`status === 409 && !mustReplacePassword`) | `false &&` | `App.test.tsx:247`("replaces an administrator-set password…") |
| 무소유 승격(L173 힌트) | `false` | `AdminConsole.test.tsx:59`(힌트 텍스트) |

12자 경계는 CLAUDE.md §4 "Two-directional regression guards"의 양방향 락을 충족.

### ★ C-6 공백 해소 — 잠겼다
C-6 검증(`d8_5_c6_forced_password_change.md`)이 ★로 D8-5d 필수 항목으로 올린 "관리자 계정 브라우저 로그인 불가"가
`AuthGate.tsx` `LoginScreen`으로 닫혔다: 409 → `mustReplacePassword` 전환 → 새 비밀번호(12자 + 확인 일치)를
`new_password`로 전송(L178-182, L188-190, L252-290). 위 409 분기 셀이 이 흐름을 잠근다.

### 무소유 project 승격 — 프론트 UX로도 차단
`AdminConsole.tsx:173-179`가 `owner_id === null`인 project의 사유 입력을 숨기고 승격 버튼을 disabled.
백엔드 403(D8-5e `8f3c52e` fix)과 이중. 하지만 아래 Hardening 참조.

### 플레이크 부재
234셀 3회 연속 234/234 합격. 타이밍 의존 셀 없음. 이전 K-4 검증(`2026-07-31/k4_front_counter_budget.md`)이
잡은 ~1/9 플레이크는 WritingPanel 글자수 카운터 영역이라 이번 관리 화면 셀들(fetch mock 기반)과 무관.

## Issues / Risks

### Blocking (계약 의무 위반)
없음.

### Hardening recommendations (비차단)
**무소유 project 버튼 disabled 단정이 vacuous.** `AdminConsole.test.tsx:58`의
`within(orphanProject).getByRole("button", { name: "1시간 읽기 권한 발급" }).toBeDisabled()` — 이때
`state.reason`이 빈 문자열이라 `disabled` 조건 중 `reason.trim() === ""`가 이미 true다. 즉 owner_id 조건
(`project.owner_id === null`)을 제거해도 버튼이 여전히 disabled여서 **이 단정은 owner_id disabled-prop을
직접 잠그지 못한다**(vacuous assertion). 에이전트 증명: L173/L179의 owner_id 조건을 `false`로 바꿔도
깨지는 건 L59 힌트 텍스트뿐, L58 disabled 단정은 통과. 백엔드 403이 최종 방어라 치명적이지 않지만,
owner_id disabled-prop을 reason이 채워진 상태에서 직접 단정하는 보강 셀이 있으면 프론트 UX 경계가 단단해진다.

## Verdict

**합격.** /admin guard·C-6 공백 해소·12자 양방향 경계·무소유 승격 UX 차단·lazy loading이 코드·테스트에서
일관되고, 뮤테이션 4개 가드가 전부 작동하며, 플레이크가 없다. D8-5 트랙이 이것으로 종료된다. Hardening 1건은
백엔드 403이 최종 방어라 비차단이나, vacuous 단정은 보강 가치가 있다.

## Outstanding items

- Hardening(무소유 disabled 직접 단정) — 작업 AI 판단에 맡김.
- D8-5 종료. 남은 잔여: 영구 삭제 UI(작업 AI가 별도 잔여로 남김).
- 본 검증은 기록만 작성 후 커밋.

## Reproduction

```bash
cd frontend && npm run test    # 234 passed / 17 files
cd frontend && npm run build   # exit 0, AdminConsole lazy chunk 분리
python3 -m pytest -q           # 1900 passed (D8-5d 백엔드 무변)

# 프론트 뮤테이션(Edit → npm run test → 원복, 커밋 금지)
# 1. App.tsx AdminRoute 의 if (!user.is_admin) → if (false) → App.test.tsx:285 실패
# 2. AuthGate.tsx newPassword.length < 12 → < 1 → App.test.tsx:253 실패 (under-strict)
# 3. AuthGate.tsx !== confirmation → false → App.test.tsx:259 실패 (over-strict)
# 4. AuthGate.tsx 409 분기 → false && → App.test.tsx:247 실패 (C-6 공백 해소 잠금)
# 5. AdminConsole.tsx L173/L179 owner_id === null → false → AdminConsole.test.tsx:59 (힌트)만 실패,
#    L58 disabled 단정은 reason 빈 문자열이라 통과(vacuous)
```
