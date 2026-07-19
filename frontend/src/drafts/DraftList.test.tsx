import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import JSZip from "jszip";
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
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "scene", position: 1,
            },
            {
              id: "d2", project_id: "p1", title: "묵은 장면", archived: true,
              unit_kind: "other", position: 2,
            },
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
    expect(screen.getByText("정본 순서 1 · 장면")).toBeInTheDocument();
    expect(screen.getByText("정본 순서 2 · 기타")).toBeInTheDocument();
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
      {
        body: {
          id: "d1", project_id: "p1", title: "첫 장면", archived: false,
          unit_kind: "scene", position: 1,
        },
      },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "scene", position: 1,
            },
          ],
        },
      },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");
    await userEvent.selectOptions(screen.getByLabelText("원고 단위"), "scene");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    expect(await screen.findByText("첫 장면")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/drafts");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ title: "첫 장면", unit_kind: "scene" });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("reorders the complete server-owned draft permutation", async () => {
    const one = {
      id: "d1", project_id: "p1", title: "첫 장", archived: false,
      unit_kind: "chapter", position: 1,
    };
    const two = {
      id: "d2", project_id: "p1", title: "둘째 장면", archived: true,
      unit_kind: "scene", position: 2,
    };
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [one, two] } },
      { body: { drafts: [{ ...two, position: 1 }, { ...one, position: 2 }] } },
    );

    renderDraftList();
    await screen.findByText("첫 장");
    await userEvent.click(screen.getByRole("button", { name: "첫 장 아래로" }));

    await waitFor(() => {
      const rows = screen.getAllByRole("listitem");
      expect(rows[0]).toHaveTextContent("둘째 장면");
      expect(rows[1]).toHaveTextContent("첫 장");
    });
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/draft-order");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ ordered_draft_ids: ["d2", "d1"] });
  });

  it("trims a normal title but never posts a whitespace-only title", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      {
        body: {
          id: "d1", project_id: "p1", title: "첫 장면", archived: false,
          unit_kind: "other", position: 1,
        },
      },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "other", position: 1,
            },
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
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      title: "첫 장면",
      unit_kind: "other",
    });
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
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "other", position: 1,
            },
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
      json: async () => ({
        id: "d1", project_id: "p1", title: "첫 장면", archived: false,
        unit_kind: "other", position: 1,
      }),
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
            {
              id: "d1", project_id: "p1", title: "남은 원고", archived: false,
              unit_kind: "other", position: 1,
            },
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

  /** Read a Blob's text (jsdom's Blob lacks the async .text() helper). */
  function blobText(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(blob);
    });
  }

  /** Capture browser downloads triggered via URL.createObjectURL + anchor. */
  function captureDownloads() {
    const blobs: Blob[] = [];
    const downloads: string[] = [];
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = (
      blob: Blob,
    ) => {
      blobs.push(blob);
      return "blob:mock";
    };
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = () => {};
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });
    return { blobs, downloads };
  }

  const twoDrafts = {
    drafts: [
      {
        id: "d1", project_id: "p1", title: "1장", archived: false,
        unit_kind: "chapter", position: 1,
      },
      {
        id: "d2", project_id: "p1", title: "2장", archived: false,
        unit_kind: "chapter", position: 2,
      },
    ],
  };

  it("downloads the whole project as one combined file", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: twoDrafts },
      {
        body: {
          format: "txt",
          filename: "p1.txt",
          content_type: "text/plain; charset=utf-8",
          body: "1장\n\nfirst\n\n2장\n\nsecond",
          project_id: "p1",
          include_archived: false,
          manifest: null,
        },
      },
    );
    const { blobs, downloads } = captureDownloads();

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "TXT로 내보내기" }));

    await waitFor(() => expect(downloads).toEqual(["p1.txt"]));
    // The combined export hits the whole-project endpoint without a manifest.
    const exportCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes("/projects/p1/export?"),
    );
    expect(String(exportCall?.[0])).toContain("format=txt");
    expect(String(exportCall?.[0])).not.toContain("manifest=true");
    // The downloaded blob carries the server body verbatim with its content type
    // (no client-side transformation).
    const blob = blobs.at(-1)!;
    expect(await blobText(blob)).toBe("1장\n\nfirst\n\n2장\n\nsecond");
    expect(blob.type).toBe("text/plain; charset=utf-8");
  });

  it("bundles each unit as its own file inside a zip", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: twoDrafts },
      {
        // manifest=true response: enumerates the included units.
        body: {
          format: "markdown",
          filename: "p1.md",
          content_type: "text/markdown; charset=utf-8",
          body: "# 1장\n\nfirst\n\n# 2장\n\nsecond",
          project_id: "p1",
          include_archived: false,
          manifest: {
            project_id: "p1",
            format: "markdown",
            include_archived: false,
            units: [
              {
                draft_id: "d1", title: "1장", unit_kind: "chapter", position: 1,
                version_id: "v1", version_number: 1, snapshot_id: "s1",
                content_hash: "h1",
              },
              {
                draft_id: "d2", title: "2장", unit_kind: "chapter", position: 2,
                version_id: "v2", version_number: 1, snapshot_id: "s2",
                content_hash: "h2",
              },
            ],
          },
        },
      },
      // Per-unit verbatim bodies, one fetch each.
      {
        body: {
          format: "markdown", filename: "d1-v1.md",
          content_type: "text/markdown; charset=utf-8", body: "first",
          project_id: "p1", draft_id: "d1", version_id: "v1", version_number: 1,
          snapshot_id: "s1", content_hash: "h1",
        },
      },
      {
        body: {
          format: "markdown", filename: "d2-v1.md",
          content_type: "text/markdown; charset=utf-8", body: "second",
          project_id: "p1", draft_id: "d2", version_id: "v2", version_number: 1,
          snapshot_id: "s2", content_hash: "h2",
        },
      },
    );
    const { blobs, downloads } = captureDownloads();

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "Markdown ZIP" }));

    await waitFor(() => expect(downloads).toEqual(["p1.zip"]));
    // Manifest was requested, then each unit's latest version was fetched.
    const manifestCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes("manifest=true"),
    );
    expect(manifestCall).toBeDefined();
    const perUnit = fetchMock.mock.calls.filter((call) =>
      /\/drafts\/d\d\/versions\/v\d\/export/.test(String(call[0])),
    );
    expect(perUnit).toHaveLength(2);
    // The bundle is a real zip whose entries include each unit and the manifest.
    const zip = await JSZip.loadAsync(blobs.at(-1)!);
    expect(Object.keys(zip.files).sort()).toEqual([
      "01-1장.md",
      "02-2장.md",
      "manifest.json",
    ]);
    expect(await zip.file("01-1장.md")!.async("string")).toBe("first");
  });

  it("does not start a second export while the first is in flight", async () => {
    let releaseExport!: (response: unknown) => void;
    const pendingExport = new Promise((resolve) => {
      releaseExport = resolve;
    });
    const fetchMock = vi.fn();
    fetchMock
      .mockResolvedValueOnce({
        ok: true, status: 200, statusText: "",
        json: async () => ({ id: "p1", name: "겨울 이야기", archived: false }),
      })
      .mockResolvedValueOnce({
        ok: true, status: 200, statusText: "",
        json: async () => twoDrafts,
      })
      .mockReturnValueOnce(pendingExport);
    vi.stubGlobal("fetch", fetchMock);
    captureDownloads();

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "TXT로 내보내기" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    // Every export button is disabled while one export is running.
    expect(screen.getByRole("button", { name: "내보내는 중…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Markdown ZIP" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Markdown ZIP" }));
    expect(fetchMock).toHaveBeenCalledTimes(3);

    releaseExport({
      ok: true, status: 200, statusText: "",
      json: async () => ({
        format: "txt", filename: "p1.txt", content_type: "text/plain; charset=utf-8",
        body: "1장\n\nfirst\n\n2장\n\nsecond", project_id: "p1",
        include_archived: false, manifest: null,
      }),
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "TXT로 내보내기" })).toBeEnabled(),
    );
  });

  it("hides export controls when the project has no units", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    expect(screen.queryByRole("button", { name: "TXT로 내보내기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Markdown ZIP" })).toBeNull();
  });

  it("hides export controls when every unit is archived", async () => {
    // Archived units are excluded by default, so an archived-only project would
    // only ever export an empty file / manifest-only zip. Don't offer controls
    // that produce nothing.
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "묵은 장", archived: true,
              unit_kind: "chapter", position: 1,
            },
          ],
        },
      },
    );

    renderDraftList();
    // The archived unit still renders in the list…
    await screen.findByText("묵은 장");
    // …but no export control is offered.
    expect(screen.queryByRole("button", { name: "TXT로 내보내기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Markdown ZIP" })).toBeNull();
  });

  it("sanitizes unit titles and falls back to the draft id for zip entry names", async () => {
    const trickyDrafts = {
      drafts: [
        {
          id: "d1", project_id: "p1", title: 'a/b:c*?"<>|', archived: false,
          unit_kind: "other", position: 1,
        },
        {
          id: "draft-xyz", project_id: "p1", title: "   ", archived: false,
          unit_kind: "other", position: 2,
        },
      ],
    };
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: trickyDrafts },
      {
        body: {
          format: "txt", filename: "p1.txt",
          content_type: "text/plain; charset=utf-8", body: "x", project_id: "p1",
          include_archived: false,
          manifest: {
            project_id: "p1", format: "txt", include_archived: false,
            units: [
              {
                draft_id: "d1", title: 'a/b:c*?"<>|', unit_kind: "other",
                position: 1, version_id: "v1", version_number: 1,
                snapshot_id: "s1", content_hash: "h1",
              },
              {
                draft_id: "draft-xyz", title: "   ", unit_kind: "other",
                position: 2, version_id: "v2", version_number: 1,
                snapshot_id: "s2", content_hash: "h2",
              },
            ],
          },
        },
      },
      {
        body: {
          format: "txt", filename: "d1-v1.txt",
          content_type: "text/plain; charset=utf-8", body: "one",
          project_id: "p1", draft_id: "d1", version_id: "v1", version_number: 1,
          snapshot_id: "s1", content_hash: "h1",
        },
      },
      {
        body: {
          format: "txt", filename: "draft-xyz-v1.txt",
          content_type: "text/plain; charset=utf-8", body: "two",
          project_id: "p1", draft_id: "draft-xyz", version_id: "v2",
          version_number: 1, snapshot_id: "s2", content_hash: "h2",
        },
      },
    );
    const { blobs, downloads } = captureDownloads();

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "TXT ZIP" }));

    await waitFor(() => expect(downloads).toEqual(["p1.zip"]));
    const zip = await JSZip.loadAsync(blobs.at(-1)!);
    expect(Object.keys(zip.files).sort()).toEqual([
      // path-unsafe chars (/ : * ? " < > |) each replaced with "_"; a title that
      // sanitizes to empty (whitespace-only) falls back to the draft id; position
      // is zero-padded to two digits.
      "01-a_b_c______.txt",
      "02-draft-xyz.txt",
      "manifest.json",
    ]);
  });
});
