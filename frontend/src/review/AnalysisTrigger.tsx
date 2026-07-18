import { useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router";
import { analyzeVersion, describeApiError } from "../api/client";

type AnalysisTriggerProps = {
  projectId: string;
  draftId: string;
  // The latest saved version + its snapshot; analysis runs against a saved
  // snapshot, so these are null until the first save.
  latestVersionId: string | null;
  latestSnapshotId: string | null;
  readOnly: boolean;
  dirty: boolean;
  onStatusChange?: (status: "idle" | "running" | "failed" | "complete") => void;
  onBeforeNavigateAway?: () => boolean;
};

type Result = { candidateCount: number };

// The bridge from writing to review: running analysis extracts needs_review
// candidates (인물·사건·미해결 질문) from the latest saved snapshot via the 12B,
// which then appear in the Review Inbox. Without this the review surface stays
// empty and the loop is unreachable from the editor.
export function AnalysisTrigger(props: AnalysisTriggerProps) {
  const {
    projectId,
    draftId,
    latestVersionId,
    latestSnapshotId,
    readOnly,
    dirty,
    onStatusChange,
    onBeforeNavigateAway,
  } = props;
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Synchronous re-entrancy guard: setBusy is async, so a fast double-click can
  // pass the state check and launch two jobs (WritingPanel uses the same busyRef
  // pattern). The ref flips immediately.
  const busyRef = useRef(false);

  function guardNavigation(event: MouseEvent<HTMLAnchorElement>): void {
    if (onBeforeNavigateAway?.() === false) event.preventDefault();
  }

  const noVersion = latestSnapshotId === null || latestVersionId === null;
  const blocked =
    readOnly || dirty || noVersion
      ? readOnly
        ? "보관된 원고는 분석할 수 없습니다."
        : dirty
          ? "저장하지 않은 변경이 있습니다. 먼저 저장한 뒤 분석하세요."
          : "저장된 version이 없습니다. 본문을 먼저 저장하세요."
      : null;

  async function run() {
    if (
      busyRef.current ||
      blocked !== null ||
      latestSnapshotId === null ||
      latestVersionId === null
    )
      return;
    busyRef.current = true;
    setBusy(true);
    onStatusChange?.("running");
    setError(null);
    setResult(null);
    try {
      const outcome = await analyzeVersion(
        projectId,
        draftId,
        latestVersionId,
        latestSnapshotId,
      );
      setResult({ candidateCount: outcome.candidateCount });
      onStatusChange?.("complete");
    } catch (err) {
      setError(describeApiError(err));
      onStatusChange?.("failed");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="workspace-panel analysis-trigger" aria-labelledby="analysis-title">
      <div className="version-panel-heading">
        <div>
          <p className="eyebrow">검토 후보 생성</p>
          <h2 id="analysis-title">원고 분석</h2>
        </div>
        <Link
          className="review-link"
          to={`/projects/${projectId}/review`}
          onClick={guardNavigation}
        >
          검토함 →
        </Link>
      </div>

      {blocked !== null ? (
        <p className="writing-block" role="note">
          <span className="writing-block-reason">{blocked}</span>
        </p>
      ) : (
        <p className="writing-hint">
          최신 저장 version에서 인물·사건·미해결 질문을 추출해 검토 후보를 만듭니다.
          생성된 후보는 검토함에서 승인·거절·수정할 수 있습니다.
        </p>
      )}

      <div className="writing-actions">
        <button type="button" disabled={busy || blocked !== null} onClick={() => void run()}>
          {busy ? "분석 중… (12B 추출)" : "이 원고 분석"}
        </button>
      </div>

      {busy && (
        <p className="writing-progress" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          원고에서 검토 후보를 추출하는 중…
        </p>
      )}
      {error !== null && (
        <div className="writing-error" role="alert">
          <p className="alert">{error}</p>
          <button
            type="button"
            className="writing-retry"
            disabled={busy || blocked !== null}
            onClick={() => void run()}
          >
            다시 분석
          </button>
        </div>
      )}
      {result !== null && (
        <p className="writing-notice" role="status">
          {result.candidateCount > 0 ? (
            <>
              {result.candidateCount}개 검토 후보가 생성됐습니다.{" "}
              <Link to={`/projects/${projectId}/review`} onClick={guardNavigation}>
                검토함에서 확인하세요 →
              </Link>
            </>
          ) : (
            "이번 분석에서는 새 검토 후보가 추출되지 않았습니다. 본문을 보완한 뒤 다시 시도해 보세요."
          )}
        </p>
      )}
    </section>
  );
}
