import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectSettingsPage } from "./ProjectSettingsPage";

/** 탭이 무엇을 청하든 답한다 — 이 파일이 재는 것은 셸이지 탭 내용이 아니다. */
function stubFetch() {
  const fetchMock = vi.fn(async (url: string) => {
    const body = url.endsWith("/p1")
      ? { id: "p1", name: "겨울 이야기", archived: false }
      : url.includes("/brief")
        ? { brief: null }
        : url.includes("/memory")
          ? { memory: [] }
          : url.includes("/review")
            ? { project_id: "p1", items: [], gate_findings: [] }
            : url.includes("/activity")
              ? { events: [] }
              : { drafts: [] };
    return { ok: true, status: 200, statusText: "", json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderSettings(path = "/projects/p1/settings") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId/settings" element={<ProjectSettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * 프로젝트 설정 셸 (오너 2026-08-27).
 *
 * under-strict: 세 화면 중 하나를 다시 작업 공간 첫 화면으로 빼면 탭이 사라져
 * 재실패한다 — *"너무 어지럽다"* 던 그 상태다.
 * over-strict: 검토함까지 여기로 끌어오는 과대교정도 실패한다. 검토함은 집필
 * 중 수시로 드나드는 작업 흐름이라 설정이 아니다(오너 결정).
 */
describe("ProjectSettingsPage", () => {
  it("gathers the three occasional screens under one tab bar", async () => {
    stubFetch();
    renderSettings();

    expect(await screen.findByRole("heading", { name: "겨울 이야기" }))
      .toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["작품 정보·개요", "원고 내보내기", "활동 타임라인"]);
    expect(screen.queryByRole("tab", { name: "검토함" })).toBeNull();
    expect(screen.getByRole("link", { name: "← 원고 작업 공간" }))
      .toHaveAttribute("href", "/projects/p1");
  });

  it("opens the brief tab by default and switches on click", async () => {
    stubFetch();
    renderSettings();

    await screen.findByRole("heading", { name: "작품 시작 정보" });

    await userEvent.click(screen.getByRole("tab", { name: "원고 내보내기" }));
    expect(await screen.findByRole("heading", { name: "원고 내보내기" }))
      .toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "작품 시작 정보" })).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: "활동 타임라인" }));
    expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
  });

  it("honours ?tab= so a shared link opens where it says", async () => {
    // 탭 상태가 컴포넌트 안에만 있으면 새로고침·공유 링크가 첫 탭으로 되돌아간다.
    stubFetch();
    renderSettings("/projects/p1/settings?tab=activity");

    expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "활동 타임라인" }))
      .toHaveAttribute("aria-selected", "true");
  });

  it("falls back to the brief tab for an unknown tab name", async () => {
    stubFetch();
    renderSettings("/projects/p1/settings?tab=nonsense");

    expect(await screen.findByRole("heading", { name: "작품 시작 정보" }))
      .toBeInTheDocument();
  });
});
