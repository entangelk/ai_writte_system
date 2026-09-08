import { useEffect, useRef, useState } from "react";
import {
  discardWritingScratch,
  discardWritingScratchItem,
  listWritingScratch,
  type ScratchCandidate,
} from "../api/client";

type ScratchRecoveryProps = {
  projectId: string;
  draftId: string;
  // Bumped by the parent after a settled background job, so the list re-fetches
  // — the worker appends results.
  refreshKey?: number;
};

// Pre-dogfood safety net (brief D0=B/D1=B/D2=A): a candidate generated but not
// accepted is persisted to `writing_drafts_scratch`. This pad surfaces the
// newest-first unaccepted history. The store is not canonical; per item the user
// can 복사 (copy the text back into the editor by hand) or 버리기 (per-item
// delete).
//
// ★ 채택은 이 패드에 없다(오너 2026-09-08): *"채택은 완전 자동화일 때 사용할 수 있을
// 것 같아. 일반 사용자에게는 불필요한 항목 같아. 버튼을 그냥 없애주고 통로만 열어두자."*
// 서버 엔드포인트(`POST …/writing/accept`)와 API 클라이언트(`acceptWriting`)는 그대로
// 열려 있다 — 없앤 것은 화면의 버튼이지 통로가 아니다.
export function ScratchRecovery(props: ScratchRecoveryProps) {
  const { projectId, draftId, refreshKey } = props;
  const [items, setItems] = useState<ScratchCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [discardingId, setDiscardingId] = useState<string | null>(null);
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

  async function discardItem(entry: ScratchCandidate) {
    if (discardingRef.current) return;
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
        이어쓰던 미채택 초안 {items.length}개가 있습니다. 항목을 펼쳐 본문을 복사해
        편집기에 붙여넣거나, 버릴 수 있습니다.
      </p>
      {error !== null && <p className="scratch-recovery-error">{error}</p>}
      <ol className="scratch-recovery-list">
        {items.map((entry) => (
          <li key={entry.id} className="scratch-recovery-item">
            {/*
              오너 2026-09-08: *"이어쓰기에 있는 글들이 너무 긴데 접어둘 수 없나?"*
              패드 항목은 **지나간 후보**라 기본 접힘이다(방금 만든 후보는 펼침 —
              WritingPanel 쪽 주석 참조). 상태 없이 네이티브 <details> 로 접는다.
            */}
            <details className="scratch-recovery-fold">
              <summary>{previewOf(entry.candidate_text)}</summary>
              <pre className="scratch-recovery-text">{entry.candidate_text}</pre>
            </details>
            <div className="scratch-recovery-actions">
              <button
                type="button"
                disabled={discardingId !== null}
                onClick={() => void discardItem(entry)}
              >
                버리기
              </button>
              <button type="button" onClick={() => void copy(entry)}>
                {copiedId === entry.id ? "복사됨" : "복사"}
              </button>
            </div>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="scratch-recovery-discard"
        disabled={discardingId !== null}
        onClick={() => void discardAll()}
      >
        모두 버리기
      </button>
    </section>
  );
}

/** 접힌 항목의 한 줄 미리보기. 첫 줄을 40자까지 — 넘치면 말줄임을 붙인다. */
function previewOf(text: string): string {
  const firstLine = text.trim().split("\n")[0] ?? "";
  const chars = [...firstLine];
  return chars.length > 40 ? `${chars.slice(0, 40).join("")}…` : firstLine;
}
