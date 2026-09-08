import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingPanel } from "./WritingPanel";
import {
  resetWritingBudgetCache,
  seedWritingBudgetCache,
} from "./useWritingBudget";
import { resetMemberQuota } from "../quota/useMemberQuota";

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
  intent: "append_current",
  next_unit: null,
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

function renderPanel(overrides: Partial<PanelProps> = {}) {
  const props: PanelProps = {
    projectId: "p1",
    draftId: "d1",
    latestVersionId: "v3",
    onLatest: true,
    dirty: false,
    hasVersions: true,
    readOnly: false,
    ...overrides,
  };
  return render(<WritingPanel {...props} />);
}

const generateButton = () => screen.getByRole("button", { name: "이어쓰기 생성" });
const copyButton = () => screen.getByRole("button", { name: /본문 복사|복사됨/ });

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
      intent: "append_current",
      next_unit: null,
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
    // Gate 가 죽어도 후보는 남고 복사 길은 열려 있다(작가가 손으로 판단해 가져간다).
    expect(copyButton()).toBeEnabled();
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
    expect(copyButton()).toBeEnabled();
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
    ["pass", "자동 개선 완료", "복사해 쓰세요."],
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

  it("carries the loop's final candidate text into the copy path (candidate-change safety)", async () => {
    // 개선 루프가 후보를 바꾸면 화면도 **바뀐 본문**을 들어야 한다 — 복사가 개선 전
    // 본문을 집어가면 작가는 자기가 본 것과 다른 글을 붙여넣게 된다.
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const fetchMock = mockFetch(
      { body: candidate },
      { body: gateEligibleRevise },
      { body: loopResponse("pass") },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await screen.findByText(revisedCandidate.text);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    copyButton().click();

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(revisedCandidate.text));
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

  it("keeps the decision at pass and shows the style finding as advisory", async () => {
    // D5=A/D6=A: a style finding is advisory — the decision stays pass, so no
    // "Gate가 통과 판정을 내리지 않았습니다" warning appears. If style escalated the
    // decision, that warning would show and this fails.
    const fetchMock = mockFetch({ body: candidate }, { body: gatePassWithStyle });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(
      screen.queryByText(/Gate가 통과 판정을 내리지 않았습니다/),
    ).not.toBeInTheDocument();
    expect(screen.getByText("설정한 문체와 어조가 다릅니다.")).toBeInTheDocument();
    expect(
      screen.getByText(/문체 참고 사항입니다.*그대로 두어도 됩니다/),
    ).toBeInTheDocument();
    // style is not auto-revise eligible → no loop call, only generate + gate.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("WritingPanel — 후보를 꺼내는 길 (오너 2026-09-08: 채택 버튼 제거)", () => {
  /**
   * 오너 결정 2026-09-08: *"채택은 완전 자동화일 때 사용할 수 있을 것 같아. 일반
   * 사용자에게는 불필요한 항목 같아. 버튼을 그냥 없애주고 통로만 열어두자."*
   *
   * 없앤 것은 **화면의 버튼**이다 — 서버 `POST …/writing/accept` 와 API 클라이언트
   * `acceptWriting` 은 그대로 있다(완전 자동화가 쓸 통로). 사람이 쓰는 길은
   * 복사 → 편집기 붙여넣기 → 저장이고, 그 저장은 유료가 아니다.
   */
  it("채택 버튼이 없고, 후보에는 복사 버튼이 있다", async () => {
    // 양방향: 채택이 되살아나면 첫 단정이, 복사까지 같이 지우면 둘째 단정이 재실패한다.
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await generateAndGate(fetchMock);

    expect(
      screen.queryByRole("button", { name: /채택/ }),
    ).not.toBeInTheDocument();
    expect(copyButton()).toBeEnabled();
    expect(
      screen.getByText(/복사해 편집기에 붙여넣고 저장하세요/),
    ).toBeInTheDocument();
    // Gate 는 그대로 돈다 — 없앤 것은 채택이지 검사가 아니다.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("Gate 가 통과가 아니어도 후보를 복사할 수 있다", async () => {
    // 종전에는 pass 가 아니면 채택이 잠겼다. 복사는 사람이 판단해서 가져가는 길이라
    // 판정으로 막지 않는다 — 대신 통과가 아니라는 사실은 말한다.
    const fetchMock = mockFetch({ body: candidate }, { body: gateRevise });
    renderPanel();
    await generateAndGate(fetchMock);

    expect(copyButton()).toBeEnabled();
    expect(
      screen.getByText(/Gate가 통과 판정을 내리지 않았습니다/),
    ).toBeInTheDocument();
  });

  it("복사 버튼이 후보 본문을 클립보드에 넣고 문구가 바뀐다", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await generateAndGate(fetchMock);

    copyButton().click();

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(candidate.text));
    expect(await screen.findByRole("button", { name: "복사됨" })).toBeInTheDocument();
    // 복사는 서버를 부르지 않는다 — 생성·Gate 두 번 그대로다(무료 경로).
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("클립보드를 못 쓰면 직접 선택해 복사하라고 말한다", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await generateAndGate(fetchMock);

    copyButton().click();

    // ★ 문구는 **버튼 옆**에 그려져야 한다 — 위쪽 오류 상자에 그리면 세로로 긴 이 패널에서
    // 화면 밖이 되고, 그것이 2026-09-07 429 와 2026-09-08 채택 400 이 두 번 안 보인 이유다.
    const note = await screen.findByText(/클립보드 복사를 사용할 수 없습니다/);
    expect(note.closest(".candidate-actions")).not.toBeNull();
    expect(note.closest(".writing-error")).toBeNull();
  });

  it("후보 본문은 기본 펼침이고 접을 수 있다 (오너 2026-09-08: 글이 너무 길다)", async () => {
    // 양방향: 기본을 접힘으로 바꾸면 첫 단정이(방금 만든 후보는 읽으라고 만든 것),
    // 접기 자체를 없애면 둘째 단정이 재실패한다. 지나간 후보(패드)는 반대로 기본 접힘.
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    const { container } = renderPanel();
    await generateAndGate(fetchMock);

    const fold = container.querySelector("details.candidate-fold") as HTMLDetailsElement;
    expect(fold.open).toBe(true);
    expect(screen.getByText(candidate.text)).toBeVisible();

    await userEvent.click(fold.querySelector("summary") as HTMLElement);

    expect(fold.open).toBe(false);
    expect(screen.getByText(candidate.text)).not.toBeVisible();
  });

  it("sends intent=start_next_unit with the next-unit metadata on generate", async () => {
    const fetchMock = mockFetch({ body: candidate }, { body: gatePass });
    renderPanel();
    await userEvent.click(screen.getByLabelText("같은 장의 다음 장면 시작"));
    await userEvent.type(screen.getByLabelText("새 장면 제목"), "성 안");
    await userEvent.type(screen.getByLabelText("장면 목표(선택)"), "반전을 심는다");
    await generateAndGate(fetchMock);

    const generated = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(generated.intent).toBe("start_next_unit");
    expect(generated.next_unit).toEqual({ title: "성 안", goal: "반전을 심는다" });
  });

  it("blocks generation when starting the next unit without a title", async () => {
    const fetchMock = mockFetch();
    renderPanel();
    await userEvent.click(screen.getByLabelText("같은 장의 다음 장면 시작"));
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    expect(generateButton()).toBeDisabled();
    await userEvent.type(screen.getByLabelText("새 장면 제목"), "장면 2");
    expect(generateButton()).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
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

describe("WritingPanel — 요청 quota (Slice 8.4 W3=A · W5=B)", () => {
  const quotaBody = {
    remaining: 12,
    unlimited: false,
    status: "active",
    daily: { limit: 20, used: 8, remaining: 12, resets_at: "2026-08-04T15:00:00Z" },
    weekly: { limit: 100, used: 30, remaining: 70, resets_at: "2026-08-08T15:00:00Z" },
  };

  function headersOf(fetchMock: ReturnType<typeof mockFetch>, index: number) {
    return new Headers(
      (fetchMock.mock.calls[index][1] as RequestInit).headers as HeadersInit,
    );
  }

  it("shows the remaining count and says one click is not one unit", () => {
    // 전역 시드(vitest.setup.ts)가 잔여 12를 준다. 숫자보다 중요한 것은 title —
    // 한 번의 생성이 유료 요청 2~3건이라 "12회 = 12번 클릭"이 아니다.
    renderPanel();
    const tile = screen.getByText("남은 사용 12회");
    expect(tile).toHaveAttribute(
      "title",
      "생성·Gate 검사·자동 개선이 각각 1회입니다.",
    );
  });

  it("asks before spending a second unit when the server locks a duplicate (429)", async () => {
    const fetchMock = mockFetch(
      { status: 429, body: { detail: "the same request is already in progress" } },
      { body: candidate },
      { body: gatePass },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());

    // 되묻는다 — 그리고 **아직 아무것도 다시 보내지 않았다**(W4=A).
    const prompt = await screen.findByRole("alertdialog", { name: "중복 요청 확인" });
    expect(prompt).toHaveTextContent("하나 더 만들까요?");
    expect(prompt).toHaveTextContent("사용량이 1회 더 듭니다");
    expect(prompt).toHaveTextContent("이번 창 잔여 12회");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "하나 더 만들기" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    // 확인은 두 번째 요청에만 실린다(첫 요청은 확인 없이 나갔다).
    expect(headersOf(fetchMock, 0).has("X-Confirm-Duplicate")).toBe(false);
    expect(headersOf(fetchMock, 1).get("X-Confirm-Duplicate")).toBe("1");
  });

  it("sends nothing when the duplicate prompt is cancelled", async () => {
    // over-strict 짝: 취소가 조용히 통과시키면 확인이 있으나 마나다.
    const fetchMock = mockFetch(
      { status: 429, body: { detail: "duplicate" } },
    );
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await screen.findByRole("alertdialog", { name: "중복 요청 확인" });
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("explains an exhausted window instead of offering a retry (402)", async () => {
    // 402는 확인으로 뚫리지 않는다 — 확인 버튼을 주면 눌러도 또 402다.
    mockFetch({ status: 402, body: { detail: "daily request quota exhausted (20/20)" } });
    renderPanel();
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("이번 사용 한도를 모두 썼습니다");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByRole("button", { name: "하나 더 만들기" })).toBeNull();
    // raw 상태코드 덤프가 아니다(8.4 이전에는 "402: …" 가 그대로 떴다).
    expect(alert).not.toHaveTextContent("402:");
  });

  it("re-reads the remaining count after a billable request", async () => {
    // 시드를 끄고 실제 조회를 켠다 — 갱신하지 않으면 화면의 숫자가 방금 쓴 1회를
    // 반영하지 않아, 사용자가 잔여를 믿을 수 없게 된다.
    resetMemberQuota();
    const fetchMock = mockFetch(
      { body: quotaBody },                                   // mount
      { body: candidate },                                   // generate
      { body: { ...quotaBody, remaining: 11 } },             // generate 뒤 갱신
      { body: gatePass },                                    // gate
      { body: { ...quotaBody, remaining: 10 } },             // gate 뒤 갱신
    );
    renderPanel();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await waitFor(() =>
      expect(screen.getByText("남은 사용 10회")).toBeInTheDocument());
  });

  it("confirms a suspension by re-reading the quota when the tile has not loaded yet", async () => {
    // 독립 검증 2026-08-04 H-1이 지적한 경합 창: 정지 계정의 **첫** 유료 요청이
    // 잔여 조회보다 먼저 도착하면 `quota` 가 아직 `null` 이라 403이 소유권 거절로
    // 위장된다. 403을 받은 그 자리에서 한 번 다시 읽어 확정한다.
    resetMemberQuota();
    const fetchMock = mockFetch(
      { status: 503, body: { detail: "quota unavailable" } },   // mount 조회 실패
      { status: 403, body: { detail: "forbidden" } },           // 유료 요청
      { body: { ...quotaBody, status: "suspended" } },          // 403 뒤 재조회
    );
    renderPanel();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "계정이 정지되어 있습니다",
    );
  });

  it("leaves an ownership 403 alone when the re-read says the account is active", async () => {
    // over-strict 짝이자 이 수정에서 가장 위험한 방향: 모든 403을 정지로 말하면
    // 남의 프로젝트를 열었을 때 "계정이 정지됐다"는 **거짓 안내**가 뜬다.
    resetMemberQuota();
    const fetchMock = mockFetch(
      { status: 503, body: { detail: "quota unavailable" } },
      { status: 403, body: { detail: "project is owned by another user" } },
      { body: quotaBody },                                       // status: active
    );
    renderPanel();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("정지");
    expect(alert).toHaveTextContent("403");
  });

  it("does not re-read the quota for refusals that are not 403", async () => {
    // 402·429는 그 자체로 quota 사건이라 재조회할 이유가 없다. 아무 실패에나
    // 조회를 한 번 더 붙이면 실패 경로가 두 배로 시끄러워진다.
    resetMemberQuota();
    const fetchMock = mockFetch(
      { body: quotaBody },                                       // mount
      { status: 402, body: { detail: "daily request quota exhausted (20/20)" } },
      { body: quotaBody },                                       // 거절 뒤 갱신 1회
    );
    renderPanel();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await userEvent.type(screen.getByLabelText("이어쓰기 지시"), "이어서 써줘");
    await userEvent.click(generateButton());
    await screen.findByRole("alert");
    // mount 1 + 유료 1 + 거절 뒤 갱신 1 = 3. 재확정 조회가 붙으면 4가 된다.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
