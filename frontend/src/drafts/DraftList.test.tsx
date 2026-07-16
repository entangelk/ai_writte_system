import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftList } from "./DraftList";

/** Queue one JSON response per fetch call, in order. */
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

function renderDraftList(path = "/projects/p1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>프로젝트 홈</p>} />
        <Route path="/projects/:projectId" element={<DraftList />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DraftList", () => {
  it("loads the selected project and only that project's drafts", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      {
        body: {
          drafts: [
            { id: "d1", project_id: "p1", title: "첫 장면", archived: false },
            { id: "d2", project_id: "p1", title: "묵은 장면", archived: true },
          ],
        },
      },
    );

    renderDraftList();

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
    expect(screen.getByText("첫 장면")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "첫 장면" })).toHaveAttribute(
      "href",
      "/projects/p1/drafts/d1",
    );
    expect(screen.getByText("묵은 장면")).toBeInTheDocument();
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1",
      "/api/projects/p1/drafts",
    ]);
  });

  it("supports a direct project URL and shows an empty draft state", async () => {
    mockFetch(
      { body: { id: "deep-link", name: "직접 진입", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList("/projects/deep-link");

    expect(await screen.findByText(/아직 원고가 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "직접 진입" })).toBeInTheDocument();
  });

  it("posts a new draft and reloads the server-owned draft list", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      { body: { id: "d1", project_id: "p1", title: "첫 장면", archived: false } },
      {
        body: {
          drafts: [
            { id: "d1", project_id: "p1", title: "첫 장면", archived: false },
          ],
        },
      },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    expect(await screen.findByText("첫 장면")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/drafts");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ title: "첫 장면" });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("trims a normal title but never posts a whitespace-only title", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      { body: { id: "d1", project_id: "p1", title: "첫 장면", archived: false } },
      {
        body: {
          drafts: [
            { id: "d1", project_id: "p1", title: "첫 장면", archived: false },
          ],
        },
      },
    );

    const { container } = renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    const field = screen.getByLabelText("새 원고 제목");
    await userEvent.type(field, "   ");
    expect(screen.getByRole("button", { name: "원고 만들기" })).toBeDisabled();
    const form = container.querySelector("form");
    if (form === null) {
      throw new Error("form is missing");
    }
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await userEvent.clear(field);
    await userEvent.type(field, "  첫 장면  ");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    await waitFor(() => expect(field).toHaveValue(""));
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ title: "첫 장면" });
  });

  it("does not mint two drafts while the first create is in flight", async () => {
    let releasePost!: (response: unknown) => void;
    const pendingPost = new Promise((resolve) => {
      releasePost = resolve;
    });
    const fetchMock = vi.fn();
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ id: "p1", name: "겨울 이야기", archived: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ drafts: [] }),
      })
      .mockReturnValueOnce(pendingPost)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({
          drafts: [
            { id: "d1", project_id: "p1", title: "첫 장면", archived: false },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);
    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");

    const form = container.querySelector("form");
    if (form === null) {
      throw new Error("form is missing");
    }
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    releasePost({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ id: "d1", project_id: "p1", title: "첫 장면", archived: false }),
    });

    expect(await screen.findByText("첫 장면")).toBeInTheDocument();
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts).toHaveLength(1);
  });

  it("keeps an archived project readable but prevents an over-strict write", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "보관 작품", archived: true } },
      {
        body: {
          drafts: [
            { id: "d1", project_id: "p1", title: "남은 원고", archived: false },
          ],
        },
      },
    );

    renderDraftList();

    expect(await screen.findByText("남은 원고")).toBeInTheDocument();
    expect(screen.getByText(/보관된 프로젝트에서는 새 원고를 만들 수 없습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText("새 원고 제목")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("surfaces a draft list failure without leaking another project", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { status: 404, body: { detail: "project not found" } },
    );

    renderDraftList();

    expect(await screen.findByRole("alert")).toHaveTextContent("404: project not found");
    expect(screen.queryByText("첫 장면")).not.toBeInTheDocument();
  });

  it("surfaces create failure and keeps the title for retry", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      { status: 409, body: { detail: "project is archived" } },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);
    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "409: project is archived",
    );
    expect(screen.getByLabelText("새 원고 제목")).toHaveValue("첫 장면");
  });

  it("returns to the project list through browser navigation", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(
      screen.getByRole("link", { name: /프로젝트로 돌아가기/ }),
    );

    expect(await screen.findByText("프로젝트 홈")).toBeInTheDocument();
  });
});
