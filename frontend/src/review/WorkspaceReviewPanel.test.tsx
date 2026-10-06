import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
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

  it("runs the server-declared confirm action and reloads the list", async () => {
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

  it("runs the distinct server-declared reject action and reloads the list", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(list))
      .mockResolvedValueOnce(response(detail))
      .mockResolvedValueOnce(response({ candidate_id: "c1", status: "rejected" }))
      .mockResolvedValueOnce(response({ ...list, items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/?panel=review&candidate=c1"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "거절" }));
    expect(await screen.findByText("검토할 기억 후보가 없습니다.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/projects/p1/analysis/candidates/c1/reject",
    );
  });

  it("groups related candidates in the rail while keeping each member selectable", async () => {
    // Under-strict: a flat list loses the identity group. Over-strict: the
    // unrelated candidate must remain outside the group and still selectable.
    const identityGroup = {
      group_id: "g1", group_size: 2, group_status: "open",
      group_revision: 3, group_member_ids: ["c1", "c2"],
      identity_rationale_summary: "같은 인물",
    };
    const grouped = { ...item, identity_group: identityGroup };
    const another = { ...grouped, candidate_id: "c2", job_id: "j2" };
    const separate = { ...item, candidate_id: "c3" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ ...list, items: [grouped, another, separate] }))
      .mockResolvedValueOnce(response({ ...detail, ...another }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/?panel=review"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );

    expect(await screen.findByText("인물 후보 2건 묶음")).toBeInTheDocument();
    expect(screen.getByText("같은 인물")).toBeInTheDocument();
    const groupList = screen.getByRole("list", { name: "그룹 안 후보 목록" });
    expect(groupList.querySelectorAll("button")).toHaveLength(2);
    expect(screen.getByText("검토 대기").parentElement).toHaveTextContent("3건");
    await userEvent.click(groupList.querySelectorAll("button")[1]);
    expect(await screen.findByText("민아")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/analysis/review-inbox/c2");
  });

  it("corrects a grouped character name from the rail", async () => {
    const identityGroup = {
      group_id: "g1", group_size: 2, group_status: "open",
      group_revision: 3, group_member_ids: ["c1", "c2"],
      identity_rationale_summary: null,
    };
    const grouped = { ...item, payload: detail.payload, identity_group: identityGroup };
    const another = { ...grouped, candidate_id: "c2", job_id: "j2" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ ...list, items: [grouped, another] }))
      .mockResolvedValueOnce(response({ group_id: "g1", group_revision: 4, corrected_ids: ["n1", "n2"] }))
      .mockResolvedValueOnce(response({ ...list, items: [grouped, another] }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter initialEntries={["/?panel=review"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "그룹 이름 수정" }));
    const input = screen.getByRole("textbox", { name: "그룹에 함께 적용할 인물 이름" });
    await userEvent.clear(input);
    await userEvent.type(input, "새 이름");
    await userEvent.click(screen.getByRole("button", { name: "이름 적용" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/analysis/review-inbox/groups/g1/correct-name");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ expected_revision: 3, name: "새 이름" });
  });

  it("edits a candidate in the rail using the existing edit-and-confirm action", async () => {
    // Under-strict: saving must call the edit endpoint with every payload field.
    // Over-strict: opening edit alone must not submit or remove the candidate.
    const editable = {
      ...detail,
      actions: [...item.actions, { action: "edit", eligible: true, reason: null }],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(list))
      .mockResolvedValueOnce(response(editable))
      .mockResolvedValueOnce(response({ candidate_id: "c2", status: "confirmed" }))
      .mockResolvedValueOnce(response({ ...list, items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/?panel=review&candidate=c1"]}>
        <WorkspaceReviewPanel projectId="p1" onSourceSelect={vi.fn()} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await userEvent.clear(screen.getByRole("textbox", { name: "관찰" }));
    await userEvent.type(screen.getByRole("textbox", { name: "관찰" }), "편지를 발견함");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("검토할 기억 후보가 없습니다.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/analysis/candidates/c1/edit");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      payload: { name: "민아", observation: "편지를 발견함" },
    });
  });

  it("lets the editor guard cancel a full-inbox link while text is dirty", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(list)));
    const onBeforeNavigateAway = vi.fn(() => false);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <WorkspaceReviewPanel
                projectId="p1"
                onSourceSelect={vi.fn()}
                onBeforeNavigateAway={onBeforeNavigateAway}
              />
            }
          />
          <Route path="/projects/:projectId/review" element={<p>전체 검토함 route</p>} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("link", { name: "전체 검토함 열기 →" }));

    expect(onBeforeNavigateAway).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("전체 검토함 route")).toBeNull();
    expect(screen.getByRole("heading", { name: "검토 대기" })).toBeInTheDocument();
  });

  // 작품 기억 탭으로 가는 길(2026-10-06) — 드로어의 같은 검토함에서도 열리고
  // 편집기 이탈 가드를 그대로 지난다(전체 검토함 링크와 같은 처방).
  it("links to the canonical memory tab through the same dirty guard", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(list)));
    const onBeforeNavigateAway = vi.fn(() => false);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <WorkspaceReviewPanel
                projectId="p1"
                onSourceSelect={vi.fn()}
                onBeforeNavigateAway={onBeforeNavigateAway}
              />
            }
          />
          <Route
            path="/projects/:projectId/settings"
            element={<p>설정 라우트</p>}
          />
        </Routes>
      </MemoryRouter>,
    );

    const link = await screen.findByRole("link", {
      name: "승인된 작품 기억 보기 →",
    });
    expect(link).toHaveAttribute("href", "/projects/p1/settings?tab=memory");

    await userEvent.click(link);
    expect(onBeforeNavigateAway).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("설정 라우트")).toBeNull();
    expect(screen.getByRole("heading", { name: "검토 대기" })).toBeInTheDocument();
  });
});
