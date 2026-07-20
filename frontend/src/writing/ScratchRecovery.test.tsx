import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScratchRecovery } from "./ScratchRecovery";

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

const listBody = (items: Array<{ id: string; text: string }>) => ({
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
      intent: null,
      created_at: "2026-07-20T00:00:00Z",
    })),
  },
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ScratchRecovery", () => {
  it("renders nothing when there is no unaccepted draft", async () => {
    mockFetch(listBody([]));
    const { container } = render(
      <ScratchRecovery projectId="p1" draftId="d1" />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
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
});
