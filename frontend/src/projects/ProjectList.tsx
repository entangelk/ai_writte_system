import { useCallback, useEffect, useState } from "react";
import { ApiError, createProject, listProjects, type Project } from "../api/client";

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
      setError(describe(err));
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
      setError(describe(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h1>프로젝트</h1>

      <form onSubmit={submit}>
        <label htmlFor="project-name">새 프로젝트 이름</label>
        <input
          id="project-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="off"
        />
        <button type="submit" disabled={name.trim() === "" || saving}>
          만들기
        </button>
      </form>

      {error !== null && <p role="alert">{error}</p>}

      {projects === null ? (
        <p>불러오는 중…</p>
      ) : projects.length === 0 ? (
        <p>아직 프로젝트가 없습니다. 첫 프로젝트를 만들어 시작하세요.</p>
      ) : (
        <ul>
          {projects.map((project) => (
            <li key={project.id}>
              <span>{project.name}</span>
              {project.archived && <span> (보관됨)</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.status}: ${err.detail}`;
  }
  return err instanceof Error ? err.message : String(err);
}
