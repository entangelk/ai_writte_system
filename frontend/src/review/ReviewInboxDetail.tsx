import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  confirmCandidate,
  describeApiError,
  editCandidate,
  getReviewInboxItem,
  reconcileConflict,
  rejectCandidate,
  type ReviewInboxDetailItem,
} from "../api/client";

const CANDIDATE_TYPE_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥",
};

const CONFLICT_ACTION_LABELS: Record<string, string> = {
  merge: "병합",
  split: "분리",
};

function renderValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

export function ReviewInboxDetail() {
  const { projectId, candidateId } = useParams<{
    projectId: string;
    candidateId: string;
  }>();
  const navigate = useNavigate();
  const [item, setItem] = useState<ReviewInboxDetailItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // Edit mode holds a per-field string draft of the candidate payload. The
  // taxonomy payload is an exact key set of non-empty strings, so we edit the
  // existing fields in place (adding/removing keys would fail server validation).
  const [draft, setDraft] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    if (projectId === undefined || candidateId === undefined) {
      setError("검토 항목 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    void getReviewInboxItem(projectId, candidateId)
      .then((detail) => {
        if (active) {
          setItem(detail);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(describeApiError(err));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [projectId, candidateId]);

  // Every write here (confirm/reject/edit/merge/split) removes the candidate or
  // resolves its conflict, so on success we leave the detail and return to the
  // list, which re-reads the server truth. No optimistic patch.
  async function submit(op: () => Promise<void>): Promise<void> {
    if (projectId === undefined || busy) {
      return;
    }
    setBusy(true);
    try {
      await op();
      navigate(`/projects/${projectId}/review`);
    } catch (err) {
      setError(describeApiError(err));
      setBusy(false);
    }
  }

  function startEdit(): void {
    if (item === null) {
      return;
    }
    const next: Record<string, string> = {};
    for (const [field, value] of Object.entries(item.payload)) {
      next[field] = typeof value === "string" ? value : renderValue(value);
    }
    setDraft(next);
  }

  const confirm = item?.actions.find((a) => a.action === "confirm");
  const reject = item?.actions.find((a) => a.action === "reject");
  const edit = item?.actions.find((a) => a.action === "edit");
  const editIncomplete =
    draft !== null && Object.values(draft).some((v) => v.trim() === "");

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}/review`}>
        ← 검토함으로
      </Link>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {loading ? (
        <p className="status-copy">검토 항목을 불러오는 중…</p>
      ) : item === null ? null : (
        <>
          <header className="page-heading">
            <p className="eyebrow">
              {CANDIDATE_TYPE_LABELS[item.candidate_type] ?? item.candidate_type}{" "}
              후보
            </p>
            <h1>기억 후보 검토</h1>
            <p>신뢰도 {item.confidence.toFixed(2)} · 근거 {item.source_refs.length}건</p>
          </header>

          {draft === null && (
            <div className="row-actions detail-actions">
              {confirm && (
                <button
                  type="button"
                  disabled={!confirm.eligible || busy}
                  title={confirm.reason ?? undefined}
                  onClick={() =>
                    submit(() => confirmCandidate(projectId!, candidateId!))
                  }
                >
                  승인
                </button>
              )}
              {edit && (
                <button
                  type="button"
                  className="ghost"
                  disabled={!edit.eligible || busy}
                  title={edit.reason ?? undefined}
                  onClick={startEdit}
                >
                  수정
                </button>
              )}
              {reject && (
                <button
                  type="button"
                  className="ghost"
                  disabled={!reject.eligible || busy}
                  title={reject.reason ?? undefined}
                  onClick={() =>
                    submit(() => rejectCandidate(projectId!, candidateId!))
                  }
                >
                  거절
                </button>
              )}
            </div>
          )}

          <h2 className="section-title">새 값</h2>
          {draft === null ? (
            <dl className="detail-fields">
              {Object.entries(item.payload).map(([field, value]) => (
                <div className="detail-field" key={field}>
                  <dt>{field}</dt>
                  <dd>{renderValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <form
              className="edit-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (!editIncomplete) {
                  submit(() => editCandidate(projectId!, candidateId!, draft));
                }
              }}
            >
              {Object.entries(draft).map(([field, value]) => (
                <div className="edit-field" key={field}>
                  <label htmlFor={`edit-${field}`}>{field}</label>
                  <textarea
                    id={`edit-${field}`}
                    value={value}
                    rows={field === "name" ? 1 : 3}
                    onChange={(event) =>
                      setDraft({ ...draft, [field]: event.target.value })
                    }
                  />
                </div>
              ))}
              <div className="row-actions">
                <button type="submit" disabled={editIncomplete || busy}>
                  저장
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => setDraft(null)}
                >
                  취소
                </button>
              </div>
            </form>
          )}

          <h2 className="section-title">원문 근거</h2>
          {item.source_refs.length === 0 ? (
            <p className="status-copy">연결된 원문 근거가 없습니다.</p>
          ) : (
            <ul className="quote-list">
              {item.source_refs.map((ref) => (
                <li className="quote-row" key={ref.source_ref_id}>
                  {ref.status === "resolved" ? (
                    <blockquote>{ref.quote}</blockquote>
                  ) : (
                    <p className="status-copy">원문을 찾을 수 없습니다.</p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {item.conflicts.length > 0 && (
            <>
              <h2 className="section-title">기존 기억과의 차이</h2>
              {item.conflicts.map((conflict) => {
                const merge = conflict.actions.find((a) => a.action === "merge");
                const split = conflict.actions.find((a) => a.action === "split");
                return (
                  <div className="conflict-card" key={conflict.entry_id}>
                    <p className="row-meta">{conflict.rationale}</p>
                    {conflict.diff.length > 0 && (
                      <table className="diff-table">
                        <thead>
                          <tr>
                            <th>필드</th>
                            <th>기존</th>
                            <th>제안</th>
                          </tr>
                        </thead>
                        <tbody>
                          {conflict.diff.map((diff) => (
                            <tr key={diff.field}>
                              <td>{diff.field}</td>
                              <td>{renderValue(diff.before)}</td>
                              <td>{renderValue(diff.after)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {draft === null && (merge || split) && (
                      <div className="row-actions">
                        {merge && (
                          <button
                            type="button"
                            disabled={!merge.eligible || busy}
                            title={merge.reason ?? undefined}
                            onClick={() =>
                              submit(() =>
                                reconcileConflict(
                                  projectId!,
                                  conflict.entry_id,
                                  "merge",
                                ),
                              )
                            }
                          >
                            {CONFLICT_ACTION_LABELS.merge}
                          </button>
                        )}
                        {split && (
                          <button
                            type="button"
                            className="ghost"
                            disabled={!split.eligible || busy}
                            title={split.reason ?? undefined}
                            onClick={() =>
                              submit(() =>
                                reconcileConflict(
                                  projectId!,
                                  conflict.entry_id,
                                  "split",
                                ),
                              )
                            }
                          >
                            {CONFLICT_ACTION_LABELS.split}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </>
      )}
    </section>
  );
}
