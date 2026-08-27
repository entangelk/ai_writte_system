import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectExportPanel } from "./ProjectExportPanel";

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

function renderPanel() {
  return render(<ProjectExportPanel projectId="p1" />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * 원고 내보내기 (오너 2026-08-27 — 작업 공간에서 프로젝트 설정 탭으로 이관).
 *
 * 셀 본문은 `DraftList.test.tsx` 에서 그대로 옮겨 왔다 — **동작은 안 바뀌었고
 * 사는 자리만 바뀌었다**. 바뀐 것 하나는 추적 정보(manifest) 옵션이 사라진 것이고,
 * 그 자리는 아래 "추적 정보" 셀이 잠근다.
 */
describe("ProjectExportPanel", () => {
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

  const mixedDrafts = {
    drafts: [
      {
        id: "d1", project_id: "p1", title: "1장", archived: false,
        unit_kind: "chapter", position: 1,
      },
      {
        id: "d2", project_id: "p1", title: "묵은 장", archived: true,
        unit_kind: "chapter", position: 2,
      },
    ],
  };

  it("downloads the whole project as one combined file", async () => {
    const fetchMock = mockFetch(
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

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
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

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
    await userEvent.click(screen.getByRole("button", { name: "Markdown ZIP" }));

    await waitFor(() => expect(downloads).toEqual(["p1.zip"]));
    // The bundle always needs the manifest to enumerate units, then fetches each.
    const manifestCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes("manifest=true"),
    );
    expect(manifestCall).toBeDefined();
    const perUnit = fetchMock.mock.calls.filter((call) =>
      /\/drafts\/d\d\/versions\/v\d\/export/.test(String(call[0])),
    );
    expect(perUnit).toHaveLength(2);
    // Without the manifest option the zip holds only the per-unit files.
    const zip = await JSZip.loadAsync(blobs.at(-1)!);
    expect(Object.keys(zip.files).sort()).toEqual(["01-1장.md", "02-2장.md"]);
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
        json: async () => twoDrafts,
      })
      .mockReturnValueOnce(pendingExport);
    vi.stubGlobal("fetch", fetchMock);
    captureDownloads();

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
    await userEvent.click(screen.getByRole("button", { name: "TXT로 내보내기" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    // Every export button is disabled while one export is running.
    expect(screen.getByRole("button", { name: "내보내는 중…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Markdown ZIP" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Markdown ZIP" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);

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
      { body: { drafts: [] } },
    );

    renderPanel();
    await screen.findByText(/내보낼 원고가 없습니다/);

    expect(screen.queryByRole("button", { name: "TXT로 내보내기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Markdown ZIP" })).toBeNull();
  });

  it("disables export for an archived-only project until archived units are opted in", async () => {
    // Archived units are excluded by default, so an archived-only project would
    // export nothing. Offer the controls but disable them, and let the
    // "보관된 원고 포함" toggle re-enable them (its escape hatch).
    mockFetch(
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

    renderPanel();
    // 패널은 원고 목록을 그리지 않는다(그 목록은 작업 공간에 있다) — 보관 원고가
    // 있을 때만 뜨는 이 토글이 여기 앵커다.
    await screen.findByLabelText("보관된 원고 포함");

    // Buttons render but are disabled because nothing is exportable yet.
    expect(screen.getByRole("button", { name: "TXT로 내보내기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Markdown ZIP" })).toBeDisabled();
    expect(screen.getByText(/내보낼 원고가 없습니다/)).toBeInTheDocument();

    // Opting archived units in re-enables export.
    await userEvent.click(screen.getByLabelText("보관된 원고 포함"));
    expect(screen.getByRole("button", { name: "TXT로 내보내기" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Markdown ZIP" })).toBeEnabled();
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

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
    await userEvent.click(screen.getByRole("button", { name: "TXT ZIP" }));

    await waitFor(() => expect(downloads).toEqual(["p1.zip"]));
    const zip = await JSZip.loadAsync(blobs.at(-1)!);
    expect(Object.keys(zip.files).sort()).toEqual([
      // path-unsafe chars (/ : * ? " < > |) each replaced with "_"; a title that
      // sanitizes to empty (whitespace-only) falls back to the draft id; position
      // is zero-padded to two digits.
      "01-a_b_c______.txt",
      "02-draft-xyz.txt",
    ]);
  });

  it("passes include_archived when the archived toggle is on", async () => {
    const fetchMock = mockFetch(
      { body: mixedDrafts },
      {
        body: {
          format: "txt", filename: "p1.txt",
          content_type: "text/plain; charset=utf-8",
          body: "1장\n\nfirst\n\n묵은 장\n\narchived body",
          project_id: "p1", include_archived: true, manifest: null,
        },
      },
    );
    captureDownloads();

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
    // Default request excludes archived; opting in flips the query flag.
    await userEvent.click(screen.getByLabelText("보관된 원고 포함"));
    await userEvent.click(screen.getByRole("button", { name: "TXT로 내보내기" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/projects/p1/export?"),
      );
      expect(String(call?.[0])).toContain("include_archived=true");
    });
  });

  it("no longer offers the manifest, but still reads one to build the zip", async () => {
    // 오너 2026-08-27: *"추적 정보를 함께 내보내는 건 필요없을 것 같다"*.
    // under-strict: 옵션을 되살리면 첫 단정이 실패한다.
    // over-strict: **묶음이 manifest 를 읽는 것까지 지우는** 과대교정도 실패한다 —
    // 무엇이 포함되고 어느 version 인지가 거기에만 있어 그것 없이는 zip 을 채울 수
    // 없다. 사용자에게 파일을 주지 않는 것과 서버에 묻지 않는 것은 다른 일이다.
    const fetchMock = mockFetch(
      { body: twoDrafts },
      {
        body: {
          format: "txt", filename: "p1.txt",
          content_type: "text/plain; charset=utf-8",
          body: "1장\n\nfirst", project_id: "p1",
          include_archived: false, manifest: null,
        },
      },
    );
    const { downloads } = captureDownloads();

    renderPanel();
    await screen.findByRole("button", { name: "TXT로 내보내기" });
    expect(screen.queryByLabelText(/추적 정보/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "TXT로 내보내기" }));

    // 한 파일로 내보내기는 manifest 를 아예 청하지 않는다 — 파일도 하나뿐이다.
    await waitFor(() => expect(downloads).toEqual(["p1.txt"]));
    expect(String(fetchMock.mock.calls[1][0])).not.toContain("manifest");
  });
});
