import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  confirmCandidate,
  describeApiError,
  dismissGateFinding,
  listReviewInbox,
  rejectCandidate,
  resolveGateFinding,
  type ReviewAffordance,
  type ReviewInboxListResponse,
} from "../api/client";

// The frontend never recomputes eligibility. Each button is rendered from the
// server's affordance (`eligible` drives `disabled`, `reason` fills the title),
// and this slice only wires the four binary actions — confirm/reject on a
// candidate and resolve/dismiss on a gate finding. Candidate `edit` and conflict
// `merge`/`split` affordances are carried in the payload but not yet actioned.
const ACTION_LABELS: Record<string, string> = {
  confirm: "승인",
  reject: "거절",
  resolve: "해결",
  dismiss: "무시",
};

const CANDIDATE_TYPE_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥",
};

const PAYLOAD_FIELD_LABELS: Record<string, string> = {
  name: "이름",
  observation: "관찰",
  event: "사건",
  question: "미해결 질문",
};

function renderPayloadValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function findAffordance(
  actions: ReviewAffordance[],
  action: string,
): ReviewAffordance | undefined {
  return actions.find((a) => a.action === action);
}

export function ReviewInbox() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<ReviewInboxListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (projectId === undefined) {
      return;
    }
    const response = await listReviewInbox(projectId);
    setData(response);
  }, [projectId]);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    void listReviewInbox(projectId)
      .then((response) => {
        if (active) {
          setData(response);
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
  }, [projectId]);

  // Run one review action, then re-read the inbox so the rendered list is always
  // the server's truth (the acted item leaves the inbox). No optimistic patch.
  async function runAction(
    key: string,
    op: () => Promise<void>,
  ): Promise<void> {
    if (busy !== null) {
      return;
    }
    setBusy(key);
    try {
      await op();
      setError(null);
      await load();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>
        ← 원고 작업 공간으로
      </Link>

      <header className="page-heading">
        <p className="eyebrow">검토함</p>
        <h1>기억 후보와 게이트 지적</h1>
        <p>AI가 만든 기억 후보와 문맥 게이트 지적을 확인하고 처리합니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {loading ? (
        <p className="status-copy">검토 항목을 불러오는 중…</p>
      ) : data === null ? null : (
        <>
          <h2 className="section-title">기억 후보</h2>
          {data.items.length === 0 ? (
            <div className="empty-state">
              <p>검토할 기억 후보가 없습니다.</p>
              <span>분석이 새 후보를 만들면 여기에서 승인·거절할 수 있습니다.</span>
            </div>
          ) : (
            <ul className="resource-list" aria-label="기억 후보 목록">
              {data.items.map((item) => {
                const confirm = findAffordance(item.actions, "confirm");
                const reject = findAffordance(item.actions, "reject");
                return (
                  <li className="resource-row review-row" key={item.candidate_id}>
                    <Link
                      className="resource-link review-summary-link"
                      to={`/projects/${projectId}/review/${item.candidate_id}`}
                    >
                      <div className="review-summary">
                        <div className="review-summary-heading">
                          <strong>
                            {CANDIDATE_TYPE_LABELS[item.candidate_type] ??
                              item.candidate_type}
                          </strong>
                          <span className="row-meta">
                            신뢰도 {item.confidence.toFixed(2)}
                            {item.conflict_count > 0 &&
                              ` · 충돌 ${item.conflict_count}`}
                          </span>
                        </div>
                        <dl className="review-preview-fields">
                          {Object.entries(item.payload).map(([key, value]) => (
                            <div key={key}>
                              <dt>{PAYLOAD_FIELD_LABELS[key] ?? key}</dt>
                              <dd>{renderPayloadValue(value)}</dd>
                            </div>
                          ))}
                        </dl>
                        <span className="review-detail-link">상세 검토 →</span>
                      </div>
                    </Link>
                    <div className="row-actions">
                      {confirm && (
                        <button
                          type="button"
                          disabled={!confirm.eligible || busy !== null}
                          title={confirm.reason ?? undefined}
                          onClick={() =>
                            runAction(`confirm:${item.candidate_id}`, () =>
                              confirmCandidate(projectId!, item.candidate_id),
                            )
                          }
                        >
                          {ACTION_LABELS.confirm}
                        </button>
                      )}
                      {reject && (
                        <button
                          type="button"
                          className="ghost"
                          disabled={!reject.eligible || busy !== null}
                          title={reject.reason ?? undefined}
                          onClick={() =>
                            runAction(`reject:${item.candidate_id}`, () =>
                              rejectCandidate(projectId!, item.candidate_id),
                            )
                          }
                        >
                          {ACTION_LABELS.reject}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <h2 className="section-title">게이트 지적</h2>
          {data.gate_findings.length === 0 ? (
            <div className="empty-state">
              <p>열린 게이트 지적이 없습니다.</p>
            </div>
          ) : (
            <ul className="resource-list" aria-label="게이트 지적 목록">
              {data.gate_findings.map((finding) => {
                const resolve = findAffordance(finding.actions, "resolve");
                const dismiss = findAffordance(finding.actions, "dismiss");
                return (
                  <li className="resource-row review-row" key={finding.id}>
                    <div className="finding-copy">
                      <span className="finding-check">{finding.check}</span>
                      <span className="row-meta">{finding.detail}</span>
                    </div>
                    <div className="row-actions">
                      {resolve && (
                        <button
                          type="button"
                          disabled={!resolve.eligible || busy !== null}
                          title={resolve.reason ?? undefined}
                          onClick={() =>
                            runAction(`resolve:${finding.id}`, () =>
                              resolveGateFinding(projectId!, finding.id),
                            )
                          }
                        >
                          {ACTION_LABELS.resolve}
                        </button>
                      )}
                      {dismiss && (
                        <button
                          type="button"
                          className="ghost"
                          disabled={!dismiss.eligible || busy !== null}
                          title={dismiss.reason ?? undefined}
                          onClick={() =>
                            runAction(`dismiss:${finding.id}`, () =>
                              dismissGateFinding(projectId!, finding.id),
                            )
                          }
                        >
                          {ACTION_LABELS.dismiss}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
