import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectOverview } from "./ProjectOverview";

function mockFetch(...bodies: unknown[]) {
  const fetchMock = vi.fn();
  for (const body of bodies) {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => body,
    });
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={["/projects/p1/overview"]}>
      <Routes>
        <Route path="/projects/:projectId/overview" element={<ProjectOverview />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProjectOverview", () => {
  it("progressively onboards an empty project and saves normalized fields", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "brief-key-1") });
    const fetchMock = mockFetch(
      { id: "p1", name: "겨울 이야기", archived: false },
      { brief: null },
      { memory: [] },
      { project_id: "p1", items: [], gate_findings: [] },
      {
        brief: {
          id: "pb1",
          project_id: "p1",
          version_number: 1,
          premise: "겨울 항구의 비밀",
          genre: null,
          tone: null,
          pov: null,
          constraints: ["시간 여행 금지"],
        },
        idempotent_replay: false,
      },
    );

    renderOverview();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.type(screen.getByLabelText("작품 전제"), "  겨울 항구의 비밀  ");
    await userEvent.type(screen.getByLabelText(/핵심 제약/), " 시간 여행 금지 ");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText(/version 1을 저장/)).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[4][1].body);
    expect(body).toEqual({
      base_version_id: null,
      idempotency_key: "brief-key-1",
      premise: "겨울 항구의 비밀",
      genre: null,
      tone: null,
      pov: null,
      constraints: ["시간 여행 금지"],
    });
  });

  it("separates canonical cards from pending review count", async () => {
    mockFetch(
      { id: "p1", name: "겨울 이야기", archived: false },
      {
        brief: {
          id: "pb2", project_id: "p1", version_number: 2,
          premise: "전제", genre: "미스터리", tone: null, pov: null,
          constraints: [],
        },
      },
      {
        memory: [
          { id: "m1", memory_type: "character_observation", status: "canonical", payload: { name: "민아" }, version: 1 },
          { id: "m2", memory_type: "event_observation", status: "candidate", payload: { event: "숨은 후보" }, version: 1 },
        ],
      },
      { project_id: "p1", items: [{ candidate_id: "c1" }], gate_findings: [{ id: "g1" }] },
    );

    renderOverview();

    expect(await screen.findByText("민아")).toBeInTheDocument();
    expect(screen.queryByText("숨은 후보")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "검토 전 2개 →" })).toHaveAttribute(
      "href",
      "/projects/p1/review",
    );
    expect(screen.getByText(/인물 · 정본/)).toBeInTheDocument();
  });

  it("clears by appending an empty version and tells the user history remains", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "clear-key") });
    const current = {
      id: "pb1", project_id: "p1", version_number: 1,
      premise: "전제", genre: null, tone: null, pov: null, constraints: [],
    };
    const fetchMock = mockFetch(
      { id: "p1", name: "겨울 이야기", archived: false },
      { brief: current },
      { memory: [] },
      { project_id: "p1", items: [], gate_findings: [] },
      {
        brief: { ...current, id: "pb2", version_number: 2, premise: null },
        idempotent_replay: false,
      },
    );

    renderOverview();
    await userEvent.click(
      await screen.findByRole("button", { name: "작품 정보 지우기 (이력 보존)" }),
    );

    expect(await screen.findByText(/이전 version 이력은 보존/)).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toMatchObject({
      base_version_id: "pb1",
      premise: null,
      constraints: [],
    });
  });

  it("keeps archived projects readable without edit actions", async () => {
    mockFetch(
      { id: "p1", name: "보관 작품", archived: true },
      { brief: { id: "pb1", project_id: "p1", version_number: 1, premise: "남은 전제", genre: null, tone: null, pov: null, constraints: [] } },
      { memory: [] },
      { project_id: "p1", items: [], gate_findings: [] },
    );
    renderOverview();
    expect(await screen.findByText("남은 전제")).toBeInTheDocument();
    expect(screen.getByText(/읽기만 가능/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "수정" })).not.toBeInTheDocument());
  });
});
