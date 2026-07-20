import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function ok(body: unknown) {
  return { ok: true, status: 200, statusText: "", json: async () => body };
}

function mockFetch(...bodies: unknown[]) {
  const fetchMock = vi.fn();
  for (const body of bodies) {
    fetchMock.mockResolvedValueOnce(ok(body));
  }
  // The draft editor's unaccepted-candidate recovery banner (ScratchRecovery)
  // fetches its own list on mount. That call is orthogonal to the routing these
  // tests pin, so it is served an empty list *outside* the recorded mock —
  // otherwise the expected request sequences below would gain a stray entry.
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (typeof url === "string" && url.includes("/writing/scratch")) {
      return Promise.resolve(ok({ project_id: "p1", draft_id: "d1", items: [] }));
    }
    return fetchMock(url, init);
  });
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App routes", () => {
  it("renders the project index at the root route", async () => {
    mockFetch({ projects: [] });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
  });

  it("renders a directly addressed project workspace", async () => {
    const fetchMock = mockFetch(
      { id: "p1", name: "겨울 이야기", archived: false },
      { drafts: [] },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1",
      "/api/projects/p1/drafts",
    ]);
  });

  it("renders a directly addressed draft editor", async () => {
    const fetchMock = mockFetch(
      { id: "p1", name: "겨울 이야기", archived: false },
      { id: "d1", project_id: "p1", title: "첫 장면", archived: false },
      { versions: [] },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1/drafts/d1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "첫 장면" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1",
      "/api/projects/p1/drafts/d1",
      "/api/projects/p1/drafts/d1/versions",
    ]);
  });

  it("keeps an unknown route inside the product shell", async () => {
    render(
      <MemoryRouter initialEntries={["/missing"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "이 작업 공간은 없습니다." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "프로젝트로 돌아가기" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
