import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  createAdminUser,
  deactivateAdminUser,
  describeApiError,
  getAdminObservabilityKpi,
  issueProjectAccessGrant,
  listAdminProjects,
  listAdminUsers,
  listProjectAccessLog,
  type AccessGrant,
  type AccessLogEntry,
  type AdminObservabilityKpi,
  type AdminProject,
  type AdminUser,
} from "../api/client";

type ProjectAccessState = {
  reason: string;
  grant?: AccessGrant;
  entries?: AccessLogEntry[];
  busy?: boolean;
  error?: string;
};

export function AdminConsole() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [kpi, setKpi] = useState<AdminObservabilityKpi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [access, setAccess] = useState<Record<string, ProjectAccessState>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAdminUsers(), listAdminProjects(), getAdminObservabilityKpi()])
      .then(([userResult, projectResult, kpiResult]) => {
        if (cancelled) return;
        setUsers(userResult.users);
        setProjects(projectResult.projects);
        setKpi(kpiResult);
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

  return (
    <section className="admin-page page-enter">
      <header className="page-heading">
        <p className="eyebrow">운영</p>
        <h1>관리</h1>
        <p>사용자와 프로젝트 메타데이터를 관리하고, 필요한 경우에만 감사되는 읽기 권한을 발급합니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}
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

          <section className="admin-section" aria-labelledby="admin-projects-heading">
            <h2 id="admin-projects-heading">전체 프로젝트</h2>
            <div className="admin-projects">
              {projects.map((project) => {
                const state = access[project.id] ?? { reason: "" };
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
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
