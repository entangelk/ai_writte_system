import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectList } from "./ProjectList";

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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderProjectList() {
  return render(
    <MemoryRouter>
      <ProjectList />
    </MemoryRouter>,
  );
}

describe("ProjectList", () => {
  it("lists projects returned by GET /projects", async () => {
    mockFetch({
      body: {
        projects: [
          { id: "p1", name: "겨울 이야기", archived: false },
          { id: "p2", name: "묵은 초고", archived: true },
        ],
      },
    });

    renderProjectList();

    expect(await screen.findByText("겨울 이야기")).toBeInTheDocument();
    expect(screen.getByText("묵은 초고")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "겨울 이야기" })).toHaveAttribute(
      "href",
      "/projects/p1",
    );
    // Archived projects are readable but marked (Core SOT: archive = read + write 409).
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
  });

  it("calls the single-origin /api path, never a cross-origin URL", async () => {
    // Over-strict guard: the deployed stack keeps one origin via the nginx /api
    // proxy (D2=B). An absolute API base would silently require CORS.
    const fetchMock = mockFetch({ body: { projects: [] } });

    renderProjectList();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects");
  });

  it("shows an empty state instead of a list when there are no projects", async () => {
    mockFetch({ body: { projects: [] } });

    renderProjectList();

    expect(await screen.findByText(/아직 프로젝트가 없습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("posts a new project and reloads the list", async () => {
    const fetchMock = mockFetch(
      { body: { projects: [] } },
      { body: { id: "p1", name: "새 작품", archived: false } },
      { body: { projects: [{ id: "p1", name: "새 작품", archived: false }] } },
    );

    renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 프로젝트 이름"), "새 작품");
    await userEvent.click(screen.getByRole("button", { name: "만들기" }));

    expect(await screen.findByText("새 작품")).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/projects");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ name: "새 작품" });
    // The list is re-read from the server rather than patched client-side, so
    // the rendered list stays the server's truth.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("trims the name before posting and clears the field on success", async () => {
    const fetchMock = mockFetch(
      { body: { projects: [] } },
      { body: { id: "p1", name: "새 작품", archived: false } },
      { body: { projects: [{ id: "p1", name: "새 작품", archived: false }] } },
    );

    renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    const field = screen.getByLabelText("새 프로젝트 이름");
    await userEvent.type(field, "  새 작품  ");
    await userEvent.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() => expect(field).toHaveValue(""));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ name: "새 작품" });
  });

  it("does not post a whitespace-only name", async () => {
    // Over-strict guard on the trim: blank input must not reach the API at all.
    const fetchMock = mockFetch({ body: { projects: [] } });

    renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 프로젝트 이름"), "   ");
    expect(screen.getByRole("button", { name: "만들기" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not post twice while a create is already in flight", async () => {
    // Over-strict guard on the in-flight guard (ProjectList `saving`): a second
    // submit during the POST must not mint a second project. Submitting the form
    // directly bypasses the disabled button, so this pins the guard inside
    // submit() rather than only the button's disabled attribute.
    let releasePost!: (response: unknown) => void;
    const pendingPost = new Promise((resolve) => {
      releasePost = resolve;
    });

    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ projects: [] }),
    });
    fetchMock.mockReturnValueOnce(pendingPost);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ projects: [{ id: "p1", name: "새 작품", archived: false }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    const form = container.querySelector("form");
    if (form === null) {
      throw new Error("form is missing");
    }
    await userEvent.type(screen.getByLabelText("새 프로젝트 이름"), "새 작품");

    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2)); // list + POST
    expect(screen.getByRole("button", { name: "만들기" })).toBeDisabled();

    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(2); // still just the one POST

    releasePost({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ id: "p1", name: "새 작품", archived: false }),
    });

    // The single POST completes normally and the list reloads once.
    expect(await screen.findByText("새 작품")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts).toHaveLength(1);
  });

  it("surfaces the API error detail when the list request fails", async () => {
    mockFetch({ status: 500, body: { detail: "core sot unavailable" } });

    renderProjectList();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "500: core sot unavailable",
    );
  });

  it("surfaces the API error detail when create fails and keeps the input", async () => {
    mockFetch(
      { body: { projects: [] } },
      { status: 409, body: { detail: "project is archived" } },
    );

    renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 프로젝트 이름"), "새 작품");
    await userEvent.click(screen.getByRole("button", { name: "만들기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "409: project is archived",
    );
    // The typed name survives a failed save so the user does not retype it.
    expect(screen.getByLabelText("새 프로젝트 이름")).toHaveValue("새 작품");
  });

  it("clears a previous error once a later request succeeds", async () => {
    mockFetch(
      { body: { projects: [] } },
      { status: 409, body: { detail: "project is archived" } },
      { body: { id: "p1", name: "새 작품", archived: false } },
      { body: { projects: [{ id: "p1", name: "새 작품", archived: false }] } },
    );

    renderProjectList();
    await screen.findByText(/아직 프로젝트가 없습니다/);

    const button = screen.getByRole("button", { name: "만들기" });
    await userEvent.type(screen.getByLabelText("새 프로젝트 이름"), "새 작품");
    await userEvent.click(button);
    await screen.findByRole("alert");

    await userEvent.click(button);

    expect(await screen.findByText("새 작품")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
