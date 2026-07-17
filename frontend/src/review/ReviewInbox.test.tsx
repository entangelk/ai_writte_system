import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewInbox } from "./ReviewInbox";

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

const CANDIDATE_ACTIONS = [
  { action: "confirm", eligible: true, reason: null },
  { action: "reject", eligible: true, reason: null },
  { action: "edit", eligible: true, reason: null },
];

const GATE_ACTIONS = [
  { action: "resolve", eligible: true, reason: null },
  { action: "dismiss", eligible: true, reason: null },
];

function inboxBody(overrides: Record<string, unknown> = {}) {
  return {
    project_id: "p1",
    items: [
      {
        candidate_id: "c1",
        job_id: "j1",
        candidate_type: "character_observation",
        status: "needs_review",
        confidence: 0.8,
        provenance: "ai_inferred",
        conflict_count: 0,
        actions: CANDIDATE_ACTIONS,
      },
    ],
    gate_findings: [
      {
        id: "g1",
        origin: "context_gate",
        status: "open",
        check: "continuity",
        detail: "시점 불일치",
        query: "",
        purpose: "",
        needs: [],
        pointer_ids: [],
        actions: GATE_ACTIONS,
      },
    ],
    ...overrides,
  };
}

function renderInbox(path = "/projects/p1/review") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId" element={<p>원고 홈</p>} />
        <Route path="/projects/:projectId/review" element={<ReviewInbox />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ReviewInbox", () => {
  it("renders candidate and gate-finding rows from the inbox payload", async () => {
    mockFetch({ body: inboxBody() });
    renderInbox();

    expect(await screen.findByText("인물")).toBeInTheDocument();
    expect(screen.getByText("시점 불일치")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "승인" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "해결" })).toBeEnabled();
  });

  it("reads the inbox from the single-origin /api path", async () => {
    const fetchMock = mockFetch({ body: inboxBody() });
    renderInbox();
    await screen.findByText("인물");

    // over-strict: an absolute URL would silently need CORS; this pins single origin.
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/projects/p1/analysis/review-inbox",
    );
  });

  it("confirms a candidate then re-reads the inbox (server truth, no optimistic patch)", async () => {
    const fetchMock = mockFetch(
      { body: inboxBody() },
      { body: { candidate_id: "c1", status: "confirmed", memory_id: "m1", idempotent_replay: false } },
      { body: inboxBody({ items: [] }) },
    );
    renderInbox();

    await userEvent.click(await screen.findByRole("button", { name: "승인" }));

    await waitFor(() =>
      expect(screen.getByText("검토할 기억 후보가 없습니다.")).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/projects/p1/analysis/candidates/c1/confirm",
      expect.objectContaining({ method: "POST" }),
    ]);
    // third call is the reload GET
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/projects/p1/analysis/review-inbox",
    );
  });

  it("resolves a gate finding via the resolve endpoint then re-reads", async () => {
    const fetchMock = mockFetch(
      { body: inboxBody() },
      { body: { finding: {}, idempotent_replay: false } },
      { body: inboxBody({ gate_findings: [] }) },
    );
    renderInbox();

    await userEvent.click(await screen.findByRole("button", { name: "해결" }));

    await waitFor(() =>
      expect(screen.getByText("열린 게이트 지적이 없습니다.")).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/gate-findings/g1/resolve",
    );
  });

  it("dismisses a gate finding via the dismiss endpoint then re-reads", async () => {
    const fetchMock = mockFetch(
      { body: inboxBody() },
      { body: { finding: {}, idempotent_replay: false } },
      { body: inboxBody({ gate_findings: [] }) },
    );
    renderInbox();

    await userEvent.click(await screen.findByRole("button", { name: "무시" }));

    await waitFor(() =>
      expect(screen.getByText("열린 게이트 지적이 없습니다.")).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/gate-findings/g1/dismiss",
    );
  });

  it("disables a button from the server affordance instead of recomputing eligibility", async () => {
    // over-strict: if the frontend ignored `eligible` and always enabled buttons,
    // this would fail. Locks the affordance-consumption contract (v1.6.67).
    const body = inboxBody({
      items: [
        {
          candidate_id: "c1",
          job_id: "j1",
          candidate_type: "character_observation",
          status: "needs_review",
          confidence: 0.8,
          provenance: "ai_inferred",
          conflict_count: 0,
          actions: [
            { action: "confirm", eligible: false, reason: "차단됨" },
            { action: "reject", eligible: true, reason: null },
            { action: "edit", eligible: true, reason: null },
          ],
        },
      ],
    });
    mockFetch({ body });
    renderInbox();

    const confirm = await screen.findByRole("button", { name: "승인" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("title", "차단됨");
    expect(screen.getByRole("button", { name: "거절" })).toBeEnabled();
  });

  it("does not render deferred actions (edit) even though the affordance carries them", async () => {
    // over-strict: this slice wires only confirm/reject/resolve/dismiss.
    mockFetch({ body: inboxBody() });
    renderInbox();
    await screen.findByText("인물");

    expect(screen.queryByRole("button", { name: "수정" })).toBeNull();
  });

  it("surfaces the error detail when an action fails and keeps the row", async () => {
    mockFetch(
      { body: inboxBody() },
      { status: 409, body: { detail: "이미 처리된 후보" } },
    );
    renderInbox();

    await userEvent.click(await screen.findByRole("button", { name: "승인" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("이미 처리된 후보");
    expect(screen.getByText("인물")).toBeInTheDocument();
  });

  it("shows both empty states when nothing is pending", async () => {
    mockFetch({ body: inboxBody({ items: [], gate_findings: [] }) });
    renderInbox();

    expect(
      await screen.findByText("검토할 기억 후보가 없습니다."),
    ).toBeInTheDocument();
    expect(screen.getByText("열린 게이트 지적이 없습니다.")).toBeInTheDocument();
  });
});
