import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";
import { seedMemberQuota } from "./src/quota/useMemberQuota";
import { seedWithdrawal } from "./src/me/withdrawal";

// Slice 8.4 (W5=B): 잔여 표시는 **보조 조회**다. 화면 테스트는 유료 요청의 응답
// 시퀀스를 순서대로 세는데, 그 사이에 `GET /me/quota` 가 끼면 세던 것이 통째로
// 어긋난다(`seedWritingBudgetCache` 가 예산 조회에 대해 푼 것과 같은 문제).
// 그래서 기본은 시드된 오프라인 값이고, 갱신 동작 자체를 재는 셀만
// `resetMemberQuota()` 로 실제 조회를 켠다.
beforeEach(() => {
  seedMemberQuota({
    remaining: 12,
    unlimited: false,
    status: "active",
    daily: {
      limit: 20, used: 8, remaining: 12,
      resets_at: "2026-08-04T15:00:00Z",
    },
    weekly: {
      limit: 100, used: 30, remaining: 70,
      resets_at: "2026-08-08T15:00:00Z",
    },
  });
  // 계정 탈퇴 Slice 4(D1=ⓐ): 유예 배너가 **앱 셸**에 있으므로 `GET /me/withdrawal`
  // 이 모든 화면 마운트에 끼어든다 — 위 quota 와 정확히 같은 문제다. 기본값은
  // **탈퇴 중 아님**(두 필드 모두 null)이라 배너가 안 그려지고 조회도 안 나간다.
  // 탈퇴 축 셀만 자기 값을 시드하거나 `resetWithdrawal()` 로 실제 조회를 켠다.
  seedWithdrawal({ withdrawal_requested_at: null, purge_due_at: null });
});
