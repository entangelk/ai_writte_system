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

afterEach(() => {
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
    const { container } = render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 2개/);
    // 본문은 접힘 안의 <pre> 다 — summary 미리보기가 같은 글자를 한 번 더 그리므로
    // 순서는 본문 노드로만 잰다.
    const texts = [...container.querySelectorAll("pre")].map((el) => el.textContent);
    expect(texts).toEqual(["최신 초안", "오래된 초안"]);
  });

  it("접힌 항목을 펼치면 본문이 보인다 (오너 2026-09-08 — 글이 너무 길다)", async () => {
    // 양방향: 기본이 접힘이어야 하고(펼침으로 되돌리면 재실패), 펼치면 본문 전체가
    // 보여야 한다(접힘을 못 열게 만들면 재실패). summary 는 첫 줄 40자까지의 미리보기다.
    const long = "가".repeat(120);
    mockFetch(listBody([{ id: "wds:1", text: long }]));
    const { container } = render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    const fold = container.querySelector("details") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    const summary = fold.querySelector("summary") as HTMLElement;
    expect(summary.textContent).toBe(`${"가".repeat(40)}…`);
    expect(screen.getByText(long)).not.toBeVisible();

    await userEvent.click(summary);

    expect(fold.open).toBe(true);
    expect(screen.getByText(long)).toBeVisible();
  });

  it("채택 버튼이 없다 — 남는 길은 복사와 버리기뿐이다 (오너 2026-09-08)", async () => {
    // 오너 결정: *"버튼을 그냥 없애주고 통로만 열어두자."* under 방향은 버튼이
    // 되살아나면 재실패하고, over 방향은 복사·버리기까지 같이 지우면 재실패한다.
    mockFetch(listBody([{ id: "wds:1", text: "남은 초안" }]));
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    expect(screen.queryByRole("button", { name: "채택" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "복사" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "버리기" })).toBeEnabled();
  });

  it("복사 버튼이 본문을 클립보드에 넣는다", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    mockFetch(listBody([{ id: "wds:1", text: "복사할 초안" }]));
    render(<ScratchRecovery projectId="p1" draftId="d1" />);
    await screen.findByText(/미채택 초안 1개/);

    screen.getByRole("button", { name: "복사" }).click();

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("복사할 초안"));
    expect(await screen.findByRole("button", { name: "복사됨" })).toBeInTheDocument();
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
    // 접힘 때문에 같은 글자가 summary 와 <pre> 둘에 있다 — 개수가 아니라 존재를 본다.
    expect(screen.getAllByText("남을 초안").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("버릴 초안")).toHaveLength(0);
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
    expect(screen.getAllByText("지킬 초안").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("지킬 초안").length).toBeGreaterThan(0);
  });

});
