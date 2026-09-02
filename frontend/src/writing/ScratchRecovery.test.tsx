import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScratchRecovery } from "./ScratchRecovery";
import { resetMemberQuota, seedMemberQuota } from "../quota/useMemberQuota";

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

// The pad reads the member quota (accept-refusal copy). Seeding skips the
// hook's fetch so the queued responses below describe ONLY the pad's own
// requests — same reason WritingPanel tests seed the budget cache.
beforeEach(() => {
  seedMemberQuota({
    remaining: 7, unlimited: false, status: "active",
    daily: { limit: 20, used: 13, remaining: 7, resets_at: null },
    weekly: { limit: 100, used: 41, remaining: 59, resets_at: null },
  } as never);
  // crypto.randomUUID mints "uuid-1", … so the accept idempotency key is
  // observable and key reuse (the 429 replay) is assertable.
  let n = 0;
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `uuid-${++n}`) });
});

afterEach(() => {
  resetMemberQuota();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const listBody = (
  items: Array<{
    id: string;
    text: string;
    version_id?: string | null;
    intent?: string | null;
    next_unit?: { title: string; goal: string | null } | null;
  }>,
) => ({
  body: {
    project_id: "p1",
    draft_id: "d1",
    items: items.map((i) => ({
      id: i.id,
      draft_id: "d1",
      request_id: "wr1",
      task_type: "continue_scene",
      output_type: "draft_patch",
      instruction: "이어서",
      candidate_text: i.text,
      intent: i.intent === undefined ? null : i.intent,
      next_unit: i.next_unit === undefined ? null : i.next_unit,
      version_id: i.version_id === undefined ? "v1" : i.version_id,
      created_at: "2026-07-20T00:00:00Z",
    })),
  },
});

const gatePass = {
  request_id: "wr1", project_id: "p1", decision: "pass", findings: [],
  checked_constraints: [], evaluated_by_model: "fake-gate",
};

const acceptSaved = {
  accepted: true, gate: gatePass,
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

describe("ScratchRecovery", () => {
  it("renders nothing when there is no unaccepted draft", async () => {
    mockFetch(listBody([]));
    const { container } = render(
      <ScratchRecovery projectId="p1" draftId="d1" />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("accepts a start-next pad item with its stored next-unit metadata", async () => {
    const fetchMock = mockFetch(
      listBody([{
        id: "wds:1",
        text: "새 장면 본문",
        intent: "start_next_unit",
        next_unit: { title: "다음 장면", goal: "긴장 유지" },
      }]),
      { body: { ...acceptSaved, intent: "start_next_unit" } },
    );
    const onAccepted = vi.fn();
    render(
      <ScratchRecovery projectId="p1" draftId="d1" onAccepted={onAccepted} />,
    );
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    const acceptCall = fetchMock.mock.calls.find(
      ([url]) => String(url).endsWith("/writing/accept"),
    );
    const body = JSON.parse((acceptCall?.[1] as RequestInit).body as string);
    expect(body.intent).toBe("start_next_unit");
    expect(body.next_unit).toEqual({ title: "다음 장면", goal: "긴장 유지" });
  });

  it("surfaces recoverable candidates newest-first", async () => {
    mockFetch(
      listBody([
        { id: "wds:2", text: "최신 초안" },
        { id: "wds:1", text: "오래된 초안" },
      ]),
    );
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 2개/);
    const texts = screen.getAllByText(/초안$/).map((el) => el.textContent);
    expect(texts).toEqual(["최신 초안", "오래된 초안"]);
  });

  it("discards the draft's scratch after confirmation", async () => {
    const fetchMock = mockFetch(
      listBody([{ id: "wds:1", text: "버릴 초안" }]),
      { body: { project_id: "p1", draft_id: "d1", deleted: 1 } },
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "모두 버리기" }));

    await waitFor(() =>
      expect(screen.queryByText(/미채택 초안/)).not.toBeInTheDocument(),
    );
    const deleteCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "DELETE",
    );
    expect(deleteCall?.[0]).toContain("/writing/scratch?draft_id=d1");
  });

  it("does not discard when confirmation is declined", async () => {
    const fetchMock = mockFetch(listBody([{ id: "wds:1", text: "지킬 초안" }]));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "모두 버리기" }));

    expect(
      fetchMock.mock.calls.some(
        ([, init]) => (init as RequestInit | undefined)?.method === "DELETE",
      ),
    ).toBe(false);
    expect(screen.getByText(/미채택 초안 1개/)).toBeInTheDocument();
  });

  it("accepts a pad item with the stored scratch fields and a bound idempotency key", async () => {
    // under-strict: the pad must reconstruct the accept contract from the
    // stored entry — base_version_id/current_position from version_id, the
    // text/instruction/task_type as saved — and mint a body-bound key.
    const fetchMock = mockFetch(
      listBody([{ id: "wds:1", text: "복구할 초안" }]),
      { body: acceptSaved },
    );
    const onAccepted = vi.fn();
    render(
      <ScratchRecovery projectId="p1" draftId="d1" onAccepted={onAccepted} />,
    );
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    const acceptCall = fetchMock.mock.calls.find(
      ([url]) => String(url).endsWith("/writing/accept"),
    );
    expect(acceptCall?.[0]).toBe("/api/projects/p1/writing/accept");
    const body = JSON.parse((acceptCall?.[1] as RequestInit).body as string);
    expect(body).toMatchObject({
      request_id: "wr1",
      draft_id: "d1",
      base_version_id: "v1",
      instruction: "이어서",
      candidate_text: "복구할 초안",
      task_type: "continue_scene",
      output_type: "draft_patch",
      current_position: { draft_id: "d1", version_id: "v1" },
      intent: "append_current",
      next_unit: null,
    });
    expect(body.idempotency_key).toBe("uuid-1");
  });

  it("treats a 502 analysis-partial accept as a success", async () => {
    // under-strict (folding guard): a 502 with accepted=true + saved IS a
    // saved version (only the analysis job failed) — the pad must not read it
    // as an error; onAccepted fires so the editor reloads.
    mockFetch(
      listBody([{ id: "wds:1", text: "복구할 초안" }]),
      {
        status: 502,
        body: {
          accepted: true, intent: "append_current",
          saved: acceptSaved.saved,
          analysis_job: null, analysis_error: "analysis worker down",
        },
      },
    );
    const onAccepted = vi.fn();
    render(
      <ScratchRecovery projectId="p1" draftId="d1" onAccepted={onAccepted} />,
    );
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/실패했습니다/)).not.toBeInTheDocument();
  });

  it("shows the gate decision inline when the accept is refused", async () => {
    // over-strict: a non-pass re-gate saved nothing — the item STAYS (still
    // copyable) and the decision is named with its findings.
    mockFetch(
      listBody([{ id: "wds:1", text: "반려될 초안" }]),
      {
        body: {
          accepted: false,
          gate: {
            request_id: "wr1", project_id: "p1", decision: "revise",
            findings: [{
              type: "continuity", severity: "error",
              message: "주인공 이름이 앞 문단과 다릅니다.", evidence: "아린",
              recommended_decision: "revise",
            }],
            checked_constraints: [], evaluated_by_model: "fake-gate",
          },
        },
      },
    );
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    expect(await screen.findByText(/채택되지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText(/수정 필요 \(revise\)/)).toBeInTheDocument();
    expect(
      screen.getByText("주인공 이름이 앞 문단과 다릅니다."),
    ).toBeInTheDocument();
    // The item itself is still here (copy remains the escape hatch).
    expect(screen.getByText("반려될 초안")).toBeInTheDocument();
  });

  it("keeps the item and suggests copy on a 409 stale base", async () => {
    // over-strict: the draft moved on since generation — nothing was saved,
    // so the entry must survive and point at the copy path.
    mockFetch(
      listBody([{ id: "wds:1", text: "늦은 초안" }]),
      {
        status: 409,
        body: { detail: "base draft version is not the latest version" },
      },
    );
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    expect(
      await screen.findByText(/그 사이 새 저장이 생겨 기준 version이 최신이 아닙니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/복사해 직접 반영하세요/)).toBeInTheDocument();
    expect(screen.getByText("늦은 초안")).toBeInTheDocument();
  });

  it("disables 채택 and explains when the entry has no version_id", async () => {
    // over-strict: a pre-D7 record has no base version — it can never be
    // accepted, so the button must be disabled (not a mystery click) and the
    // copy path named.
    mockFetch(listBody([{ id: "wds:1", text: "오래된 초안", version_id: null }]));
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    expect(screen.getByRole("button", { name: "채택" })).toBeDisabled();
    expect(
      screen.getByText(/기준 version이 기록되지 않은 오래된 항목입니다/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "버리기" })).toBeEnabled();
  });

  it("discards a single item after confirmation, keeping siblings", async () => {
    // under-strict: per-item [버리기] deletes exactly the named entry; the
    // sibling and the banner count reflect the remainder.
    const fetchMock = mockFetch(
      listBody([
        { id: "wds:1", text: "버릴 초안" },
        { id: "wds:2", text: "남을 초안" },
      ]),
      { body: { project_id: "p1", scratch_id: "wds:1", deleted: true } },
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 2개/);

    const buttons = screen.getAllByRole("button", { name: "버리기" });
    await userEvent.click(buttons[0]);

    await waitFor(() =>
      expect(screen.getByText(/미채택 초안 1개/)).toBeInTheDocument(),
    );
    expect(screen.getByText("남을 초안")).toBeInTheDocument();
    expect(screen.queryByText("버릴 초안")).not.toBeInTheDocument();
    const deleteCall = fetchMock.mock.calls.find(
      ([url]) => String(url).includes("/writing/scratch/"),
    );
    // encodeURIComponent keeps the "wds:" prefix safe in the path segment.
    expect(deleteCall?.[0]).toBe(
      "/api/projects/p1/writing/scratch/wds%3A1",
    );
    expect((deleteCall?.[1] as RequestInit).method).toBe("DELETE");
  });

  it("restores the item when a per-item discard fails", async () => {
    // over-strict: a failed DELETE must bring the optimistic removal back —
    // the safety net never loses an entry to a transport fault.
    mockFetch(
      listBody([{ id: "wds:1", text: "지킬 초안" }]),
      { status: 500, body: { detail: "boom" } },
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "버리기" }));

    expect(
      await screen.findByText(/초안 버리기에 실패했습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText("지킬 초안")).toBeInTheDocument();
  });

  it("does not send a per-item discard when confirmation is declined", async () => {
    const fetchMock = mockFetch(
      listBody([{ id: "wds:1", text: "지킬 초안" }]),
    );
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "버리기" }));

    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/writing/scratch/")),
    ).toBe(false);
    expect(screen.getByText("지킬 초안")).toBeInTheDocument();
  });

  it("re-asks on a 429 quota lock and replays with the same idempotency key", async () => {
    // The 429 duplicate-lock confirm (8.4 W3=A). The replay MUST reuse the
    // bound key (a fresh key would break accept's idempotency contract) and
    // carry the X-Confirm-Duplicate header the server requires.
    const fetchMock = mockFetch(
      listBody([{ id: "wds:1", text: "채택될 초안" }]),
      {
        status: 429,
        body: { detail: "the same request is already in progress" },
      },
      { body: acceptSaved },
    );
    const onAccepted = vi.fn();
    render(
      <ScratchRecovery projectId="p1" draftId="d1" onAccepted={onAccepted} />,
    );
    await screen.findByText(/미채택 초안 1개/);

    await userEvent.click(screen.getByRole("button", { name: "채택" }));

    const dialog = await screen.findByRole("alertdialog", {
      name: "중복 요청 확인",
    });
    expect(dialog).toBeInTheDocument();
    expect(onAccepted).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("button", { name: "하나 더 만들기" }),
    );

    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    const acceptCalls = fetchMock.mock.calls.filter(
      ([url]) => String(url).endsWith("/writing/accept"),
    );
    expect(acceptCalls).toHaveLength(2);
    const firstBody = JSON.parse((acceptCalls[0][1] as RequestInit).body as string);
    const replayBody = JSON.parse((acceptCalls[1][1] as RequestInit).body as string);
    expect(replayBody.idempotency_key).toBe(firstBody.idempotency_key);
    expect((acceptCalls[1][1] as RequestInit).headers).toMatchObject({
      "X-Confirm-Duplicate": "1",
    });
  });
});
