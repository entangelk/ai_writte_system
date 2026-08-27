import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PersonalHubPage } from "./PersonalHubPage";
import { resetMemberQuota, seedMemberQuota } from "../quota/useMemberQuota";

beforeEach(() => {
  seedMemberQuota({
    remaining: 7, unlimited: false, status: "active",
    daily: { limit: 20, used: 13, remaining: 7, resets_at: null },
    weekly: { limit: 100, used: 41, remaining: 59, resets_at: null },
  } as never);
});

afterEach(() => {
  resetMemberQuota();
  vi.unstubAllGlobals();
});

/** `/projects` 와 `/me/activity` 두 응답을 순서대로 준다. */
function stub(projects: unknown[], events: unknown[]) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const body = String(url).includes("/me/activity")
      ? { events }
      : { projects };
    return Promise.resolve({
      ok: true, status: 200, statusText: "", json: async () => body,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderHub() {
  render(
    <MemoryRouter initialEntries={["/me"]}>
      <Routes>
        <Route path="/me" element={<PersonalHubPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const PROJECTS = [
  { id: "p1", name: "겨울 이야기", archived: false, owner_id: "u1" },
  { id: "p2", name: "여름 습작", archived: false, owner_id: "u1" },
];

const EVENTS = [
  {
    id: "e1", project_id: "p2", actor_user_id: "u1", action: "draft_created",
    target_type: "draft", target_id: "d9",
    at: "2026-08-10T02:00:00Z", before: null, after: "1장",
  },
  {
    id: "e2", project_id: "p1", actor_user_id: "u1", action: "project_renamed",
    target_type: "project", target_id: "p1",
    at: "2026-08-10T01:00:00Z", before: "옛 이름", after: "겨울 이야기",
  },
];

it("gives the remaining request budget a home", async () => {
  // 이 페이지가 생긴 첫 이유다 — `useMemberQuota` 가 화면 없이 떠돌던 것을 받는다.
  stub(PROJECTS, EVENTS);
  renderHub();

  const usage = await screen.findByRole("heading", { name: "이번 주기 사용량" });
  const section = usage.closest("section") as HTMLElement;
  expect(within(section).getByText("7회")).toBeInTheDocument();
  expect(within(section).getByText("13 / 20")).toBeInTheDocument();
  expect(within(section).getByText("41 / 100")).toBeInTheDocument();
});

it("merges activity across projects and names each project", async () => {
  // ★ 응답은 `project_id` 만 들고 온다. 이름을 붙이지 않으면 화면에 24자 hex 가
  // 줄마다 뜬다 — 9.1 에서 행위자 열을 만들지 않기로 한 것과 같은 판단이다.
  stub(PROJECTS, EVENTS);
  renderHub();

  await screen.findByText("원고 생성");
  // 프로젝트 이름은 목록에도 나오므로 **활동 섹션 안에서** 확인한다.
  // 활동 섹션은 접히는 <details> 다(오너 2026-08-27) — 100건이 한 번에 펼쳐져
  // 화면을 다 먹던 것을 날짜 그룹 단위로 접었다. 그래서 경계는 section 이 아니다.
  const recent = (await screen.findByRole("heading", { name: "최근 활동" }))
    .closest("details") as HTMLElement;
  expect(within(recent).getByText(/여름 습작/)).toBeInTheDocument();
  expect(within(recent).getByText("프로젝트 이름 변경")).toBeInTheDocument();
  expect(within(recent).getByText(/옛 이름 → 겨울 이야기/)).toBeInTheDocument();
});

it("asks the server once instead of fanning out per project", async () => {
  // P1=ⓐ 의 관측 가능한 성질. fan-out(ⓑ)으로 되돌아가면 요청 수가 프로젝트 수에
  // 비례해 늘고, 이 셀이 그 회귀를 잡는다.
  const fetchMock = stub(PROJECTS, EVENTS);
  renderHub();

  await screen.findByText("원고 생성");
  const urls = fetchMock.mock.calls.map(([url]) => String(url));
  expect(urls).toContain("/api/me/activity");
  expect(urls.filter((url) => url.includes("/activity"))).toHaveLength(1);
});

it("never puts a project id in the activity request", async () => {
  // S-3 — 경로가 project id 를 받지 않는 것이 IDOR 표면이 없다는 뜻이다.
  const fetchMock = stub(PROJECTS, EVENTS);
  renderHub();

  await screen.findByText("원고 생성");
  const activityCall = fetchMock.mock.calls
    .map(([url]) => String(url))
    .find((url) => url.includes("/me/activity")) as string;
  expect(activityCall).toBe("/api/me/activity");
  expect(activityCall).not.toContain("p1");
  expect(activityCall).not.toContain("p2");
});

it("says the ceiling out loud", async () => {
  stub(PROJECTS, EVENTS);
  renderHub();

  expect(
    await screen.findByText(/내 프로젝트 전체에서 최근 100건까지 보여줍니다/),
  ).toBeInTheDocument();
});

it("branches out to each project without leaving the hub empty-handed", async () => {
  // P3=ⓐ — 관측은 **진입만**이다(집계를 여기 그리지 않는다).
  stub(PROJECTS, EVENTS);
  renderHub();

  const project = await screen.findByRole("link", { name: "겨울 이야기" });
  expect(project).toHaveAttribute("href", "/projects/p1");
  const links = screen.getAllByRole("link", { name: "관측" });
  expect(links[0]).toHaveAttribute("href", "/projects/p1/observability");
});

it("does not show an actor column", async () => {
  // 9.1 S3 과 같은 이유 — 행위자가 항상 보는 사람이다.
  stub(PROJECTS, EVENTS);
  renderHub();

  await screen.findByText("원고 생성");
  expect(screen.queryByText(/u1/)).not.toBeInTheDocument();
});

it("tells a brand-new member there is nothing yet", async () => {
  stub([], []);
  renderHub();

  expect(await screen.findByText("아직 프로젝트가 없습니다.")).toBeInTheDocument();
  expect(screen.getByText("아직 기록된 활동이 없습니다.")).toBeInTheDocument();
});

it("surfaces a failed load instead of an empty page", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, status: 503, statusText: "Service Unavailable",
    json: async () => ({ detail: "storage down" }),
  }));
  renderHub();

  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

describe("날짜 그룹 (Phase 10 Slice 10.2, D3=ⓓ)", () => {
  /**
   * 규칙은 `activityDays.test.ts`, 여기는 **허브가 그 모듈을 쓰는가**. 연도가 다른
   * 날짜를 써서 시계에 의존하지 않는다(사유는 `ActivityTimelinePage.test.tsx`).
   *
   * ★ 통합 화면이라 행은 날짜가 빠져도 **어느 프로젝트인지**는 계속 말해야 한다 —
   * 그것이 project-scoped 응답과 이 tier 의 유일한 차이다(9.2 P1).
   */
  it("groups by day while each row still names its project", async () => {
    stub(PROJECTS, [
      { ...EVENTS[0], id: "g1", at: new Date(2024, 2, 5, 9, 0).toISOString() },
      { ...EVENTS[1], id: "g2", at: new Date(2024, 1, 27, 9, 0).toISOString() },
    ]);
    renderHub();

    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(
      ["2024년 3월 5일", "2024년 2월 27일"]);
    // 프로젝트 이름은 그대로 — 목록 링크와 활동 행 양쪽에 나온다.
    expect(screen.getAllByText(/여름 습작/).length).toBeGreaterThanOrEqual(2);
  });
});

describe("접기 · 목록 스타일 (오너 2026-08-27 dogfood)", () => {
  /**
   * under-strict: 활동 그룹을 다시 전부 펼쳐 두면(`open` 을 모든 그룹에) 첫 그룹
   * 외의 `open` 이 생겨 재실패한다 — 100건이 화면을 다 먹던 그 상태다.
   * over-strict: 상한을 줄여 "접는" 과대교정도 실패한다. 접는 것은 화면이지
   * 데이터가 아니다 — 100건 문구와 렌더된 행 수를 함께 잠근다.
   */
  it("folds each activity day and opens only the most recent", async () => {
    stub(PROJECTS, [
      { ...EVENTS[0], id: "g1", at: new Date(2024, 2, 5, 9, 0).toISOString() },
      { ...EVENTS[1], id: "g2", at: new Date(2024, 1, 27, 9, 0).toISOString() },
    ]);
    renderHub();

    await screen.findByText("2024년 3월 5일");
    const days = document.querySelectorAll("details.activity-day");
    expect(days).toHaveLength(2);
    expect((days[0] as HTMLDetailsElement).open).toBe(true);
    expect((days[1] as HTMLDetailsElement).open).toBe(false);

    // 접는 것은 화면일 뿐 — 두 그룹의 행은 모두 렌더되어 있다.
    expect(screen.getByText("원고 생성")).toBeInTheDocument();
    expect(screen.getByText("프로젝트 이름 변경")).toBeInTheDocument();
    expect(screen.getByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
  });

  it("gives my projects the same row treatment as the project list", async () => {
    // 종전에는 맨 하이퍼링크였다 — 같은 것(프로젝트 목록)은 같게 보여야 한다.
    stub(PROJECTS, EVENTS);
    renderHub();

    const link = await screen.findByRole("link", { name: "겨울 이야기" });
    expect(link).toHaveClass("resource-link");
    expect(link.closest("li")).toHaveClass("resource-row");
    expect(screen.getByRole("list", { name: "내 프로젝트 목록" }))
      .toHaveClass("resource-list");
  });
});
