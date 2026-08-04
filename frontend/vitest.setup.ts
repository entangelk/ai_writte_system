import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";
import { seedMemberQuota } from "./src/quota/useMemberQuota";

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
});
