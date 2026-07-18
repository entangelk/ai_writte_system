import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisTrigger } from "./AnalysisTrigger";

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

// The two blocks the version detail exposes; catalog coverage is matched by
// exact (start_offset, end_offset).
const VERSION_DETAIL = {
  body: {
    draft_version: { id: "v1" },
    snapshot: { id: "s1" },
    blocks: [
      { start_offset: 0, end_offset: 10, kind: "paragraph" },
      { start_offset: 12, end_offset: 20, kind: "paragraph" },
    ],
  },
};
// A catalog that already covers BOTH blocks → no source_ref is created.
const CATALOG_FULL = {
  body: { source_refs: [{ start_offset: 0, end_offset: 10 }, { start_offset: 12, end_offset: 20 }] },
};
// A catalog left half-built by an earlier partial failure (only block 1).
const CATALOG_PARTIAL = { body: { source_refs: [{ start_offset: 0, end_offset: 10 }] } };
const CATALOG_EMPTY = { body: { source_refs: [] } };
const JOB_CREATED = { body: { job: { id: "j1", status: "pending" }, idempotent_replay: false } };
const runResult = (n: number) => ({
  body: { job: { id: "j1", status: "succeeded" }, candidates: Array.from({ length: n }, () => ({})) },
});

function renderTrigger(
  props: Partial<React.ComponentProps<typeof AnalysisTrigger>> = {},
) {
  return render(
    <MemoryRouter initialEntries={["/projects/p1/drafts/d1"]}>
      <Routes>
        <Route path="/projects/:projectId/review" element={<p>검토함 페이지</p>} />
        <Route
          path="/projects/:projectId/drafts/:draftId"
          element={
            <AnalysisTrigger
              projectId="p1"
              draftId="d1"
              latestVersionId="v1"
              latestSnapshotId="s1"
              readOnly={false}
              dirty={false}
              {...props}
            />
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

const runButton = () => screen.getByRole("button", { name: /이 원고 분석/ });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AnalysisTrigger", () => {
  it("runs the job and reports the candidate count with a review link when the catalog is complete", async () => {
    const fetchMock = mockFetch(CATALOG_FULL, VERSION_DETAIL, JOB_CREATED, runResult(2));
    renderTrigger();
    await userEvent.click(runButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    // Over-strict single-origin /api paths; catalog fully covers both blocks so
    // no source_ref POST, straight to create-job + run.
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p1/snapshots/s1/source-refs");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/drafts/d1/versions/v1");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/analysis/jobs");
    // D5=A alignment: per-snapshot deterministic key (mirrors accept's
    // analysis_job_key) so accept's job + re-clicks converge on one job — a
    // random uuid here would orphan accept's job and duplicate candidates.
    expect(JSON.parse(fetchMock.mock.calls[2][1].body).idempotency_key).toBe("analyze:s1");
    expect(fetchMock.mock.calls[3][0]).toBe("/api/projects/p1/analysis/jobs/j1/run");
    expect(await screen.findByText(/2개 검토 후보가 생성/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /검토함에서 확인/ }),
    ).toHaveAttribute("href", "/projects/p1/review");
  });

  it("builds a source_ref catalog per uncovered block when none exists", async () => {
    const fetchMock = mockFetch(
      CATALOG_EMPTY,
      VERSION_DETAIL,
      { body: { id: "sr1" } }, // create block 1
      { body: { id: "sr2" } }, // create block 2
      JOB_CREATED,
      runResult(3),
    );
    renderTrigger();
    await userEvent.click(runButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/snapshots/s1/source-refs");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ start_offset: 0, end_offset: 10 });
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ start_offset: 12, end_offset: 20 });
    expect(await screen.findByText(/3개 검토 후보가 생성/)).toBeInTheDocument();
  });

  it("self-heals a partial catalog: creates only the missing block, then runs", async () => {
    // Blocking #3 regression: an earlier partial failure left block 1's ref. The
    // retry must create only the MISSING block 2 (not skip because refs exist,
    // which would run extraction against a missing anchor).
    const fetchMock = mockFetch(
      CATALOG_PARTIAL,
      VERSION_DETAIL,
      { body: { id: "sr2" } }, // create ONLY the missing block 2
      JOB_CREATED,
      runResult(1),
    );
    renderTrigger();
    await userEvent.click(runButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    // Exactly one create, and it is block 2 (the missing one), not block 1.
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/snapshots/s1/source-refs");
    expect(fetchMock.mock.calls[2][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ start_offset: 12, end_offset: 20 });
    expect(fetchMock.mock.calls[3][0]).toBe("/api/projects/p1/analysis/jobs");
    expect(await screen.findByText(/1개 검토 후보가 생성/)).toBeInTheDocument();
  });

  it("stops with a clear error when the snapshot has no anchorable blocks", async () => {
    // All blocks degenerate (end <= start) → nothing to catalog → extraction
    // would 400. The trigger surfaces a friendly message instead of running.
    const fetchMock = mockFetch(CATALOG_EMPTY, {
      body: { draft_version: { id: "v1" }, snapshot: { id: "s1" }, blocks: [{ start_offset: 5, end_offset: 5 }] },
    });
    renderTrigger();
    await userEvent.click(runButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("분석할 본문 블록이 없습니다");
    // No job was created/run — it stopped at the catalog step.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not launch a second run on a fast double-click (busyRef guard)", async () => {
    const fetchMock = mockFetch(CATALOG_FULL, VERSION_DETAIL, JOB_CREATED, runResult(2));
    renderTrigger();
    // Capture the element once (its label flips to "분석 중…" after the first
    // click) and click twice: only ONE analyze sequence must run (4 calls, not 8).
    const btn = runButton();
    fireEvent.click(btn);
    fireEvent.click(btn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(await screen.findByText(/2개 검토 후보가 생성/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("reports when a run extracts no candidates", async () => {
    mockFetch(CATALOG_FULL, VERSION_DETAIL, JOB_CREATED, runResult(0));
    renderTrigger();
    await userEvent.click(runButton());
    expect(
      await screen.findByText(/새 검토 후보가 추출되지 않았습니다/),
    ).toBeInTheDocument();
  });

  it("disables the button and states why when there is no saved version", () => {
    renderTrigger({ latestSnapshotId: null, latestVersionId: null });
    expect(runButton()).toBeDisabled();
    expect(screen.getByText(/저장된 version이 없습니다/)).toBeInTheDocument();
  });

  it("disables the button and states why when there are unsaved changes", () => {
    renderTrigger({ dirty: true });
    expect(runButton()).toBeDisabled();
    expect(screen.getByText(/먼저 저장한 뒤 분석/)).toBeInTheDocument();
  });

  it("disables the button for an archived (read-only) draft", () => {
    renderTrigger({ readOnly: true });
    expect(runButton()).toBeDisabled();
    expect(screen.getByText(/보관된 원고는 분석할 수 없습니다/)).toBeInTheDocument();
  });

  it("surfaces an error and offers retry when the run fails", async () => {
    mockFetch(CATALOG_FULL, VERSION_DETAIL, JOB_CREATED, { status: 502, body: { detail: "extraction failed" } });
    renderTrigger();
    await userEvent.click(runButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("extraction failed");
    expect(screen.getByRole("button", { name: "다시 분석" })).toBeInTheDocument();
  });
});
