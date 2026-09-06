import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  approveIdentityGroup,
  confirmCandidate,
  describeApiError,
  dismissGateFinding,
  listReviewInbox,
  rejectCandidate,
  rejectIdentityGroup,
  resolveGateFinding,
  type IdentityGroupApproveResult,
  type IdentityGroupRejectResult,
  type ReviewAffordance,
  type ReviewIdentityGroup,
  type ReviewInboxItem,
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

// Slice 6 — the server's step literals. Unknown values render verbatim rather
// than as "알 수 없음": a literal the UI has not learned yet is still a fact.
const STEP_STATUS_LABELS: Record<string, string> = {
  applied: "반영됨",
  conflict: "충돌 — 검토 대기열로",
  failed: "실패",
  skipped: "건너뜀",
  pending: "이번 패스에서 처리 안 됨",
};

const GROUP_STATUS_NOTES: Record<string, string> = {
  contradicted: "상충하는 판정이 있는 그룹입니다. 승인 전에 후보를 직접 확인하세요.",
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

/**
 * One rendered entry: either a lone candidate or a whole identity group.
 *
 * The server sends a flat item list where every member of a group repeats the
 * same `identity_group` object, so the grouping happens here. Order is first
 * appearance — a group sits where its first member did, which keeps the list
 * stable against member churn (a member leaving the inbox must not make the
 * group jump).
 */
type InboxEntry =
  | { kind: "candidate"; item: ReviewInboxItem }
  | { kind: "group"; group: ReviewIdentityGroup; members: ReviewInboxItem[] };

function buildEntries(items: ReviewInboxItem[]): InboxEntry[] {
  const entries: InboxEntry[] = [];
  const byGroup = new Map<string, Extract<InboxEntry, { kind: "group" }>>();
  for (const item of items) {
    const group = item.identity_group ?? null;
    if (group === null) {
      entries.push({ kind: "candidate", item });
      continue;
    }
    const existing = byGroup.get(group.group_id);
    if (existing === undefined) {
      const entry = {
        kind: "group" as const,
        group,
        members: [item],
      };
      byGroup.set(group.group_id, entry);
      entries.push(entry);
    } else {
      existing.members.push(item);
    }
  }
  return entries;
}

/** The last group action's outcome, kept across the reload that follows it. */
type GroupOutcome =
  | { kind: "approve"; groupId: string; result: IdentityGroupApproveResult }
  | { kind: "reject"; groupId: string; result: IdentityGroupRejectResult };

export function ReviewInbox() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<ReviewInboxListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Kept out of `data` on purpose: the reload after an action replaces `data`,
  // and a partial pass (conflict/failed/pending members) must not disappear
  // with it — "부분 실패는 성공처럼 닫지 않는다" lives here.
  const [outcome, setOutcome] = useState<GroupOutcome | null>(null);

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

  function toggleGroup(groupId: string): void {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  }

  function candidateActions(item: ReviewInboxItem) {
    const confirm = findAffordance(item.actions, "confirm");
    const reject = findAffordance(item.actions, "reject");
    return (
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
    );
  }

  function candidateSummary(item: ReviewInboxItem) {
    return (
      <Link
        className="resource-link review-summary-link"
        to={`/projects/${projectId}/review/${item.candidate_id}`}
      >
        <div className="review-summary">
          <div className="review-summary-heading">
            <strong>
              {CANDIDATE_TYPE_LABELS[item.candidate_type] ?? item.candidate_type}
            </strong>
            <span className="row-meta">
              신뢰도 {item.confidence.toFixed(2)}
              {item.conflict_count > 0 && ` · 충돌 ${item.conflict_count}`}
              {/* 그룹 안에서 후보를 가르는 축은 어느 분석 job이 만들었는가다. */}
              {item.identity_group != null && ` · 분석 ${item.job_id}`}
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
    );
  }

  /**
   * The last group action's outcome, rendered at page level rather than inside
   * the group row. A finished group leaves the inbox entirely, so a panel that
   * lived in the row would vanish with it — and the reject summary ("건너뜀 N건")
   * and a partial pass are exactly the facts that must outlive the reload.
   */
  function groupOutcomePanel() {
    if (outcome === null) {
      return null;
    }
    if (outcome.kind === "reject") {
      const { rejected, skipped, idempotent_replay } = outcome.result;
      return (
        <div className="group-outcome" role="status">
          <p>
            그룹 거절 — 거절 {rejected.length}건 · 건너뜀 {skipped.length}건
            {idempotent_replay && " (이미 끝난 그룹이라 새로 바뀐 것은 없습니다)"}
          </p>
        </div>
      );
    }
    const { steps, canonical_memory_id, idempotent_replay } = outcome.result;
    // A pass is unfinished while any member is not `applied`/`skipped`. Saying
    // so explicitly is the point: the click succeeded (200) but the group did
    // not close, and the next click resumes from the stored progress.
    const unfinished = steps.filter(
      (step) => step.status !== "applied" && step.status !== "skipped",
    );
    return (
      <div className="group-outcome" role="status">
        <p>
          그룹 승인 — 반영 {steps.filter((s) => s.status === "applied").length}건
          {canonical_memory_id !== null && ` · 정본 기억 ${canonical_memory_id}`}
          {idempotent_replay && " (이미 끝난 패스의 재확인입니다)"}
        </p>
        <ul className="group-step-list">
          {steps.map((step) => (
            <li key={step.candidate_id}>
              <span className="group-step-status">
                {STEP_STATUS_LABELS[step.status] ?? step.status}
              </span>
              <span className="row-meta">
                {step.candidate_id}
                {step.action !== null && ` · ${step.action}`}
                {step.error !== null && ` · ${step.error}`}
              </span>
            </li>
          ))}
        </ul>
        {unfinished.length > 0 && (
          <p className="group-outcome-remaining">
            {unfinished.length}건이 남았습니다. 충돌 후보는 검토 대기열에서 개별로
            처리하고, 나머지는 승인을 다시 눌러 이어서 진행합니다.
          </p>
        )}
      </div>
    );
  }

  function groupEntry(entry: Extract<InboxEntry, { kind: "group" }>) {
    const { group, members } = entry;
    const isCollapsed = collapsed.has(group.group_id);
    const note = GROUP_STATUS_NOTES[group.group_status];
    return (
      <li className="resource-row review-group" key={`group:${group.group_id}`}>
        <div className="review-group-header">
          <div className="review-group-copy">
            <div className="review-summary-heading">
              <strong>
                {CANDIDATE_TYPE_LABELS[members[0].candidate_type] ??
                  members[0].candidate_type}{" "}
                후보 {group.group_size}건이 같은 대상으로 묶였습니다
              </strong>
              <span className="row-meta">
                {group.group_status === "contradicted" ? "상충" : "묶임"}
              </span>
            </div>
            {group.identity_rationale_summary !== null && (
              <p className="row-meta">
                근거 — {group.identity_rationale_summary}
              </p>
            )}
            {note !== undefined && <p className="group-warning">{note}</p>}
          </div>
          <div className="row-actions">
            <button
              type="button"
              className="ghost"
              aria-expanded={!isCollapsed}
              onClick={() => toggleGroup(group.group_id)}
            >
              {isCollapsed ? "펼치기" : "접기"}
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                runAction(`group-confirm:${group.group_id}`, async () => {
                  const result = await approveIdentityGroup(
                    projectId!,
                    group.group_id,
                    group.group_revision,
                  );
                  setOutcome({
                    kind: "approve",
                    groupId: group.group_id,
                    result,
                  });
                })
              }
            >
              그룹 승인
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy !== null}
              onClick={() =>
                runAction(`group-reject:${group.group_id}`, async () => {
                  const result = await rejectIdentityGroup(
                    projectId!,
                    group.group_id,
                  );
                  setOutcome({
                    kind: "reject",
                    groupId: group.group_id,
                    result,
                  });
                })
              }
            >
              그룹 거절
            </button>
          </div>
        </div>

        {!isCollapsed && (
          <ul
            className="review-group-members"
            aria-label="그룹 안 후보 목록"
          >
            {members.map((item) => (
              <li className="review-row" key={item.candidate_id}>
                {candidateSummary(item)}
                {candidateActions(item)}
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  }

  const entries = data === null ? [] : buildEntries(data.items);

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

      {groupOutcomePanel()}

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
              {entries.map((entry) =>
                entry.kind === "group" ? (
                  groupEntry(entry)
                ) : (
                  <li
                    className="resource-row review-row"
                    key={entry.item.candidate_id}
                  >
                    {candidateSummary(entry.item)}
                    {candidateActions(entry.item)}
                  </li>
                ),
              )}
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
