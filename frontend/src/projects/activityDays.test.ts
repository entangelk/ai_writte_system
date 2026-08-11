import { describe, expect, it } from "vitest";
import { groupActivityByDay } from "./activityDays";

/** 로컬 시간대로 `Date` 를 만든다 — 문자열 파싱이 UTC 로 새는 것을 피한다. */
function localAt(
  year: number, month: number, day: number, hour = 12, minute = 0,
): string {
  return new Date(year, month - 1, day, hour, minute).toISOString();
}

const NOW = new Date(2026, 7, 11, 15, 0); // 2026-08-11 15:00 로컬

describe("groupActivityByDay (Phase 10 Slice 10.2)", () => {
  it("names today and yesterday instead of printing their dates", () => {
    const groups = groupActivityByDay([
      { at: localAt(2026, 8, 11, 9) },
      { at: localAt(2026, 8, 10, 22) },
    ], NOW);

    expect(groups.map((g) => g.label)).toEqual(["오늘", "어제"]);
  });

  it("dates older days, and adds the year only when it differs", () => {
    const groups = groupActivityByDay([
      { at: localAt(2026, 8, 3) },
      { at: localAt(2025, 12, 31) },
    ], NOW);

    expect(groups.map((g) => g.label)).toEqual(["8월 3일", "2025년 12월 31일"]);
  });

  it("keeps the order the server gave and never re-sorts", () => {
    /**
     * ★ 정렬의 정본은 저장소다(`log_mongo.py` 가 `at` DESC). 여기서 한 번 더
     * 정렬하면 순서를 정하는 곳이 둘이 된다. 그래서 **일부러 뒤섞인 입력**을 주고
     * 그대로 나오는지 본다 — "정렬해 주는" 친절이 들어오면 이 셀이 문다.
     */
    const events = [
      { at: localAt(2026, 8, 11, 9), id: "a" },
      { at: localAt(2026, 8, 3), id: "b" },
      { at: localAt(2026, 8, 11, 8), id: "c" }, // 같은 날인데 떨어져 있다
    ];

    const groups = groupActivityByDay(events, NOW);

    expect(groups.map((g) => g.events.map((e) => e.id))).toEqual([
      ["a"], ["b"], ["c"],
    ]);
    expect(groups.map((g) => g.label)).toEqual(["오늘", "8월 3일", "오늘"]);
  });

  it("folds only adjacent events of the same day", () => {
    const groups = groupActivityByDay([
      { at: localAt(2026, 8, 11, 9), id: "a" },
      { at: localAt(2026, 8, 11, 8), id: "b" },
      { at: localAt(2026, 8, 10, 23), id: "c" },
    ], NOW);

    expect(groups).toHaveLength(2);
    expect(groups[0].events.map((e) => e.id)).toEqual(["a", "b"]);
    expect(groups[1].events.map((e) => e.id)).toEqual(["c"]);
  });

  it("uses the local calendar day, not UTC", () => {
    /**
     * ★ 각 행이 `toLocaleString("ko-KR")` 로 **로컬 시각**을 찍는다. 머리글을
     * UTC 로 계산하면 *"오늘"* 아래에 어제 시각이 적힌 행이 앉는다 — 머리글은
     * 옆에 적힌 시각과 **같은 날**을 말해야 한다. 로컬 자정 직후 1분을 준다:
     * UTC 로 바꾸면(KST 기준) 전날로 넘어가는 시각이다.
     */
    const justAfterLocalMidnight = localAt(2026, 8, 11, 0, 1);

    const groups = groupActivityByDay([{ at: justAfterLocalMidnight }], NOW);

    expect(groups[0].label).toBe("오늘");
  });

  it("keeps rows it cannot date instead of dropping them", () => {
    // 행이 조용히 사라지는 것이 잘못된 머리글보다 나쁘다.
    const groups = groupActivityByDay([{ at: "not-a-date" }], NOW);

    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("날짜를 읽을 수 없음");
    expect(groups[0].events).toHaveLength(1);
  });

  it("returns nothing for an empty log", () => {
    expect(groupActivityByDay([], NOW)).toEqual([]);
  });
});
