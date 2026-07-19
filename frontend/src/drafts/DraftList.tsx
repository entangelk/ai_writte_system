import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  createDraft,
  describeApiError,
  getProject,
  listDrafts,
  type Draft,
  type Project,
} from "../api/client";

export function DraftList() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadDrafts = useCallback(async () => {
    if (projectId === undefined) {
      return;
    }
    const response = await listDrafts(projectId);
    setDrafts(response.drafts);
  }, [projectId]);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    void Promise.all([getProject(projectId), listDrafts(projectId)])
      .then(([nextProject, response]) => {
        if (!active) {
          return;
        }
        setProject(nextProject);
        setDrafts(response.drafts);
        setError(null);
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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (projectId === undefined || trimmed === "" || saving || project?.archived) {
      return;
    }
    setSaving(true);
    try {
      await createDraft(projectId, { title: trimmed });
      setTitle("");
      setError(null);
      await loadDrafts();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to="/">← 프로젝트로 돌아가기</Link>

      <header className="page-heading project-heading">
        <p className="eyebrow">원고 작업 공간</p>
        <h1>{project?.name ?? "프로젝트"}</h1>
        <p>장면이나 장을 원고 단위로 나누어 관리합니다.</p>
        {projectId !== undefined && (
          <div className="section-links">
            <Link className="section-link" to={`/projects/${projectId}/overview`}>
              작품 정보·개요 →
            </Link>
            <Link className="section-link" to={`/projects/${projectId}/review`}>
              검토함 →
            </Link>
          </div>
        )}
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {loading ? (
        <p className="status-copy">원고를 불러오는 중…</p>
      ) : project === null || drafts === null ? null : (
        <>
          {project.archived ? (
            <p className="read-only-note">
              보관된 프로젝트에서는 새 원고를 만들 수 없습니다. 기존 원고는 계속 읽을 수 있습니다.
            </p>
          ) : (
            <form className="creation-form" onSubmit={submit}>
              <div className="form-copy">
                <label htmlFor="draft-title">새 원고 제목</label>
                <span>본문과 version 저장은 다음 단계에서 연결됩니다.</span>
              </div>
              <div className="form-controls">
                <input
                  id="draft-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  autoComplete="off"
                  placeholder="예: 1장 — 첫눈"
                />
                <button type="submit" disabled={title.trim() === "" || saving}>
                  원고 만들기
                </button>
              </div>
            </form>
          )}

          {drafts.length === 0 ? (
            <div className="empty-state">
              <p>아직 원고가 없습니다.</p>
              <span>첫 장면이나 장을 만들어 작품의 본문을 시작하세요.</span>
            </div>
          ) : (
            <ul className="resource-list" aria-label="원고 목록">
              {drafts.map((draft) => (
                <li className="resource-row draft-row" key={draft.id}>
                  <Link
                    aria-label={draft.title}
                    className="resource-link"
                    to={`/projects/${projectId}/drafts/${draft.id}`}
                  >
                    <span>{draft.title}</span>
                    <span className="row-arrow" aria-hidden="true">→</span>
                  </Link>
                  {draft.archived && <span className="status-badge">(보관됨)</span>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
