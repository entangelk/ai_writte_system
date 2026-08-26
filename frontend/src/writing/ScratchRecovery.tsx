import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  acceptWriting,
  describeApiError,
  describeQuotaError,
  discardWritingScratch,
  discardWritingScratchItem,
  listWritingScratch,
  type BillableRequestOptions,
  type ScratchCandidate,
  type WritingAcceptRequest,
  type WritingGateFinding,
} from "../api/client";
import { useMemberQuota } from "../quota/useMemberQuota";
import { DECISION_LABEL, MAX_TOKENS } from "./WritingPanel";
import { confirmPrompt, formatResetMoment } from "./quotaConfirm";

type ScratchRecoveryProps = {
  projectId: string;
  draftId: string;
  // Bumped by the parent after a successful accept (WritingPanel or this pad)
  // or a settled background job, so the list re-fetches — the server retires
  // the accepted item (D2=A: siblings stay) and the worker appends results.
  refreshKey?: number;
  // Mirrors WritingPanel.accept: a pad accept saves base+candidate as a new
  // version and the editor reloads, discarding unsaved edits — never silently.
  dirty?: boolean;
  readOnly?: boolean;
  // Called after a saved accept (200 or 502-partial) so the editor reloads the
  // new latest version, same contract as WritingPanel's onAccepted.
  onAccepted?: () => void;
};

// 400/404/422 are definitive rejections (same set as WritingPanel.accept): the
// entry can never be accepted with the same body, so the idempotency key is
// discarded. 409 (stale base) is handled separately; transport/5xx keep it.
const DEFINITIVE_ACCEPT_FAILURES = new Set([400, 404, 422]);

type ItemNote =
  | { kind: "gate"; decision: string; findings: WritingGateFinding[] }
  | { kind: "error"; message: string };

// Pre-dogfood safety net (brief D0=B/D1=B/D2=A): a candidate generated but not
// accepted is persisted to `writing_drafts_scratch`. This pad surfaces the
// newest-first unaccepted history. The store is not canonical; per item the
// user can 채택 (accept → new draft version; the server retires ONLY that item,
// siblings stay recoverable — D2=A, SoT v1.7.25), 버리기 (per-item delete), or
// copy the text back manually. [채택] needs the stored base version_id; null
// (pre-D7 record) means copy-only.
export function ScratchRecovery(props: ScratchRecoveryProps) {
  const { projectId, draftId, refreshKey, dirty, readOnly, onAccepted } = props;
  const [items, setItems] = useState<ScratchCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [acceptingId, setAcceptingId] = useState<string | null>(null);
  const [discardingId, setDiscardingId] = useState<string | null>(null);
  const [itemNotes, setItemNotes] = useState<Record<string, ItemNote>>({});
  const [pendingConfirm, setPendingConfirm] = useState<{
    message: string;
    run: () => void;
  } | null>(null);
  const discardingRef = useRef(false);
  const acceptBusyRef = useRef(false);
  // Idempotency key bound to the EXACT accept body (minus the key), same lock
  // as WritingPanel.accept: a retry of the same entry replays with the same
  // key, a different entry mints a new one.
  const acceptIntentRef = useRef<{ key: string; signature: string } | null>(
    null,
  );
  const { quota, refresh: refreshQuota } = useMemberQuota();

  useEffect(() => {
    let cancelled = false;
    listWritingScratch(projectId, draftId)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        // The safety net must never add noise to the editor: a failed lookup
        // just means nothing to recover is shown.
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, draftId, refreshKey]);

  if (items.length === 0) return null;

  async function copy(entry: ScratchCandidate) {
    try {
      await navigator.clipboard?.writeText(entry.candidate_text);
      setCopiedId(entry.id);
    } catch {
      setError("클립보드 복사를 사용할 수 없습니다. 아래 본문을 직접 선택해 복사하세요.");
    }
  }

  /**
   * quota 거절이면 화면 언어로 처리하고 `true`, 아니면 `false` — WritingPanel의
   * handleQuotaRefusal를 패드 표면에 맞춘 축약판. 확인 가능한 사건(429)은 되묻고,
   * 그 밖(402·정지)은 평범한 에러로 보여 준다.
   */
  async function handleQuotaRefusal(
    err: unknown,
    retry: () => void,
  ): Promise<boolean> {
    let refusal = describeQuotaError(err, quota);
    if (refusal === null && err instanceof ApiError && err.status === 403) {
      // 403 은 소유권·정지 둘뿐 — 그 자리에서 잔여를 다시 읽어 정지를 확정한다
      // (WritingPanel 2026-08-04 H-1과 같은 경합 창 닫기).
      refusal = describeQuotaError(err, await refreshQuota());
    }
    if (refusal === null) {
      return false;
    }
    if (refusal.kind !== "suspended") {
      void refreshQuota();
    }
    if (refusal.confirmable) {
      setError(null);
      setPendingConfirm({ message: confirmPrompt(quota), run: retry });
      return true;
    }
    setPendingConfirm(null);
    setError(
      refusal.kind === "exhausted" && quota?.daily.resets_at
        ? `${refusal.message} (${formatResetMoment(quota)} 초기화)`
        : refusal.message,
    );
    return true;
  }

  async function acceptItem(
    entry: ScratchCandidate,
    options: BillableRequestOptions = {},
  ) {
    if (
      entry.version_id === null ||
      readOnly === true ||
      acceptingId !== null ||
      acceptBusyRef.current
    ) {
      return;
    }
    if (
      dirty === true &&
      !window.confirm(
        "저장하지 않은 편집 내용이 있습니다. 채택하면 그 내용은 사라지고, 채택된 후보가 새 version으로 저장됩니다. 계속할까요?",
      )
    ) {
      return;
    }
    acceptBusyRef.current = true;
    setAcceptingId(entry.id);
    setItemNotes((notes) => {
      const next = { ...notes };
      delete next[entry.id];
      return next;
    });
    // The stored entry is the whole accept contract: base_version_id is the
    // version the candidate was generated against (async-pad D7), so a draft
    // that moved on since is a 409 stale base — surfaced, not retried.
    const fields: Omit<WritingAcceptRequest, "idempotency_key"> = {
      request_id: entry.request_id,
      draft_id: entry.draft_id,
      base_version_id: entry.version_id,
      instruction: entry.instruction,
      candidate_text: entry.candidate_text,
      draft_excerpt: "",
      max_tokens: MAX_TOKENS,
      task_type: entry.task_type,
      output_type: entry.output_type,
      current_position: {
        draft_id: entry.draft_id,
        version_id: entry.version_id,
      },
      intent: entry.intent ?? "append_current",
      next_unit: null,
    };
    const signature = JSON.stringify(fields);
    const intent = acceptIntentRef.current?.signature === signature
      ? acceptIntentRef.current
      : { key: crypto.randomUUID(), signature };
    acceptIntentRef.current = intent;
    try {
      const outcome = await acceptWriting(projectId, {
        ...fields,
        idempotency_key: intent.key,
      }, options);
      void refreshQuota();
      if (outcome.accepted) {
        // 200 accepted or 502-partial (only analysis failed): a version was
        // saved and the server retired this entry. The parent's refreshKey
        // bump re-fetches and drops it from the list.
        acceptIntentRef.current = null;
        onAccepted?.();
      } else {
        // Non-pass re-gate: nothing saved. The item stays; show why.
        setItemNotes((notes) => ({
          ...notes,
          [entry.id]: {
            kind: "gate",
            decision: outcome.gate?.decision ?? "unknown",
            findings: outcome.gate?.findings ?? [],
          },
        }));
      }
    } catch (err) {
      if (await handleQuotaRefusal(err, () =>
        void acceptItem(entry, { confirmDuplicate: true }))) {
        // 확인 대화가 뜬 상태다 — intent 는 그대로 두어야 확인 뒤 같은 키로
        // 재전송된다(다른 키면 accept 의 멱등 계약이 깨진다).
      } else if (err instanceof ApiError && err.status === 409) {
        // The draft moved on since generation: this entry can't be accepted as
        // -is. Keep it — the copy path is the escape hatch.
        acceptIntentRef.current = null;
        setItemNotes((notes) => ({
          ...notes,
          [entry.id]: {
            kind: "error",
            message:
              "그 사이 새 저장이 생겨 기준 version이 최신이 아닙니다. 아래 본문을 복사해 직접 반영하세요.",
          },
        }));
      } else if (
        err instanceof ApiError &&
        DEFINITIVE_ACCEPT_FAILURES.has(err.status)
      ) {
        acceptIntentRef.current = null;
        setItemNotes((notes) => ({
          ...notes,
          [entry.id]: { kind: "error", message: describeApiError(err) },
        }));
      } else {
        // transport/5xx (or a 502 without a saved version): keep the intent so
        // the same body retries with the same key.
        setItemNotes((notes) => ({
          ...notes,
          [entry.id]: { kind: "error", message: describeApiError(err) },
        }));
      }
    } finally {
      acceptBusyRef.current = false;
      setAcceptingId(null);
    }
  }

  async function discardItem(entry: ScratchCandidate) {
    if (acceptingId !== null || discardingRef.current) return;
    if (!window.confirm("이 초안을 버립니다. 되돌릴 수 없습니다. 계속할까요?")) {
      return;
    }
    const snapshot = items;
    discardingRef.current = true;
    setDiscardingId(entry.id);
    // Optimistic removal; a failed DELETE restores the snapshot (the endpoint
    // 404s only for unknown/cross-project ids, which the pad never produces).
    setItems((prev) => prev.filter((e) => e.id !== entry.id));
    try {
      await discardWritingScratchItem(projectId, entry.id);
    } catch {
      setItems(snapshot);
      setError("초안 버리기에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      discardingRef.current = false;
      setDiscardingId(null);
    }
  }

  async function discardAll() {
    if (discardingRef.current) return;
    if (
      !window.confirm("이어쓰던 미채택 초안을 모두 버립니다. 되돌릴 수 없습니다. 계속할까요?")
    ) {
      return;
    }
    discardingRef.current = true;
    try {
      await discardWritingScratch(projectId, draftId);
      setItems([]);
      setError(null);
    } catch {
      setError("초안 버리기에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      discardingRef.current = false;
    }
  }

  return (
    <section className="scratch-recovery" aria-label="미채택 초안 복구">
      <p className="scratch-recovery-lead">
        이어쓰던 미채택 초안 {items.length}개가 있습니다. 항목을 채택해 version으로
        저장하거나 버릴 수 있습니다.
      </p>
      {error !== null && <p className="scratch-recovery-error">{error}</p>}
      <ol className="scratch-recovery-list">
        {items.map((entry) => {
          const note = itemNotes[entry.id];
          const acceptDisabled =
            entry.version_id === null || readOnly === true || acceptingId !== null;
          return (
            <li key={entry.id} className="scratch-recovery-item">
              <pre className="scratch-recovery-text">{entry.candidate_text}</pre>
              <div className="scratch-recovery-actions">
                <button
                  type="button"
                  className="scratch-recovery-accept"
                  disabled={acceptDisabled}
                  onClick={() => void acceptItem(entry)}
                >
                  {acceptingId === entry.id ? "채택 중…" : "채택"}
                </button>
                <button
                  type="button"
                  disabled={acceptingId !== null || discardingId !== null}
                  onClick={() => void discardItem(entry)}
                >
                  버리기
                </button>
                <button type="button" onClick={() => void copy(entry)}>
                  {copiedId === entry.id ? "복사됨" : "복사"}
                </button>
              </div>
              {entry.version_id === null && (
                <p className="scratch-recovery-note">
                  기준 version이 기록되지 않은 오래된 항목입니다. 복사해 직접
                  반영하세요.
                </p>
              )}
              {note?.kind === "gate" && (
                <div className="scratch-recovery-gate">
                  <p>
                    채택되지 않았습니다. Gate 판정:{" "}
                    <strong>
                      {DECISION_LABEL[note.decision] ?? note.decision}
                    </strong>
                  </p>
                  {note.findings.length > 0 && (
                    <ul>
                      {note.findings.map((finding, index) => (
                        <li key={index} className={`severity-${finding.severity}`}>
                          {finding.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {note?.kind === "error" && (
                <p className="scratch-recovery-error">{note.message}</p>
              )}
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        className="scratch-recovery-discard"
        disabled={acceptingId !== null || discardingId !== null}
        onClick={() => void discardAll()}
      >
        모두 버리기
      </button>
      {pendingConfirm !== null && (
        <div className="writing-confirm" role="alertdialog" aria-label="중복 요청 확인">
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
              하나 더 만들기
            </button>
            <button type="button" onClick={() => setPendingConfirm(null)}>
              취소
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
