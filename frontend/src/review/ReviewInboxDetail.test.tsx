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
    payload: { name: "철수", observation: "말이 없었다" },
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

  it("renders conflict merge/split buttons from the affordances", async () => {
    mockFetch({ body: detailBody() });
    renderDetail();
    await screen.findByText("철수");

    expect(screen.getByRole("button", { name: "병합" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "분리" })).toBeEnabled();
  });

  it("disables merge from the conflict affordance rather than recomputing", async () => {
    // over-strict: merge is character+matched-only. When the server declares
    // eligible=false, the button must be disabled with the server reason — the
    // frontend must not recompute character/matched itself.
    mockFetch({
      body: detailBody({
        conflicts: [
          {
            entry_id: "e1",
            action: "conflict",
            rationale: "matched 없음",
            matched_memory: null,
            diff: [],
            actions: [
              {
                action: "merge",
                eligible: false,
                reason: "merge requires a matched canonical memory",
              },
              { action: "split", eligible: true, reason: null },
            ],
          },
        ],
      }),
    });
    renderDetail();
    await screen.findByText("철수");

    const merge = screen.getByRole("button", { name: "병합" });
    expect(merge).toBeDisabled();
    expect(merge).toHaveAttribute(
      "title",
      "merge requires a matched canonical memory",
    );
    expect(screen.getByRole("button", { name: "분리" })).toBeEnabled();
  });

  it("disables split from the conflict affordance rather than recomputing", async () => {
    // over-strict: split is character-only. Symmetric to the merge guard —
    // when the server declares eligible=false, the button is disabled + reason;
    // the frontend must not recompute the candidate_type itself.
    mockFetch({
      body: detailBody({
        conflicts: [
          {
            entry_id: "e1",
            action: "conflict",
            rationale: "비-character",
            matched_memory: null,
            diff: [],
            actions: [
              {
                action: "merge",
                eligible: false,
                reason: "merge/split is character-only",
              },
              {
                action: "split",
                eligible: false,
                reason: "merge/split is character-only",
              },
            ],
          },
        ],
      }),
    });
    renderDetail();
    await screen.findByText("철수");

    const split = screen.getByRole("button", { name: "분리" });
    expect(split).toBeDisabled();
    expect(split).toHaveAttribute("title", "merge/split is character-only");
  });

  it("hides confirm/reject and merge/split while editing", async () => {
    // over-strict: entering edit mode must hide the other actions so the user
    // can't confirm/reject/merge a candidate mid-edit (state confusion).
    mockFetch({ body: detailBody() });
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));

    expect(screen.queryByRole("button", { name: "승인" })).toBeNull();
    expect(screen.queryByRole("button", { name: "거절" })).toBeNull();
    expect(screen.queryByRole("button", { name: "병합" })).toBeNull();
    expect(screen.queryByRole("button", { name: "분리" })).toBeNull();
    // the edit form controls are present instead
    expect(screen.getByRole("button", { name: "저장" })).toBeInTheDocument();
  });

  it("merges a conflict via the reconcile endpoint then returns to the inbox list", async () => {
    const fetchMock = mockFetch(
      { body: detailBody() },
      { body: { entry_id: "e1", action: "merge", memory_id: "m1", superseded_memory_id: null, idempotent_replay: false } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "병합" }));

    expect(await screen.findByText("검토함 목록")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/review-queue/e1/reconcile",
    );
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      action: "merge",
    });
  });

  it("splits a conflict via the reconcile endpoint with the split action", async () => {
    const fetchMock = mockFetch(
      { body: detailBody() },
      { body: { entry_id: "e1", action: "split", memory_id: "m1", superseded_memory_id: null, idempotent_replay: false } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "분리" }));

    expect(await screen.findByText("검토함 목록")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      action: "split",
    });
  });

  it("edits the candidate payload then re-versions via the edit endpoint", async () => {
    const fetchMock = mockFetch(
      { body: detailBody() },
      { body: { original_candidate_id: "c1", candidate_id: "c2", status: "confirmed", memory_id: "m1", idempotent_replay: false } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    // form is prefilled from the payload
    const observation = screen.getByLabelText("observation");
    await userEvent.clear(observation);
    await userEvent.type(observation, "말수가 적다");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("검토함 목록")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/candidates/c1/edit",
    );
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      payload: { name: "철수", observation: "말수가 적다" },
    });
  });

  it("disables save while an edited field is blank (server rejects empty)", async () => {
    // under-strict guard: the taxonomy requires non-empty strings; blanking a
    // field must not POST (the server would 400). Not a contract literal — a UX
    // convenience mirroring the repo's NonBlankName pattern.
    mockFetch({ body: detailBody() });
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    await userEvent.clear(screen.getByLabelText("observation"));

    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("cancels an edit and restores the read-only payload", async () => {
    mockFetch({ body: detailBody() });
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    expect(screen.getByLabelText("observation")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(screen.queryByLabelText("observation")).toBeNull();
    // read-only actions are back
    expect(screen.getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("keeps the edit form and surfaces the error when the edit is rejected", async () => {
    mockFetch(
      { body: detailBody() },
      { status: 400, body: { detail: "payload fields must be non-empty strings" } },
    );
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "payload fields must be non-empty strings",
    );
    // still on the form (did not navigate away)
    expect(screen.getByLabelText("observation")).toBeInTheDocument();
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
