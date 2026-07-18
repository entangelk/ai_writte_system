import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useSearchParams } from "react-router";
import {
  confirmCandidate,
  describeApiError,
  getReviewInboxItem,
  listReviewInbox,
  rejectCandidate,
  type ReviewInboxDetailItem,
  type ReviewInboxListResponse,
  type ReviewSourcePointer,
} from "../api/client";

type Props = {
  projectId: string;
  onSourceSelect: (source: ReviewSourcePointer) => void;
  onPendingCountChange?: (count: number) => void;
  onBeforeNavigateAway?: () => boolean;
};

const TYPE_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥",
};

function exactSource(source: ReviewSourcePointer): boolean {
  return source.status === "resolved" &&
    source.snapshot_id !== undefined &&
    source.start_offset !== undefined &&
    source.end_offset !== undefined &&
    source.quote !== undefined &&
    source.content_hash !== undefined;
}

function renderValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function WorkspaceReviewPanel({
  projectId,
  onSourceSelect,
  onPendingCountChange,
  onBeforeNavigateAway,
}: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const candidateId = searchParams.get("candidate");
  const sourceId = searchParams.get("source");
  const [data, setData] = useState<ReviewInboxListResponse | null>(null);
  const [detail, setDetail] = useState<ReviewInboxDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredSourceRef = useRef<string | null>(null);
  const confirm = detail?.actions.find((action) => action.action === "confirm");
  const reject = detail?.actions.find((action) => action.action === "reject");

  function guardNavigation(event: MouseEvent<HTMLAnchorElement>): void {
    if (onBeforeNavigateAway?.() === false) event.preventDefault();
  }

  const load = useCallback(async () => {
    const response = await listReviewInbox(projectId);
    setData(response);
    onPendingCountChange?.(response.items.length + response.gate_findings.length);
  }, [onPendingCountChange, projectId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void listReviewInbox(projectId)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError(null);
        onPendingCountChange?.(response.items.length + response.gate_findings.length);
      })
      .catch((err: unknown) => {
        if (active) setError(describeApiError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [onPendingCountChange, projectId]);

  useEffect(() => {
    if (candidateId === null) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    void getReviewInboxItem(projectId, candidateId)
      .then((response) => {
        if (!active) return;
        setDetail(response);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(describeApiError(err));
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [candidateId, projectId]);

  useEffect(() => {
    if (detail === null || sourceId === null) return;
    const restoreKey = `${candidateId ?? ""}:${sourceId}`;
    if (restoredSourceRef.current === restoreKey) return;
    const source = detail.source_refs.find((item) => item.source_ref_id === sourceId);
    if (source !== undefined && exactSource(source)) {
      restoredSourceRef.current = restoreKey;
      onSourceSelect(source);
    }
  }, [candidateId, detail, onSourceSelect, sourceId]);

  function selectCandidate(nextCandidateId: string | null): void {
    const next = new URLSearchParams(searchParams);
    if (nextCandidateId === null) next.delete("candidate");
    else next.set("candidate", nextCandidateId);
    next.delete("source");
    setSearchParams(next);
  }

  function selectSource(source: ReviewSourcePointer): void {
    if (!exactSource(source)) return;
    const next = new URLSearchParams(searchParams);
    next.set("source", source.source_ref_id);
    setSearchParams(next);
    restoredSourceRef.current = `${candidateId ?? ""}:${source.source_ref_id}`;
    onSourceSelect(source);
  }

  async function runAction(action: "confirm" | "reject"): Promise<void> {
    if (candidateId === null || busy) return;
    setBusy(true);
    try {
      if (action === "confirm") await confirmCandidate(projectId, candidateId);
      else await rejectCandidate(projectId, candidateId);
      selectCandidate(null);
      await load();
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="status-copy">검토 항목을 불러오는 중…</p>;

  return (
    <div className="workspace-review">
      {error !== null && <p className="alert" role="alert">{error}</p>}
      {candidateId === null ? (
        <>
          <div className="rail-section-heading">
            <h2>검토 대기</h2>
            <span>{(data?.items.length ?? 0) + (data?.gate_findings.length ?? 0)}건</span>
          </div>
          {data?.items.length === 0 ? (
            <p className="status-copy">검토할 기억 후보가 없습니다.</p>
          ) : (
            <ul className="rail-review-list" aria-label="검토 후보 목록">
              {data?.items.map((item) => (
                <li key={item.candidate_id}>
                  <button type="button" onClick={() => selectCandidate(item.candidate_id)}>
                    <span>{TYPE_LABELS[item.candidate_type] ?? item.candidate_type}</span>
                    <small>신뢰도 {item.confidence.toFixed(2)} · 근거 보기</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {(data?.gate_findings.length ?? 0) > 0 && (
            <p className="status-copy">게이트 지적 {data!.gate_findings.length}건은 전체 검토함에서 처리할 수 있습니다.</p>
          )}
          <Link
            className="section-link"
            to={`/projects/${projectId}/review`}
            onClick={guardNavigation}
          >전체 검토함 열기 →</Link>
        </>
      ) : detailLoading ? (
        <p className="status-copy">후보 상세를 불러오는 중…</p>
      ) : detail === null ? null : (
        <>
          <button className="rail-back" type="button" onClick={() => selectCandidate(null)}>← 후보 목록</button>
          <div className="rail-section-heading">
            <h2>{TYPE_LABELS[detail.candidate_type] ?? detail.candidate_type} 후보</h2>
            <span>신뢰도 {detail.confidence.toFixed(2)}</span>
          </div>
          <dl className="rail-detail-fields">
            {Object.entries(detail.payload).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{renderValue(value)}</dd></div>
            ))}
          </dl>
          <div className="row-actions rail-actions">
            {confirm !== undefined && (
              <button
                type="button"
                disabled={busy || !confirm.eligible}
                title={confirm.reason ?? undefined}
                onClick={() => void runAction("confirm")}
              >승인</button>
            )}
            {reject !== undefined && (
              <button
                className="ghost"
                type="button"
                disabled={busy || !reject.eligible}
                title={reject.reason ?? undefined}
                onClick={() => void runAction("reject")}
              >거절</button>
            )}
          </div>
          <h3>원문 근거</h3>
          <ul className="rail-source-list">
            {detail.source_refs.map((source) => (
              <li key={source.source_ref_id}>
                {exactSource(source) ? (
                  <button type="button" onClick={() => selectSource(source)}>
                    <q>{source.quote}</q><span>원고에서 보기 →</span>
                  </button>
                ) : (
                  <p className="status-copy">원문을 찾을 수 없습니다.</p>
                )}
              </li>
            ))}
          </ul>
          <Link
            className="section-link"
            to={`/projects/${projectId}/review/${candidateId}`}
            onClick={guardNavigation}
          >수정·충돌 처리 열기 →</Link>
        </>
      )}
    </div>
  );
}
