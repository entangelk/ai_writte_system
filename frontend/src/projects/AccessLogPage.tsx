import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  describeApiError,
  listProjectAccessLog,
  type AccessLogEntry,
} from "../api/client";

export function AccessLogPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [entries, setEntries] = useState<AccessLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      return;
    }
    let active = true;
    listProjectAccessLog(projectId)
      .then((result) => {
        if (active) setEntries(result);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      });
    return () => { active = false; };
  }, [projectId]);

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>← 원고 목록</Link>
      <header className="page-heading">
        <p className="eyebrow">감사</p>
        <h1>관리자 접근 이력</h1>
        <p>관리자가 한시적 읽기 권한으로 열어 본 요청과 발급 사유를 최신순으로 확인합니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {entries === null && error === null && <p className="status-copy">접근 이력을 불러오는 중…</p>}
      {entries !== null && entries.length === 0 && (
        <div className="empty-state"><p>기록된 관리자 접근이 없습니다.</p></div>
      )}
      {entries !== null && entries.length > 0 && (
        <ul className="access-log access-log-page">
          {entries.map((entry, index) => (
            <li key={`${entry.grant_id}-${entry.at}-${index}`}>
              <strong>{entry.method} {entry.path}</strong>
              <span>{entry.reason} · 관리자 {entry.admin_user_id} · {new Date(entry.at).toLocaleString("ko-KR")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
