import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityTimelinePage } from "./ActivityTimelinePage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubEvents(events: unknown[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "",
    json: async () => ({ events }),
  }));
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/projects/p1/activity"]}>
      <Routes>
        <Route path="/projects/:projectId/activity" element={<ActivityTimelinePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const SAVED = {
  id: "e1", actor_user_id: "u1", action: "draft_version_saved",
  target_type: "draft_version", target_id: "v1",
  at: "2026-08-10T01:00:00Z", before: null, after: "3",
};

it("labels each action in Korean instead of the raw literal", async () => {
  stubEvents([SAVED]);
  renderPage();

  expect(await screen.findByText("원고 저장")).toBeInTheDocument();
  expect(screen.queryByText("draft_version_saved")).not.toBeInTheDocument();
});

it("says the 100-item ceiling out loud", async () => {
  // S2=ⓐ: 응답은 최신 100건 고정인데 그 사실이 응답 어디에도 없다. 화면이 말하지
  // 않으면 사용자는 이것을 **전부**로 읽는다 — purge UI 문구가 부분적으로 거짓이 되어
  // 값을 치른 것과 같은 형태(8.2c N5)라 문구를 회귀로 잠근다.
  stubEvents([SAVED]);
  renderPage();

  expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
});

it("shows the before → after label pair when a value changed", async () => {
  stubEvents([{
    ...SAVED, id: "e2", action: "draft_renamed", target_type: "draft",
    target_id: "d1", before: "1장 초고", after: "1장 — 재회",
  }]);
  renderPage();

  expect(await screen.findByText(/1장 초고 → 1장 — 재회/)).toBeInTheDocument();
});

it("links only the target types that have a screen", async () => {
  // S6: draft 는 편집 화면으로 간다. draft_version 은 payload 에 draft_id 가 없어
  // route 를 만들 수 없으므로 링크하지 않는다(브리프 F7) — 그 비대칭이 의도임을 잠근다.
  stubEvents([
    { ...SAVED, id: "e3", action: "draft_created", target_type: "draft", target_id: "d1" },
    SAVED,
  ]);
  renderPage();

  const links = await screen.findAllByRole("link", { name: "원고 열기" });
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAttribute("href", "/projects/p1/drafts/d1");
});

it("does not show an actor column", async () => {
  // S3=ⓑ over-strict: 행위자가 항상 본인이라 열을 안 만든다. 선례(access-log)를 따라
  // 원시 id 를 렌더하는 회귀를 막는다 — 24자 hex 가 줄마다 뜬다.
  stubEvents([SAVED]);
  renderPage();

  await screen.findByText("원고 저장");
  expect(screen.queryByText(/u1/)).not.toBeInTheDocument();
});

it("tells the owner when nothing has been recorded yet", async () => {
  stubEvents([]);
  renderPage();

  expect(await screen.findByText("아직 기록된 활동이 없습니다.")).toBeInTheDocument();
});

it("surfaces a failed load instead of an empty page", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, status: 403, statusText: "Forbidden",
    json: async () => ({ detail: "not the owner" }),
  }));
  renderPage();

  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText("아직 기록된 활동이 없습니다.")).not.toBeInTheDocument();
});

describe("날짜 그룹 (Phase 10 Slice 10.2, D3=ⓓ)", () => {
  /**
   * 그전까지 최대 100건이 **한 덩어리로 주르륵** 쌓였다(오너 육안 확인 지적).
   * 그룹핑 규칙 자체는 `activityDays.test.ts` 가 잰다 — 여기는 **화면이 그것을
   * 실제로 쓰는가**를 본다(모듈은 멀쩡한데 화면이 안 부르는 상태가 가능하다).
   */

  /**
   * ★ 이 셀들은 **시계에 의존하지 않는다.** 화면은 `groupActivityByDay(events)` 를
   * 기본 `now`(=실제 지금)로 부르므로 "오늘"·"어제" 를 여기서 재려면 시계를 고정해야
   * 하는데, `vi.useFakeTimers()` 는 `findBy*` 의 `waitFor` 를 멈춰 세워 전부 타임아웃이
   * 된다(초판이 그랬다). **연도가 다른 날짜**를 쓰면 라벨이 무슨 날에 돌려도 같다.
   * "오늘"·"어제" 자체는 `activityDays.test.ts` 가 `now` 를 주입해 결정적으로 잰다 —
   * 여기가 재는 것은 **화면이 그 모듈을 실제로 쓰는가**다.
   */
  const DAY_ONE = {
    ...SAVED, id: "d1", at: new Date(2024, 2, 5, 9, 0).toISOString(),
  };
  const DAY_ONE_LATER = {
    ...SAVED, id: "d1b", action: "draft_renamed", target_type: "draft",
    target_id: "dr1", at: new Date(2024, 2, 5, 8, 0).toISOString(),
  };
  const DAY_TWO = {
    ...SAVED, id: "d2", action: "project_renamed", target_type: "project",
    target_id: "p1", at: new Date(2024, 1, 27, 9, 0).toISOString(),
  };

  it("puts a dated heading above each day's rows", async () => {
    stubEvents([DAY_ONE, DAY_ONE_LATER, DAY_TWO]);
    renderPage();

    // 같은 날 둘은 머리글 하나 아래로 접힌다 — 머리글이 행마다 반복되지 않는다.
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(
      ["2024년 3월 5일", "2024년 2월 27일"]);
  });

  it("drops the date from each row now that the heading carries it", async () => {
    /**
     * over-strict 방향: 머리글을 얹고도 행이 전체 날짜를 그대로 찍으면 같은 정보가
     * 두 번 나온다 — 그룹핑을 한 이유가 사라진다. 행에는 **시각만** 남아야 한다.
     */
    stubEvents([DAY_ONE]);
    renderPage();

    await screen.findByRole("heading", { level: 2, name: "2024년 3월 5일" });
    const row = screen.getByText("원고 저장").closest("li");
    expect(row?.textContent).not.toContain("2024");
    expect(row?.textContent).not.toContain("3월 5일");
    expect(row?.textContent).toMatch(/\d{2}:\d{2}/);
  });

  it("still says the ceiling — grouping did not raise it", async () => {
    // D3=ⓓ 는 커서를 **유예**한 것이지 상한을 없앤 것이 아니다. 문구가 사라지면
    // 화면이 "더 있다"고 암시하게 된다.
    stubEvents([DAY_ONE]);
    renderPage();

    expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
  });
});
