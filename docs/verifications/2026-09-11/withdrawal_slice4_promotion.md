# 계정 탈퇴 Slice 4(화면) — 조건 폐쇄 승격 재검

**합격** — 세션 56 검증의 조건 둘(B1·B2)이 세션 57(`b52633d`, SoT v1.8.55)에서 닫혔고, 이 재검이 변이 재적용으로 그 폐쇄를 확증했다. 선행 기록 [`withdrawal_slice4_screen.md`](withdrawal_slice4_screen.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존 — 2026-08-10 선례).

- **일시**: 2026-09-11 · **검증자**: 세션 59 — 구현(55)·검증(56)·폐쇄(57) 어느 쪽도 아니다
- **대상**: 폐쇄 커밋 `b52633d`(프로덕션 코드 무변, 셀 11→13) — 검증 트리 HEAD `897aa72`
- **방법**: 프리플라이트 무출력 게이트 → 변이 → 초점(`src/me/withdrawal.test.tsx`, 13셀) → 절대경로 원복 → 무출력 확인

## 변이 재적용 — 6종 전부 세션 57 기록과 일치

| 변이 | diff | 세션 57 기록 | 실측 |
|---|---|---|---|
| MV-2b (under) | `AuthGate` 에서 `<WithdrawalBanner />` 통째 제거 | 1실패 | **1실패** `hangs the banner off the real app shell` — 종전(세션 56) 3파일 52셀 전건 초록이던 자리 |
| MV-2 (under) | `{location.pathname === "/me" && <WithdrawalBanner />}` | 1실패 | **1실패**(같은 셀) — ★ 첫 측정은 3실패였으나 **2는 H1 시계 플레이크**("남은 기간 4일")로, 재측 정확히 1(재발 관측은 랜딩 ② 기록 H4 참조) |
| MV-2d (over/등가) | 배너를 `<header>` 위로 이동(셸 안 줄 위치만 변경) | 13/13 초록 | **13/13 초록** — 줄 위치가 아니라 *셸이 거는가* 를 잰다는 설계의 실증 |
| MV-7 (under) | 409 재조회를 로컬 `null` 합성으로 치환(양쪽) | 2실패 | **2실패**(409 수단 셀 + 재조회 실패 셀) — 종전 11/11 초록 |
| MV-11 (under) | 재조회 실패 분기(try/catch) 제거 | 1실패 | **1실패** `says the state could not be re-read…` |
| MV-12 (over) | 재조회 실패 catch 에서 상태를 `null` 로 합성 | 1실패 | **1실패**(같은 셀) |

## 폐쇄 ↔ 처방 대조

- **B1**: 처방("진짜 `AuthGate` 를 렌더하는 셀 하나") 그대로 — 실측으로 섰다는 전제(화면 렌더 단정)부터 세우고 배너를 봤으며, 남은 일수를 일부러 안 재 시계 플래이크(H1)를 장착 셀로 끌어들이지 않았다. **테스트가 프로덕션 배선을 복제하면 배선 자체가 무잠금이 된다**는 파일 머리말의 일반형 문장이 이 폐쇄의 교훈으로 남는다.
- **B2**: 처방(409 셀에 fetch 호출 단정)을 넘어 **재조회 실패 경로 셀**까지 덮었다 — 검증이 무테스트로 지목했던 바로 그 경로다. 수단 단정(호출 2회·GET)이 로컬 합성(MV-7)과 결과가 같은 함정을 정확히 가른다.

## Verdict

**합격** — 조건 B1·B2 모두 폐쇄됐고 변이 재적용 여섯 종이 기록 그대로 문다. 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — B1(진짜 앱 셸을 세우는 배너 장착 셀)·B2(취소 409 재조회의 fetch 단정)를 닫아야 합격이다.

## Outstanding items

- 없음(이 축은 닫혔다). Slice 4b(관리자 잔여 정리 — 브리프 선행)·Slice 5(문서 승격)는 별개 슬라이스.
- H1 플레이크(시계 의존 픽스처)는 등재 상태 그대로 — 이 재검 중 2회째 관측(랜딩 ② 기록 H4).

## Reproduction

```bash
cd <repo>/frontend && git status --short   # 무출력
# MV-2b: src/auth/AuthGate.tsx 의 <WithdrawalBanner /> 줄 제거
npx vitest run src/me/withdrawal.test.tsx  # 1 failed(hangs the banner off the real app shell)
git checkout -- src/auth/AuthGate.tsx      # 절대경로로
# MV-7: src/me/withdrawal.tsx 의 apply(await getMyWithdrawal()) 두 곳을
#       apply({ withdrawal_requested_at: null, purge_due_at: null }) 로
npx vitest run src/me/withdrawal.test.tsx  # 2 failed
git checkout -- src/me/withdrawal.tsx
```
