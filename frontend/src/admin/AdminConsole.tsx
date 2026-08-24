import { useEffect, useState } from "react";
import { Link } from "react-router";
import { MemberQuotaSection } from "./MemberQuotaSection";
import {
  ApiError,
  approveAdminSignup,
  createAdminUser,
  deactivateAdminUser,
  describeApiError,
  getAdminObservabilityKpi,
  issueProjectAccessGrant,
  listAdminAuditEvents,
  listAdminProjects,
  listAdminSignupRequests,
  listAdminUsers,
  listProjectAccessLog,
  purgeAdminProject,
  rejectAdminSignup,
  type AccessGrant,
  type AccessLogEntry,
  type AdminObservabilityKpi,
  type AdminAuditEvent,
  type AdminProject,
  type AdminSignupRequest,
  type AdminUser,
} from "../api/client";

type ProjectAccessState = {
  reason: string;
  grant?: AccessGrant;
  entries?: AccessLogEntry[];
  busy?: boolean;
  error?: string;
};

type ProjectPurgeState = {
  open?: boolean;
  reason: string;
  confirmation: string;
  busy?: boolean;
  uncertain?: boolean;
  error?: string;
};

export function AdminConsole() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [kpi, setKpi] = useState<AdminObservabilityKpi | null>(null);
  const [auditEvents, setAuditEvents] = useState<AdminAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [access, setAccess] = useState<Record<string, ProjectAccessState>>({});
  const [purges, setPurges] = useState<Record<string, ProjectPurgeState>>({});
  const [signups, setSignups] = useState<AdminSignupRequest[]>([]);
  const [signupBusy, setSignupBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listAdminUsers(), listAdminProjects(), getAdminObservabilityKpi(),
      listAdminAuditEvents(), listAdminSignupRequests(),
    ])
      .then(([userResult, projectResult, kpiResult, auditResult, signupResult]) => {
        if (cancelled) return;
        setUsers(userResult.users);
        setProjects(projectResult.projects);
        setKpi(kpiResult);
        setAuditEvents(auditResult.events);
        setSignups(signupResult.requests);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const ownerNames = new Map(users.map((user) => [user.id, user.username]));

  async function createUser(event: React.FormEvent) {
    event.preventDefault();
    if (savingUser || username.trim() === "" || password === "") return;
    setSavingUser(true);
    setError(null);
    try {
      const created = await createAdminUser({
        username: username.trim(), password, is_admin: makeAdmin,
      });
      setUsers((current) => [...current, created]);
      setUsername("");
      setPassword("");
      setMakeAdmin(false);
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setSavingUser(false);
    }
  }

  /** 승인·거절 뒤에는 목록을 다시 읽는다(성공·409 모두) — 다른 관리자가 방금
   * 처리했을 수 있어 로컬 배열 조작보다 서버 상태가 정직하다. */
  async function resolveSignup(
    signup: AdminSignupRequest,
    action: "approve" | "reject",
  ) {
    if (signupBusy !== null) return;
    setSignupBusy(signup.id);
    setError(null);
    setNotice(null);
    try {
      const call = action === "approve"
        ? approveAdminSignup
        : rejectAdminSignup;
      await call(signup.id);
      setNotice(
        action === "approve"
          ? `${signup.username} 계정을 승인했습니다.`
          : `${signup.username} 요청을 거절했습니다.`,
      );
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      try {
        const refreshed = await listAdminSignupRequests();
        setSignups(refreshed.requests);
      } catch {
        // 갱신 실패는 본 오류를 덮지 않는다 — 목록은 다음 방문 때 맞춰진다.
      }
      setSignupBusy(null);
    }
  }

  async function deactivate(userId: string) {
    setError(null);
    try {
      const updated = await deactivateAdminUser(userId);
      setUsers((current) => current.map((user) => user.id === userId ? updated : user));
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }

  function updateAccess(projectId: string, patch: Partial<ProjectAccessState>) {
    setAccess((current) => ({
      ...current,
      [projectId]: { ...(current[projectId] ?? { reason: "" }), ...patch },
    }));
  }

  async function issueGrant(projectId: string) {
    const state = access[projectId] ?? { reason: "" };
    if (state.busy || state.reason.trim() === "") return;
    updateAccess(projectId, { busy: true, error: undefined });
    try {
      const grant = await issueProjectAccessGrant(projectId, state.reason.trim());
      updateAccess(projectId, { grant, busy: false });
    } catch (cause) {
      updateAccess(projectId, { busy: false, error: describeApiError(cause) });
    }
  }

  async function loadAccessLog(projectId: string) {
    updateAccess(projectId, { busy: true, error: undefined });
    try {
      const entries = await listProjectAccessLog(projectId);
      updateAccess(projectId, { entries, busy: false });
    } catch (cause) {
      updateAccess(projectId, { busy: false, error: describeApiError(cause) });
    }
  }

  function updatePurge(projectId: string, patch: Partial<ProjectPurgeState>) {
    setPurges((current) => ({
      ...current,
      [projectId]: {
        ...(current[projectId] ?? { reason: "", confirmation: "" }),
        ...patch,
      },
    }));
  }

  async function purge(project: AdminProject) {
    const state = purges[project.id] ?? { reason: "", confirmation: "" };
    if (
      !project.archived || state.busy || state.uncertain
      || state.reason.trim() === "" || state.confirmation !== project.name
    ) return;
    updatePurge(project.id, { busy: true, error: undefined });
    setNotice(null);
    try {
      await purgeAdminProject(project.id, state.reason.trim());
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setPurges((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
      setNotice(`“${project.name}” 프로젝트를 영구 삭제했습니다.`);
      try {
        setAuditEvents((await listAdminAuditEvents()).events);
      } catch {
        // The purge already succeeded. A read-out failure must not turn it into
        // a deletion failure or offer a retry for an irreversible operation.
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 503) {
        updatePurge(project.id, {
          busy: false,
          uncertain: true,
          error: "삭제 상태를 확정할 수 없습니다. 다시 시도하지 말고 purge reconciler로 잔류 데이터를 확인하세요.",
        });
      } else if (cause instanceof ApiError && cause.status === 404) {
        setProjects((current) => current.filter((item) => item.id !== project.id));
        setNotice(`“${project.name}” 프로젝트가 이미 존재하지 않습니다.`);
      } else {
        updatePurge(project.id, { busy: false, error: describeApiError(cause) });
      }
    }
  }

  return (
    <section className="admin-page page-enter">
      <header className="page-heading">
        <p className="eyebrow">운영</p>
        <h1>관리</h1>
        <p>사용자와 프로젝트 메타데이터를 관리하고, 필요한 경우에만 감사되는 읽기 권한을 발급합니다.</p>
      </header>

      {/* header 안에 넣으면 .page-heading > p:last-child 가 소개 문단에 안
          걸린다 — 링크는 header 밖이 정위치다. */}
      <Link className="section-link" to="/">서비스로 이동</Link>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {notice !== null && <p className="status-copy" role="status">{notice}</p>}
      {loading && <p className="status-copy">관리 정보를 불러오는 중…</p>}

      {!loading && (
        <>
          {kpi !== null && (
            <section className="admin-section" aria-labelledby="admin-kpi-heading">
              <h2 id="admin-kpi-heading">전역 관측</h2>
              <dl className="admin-kpi">
                <div><dt>프로젝트</dt><dd>{kpi.projects_considered}</dd></div>
                <div><dt>LLM 호출</dt><dd>{kpi.totals.calls}</dd></div>
                <div><dt>성공</dt><dd>{kpi.totals.success}</dd></div>
                <div><dt>오류</dt><dd>{kpi.totals.provider_error + kpi.totals.parse_error}</dd></div>
              </dl>
            </section>
          )}

          <section className="admin-section" aria-labelledby="admin-users-heading">
            <h2 id="admin-users-heading">사용자</h2>
            <form className="admin-create-form" onSubmit={createUser}>
              <label>새 사용자 아이디<input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
              <label>초기 비밀번호<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
              <label className="admin-checkbox"><input type="checkbox" checked={makeAdmin} onChange={(e) => setMakeAdmin(e.target.checked)} />관리자로 만들기</label>
              <button type="submit" disabled={savingUser || username.trim() === "" || password === ""}>사용자 만들기</button>
            </form>
            <p className="form-hint">초기 비밀번호는 1회용이며, 사용자가 첫 로그인에서 12자 이상으로 바꿉니다.</p>
            <ul className="admin-list">
              {users.map((user) => (
                <li key={user.id}>
                  <div><strong>{user.username}</strong><span>{user.is_admin ? "관리자" : "사용자"} · {user.is_active ? "활성" : "비활성"}</span></div>
                  {user.is_active && <button type="button" onClick={() => void deactivate(user.id)}>비활성화</button>}
                </li>
              ))}
            </ul>
          </section>

          <MemberQuotaSection />

          <section className="admin-section" aria-labelledby="admin-signups-heading">
            <h2 id="admin-signups-heading">가입 요청</h2>
            {signups.length === 0 ? (
              <p className="form-hint">기다리는 가입 요청이 없습니다.</p>
            ) : (
              <ul className="admin-list">
                {signups.map((signup) => (
                  <li key={signup.id}>
                    <div>
                      <strong>{signup.username}</strong>
                      <span>요청 {new Date(signup.requested_at).toLocaleString()}</span>
                    </div>
                    <div className="row-actions">
                      <button
                        type="button"
                        disabled={signupBusy !== null}
                        onClick={() => void resolveSignup(signup, "approve")}
                      >
                        승인
                      </button>
                      <button
                        type="button"
                        disabled={signupBusy !== null}
                        onClick={() => void resolveSignup(signup, "reject")}
                      >
                        거절
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="admin-section" aria-labelledby="admin-projects-heading">
            <h2 id="admin-projects-heading">전체 프로젝트</h2>
            <div className="admin-projects">
              {projects.map((project) => {
                const state = access[project.id] ?? { reason: "" };
                const purgeState = purges[project.id] ?? { reason: "", confirmation: "" };
                const owner = project.owner_id === null
                  ? "소유자 없음"
                  : ownerNames.get(project.owner_id) ?? project.owner_id;
                return (
                  <article key={project.id} className="admin-project-card">
                    <header><div><h3>{project.name}</h3><p>{owner} · {project.archived ? "보관됨" : "사용 중"}</p></div><code>{project.id}</code></header>
                    {project.owner_id === null ? (
                      <p className="form-hint">소유자 없는 프로젝트는 승격으로 열 수 없습니다.</p>
                    ) : (
                      <>
                        <label>접근 사유<input value={state.reason} onChange={(e) => updateAccess(project.id, { reason: e.target.value })} /></label>
                        <div className="row-actions">
                          <button type="button" disabled={state.busy || state.reason.trim() === ""} onClick={() => void issueGrant(project.id)}>1시간 읽기 권한 발급</button>
                          {state.grant && <Link to={`/projects/${project.id}`}>프로젝트 열기</Link>}
                          <button type="button" disabled={state.busy || !state.grant} onClick={() => void loadAccessLog(project.id)}>접근 이력 보기</button>
                        </div>
                        {state.grant && <p className="grant-status">권한 만료: {new Date(state.grant.expires_at).toLocaleString("ko-KR")}</p>}
                        {state.error && <p className="alert" role="alert">{state.error}</p>}
                        {state.entries && (
                          <ul className="access-log">
                            {state.entries.length === 0
                              ? <li>기록된 접근이 없습니다.</li>
                              : state.entries.map((entry, index) => <li key={`${entry.grant_id}-${entry.at}-${index}`}><strong>{entry.method} {entry.path}</strong><span>{entry.reason} · {new Date(entry.at).toLocaleString("ko-KR")}</span></li>)}
                          </ul>
                        )}
                      </>
                    )}
                    {project.archived ? (
                      <section className="admin-danger-zone" aria-label={`${project.name} 영구 삭제`}>
                        {!purgeState.open ? (
                          <button
                            type="button"
                            className="danger-button"
                            onClick={() => updatePurge(project.id, { open: true })}
                          >영구 삭제 준비</button>
                        ) : (
                          <>
                            <h4>영구 삭제</h4>
                            {/* 8.2c N5=A: 종전 문구("전체가 삭제")는 이름 이력이 생긴
                                뒤로 부분적으로 거짓이다. 무엇이 남는지 말하지 않는 경고는
                                관리자가 확인할 수 없으므로, 예외를 문장에 드러낸다. */}
                            <p>원고·기억·감사·색인이 삭제됩니다. 복구할 수 없습니다. 다만 <strong>사용 기록 조회를 위해 프로젝트 이름은 보관됩니다.</strong></p>
                            <label>삭제 사유<input disabled={purgeState.busy || purgeState.uncertain} value={purgeState.reason} onChange={(e) => updatePurge(project.id, { reason: e.target.value })} /></label>
                            <label>확인을 위해 <strong>{project.name}</strong> 입력<input disabled={purgeState.busy || purgeState.uncertain} value={purgeState.confirmation} onChange={(e) => updatePurge(project.id, { confirmation: e.target.value })} /></label>
                            {!purgeState.uncertain && (
                              <button
                                type="button"
                                className="danger-button"
                                disabled={purgeState.busy || purgeState.reason.trim() === "" || purgeState.confirmation !== project.name}
                                onClick={() => void purge(project)}
                              >영구 삭제</button>
                            )}
                            {purgeState.error && <p className="alert" role="alert">{purgeState.error}</p>}
                          </>
                        )}
                      </section>
                    ) : (
                      <p className="form-hint">영구 삭제하려면 사용자가 먼저 프로젝트를 보관해야 합니다.</p>
                    )}
                  </article>
                );
              })}
            </div>
          </section>

          <section className="admin-section" aria-labelledby="admin-audit-heading">
            <h2 id="admin-audit-heading">최근 영구 삭제 기록</h2>
            <ul className="admin-list admin-audit-list">
              {auditEvents.length === 0
                ? <li>기록된 영구 삭제가 없습니다.</li>
                : auditEvents.map((event) => (
                  <li key={event.id}>
                    <div>
                      <strong>{event.target_project_id}</strong>
                      <span>
                        {ownerNames.get(event.admin_user_id) ?? event.admin_user_id}
                        {" · "}{event.outcome === "requested" ? "요청" : event.outcome === "succeeded" ? "완료" : "실패"}
                        {" · "}{new Date(event.at).toLocaleString("ko-KR")}
                      </span>
                      <span>{event.reason}</span>
                    </div>
                  </li>
                ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}
