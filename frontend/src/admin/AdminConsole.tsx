import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { MemberQuotaSection } from "./MemberQuotaSection";
import { AdminProjectCard } from "./AdminProjectCard";
import { adminUserStateLabel } from "./userStatus";
import {
  approveAdminSignup,
  createAdminUser,
  deactivateAdminUser,
  describeApiError,
  getAdminObservabilityKpi,
  listAdminAuditEvents,
  listAdminProjects,
  listAdminSignupRequests,
  listAdminUsers,
  rejectAdminSignup,
  type AdminObservabilityKpi,
  type AdminAuditEvent,
  type AdminProject,
  type AdminSignupRequest,
  type AdminUser,
} from "../api/client";

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
  const [userQuery, setUserQuery] = useState("");
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

  // 소유자 있는 프로젝트는 사용자 상세(`/admin/users/:id`)가 맡는다 — 여기 남는
  // 것은 **거기로 갈 수 없는 것**뿐이다(오너 2026-08-27). 보통 0건이라 화면을
  // 늘리지 않고, 생기면 그 자체로 이상 신호다.
  const orphanProjects = projects.filter((project) => project.owner_id === null);

  const projectCount = useMemo(() => {
    const counts = new Map<string, number>();
    for (const project of projects) {
      if (project.owner_id === null) continue;
      counts.set(project.owner_id, (counts.get(project.owner_id) ?? 0) + 1);
    }
    return counts;
  }, [projects]);

  const visibleUsers = useMemo(() => {
    const needle = userQuery.trim().toLowerCase();
    if (needle === "") return users;
    return users.filter((user) => user.username.toLowerCase().includes(needle));
  }, [users, userQuery]);

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
   * 처리했을 수 있어 로컬 배열 조작보다 서버 상태가 정직하다. 사용자 목록도
   * 함께 읽는다: 승인은 그 행의 상태를 대기 → 활성으로 바꾼다. */
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
        const [refreshed, refreshedUsers] = await Promise.all([
          listAdminSignupRequests(), listAdminUsers(),
        ]);
        setSignups(refreshed.requests);
        setUsers(refreshedUsers.users);
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

  return (
    <section className="admin-page page-enter">
      <header className="page-heading">
        <p className="eyebrow">운영</p>
        <h1>관리</h1>
        <p>사용자와 프로젝트 메타데이터를 관리하고, 필요한 경우에만 감사되는 읽기 권한을 발급합니다.</p>
      </header>

      {/* header 안에 넣으면 .page-heading > p:last-child 가 소개 문단에 안
          걸린다 — 링크는 header 밖이 정위치다. 관리자도 글을 쓰는 사람이라
          작업장으로 가는 출구는 눈에 띄어야 한다(오너 2026-08-27). */}
      <Link className="section-link primary-link" to="/">작업장으로 이동 →</Link>

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
            <label className="admin-search">
              사용자 검색
              <input
                type="search"
                value={userQuery}
                placeholder="아이디"
                onChange={(event) => setUserQuery(event.target.value)}
              />
            </label>
            {visibleUsers.length === 0 ? (
              <p className="form-hint">검색과 일치하는 사용자가 없습니다.</p>
            ) : (
              <ul className="admin-list">
                {visibleUsers.map((user) => (
                  <li key={user.id}>
                    <div>
                      <Link
                        className="admin-user-detail-link"
                        to={`/admin/users/${user.id}`}
                        aria-label={`${user.username} 상세 보기 →`}
                      >
                        <strong>{user.username}</strong>
                        <span>상세 보기 →</span>
                      </Link>
                      <span>
                        {user.is_admin ? "관리자" : "사용자"}
                        {" · "}{adminUserStateLabel(user)}
                        {" · 프로젝트 "}{projectCount.get(user.id) ?? 0}개
                      </span>
                    </div>
                    <div className="row-actions">
                      {user.is_active && <button type="button" onClick={() => void deactivate(user.id)}>비활성화</button>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
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

          <section className="admin-section" aria-labelledby="admin-orphans-heading">
            <h2 id="admin-orphans-heading">소유자 없는 프로젝트</h2>
            {orphanProjects.length === 0 ? (
              <p className="form-hint">
                소유자 없는 프로젝트가 없습니다. 프로젝트는 각 사용자 상세에서 관리합니다.
              </p>
            ) : (
              <div className="admin-projects">
                {orphanProjects.map((project) => (
                  <AdminProjectCard
                    key={project.id}
                    project={project}
                    owner="소유자 없음"
                    onPurged={(purged) => {
                      setProjects((current) =>
                        current.filter((item) => item.id !== purged.id));
                      setNotice(`“${purged.name}” 프로젝트를 영구 삭제했습니다.`);
                      void listAdminAuditEvents()
                        .then((result) => setAuditEvents(result.events))
                        .catch(() => {
                          // 삭제는 이미 성공했다. 읽기 실패를 삭제 실패로
                          // 바꾸거나 되돌릴 수 없는 작업에 재시도를 권하면 안 된다.
                        });
                    }}
                  />
                ))}
              </div>
            )}
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
