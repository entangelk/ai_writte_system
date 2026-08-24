import { useEffect, useState } from "react";
import {
  activateAdminQuota,
  changeAdminQuotaLimits,
  describeApiError,
  getAdminQuotaPolicy,
  listAdminQuotaPolicies,
  suspendAdminQuota,
  type AdminQuotaPolicy,
  type AdminQuotaPolicyDetail,
} from "../api/client";

type QuotaPanelState = {
  open?: boolean;
  reason: string;
  dailyText: string;
  weeklyText: string;
  dailyUnlimited: boolean;
  weeklyUnlimited: boolean;
  detail?: AdminQuotaPolicyDetail;
  busy?: boolean;
  error?: string;
};

/** 창 한도 표기 — null(무제한)은 "무제한"으로 읽힌다(체크박스와 같은 어휘). */
function describeLimit(limit: number | null): string {
  return limit === null ? "무제한" : String(limit);
}

function quotaStatusLine(policy: AdminQuotaPolicy): string {
  if (policy.status === "suspended") return "정지됨";
  if (policy.unlimited) return "무제한";
  return `남은 사용 ${policy.remaining}회`;
}

function quotaUsageLine(policy: AdminQuotaPolicy): string {
  return `일 ${policy.daily.used}/${describeLimit(policy.daily.limit)}`
    + ` · 주 ${policy.weekly.used}/${describeLimit(policy.weekly.limit)}`;
}

/** 제출 가능한 값인가 — 빈 문자열·해석 불가는 undefined 로 제출을 막는다.
 *  Number("") === 0 이라 빈 칸을 그냥 파싱하면 "0 한도"가 나가고,
 *  NaN 은 JSON.stringify 에서 null(=무제한)로 직렬화되므로 둘 다 여기서 걸른다.
 *  소수는 통과시킨다 — 타입 오류(StrictInt 422)는 서버의 것이게 한다. */
function parseLimitText(text: string): number | undefined {
  if (text.trim() === "") return undefined;
  const value = Number(text);
  return Number.isFinite(value) ? value : undefined;
}

export function MemberQuotaSection() {
  const [rows, setRows] = useState<AdminQuotaPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [panels, setPanels] = useState<Record<string, QuotaPanelState>>({});

  useEffect(() => {
    let cancelled = false;
    listAdminQuotaPolicies()
      .then((result) => {
        if (!cancelled) setRows(result.policies);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  function updatePanel(userId: string, patch: Partial<QuotaPanelState>) {
    setPanels((current) => ({
      ...current,
      [userId]: { ...(current[userId] ?? emptyPanel()), ...patch },
    }));
  }

  /** 상세 응답으로 행과 패널을 함께 맞춘다 — 상세는 목록 필드 전부를 포함한다.
   *  실패 뒤 재독기(keepError)에서도 쓴다: 감사 쓰기 실패(H2)는 변경이 이미
   *  적용된 채 요청만 죽었을 수 있어, 화면은 서버 상태를 다시 믿는다. */
  function applyDetail(detail: AdminQuotaPolicyDetail, keepError = false) {
    setRows((current) => current.map(
      (row) => (row.user_id === detail.user_id ? detail : row),
    ));
    updatePanel(detail.user_id, {
      detail,
      dailyText: detail.daily.limit === null ? "" : String(detail.daily.limit),
      weeklyText: detail.weekly.limit === null ? "" : String(detail.weekly.limit),
      dailyUnlimited: detail.daily.limit === null,
      weeklyUnlimited: detail.weekly.limit === null,
      ...(keepError ? {} : { error: undefined }),
    });
  }

  async function refreshAfterFailure(userId: string) {
    try {
      applyDetail(await getAdminQuotaPolicy(userId), true);
    } catch {
      // 본 오류를 덮지 않는다 — 행은 다음 방문 때 맞춰진다.
    }
  }

  function togglePanel(row: AdminQuotaPolicy) {
    if (panels[row.user_id]?.open) {
      updatePanel(row.user_id, { open: false });
      return;
    }
    // 프리필은 상세 응답으로만 한다 — 목록은 다른 관리자의 변경 뒤 낡았을 수
    // 있고, 폼은 상세가 오기 전에 입력을 받지 않는다(덮어쓰기 사고 방지).
    updatePanel(row.user_id, { ...emptyPanel(), open: true });
    getAdminQuotaPolicy(row.user_id)
      .then((detail) => { applyDetail(detail); })
      .catch((cause: unknown) => {
        updatePanel(row.user_id, { error: describeApiError(cause) });
      });
  }

  async function changeLimits(userId: string) {
    const panel = panels[userId];
    if (panel?.detail === undefined || panel.busy) return;
    if (panel.reason.trim() === "") return;
    const daily: number | null | undefined = panel.dailyUnlimited
      ? null : parseLimitText(panel.dailyText);
    const weekly: number | null | undefined = panel.weeklyUnlimited
      ? null : parseLimitText(panel.weeklyText);
    if (daily === undefined || weekly === undefined) return;
    updatePanel(userId, { busy: true, error: undefined });
    try {
      // 두 창을 항상 같이 보낸다 — 서버는 QuotaLimits 전체를 대체하므로 한 창만
      // 실으면 나머지 창이 null(무제한)이 된다.
      applyDetail(await changeAdminQuotaLimits(userId, {
        daily_limit: daily,
        weekly_limit: weekly,
        reason: panel.reason,
      }));
    } catch (cause: unknown) {
      updatePanel(userId, { error: describeApiError(cause) });
      await refreshAfterFailure(userId);
    } finally {
      updatePanel(userId, { busy: false });
    }
  }

  async function setSuspended(userId: string, suspended: boolean) {
    const panel = panels[userId];
    if (panel === undefined || panel.busy) return;
    if (panel.reason.trim() === "") return;
    updatePanel(userId, { busy: true, error: undefined });
    try {
      const detail = suspended
        ? await suspendAdminQuota(userId, panel.reason)
        : await activateAdminQuota(userId, panel.reason);
      applyDetail(detail);
    } catch (cause: unknown) {
      updatePanel(userId, { error: describeApiError(cause) });
      await refreshAfterFailure(userId);
    } finally {
      updatePanel(userId, { busy: false });
    }
  }

  return (
    <section className="admin-section" aria-labelledby="admin-quota-heading">
      <h2 id="admin-quota-heading">회원 사용량 한도</h2>
      {error !== null && <p className="alert" role="alert">{error}</p>}
      {loading && <p className="status-copy">회원 사용량을 불러오는 중…</p>}
      {!loading && rows.length === 0 && (
        <p className="form-hint">활성 회원이 없습니다.</p>
      )}
      {!loading && rows.length > 0 && (
        <ul className="admin-list">
          {rows.map((row) => {
            const panel = panels[row.user_id];
            const detail = panel?.detail;
            const limitsInvalid = panel !== undefined
              && (!panel.dailyUnlimited && parseLimitText(panel.dailyText) === undefined
                || !panel.weeklyUnlimited && parseLimitText(panel.weeklyText) === undefined
                || (panel.dailyUnlimited && panel.weeklyUnlimited));
            return (
              <li key={row.user_id}>
                <div>
                  <strong>{row.username}</strong>
                  <span>{quotaStatusLine(row)}</span>
                  <span>{quotaUsageLine(row)}</span>
                  {row.has_pending && <span>변경 예약됨</span>}
                  {panel?.open && (
                    <div className="admin-quota-detail">
                      {detail === undefined && panel.error === undefined && (
                        <p className="status-copy">정책을 불러오는 중…</p>
                      )}
                      {detail !== undefined && (
                        <>
                          {detail.pending !== null && (
                            <p className="form-hint">
                              축소 예약: 일 {describeLimit(detail.pending.daily_limit)}
                              {" · 주 "}
                              {describeLimit(detail.pending.weekly_limit)}
                              {" · "}
                              {new Date(detail.pending.effective_at).toLocaleString("ko-KR")}
                              발효
                            </p>
                          )}
                          {detail.stored_daily_limit === null
                            && detail.stored_weekly_limit === null && (
                            <p className="form-hint">
                              저장된 정책 없음 — 기본 한도로 운영 중입니다.
                            </p>
                          )}
                          <label>일일 한도
                            <input
                              value={panel.dailyText}
                              disabled={panel.dailyUnlimited || panel.busy}
                              onChange={(e) =>
                                updatePanel(row.user_id, { dailyText: e.target.value })}
                            />
                          </label>
                          <label className="admin-checkbox">
                            <input
                              type="checkbox"
                              checked={panel.dailyUnlimited}
                              disabled={panel.busy}
                              onChange={(e) =>
                                updatePanel(row.user_id, { dailyUnlimited: e.target.checked })}
                            />일일 무제한
                          </label>
                          <label>주간 한도
                            <input
                              value={panel.weeklyText}
                              disabled={panel.weeklyUnlimited || panel.busy}
                              onChange={(e) =>
                                updatePanel(row.user_id, { weeklyText: e.target.value })}
                            />
                          </label>
                          <label className="admin-checkbox">
                            <input
                              type="checkbox"
                              checked={panel.weeklyUnlimited}
                              disabled={panel.busy}
                              onChange={(e) =>
                                updatePanel(row.user_id, { weeklyUnlimited: e.target.checked })}
                            />주간 무제한
                          </label>
                          <label>사유
                            <input
                              value={panel.reason}
                              disabled={panel.busy}
                              onChange={(e) =>
                                updatePanel(row.user_id, { reason: e.target.value })}
                            />
                          </label>
                          {limitsInvalid && (
                            <p className="form-hint">
                              창마다 숫자 한도를 하나 이상 입력해야 합니다.
                            </p>
                          )}
                          <p className="form-hint">
                            한도를 늘리면 즉시, 줄이면 다음 창 경계에 반영됩니다.
                          </p>
                          {panel.error !== undefined && (
                            <p className="alert" role="alert">{panel.error}</p>
                          )}
                          <div>
                            <button
                              type="button"
                              disabled={panel.busy || panel.reason.trim() === ""
                                || limitsInvalid}
                              onClick={() => void changeLimits(row.user_id)}
                            >한도 변경</button>
                            <button
                              type="button"
                              disabled={panel.busy || panel.reason.trim() === ""}
                              onClick={() =>
                                void setSuspended(row.user_id, row.status !== "suspended")}
                            >
                              {row.status === "suspended" ? "정지 해제" : "정지"}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
                <button type="button" onClick={() => togglePanel(row)}>
                  한도·정지 관리
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function emptyPanel(): QuotaPanelState {
  return {
    reason: "",
    dailyText: "",
    weeklyText: "",
    dailyUnlimited: false,
    weeklyUnlimited: false,
  };
}
