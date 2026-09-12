import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { AdminProjectCard } from "./AdminProjectCard";
import { adminUserStateLabel, adminWithdrawalLabel } from "./userStatus";
import {
  deactivateAdminUser,
  describeApiError,
  listAdminProjects,
  listAdminUsers,
  reconcileAdminAccount,
  surveyAdminAccountReconcile,
  type AdminProject,
  type AdminAccountReconcileSurvey,
  type AdminAccountReconcileResult,
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
 *
 * 잔여 정리(계정 탈퇴 Slice 4b, 2026-09-12): 파기 데몬이 실패한 계정
 * (`purge_started_at` 스탬프가 찍힌 채 남은 행)의 수습 표면. 조사 → 사용자명
 * 확인 → 실행의 두 단계는 오너 결정 ②ⓐ 그대로고, 프로젝트 파기 UI 의
 * 확인 패턴(사유 + 이름 입력)을 계정 축으로 옮긴 것이다.
 */

type ReconcileState = {
  survey: AdminAccountReconcileSurvey | null;
  result: AdminAccountReconcileResult | null;
  reason: string;
  confirmation: string;
  busy: boolean;
  error: string | null;
};

const RECONCILE_INITIAL: ReconcileState = {
  survey: null, result: null, reason: "", confirmation: "", busy: false,
  error: null,
};

export function AdminUserDetail() {
  const { userId } = useParams<{ userId: string }>();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [reconcile, setReconcile] = useState<ReconcileState>(RECONCILE_INITIAL);

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

  // 대상이 바뀌면 정리 상태도 초기화 — 조사 결과는 계정마다 다른 사실이다.
  useEffect(() => {
    setReconcile(RECONCILE_INITIAL);
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

  async function surveyResidue() {
    if (user === null || reconcile.busy) return;
    setReconcile((current) => ({ ...current, busy: true, error: null }));
    try {
      const survey = await surveyAdminAccountReconcile(user.id);
      setReconcile((current) => ({ ...current, survey, busy: false }));
    } catch (cause) {
      setReconcile((current) => ({
        ...current, busy: false, error: describeApiError(cause),
      }));
    }
  }

  async function executeReconcile() {
    if (
      user === null || reconcile.busy || reconcile.result !== null
      || reconcile.reason.trim() === ""
      || reconcile.confirmation !== user.username
    ) return;
    setReconcile((current) => ({ ...current, busy: true, error: null }));
    try {
      const result = await reconcileAdminAccount(user.id, {
        reason: reconcile.reason.trim(),
      });
      setReconcile((current) => ({ ...current, result, busy: false }));
    } catch (cause) {
      setReconcile((current) => ({
        ...current, busy: false, error: describeApiError(cause),
      }));
    }
  }

  const withdrawalLabel = user !== null ? adminWithdrawalLabel(user) : "";

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
              {withdrawalLabel !== "" && (
                <div><dt>탈퇴</dt><dd>{withdrawalLabel}</dd></div>
              )}
              <div><dt>프로젝트</dt><dd>{projects.length}</dd></div>
            </dl>
            {user.is_active && (
              <div className="row-actions admin-user-account-actions">
                <button type="button" onClick={() => void deactivate()}>비활성화</button>
              </div>
            )}
          </section>

          {user.purge_started_at !== null && (
            <section
              className="admin-section admin-danger-zone"
              aria-labelledby="admin-user-reconcile-heading"
            >
              <h2 id="admin-user-reconcile-heading">잔여 정리</h2>
              <p>
                이 계정은 파기가 시작된 뒤 중단되었습니다(부분 파기). 조사로 무엇이
                남았는지 먼저 보고, 정리를 실행하면 남은 데이터를 지우고 계정 행을
                마무리합니다. 복구할 수 없습니다.
              </p>
              {!reconcile.survey && (
                <div className="row-actions">
                  <button
                    type="button"
                    className="danger-button"
                    disabled={reconcile.busy}
                    onClick={() => void surveyResidue()}
                  >{reconcile.busy ? "조사 중…" : "잔여 조사"}</button>
                </div>
              )}
              {reconcile.survey && reconcile.result === null && (
                <>
                  <h3>조사 결과</h3>
                  <ul className="access-log">
                    {reconcile.survey.leftover_projects.length === 0
                      ? <li>남은 프로젝트가 없습니다.</li>
                      : reconcile.survey.leftover_projects.map((projectId) => (
                        <li key={projectId}>
                          <strong>{projectId}</strong>
                          <span>프로젝트가 남아 있어 계정 행은 유지됩니다</span>
                        </li>
                      ))}
                    <li>
                      {reconcile.survey.has_username_tombstone
                        ? <span>사용자명 묘비가 있습니다 — 정리가 끝나면 계정 행이 삭제됩니다.</span>
                        : <span><strong>사용자명 묘비가 없습니다</strong> — 원장이 이름 없이 id 로만 답하지 않도록 계정 행을 유지합니다.</span>}
                    </li>
                  </ul>
                  <label>정리 사유<input
                    disabled={reconcile.busy}
                    value={reconcile.reason}
                    onChange={(e) => setReconcile((current) => ({ ...current, reason: e.target.value }))}
                  /></label>
                  <label>확인을 위해 <strong>{user.username}</strong> 입력<input
                    disabled={reconcile.busy}
                    value={reconcile.confirmation}
                    onChange={(e) => setReconcile((current) => ({ ...current, confirmation: e.target.value }))}
                  /></label>
                  <button
                    type="button"
                    className="danger-button"
                    disabled={
                      reconcile.busy || reconcile.reason.trim() === ""
                      || reconcile.confirmation !== user.username
                    }
                    onClick={() => void executeReconcile()}
                  >{reconcile.busy ? "정리 중…" : "잔여 정리 실행"}</button>
                </>
              )}
              {reconcile.result !== null && (
                <>
                  <h3>정리 결과</h3>
                  <ul className="access-log">
                    {Object.entries(reconcile.result.swept).length === 0
                      ? <li>지운 계정 축 데이터가 없습니다.</li>
                      : Object.entries(reconcile.result.swept).map(([name, count]) => (
                        <li key={name}><strong>{name}</strong><span>{count}건 삭제</span></li>
                      ))}
                    {reconcile.result.leftover_projects.length > 0 && (
                      <li><strong>프로젝트 {reconcile.result.leftover_projects.length}개</strong><span>남아 있어 계정 행을 유지했습니다</span></li>
                    )}
                    <li>
                      {reconcile.result.removed_user_row
                        ? <span>계정 행을 삭제했습니다 — 이 사용자의 상세는 더 이상 없습니다.</span>
                        : <span>계정 행을 유지했습니다(남은 조건 참조).</span>}
                    </li>
                  </ul>
                  {reconcile.result.removed_user_row && (
                    <Link className="inline-navigation-link" to="/admin">사용자 목록으로</Link>
                  )}
                </>
              )}
              {reconcile.error && (
                <p className="alert" role="alert">{reconcile.error}</p>
              )}
            </section>
          )}

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
                      setNotice(`"${purged.name}" 프로젝트를 영구 삭제했습니다.`);
                    }}
                    onArchived={(archived) => {
                      setProjects((current) =>
                        current.map((item) =>
                          item.id === archived.id ? archived : item));
                      setNotice(`"${archived.name}" 프로젝트를 보관했습니다.`);
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
