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
        payload: { name: "서윤", observation: "비밀 통로를 알고 있다" },
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

/** A grouped candidate row. Every member of one group repeats this object. */
function group(overrides: Record<string, unknown> = {}) {
  return {
    group_id: "g-1",
    group_size: 2,
    group_status: "open",
    // Not 0 on purpose: a UI that hardcodes the revision (or derives it from
    // the member count) passes with 0 and fails here.
    group_revision: 3,
    group_member_ids: ["c1", "c2"],
    identity_rationale_summary: "정규화된 이름이 같다",
    ...overrides,
  };
}

function member(candidateId: string, jobId: string, name: string,
                identityGroup: Record<string, unknown> | null) {
  return {
    candidate_id: candidateId,
    job_id: jobId,
    candidate_type: "character_observation",
    status: "needs_review",
    confidence: 0.8,
    provenance: "ai_inferred",
    conflict_count: 0,
    payload: { name, observation: "비밀 통로를 알고 있다" },
    actions: CANDIDATE_ACTIONS,
    identity_group: identityGroup,
  };
}

/** Two grouped members + one ungrouped candidate, in that order. */
function mixedInbox() {
  return inboxBody({
    items: [
      member("c1", "j1", "서윤", group()),
      member("c2", "j2", "서윤", group()),
      member("c9", "j3", "이설", null),
    ],
    gate_findings: [],
  });
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
    expect(screen.getByText("서윤")).toBeInTheDocument();
    expect(screen.getByText("비밀 통로를 알고 있다")).toBeInTheDocument();
    expect(screen.getByText("시점 불일치")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "승인" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "해결" })).toBeEnabled();
  });

  it("renders event and open-question summaries inside their list rows", async () => {
    mockFetch({
      body: inboxBody({
        items: [
          {
            candidate_id: "event-1", job_id: "j1",
            candidate_type: "event_observation", status: "needs_review",
            confidence: 0.7, provenance: "source_observed", conflict_count: 0,
            payload: { event: "서윤이 비밀 통로를 발견했다" }, actions: CANDIDATE_ACTIONS,
          },
          {
            candidate_id: "question-1", job_id: "j1",
            candidate_type: "open_question_observation", status: "needs_review",
            confidence: 0.6, provenance: "ai_inferred", conflict_count: 0,
            payload: { question: "통로 끝에는 무엇이 있는가?" }, actions: CANDIDATE_ACTIONS,
          },
        ],
      }),
    });
    renderInbox();

    expect(await screen.findByText("서윤이 비밀 통로를 발견했다")).toBeInTheDocument();
    expect(screen.getAllByText("사건")).toHaveLength(2);
    expect(screen.getByText("미해결 질문")).toBeInTheDocument();
    expect(screen.getByText("통로 끝에는 무엇이 있는가?")).toBeInTheDocument();
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
          payload: { event: "거센 비가 내림" },
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

/**
 * 정체성 그룹 grouped Inbox UI (Slice 6).
 *
 * 서버는 **평평한 item 목록**을 주고 같은 그룹의 멤버가 같은 `identity_group`
 * 객체를 반복한다 — 묶는 것은 이 화면의 일이다. 그래서 여기서 재는 것은
 * "묶였는가"와 **"묶고도 개별 처리 경로를 잃지 않았는가"** 둘이다.
 *
 * 양방향:
 * - under-strict — 그룹을 안 묶고 평평하게 그리면 첫 셀이 실패한다.
 * - under-strict — 승인 body 의 `expected_revision` 을 안 싣거나 상수로 박으면
 *   요청 셀이 실패한다(픽스처 revision 은 일부러 3이다).
 * - over-strict — 그룹으로 묶었다고 멤버의 개별 승인·거절을 없애면(= 그룹
 *   단위로만 처리 가능하게 만들면) affordance 유지 셀이 실패한다.
 * - over-strict — 부분 실패를 재조회로 지워 "성공"처럼 닫으면 잔여 셀이 실패한다.
 */
describe("ReviewInbox — 정체성 그룹", () => {
  it("folds grouped members into one group row and leaves ungrouped rows alone", async () => {
    mockFetch({ body: mixedInbox() });
    renderInbox();

    expect(
      await screen.findByText(/인물 후보 2건이 같은 대상으로 묶였습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/근거 — 정규화된 이름이 같다/)).toBeInTheDocument();
    // 목록 첫 화면에서 실제 후보 payload 가 보인다(계획 §Slice 6 "규칙").
    expect(screen.getAllByText("서윤")).toHaveLength(2);
    // ungrouped 후보는 그룹 상자 밖에 그대로 남는다.
    expect(screen.getByText("이설")).toBeInTheDocument();
    expect(screen.getAllByRole("list", { name: "그룹 안 후보 목록" })).toHaveLength(1);
  });

  it("shows which analysis job produced each member of a group", async () => {
    // 그룹 안 후보를 가르는 축은 어느 분석 job 이 만들었는가다(계획 §Slice 6).
    mockFetch({ body: mixedInbox() });
    renderInbox();
    await screen.findByText(/같은 대상으로 묶였습니다/);

    expect(screen.getByText(/분석 j1/)).toBeInTheDocument();
    expect(screen.getByText(/분석 j2/)).toBeInTheDocument();
    // ungrouped 행에는 붙지 않는다 — 비교할 상대가 없다.
    expect(screen.queryByText(/분석 j3/)).toBeNull();
  });

  it("keeps each member's own confirm/reject affordance inside the group", async () => {
    // over-strict: 그룹을 만들었다고 개별 경로를 뺏으면 실패한다. 그룹 안
    // 2명 + ungrouped 1명 = 개별 버튼 3쌍.
    mockFetch({ body: mixedInbox() });
    renderInbox();
    await screen.findByText(/같은 대상으로 묶였습니다/);

    expect(screen.getAllByRole("button", { name: "승인" })).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: "거절" })).toHaveLength(3);
  });

  it("collapses and expands the members of a group", async () => {
    mockFetch({ body: mixedInbox() });
    renderInbox();
    const toggle = await screen.findByRole("button", { name: "접기" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(toggle);

    expect(screen.queryByText("서윤")).toBeNull();
    // 그룹 머리와 그룹 액션은 접어도 남는다 — 접힌 그룹도 처리할 수 있어야 한다.
    expect(screen.getByText(/같은 대상으로 묶였습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "그룹 승인" })).toBeEnabled();
    // ungrouped 행은 그룹 접기의 영향을 받지 않는다.
    expect(screen.getByText("이설")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "펼치기" }));
    expect(screen.getAllByText("서윤")).toHaveLength(2);
  });

  it("approves a group with the revision the read surface gave it, then re-reads", async () => {
    const fetchMock = mockFetch(
      { body: mixedInbox() },
      {
        body: {
          group_id: "g-1", expected_revision: 3, canonical_memory_id: "m-1",
          steps: [
            { candidate_id: "c1", status: "applied", action: "create",
              memory_id: "m-1", version: 1, error: null },
            { candidate_id: "c2", status: "applied", action: "add_evidence",
              memory_id: "m-1", version: 2, error: null },
          ],
          idempotent_replay: false,
        },
      },
      { body: inboxBody({ items: [], gate_findings: [] }) },
    );
    renderInbox();

    await userEvent.click(
      await screen.findByRole("button", { name: "그룹 승인" }),
    );

    await waitFor(() =>
      expect(screen.getByText("검토할 기억 후보가 없습니다.")).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/review-inbox/groups/g-1/approve",
    );
    // revision 이 멱등 key 를 겸한다(D1=A) — 읽기면이 준 값 그대로여야 한다.
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      expected_revision: 3,
    });
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/projects/p1/analysis/review-inbox",
    );
    expect(screen.getByText(/그룹 승인 — 반영 2건/)).toBeInTheDocument();
  });

  it("rejects a group with no request body and reports what it skipped", async () => {
    const fetchMock = mockFetch(
      { body: mixedInbox() },
      {
        body: {
          group_id: "g-1", rejected: ["c1"], skipped: ["c2"],
          idempotent_replay: false,
        },
      },
      { body: inboxBody({ items: [member("c9", "j3", "이설", null)],
                          gate_findings: [] }) },
    );
    renderInbox();

    await userEvent.click(
      await screen.findByRole("button", { name: "그룹 거절" }),
    );

    await waitFor(() =>
      expect(screen.getByText(/거절 1건 · 건너뜀 1건/)).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/projects/p1/analysis/review-inbox/groups/g-1/reject",
    );
    // 멱등을 상태에서 유도한다(Slice 4) — body 를 실으면 계약이 갈린다.
    expect(fetchMock.mock.calls[1][1].body).toBeUndefined();
  });

  it("keeps a partial approval visible instead of closing it like a success", async () => {
    // D4=A: 첫 판정 실패에 그 step=failed·패스 종료. 응답은 200 이라 화면이
    // 아무 말도 안 하면 사용자는 끝난 줄 안다 — 남은 조치가 보여야 한다.
    mockFetch(
      { body: mixedInbox() },
      {
        body: {
          group_id: "g-1", expected_revision: 3, canonical_memory_id: "m-1",
          steps: [
            { candidate_id: "c1", status: "applied", action: "create",
              memory_id: "m-1", version: 1, error: null },
            { candidate_id: "c2", status: "failed", action: null,
              memory_id: null, version: null, error: "InvalidJudgeResult" },
          ],
          idempotent_replay: false,
        },
      },
      { body: mixedInbox() },
    );
    renderInbox();

    await userEvent.click(
      await screen.findByRole("button", { name: "그룹 승인" }),
    );

    // 재조회가 목록을 갈아 끼워도 결과 상자는 남는다.
    await waitFor(() => expect(screen.getByText("실패")).toBeInTheDocument());
    expect(screen.getByText("반영됨")).toBeInTheDocument();
    expect(screen.getByText(/InvalidJudgeResult/)).toBeInTheDocument();
    expect(screen.getByText(/1건이 남았습니다/)).toBeInTheDocument();
  });

  it("marks conflict members as unfinished work rather than as applied", async () => {
    // conflict 는 needs_review 잔류 + 대기열 적재(D2=A)다. "성공 2건"으로 세면
    // 사용자가 대기열을 안 본다.
    mockFetch(
      { body: mixedInbox() },
      {
        body: {
          group_id: "g-1", expected_revision: 3, canonical_memory_id: "m-1",
          steps: [
            { candidate_id: "c1", status: "applied", action: "create",
              memory_id: "m-1", version: 1, error: null },
            { candidate_id: "c2", status: "conflict", action: null,
              memory_id: null, version: null, error: null },
          ],
          idempotent_replay: false,
        },
      },
      { body: mixedInbox() },
    );
    renderInbox();

    await userEvent.click(
      await screen.findByRole("button", { name: "그룹 승인" }),
    );

    await waitFor(() =>
      expect(screen.getByText("충돌 — 검토 대기열로")).toBeInTheDocument(),
    );
    expect(screen.getByText(/그룹 승인 — 반영 1건/)).toBeInTheDocument();
    expect(screen.getByText(/1건이 남았습니다/)).toBeInTheDocument();
  });

  it("warns on a contradicted group instead of grouping it silently", async () => {
    mockFetch({
      body: inboxBody({
        items: [
          member("c1", "j1", "서윤", group({ group_status: "contradicted" })),
          member("c2", "j2", "서윤", group({ group_status: "contradicted" })),
        ],
        gate_findings: [],
      }),
    });
    renderInbox();

    expect(
      await screen.findByText(/상충하는 판정이 있는 그룹입니다/),
    ).toBeInTheDocument();
    // 경고를 달아도 그룹 액션은 막지 않는다 — 서버가 contradicted 를 거절·승인
    // 대상으로 받는다(읽기면 정본과 같은 순서).
    expect(screen.getByRole("button", { name: "그룹 승인" })).toBeEnabled();
  });

  it("surfaces a stale-revision 409 and keeps the group on screen", async () => {
    mockFetch(
      { body: mixedInbox() },
      { status: 409, body: { detail: "expected revision 3 but the group is at revision 4" } },
    );
    renderInbox();

    await userEvent.click(
      await screen.findByRole("button", { name: "그룹 승인" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("revision 4");
    expect(screen.getByText(/같은 대상으로 묶였습니다/)).toBeInTheDocument();
  });

  it("shows every group action even when the group has no rationale", async () => {
    // `identity_rationale_summary` 는 없을 수 있다(same relation 이 없는 그룹).
    // 없는 사실을 지어내지 않되, 그것 때문에 처리를 못 하게 하지도 않는다.
    mockFetch({
      body: inboxBody({
        items: [
          member("c1", "j1", "서윤", group({ identity_rationale_summary: null })),
          member("c2", "j2", "서윤", group({ identity_rationale_summary: null })),
        ],
        gate_findings: [],
      }),
    });
    renderInbox();

    await screen.findByText(/같은 대상으로 묶였습니다/);
    expect(screen.queryByText(/근거 —/)).toBeNull();
    expect(screen.getByRole("button", { name: "그룹 승인" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "그룹 거절" })).toBeEnabled();
  });

  it("leaves the flat list untouched when nothing is grouped", async () => {
    // over-strict: 모든 후보를 그룹 상자로 감싸는 과잉 교정을 막는다. Slice 3
    // 이 확정한 대로 가시 멤버 < 2인 그룹은 서버가 이미 ungrouped 로 읽는다 —
    // 화면이 그 판단을 되돌리면 안 된다.
    mockFetch({ body: inboxBody() });
    renderInbox();

    await screen.findByText("인물");
    expect(screen.queryByText(/같은 대상으로 묶였습니다/)).toBeNull();
    expect(screen.queryByRole("button", { name: "그룹 승인" })).toBeNull();
    expect(screen.queryByRole("list", { name: "그룹 안 후보 목록" })).toBeNull();
  });
});
