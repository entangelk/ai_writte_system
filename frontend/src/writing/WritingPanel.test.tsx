import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingPanel } from "./WritingPanel";

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

const saved = {
  draft_version_id: "v4",
  version_number: 4,
  snapshot_id: "s4",
  content_hash: "h4",
};

const acceptOk = {
  accepted: true,
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
}

beforeEach(() => {
  stubIncrementingUuid();
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
      max_tokens: 4096,
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

  it("preserves the candidate when the gate call fails after generate", async () => {
    // transport/5xx on gate: keep the candidate, no gate, accept stays disabled.
    const fetchMock = mockFetch({ body: candidate }, { status: 502, body: { detail: "gate down" } });
    renderPanel();
    await generateAndGate(fetchMock);
    expect(screen.getByText(candidate.text)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("gate down");
    expect(acceptButton()).toBeDisabled();
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
      max_tokens: 4096,
      task_type: "continue_scene",
      output_type: "draft_patch",
      current_position: { draft_id: "d1", version_id: "v3" },
      idempotency_key: "uuid-2",
    });
    expect(onAccepted).toHaveBeenCalledTimes(1);
    // Candidate consumed after a successful save.
    await waitFor(() => expect(screen.queryByText(candidate.text)).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("채택되어 새 version으로 저장됐습니다.");
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
