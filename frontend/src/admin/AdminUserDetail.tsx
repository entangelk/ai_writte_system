import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { AdminProjectCard } from "./AdminProjectCard";
import { adminUserStateLabel } from "./userStatus";
import {
  deactivateAdminUser,
  describeApiError,
  listAdminProjects,
  listAdminUsers,
  type AdminProject,
  type AdminUser,
} from "../api/client";

/**
 * 사용자 한 명의 관리 상세 `/admin/users/:userId` (오너 2026-08-27).
 *
 * **전 프로젝트 목록을 사람 단위로 쪼갠 자리다.** 관리 메인에 전 프로젝트가
 * 평평하게 쌓이면 계정이 늘수록 화면이 한없이 늘어진다 — 프로젝트 관리는 그
 * 프로젝트를 가진 사람 아래에서 한다.
 *
 * 목록 두 개(`/admin/users`·`/admin/projects`)를 그대로 읽고 여기서 좁힌다.
 * 사용자별 프로젝트 조회 operation 을 새로 파지 않는 것은 의도다 — 계약을
 * 늘리지 않고 화면만 바꾸는 슬라이스다.
 */
export function AdminUserDetail() {
  const { userId } = useParams<{ userId: string }>();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAdminUsers(), listAdminProjects()])
      .then(([userResult, projectResult]) => {
        if (cancelled) return;
        setUser(userResult.users.find((item) => item.id === userId) ?? null);
        setProjects(
          projectResult.projects.filter((item) => item.owner_id === userId),
        );
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [userId]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") return projects;
    return projects.filter((project) =>
      project.name.toLowerCase().includes(needle)
      || project.id.toLowerCase().includes(needle));
  }, [projects, query]);

  async function deactivate() {
    if (user === null) return;
    setError(null);
    try {
      setUser(await deactivateAdminUser(user.id));
      setNotice(`${user.username} 계정을 비활성화했습니다.`);
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }

  return (
    <section className="admin-page admin-user-detail page-enter">
      <Link className="back-link" to="/admin">← 관리로 돌아가기</Link>

      <header className="page-heading">
        <p className="eyebrow">사용자 상세</p>
        <h1>{user?.username ?? "사용자"}</h1>
        <p>이 사용자의 계정 상태와 프로젝트를 관리합니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {notice !== null && <p className="status-copy" role="status">{notice}</p>}
      {loading && <p className="status-copy">사용자 정보를 불러오는 중…</p>}

      {!loading && user === null && (
        <div className="empty-state"><p>그런 사용자가 없습니다.</p></div>
      )}

      {user !== null && (
        <>
          <section className="admin-section" aria-labelledby="admin-user-account">
            <h2 id="admin-user-account">계정</h2>
            <dl className="admin-kpi">
              <div><dt>아이디</dt><dd>{user.username}</dd></div>
              <div><dt>권한</dt><dd>{user.is_admin ? "관리자" : "사용자"}</dd></div>
              <div><dt>상태</dt><dd>{adminUserStateLabel(user)}</dd></div>
              <div><dt>프로젝트</dt><dd>{projects.length}</dd></div>
            </dl>
            {user.is_active && (
              <div className="row-actions admin-user-account-actions">
                <button type="button" onClick={() => void deactivate()}>비활성화</button>
              </div>
            )}
          </section>

          <section className="admin-section" aria-labelledby="admin-user-projects">
            <h2 id="admin-user-projects">프로젝트</h2>
            <label className="admin-search">
              프로젝트 검색
              <input
                type="search"
                value={query}
                placeholder="제목 또는 id"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            {projects.length === 0 ? (
              <p className="form-hint">이 사용자가 가진 프로젝트가 없습니다.</p>
            ) : visible.length === 0 ? (
              <p className="form-hint">검색과 일치하는 프로젝트가 없습니다.</p>
            ) : (
              <div className="admin-projects admin-user-project-list">
                {visible.map((project) => (
                  <AdminProjectCard
                    key={project.id}
                    project={project}
                    owner={user.username}
                    onPurged={(purged) => {
                      setProjects((current) =>
                        current.filter((item) => item.id !== purged.id));
                      setNotice(`“${purged.name}” 프로젝트를 영구 삭제했습니다.`);
                    }}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
