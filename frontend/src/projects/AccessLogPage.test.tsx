import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { AccessLogPage } from "./AccessLogPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("shows the project owner which administrator accessed what and why", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "",
    json: async () => ({ entries: [{
      grant_id: "g1", admin_user_id: "admin-1", method: "GET",
      path: "/projects/p1/drafts", at: "2026-08-02T00:10:00Z", reason: "지원 요청 확인",
    }] }),
  }));

  render(
    <MemoryRouter initialEntries={["/projects/p1/access-log"]}>
      <Routes>
        <Route path="/projects/:projectId/access-log" element={<AccessLogPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: "관리자 접근 이력" })).toBeInTheDocument();
  expect(screen.getByText("GET /projects/p1/drafts")).toBeInTheDocument();
  expect(screen.getByText(/지원 요청 확인/)).toBeInTheDocument();
  expect(screen.getByText(/admin-1/)).toBeInTheDocument();
});
