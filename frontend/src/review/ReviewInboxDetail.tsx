import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  confirmCandidate,
  describeApiError,
  getReviewInboxItem,
  rejectCandidate,
  type ReviewInboxDetailItem,
} from "../api/client";

const CANDIDATE_TYPE_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥",
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

  // A confirm/reject removes the candidate from the inbox, so on success we
  // leave the detail and return to the list (which re-reads the server truth).
  async function runAction(
    op: (projectId: string, candidateId: string) => Promise<void>,
  ): Promise<void> {
    if (projectId === undefined || candidateId === undefined || busy) {
      return;
    }
    setBusy(true);
    try {
      await op(projectId, candidateId);
      navigate(`/projects/${projectId}/review`);
    } catch (err) {
      setError(describeApiError(err));
      setBusy(false);
    }
  }

  const confirm = item?.actions.find((a) => a.action === "confirm");
  const reject = item?.actions.find((a) => a.action === "reject");

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

          <div className="row-actions detail-actions">
            {confirm && (
              <button
                type="button"
                disabled={!confirm.eligible || busy}
                title={confirm.reason ?? undefined}
                onClick={() => runAction(confirmCandidate)}
              >
                승인
              </button>
            )}
            {reject && (
              <button
                type="button"
                className="ghost"
                disabled={!reject.eligible || busy}
                title={reject.reason ?? undefined}
                onClick={() => runAction(rejectCandidate)}
              >
                거절
              </button>
            )}
          </div>

          <h2 className="section-title">새 값</h2>
          <dl className="detail-fields">
            {Object.entries(item.payload).map(([field, value]) => (
              <div className="detail-field" key={field}>
                <dt>{field}</dt>
                <dd>{renderValue(value)}</dd>
              </div>
            ))}
          </dl>

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
              {item.conflicts.map((conflict) => (
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
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}
