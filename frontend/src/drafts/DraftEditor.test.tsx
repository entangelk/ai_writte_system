import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftEditor } from "./DraftEditor";
import { resetMemberQuota, seedMemberQuota } from "../quota/useMemberQuota";

type MockResponse = { status?: number; body: unknown };

function response({ status = 200, body }: MockResponse) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

// The unaccepted-candidate recovery banner (ScratchRecovery) fetches its own
// list when the editor mounts, which is orthogonal to every flow pinned in this
// file. Serve it an empty list *outside* the recorded mock so the ordered
// indices and call counts below keep describing the editor's own requests only.
// (The always-mounted WorkspaceReviewPanel skips its fetch when its tab is
// inactive — see `tabActive` — so no review-inbox stub is needed here.)
function stubFetch<T extends ReturnType<typeof vi.fn>>(fetchMock: T): T {
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (typeof url === "string" && url.includes("/writing/scratch")) {
      return Promise.resolve(
        response({ body: { project_id: "p1", draft_id: "d1", items: [] } }),
      );
    }
    // K-4: WritingPanel 마운트 시 /writing/budget GET 이 발생 — 기존 fetchMock 시퀀스를
    // 건드리지 않게 자동 응답한다(stubFetch 의 URL 가로채기 패턴).
    if (typeof url === "string" && url.includes("/writing/budget")) {
      return Promise.resolve(
        response({
          body: {
            project_id: "p1",
            context_budget_tokens: { short: 8192, medium: 8192, long: 8192 },
          },
        }),
      );
    }
    return fetchMock(url, init);
  });
  return fetchMock;
}

function mockFetch(...responses: MockResponse[]) {
  const fetchMock = vi.fn();
  for (const next of responses) {
    fetchMock.mockResolvedValueOnce(response(next));
  }
  return stubFetch(fetchMock);
}

// 기본 경로는 드로어를 연 채 시작한다(?panel=writing) — 이 파일의 대부분 셀은
// 이어쓰기 패널의 컨트롤을 조작한다. 드로어가 닫힌 기본 상태는 별도 셀이 잠근다.
function renderEditor(path = "/projects/p1/drafts/d1?panel=writing") {
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
  // Restore real timers first so a fake-timer test that throws before its own
  // cleanup cannot leak faked timers into later tests (they would hang waitFor).
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetMemberQuota();
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
    // K-4 (plans/context-budget-korean-tokens-decisions.md:655): 원고 본문에 hard maxLength 가
    // 없어야 한다 — 붙여넣기가 잘려 정본이 소리 없이 손상되는 일을 막는다(정본 보존 정책).
    // under-strict: 누가 textarea 에 maxLength 를 추가하면 이 줄이 문다.
    expect(screen.getByLabelText("원고 본문")).not.toHaveAttribute("maxlength");
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
    stubFetch(fetchMock);

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
    stubFetch(fetchMock);

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

  it("confirms dirty text before an in-app link leaves the editor", async () => {
    const confirm = vi.spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [] } },
    );

    renderEditor();
    await userEvent.type(await screen.findByLabelText("원고 본문"), "미저장 본문");
    const back = screen.getByRole("link", { name: "← 원고 목록으로 돌아가기" });

    await userEvent.click(back);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("원고 본문")).toHaveValue("미저장 본문");

    await userEvent.click(back);
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("원고 목록")).toBeInTheDocument();
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
    stubFetch(fetchMock);

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

  // C1 Writing panel wiring: DraftEditor derives the D1=A gating props (dirty /
  // onLatest / hasVersions / readOnly) and reloads after an accept. The Writing
  // flow itself is unit-locked in WritingPanel.test.tsx; these two lock the seam.
  it("derives the dirty block for the Writing panel from editor state", async () => {
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존 본문") },
    );
    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    // clean latest → Writing available (no block, generate present).
    expect(
      screen.queryByText("저장하지 않은 변경 사항이 있습니다."),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이어쓰기 생성" })).toBeInTheDocument();
    await userEvent.type(editor, "!");
    // dirty → block with reason + resolution, generate disabled.
    expect(screen.getByText("저장하지 않은 변경 사항이 있습니다.")).toBeInTheDocument();
    expect(
      screen.getByText("현재 변경을 먼저 저장한 뒤 이어쓰기를 생성하세요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이어쓰기 생성" })).toBeDisabled();
  });

  it("reloads the editor to the new latest after a Writing candidate is accepted", async () => {
    const randomUUID = vi.fn()
      .mockReturnValueOnce("req-1")
      .mockReturnValueOnce("accept-1");
    vi.stubGlobal("crypto", { randomUUID });
    const version4 = { ...version1, id: "v4", version_number: 4, snapshot_id: "s4" };
    const candidate = {
      request_id: "req-1", project_id: "p1", task_type: "continue_scene",
      output_type: "draft_patch", text: "아린은 도시로 들어섰다.", status: "candidate",
      self_reported_constraints: [], candidate_claims: [], new_memory_hints: [],
      risk_notes: [], candidate_id: null, generated_by_model: "fake-writer",
    };
    const gatePass = {
      request_id: "req-1", project_id: "p1", decision: "pass", findings: [],
      checked_constraints: [], evaluated_by_model: "fake-gate",
    };
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존.") },
      { body: candidate },
      { body: gatePass },
      {
        body: {
          accepted: true, gate: gatePass,
          saved: { draft_version_id: "v4", version_number: 4, snapshot_id: "s4", content_hash: "h4" },
          analysis_job: { id: "j1", project_id: "p1", snapshot_id: "s4", status: "pending", failure_reason: null, failure_detail: null },
          idempotent_replay: false,
        },
      },
      { body: { versions: [version1, version4] } },
      { body: detail(version4, "기존.\n\n아린은 도시로 들어섰다.") },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(screen.getByRole("button", { name: "이어쓰기 생성" }));
    await userEvent.click(await screen.findByRole("button", { name: "채택하고 저장" }));

    // The editor reloaded to the new latest saved by accept.
    await waitFor(() =>
      expect(screen.getByLabelText("원고 본문")).toHaveValue("기존.\n\n아린은 도시로 들어섰다."),
    );
    expect(screen.getByText("현재 version 4")).toBeInTheDocument();
    expect(fetchMock.mock.calls[6][0]).toBe("/api/projects/p1/writing/accept");
    expect(fetchMock.mock.calls[7][0]).toBe("/api/projects/p1/drafts/d1/versions");
  });

  it("reloads the editor to the new latest after a PAD item is accepted (패드 채택 배선)", async () => {
    // Same seam as the WritingPanel accept above, driven from the recovery
    // pad: an async-generated candidate living in scratch is 채택'd there, and
    // the editor must reload the saved version (scratchRefresh + reloadLatest).
    seedMemberQuota({
      remaining: 7, unlimited: false, status: "active",
      daily: { limit: 20, used: 13, remaining: 7, resets_at: null },
      weekly: { limit: 100, used: 41, remaining: 59, resets_at: null },
    } as never);
    const version4 = { ...version1, id: "v4", version_number: 4, snapshot_id: "s4" };
    const padItem = {
      id: "wds:1", draft_id: "d1", request_id: "wr1",
      task_type: "continue_scene", output_type: "draft_patch",
      instruction: "이어서", candidate_text: "복구된 문단.",
      intent: null, version_id: "v1", created_at: "2026-07-20T00:00:00Z",
    };
    const acceptBody = {
      accepted: true,
      gate: {
        request_id: "wr1", project_id: "p1", decision: "pass", findings: [],
        checked_constraints: [], evaluated_by_model: "fake-gate",
      },
      saved: {
        draft_version_id: "v4", version_number: 4, snapshot_id: "s4",
        content_hash: "h4",
      },
      analysis_job: {
        id: "j1", project_id: "p1", snapshot_id: "s4", status: "pending",
        failure_reason: null, failure_detail: null,
      },
      idempotent_replay: false,
    };
    const fetchMock = vi.fn();
    for (const next of [
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존.") },
      { body: acceptBody },
      { body: { versions: [version1, version4] } },
      { body: detail(version4, "기존.\n\n복구된 문단.") },
    ]) {
      fetchMock.mockResolvedValueOnce(response(next));
    }
    // Local stub: the scratch LIST (GET) serves the pad item — the file-level
    // stubFetch always answers empty, which this test must override.
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (
        typeof url === "string" && url.includes("/writing/scratch") &&
        init?.method !== "DELETE"
      ) {
        return Promise.resolve(
          response({ body: { project_id: "p1", draft_id: "d1", items: [padItem] } }),
        );
      }
      if (typeof url === "string" && url.includes("/writing/budget")) {
        return Promise.resolve(
          response({
            body: {
              project_id: "p1",
              context_budget_tokens: { short: 8192, medium: 8192, long: 8192 },
            },
          }),
        );
      }
      return fetchMock(url, init);
    });

    renderEditor();
    await screen.findByText("복구된 문단.");
    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    // The editor reloaded to the version the pad accept saved.
    await waitFor(() =>
      expect(screen.getByLabelText("원고 본문")).toHaveValue(
        "기존.\n\n복구된 문단.",
      ),
    );
    expect(screen.getByText("현재 version 4")).toBeInTheDocument();
    const acceptCall = fetchMock.mock.calls.find(
      ([url]) => String(url).endsWith("/writing/accept"),
    );
    expect(acceptCall?.[0]).toBe("/api/projects/p1/writing/accept");
  });

  it("confirms before an accept discards unsaved editor edits, and cancel keeps them (미저장 편집 결손 fix)", async () => {
    // The candidate is generated on a clean latest; the author then types into the
    // editor (dirty) before accepting. Accept saves base+candidate and reloadLatest
    // overwrites the editor with it — silently dropping those edits. The guard
    // confirms first; cancel must abort the save AND preserve the typed text.
    const randomUUID = vi.fn()
      .mockReturnValueOnce("req-1")
      .mockReturnValueOnce("accept-1");
    vi.stubGlobal("crypto", { randomUUID });
    const candidate = {
      request_id: "req-1", project_id: "p1", task_type: "continue_scene",
      output_type: "draft_patch", text: "아린은 도시로 들어섰다.", status: "candidate",
      self_reported_constraints: [], candidate_claims: [], new_memory_hints: [],
      risk_notes: [], candidate_id: null, generated_by_model: "fake-writer",
    };
    const gatePass = {
      request_id: "req-1", project_id: "p1", decision: "pass", findings: [],
      checked_constraints: [], evaluated_by_model: "fake-gate",
    };
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존.") },
      { body: candidate },
      { body: gatePass },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(screen.getByRole("button", { name: "이어쓰기 생성" }));
    await screen.findByRole("button", { name: "채택하고 저장" });

    // Author types unsaved edits into the editor after the candidate appears.
    const kept = "기존. 손으로 이어쓴 미저장 문장";
    fireEvent.change(screen.getByLabelText("원고 본문"), { target: { value: kept } });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "채택하고 저장" }));

    // Cancel: nothing saved (still 6 fetches) and the unsaved edits survive.
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(6); // load(4) + generate + gate; no accept
    expect(screen.getByLabelText("원고 본문")).toHaveValue(kept);
    expect(screen.getByText(candidate.text)).toBeInTheDocument(); // candidate still offered
  });

  it("confirming the discard proceeds: accept saves and the editor reloads to the new latest (미저장 편집 결손 fix, proceed 사슬)", async () => {
    // The proceed direction of the same guard, driven end-to-end: dirty editor +
    // confirm=true must run accept AND let reloadLatest overwrite the typed text
    // with base+candidate (the consented discard). Locks onAccepted→reloadLatest→
    // setRawText integration, not just WritingPanel's onAccepted call.
    const randomUUID = vi.fn()
      .mockReturnValueOnce("req-1")
      .mockReturnValueOnce("accept-1");
    vi.stubGlobal("crypto", { randomUUID });
    const version4 = { ...version1, id: "v4", version_number: 4, snapshot_id: "s4" };
    const candidate = {
      request_id: "req-1", project_id: "p1", task_type: "continue_scene",
      output_type: "draft_patch", text: "아린은 도시로 들어섰다.", status: "candidate",
      self_reported_constraints: [], candidate_claims: [], new_memory_hints: [],
      risk_notes: [], candidate_id: null, generated_by_model: "fake-writer",
    };
    const gatePass = {
      request_id: "req-1", project_id: "p1", decision: "pass", findings: [],
      checked_constraints: [], evaluated_by_model: "fake-gate",
    };
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존.") },
      { body: candidate },
      { body: gatePass },
      {
        body: {
          accepted: true, gate: gatePass,
          saved: { draft_version_id: "v4", version_number: 4, snapshot_id: "s4", content_hash: "h4" },
          analysis_job: { id: "j1", project_id: "p1", snapshot_id: "s4", status: "pending", failure_reason: null, failure_detail: null },
          idempotent_replay: false,
        },
      },
      { body: { versions: [version1, version4] } },
      { body: detail(version4, "기존.\n\n아린은 도시로 들어섰다.") },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(screen.getByRole("button", { name: "이어쓰기 생성" }));
    await screen.findByRole("button", { name: "채택하고 저장" });

    fireEvent.change(screen.getByLabelText("원고 본문"), {
      target: { value: "기존. 채택하며 버릴 미저장 문장" },
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "채택하고 저장" }));

    // Confirmed discard: accept saved, and the editor reloaded to base+candidate
    // (the typed text is intentionally gone — the user consented).
    await waitFor(() =>
      expect(screen.getByLabelText("원고 본문")).toHaveValue("기존.\n\n아린은 도시로 들어섰다."),
    );
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[6][0]).toBe("/api/projects/p1/writing/accept");
    expect(screen.getByText("현재 version 4")).toBeInTheDocument();
  });

  // 증분 3 (D6): a medium/long generate returns a 202 job that the editor tracks
  // and polls. The in-progress state renders in the pad; on completion the worker
  // result surfaces via the scratch list.
  const asyncJob = {
    job_id: "wgj-1", request_id: "req-1", project_id: "p1", draft_id: "d1",
    version_id: "v1", task_type: "continue_scene", output_length: "medium",
    status: "pending", created_at: "2026-07-22T00:00:00Z",
    result_scratch_id: null, failure_reason: null, failure_detail: null,
  };
  const scratchResult = {
    id: "sc-1", draft_id: "d1", request_id: "req-1", task_type: "continue_scene",
    output_type: "draft_patch", instruction: "이어서 써줘",
    candidate_text: "백그라운드로 완성한 긴 산문입니다.", intent: "append_current",
    version_id: "v1", created_at: "2026-07-22T00:00:00Z",
  };

  // Routes the async-pad flow by URL so timer-driven polling can be observed.
  // `state.jobStatus` advances pending → succeeded between polls, and the scratch
  // list returns the worker's result only once the job has succeeded.
  function routeAsyncPad(state: { jobStatus: string }) {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/writing/scratch")) {
        const items = state.jobStatus === "succeeded" ? [scratchResult] : [];
        return Promise.resolve(
          response({ body: { project_id: "p1", draft_id: "d1", items } }),
        );
      }
      if (url.includes("/retry")) {
        // Retry POST (재시도 슬라이스): the server resets a FAILED job to PENDING
        // (failure fields cleared), so polling resumes. Must be matched BEFORE the
        // GET poll branch — the retry URL also contains /generation-jobs/.
        return Promise.resolve(
          response({
            body: {
              ...asyncJob,
              status: "pending",
              failure_reason: null,
              failure_detail: null,
            },
          }),
        );
      }
      if (url.includes("/writing/generation-jobs/")) {
        return Promise.resolve(
          response({
            body: {
              ...asyncJob,
              status: state.jobStatus,
              result_scratch_id: state.jobStatus === "succeeded" ? "sc-1" : null,
            },
          }),
        );
      }
      if (url.includes("/writing/generate")) {
        return Promise.resolve(
          response({ status: 202, body: { idempotent_replay: false, job: asyncJob } }),
        );
      }
      if (url === "/api/projects/p1") return Promise.resolve(response({ body: project }));
      if (url === "/api/projects/p1/drafts/d1") return Promise.resolve(response({ body: draft }));
      if (url.endsWith("/drafts/d1/versions")) {
        return Promise.resolve(response({ body: { versions: [version1] } }));
      }
      if (url.includes("/versions/v1")) {
        return Promise.resolve(response({ body: detail(version1, "기존.") }));
      }
      if (url.includes("/analysis/review-inbox")) {
        return Promise.resolve(
          response({ body: { project_id: "p1", items: [], gate_findings: [] } }),
        );
      }
      return Promise.reject(new Error(`unexpected ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  // Fake timers drive the 5s poll. userEvent deadlocks under fake timers even with
  // delay:null, so inputs use timer-free fireEvent and a multi-round pump flushes
  // the fetch promise chains. Plain getBy queries are used throughout, since
  // findBy/waitFor advance timers themselves and would fight the 5s interval.
  async function pump(ms = 0) {
    for (let round = 0; round < 6; round += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    }
  }

  async function startAsyncGenerate() {
    renderEditor();
    await pump();
    fireEvent.change(screen.getByLabelText("이어쓰기 지시"), {
      target: { value: "이어서 써줘" },
    });
    fireEvent.change(screen.getByLabelText("생성 분량"), {
      target: { value: "medium" },
    });
    fireEvent.click(screen.getByRole("button", { name: "이어쓰기 생성" }));
    await pump();
  }

  const jobPolls = (fetchMock: ReturnType<typeof vi.fn>) =>
    fetchMock.mock.calls.filter(
      (call) => typeof call[0] === "string" && call[0].includes("/generation-jobs/"),
    ).length;

  it("tracks an async generate and surfaces its result in the pad on completion (증분 3)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("crypto", { randomUUID: () => "req-1" });
    const state = { jobStatus: "running" };
    const fetchMock = routeAsyncPad(state);

    await startAsyncGenerate();

    // The started job shows as in-progress in the pad (no result yet).
    expect(screen.getByText(/백그라운드 생성 1건 진행 중/)).toBeInTheDocument();
    expect(screen.queryByText(scratchResult.candidate_text)).not.toBeInTheDocument();
    const pollsBefore = jobPolls(fetchMock);

    // Worker finished: the next poll (5s) sees succeeded → pad refreshes from scratch.
    state.jobStatus = "succeeded";
    await pump(5000);

    expect(screen.getByText(scratchResult.candidate_text)).toBeInTheDocument();
    expect(screen.queryByText(/진행 중/)).not.toBeInTheDocument();
    expect(jobPolls(fetchMock)).toBeGreaterThan(pollsBefore); // it actually polled

    // Under-strict guard: a settled job must stop polling (no further job fetches).
    const pollsAfter = jobPolls(fetchMock);
    await pump(10000);
    expect(jobPolls(fetchMock)).toBe(pollsAfter);
    vi.useRealTimers();
  });

  it("lights the writing-tab completion badge when a job finishes off-tab, and clears it on return (증분 3)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("crypto", { randomUUID: () => "req-1" });
    const state = { jobStatus: "running" };
    routeAsyncPad(state);

    await startAsyncGenerate();
    expect(screen.getByText(/백그라운드 생성 1건 진행 중/)).toBeInTheDocument();

    // Leave the writing tab, then let the job finish while away.
    fireEvent.click(screen.getByRole("tab", { name: "검토" }));
    await pump();
    state.jobStatus = "succeeded";
    await pump(5000);

    // The completion badge appears on the writing tab (author is elsewhere).
    const writingTab = screen.getByRole("tab", { name: /이어쓰기/ });
    expect(
      within(writingTab).getByLabelText("백그라운드 생성 완료 1건"),
    ).toBeInTheDocument();

    // Returning to the writing tab acknowledges (clears) the badge.
    fireEvent.click(writingTab);
    await pump();
    expect(
      within(screen.getByRole("tab", { name: /이어쓰기/ })).queryByLabelText(
        "백그라운드 생성 완료 1건",
      ),
    ).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  // Regression (dogfood 결손 — 우측 레일 탭 레이어화, commit eb304ed): leaving the
  // writing tab and returning must PRESERVE the WritingPanel's local input state
  // (이어쓰기 지시 등은 컴포넌트 로컬 useState). Before the fix the rail rendered the
  // panel conditionally (`activePanel === "writing" && …`), so switching tabs
  // unmounted it and the typed instruction was silently lost on return.
  //   - under-strict guard: revert to conditional rendering → the panel remounts
  //     fresh on return → the field reads "" → this test re-fails.
  //   - the mid-switch "이 원고 분석" assertion pins that the tab actually changed,
  //     so a no-op tab switch (over-correction) cannot pass this trivially.
  it("preserves the Writing panel instruction input across a tab switch (탭 전환 state 유지)", async () => {
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존 본문") },
    );
    renderEditor();
    await screen.findByLabelText("원고 본문");

    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    expect(screen.getByLabelText("이어쓰기 지시")).toHaveValue("이어서 써줘");

    // Leave for the analysis tab (its trigger button proves the switch happened),
    // then return to the writing tab.
    await userEvent.click(screen.getByRole("tab", { name: "분석" }));
    expect(screen.getByRole("button", { name: "이 원고 분석" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /이어쓰기/ }));

    // The typed instruction survived the round-trip (the layer stayed mounted).
    expect(screen.getByLabelText("이어쓰기 지시")).toHaveValue("이어서 써줘");
  });

  // ── 오버레이 드로어(2026-08-26) ─────────────────────────────────────────────
  // 기본은 닫힘 — panel param 이 있을 때만 열린다. 닫힘 상태의 a11y 트리 가림과
  // 마운트 유지 인바리언트를 양방향으로 잠근다.

  it("hides the rail drawer from the a11y tree until a tab opens it (드로어 기본 닫힘)", async () => {
    // under-strict: no panel param → the drawer content (writing controls) is
    // aria-hidden — the dock tabs are the only reachable surface.
    // over-strict: a dock tab click must open the drawer and reveal the panel
    // (a permanently hidden drawer cannot pass).
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존 본문") },
    );
    renderEditor("/projects/p1/drafts/d1");
    await screen.findByLabelText("원고 본문");

    expect(screen.getByRole("tablist", { name: "집필 도구 선택" })).toBeInTheDocument();
    // Role queries respect aria-hidden (the a11y contract the drawer closes
    // under); label queries don't, so the hidden state is asserted by role.
    expect(
      screen.queryByRole("button", { name: "이어쓰기 생성" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("집필 도구")).toHaveAttribute(
      "aria-hidden",
      "true",
    );

    await userEvent.click(screen.getByRole("tab", { name: /이어쓰기/ }));
    expect(await screen.findByLabelText("이어쓰기 지시")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이어쓰기 생성" })).toBeInTheDocument();
  });

  it("closes the drawer (and review params) on ✕ and Esc, leaving the editor usable", async () => {
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존 본문") },
    );
    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1");
    await screen.findByLabelText("원고 본문");
    expect(screen.getByRole("button", { name: "패널 닫기" })).toBeInTheDocument();

    // ✕ closes and drops the review deep-link params with the panel param.
    await userEvent.click(screen.getByRole("button", { name: "패널 닫기" }));
    expect(screen.queryByRole("button", { name: "패널 닫기" })).not.toBeInTheDocument();
    expect(window.location.search).toBe("");

    // Reopen, then Esc closes too — and the editor underneath stays usable.
    await userEvent.click(screen.getByRole("tab", { name: /이어쓰기/ }));
    expect(screen.getByRole("button", { name: "이어쓰기 생성" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("원고 본문"), "!");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(
      screen.queryByRole("button", { name: "이어쓰기 생성" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("원고 본문")).toHaveValue("기존 본문!");
  });

  it("keeps the completion badge lit while the drawer is closed, clearing it only when the writing tab is open (드로어 배지 회귀 방어)", async () => {
    // over-strict: pre-drawer code acknowledged on activePanel === "writing"
    // alone — with the drawer closed that default would clear the badge while
    // the pad is invisible. The badge must survive a closed drawer and clear
    // only on an OPEN writing tab.
    vi.useFakeTimers();
    vi.stubGlobal("crypto", { randomUUID: () => "req-1" });
    const state = { jobStatus: "running" };
    routeAsyncPad(state);

    // Start from the CLOSED drawer (the default path routes writing tab, so
    // drive it explicitly closed).
    renderEditor("/projects/p1/drafts/d1");
    await pump();
    fireEvent.change(screen.getByLabelText("이어쓰기 지시"), {
      target: { value: "이어서 써줘" },
    });
    // Drawer closed → the generate control is unreachable; open writing first,
    // generate, then CLOSE the drawer while the job runs.
    fireEvent.click(screen.getByRole("tab", { name: /이어쓰기/ }));
    fireEvent.change(screen.getByLabelText("생성 분량"), {
      target: { value: "medium" },
    });
    fireEvent.click(screen.getByRole("button", { name: "이어쓰기 생성" }));
    await pump();
    expect(screen.getByText(/백그라운드 생성 1건 진행 중/)).toBeInTheDocument();

    // Finish the job with the drawer CLOSED.
    fireEvent.click(screen.getByRole("button", { name: "패널 닫기" }));
    state.jobStatus = "succeeded";
    await pump(5000);

    const writingTab = screen.getByRole("tab", { name: /이어쓰기/ });
    expect(
      within(writingTab).getByLabelText("백그라운드 생성 완료 1건"),
    ).toBeInTheDocument(); // still lit behind the closed drawer

    // Opening the writing tab acknowledges it.
    fireEvent.click(writingTab);
    await pump();
    expect(
      within(screen.getByRole("tab", { name: /이어쓰기/ })).queryByLabelText(
        "백그라운드 생성 완료 1건",
      ),
    ).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("preserves the Writing panel instruction across drawer close/reopen (드로어 마운트 유지)", async () => {
    // Same invariant as the tab-switch cell above, driven by the drawer: the
    // panels stay mounted while the drawer is closed.
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "기존 본문") },
    );
    renderEditor();
    await screen.findByLabelText("원고 본문");

    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(screen.getByRole("button", { name: "패널 닫기" }));
    expect(
      screen.queryByRole("button", { name: "이어쓰기 생성" }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /이어쓰기/ }));
    expect(screen.getByLabelText("이어쓰기 지시")).toHaveValue("이어서 써줘");
  });

  it("retries a failed async job end-to-end: failure → 다시 시도 → poll resumes → result (재시도 슬라이스 보강)", async () => {
    // End-to-end wiring the unit tests can't reach: the pad's "다시 시도" button
    // is wired through DraftEditor into the hook, and retrying a FAILED job resets
    // it to PENDING (polling resumes) so the worker's re-run surfaces the result.
    vi.useFakeTimers();
    vi.stubGlobal("crypto", { randomUUID: () => "req-1" });
    const state = { jobStatus: "failed" }; // the first 5s poll sees a failure
    const fetchMock = routeAsyncPad(state);

    await startAsyncGenerate();
    await pump(5000); // poll → FAILED → pad shows the failure row + retry button

    expect(screen.getByRole("alert")).toBeInTheDocument(); // failure surfaced
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    const pollsBeforeRetry = jobPolls(fetchMock);

    // Author retries. The POST .../retry fires, the server resets to PENDING, so
    // polling resumes; the worker's re-run is seen on the next poll → result.
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    state.jobStatus = "succeeded";
    await pump(5000);

    expect(
      fetchMock.mock.calls.some(
        (call) => typeof call[0] === "string" && call[0].includes("/retry"),
      ),
    ).toBe(true); // the retry button actually hit the retry endpoint
    expect(jobPolls(fetchMock)).toBeGreaterThan(pollsBeforeRetry); // polling resumed
    expect(screen.getByText(scratchResult.candidate_text)).toBeInTheDocument(); // result
    vi.useRealTimers();
  });

  it("renders and updates the save, analysis, and pending-review status bar", async () => {
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "본문") },
      { body: { source_refs: [{ start_offset: 0, end_offset: 2 }] } },
      {
        body: {
          ...detail(version1, "본문"),
          blocks: [{ start_offset: 0, end_offset: 2, kind: "paragraph" }],
        },
      },
      { body: { job: { id: "j1", status: "pending" }, idempotent_replay: false } },
      { body: { job: { id: "j1", status: "succeeded" }, candidates: [] } },
      {
        body: {
          project_id: "p1",
          items: [{
            candidate_id: "c1", job_id: "j1", candidate_type: "event_observation",
            status: "needs_review", confidence: 0.8, provenance: "ai_inferred",
            conflict_count: 0, actions: [],
          }],
          gate_findings: [{
            id: "g1", origin: "context_gate", status: "open", check: "stale_item",
            detail: "stale", query: "q", purpose: "p", needs: [], pointer_ids: [], actions: [],
          }],
        },
      },
    );

    renderEditor();

    const status = await screen.findByLabelText("작업 상태");
    expect(within(status).getByText("저장됨")).toBeInTheDocument();
    expect(within(status).getByText("분석 미실행")).toBeInTheDocument();
    expect(within(status).getByText("검토 대기 —")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("원고 본문"), "!");
    expect(within(status).getByText("저장 안 됨")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("원고 본문"));
    await userEvent.type(screen.getByLabelText("원고 본문"), "본문");

    await userEvent.click(screen.getByRole("tab", { name: "분석" }));
    await userEvent.click(screen.getByRole("button", { name: "이 원고 분석" }));
    expect(await within(status).findByText("분석 완료")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "검토" }));
    expect(await within(status).findByText("검토 대기 2건")).toBeInTheDocument();
  });

  it("restores a historical source by exact snapshot and code-point offsets", async () => {
    const reviewItem = {
      candidate_id: "c1", job_id: "j1", candidate_type: "character_observation",
      status: "needs_review", confidence: 0.9, provenance: "ai_inferred",
      conflict_count: 0,
      actions: [
        { action: "confirm", eligible: true, reason: null },
        { action: "reject", eligible: true, reason: null },
      ],
    };
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3, version1] } },
      { body: detail(version3, "최신 본문") },
      { body: { project_id: "p1", items: [reviewItem], gate_findings: [] } },
      {
        body: {
          ...reviewItem,
          payload: { name: "민아", observation: "근거를 봄" },
          source_refs: [{
            source_ref_id: "sr1", status: "resolved", snapshot_id: "s1",
            block_id: "b1", start_offset: 1, end_offset: 3,
            quote: "근거", content_hash: "hash-1",
          }],
          conflicts: [],
        },
      },
      { body: detail(version1, "😀근거 끝") },
      { body: detail(version3, "최신 본문") },
    );

    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1&source=sr1");

    const editor = await screen.findByLabelText("원고 본문");
    await waitFor(() => expect(editor).toHaveValue("😀근거 끝"));
    expect(screen.getByText(/과거 version 1 근거 · 현재 최신 원고가 아님/)).toBeInTheDocument();
    // Server offsets count Unicode code points; textarea selection counts UTF-16
    // code units. The leading emoji therefore moves the browser span by one.
    //
    // ★ waitFor 인 것은 의도다(2026-08-10, 검증 §Hardening 2 의 flake 폐쇄): 선택 영역은
    // 값과 **다른 effect** 에서 적용된다(DraftEditor.tsx 의 pendingSelection effect →
    // setSelectionRange). 값이 도착한 직후 동기로 읽으면 그 effect 가 아직 안 돌았을 수
    // 있고, 과부하 전수 run 에서 실제로 1건 실패했다(단독 실행은 green). **단정은 그대로
    // 정확히 2·4 다** — 느슨하게 만든 것이 아니라 effect flush 를 기다리는 것뿐이다.
    await waitFor(() => {
      expect((editor as HTMLTextAreaElement).selectionStart).toBe(2);
      expect((editor as HTMLTextAreaElement).selectionEnd).toBe(4);
    });
    expect(fetchMock.mock.calls[6][0]).toBe(
      "/api/projects/p1/drafts/d1/versions/v1",
    );

    await userEvent.click(screen.getByRole("button", { name: "version 3" }));
    await waitFor(() => expect(editor).toHaveValue("최신 본문"));
    expect(screen.queryByText(/과거 version 1 근거/)).toBeNull();
  });

  it("confirms before replacing dirty text with a same-draft source version", async () => {
    const reviewItem = {
      candidate_id: "c1", job_id: "j1", candidate_type: "event_observation",
      status: "needs_review", confidence: 0.7, provenance: "ai_inferred",
      conflict_count: 0, actions: [],
    };
    const confirm = vi.spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3, version1] } },
      { body: detail(version3, "최신 본문") },
      { body: { project_id: "p1", items: [reviewItem], gate_findings: [] } },
      {
        body: {
          ...reviewItem, payload: { event: "과거 사건" }, conflicts: [],
          source_refs: [{
            source_ref_id: "sr1", status: "resolved", snapshot_id: "s1",
            block_id: "b1", start_offset: 0, end_offset: 2,
            quote: "과거", content_hash: "hash-1",
          }],
        },
      },
      { body: detail(version1, "과거 본문") },
    );

    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1");
    const editor = await screen.findByLabelText("원고 본문");
    await userEvent.type(editor, "!");
    const sourceButton = await screen.findByRole("button", { name: /원고에서 보기/ });

    await userEvent.click(sourceButton);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(editor).toHaveValue("최신 본문!");
    expect(fetchMock).toHaveBeenCalledTimes(6);

    await userEvent.click(sourceButton);
    await waitFor(() => expect(editor).toHaveValue("과거 본문"));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[6][0]).toBe(
      "/api/projects/p1/drafts/d1/versions/v1",
    );
  });

  it("reports a source snapshot that no project draft version owns", async () => {
    const reviewItem = {
      candidate_id: "c1", job_id: "j1", candidate_type: "event_observation",
      status: "needs_review", confidence: 0.7, provenance: "ai_inferred",
      conflict_count: 0, actions: [],
    };
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3] } },
      { body: detail(version3, "최신 본문") },
      { body: { project_id: "p1", items: [reviewItem], gate_findings: [] } },
      {
        body: {
          ...reviewItem, payload: { event: "유실 근거" }, conflicts: [],
          source_refs: [{
            source_ref_id: "missing", status: "resolved", snapshot_id: "missing-snapshot",
            block_id: "b1", start_offset: 0, end_offset: 2,
            quote: "유실", content_hash: "missing-hash",
          }],
        },
      },
      { body: { drafts: [draft] } },
    );

    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1&source=missing");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "이 근거가 가리키는 원고 version을 찾을 수 없습니다.",
    );
    expect(screen.getByLabelText("원고 본문")).toHaveValue("최신 본문");
  });

  it.each([
    ["quote", { quote: "틀린 인용", content_hash: "hash-1" }],
    ["content hash", { quote: "과거", content_hash: "wrong-hash" }],
  ])("rejects a source whose %s does not match the immutable version", async (_label, mismatch) => {
    const reviewItem = {
      candidate_id: "c1", job_id: "j1", candidate_type: "event_observation",
      status: "needs_review", confidence: 0.7, provenance: "ai_inferred",
      conflict_count: 0, actions: [],
    };
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3, version1] } },
      { body: detail(version3, "최신 본문") },
      { body: { project_id: "p1", items: [reviewItem], gate_findings: [] } },
      {
        body: {
          ...reviewItem, payload: { event: "과거 사건" }, conflicts: [],
          source_refs: [{
            source_ref_id: "sr1", status: "resolved", snapshot_id: "s1",
            block_id: "b1", start_offset: 0, end_offset: 2,
            ...mismatch,
          }],
        },
      },
      { body: detail(version1, "과거 본문") },
    );

    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1&source=sr1");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "근거의 offset 또는 내용이 저장된 version과 일치하지 않습니다.",
    );
    expect(screen.getByLabelText("원고 본문")).toHaveValue("최신 본문");
    expect(screen.queryByText(/과거 version 1 근거/)).toBeNull();
  });

  it("keeps latest source evidence labeled latest instead of marking it stale", async () => {
    const reviewItem = {
      candidate_id: "c1", job_id: "j1", candidate_type: "event_observation",
      status: "needs_review", confidence: 0.7, provenance: "ai_inferred",
      conflict_count: 0, actions: [],
    };
    const fetchMock = mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version3, version1] } },
      { body: detail(version3, "최신 본문") },
      { body: { project_id: "p1", items: [reviewItem], gate_findings: [] } },
      {
        body: {
          ...reviewItem, payload: { event: "최신 사건" }, conflicts: [],
          source_refs: [{
            source_ref_id: "sr3", status: "resolved", snapshot_id: "s3",
            block_id: "b3", start_offset: 0, end_offset: 2,
            quote: "최신", content_hash: "hash-3",
          }],
        },
      },
    );

    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c1&source=sr3");

    expect(await screen.findByText(/최신 version 3 근거 · 선택 영역 0–2/)).toBeInTheDocument();
    expect(screen.queryByText(/현재 최신 원고가 아님/)).toBeNull();
    // The already-open exact snapshot is selected in place; no version refetch.
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("follows a source snapshot into another draft and restores the exact selection", async () => {
    const otherDraft = { ...draft, id: "d2", title: "둘째 장면" };
    const otherVersion = {
      ...version1,
      id: "v2",
      draft_id: "d2",
      version_number: 2,
      snapshot_id: "s2",
    };
    const reviewItem = {
      candidate_id: "c2", job_id: "j2", candidate_type: "event_observation",
      status: "needs_review", confidence: 0.8, provenance: "ai_inferred",
      conflict_count: 0, actions: [],
    };
    const reviewDetail = {
      ...reviewItem, payload: { event: "타 원고 사건" }, conflicts: [],
      source_refs: [{
        source_ref_id: "sr2", status: "resolved", snapshot_id: "s2",
        block_id: "b2", start_offset: 0, end_offset: 2,
        quote: "둘째", content_hash: "hash-2",
      }],
    };
    const fetchMock = vi.fn(async (input: string) => {
      const bodies: Record<string, unknown> = {
        "/api/projects/p1": project,
        "/api/projects/p1/drafts": { drafts: [draft, otherDraft] },
        "/api/projects/p1/drafts/d1": draft,
        "/api/projects/p1/drafts/d2": otherDraft,
        "/api/projects/p1/drafts/d1/versions": { versions: [version3] },
        "/api/projects/p1/drafts/d2/versions": { versions: [otherVersion] },
        "/api/projects/p1/drafts/d1/versions/v3": detail(version3, "첫 원고"),
        "/api/projects/p1/drafts/d2/versions/v2": {
          ...detail(otherVersion, "둘째 원고"),
          snapshot: {
            ...detail(otherVersion, "둘째 원고").snapshot,
            draft_id: "d2",
          },
        },
        "/api/projects/p1/analysis/review-inbox": {
          project_id: "p1", items: [reviewItem], gate_findings: [],
        },
        "/api/projects/p1/analysis/review-inbox/c2": reviewDetail,
      };
      return response({ body: bodies[input] });
    });
    stubFetch(fetchMock);

    const confirm = vi.spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    renderEditor("/projects/p1/drafts/d1?panel=review&candidate=c2");

    const editor = await screen.findByLabelText("원고 본문") as HTMLTextAreaElement;
    await userEvent.type(editor, "미저장");
    const sourceButton = await screen.findByRole("button", { name: /원고에서 보기/ });
    await userEvent.click(sourceButton);
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("heading", { name: "첫 장면" })).toBeInTheDocument();
    expect(editor).toHaveValue("첫 원고미저장");

    await userEvent.click(sourceButton);
    expect(await screen.findByRole("heading", { name: "둘째 장면" })).toBeInTheDocument();
    const targetEditor = screen.getByLabelText("원고 본문") as HTMLTextAreaElement;
    await waitFor(() => expect(targetEditor).toHaveValue("둘째 원고"));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/최신 version 2 근거 · 선택 영역 0–2/)).toBeInTheDocument();
    // 같은 effect 경쟁(위 주석) — 패턴 스윕으로 찾은 두 번째 자리다.
    await waitFor(() => {
      expect(targetEditor.selectionStart).toBe(0);
      expect(targetEditor.selectionEnd).toBe(2);
    });
    expect(fetchMock.mock.calls.map(([url]) => url)).toContain(
      "/api/projects/p1/drafts",
    );
  });
});

describe("저장 기록 접기 (오너 2026-08-27 dogfood)", () => {
  /** version N 개를 최신순으로 만든다(자세한 필드는 위 픽스처를 따른다). */
  function manyVersions(count: number) {
    return Array.from({ length: count }, (_, index) => ({
      ...version1,
      id: `v${index + 1}`,
      version_number: index + 1,
      snapshot_id: `s${index + 1}`,
    }));
  }

  it("keeps the newest five in hand and folds the rest away", async () => {
    // under-strict: 다시 전부 펼치면 최신 목록이 8개가 되어 재실패한다 —
    // 저장할수록 버튼이 끝없이 늘어나던 그 상태다.
    // over-strict: **목록을 잘라서** 줄이는 과대교정도 실패한다. 접힘 안에
    // 나머지 셋이 그대로 있어야 하고, 옛 version 은 여전히 고를 수 있어야 한다.
    const all = manyVersions(8);
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: all } },
      { body: detail(all[7], "여덟째 원고") },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");

    const recent = screen.getByRole("list", { name: "버전 기록" });
    expect(within(recent).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "version 8", "version 7", "version 6", "version 5", "version 4",
    ]);

    const older = screen.getByRole("list", { name: "이전 버전 기록" });
    expect(within(older).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "version 3", "version 2", "version 1",
    ]);
    expect(screen.getByText("이전 version 3개 더 보기")).toBeInTheDocument();
    expect(older.closest("details")).not.toHaveAttribute("open");
  });

  it("does not fold at all when there are five or fewer", async () => {
    const all = manyVersions(5);
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: all } },
      { body: detail(all[4], "다섯째 원고") },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");

    expect(within(screen.getByRole("list", { name: "버전 기록" }))
      .getAllByRole("button")).toHaveLength(5);
    expect(screen.queryByText(/이전 version/)).toBeNull();
  });

  it("opens the fold when the version being viewed lives inside it", async () => {
    // 무엇을 보고 있는지가 화면에서 사라지면 안 된다 — 옛 version 을 고르면
    // 그 자리가 열린 채로 있어야 한다.
    const all = manyVersions(8);
    mockFetch(
      { body: project }, { body: draft }, { body: { versions: all } },
      { body: detail(all[7], "여덟째 원고") },
      { body: detail(all[0], "첫 원고") },
    );

    renderEditor();
    await screen.findByLabelText("원고 본문");
    await userEvent.click(screen.getByRole("button", { name: "version 1" }));

    await waitFor(() =>
      expect(screen.getByLabelText("원고 본문")).toHaveValue("첫 원고"));
    const older = screen.getByRole("list", { name: "이전 버전 기록" });
    expect(older.closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("button", { name: "version 1" }))
      .toHaveAttribute("aria-current", "true");
  });
});

describe("본문 4000자 상한 (D5-2, 오너 2026-08-27)", () => {
  // ★ 시행 방식: **경고 + 저장 차단**이지 잘라내기가 아니다 — textarea maxLength 는
  // 붙여넣기를 몰래 잘라 정본을 손상시키므로 금지다(위 "opens a zero-version" 셀이
  // no-maxlength 를 잠근다). 서버가 최후 방어(저장 422·accept 400)다.

  it("warns as the body approaches the limit", async () => {
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "가".repeat(3_900)) },
    );

    renderEditor();

    const counter = await screen.findByText(/3,900자/);
    expect(counter).toHaveClass("limit-near");
    expect(counter).toHaveTextContent("상한 4,000자 임박");
  });

  it("keeps save disabled for a body already past the limit", async () => {
    // 상한 이전에 저장된 긴 본문을 불러온 레거시 케이스. dirty 여부와 무관하게
    // overLimit 이 저장을 막는다 — 고쳐도 여전히 상한 위면 저장 버튼은 잠긴 채다.
    mockFetch(
      { body: project },
      { body: draft },
      { body: { versions: [version1] } },
      { body: detail(version1, "가".repeat(4_100)) },
    );

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    const counter = await screen.findByText(/4,100자/);
    expect(counter).toHaveClass("limit-over");
    expect(counter).toHaveTextContent("상한 4,000자 초과 — 저장할 수 없습니다");

    await userEvent.type(editor, "다");
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("blocks saving a freshly typed body that passes the limit", async () => {
    // under 방향 앵커: overLimit 차단을 지우면 이 셀이 재실패한다. fireEvent.change 로
    // 4001자를 한 번에 넣는다(4001키 타이핑은 느리다).
    mockFetch({ body: project }, { body: draft }, { body: { versions: [] } });

    renderEditor();
    const editor = await screen.findByLabelText("원고 본문");
    fireEvent.change(editor, { target: { value: "가".repeat(4_001) } });

    const counter = await screen.findByText(/4,001자/);
    expect(counter).toHaveClass("limit-over");
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });
});
