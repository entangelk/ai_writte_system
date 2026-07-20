import { useEffect, useRef, useState } from "react";
import {
  discardWritingScratch,
  listWritingScratch,
  type ScratchCandidate,
} from "../api/client";

type ScratchRecoveryProps = {
  projectId: string;
  draftId: string;
  // Bumped by the parent after a successful accept so the banner re-fetches and
  // disappears once the draft's scratch was cleared server-side.
  refreshKey?: number;
};

// Pre-dogfood safety net (brief D0=B/D1=B/D2=A): a candidate generated but not
// accepted is persisted to `writing_drafts_scratch`. On draft-editor entry this
// surfaces the newest-first unaccepted history so the user can recover the text
// (copy it back) or discard it — closing the "새로고침하면 초안 소실" gap. The
// store is not canonical; recovery here is copy-back, not an editor mutation.
export function ScratchRecovery(props: ScratchRecoveryProps) {
  const { projectId, draftId, refreshKey } = props;
  const [items, setItems] = useState<ScratchCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const discardingRef = useRef(false);

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
        이어쓰던 미채택 초안 {items.length}개가 있습니다. 저장(채택)하면 자동으로 정리됩니다.
      </p>
      {error !== null && <p className="scratch-recovery-error">{error}</p>}
      <ol className="scratch-recovery-list">
        {items.map((entry) => (
          <li key={entry.id} className="scratch-recovery-item">
            <pre className="scratch-recovery-text">{entry.candidate_text}</pre>
            <button type="button" onClick={() => void copy(entry)}>
              {copiedId === entry.id ? "복사됨" : "복사"}
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="scratch-recovery-discard"
        onClick={() => void discardAll()}
      >
        모두 버리기
      </button>
    </section>
  );
}
