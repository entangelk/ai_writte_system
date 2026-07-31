import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingPanel } from "./WritingPanel";
import {
  resetWritingBudgetCache,
  seedWritingBudgetCache,
} from "./useWritingBudget";

type PanelProps = ComponentProps<typeof WritingPanel>;

type MockResponse = { status?: number; body: unknown };

function response({ status = 200, body }: MockResponse) {
  return { ok: status >= 200 && status < 300, status, statusText: "", json: async () => body };
}

function mockFetch(...responses: MockResponse[]) {
  const fetchMock = vi.fn();
  for (const next of responses) fetchMock.mockResolvedValueOnce(response(next));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// crypto.randomUUID mints "uuid-1", "uuid-2", … so generate's request_id and the
// accept idempotency key are distinguishable and key reuse is observable.
function stubIncrementingUuid() {
  let n = 0;
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `uuid-${++n}`) });
}

const candidate = {
  request_id: "uuid-1",
  project_id: "p1",
  task_type: "continue_scene",
  output_type: "draft_patch",
  text: "아린은 성문을 지나 도시로 들어섰다.",
  status: "candidate",
  self_reported_constraints: [],
  candidate_claims: [],
  new_memory_hints: [],
  risk_notes: [],
  candidate_id: null,
  generated_by_model: "fake-writer",
};

// 증분 2c (D5=A): medium/long presets get a 202 job reference instead of a
// candidate. Shape mirrors WritingGenerationJobAcceptedPayload.
const generationJobAccepted = {
  job: {
    job_id: "wgj-1",
    request_id: "uuid-1",
    project_id: "p1",
    draft_id: "d1",
    version_id: "v1",
    task_type: "continue_scene",
    output_length: "medium",
    status: "pending",
    created_at: "2026-07-21T00:00:00Z",
    result_scratch_id: null,
    failure_reason: null,
    failure_detail: null,
  },
  idempotent_replay: false,
};

const gatePass = {
  request_id: "uuid-1",
  project_id: "p1",
  decision: "pass",
  findings: [],
  checked_constraints: [],
  evaluated_by_model: "fake-gate",
};

const gateRevise = {
  request_id: "uuid-1",
  project_id: "p1",
  decision: "revise",
  findings: [
    {
      type: "continuity",
      severity: "error",
      message: "앞 문단과 상태가 다르다.",
      evidence: "문을 열었다",
      recommended_decision: "revise",
    },
  ],
  checked_constraints: [],
  evaluated_by_model: "fake-gate",
};

const gateEligibleRevise = {
  ...gateRevise,
  findings: [
    {
      ...gateRevise.findings[0],
      evidence: "도시로 들어섰다",
    },
  ],
};

const revisedCandidate = {
  ...candidate,
  text: "아린은 열린 성문을 지나 조심스럽게 도시로 들어섰다.",
  generated_by_model: "fake-reviser",
};

const loopStages = [
  { stage: "revise", ordinal: 1, status: "completed" },
  { stage: "report", ordinal: 2, status: "completed" },
  { stage: "gate", ordinal: 3, status: "completed" },
];

function loopResponse(
  status:
    | "pass"
    | "terminal_decision"
    | "not_eligible"
    | "budget_exhausted"
    | "no_change"
    | "failed",
  overrides: Record<string, unknown> = {},
) {
  return {
    candidate: revisedCandidate,
    gate: status === "pass" ? gatePass : gateEligibleRevise,
    loop: {
      status,
      revision_rounds: 1,
      retrieval_rounds: 0,
      gate_evaluations: 1,
    },
    stages: loopStages,
    audit_id: null,
    audit_error: null,
    ...overrides,
  };
}

const saved = {
  draft_id: "d1",
  draft_version_id: "v4",
  version_number: 4,
  snapshot_id: "s4",
  content_hash: "h4",
  unit_kind: "chapter",
  position: 1,
};

const acceptOk = {
  accepted: true,
  intent: "append_current",
  gate: gatePass,
  saved,
  analysis_job: {
    id: "job-1",
    project_id: "p1",
    snapshot_id: "s4",
    status: "pending",
    failure_reason: null,
    failure_detail: null,
  },
  idempotent_replay: false,
};

function renderPanel(overrides: Partial<PanelProps> = {}) {
  const onAccepted = vi.fn();
  const props: PanelProps = {
    projectId: "p1",
    draftId: "d1",
    latestVersionId: "v3",
    onLatest: true,
    dirty: false,
    hasVersions: true,
    readOnly: false,
    onAccepted,
    ...overrides,
  };
  const utils = render(<WritingPanel {...props} />);
  return { ...utils, onAccepted };
}

const generateButton = () => screen.getByRole("button", { name: "이어쓰기 생성" });
const acceptButton = () => screen.getByRole("button", { name: /채택하고 저장|채택 중/ });

async function generateAndGate(fetchMock: ReturnType<typeof mockFetch>) {
  await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
  await userEvent.click(generateButton());
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(generateButton()).toBeEnabled());
}

beforeEach(() => {
  stubIncrementingUuid();
  // K-4: WritingPanel mount 시 /writing/budget GET 이 발생 — 캐시 시드로 fetch 를 스킵해
  // 기존 mockResolvedValueOnce(generate→gate) 시퀀스를 건드리지 않는다.
  resetWritingBudgetCache();
  seedWritingBudgetCache("p1", { short: 8192, medium: 8192, long: 8192 });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("WritingPanel — D1 clean-latest gating", () => {
  // Each blocked state must NAME why it is unavailable and the resolving action,
  // and disable generate — never a bare disabled control (brief D1=A).
  const blocked: Array<[string, Partial<PanelProps>, string, string]> = [
    [
      "archived",
      { readOnly: true },
      "보관된 원고에서는 이어쓰기를 생성할 수 없습니다.",
      "원고 보관을 해제하면 다시 생성할 수 있습니다.",
    ],
    [
      "zero versions",
      { hasVersions: false },
      "아직 저장된 version이 없습니다.",
      "본문을 먼저 저장해 첫 version을 만든 뒤 이어쓰기를 생성하세요.",
    ],
    [
      "dirty",
      { dirty: true },
      "저장하지 않은 변경 사항이 있습니다.",
      "현재 변경을 먼저 저장한 뒤 이어쓰기를 생성하세요.",
    ],
    [
      "past version",
      { onLatest: false },
      "과거 version을 보고 있습니다.",
      "최신 version으로 돌아온 뒤 이어쓰기를 생성하세요.",
    ],
  ];

  for (const [name, override, reason, resolution] of blocked) {
    it(`blocks generate and explains why: ${name}`, () => {
      const fetchMock = mockFetch();
      renderPanel(override);
      expect(screen.getByText(reason)).toBeInTheDocument();
      expect(screen.getByText(resolution)).toBeInTheDocument();
      expect(generateButton()).toBeDisabled();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }

  it("keeps generate disabled while blocked even after an instruction is typed", async () => {
    // over-strict: typing must not re-enable generate on a blocked (dirty) state.
    const fetchMock = mockFetch();
    renderPanel({ dirty: true });
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    expect(generateButton()).toBeDisabled();
    fireEvent.submit(screen.getByLabelText("이어쓰기 지시").closest("form")!);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("enables generate on a clean latest once a non-blank instruction is typed", async () => {
    mockFetch();
    renderPanel();
    // over-strict: blank/whitespace-only stays disabled; a real instruction enables.
    expect(generateButton()).toBeDisabled();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "   ");
    expect(generateButton()).toBeDisabled();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    expect(generateButton()).toBeEnabled();
  });
});

describe("WritingPanel — generate → gate", () => {
  it("runs generate then gate on the latest base and shows candidate + findings", async () => {
    const fetchMock = mockFetch({ body: candidate }, { body: gateRevise });
    renderPanel();
    await generateAndGate(fetchMock);

    const [genUrl, genInit] = fetchMock.mock.calls[0];
    expect(genUrl).toBe("/api/projects/p1/writing/generate");
    expect(JSON.parse(genInit.body)).toEqual({
      request_id: "uuid-1",
      instruction: "이어서 써줘",
      draft_excerpt: "",
      max_tokens: 8192,
      output_length: "short",
      task_type: "continue_scene",
      current_position: { draft_id: "d1", version_id: "v3" },
    });

    const [gateUrl, gateInit] = fetchMock.mock.calls[1];
    expect(gateUrl).toBe("/api/projects/p1/writing/gate");
    expect(JSON.parse(gateInit.body).candidate_text).toBe(candidate.text);
    expect(JSON.parse(gateInit.body).current_position).toEqual({
      draft_id: "d1",
      version_id: "v3",
    });

    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    // Gate decision + each finding field (type/severity/message/evidence/recommended).
    expect(screen.getByText(/수정 필요 \(revise\)/)).toBeInTheDocument();
    expect(screen.getByText("[error] continuity → revise")).toBeInTheDocument();
    expect(screen.getByText("앞 문단과 상태가 다르다.")).toBeInTheDocument();
    expect(screen.getByText("근거: 문을 열었다")).toBeInTheDocument();
  });

  it("prevents a duplicate generate while one is in flight", async () => {
    let release!: (value: unknown) => void;
    const pending = new Promise((resolve) => { release = resolve; });
    const fetchMock = vi.fn()
      .mockReturnValueOnce(pending)
      .mockResolvedValueOnce(response({ body: gatePass }));
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    const form = screen.getByLabelText("이어쓰기 지시").closest("form")!;
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.submit(form); // ignored while the first generate is in flight
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Let the in-flight generate settle so its gate follow-up runs, keeping the
    // state updates inside the test (no act warning).
    release(response({ body: candidate }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await screen.findByText(candidate.text);
  });

  it("preserves the candidate and offers retry when the gate call fails after generate", async () => {
    // transport/5xx on gate: keep the candidate, no gate, accept stays disabled.
    // The raw detail is mapped to human guidance + a retry affordance (2026-07-18
    // test-bed UX) so a 5xx is not a dead-end.
    const fetchMock = mockFetch({ body: candidate }, { status: 502, body: { detail: "gate down" } });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("다시 생성해 주세요");
    expect(screen.getByRole("button", { name: "다시 생성" })).toBeInTheDocument();
    expect(acceptButton()).toBeDisabled();
  });

  it("maps a 502 report failure on generate to human guidance and retries", async () => {
    // The owner's real 502 (intermittent 12B non-array report). It must not be a
    // raw dead-end: friendly copy + a retry that re-invokes generate.
    const fetchMock = mockFetch(
      { status: 502, body: { detail: "invalid_candidate_report: report field must be an array" } },
      { body: candidate }, // retry generate succeeds
      { body: gatePass }, // its gate
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "근거 보고서를 형식에 맞게 만들지 못했습니다",
    );
    await userEvent.click(screen.getByRole("button", { name: "다시 생성" }));
    await screen.findByText(candidate.text);
    expect(fetchMock).toHaveBeenCalledTimes(3); // failed generate + retry generate + gate
  });

  it("shows coarse pipeline progress: generate phase then Gate phase (SoT v1.7.6 C)", async () => {
    // Observability contract: the server-side pipeline is surfaced as phases so
    // it is not a black box. Removing setProgress must fail this (under-strict).
    let releaseGen!: (v: unknown) => void;
    const genPending = new Promise((r) => { releaseGen = r; });
    let releaseGate!: (v: unknown) => void;
    const gatePending = new Promise((r) => { releaseGate = r; });
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(genPending)
      .mockReturnValueOnce(gatePending);
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    fireEvent.submit(screen.getByLabelText("이어쓰기 지시").closest("form")!);
    // generate in flight → generate-phase progress.
    expect(
      await screen.findByText("근거를 검색하고 초안을 생성하는 중…"),
    ).toBeInTheDocument();
    // generate resolves → gate in flight → gate-phase progress.
    releaseGen(response({ body: candidate }));
    expect(
      await screen.findByText("Gate로 근거를 평가하는 중…"),
    ).toBeInTheDocument();
    // gate resolves → progress cleared.
    releaseGate(response({ body: gatePass }));
    await screen.findByText(candidate.text);
    await waitFor(() =>
      expect(
        screen.queryByText("Gate로 근거를 평가하는 중…"),
      ).not.toBeInTheDocument(),
    );
  });

  it("summarizes the candidate's report output (근거 주장 count) (SoT v1.7.6 C)", async () => {
    // The report enrichment result must be visible as a count — removing the
    // candidate-summary render must fail this (under-strict).
    const withClaims = {
      ...candidate,
      candidate_claims: [
        { text: "a", type: "narrative_event", requires_gate_check: true, related_context_pointers: [] },
        { text: "b", type: "character_state", requires_gate_check: false, related_context_pointers: [] },
      ],
      risk_notes: [{ type: "pov", severity: "low", message: "m" }],
    };
    const fetchMock = mockFetch({ body: withClaims }, { body: gatePass });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(screen.getByText(/근거 주장 2개/)).toBeInTheDocument();
    expect(screen.getByText(/위험 지적 1개/)).toBeInTheDocument();
  });
});

describe("WritingPanel — automatic revise/retrieve loop", () => {
  it("enters revise-and-gate only for an eligible finding and sends the exact request", async () => {
    const warning = {
      ...gateEligibleRevise.findings[0],
      severity: "warning",
      evidence: "성문을 지나",
      message: "경미한 연결 문제",
    };
    const error = {
      ...gateEligibleRevise.findings[0],
      evidence: "도시로 들어섰다",
      message: "중대한 연결 문제",
    };
    const laterError = {
      ...gateEligibleRevise.findings[0],
      evidence: "아린은",
      message: "뒤에 나온 중대한 연결 문제",
    };
    const fetchMock = mockFetch(
      { body: candidate },
      { body: { ...gateEligibleRevise, findings: [warning, error, laterError] } },
      { body: loopResponse("pass") },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/writing/revise-and-gate");
    expect(JSON.parse(init.body)).toEqual({
      request_id: "uuid-1",
      instruction: "이어서 써줘",
      candidate_text: candidate.text,
      finding: error,
      max_tokens: 8192,
      task_type: "continue_scene",
      current_position: { draft_id: "d1", version_id: "v3" },
      persist_audit: false,
    });
    expect(screen.getByText(revisedCandidate.text)).toBeInTheDocument();
    expect(screen.getByText("자동 개선 완료")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "자동 개선 단계" })).toHaveTextContent(
      "1. 후보 수정완료",
    );
    expect(acceptButton()).toBeEnabled();
  });

  it("does not enter the loop for a non-continuity or non-unique evidence finding", async () => {
    // Both directions of the safe subset: a normal eligible finding enters in
    // the previous test; broader revise findings remain manual and make no call.
    const unsafe = {
      ...gateRevise,
      findings: [
        { ...gateRevise.findings[0], type: "pov", evidence: "성문을 지나" },
        { ...gateRevise.findings[0], evidence: "문장" },
      ],
    };
    const fetchMock = mockFetch({ body: candidate }, { body: unsafe });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
  });

  it("does not enter the loop when eligible evidence appears more than once", async () => {
    // over-strict counterpart to the eligible one-occurrence case: changing the
    // production guard from === 1 to >= 1 must make this test fail.
    const repeatedCandidate = {
      ...candidate,
      text: `${candidate.text} 다시 도시로 들어섰다.`,
    };
    const fetchMock = mockFetch(
      { body: repeatedCandidate },
      { body: gateEligibleRevise },
    );
    renderPanel();
    await generateAndGate(fetchMock);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText(repeatedCandidate.text)).toBeInTheDocument();
  });

  it("does not enter the loop for a non-revise Gate decision", async () => {
    const fetchMock = mockFetch(
      { body: candidate },
      { body: { ...gateEligibleRevise, decision: "retrieve_more" } },
    );
    renderPanel();
    await generateAndGate(fetchMock);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
  });

  it.each([
    ["pass", "자동 개선 완료", "채택해 저장할 수 있습니다."],
    ["terminal_decision", "자동 개선 중단", "사용자 판단이 필요한 Gate 결과입니다."],
    ["not_eligible", "자동 수정 대상 아님", "안전하게 자동 수정할 수 없는 지적입니다."],
    ["budget_exhausted", "자동 개선 한도 도달", "마지막 후보를 보존했습니다."],
    ["no_change", "수정 결과 변화 없음", "후보가 달라지지 않았습니다."],
    ["failed", "자동 개선 실패", "오류 안내에 따라 재시도하거나 새로 생성하세요."],
  ] as const)("maps %s to a distinct next action", async (status, label, action) => {
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { body: loopResponse(status) },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(action))).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "자동 개선 다시 시도" }),
    ).not.toBeInTheDocument();
  });

  it("preserves a 5xx partial candidate, shows its typed error, and retries the same intent", async () => {
    const partial = loopResponse("failed", {
      gate: null,
      stages: [
        { stage: "revise", ordinal: 1, status: "completed" },
        { stage: "report", ordinal: 2, status: "failed" },
      ],
      report_error: { type: "provider_timeout", detail: "report timed out" },
    });
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { status: 504, body: partial },
      { body: loopResponse("pass") },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());

    expect(await screen.findByText(revisedCandidate.text)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "504 · provider_timeout: report timed out",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("다시 시도할 수 있습니다.");
    const retry = screen.getByRole("button", { name: "자동 개선 다시 시도" });
    await userEvent.click(retry);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual(
      JSON.parse(fetchMock.mock.calls[2][1].body),
    );
    expect(await screen.findByText("자동 개선 완료")).toBeInTheDocument();
  });

  it("preserves a 400 partial candidate and marks it non-retryable", async () => {
    const partial = loopResponse("failed", {
      candidate,
      gate: null,
      stages: [{ stage: "revise", ordinal: 1, status: "failed" }],
      revision_error: {
        type: "writing_revision_error",
        detail: "finding is no longer valid",
      },
    });
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { status: 400, body: partial },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    expect(await screen.findByText(candidate.text)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "400 · writing_revision_error: finding is no longer valid",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "같은 요청 재시도보다 지시나 후보를 수정해야 합니다.",
    );
    expect(
      screen.queryByRole("button", { name: "자동 개선 다시 시도" }),
    ).not.toBeInTheDocument();
  });

  it.each([
    ["gate_error", "invalid_gate_result", "gate output was invalid"],
    ["retrieval_error", "retrieval_not_configured", "retrieval is unavailable"],
  ] as const)("shows the %s partial discriminator", async (key, type, detail) => {
    const partial = loopResponse("failed", {
      gate: null,
      stages: [{ stage: "gate", ordinal: 1, status: "failed" }],
      [key]: { type, detail },
    });
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { status: 502, body: partial },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("alert")).toHaveTextContent(`502 · ${type}: ${detail}`);
  });

  it("accepts the loop's final candidate text (candidate-change safety)", async () => {
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { body: loopResponse("pass") },
      { body: acceptOk },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await screen.findByText(revisedCandidate.text);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const accepted = JSON.parse(fetchMock.mock.calls[3][1].body);
    expect(accepted.candidate_text).toBe(revisedCandidate.text);
    expect(accepted.idempotency_key).toBe("uuid-2");
  });
});

describe("WritingPanel — output-length preset (증분 2)", () => {
  it("defaults to short and sends the selected preset on generate", async () => {
    // medium is async under 증분 2c: generate returns 202 (a job ref), so there is
    // no Gate fetch (1 fetch total) and a background-started notice shows. The
    // preset still flows to the request body.
    const fetchMock = mockFetch({ status: 202, body: generationJobAccepted });
    renderPanel();
    // The select starts on short; picking medium must flow to the generate body.
    expect((screen.getByLabelText("생성 분량") as HTMLSelectElement).value).toBe(
      "short",
    );
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "medium");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).output_length).toBe(
      "medium",
    );
    expect(
      screen.getByText(
        "백그라운드 생성을 시작했습니다. 완료되면 결과 패드에 표시됩니다.",
      ),
    ).toBeInTheDocument();
  });

  it("async presets (long) start background generation and skip Gate/loop", async () => {
    // long is async under 증분 2c: generate returns 202, so neither Gate nor the
    // revise-and-gate loop runs (1 fetch total). over-strict guard: dropping the
    // `"job" in produced` early return would call gateWriting (a 2nd fetch) and
    // crash reading produced.text on the job-ref body.
    const fetchMock = mockFetch({ status: 202, body: generationJobAccepted });
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "long");
    await userEvent.click(generateButton());
    await waitFor(() => expect(generateButton()).toBeEnabled());
    expect(fetchMock).toHaveBeenCalledTimes(1); // generate only — no gate, no loop
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).output_length).toBe("long");
    expect(
      screen.getByText(
        "백그라운드 생성을 시작했습니다. 완료되면 결과 패드에 표시됩니다.",
      ),
    ).toBeInTheDocument();
  });

  it("hands the enqueued job to onAsyncJobStarted so the pad can poll it (증분 3)", async () => {
    // The async branch must forward the 202 job reference to the parent, which
    // owns polling + the result pad. under-strict: dropping the callback would
    // leave the background job untracked (result never surfaces). over-strict: a
    // sync short generate must NOT fire it (asserted in the short test below).
    mockFetch({ status: 202, body: generationJobAccepted });
    const onAsyncJobStarted = vi.fn();
    renderPanel({ onAsyncJobStarted });
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "medium");
    await userEvent.click(generateButton());
    await waitFor(() => expect(onAsyncJobStarted).toHaveBeenCalledTimes(1));
    expect(onAsyncJobStarted.mock.calls[0][0].job_id).toBe("wgj-1");
  });

  it("does not fire onAsyncJobStarted for a synchronous short generate (증분 3)", async () => {
    // over-strict guard: short is sync (candidate + Gate), never an async job.
    mockFetch({ body: candidate }, { body: gatePass });
    const onAsyncJobStarted = vi.fn();
    renderPanel({ onAsyncJobStarted });
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "short");
    await userEvent.click(generateButton());
    await waitFor(() => expect(screen.getByText(candidate.text)).toBeInTheDocument());
    expect(onAsyncJobStarted).not.toHaveBeenCalled();
  });

  it("short preset stays synchronous (candidate + Gate, not async)", async () => {
    // over-strict guard: short must NOT take the async branch. It returns a real
    // candidate and runs Gate (2 fetches) with no background-started notice.
    // Flipping short into the async branch would drop this to 1 fetch + notice.
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "short");
    await userEvent.click(generateButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).output_length).toBe(
      "short",
    );
    expect(
      screen.queryByText(
        "백그라운드 생성을 시작했습니다. 완료되면 결과 패드에 표시됩니다.",
      ),
    ).not.toBeInTheDocument();
  });
});

describe("WritingPanel — style advisory (증분 3)", () => {
  const gatePassWithStyle = {
    ...gatePass,
    findings: [
      {
        type: "style",
        severity: "warning",
        message: "설정한 문체와 어조가 다릅니다.",
        evidence: "그는 말했다",
        recommended_decision: "needs_user_review",
      },
    ],
  };

  it("keeps accept enabled on a pass and shows the style finding as advisory", async () => {
    // D5=A/D6=A: a style finding is advisory — decision stays pass, so accept is
    // enabled and the author sees the note. If style escalated the decision, accept
    // would be disabled and this fails.
    const fetchMock = mockFetch({ body: candidate }, { body: gatePassWithStyle });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(acceptButton()).toBeEnabled();
    expect(screen.getByText("설정한 문체와 어조가 다릅니다.")).toBeInTheDocument();
    expect(
      screen.getByText(/문체 참고 사항입니다.*채택할 수 있습니다/),
    ).toBeInTheDocument();
    // style is not auto-revise eligible → no loop call, only generate + gate.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("WritingPanel — accept (pass only)", () => {
  it("enables accept only on a pass gate", async () => {
    const fetchMock = mockFetch({ body: candidate }, { body: gateRevise });
    renderPanel();
    await generateAndGate(fetchMock);
    // revise → disabled, with the pass-only explanation.
    expect(acceptButton()).toBeDisabled();
    expect(
      screen.getByText("Gate 판정이 pass일 때만 채택할 수 있습니다."),
    ).toBeInTheDocument();
  });

  it("accepts a pass candidate, binds the exact body, reloads, and clears", async () => {
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { body: acceptOk },
    );
    const { onAccepted } = renderPanel();
    await generateAndGate(fetchMock);
    expect(acceptButton()).toBeEnabled();
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    const [acceptUrl, acceptInit] = fetchMock.mock.calls[2];
    expect(acceptUrl).toBe("/api/projects/p1/writing/accept");
    expect(JSON.parse(acceptInit.body)).toEqual({
      request_id: "uuid-1",
      draft_id: "d1",
      base_version_id: "v3",
      instruction: "이어서 써줘",
      candidate_text: candidate.text,
      draft_excerpt: "",
      max_tokens: 8192,
      task_type: "continue_scene",
      output_type: "draft_patch",
      current_position: { draft_id: "d1", version_id: "v3" },
      intent: "append_current",
      next_unit: null,
      idempotency_key: "uuid-2",
    });
    expect(onAccepted).toHaveBeenCalledTimes(1);
    // Candidate consumed after a successful save.
    await waitFor(() => expect(screen.queryByText(candidate.text)).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("채택되어 새 version으로 저장됐습니다.");
  });

  it("sends intent=start_next_unit with the next-unit metadata (goal not persisted client-side)", async () => {
    const startAccept = { ...acceptOk, intent: "start_next_unit" };
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { body: startAccept },
    );
    renderPanel();
    await userEvent.click(screen.getByLabelText("다음 유닛 시작"));
    await userEvent.type(screen.getByLabelText("새 유닛 제목"), "2장 — 성 안");
    await userEvent.selectOptions(screen.getByLabelText("유닛 종류"), "scene");
    await userEvent.type(screen.getByLabelText("유닛 목표(선택)"), "반전을 심는다");
    await generateAndGate(fetchMock);
    expect(acceptButton()).toBeEnabled();
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const body = JSON.parse(fetchMock.mock.calls[2][1].body);
    expect(body.intent).toBe("start_next_unit");
    expect(body.next_unit).toEqual({
      title: "2장 — 성 안",
      unit_kind: "scene",
      goal: "반전을 심는다",
    });
    expect(screen.getByRole("status")).toHaveTextContent("새 유닛으로 채택·저장됐습니다.");
  });

  it("blocks accept when starting the next unit without a title", async () => {
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await userEvent.click(screen.getByLabelText("다음 유닛 시작"));
    await generateAndGate(fetchMock);
    // Gate passed, but a blank next-unit title keeps accept disabled.
    expect(acceptButton()).toBeDisabled();
    expect(
      screen.getByText("새 유닛 제목을 입력해야 채택할 수 있습니다."),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("새 유닛 제목"), "2장");
    expect(acceptButton()).toBeEnabled();
  });

  it("treats 200 accepted=false as a Gate result, not a failure (candidate kept)", async () => {
    const acceptNonPass = { accepted: false, gate: gateRevise, saved: null, analysis_job: null, idempotent_replay: false };
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass }, { body: acceptNonPass });
    const { onAccepted } = renderPanel();
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(onAccepted).not.toHaveBeenCalled();
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("채택되지 않았습니다");
    // The re-gate result replaces the shown gate; accept disables (now revise).
    expect(screen.getByText("[error] continuity → revise")).toBeInTheDocument();
    expect(acceptButton()).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("treats 502 + accepted=true + saved as a saved version with a failed analysis", async () => {
    const partial = { accepted: true, saved, analysis_job: null, analysis_error: "job store down" };
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass }, { status: 502, body: partial });
    const { onAccepted } = renderPanel();
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(onAccepted).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status")).toHaveTextContent("분석 작업은 실패해 재시도가 필요합니다");
    expect(screen.queryByText(candidate.text)).not.toBeInTheDocument();
    // A saved 502 partial is NOT surfaced as an error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the candidate and steers to reload on a 409 stale base", async () => {
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { status: 409, body: { detail: "base draft version is not the latest version" } },
    );
    const { onAccepted } = renderPanel();
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(onAccepted).not.toHaveBeenCalled();
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("최신 version을 불러온 뒤 다시 생성하세요");
  });

  it("reuses the same idempotency key when retrying the same body after a 5xx", async () => {
    // under-strict: a transport/5xx retry of the SAME candidate must replay with
    // the SAME key (no duplicate-intent). A new UUID here would be a bug.
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { status: 500, body: { detail: "boom" } },
      { body: acceptOk },
    );
    renderPanel();
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    // candidate preserved for retry
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const firstKey = JSON.parse(fetchMock.mock.calls[2][1].body).idempotency_key;
    const retryKey = JSON.parse(fetchMock.mock.calls[3][1].body).idempotency_key;
    expect(firstKey).toBe("uuid-2");
    expect(retryKey).toBe("uuid-2");
  });

  it("mints a NEW key when the accept body changes before retrying (over-strict)", async () => {
    // The counterpart of the reuse test: if the accept body changes (here the
    // instruction is edited after generate, no regenerate), the retry must NOT
    // replay the previous key. This pins the signature guard directly — removing
    // it would reuse uuid-2. Load-bearing once candidates become mutable (C2/D4=B):
    // replaying a different candidate under the same key would let the server's
    // key-only idempotency silently return the old version (verification H1).
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { status: 500, body: { detail: "boom" } },
      { body: acceptOk },
    );
    renderPanel();
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    // change the request body (instruction) without regenerating the candidate
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), " 더 자세히");
    await userEvent.click(acceptButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const firstKey = JSON.parse(fetchMock.mock.calls[2][1].body).idempotency_key;
    const retryKey = JSON.parse(fetchMock.mock.calls[3][1].body).idempotency_key;
    expect(firstKey).toBe("uuid-2");
    expect(retryKey).toBe("uuid-3");
    expect(retryKey).not.toBe(firstKey);
  });

  it.each([400, 422])(
    "rejects definitively and keeps the candidate on a %i accept",
    async (status) => {
      // brief D2=A: 400/404/422 are definitive rejections (shown, not retried as
      // the same intent). The candidate is preserved and no save is reported.
      const fetchMock = mockFetch(
        { body: candidate },
        { body: gatePass },
        { status, body: { detail: "정본 위반" } },
      );
      const { onAccepted } = renderPanel();
      await generateAndGate(fetchMock);
      await userEvent.click(acceptButton());
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
      expect(onAccepted).not.toHaveBeenCalled();
      expect(screen.getByRole("alert")).toHaveTextContent(String(status));
      expect(screen.getByText(candidate.text)).toBeInTheDocument();
    },
  );
});

describe("WritingPanel — accept dirty guard (미저장 편집 덮어쓰기 결손 fix)", () => {
  // The candidate is generated on a clean latest, then the user types into the
  // editor (dirty=true) before accepting. Accept saves base+candidate and the
  // editor reloads to it, discarding those edits — this guard confirms first.
  const dirtyProps: PanelProps = {
    projectId: "p1",
    draftId: "d1",
    latestVersionId: "v3",
    onLatest: true,
    dirty: false, // clean at generate time; flipped to dirty before accept
    hasVersions: true,
    readOnly: false,
    onAccepted: vi.fn(),
  };

  it("aborts the accept when the discard confirm is cancelled (under-strict: the fix)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    const onAccepted = vi.fn();
    const { rerender } = render(
      <WritingPanel {...dirtyProps} onAccepted={onAccepted} />,
    );
    await generateAndGate(fetchMock);
    // The editor became dirty after generate.
    rerender(<WritingPanel {...dirtyProps} dirty onAccepted={onAccepted} />);
    await userEvent.click(acceptButton());

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2); // generate + gate only — no accept
    expect(onAccepted).not.toHaveBeenCalled();
    expect(screen.getByText(candidate.text)).toBeInTheDocument(); // candidate kept
  });

  it("proceeds with the accept once the discard is confirmed", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { body: acceptOk },
    );
    const onAccepted = vi.fn();
    const { rerender } = render(
      <WritingPanel {...dirtyProps} onAccepted={onAccepted} />,
    );
    await generateAndGate(fetchMock);
    rerender(<WritingPanel {...dirtyProps} dirty onAccepted={onAccepted} />);
    await userEvent.click(acceptButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/p1/writing/accept");
    expect(onAccepted).toHaveBeenCalledTimes(1);
  });

  it("does not prompt when the editor is clean (over-strict: no needless nag)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gatePass },
      { body: acceptOk },
    );
    renderPanel(); // dirty defaults to false
    await generateAndGate(fetchMock);
    await userEvent.click(acceptButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});

describe("WritingPanel — K-4 instruction budget counter", () => {
  it("지시문 아래에 글자수·토큰 카운터를 표시하고 예산 여유면 경고를 띄우지 않는다(under-strict)", async () => {
    // beforeEach 가 시드한 기본 예산(8192) — 작은 지시문은 여유.
    mockFetch();
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    const counter = screen.getByText(/자 \(≈\d+ 토큰\)/);
    expect(counter.className).toContain("writing-counter");
    expect(counter.className).not.toContain("writing-counter-warn");
  });

  it("해당 출력 preset 예산의 90% 를 넘으면 소프트 경고 색으로 바뀐다(하중받침)", async () => {
    // outputLength 기본 "short" → short 예산 100. 90 토큰(≈153자) 넘으면 경고.
    seedWritingBudgetCache("p1", { short: 100, medium: 8192, long: 8192 });
    mockFetch();
    renderPanel();
    // 160자 → 95 토큰 추정 → round(100 * 0.9)=90 초과 → warn.
    await userEvent.type(
      screen.getByLabelText("이어쓰기 지시"),
      "가".repeat(160),
    );
    const counter = screen.getByText(/160자/);
    expect(counter.className).toContain("writing-counter-warn");
  });

  it("preset 이 바뀌면 같은 지시문 길이에서도 경고 기준이 달라진다(over-strict)", async () => {
    // short 예산은 작게, long 예산은 크게 → 같은 160자가 short 에선 경고, long 에선 안전.
    seedWritingBudgetCache("p1", { short: 100, medium: 8192, long: 8192 });
    mockFetch();
    renderPanel();
    await userEvent.type(
      screen.getByLabelText("이어쓰기 지시"),
      "가".repeat(160),
    );
    // short(기본 preset): 경고
    expect(screen.getByText(/160자/).className).toContain(
      "writing-counter-warn",
    );
    // long preset 으로 변경 → 예산 8192 → 경고 해제
    await userEvent.selectOptions(screen.getByLabelText("생성 분량"), "long");
    expect(screen.getByText(/160자/).className).not.toContain(
      "writing-counter-warn",
    );
  });
});
