import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftEditor } from "./DraftEditor";

type MockResponse = { status?: number; body: unknown };

function response({ status = 200, body }: MockResponse) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

function mockFetch(...responses: MockResponse[]) {
  const fetchMock = vi.fn();
  for (const next of responses) {
    fetchMock.mockResolvedValueOnce(response(next));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderEditor(path = "/projects/p1/drafts/d1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId" element={<p>원고 목록</p>} />
        <Route path="/projects/:projectId/drafts/:draftId" element={<DraftEditor />} />
      </Routes>
    </MemoryRouter>,
  );
}

const project = { id: "p1", name: "겨울 이야기", archived: false };
const draft = { id: "d1", project_id: "p1", title: "첫 장면", archived: false };
const version1 = {
  id: "v1",
  project_id: "p1",
  draft_id: "d1",
  version_number: 1,
  snapshot_id: "s1",
};
const version3 = { ...version1, id: "v3", version_number: 3, snapshot_id: "s3" };

function detail(version: typeof version1, rawText: string) {
  return {
    draft_version: version,
    snapshot: {
      id: version.snapshot_id,
      project_id: "p1",
      draft_id: "d1",
      version_id: version.id,
      raw_text: rawText,
      content_hash: `hash-${version.version_number}`,
    },
    blocks: [],
  };
}

function mockBlobDownload() {
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:download");
  const revokeObjectURL = vi.fn<(url: string) => void>();
  const clickedAnchors: HTMLAnchorElement[] = [];
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clickedAnchors.push(this);
  });
  return { createObjectURL, revokeObjectURL, click, clickedAnchors };
}

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsText(blob);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
});

describe("DraftEditor", () => {
  it("opens a zero-version draft as an unchanged empty editor", async () => {
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [] } },
    );

    renderEditor();

    expect(await screen.findByRole("heading", { name: "첫 장면" })).toBeInTheDocument();
    expect(screen.getByLabelText("원고 본문")).toHaveValue("");
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1",
      "/api/projects/p1/drafts/d1",
      "/api/projects/p1/drafts/d1/versions",
    ]);
  });

  it("loads the greatest version number and displays its exact raw text", async () => {
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3, version1] } },
      {
        body: {
          draft_version: version3,
          snapshot: {
            id: "s3",
            project_id: "p1",
            draft_id: "d1",
            version_id: "v3",
            raw_text: "첫 줄\n\n셋째 줄",
            content_hash: "hash-3",
          },
          blocks: [],
        },
      },
    );

    renderEditor();

    expect(await screen.findByLabelText("원고 본문")).toHaveValue("첫 줄\n\n셋째 줄");
    expect(screen.getByText("현재 version 3")).toBeInTheDocument();
    expect(fetchMock.mock.calls[3][0]).toBe(
      "/api/projects/p1/drafts/d1/versions/v3",
    );
  });

  it("saves the exact text once and adopts the returned version as baseline", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [] } },
      {
        body: {
          draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
          snapshot: { id: "s1", content_hash: "hash-1" },
          blocks: [],
          idempotent_replay: false,
        },
      },
    );

    const { container } = renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "첫 문장");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("version 1 저장됨")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[3];
    expect(url).toBe("/api/projects/p1/drafts/d1/versions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      raw_text: "첫 문장",
      idempotency_key: "intent-1",
    });
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();

    const form = container.querySelector("form");
    if (form === null) throw new Error("save form is missing");
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("allows a nonempty version to be deliberately saved as empty", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-empty") });
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      {
        body: {
          draft_version: version1,
          snapshot: {
            id: "s1", project_id: "p1", draft_id: "d1", version_id: "v1",
            raw_text: "지울 본문", content_hash: "hash-1",
          },
          blocks: [],
        },
      },
      {
        body: {
          draft_version: { id: "v2", version_number: 2, snapshot_id: "s2" },
          snapshot: { id: "s2", content_hash: "hash-2" },
          blocks: [],
          idempotent_replay: false,
        },
      },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.clear(editor);
    expect(screen.getByRole("button", { name: "저장" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    await screen.findByText("version 2 저장됨");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body).raw_text).toBe("");
  });

  it("prevents duplicate submits while a save is in flight", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    let releaseSave!: (value: unknown) => void;
    const pending = new Promise((resolve) => { releaseSave = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ body: project }))
      .mockResolvedValueOnce(response({ body: draft }))
      .mockResolvedValueOnce(response({ body: { versions: [] } }))
      .mockReturnValueOnce(pending);
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderEditor();
    await userEvent.type(await screen.findByLabelText("원고 본문"), "첫 문장");
    const form = container.querySelector("form");
    if (form === null) throw new Error("save form is missing");
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(4);

    releaseSave(response({
      body: {
        draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
        snapshot: { id: "s1", content_hash: "hash-1" }, blocks: [],
        idempotent_replay: false,
      },
    }));
    expect(await screen.findByText("version 1 저장됨")).toBeInTheDocument();
  });

  it("preserves edits typed while a save is in flight", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    let releaseSave!: (value: unknown) => void;
    const pending = new Promise((resolve) => { releaseSave = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ body: project }))
      .mockResolvedValueOnce(response({ body: draft }))
      .mockResolvedValueOnce(response({ body: { versions: [] } }))
      .mockReturnValueOnce(pending);
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "A");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    await userEvent.type(editor, "B");

    releaseSave(response({
      body: {
        draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
        snapshot: { id: "s1", content_hash: "hash-1" }, blocks: [],
        idempotent_replay: false,
      },
    }));

    expect(await screen.findByText("version 1 저장됨")).toBeInTheDocument();
    expect(editor).toHaveValue("AB");
    expect(screen.getByRole("button", { name: "저장" })).toBeEnabled();
    expect(JSON.parse(fetchMock.mock.calls[3][1].body).raw_text).toBe("A");
  });

  it("reuses an ambiguous intent only for the exact same text", async () => {
    const randomUUID = vi.fn()
      .mockReturnValueOnce("intent-1")
      .mockReturnValueOnce("intent-2");
    vi.stubGlobal("crypto", { randomUUID });
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [] } },
      { status: 500, body: { detail: "upstream timeout" } },
      { status: 500, body: { detail: "upstream timeout" } },
      {
        body: {
          draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
          snapshot: { id: "s1", content_hash: "hash-1" }, blocks: [],
          idempotent_replay: false,
        },
      },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "첫 문장");
    const button = screen.getByRole("button", { name: "저장" });
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("500: upstream timeout");
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("500: upstream timeout");

    expect(JSON.parse(fetchMock.mock.calls[3][1].body).idempotency_key).toBe("intent-1");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body).idempotency_key).toBe("intent-1");

    await userEvent.type(editor, " 수정");
    await userEvent.click(button);
    expect(await screen.findByText("version 1 저장됨")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[5][1].body)).toEqual({
      raw_text: "첫 문장 수정",
      idempotency_key: "intent-2",
    });
  });

  it("shows an idempotent replay only when the same ambiguous intent succeeds", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [] } },
      { status: 500, body: { detail: "response lost" } },
      {
        body: {
          draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
          snapshot: { id: "s1", content_hash: "hash-1" }, blocks: [],
          idempotent_replay: true,
        },
      },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "첫 문장");
    const button = screen.getByRole("button", { name: "저장" });
    await userEvent.click(button);
    await screen.findByRole("alert");
    await userEvent.click(button);

    expect(await screen.findByText("version 1 재확인됨")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[3][1].body).idempotency_key).toBe("intent-1");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body).idempotency_key).toBe("intent-1");
  });

  it("warns before unload only while the editor is dirty", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: [] } },
      {
        body: {
          draft_version: { id: "v1", version_number: 1, snapshot_id: "s1" },
          snapshot: { id: "s1", content_hash: "hash-1" }, blocks: [],
          idempotent_replay: false,
        },
      },
    );

    renderEditor();
    await userEvent.type(await screen.findByLabelText("원고 본문"), "첫 문장");
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyEvent);
    expect(dirtyEvent.defaultPrevented).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "저장" })).toBeDisabled());
    const cleanEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanEvent);
    expect(cleanEvent.defaultPrevented).toBe(false);
  });

  it("lists versions newest-first and loads a selected historical version", async () => {
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version1, version3] } },
      { body: detail(version3, "셋째 원고") },
      { body: detail(version1, "첫 원고") },
    );

    renderEditor();
    expect(await screen.findByLabelText("원고 본문")).toHaveValue("셋째 원고");
    const history = screen.getByRole("list", { name: "버전 기록" });
    expect(within(history).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "version 3",
      "version 1",
    ]);
    expect(screen.getByRole("button", { name: "version 3" })).toHaveAttribute(
      "aria-current",
      "true",
    );

    await userEvent.click(screen.getByRole("button", { name: "version 1" }));

    expect(await screen.findByLabelText("원고 본문")).toHaveValue("첫 원고");
    expect(screen.getByText("현재 version 1")).toBeInTheDocument();
    expect(fetchMock.mock.calls[4][0]).toBe("/api/projects/p1/drafts/d1/versions/v1");
  });

  it("cancels a dirty version switch, then discards only after confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version1, version3] } },
      { body: detail(version3, "셋째 원고") },
      { body: detail(version1, "첫 원고") },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, " 수정");
    await userEvent.click(screen.getByRole("button", { name: "version 1" }));

    expect(editor).toHaveValue("셋째 원고 수정");
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(confirm).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "version 1" }));
    expect(await screen.findByLabelText("원고 본문")).toHaveValue("첫 원고");
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("preserves the current text when a confirmed version load fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version1, version3] } },
      { body: detail(version3, "셋째 원고") },
      { status: 404, body: { detail: "version not found" } },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, " 수정");
    await userEvent.click(screen.getByRole("button", { name: "version 1" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("404: version not found");
    expect(editor).toHaveValue("셋째 원고 수정");
    expect(screen.getByRole("button", { name: "version 3" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("locks editing only while a version selection is in flight", async () => {
    let releaseSelection!: (value: unknown) => void;
    const pendingSelection = new Promise((resolve) => { releaseSelection = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ body: project }))
      .mockResolvedValueOnce(response({ body: draft }))
      .mockResolvedValueOnce(response({ body: { versions: [version1, version3] } }))
      .mockResolvedValueOnce(response({ body: detail(version3, "셋째 원고") }))
      .mockReturnValueOnce(pendingSelection);
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.click(screen.getByRole("button", { name: "version 1" }));

    await waitFor(() => expect(editor).toHaveAttribute("aria-busy", "true"));
    expect(editor).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "version 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "version 3" })).toBeDisabled();

    releaseSelection(response({ body: detail(version1, "첫 원고") }));

    expect(await screen.findByLabelText("원고 본문")).toHaveValue("첫 원고");
    await waitFor(() => expect(editor).not.toHaveAttribute("readonly"));
    expect(editor).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("button", { name: "version 1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "version 3" })).toBeEnabled();
  });

  it("selects a newly saved version without mutating historical versions", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-4") });
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version1, version3] } },
      { body: detail(version3, "셋째 원고") },
      { body: detail(version1, "첫 원고") },
      {
        body: {
          draft_version: { id: "v4", version_number: 4, snapshot_id: "s4" },
          snapshot: { id: "s4", content_hash: "hash-4" }, blocks: [],
          idempotent_replay: false,
        },
      },
    );

    renderEditor();
    await userEvent.click(await screen.findByRole("button", { name: "version 1" }));
    await userEvent.type(screen.getByLabelText("원고 본문"), "에서 이어쓰기");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("version 4 저장됨")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "version 4" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "version 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "version 3" })).toBeInTheDocument();
  });

  it.each([
    [
      "TXT 내보내기",
      "txt",
      "d1-v3.txt",
      "text/plain; charset=utf-8",
      "원문 그대로",
    ],
    [
      "Markdown 내보내기",
      "markdown",
      "d1-v3.md",
      "text/markdown; charset=utf-8",
      "# 원문 그대로",
    ],
  ])("downloads the selected version through %s", async (
    buttonName,
    format,
    filename,
    contentType,
    body,
  ) => {
    const download = mockBlobDownload();
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version3] } },
      { body: detail(version3, body) },
      {
        body: {
          format, filename, content_type: contentType, body,
          project_id: "p1", draft_id: "d1", version_id: "v3",
          version_number: 3, snapshot_id: "s3", content_hash: "hash-3",
        },
      },
    );

    renderEditor();
    await userEvent.click(await screen.findByRole("button", { name: buttonName }));

    expect(fetchMock.mock.calls[4][0]).toBe(
      `/api/projects/p1/drafts/d1/versions/v3/export?format=${format}`,
    );
    const blob = download.createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe(contentType);
    expect(await readBlob(blob)).toBe(body);
    expect(download.click).toHaveBeenCalledTimes(1);
    expect(download.clickedAnchors[0].download).toBe(filename);
    expect(download.revokeObjectURL).toHaveBeenCalledWith("blob:download");
  });

  it("surfaces export failure without changing the selected text", async () => {
    const download = mockBlobDownload();
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: [version3] } },
      { body: detail(version3, "셋째 원고") },
      { status: 404, body: { detail: "version not found" } },
    );

    renderEditor();
    await userEvent.click(await screen.findByRole("button", { name: "TXT 내보내기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("404: version not found");
    expect(screen.getByLabelText("원고 본문")).toHaveValue("셋째 원고");
    expect(download.createObjectURL).not.toHaveBeenCalled();
  });

  it("keeps archived drafts readable and turns a save 409 into read-only", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-1") });
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [] } },
      { status: 409, body: { detail: "draft is archived" } },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "보존할 입력");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("409: draft is archived");
    expect(editor).toHaveValue("보존할 입력");
    expect(editor).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "저장" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it.each([
    [{ ...project, archived: true }, draft],
    [project, { ...draft, archived: true }],
  ])("renders an initially archived project or draft read-only without a save", async (
    archivedProject,
    archivedDraft,
  ) => {
    const fetchMock = mockFetch(
      { body: archivedProject },
      { body: archivedDraft },
      { body: { versions: [] } },
    );

    renderEditor();

    expect(await screen.findByLabelText("원고 본문")).toHaveAttribute("readonly");
    expect(screen.getByText(/보관된 원고는 읽기 전용/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "저장" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([
    [
      [{ body: project }, { body: draft }, { status: 404, body: { detail: "versions not found" } }],
      "404: versions not found",
    ],
    [
      [
        { body: project }, { body: draft }, { body: { versions: [version1] } },
        { status: 404, body: { detail: "version not found" } },
      ],
      "404: version not found",
    ],
  ] as Array<[MockResponse[], string]>) (
    "surfaces version load failures without showing another draft's body",
    async (responses, message) => {
      mockFetch(...responses);

      renderEditor();

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.queryByLabelText("원고 본문")).not.toBeInTheDocument();
    },
  );

  it("surfaces a missing draft without showing another draft's body", async () => {
    mockFetch(
      { body: project },
      { status: 404, body: { detail: "draft not found" } },
      { body: { versions: [] } },
    );

    renderEditor("/projects/p1/drafts/missing");

    expect(await screen.findByRole("alert")).toHaveTextContent("404: draft not found");
    expect(screen.queryByLabelText("원고 본문")).not.toBeInTheDocument();
  });

  it("keeps text after a definitive save 404 but uses a new key on retry", async () => {
    const randomUUID = vi.fn()
      .mockReturnValueOnce("intent-1")
      .mockReturnValueOnce("intent-2");
    vi.stubGlobal("crypto", { randomUUID });
    const fetchMock = mockFetch(
      { body: project }, { body: draft }, { body: { versions: [] } },
      { status: 404, body: { detail: "draft not found" } },
      { status: 404, body: { detail: "draft not found" } },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "보존할 본문");
    const button = screen.getByRole("button", { name: "저장" });
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("404: draft not found");
    expect(editor).toHaveValue("보존할 본문");
    await userEvent.click(button);

    expect(JSON.parse(fetchMock.mock.calls[3][1].body).idempotency_key).toBe("intent-1");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body).idempotency_key).toBe("intent-2");
  });
});
