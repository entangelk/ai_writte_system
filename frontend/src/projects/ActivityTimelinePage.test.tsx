import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
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
