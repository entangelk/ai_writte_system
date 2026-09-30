import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useSearchParams } from "react-router";
import {
  confirmCandidate,
  describeApiError,
  editCandidate,
  getReviewInboxItem,
  listReviewInbox,
  rejectCandidate,
  type ReviewInboxDetailItem,
  type ReviewInboxListResponse,
  type ReviewInboxItem,
  type ReviewSourcePointer,
} from "../api/client";
import { buildEntries } from "./reviewEntries";

type Props = {
  projectId: string;
  // Layer tabs: the panel stays mounted across tab switches (so its state
  // survives), but only fetches when it is the active tab — inactive tabs skip
  // the inbox/detail fetches entirely (no mock interference, no wasted calls).
  // Optional (defaults to active) so standalone unit renders need not pass it.
  tabActive?: boolean;
  onSourceSelect: (source: ReviewSourcePointer) => void;
  onPendingCountChange?: (count: number) => void;
  onBeforeNavigateAway?: () => boolean;
};

const FIELD_LABELS: Record<string, string> = {
  name: "이름",
  observation: "관찰",
  event: "사건",
  question: "미해결 질문",
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
  tabActive,
  onSourceSelect,
  onPendingCountChange,
  onBeforeNavigateAway,
}: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const candidateId = searchParams.get("candidate");
  const sourceId = searchParams.get("source");
  const [data, setData] = useState<ReviewInboxListResponse | null>(null);
  const [detail, setDetail] = useState<ReviewInboxDetailItem | null>(null);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredSourceRef = useRef<string | null>(null);
  const confirm = detail?.actions?.find((action) => action.action === "confirm");
  const reject = detail?.actions?.find((action) => action.action === "reject");
  const edit = detail?.actions?.find((action) => action.action === "edit");
  const editIncomplete = draft !== null && Object.values(draft).some((value) => value.trim() === "");

  function guardNavigation(event: MouseEvent<HTMLAnchorElement>): void {
    if (onBeforeNavigateAway?.() === false) event.preventDefault();
  }

  const load = useCallback(async () => {
    const response = await listReviewInbox(projectId);
    setData(response);
    onPendingCountChange?.(response.items.length + response.gate_findings.length);
  }, [onPendingCountChange, projectId]);

  useEffect(() => {
    if (tabActive === false) return;
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
  }, [tabActive, onPendingCountChange, projectId]);

  useEffect(() => {
    if (candidateId === null) {
      setDetail(null);
      return;
    }
    if (tabActive === false) return;
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
  }, [tabActive, candidateId, projectId]);

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
    setDraft(null);
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

  async function runAction(action: "confirm" | "reject" | "edit"): Promise<void> {
    if (candidateId === null || busy) return;
    setBusy(true);
    try {
      if (action === "confirm") await confirmCandidate(projectId, candidateId);
      else if (action === "reject") await rejectCandidate(projectId, candidateId);
      else if (draft !== null) await editCandidate(projectId, candidateId, draft);
      selectCandidate(null);
      await load();
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(): void {
    if (detail === null) return;
    setDraft(Object.fromEntries(
      Object.entries(detail.payload).map(([field, value]) => [field, renderValue(value)]),
    ));
  }

  function candidateRow(item: ReviewInboxItem, grouped = false) {
    return (
      <li key={item.candidate_id}>
        <button type="button" onClick={() => selectCandidate(item.candidate_id)}>
          <span>{TYPE_LABELS[item.candidate_type] ?? item.candidate_type}</span>
          <small>
            {grouped && `분석 ${item.job_id} · `}
            신뢰도 {item.confidence.toFixed(2)} · 근거 보기
          </small>
        </button>
      </li>
    );
  }

  if (loading) return <p className="status-copy">검토 항목을 불러오는 중…</p>;

  return (
    <div className="workspace-review">
      {error !== null && <p className="alert" role="alert">{error}</p>}
      {candidateId === null ? (
        <>
          <div className="rail-section-heading">
            <h2>검토 대기</h2>
            <span>{(data?.items?.length ?? 0) + (data?.gate_findings?.length ?? 0)}건</span>
          </div>
          {(data?.items?.length ?? 0) === 0 ? (
            <p className="status-copy">검토할 기억 후보가 없습니다.</p>
          ) : (
            <ul className="rail-review-list" aria-label="검토 후보 목록">
              {buildEntries(data!.items).map((entry) =>
                entry.kind === "candidate" ? candidateRow(entry.item) : (
                  <li className="rail-review-group" key={entry.group.group_id}>
                    <strong>
                      {TYPE_LABELS[entry.members[0].candidate_type] ?? entry.members[0].candidate_type}
                      {" "}후보 {entry.group.group_size}건 묶음
                    </strong>
                    {entry.group.identity_rationale_summary !== null && (
                      <small>{entry.group.identity_rationale_summary}</small>
                    )}
                    {entry.group.group_status === "contradicted" && (
                      <small>상충하는 판정이 있어 개별 확인이 필요합니다.</small>
                    )}
                    <ul className="rail-group-members" aria-label="그룹 안 후보 목록">
                      {entry.members.map((item) => candidateRow(item, true))}
                    </ul>
                  </li>
                ),
              )}
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
          {draft === null ? (
            <dl className="rail-detail-fields">
              {Object.entries(detail.payload).map(([key, value]) => (
                <div key={key}><dt>{FIELD_LABELS[key] ?? key}</dt><dd>{renderValue(value)}</dd></div>
              ))}
            </dl>
          ) : (
            <form className="edit-form" onSubmit={(event) => {
              event.preventDefault();
              if (!editIncomplete) void runAction("edit");
            }}>
              {Object.entries(draft).map(([field, value]) => (
                <div className="edit-field" key={field}>
                  <label htmlFor={`rail-edit-${field}`}>{FIELD_LABELS[field] ?? field}</label>
                  <textarea
                    id={`rail-edit-${field}`}
                    value={value}
                    rows={field === "name" ? 1 : 3}
                    onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
                  />
                </div>
              ))}
              <div className="row-actions">
                <button type="submit" disabled={editIncomplete || busy}>저장</button>
                <button type="button" className="ghost" disabled={busy} onClick={() => setDraft(null)}>취소</button>
              </div>
            </form>
          )}
          {draft === null && <div className="row-actions rail-actions">
            {confirm !== undefined && (
              <button
                type="button"
                disabled={busy || !confirm.eligible}
                title={confirm.reason ?? undefined}
                onClick={() => void runAction("confirm")}
              >승인</button>
            )}
            {edit !== undefined && (
              <button
                className="ghost"
                type="button"
                disabled={busy || !edit.eligible}
                title={edit.reason ?? undefined}
                onClick={startEdit}
              >수정</button>
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
          </div>}
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
