import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceReviewPanel } from "./WorkspaceReviewPanel";

function response(body: unknown) {
  return { ok: true, status: 200, statusText: "", json: async () => body };
}

const item = {
  candidate_id: "c1",
  job_id: "j1",
  candidate_type: "character_observation",
  status: "needs_review",
  confidence: 0.8,
  provenance: "ai_inferred",
  conflict_count: 0,
  actions: [
    { action: "confirm", eligible: true, reason: null },
    { action: "reject", eligible: true, reason: null },
  ],
};

const sourceRef = {
  source_ref_id: "sr1",
  status: "resolved",
  snapshot_id: "s1",
  block_id: "b1",
  start_offset: 3,
  end_offset: 7,
  quote: "근거 문장",
  content_hash: "hash-1",
};

const list = { project_id: "p1", items: [item], gate_findings: [] };
const detail = { ...item, payload: { name: "민아", observation: "편지를 봄" }, source_refs: [sourceRef], conflicts: [] };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("WorkspaceReviewPanel", () => {
  it("restores candidate and source from the query and reports the pending count", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(list))
      .mockResolvedValueOnce(response(detail));
    vi.stubGlobal("fetch", fetchMock);
    const onSourceSelect = vi.fn();
    const onPendingCountChange = vi.fn();

    render(
      <MemoryRouter initialEntries={["/?panel=review&candidate=c1&source=sr1"]}>
        <WorkspaceReviewPanel
          projectId="p1"
          onSourceSelect={onSourceSelect}
          onPendingCountChange={onPendingCountChange}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText("민아")).toBeInTheDocument();
    await waitFor(() => expect(onSourceSelect).toHaveBeenCalledWith(sourceRef));
    expect(onPendingCountChange).toHaveBeenCalledWith(1);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1/analysis/review-inbox",
      "/api/projects/p1/analysis/review-inbox/c1",
    ]);
  });

  it("does not offer an exact source jump for an unresolved pointer", async () => {
    const unresolved = { source_ref_id: "sr2", status: "missing" };
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response(list))
        .mockResolvedValueOnce(response({ ...detail, source_refs: [unresolved] })),
    );

    render(
      <MemoryRouter initialEntries={["/?panel=review&candidate=c1"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );

    expect(await screen.findByText("원문을 찾을 수 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /원고에서 보기/ })).toBeNull();
  });

  it("runs a server-declared candidate action and reloads the list", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(list))
      .mockResolvedValueOnce(response(detail))
      .mockResolvedValueOnce(response({ candidate_id: "c1", status: "confirmed" }))
      .mockResolvedValueOnce(response({ ...list, items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/?panel=review&candidate=c1"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "승인" }));
    expect(await screen.findByText("검토할 기억 후보가 없습니다.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/projects/p1/analysis/candidates/c1/confirm",
    );
  });
});
