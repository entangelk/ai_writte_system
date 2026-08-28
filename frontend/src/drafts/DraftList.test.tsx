import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Chapter, Draft } from "../api/client";
import { DraftList } from "./DraftList";

function mockFetch(...responses: Array<{ status?: number; body: unknown }>) {
  const fetchMock = vi.fn();
  for (const { status = 200, body } of responses) {
    fetchMock.mockResolvedValueOnce({
      ok: status >= 200 && status < 300,
      status,
      statusText: "",
      json: async () => body,
    });
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function chapter(
  id: string, title: string, position: number, scenes: Draft[] = [],
): Chapter {
  return { id, project_id: "p1", title, archived: false, position, scenes };
}

function scene(
  id: string, chapterId: string, title: string, position: number,
): Draft {
  return {
    id, project_id: "p1", chapter_id: chapterId, title,
    archived: false, position,
  };
}

function renderDraftList() {
  return render(<MemoryRouter initialEntries={["/projects/p1"]}>
    <Routes><Route path="/projects/:projectId" element={<DraftList />} /></Routes>
  </MemoryRouter>);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DraftList Chapter→Scene hierarchy", () => {
  it("renders scenes inside their chapter instead of a flat unit-kind list", async () => {
    const one = scene("s1", "c1", "첫 장면", 1);
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { chapters: [chapter("c1", "1장", 1, [one])] } },
    );

    renderDraftList();

    expect(await screen.findByRole("heading", { name: "겨울 이야기" })).toBeInTheDocument();
    expect(screen.getByText("1장")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "첫 장면" })).toHaveAttribute(
      "href", "/projects/p1/drafts/s1",
    );
    expect(screen.getByText("장 순서 1")).toBeInTheDocument();
    expect(screen.getByText("장면 순서 1")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1", "/api/projects/p1/chapters",
    ]);
  });

  it("creates a chapter then creates a scene with its required chapter_id", async () => {
    const c1 = chapter("c1", "1장", 1);
    const s1 = scene("s1", "c1", "첫 장면", 1);
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "작품", archived: false } },
      { body: { chapters: [] } },
      { body: c1 },
      { body: { chapters: [c1] } },
      { body: s1 },
      { body: { chapters: [{ ...c1, scenes: [s1] }] } },
    );
    renderDraftList();
    await screen.findByText("아직 장이 없습니다.");

    await userEvent.type(screen.getByLabelText("새 장 제목"), "  1장  ");
    await userEvent.click(screen.getByRole("button", { name: "장 만들기" }));
    await screen.findByText("아직 장면이 없습니다.");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ title: "1장" });

    await userEvent.type(screen.getByLabelText("새 장면"), "첫 장면");
    await userEvent.click(screen.getByRole("button", { name: "장면 만들기" }));
    await screen.findByRole("link", { name: "첫 장면" });
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({
      title: "첫 장면", chapter_id: "c1",
    });
  });

  it("uses independent chapter and parent-scoped scene reorder endpoints", async () => {
    const s1 = scene("s1", "c1", "첫 장면", 1);
    const s2 = scene("s2", "c1", "둘째 장면", 2);
    const c1 = chapter("c1", "1장", 1, [s1, s2]);
    const c2 = chapter("c2", "2장", 2);
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "작품", archived: false } },
      { body: { chapters: [c1, c2] } },
      { body: { chapters: [{ ...c2, position: 1 }, { ...c1, position: 2 }] } },
      { body: { scenes: [{ ...s2, position: 1 }, { ...s1, position: 2 }] } },
    );
    renderDraftList();
    await screen.findByText("첫 장면");

    await userEvent.click(screen.getByRole("button", { name: "1장 아래로" }));
    await userEvent.click(screen.getByRole("button", { name: "첫 장면 아래로" }));

    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/chapter-order");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      ordered_chapter_ids: ["c2", "c1"],
    });
    expect(fetchMock.mock.calls[3][0]).toBe("/api/projects/p1/chapters/c1/scene-order");
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({
      ordered_draft_ids: ["s2", "s1"],
    });
  });

  it("requires the exact chapter title before cascade purge", async () => {
    const c1 = chapter("c1", "1장", 1, [scene("s1", "c1", "첫 장면", 1)]);
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "작품", archived: false } },
      { body: { chapters: [c1] } },
      { body: { ...c1, archived: true } },
      { status: 204, body: null },
      { body: { chapters: [] } },
    );
    renderDraftList();
    await screen.findByText("첫 장면");
    await userEvent.click(screen.getByRole("button", { name: "1장 삭제" }));
    const purge = screen.getByRole("button", { name: "장과 장면 영구 삭제" });
    expect(purge).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/장 제목을 정확히/), "1 장");
    expect(purge).toBeDisabled();
    await userEvent.clear(screen.getByLabelText(/장 제목을 정확히/));
    await userEvent.type(screen.getByLabelText(/장 제목을 정확히/), "1장");
    await userEvent.click(purge);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/chapters/c1/archive");
    expect(fetchMock.mock.calls[3][0]).toBe("/api/projects/p1/chapters/c1/purge");
  });

  it("keeps the confirmation open and marks a 503 purge result uncertain", async () => {
    const c1 = { ...chapter("c1", "1장", 1), archived: true };
    mockFetch(
      { body: { id: "p1", name: "작품", archived: false } },
      { body: { chapters: [c1] } },
      { status: 503, body: { detail: "transaction outcome unknown" } },
    );
    renderDraftList();
    await screen.findByText("1장");
    await userEvent.click(screen.getByRole("button", { name: "1장 삭제" }));
    await userEvent.type(screen.getByLabelText(/장 제목을 정확히/), "1장");
    await userEvent.click(screen.getByRole("button", { name: "장과 장면 영구 삭제" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("삭제 결과를 확정할 수 없습니다");
    expect(screen.getByRole("alertdialog", { name: "장 삭제 확인" })).toBeInTheDocument();
  });
});
