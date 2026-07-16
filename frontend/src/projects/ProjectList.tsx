import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import {
  createProject,
  describeApiError,
  listProjects,
  type Project,
} from "../api/client";

export function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { projects } = await listProjects();
      setProjects(projects);
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "" || saving) {
      return;
    }
    setSaving(true);
    try {
      await createProject({ name: trimmed });
      setName("");
      setError(null);
      await load();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-page page-enter">
      <header className="page-heading">
        <p className="eyebrow">작품 서재</p>
        <h1>프로젝트</h1>
        <p>작품을 선택하거나 새 원고 공간을 만드세요.</p>
      </header>

      <form className="creation-form" onSubmit={submit}>
        <div className="form-copy">
          <label htmlFor="project-name">새 프로젝트 이름</label>
          <span>작품별 원고와 기억은 서로 분리됩니다.</span>
        </div>
        <div className="form-controls">
          <input
            id="project-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            placeholder="예: 겨울 이야기"
          />
          <button type="submit" disabled={name.trim() === "" || saving}>
            만들기
          </button>
        </div>
      </form>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {projects === null ? (
        <p className="status-copy">불러오는 중…</p>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <p>아직 프로젝트가 없습니다.</p>
          <span>위에서 첫 프로젝트를 만들어 집필을 시작하세요.</span>
        </div>
      ) : (
        <ul className="resource-list" aria-label="프로젝트 목록">
          {projects.map((project) => (
            <li className="resource-row" key={project.id}>
              <Link
                aria-label={project.name}
                className="resource-link"
                to={`/projects/${project.id}`}
              >
                <span>{project.name}</span>
                <span className="row-arrow" aria-hidden="true">→</span>
              </Link>
              {project.archived && <span className="status-badge">(보관됨)</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
