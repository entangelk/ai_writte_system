import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  describeQuotaError,
  describeWritingError,
  gateWriting,
  generateWriting,
  reviseAndGateWriting,
  type BillableRequestOptions,
  type WritingCandidate,
  type WritingGate,
  type WritingGateFinding,
  type WritingLoop,
  type WritingLoopStage,
  type WritingGenerationJob,
  type WritingReviseGatePartial,
  type WritingReviseRequest,
} from "../api/client";
import { describeRemaining, useMemberQuota } from "../quota/useMemberQuota";
import { useWritingBudget } from "./useWritingBudget";
import { estimateTokens, formatInstructionCount } from "./tokenEstimate";
import { confirmPrompt, formatResetMoment } from "./quotaConfirm";

// continue_scene emits a draft_patch (writing-workspace brief §확인된 계약). These
// are fixed for the C1 slice; a later slice may expose other task/output types.
const TASK_TYPE = "continue_scene";
// 입력 ContextPackage 예산. **서버 기본값(8192)과 같은 값을 명시적으로 보낸다** — 화면이
// 이 값을 실어 보내므로 서버 기본값만 올리면 제품에는 아무 효과가 없다(K-1(a) 착수 시 실측으로
// 확인했다). 근거는 `main.py::DEFAULT_CONTEXT_BUDGET_TOKENS` 주석에 있다: 4096은 동기 생성
// 시절의 값이고, 회계가 한글 실측(`len/1.7`)으로 정직해지면서 같은 숫자의 실제 분량이 절반이
// 됐기 때문에 8192가 종전 실효 분량을 유지하는 짝이다.
export const MAX_TOKENS = 8192;

type WritingPanelProps = {
  projectId: string;
  draftId: string;
  // The version that is latest right now. generate/gate both reference it; when
  // Writing is available it is also the selected version (D1=A clean latest).
  latestVersionId: string | null;
  onLatest: boolean;
  dirty: boolean;
  hasVersions: boolean;
  readOnly: boolean;
  // 증분 3 (D6): called when an async (medium/long) generate is accepted as a
  // background job, so the editor starts polling it for the result pad.
  onAsyncJobStarted?: (job: WritingGenerationJob) => void;
};

type WritingBlock =
  | { blocked: false }
  | { blocked: true; reason: string; resolution: string };

type LoopResult = {
  loop: WritingLoop;
  stages: WritingLoopStage[];
  partialStatus: number | null;
  errorType: string | null;
  errorDetail: string | null;
  retryable: boolean;
};

// D1=A: Writing is only allowed from a clean latest saved version. Each blocked
// state names WHY it is unavailable and the action that resolves it — never a
// bare disabled control. The Korean copy is localizable display text, not a
// machine contract.
function availabilityOf(
  props: Pick<WritingPanelProps, "readOnly" | "hasVersions" | "dirty" | "onLatest">,
): WritingBlock {
  if (props.readOnly) {
    return {
      blocked: true,
      reason: "보관된 원고에서는 이어쓰기를 생성할 수 없습니다.",
      resolution: "원고 보관을 해제하면 다시 생성할 수 있습니다.",
    };
  }
  if (!props.hasVersions) {
    return {
      blocked: true,
      reason: "아직 저장된 version이 없습니다.",
      resolution: "본문을 먼저 저장해 첫 version을 만든 뒤 이어쓰기를 생성하세요.",
    };
  }
  if (props.dirty) {
    return {
      blocked: true,
      reason: "저장하지 않은 변경 사항이 있습니다.",
      resolution: "현재 변경을 먼저 저장한 뒤 이어쓰기를 생성하세요.",
    };
  }
  if (!props.onLatest) {
    return {
      blocked: true,
      reason: "과거 version을 보고 있습니다.",
      resolution: "최신 version으로 돌아온 뒤 이어쓰기를 생성하세요.",
    };
  }
  return { blocked: false };
}

export const DECISION_LABEL: Record<string, string> = {
  pass: "통과 (pass)",
  revise: "수정 필요 (revise)",
  retrieve_more: "추가 근거 필요 (retrieve_more)",
  needs_user_review: "사용자 검토 필요 (needs_user_review)",
  block: "차단 (block)",
};

const LOOP_STATUS_COPY: Record<
  WritingLoop["status"],
  { label: string; action: string }
> = {
  pass: {
    label: "자동 개선 완료",
    action: "Gate를 통과했습니다. 후보를 확인한 뒤 복사해 쓰세요.",
  },
  terminal_decision: {
    label: "자동 개선 중단",
    action: "사용자 판단이 필요한 Gate 결과입니다. 근거를 확인하고 지시를 바꿔 다시 생성하세요.",
  },
  not_eligible: {
    label: "자동 수정 대상 아님",
    action: "안전하게 자동 수정할 수 없는 지적입니다. 지시를 보완해 새 후보를 생성하세요.",
  },
  budget_exhausted: {
    label: "자동 개선 한도 도달",
    action: "마지막 후보를 보존했습니다. 자동 개선을 다시 시도하거나 지시를 바꿔 생성하세요.",
  },
  no_change: {
    label: "수정 결과 변화 없음",
    action: "같은 수정으로 후보가 달라지지 않았습니다. 지시를 구체화해 다시 생성하세요.",
  },
  failed: {
    label: "자동 개선 실패",
    action: "마지막 후보를 보존했습니다. 오류 안내에 따라 재시도하거나 새로 생성하세요.",
  },
};

const STAGE_LABEL: Record<WritingLoopStage["stage"], string> = {
  revise: "후보 수정",
  report: "근거 보고서 갱신",
  gate: "Gate 재평가",
  retrieve_plan: "추가 근거 계획",
  context_search: "추가 근거 검색",
  merge: "근거 병합",
};

const STAGE_STATUS_LABEL: Record<WritingLoopStage["status"], string> = {
  completed: "완료",
  failed: "실패",
  no_change: "변화 없음",
};

function occurrences(text: string, evidence: string): number {
  return evidence === "" ? 0 : text.split(evidence).length - 1;
}

function eligibleRevisionFinding(
  candidate: WritingCandidate,
  gate: WritingGate,
): WritingGateFinding | null {
  if (gate.decision !== "revise") return null;
  const eligible = gate.findings.filter(
    (finding) =>
      finding.type === "continuity" &&
      finding.recommended_decision === "revise" &&
      finding.evidence.trim() !== "" &&
      occurrences(candidate.text, finding.evidence) === 1,
  );
  return eligible.find((finding) => finding.severity === "error")
    ?? eligible[0]
    ?? null;
}

function partialStageError(
  data: Awaited<ReturnType<typeof reviseAndGateWriting>>["data"],
): { type: string; detail: string } | null {
  const partial = data as Partial<WritingReviseGatePartial>;
  for (const key of [
    "revision_error",
    "report_error",
    "gate_error",
    "retrieval_error",
  ] as const) {
    if (partial[key] != null) return partial[key];
  }
  return data.audit_error;
}

export function WritingPanel(props: WritingPanelProps) {
  const {
    projectId,
    draftId,
    latestVersionId,
    readOnly,
    onAsyncJobStarted,
  } = props;
  const [instruction, setInstruction] = useState("");
  // K-4: R-a 유도 예산(per-preset 토큰)을 서버에서 받아 카운터의 경고 기준으로 쓴다 —
  // 프론트 고정 상수(8192)가 아니다. 예산을 모르면(게이트웨이 없음·조회 실패) null 이고
  // 경고를 띄우지 않는다(거짓 경고 방지).
  const { budgetByPreset } = useWritingBudget(projectId);
  // W3 Writing intent (§3.1): append to the current unit, or open the next
  // ordered unit. The next-unit fields are only used for start_next_unit.
  const [writingIntent, setWritingIntent] =
    useState<"append_current" | "start_next_unit">("append_current");
  const [nextTitle, setNextTitle] = useState("");
  const [nextGoal, setNextGoal] = useState("");
  // 증분 2 (D3=A): output-length preset. The server owns the preset→token mapping
  // (short/medium/long → 1024/2048/4096). `long` is single-generate only — it is
  // not run through the auto revise/retrieve loop (exceeds the loop wall clock).
  const [outputLength, setOutputLength] =
    useState<"short" | "medium" | "long">("short");
  const [candidate, setCandidate] = useState<WritingCandidate | null>(null);
  const [gate, setGate] = useState<WritingGate | null>(null);
  const [loopResult, setLoopResult] = useState<LoopResult | null>(null);
  const [busy, setBusy] = useState<"generating" | "improving" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // 8.4 W3=A: 중복 잠금(429)은 되묻는 자리다. `run` 은 **그 단계만** 다시 보내는
  // 클로저이며(연쇄 전체가 아니다), 사용자가 누르기 전에는 아무 요청도 안 나간다.
  /**
   * 확인 대화를 띄운 뒤 **그 자리로 시선을 옮기기 위한** 자리.
   * ★ 이 패널은 세로로 길고 동작이 위아래에 흩어져 있다 — 생성은 맨 위, 채택은
   * 맨 아래다. 확인 대화는 한 곳(위)에만 그려지므로, **아래쪽 버튼을 누른
   * 사용자에게는 화면 밖에서 열린다**. 그러면 429(같은 요청이 이미 진행 중)가
   * *"아무 일도 안 일어났다"* 로 보인다(오너 실사용 관측 2026-09-07).
   */
  const confirmRef = useRef<HTMLDivElement | null>(null);
  const [pendingConfirm, setPendingConfirm] =
    useState<{ message: string; run: () => void; confirmLabel: string } | null>(null);
  const { quota, refresh: refreshQuota } = useMemberQuota();
  // Coarse phase label so the server-side pipeline (근거 검색 → 초안 생성 → 보고서
  // → Gate) is not a black box while the two calls run.
  const [progress, setProgress] = useState<string | null>(null);
  const busyRef = useRef(false);
  const loopIntentRef = useRef<WritingReviseRequest | null>(null);
  // 후보 본문을 클립보드로 옮긴 직후인지 — 버튼 문구를 "복사됨"으로 바꾸는 데만 쓴다.
  const [copied, setCopied] = useState(false);

  const availability = availabilityOf(props);
  const startingNextUnit = writingIntent === "start_next_unit";
  // A new unit needs a nonblank title; the backend rejects a blank one with 400.
  const nextUnitReady = !startingNextUnit || nextTitle.trim() !== "";
  const eligibleFinding =
    candidate !== null && gate !== null
      ? eligibleRevisionFinding(candidate, gate)
      : null;

  function onSubmitGenerate(event: React.FormEvent) {
    event.preventDefault();
    void runGenerate();
  }

  /**
   * quota 거절이면 화면 언어로 처리하고 `true`, 아니면 `false` (8.4 W2=A).
   *
   * 확인 가능한 사건(429)은 **되묻고**, 그 밖(402·정지)은 평범한 에러로 보여 준다.
   * `retry` 는 사용자가 "하나 더 만들기"를 누를 때만 실행된다 — 여기서 자동으로
   * 부르면 확인이 무력화되고 사용자가 모르는 사이 사용량이 늘어난다(W4=A).
   */
  // 확인 대화가 열리면 **그 자리로 시선을 옮긴다.** 이 패널은 세로로 길고 동작이
  // 위아래에 흩어져 있어(생성=위, 채택=아래) 대화가 화면 밖에서 열릴 수 있다 —
  // 그러면 429(같은 요청이 이미 진행 중)가 사용자에게 *"아무 일도 안 일어났다"* 가
  // 된다(오너 실사용 관측 2026-09-07: 채택 429 가 정확히 그랬다).
  useEffect(() => {
    if (pendingConfirm === null) return;
    // `?.()` 로 부른다 — jsdom 에는 `scrollIntoView` 가 없고(테스트 환경), 없다고
    // 해서 포커스까지 못 주면 안 된다. 스크롤은 보조이고 **포커스가 본체**다.
    confirmRef.current?.scrollIntoView?.({ block: "center" });
    confirmRef.current?.focus();
  }, [pendingConfirm]);

  async function handleQuotaRefusal(
    err: unknown,
    retry: () => void,
    /** 확인 버튼에 쓸 말. **무엇을 다시 하는지**가 동작마다 다르다 — 채택 뒤에
     *  "하나 더 만들기" 가 뜨면 사용자는 무엇을 승인하는지 알 수 없다. */
    confirmLabel: string,
  ): Promise<boolean> {
    let refusal = describeQuotaError(err, quota);
    if (refusal === null && err instanceof ApiError && err.status === 403) {
      // 독립 검증 2026-08-04 H-1 — 경합 창을 닫는다. 정지 계정의 **첫** 유료
      // 요청이 잔여 조회보다 먼저 도착하면 `quota` 가 아직 `null` 이라 정지가
      // 소유권 거절로 위장된다. 403 은 드물고 통로가 둘뿐이라(소유권·정지),
      // 그 자리에서 한 번 다시 읽어 확정하는 값이 재조회 한 번보다 크다.
      // **403 에서만** 한다 — 402·429 는 그 자체로 이미 quota 사건이다.
      refusal = describeQuotaError(err, await refreshQuota());
    }
    if (refusal === null) {
      return false;
    }
    // 거절은 요청이 **일어나지 않은** 것이므로 잔여를 다시 읽어 화면을 맞춘다
    // (진행 중 요청이 한 칸을 차지하고 있을 수 있다 — Q3=E).
    if (refusal.kind !== "suspended") {
      void refreshQuota();
    }
    if (refusal.confirmable) {
      setError(null);
      setRetryable(false);
      setPendingConfirm({ message: confirmPrompt(quota), run: retry, confirmLabel });
      return true;
    }
    setPendingConfirm(null);
    setError(
      refusal.kind === "exhausted" && quota?.daily.resets_at
        ? `${refusal.message} (${formatResetMoment(quota)} 초기화)`
        : refusal.message,
    );
    setRetryable(false);
    return true;
  }

  /** 후보 본문을 클립보드로. 실패하면(권한·비보안 컨텍스트) 직접 선택해 복사하도록 안내한다. */
  async function copyCandidate() {
    if (candidate === null) return;
    try {
      await navigator.clipboard?.writeText(candidate.text);
      setCopied(true);
    } catch {
      setError("클립보드 복사를 사용할 수 없습니다. 위 본문을 직접 선택해 복사하세요.");
    }
  }

  async function runGenerate(options: BillableRequestOptions = {}) {
    const trimmed = instruction.trim();
    if (
      trimmed === "" ||
      busyRef.current ||
      availability.blocked ||
      latestVersionId === null ||
      !nextUnitReady
    ) {
      return;
    }
    busyRef.current = true;
    setBusy("generating");
    setError(null);
    setRetryable(false);
    setNotice(null);
    setPendingConfirm(null);
    setCandidate(null);
    setGate(null);
    setLoopResult(null);
    setCopied(false);
    loopIntentRef.current = null;
    const baseVersionId = latestVersionId;
    const requestId = crypto.randomUUID();
    const position = { draft_id: draftId, version_id: baseVersionId };
    const generateNextUnit = startingNextUnit
      ? {
          title: nextTitle.trim(),
          goal: nextGoal.trim() === "" ? null : nextGoal.trim(),
        }
      : null;
    try {
      setProgress("근거를 검색하고 초안을 생성하는 중…");
      const produced = await generateWriting(projectId, {
        request_id: requestId,
        instruction: trimmed,
        draft_excerpt: "",
        max_tokens: MAX_TOKENS,
        output_length: outputLength,
        task_type: TASK_TYPE,
        current_position: position,
        intent: writingIntent,
        next_unit: generateNextUnit,
      }, options);
      void refreshQuota();
      // 증분 2c (D5=A): medium/long presets are async — the server enqueues a
      // background job and returns 202 with a job reference instead of a
      // candidate. The worker appends the result to scratch; the pad (increment 3)
      // polls the job and displays it. Until then there is no candidate to show,
      // and the Gate/auto-loop must not run (nothing to gate). The finally block
      // clears progress + busy; the notice carries the "started" signal.
      if ("job" in produced) {
        onAsyncJobStarted?.(produced.job);
        setNotice(
          "백그라운드 생성을 시작했습니다. 완료되면 결과 패드에 표시됩니다.",
        );
        return;
      }
      // short (sync): keep the candidate even if the following Gate call fails
      // (transport/5xx preserves the candidate).
      setCandidate(produced);
      await runGate(produced, { requestId, trimmed, position });
    } catch (err) {
      if (await handleQuotaRefusal(err, () =>
        void runGenerate({ confirmDuplicate: true }), "하나 더 만들기")) {
        return;
      }
      const described = describeWritingError(err);
      setError(described.message);
      setRetryable(described.retryable);
    } finally {
      setProgress(null);
      busyRef.current = false;
      setBusy(null);
    }
  }

  /**
   * 생성 뒤 이어지는 Gate 단계. **자기 try/catch 를 갖는다**(8.4 W3=A).
   *
   * 한 번의 클릭이 유료 요청 2~3건을 연쇄로 부르므로(generate → gate →
   * revise-and-gate), 중간에서 429 가 나면 되물어야 하는 것은 **그 단계**다.
   * 연쇄 전체를 다시 보내면 이미 성공한 생성까지 한 번 더 과금된다.
   */
  async function runGate(
    produced: WritingCandidate,
    context: {
      requestId: string;
      trimmed: string;
      position: { draft_id: string; version_id: string };
    },
    options: BillableRequestOptions = {},
  ) {
    const { requestId, trimmed, position } = context;
    busyRef.current = true;
    setBusy("generating");
    setProgress("Gate로 근거를 평가하는 중…");
    try {
      const evaluated = await gateWriting(projectId, {
        request_id: requestId,
        instruction: trimmed,
        candidate_text: produced.text,
        draft_excerpt: "",
        max_tokens: MAX_TOKENS,
        task_type: TASK_TYPE,
        current_position: position,
      }, options);
      void refreshQuota();
      setGate(evaluated);
      const finding = eligibleRevisionFinding(produced, evaluated);
      if (finding !== null) {
        await executeLoop({
          request_id: requestId,
          instruction: trimmed,
          candidate_text: produced.text,
          finding: {
            type: finding.type,
            severity: finding.severity,
            message: finding.message,
            evidence: finding.evidence,
            recommended_decision: finding.recommended_decision,
          },
          max_tokens: MAX_TOKENS,
          task_type: TASK_TYPE,
          current_position: position,
          persist_audit: false,
        });
      }
    } catch (err) {
      if (await handleQuotaRefusal(err, () =>
        void runGate(produced, context, { confirmDuplicate: true }), "다시 검사하기")) {
        return;
      }
      const described = describeWritingError(err);
      setError(described.message);
      setRetryable(described.retryable);
    } finally {
      setProgress(null);
      busyRef.current = false;
      setBusy(null);
    }
  }

  async function executeLoop(
    body: WritingReviseRequest,
    options: BillableRequestOptions = {},
  ) {
    busyRef.current = true;
    setBusy("improving");
    setError(null);
    setRetryable(false);
    setNotice(null);
    setLoopResult(null);
    setProgress("후보를 자동으로 개선하는 중…");
    loopIntentRef.current = body;
    try {
      const outcome = await reviseAndGateWriting(projectId, body, options);
      void refreshQuota();
      const stageError = partialStageError(outcome.data);
      setCandidate(outcome.data.candidate);
      setCopied(false);
      setGate(outcome.data.gate);
      setLoopResult({
        loop: outcome.data.loop,
        stages: outcome.data.stages,
        partialStatus: outcome.partial ? outcome.status : null,
        errorType: stageError?.type ?? null,
        errorDetail: stageError?.detail ?? null,
        retryable: outcome.retryable,
      });
      if (!outcome.partial) {
        loopIntentRef.current = null;
      }
    } catch (err) {
      if (await handleQuotaRefusal(err, () =>
        void executeLoop(body, { confirmDuplicate: true }), "다시 개선하기")) {
        return;
      }
      const described = describeWritingError(err);
      setError(described.message);
      setRetryable(described.retryable);
    } finally {
      setProgress(null);
      busyRef.current = false;
      setBusy(null);
    }
  }

  return (
    <section className="workspace-panel writing-panel" aria-labelledby="writing-title">
      <div className="version-panel-heading">
        <div>
          <p className="eyebrow">AI 이어쓰기</p>
          <h2 id="writing-title">이어쓰기 생성</h2>
        </div>
        {/*
          8.4 W5=B — 잔여는 통합값 하나다(8.2 §0.2: 두 창을 모두 통과해야 하므로
          작은 쪽이 실제 잔여다). **"N회 = 클릭 N번"이 아니다** — 한 번의 생성이
          생성·검사·(개선)로 2~3회를 쓰므로 그 사실을 title 로 함께 말한다.
          무제한이면 아무것도 그리지 않는다.
        */}
        {describeRemaining(quota) !== null && (
          <p
            className="writing-quota"
            title="생성·Gate 검사·자동 개선이 각각 1회입니다."
          >
            {describeRemaining(quota)}
          </p>
        )}
      </div>

      {pendingConfirm !== null && (
        <div
          className="writing-confirm"
          role="alertdialog"
          aria-label="중복 요청 확인"
          ref={confirmRef}
          tabIndex={-1}
        >
          <p>{pendingConfirm.message}</p>
          <div className="writing-confirm-actions">
            <button
              type="button"
              onClick={() => {
                const run = pendingConfirm.run;
                setPendingConfirm(null);
                run();
              }}
            >
              {pendingConfirm.confirmLabel}
            </button>
            <button type="button" onClick={() => setPendingConfirm(null)}>
              취소
            </button>
          </div>
        </div>
      )}

      {availability.blocked ? (
        <p className="writing-block" role="note">
          <span className="writing-block-reason">{availability.reason}</span>
          <span className="writing-block-resolution">{availability.resolution}</span>
        </p>
      ) : (
        <p className="writing-hint">
          최신 저장 version을 기준으로 다음 장면을 제안합니다. 이 패널은 원고 본문을
          바꾸지 않습니다 — 후보가 마음에 들면 편집기로 옮겨 저장하세요.
        </p>
      )}

      <form className="writing-form" onSubmit={onSubmitGenerate}>
        <label htmlFor="writing-instruction">이어쓰기 지시</label>
        <textarea
          id="writing-instruction"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          readOnly={readOnly}
          rows={3}
          placeholder="예: 아린이 성문을 지나 도시로 들어가는 장면을 이어써줘."
        />
        {(() => {
          // K-4: 현재 출력 프리셋의 R-a 유도 예산 대비 90% 를 넘으면 소프트 경고(색 변화).
          const activeBudget = budgetByPreset?.[outputLength] ?? null;
          const overBudget =
            activeBudget !== null &&
            estimateTokens(instruction) >= Math.round(activeBudget * 0.9);
          return (
            <p
              className={`writing-counter${
                overBudget ? " writing-counter-warn" : ""
              }`}
              aria-live="polite"
            >
              {formatInstructionCount(instruction)}
            </p>
          );
        })()}

        <label htmlFor="writing-output-length">생성 분량</label>
        <select
          id="writing-output-length"
          value={outputLength}
          onChange={(event) =>
            setOutputLength(event.target.value as "short" | "medium" | "long")
          }
          disabled={readOnly}
        >
          <option value="short">짧은 수정</option>
          <option value="medium">중간부터 이어쓰기</option>
          <option value="long">전체 작성 (자동 개선 없음)</option>
        </select>

        <fieldset className="writing-intent" disabled={readOnly}>
          <legend>이어쓰기 방식</legend>
          <label>
            <input
              type="radio"
              name="writing-intent"
              value="append_current"
              checked={!startingNextUnit}
              onChange={() => setWritingIntent("append_current")}
            />
            현재 유닛에 이어쓰기
          </label>
          <label>
            <input
              type="radio"
              name="writing-intent"
              value="start_next_unit"
              checked={startingNextUnit}
              onChange={() => setWritingIntent("start_next_unit")}
            />
            같은 장의 다음 장면 시작
          </label>
        </fieldset>

        {startingNextUnit && (
          <div className="writing-next-unit">
            <label htmlFor="next-unit-title">새 장면 제목</label>
            <input
              id="next-unit-title"
              type="text"
              value={nextTitle}
              onChange={(event) => setNextTitle(event.target.value)}
              readOnly={readOnly}
              placeholder="예: 성 안에서"
            />
            <label htmlFor="next-unit-goal">장면 목표(선택)</label>
            <input
              id="next-unit-goal"
              type="text"
              value={nextGoal}
              onChange={(event) => setNextGoal(event.target.value)}
              readOnly={readOnly}
              placeholder="생성에만 쓰이며 본문에는 저장되지 않습니다."
            />
          </div>
        )}

        <div className="writing-actions">
          <button
            type="submit"
            disabled={
              availability.blocked ||
              busy !== null ||
              instruction.trim() === "" ||
              !nextUnitReady
            }
          >
            {busy === "generating" ? "생성 중…" : "이어쓰기 생성"}
          </button>
        </div>
      </form>

      {progress !== null && (
        <p className="writing-progress" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          {progress}
        </p>
      )}
      {error !== null && (
        <div className="writing-error" role="alert">
          <p className="alert">{error}</p>
          {retryable && (
            <button
              type="button"
              className="writing-retry"
              disabled={busy !== null || availability.blocked || instruction.trim() === ""}
              onClick={() => void runGenerate()}
            >
              다시 생성
            </button>
          )}
        </div>
      )}
      {notice !== null && (
        <p className="writing-notice" role="status">
          {notice}
        </p>
      )}

      {candidate !== null && (
        <div className="candidate-panel" aria-label="생성된 후보">
          <div className="candidate-heading">
            <p className="eyebrow">생성된 후보 (읽기 전용)</p>
            {candidate.generated_by_model !== "" && (
              <span className="candidate-model">{candidate.generated_by_model}</span>
            )}
          </div>
          {/*
            오너 2026-09-08: *"이어쓰기에 있는 글들이 너무 긴데 접어둘 수 없나?"*
            **기본 펼침**이다 — 방금 생성한 후보는 읽으려고 만든 것이라 접힌 채
            나오면 매번 펴야 한다. 지나간 후보(ScratchRecovery 패드)는 반대로 기본
            접힘이다. 상태 없이 네이티브 <details> 로 접는다.
          */}
          <details className="candidate-fold" open>
            <summary>생성된 본문 ({[...candidate.text].length}자)</summary>
            <p className="candidate-text">{candidate.text}</p>
          </details>
          <p className="candidate-summary">
            근거 주장 {candidate.candidate_claims.length}개
            {candidate.new_memory_hints.length > 0 &&
              ` · 기억 후보 ${candidate.new_memory_hints.length}개`}
            {candidate.risk_notes.length > 0 &&
              ` · 위험 지적 ${candidate.risk_notes.length}개`}
          </p>

          {busy === "improving" ? (
            <p className="status-copy" role="status">후보를 자동으로 개선하는 중…</p>
          ) : gate === null ? (
            <p className="status-copy">Gate 결과가 없습니다.</p>
          ) : (
            <div className="gate-result" aria-label="Gate 평가">
              <p className="gate-decision">
                Gate 판정: <strong>{DECISION_LABEL[gate.decision] ?? gate.decision}</strong>
              </p>
              {gate.findings.length === 0 ? (
                <p className="gate-empty">지적된 문제가 없습니다.</p>
              ) : (
                <ul className="gate-findings" aria-label="Gate 지적">
                  {gate.findings.map((finding, index) => (
                    <li key={index} className={`gate-finding severity-${finding.severity}`}>
                      <span className="finding-head">
                        [{finding.severity}] {finding.type} → {finding.recommended_decision}
                      </span>
                      <span className="finding-message">{finding.message}</span>
                      {finding.evidence !== "" && (
                        <span className="finding-evidence">근거: {finding.evidence}</span>
                      )}
                      {finding.type === "style" && (
                        <span className="finding-advisory">
                          문체 참고 사항입니다. 의도한 표현이라면 그대로 두어도 됩니다.
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {loopResult !== null && (
            <div className="loop-result" aria-label="자동 개선 결과">
              <p className="loop-status">
                자동 개선: <strong>{LOOP_STATUS_COPY[loopResult.loop.status].label}</strong>
              </p>
              <p className="loop-action">
                {LOOP_STATUS_COPY[loopResult.loop.status].action}
              </p>
              <p className="loop-counts">
                수정 {loopResult.loop.revision_rounds}회 · 추가 검색{" "}
                {loopResult.loop.retrieval_rounds}회 · Gate{" "}
                {loopResult.loop.gate_evaluations}회
              </p>
              <ol className="loop-stages" aria-label="자동 개선 단계">
                {loopResult.stages.map((stage) => (
                  <li key={stage.ordinal}>
                    <span>{stage.ordinal}. {STAGE_LABEL[stage.stage]}</span>
                    <strong>{STAGE_STATUS_LABEL[stage.status]}</strong>
                  </li>
                ))}
              </ol>
              {loopResult.partialStatus !== null && (
                <p className="loop-error" role="alert">
                  {loopResult.partialStatus} · {loopResult.errorType ?? "loop_error"}:
                  {" "}{loopResult.errorDetail ?? "자동 개선이 완료되지 않았습니다."}{" "}
                  {loopResult.retryable
                    ? "이 오류는 다시 시도할 수 있습니다."
                    : "같은 요청 재시도보다 지시나 후보를 수정해야 합니다."}
                </p>
              )}
              {loopResult.retryable && loopIntentRef.current !== null && (
                <button
                  type="button"
                  className="loop-retry"
                  disabled={busy !== null}
                  onClick={() => void executeLoop(loopIntentRef.current!)}
                >
                  자동 개선 다시 시도
                </button>
              )}
            </div>
          )}

          <div className="candidate-actions">
            {/*
              ★ 채택 버튼은 없다(오너 2026-09-08): *"채택은 완전 자동화일 때 사용할 수
              있을 것 같아. 일반 사용자에게는 불필요한 항목 같아. 버튼을 그냥 없애주고
              통로만 열어두자."* 서버 `POST …/writing/accept` 와 API 클라이언트
              `acceptWriting` 은 그대로 있다 — 없앤 것은 화면의 버튼이지 통로가 아니다.
              사람이 쓰는 길은 **복사 → 편집기에 붙여넣기 → 저장**이고, 그 저장은 유료가
              아니다(채택은 보고서+Gate 재검사를 다시 사므로 유료였다).
            */}
            <button type="button" onClick={() => void copyCandidate()}>
              {copied ? "복사됨" : "본문 복사"}
            </button>
            <span className="candidate-accept-note">
              복사해 편집기에 붙여넣고 저장하세요. 이 패널은 원고를 직접 바꾸지 않습니다.
            </span>
            {gate !== null && gate.decision !== "pass" && (
              <>
                <span className="candidate-accept-note">
                  Gate가 통과 판정을 내리지 않았습니다. 아래 지적을 확인하세요.
                </span>
                {(gate.decision === "revise" || gate.decision === "retrieve_more") && (
                  <span className="candidate-accept-note">
                    {eligibleFinding !== null
                      ? "안전하게 자동 수정할 수 있는 continuity 지적입니다."
                      : "안전하게 자동 수정할 수 있는 지적이 없습니다. 직접 검토하거나 다시 생성하세요."}
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
