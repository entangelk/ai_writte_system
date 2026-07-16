import { useRef, useState } from "react";
import {
  ApiError,
  acceptWriting,
  describeApiError,
  gateWriting,
  generateWriting,
  type WritingAcceptRequest,
  type WritingCandidate,
  type WritingGate,
} from "../api/client";

// continue_scene emits a draft_patch (writing-workspace brief §확인된 계약). These
// are fixed for the C1 slice; a later slice may expose other task/output types.
const TASK_TYPE = "continue_scene";
const OUTPUT_TYPE = "draft_patch";
const MAX_TOKENS = 4096;
// 400/404/422 are definitive rejections: the candidate can never be accepted
// with the same body, so the bound idempotency key is discarded. 409 (stale
// base) is handled separately, and transport/5xx preserve the key for retry.
const DEFINITIVE_ACCEPT_FAILURES = new Set([400, 404, 422]);

type WritingPanelProps = {
  projectId: string;
  draftId: string;
  // The version that is latest right now. generate/gate/accept all reference it;
  // when Writing is available it is also the selected version (D1=A clean latest).
  latestVersionId: string | null;
  onLatest: boolean;
  dirty: boolean;
  hasVersions: boolean;
  readOnly: boolean;
  // Called after a version is saved (accept success or 502 partial) so the
  // editor reloads its baseline/history from the server.
  onAccepted: () => void;
};

type WritingBlock =
  | { blocked: false }
  | { blocked: true; reason: string; resolution: string };

type AcceptIntent = { key: string; signature: string };

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

const DECISION_LABEL: Record<string, string> = {
  pass: "채택 가능 (pass)",
  revise: "수정 필요 (revise)",
  retrieve_more: "추가 근거 필요 (retrieve_more)",
  needs_user_review: "사용자 검토 필요 (needs_user_review)",
  block: "차단 (block)",
};

export function WritingPanel(props: WritingPanelProps) {
  const {
    projectId,
    draftId,
    latestVersionId,
    readOnly,
    onAccepted,
  } = props;
  const [instruction, setInstruction] = useState("");
  const [candidate, setCandidate] = useState<WritingCandidate | null>(null);
  const [gate, setGate] = useState<WritingGate | null>(null);
  const [busy, setBusy] = useState<"generating" | "accepting" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const busyRef = useRef(false);
  const intentRef = useRef<AcceptIntent | null>(null);
  // The base version + request id are frozen for the lifetime of a candidate:
  // generate → gate → accept all reference the version that was latest when the
  // candidate was produced (brief D1=A: base id fixed to the intent).
  const contextRef = useRef<{ baseVersionId: string; requestId: string } | null>(null);

  const availability = availabilityOf(props);
  const canAccept = candidate !== null && gate?.decision === "pass";

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = instruction.trim();
    if (
      trimmed === "" ||
      busyRef.current ||
      availability.blocked ||
      latestVersionId === null
    ) {
      return;
    }
    busyRef.current = true;
    setBusy("generating");
    setError(null);
    setNotice(null);
    setCandidate(null);
    setGate(null);
    intentRef.current = null;
    contextRef.current = null;
    const baseVersionId = latestVersionId;
    const requestId = crypto.randomUUID();
    const position = { draft_id: draftId, version_id: baseVersionId };
    try {
      const produced = await generateWriting(projectId, {
        request_id: requestId,
        instruction: trimmed,
        draft_excerpt: "",
        max_tokens: MAX_TOKENS,
        task_type: TASK_TYPE,
        current_position: position,
      });
      // Keep the candidate even if the following Gate call fails (transport/5xx
      // preserves the candidate); accept stays disabled until a pass Gate.
      setCandidate(produced);
      contextRef.current = { baseVersionId, requestId };
      const evaluated = await gateWriting(projectId, {
        request_id: requestId,
        instruction: trimmed,
        candidate_text: produced.text,
        draft_excerpt: "",
        max_tokens: MAX_TOKENS,
        task_type: TASK_TYPE,
        current_position: position,
      });
      setGate(evaluated);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  async function accept() {
    if (
      candidate === null ||
      gate?.decision !== "pass" ||
      busyRef.current ||
      contextRef.current === null
    ) {
      return;
    }
    busyRef.current = true;
    setBusy("accepting");
    setError(null);
    setNotice(null);
    const { baseVersionId, requestId } = contextRef.current;
    const fields: Omit<WritingAcceptRequest, "idempotency_key"> = {
      request_id: requestId,
      draft_id: draftId,
      base_version_id: baseVersionId,
      instruction: instruction.trim(),
      candidate_text: candidate.text,
      draft_excerpt: "",
      max_tokens: MAX_TOKENS,
      task_type: TASK_TYPE,
      output_type: OUTPUT_TYPE,
      current_position: { draft_id: draftId, version_id: baseVersionId },
    };
    // Bind the idempotency key to the EXACT accept body (minus the key): a
    // transport/5xx retry of the same candidate replays with the same key, while
    // a different candidate/base mints a new key (brief accept intent lock).
    const signature = JSON.stringify(fields);
    const intent: AcceptIntent =
      intentRef.current?.signature === signature
        ? intentRef.current
        : { key: crypto.randomUUID(), signature };
    intentRef.current = intent;
    try {
      const outcome = await acceptWriting(projectId, {
        ...fields,
        idempotency_key: intent.key,
      });
      if (outcome.accepted) {
        // A version was saved (200 accepted=true or 502 partial). Consume the
        // candidate and let the editor reload the new latest from the server.
        setCandidate(null);
        setGate(null);
        contextRef.current = null;
        intentRef.current = null;
        setInstruction("");
        setNotice(
          outcome.analysisFailed
            ? "채택되어 새 version으로 저장됐습니다. 분석 작업은 실패해 재시도가 필요합니다."
            : "채택되어 새 version으로 저장됐습니다.",
        );
        onAccepted();
      } else {
        // A non-pass re-gate: nothing was saved. Preserve the candidate and show
        // the returned Gate — this is a result, not a failure.
        setGate(outcome.gate);
        setNotice("채택되지 않았습니다. 아래 Gate 결과를 확인하세요.");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // A newer version appeared: the frozen base is stale. Preserve the
        // candidate and steer the user to reload the latest and regenerate.
        intentRef.current = null;
        setError(
          "그 사이 새 저장이 생겨 기준 version이 최신이 아닙니다. 최신 version을 불러온 뒤 다시 생성하세요.",
        );
      } else if (
        err instanceof ApiError &&
        DEFINITIVE_ACCEPT_FAILURES.has(err.status)
      ) {
        intentRef.current = null;
        setError(describeApiError(err));
      } else {
        // transport/5xx (or a 502 without a saved version): preserve the
        // candidate and the intent so the same body retries with the same key.
        setError(describeApiError(err));
      }
    } finally {
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
      </div>

      {availability.blocked ? (
        <p className="writing-block" role="note">
          <span className="writing-block-reason">{availability.reason}</span>
          <span className="writing-block-resolution">{availability.resolution}</span>
        </p>
      ) : (
        <p className="writing-hint">
          최신 저장 version을 기준으로 다음 장면을 제안합니다. 채택하기 전에는 원고
          본문이 바뀌지 않습니다.
        </p>
      )}

      <form className="writing-form" onSubmit={generate}>
        <label htmlFor="writing-instruction">이어쓰기 지시</label>
        <textarea
          id="writing-instruction"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          readOnly={readOnly}
          rows={3}
          placeholder="예: 아린이 성문을 지나 도시로 들어가는 장면을 이어써줘."
        />
        <div className="writing-actions">
          <button
            type="submit"
            disabled={
              availability.blocked ||
              busy !== null ||
              instruction.trim() === ""
            }
          >
            {busy === "generating" ? "생성 중…" : "이어쓰기 생성"}
          </button>
        </div>
      </form>

      {error !== null && (
        <p className="alert" role="alert">
          {error}
        </p>
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
          <p className="candidate-text">{candidate.text}</p>

          {gate === null ? (
            <p className="status-copy">근거를 평가하는 중…</p>
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
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="candidate-actions">
            <button
              type="button"
              disabled={!canAccept || busy !== null}
              onClick={() => void accept()}
            >
              {busy === "accepting" ? "채택 중…" : "채택하고 저장"}
            </button>
            {gate !== null && !canAccept && (
              <span className="candidate-accept-note">
                Gate 판정이 pass일 때만 채택할 수 있습니다.
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
