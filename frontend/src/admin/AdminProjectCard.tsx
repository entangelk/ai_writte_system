import { useState } from "react";
import { Link } from "react-router";
import {
  ApiError,
  describeApiError,
  issueProjectAccessGrant,
  listProjectAccessLog,
  purgeAdminProject,
  type AccessGrant,
  type AccessLogEntry,
  type AdminProject,
} from "../api/client";

type AccessState = {
  reason: string;
  grant?: AccessGrant;
  entries?: AccessLogEntry[];
  busy?: boolean;
  error?: string;
};

type PurgeState = {
  open?: boolean;
  reason: string;
  confirmation: string;
  busy?: boolean;
  uncertain?: boolean;
  error?: string;
};

/**
 * 관리자가 한 프로젝트에 하는 일 전부 (승격 발급 · 접근 이력 · 영구 삭제).
 *
 * **두 화면이 같은 카드를 쓴다**(오너 2026-08-27): 사용자별 상세 페이지의
 * 프로젝트 목록과, 관리 메인의 "소유자 없는 프로젝트". 종전에는 관리 메인 한
 * 곳에 전 프로젝트가 평평하게 쌓여 계정이 늘수록 화면이 늘어졌다 — 그 목록을
 * 사람 단위로 쪼개면서 카드가 두 자리에 서게 됐다.
 */
export function AdminProjectCard({
  project,
  owner,
  onPurged,
}: {
  project: AdminProject;
  owner: string;
  onPurged: (project: AdminProject) => void;
}) {
  const [access, setAccess] = useState<AccessState>({ reason: "" });
  const [purgeState, setPurgeState] = useState<PurgeState>({
    reason: "", confirmation: "",
  });

  async function issueGrant() {
    if (access.busy || access.reason.trim() === "") return;
    setAccess((current) => ({ ...current, busy: true, error: undefined }));
    try {
      const grant = await issueProjectAccessGrant(project.id, access.reason.trim());
      setAccess((current) => ({ ...current, grant, busy: false }));
    } catch (cause) {
      setAccess((current) => ({
        ...current, busy: false, error: describeApiError(cause),
      }));
    }
  }

  async function loadAccessLog() {
    setAccess((current) => ({ ...current, busy: true, error: undefined }));
    try {
      const entries = await listProjectAccessLog(project.id);
      setAccess((current) => ({ ...current, entries, busy: false }));
    } catch (cause) {
      setAccess((current) => ({
        ...current, busy: false, error: describeApiError(cause),
      }));
    }
  }

  async function purge() {
    if (
      !project.archived || purgeState.busy || purgeState.uncertain
      || purgeState.reason.trim() === "" || purgeState.confirmation !== project.name
    ) return;
    setPurgeState((current) => ({ ...current, busy: true, error: undefined }));
    try {
      await purgeAdminProject(project.id, purgeState.reason.trim());
      onPurged(project);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 503) {
        setPurgeState((current) => ({
          ...current,
          busy: false,
          uncertain: true,
          error: "삭제 상태를 확정할 수 없습니다. 다시 시도하지 말고 purge reconciler로 잔류 데이터를 확인하세요.",
        }));
      } else if (cause instanceof ApiError && cause.status === 404) {
        onPurged(project);
      } else {
        setPurgeState((current) => ({
          ...current, busy: false, error: describeApiError(cause),
        }));
      }
    }
  }

  return (
    <article className="admin-project-card">
      <header>
        <div>
          <h3>{project.name}</h3>
          <p>{owner} · {project.archived ? "보관됨" : "사용 중"}</p>
        </div>
        <code>{project.id}</code>
      </header>
      {project.owner_id === null ? (
        <p className="form-hint">소유자 없는 프로젝트는 승격으로 열 수 없습니다.</p>
      ) : (
        <>
          <label>접근 사유<input value={access.reason} onChange={(e) => setAccess((current) => ({ ...current, reason: e.target.value }))} /></label>
          <div className="row-actions">
            <button type="button" disabled={access.busy || access.reason.trim() === ""} onClick={() => void issueGrant()}>1시간 읽기 권한 발급</button>
            {access.grant && <Link to={`/projects/${project.id}`}>프로젝트 열기</Link>}
            <button type="button" disabled={access.busy || !access.grant} onClick={() => void loadAccessLog()}>접근 이력 보기</button>
          </div>
          {access.grant && <p className="grant-status">권한 만료: {new Date(access.grant.expires_at).toLocaleString("ko-KR")}</p>}
          {access.error && <p className="alert" role="alert">{access.error}</p>}
          {access.entries && (
            <ul className="access-log">
              {access.entries.length === 0
                ? <li>기록된 접근이 없습니다.</li>
                : access.entries.map((entry, index) => <li key={`${entry.grant_id}-${entry.at}-${index}`}><strong>{entry.method} {entry.path}</strong><span>{entry.reason} · {new Date(entry.at).toLocaleString("ko-KR")}</span></li>)}
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
              onClick={() => setPurgeState((current) => ({ ...current, open: true }))}
            >영구 삭제 준비</button>
          ) : (
            <>
              <h4>영구 삭제</h4>
              {/* 8.2c N5=A: 종전 문구("전체가 삭제")는 이름 이력이 생긴
                  뒤로 부분적으로 거짓이다. 무엇이 남는지 말하지 않는 경고는
                  관리자가 확인할 수 없으므로, 예외를 문장에 드러낸다. */}
              <p>원고·기억·감사·색인이 삭제됩니다. 복구할 수 없습니다. 다만 <strong>사용 기록 조회를 위해 프로젝트 이름은 보관됩니다.</strong></p>
              <label>삭제 사유<input disabled={purgeState.busy || purgeState.uncertain} value={purgeState.reason} onChange={(e) => setPurgeState((current) => ({ ...current, reason: e.target.value }))} /></label>
              <label>확인을 위해 <strong>{project.name}</strong> 입력<input disabled={purgeState.busy || purgeState.uncertain} value={purgeState.confirmation} onChange={(e) => setPurgeState((current) => ({ ...current, confirmation: e.target.value }))} /></label>
              {!purgeState.uncertain && (
                <button
                  type="button"
                  className="danger-button"
                  disabled={purgeState.busy || purgeState.reason.trim() === "" || purgeState.confirmation !== project.name}
                  onClick={() => void purge()}
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
}
