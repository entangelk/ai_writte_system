# 계정 탈퇴 Slice 5 — 조건 폐쇄 승격 재검

**합격** — 발행 검증(같은 날 이전 세션)의 조건 셋 **B1·B2·B3**이 폐쇄 커밋 **`dfc455a`**(docs+test · SoT v1.8.61)로 닫혔고, 이 재검이 변이 재적용으로 그 폐쇄를 확증했다. 선행 기록 [`account_withdrawal_slice5_promotion.md`](account_withdrawal_slice5_promotion.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존).

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 구현(`e169e96`)·발행 검증·조건 폐쇄(`dfc455a`) 어느 쪽도 아니다
- **검증 트리**: HEAD `0769cc9`(Slice 4b 폐쇄 기록 — 본 슬라이스와 무관한 문서 커밋). **검증 중 다른 AI 가 미커밋 작업으로 같은 트리를 쓰고 있었다**(시작 시점 1파일 → 기록 작성 시점 6파일: `CHANGELOG.md`·`HANDOFF.md`·`README.md`·`daily_logs/2026-09-12/work_log.md`·`plans/activity-log-replay-and-partial-decisions.md`·`docs/system-contract-sot.md`) — 그 파일들은 한 번도 건드리지 않았고, 변이 원복은 **내 변이 대상 파일만 개별 경로로** `git checkout -- <절대경로>` + 백업과 `cmp` 바이트 대조로 했다(변이 시작 전 게이트에서 대상 파일의 diff 는 0이었다).
- **환경**: WSL2 · `python3 -m pytest`(pytest-subtests · test-mongo healthy) · 프런트는 `frontend/` 안에서 `npx vitest`(단일 파일)

## 변이 재적용 — 4종 전부 기명 셀로 재실패

| 변이 | 적용한 diff(실제 텍스트) | 발행 검증 시점 | 실측(폐쇄 후 현행 트리) |
|---|---|---|---|
| **MX-D** (under) | `service-policy-contract.md:85` §6 표의 ` \| 계정 탈퇴 유예 기간 \| 30일 \| \`auth/users.py::WITHDRAWAL_GRACE_PERIOD\` \| ` 행 1줄 삭제 | **10/70 초록(무셀)** | **1 실패** `test_the_document_exists_and_carries_pinned_rows`(H3 하한 `>= 14`) — `1 failed, 10 passed, 68 subtests` |
| **MX-I** (under) | `legal/README.md:59` ` \| **유예 중에는 쓰기와 유료 경로가 막힌다** \| **미기재** \| **미기재** \| ` 행 1줄 삭제 | **10/70 초록(무셀)** | **1 실패** `test_the_undisclosed_restriction_keeps_its_row_while_code_enforces_it`(H2 양방향 셀) — `1 failed, 10 passed, 70 subtests` |
| **B1-ⓐ 방향** (under·방향 전환) | `auth/users.py` `cancel_withdrawal` 의 `withdrawal_requested_at` 검사 뒤에 `if stored.purge_started_at is not None: raise WithdrawalNotRequested("purge has already started")` 삽입 — D5 경계 시행의 뼈대(ⓐ)를 강제로 깔면? | (발행 검증엔 없던 축 — 폐쇄가 특성 셀로 닫은 자리) | **1 실패** `WithdrawalCancelAfterPurgeClaimTest::test_cancelling_still_succeeds_after_the_purge_was_claimed` — `1 failed, 69 passed`. **ⓐ 가 선택되면 셀과 §6 문장이 함께 뒤집힌다**는 폐쇄 설계의 실증 |
| **MU-A** (under) | `auth/users.py:109` `WITHDRAWAL_GRACE_PERIOD = timedelta(days=30)` → `timedelta(days=60)` | **7 실패** | **7 실패, 셀 짝까지 전건 일치** — `SUBFAILED(axis='계정 탈퇴 유예 기간')` + `SUBFAILED(document='terms-of-service-draft.md')` + `SUBFAILED(document='privacy-policy-draft.md')` + `FAILED WithdrawalGracePeriodLiteralTest` + `FAILED PurgeDueBoundaryTest` 3셀. `7 failed, 77 passed, 67 subtests` |

## 폐쇄 ↔ 처방 대조

- **B1(ⓑ 채택)**: 검증이 제시한 갈래 ⓑ 그대로 — §6 문장을 *"취소는 탈퇴 스탬프가 있는 동안 된다"* 로 고치고 D5 와의 거리를 문장 안에 명시, 특성 셀이 *"문장과 코드가 같은 것을 말하는 상태"* 를 잠근다. 코드 변경(ⓐ)은 오너 결정 브리프로 이관됐다(위 B1-ⓐ 변이로 셀이 뒤집히는 것이 그 표식의 실증). **경계 시행 여부는 여전히 오너 결정 대기** — 승격은 그 대기를 닫는 것이 아니라 *문장·셀·코드가 지금 같은 말을 하는 상태*를 확증하는 것이다.
- **B2**: 방침 머리말의 거짓 문장(*"제3조 안내 상자는 아직 기능이 제공되지 않습니다"*)이 **양쪽 사본에서 사라졌다** — `grep` 0건(재확인) · `cmp` 바이트 동일 ×2(terms·privacy) · `npx vitest run src/legal/legalSource.test.ts` **4 passed EXIT=0**.
- **B3**: `legal/README.md` §8 절 머리가 *"열린 시행 전제는 이제 0 이다"* 로 표와 같은 말을 한다(자기모순 해소 — 낱독 확인). 남은 두 행은 *"시행 전제가 아니라 코드가 따로 할 일이 없던 것"* 임을 적고 §8 비울지를 오너 판단으로 남겼다.
- **하드닝 다섯 중 둘(H2·H3)은 위 변이로 재확인**했다. H4(§6 잔존 셋 — `사용량 기록 · 관리자 열람·감사 기록 · 사용자명 한 값`)와 H5(HANDOFF 함정 등재 — *"값 불일치 vs 앵커 실종"* 두 진단)는 낱독으로 존재 확인. H1(재로그인 셀)은 이 재검에서 따로 돌리지 않았다(폐쇄 보고 기술).

## 기준선(변이 전 초록)

- `tests/test_service_policy_contract.py` 단독: **11 passed / 70 subtests**(폐쇄 보고의 수치와 일치) · `tests/test_service_policy_contract.py + test_auth_users.py + test_admin_account_reconcile.py + test_admin_audit.py` 묶음: **102 passed / 73 subtests EXIT=0**.

## Verdict

**합격** — 조건 B1·B2·B3 모두 폐쇄됐고 변이 재적용 네 종이 기록 그대로 문다(둘은 폐쇄로 *무셀→재실패*로 바뀐 자리, 하나는 폐쇄가 새로 세운 특성 셀, 하나는 원본 가드의 셀 짝 보존). 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — 조건 셋: **B1** §6 *"취소는 파기가 시작되기 전까지다"* 가 코드에 없다(무셀 + 미시행) · **B2** 방침 머리말의 거짓 문장이 회원 화면에 있다 · **B3** `legal/README.md` §8 절이 자기 표와 모순한다.

## Outstanding items

- **오너 결정 둘은 그대로 열려 있다**(승격과 무관): 파기 청구 뒤 취소의 얼굴(브리프 [`slice5-withdrawal-cancel-after-purge-claim-decisions.md`](../../plans/slice5-withdrawal-cancel-after-purge-claim-decisions.md)) · 유예 중 쓰기 차단 고지 문언(약관·방침에 넣을지 — `미기재` 행이 그 자리를 표시한다).
- §8 에 남은 두 행을 §1~§7 로 올릴지도 오너 판단(폐쇄 보고 그대로).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git status --short                          # 변이 대상 파일은 diff 0이어야 한다
python3 -m pytest tests/test_service_policy_contract.py -q   # 11 passed / 70 subtests
# MX-D: service-policy-contract.md 의 §6 유예 기간 행 삭제 → 위 파일 1 failed(H3 하한 셀)
# MX-I: legal/README.md 의 미기재 행 삭제 → 1 failed(H2 셀)
# B1-ⓐ: auth/users.py cancel_withdrawal 에 purge_started_at 거부 삽입
#        → python3 -m pytest tests/test_auth_users.py -q  → 1 failed(특성 셀)
# MU-A : WITHDRAWAL_GRACE_PERIOD 30→60일 → 7 failed(위 표의 셋)
# 매 변이: git checkout -- <절대경로> 원복 + 백업과 cmp 바이트 대조
cd frontend && npx vitest run src/legal/legalSource.test.ts  # 4 passed(B2)
cmp ../docs/legal/terms-of-service-draft.md src/legal/terms-of-service.md
cmp ../docs/legal/privacy-policy-draft.md  src/legal/privacy-policy.md
```
