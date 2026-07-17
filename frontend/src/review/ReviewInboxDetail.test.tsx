import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewInboxDetail } from "./ReviewInboxDetail";

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

function detailBody(overrides: Record<string, unknown> = {}) {
  return {
    candidate_id: "c1",
    job_id: "j1",
    candidate_type: "character_observation",
    status: "needs_review",
    confidence: 0.8,
    provenance: "ai_inferred",
    conflict_count: 1,
    actions: [
      { action: "confirm", eligible: true, reason: null },
      { action: "reject", eligible: true, reason: null },
      { action: "edit", eligible: true, reason: null },
    ],
    payload: { name: "철수", trait: "과묵함" },
    source_refs: [
      {
        source_ref_id: "s1",
        status: "resolved",
        snapshot_id: "snap1",
        block_id: "b1",
        start_offset: 0,
        end_offset: 10,
        quote: "철수는 말이 없었다.",
        content_hash: "h1",
      },
    ],
    conflicts: [
      {
        entry_id: "e1",
        action: "conflict",
        rationale: "기존 인물과 특성 상충",
        matched_memory: { id: "m1", payload: { trait: "수다스러움" } },
        diff: [{ field: "trait", before: "수다스러움", after: "과묵함" }],
        actions: [
          { action: "merge", eligible: true, reason: null },
          { action: "split", eligible: true, reason: null },
        ],
      },
    ],
    ...overrides,
  };
}

function renderDetail(path = "/projects/p1/review/c1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/projects/:projectId/review"
          element={<p>검토함 목록</p>}
        />
        <Route
          path="/projects/:projectId/review/:candidateId"
          element={<ReviewInboxDetail />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ReviewInboxDetail", () => {
  it("renders the payload, source quote and conflict diff", async () => {
    mockFetch({ body: detailBody() });
    renderDetail();

    expect(await screen.findByText("철수")).toBeInTheDocument();
    expect(screen.getByText("철수는 말이 없었다.")).toBeInTheDocument();
    expect(screen.getByText("기존 인물과 특성 상충")).toBeInTheDocument();
    // diff table shows before/after (수다스러움 is the unique before value)
    expect(screen.getByText("수다스러움")).toBeInTheDocument();
  });

  it("reads the item from the single-origin /api detail path", async () => {
    const fetchMock = mockFetch({ body: detailBody() });
    renderDetail();
    await screen.findByText("철수");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/p1/analysis/review-inbox/c1",
    );
  });

  it("confirms via the confirm endpoint then returns to the inbox list", async () => {
    const fetchMock = mockFetch(
      { body: detailBody() },
      { body: { candidate_id: "c1", status: "confirmed", memory_id: "m1", idempotent_replay: false } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "승인" }));

    expect(await screen.findByText("검토함 목록")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/projects/p1/analysis/candidates/c1/confirm",
      expect.objectContaining({ method: "POST" }),
    ]);
  });

  it("rejects via the reject endpoint then returns to the inbox list", async () => {
    const fetchMock = mockFetch(
      { body: detailBody() },
      { body: { candidate_id: "c1", status: "rejected", memory_id: null, idempotent_replay: false } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "거절" }));

    expect(await screen.findByText("검토함 목록")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/candidates/c1/reject",
    );
  });

  it("does not render conflict merge/split actions in this slice", async () => {
    // over-strict: conflicts are shown read-only here; merge/split is a later slice
    // even though the affordance payload carries eligible=true for them.
    mockFetch({ body: detailBody() });
    renderDetail();
    await screen.findByText("철수");

    expect(screen.queryByRole("button", { name: "병합" })).toBeNull();
    expect(screen.queryByRole("button", { name: "분리" })).toBeNull();
  });

  it("disables confirm from the server affordance rather than recomputing", async () => {
    mockFetch({
      body: detailBody({
        actions: [
          { action: "confirm", eligible: false, reason: "차단됨" },
          { action: "reject", eligible: true, reason: null },
          { action: "edit", eligible: true, reason: null },
        ],
      }),
    });
    renderDetail();

    const confirm = await screen.findByRole("button", { name: "승인" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("title", "차단됨");
  });

  it("marks a missing source_ref instead of showing a quote", async () => {
    mockFetch({
      body: detailBody({
        source_refs: [{ source_ref_id: "s1", status: "missing" }],
        conflicts: [],
      }),
    });
    renderDetail();

    expect(
      await screen.findByText("원문을 찾을 수 없습니다."),
    ).toBeInTheDocument();
  });

  it("keeps the detail and surfaces the error when confirm fails", async () => {
    mockFetch(
      { body: detailBody() },
      { status: 409, body: { detail: "이미 처리된 후보" } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "승인" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("이미 처리된 후보");
    // still on detail (did not navigate away)
    expect(screen.getByText("철수는 말이 없었다.")).toBeInTheDocument();
  });
});
