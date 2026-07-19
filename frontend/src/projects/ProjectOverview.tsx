import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  describeApiError,
  getProject,
  getProjectBrief,
  listCanonicalMemory,
  listReviewInbox,
  putProjectBrief,
  type CanonicalMemory,
  type Project,
  type ProjectBrief,
} from "../api/client";

type BriefForm = {
  premise: string;
  genre: string;
  tone: string;
  pov: string;
  constraints: string;
};

const EMPTY_FORM: BriefForm = {
  premise: "",
  genre: "",
  tone: "",
  pov: "",
  constraints: "",
};

function briefForm(brief: ProjectBrief | null): BriefForm {
  if (brief === null) return EMPTY_FORM;
  return {
    premise: brief.premise ?? "",
    genre: brief.genre ?? "",
    tone: brief.tone ?? "",
    pov: brief.pov ?? "",
    constraints: brief.constraints.join("\n"),
  };
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function memoryTitle(memory: CanonicalMemory): string {
  const payload = memory.payload;
  const preferred =
    memory.memory_type === "character_observation"
      ? payload.name
      : memory.memory_type === "event_observation"
        ? payload.event
        : payload.question;
  return typeof preferred === "string" ? preferred : "정본 항목";
}

const MEMORY_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥·미해결 질문",
};

export function ProjectOverview() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [brief, setBrief] = useState<ProjectBrief | null>(null);
  const [form, setForm] = useState<BriefForm>(EMPTY_FORM);
  const [memory, setMemory] = useState<CanonicalMemory[]>([]);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }
    let active = true;
    void Promise.all([
      getProject(projectId),
      getProjectBrief(projectId),
      listCanonicalMemory(projectId),
      listReviewInbox(projectId),
    ])
      .then(([nextProject, briefResponse, memoryResponse, inbox]) => {
        if (!active) return;
        setProject(nextProject);
        setBrief(briefResponse.brief);
        setForm(briefForm(briefResponse.brief));
        setEditing(briefResponse.brief === null);
        setMemory(memoryResponse.memory.filter((item) => item.status === "canonical"));
        setPending(inbox.items.length + inbox.gate_findings.length);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(describeApiError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function save(clear = false) {
    if (projectId === undefined || saving || project?.archived) return;
    const next = clear ? EMPTY_FORM : form;
    const constraints = next.constraints
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
    setSaving(true);
    setNotice(null);
    try {
      const response = await putProjectBrief(projectId, {
        base_version_id: brief?.id ?? null,
        idempotency_key: crypto.randomUUID(),
        premise: optional(next.premise),
        genre: optional(next.genre),
        tone: optional(next.tone),
        pov: optional(next.pov),
        constraints,
      });
      setBrief(response.brief);
      setForm(briefForm(response.brief));
      setEditing(false);
      setError(null);
      setNotice(
        clear
          ? "작품 정보를 비웠습니다. 이전 version 이력은 보존됩니다."
          : `작품 정보 version ${response.brief.version_number}을 저장했습니다.`,
      );
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <section className="workspace-page"><p>작품 정보를 불러오는 중…</p></section>;
  }

  return (
    <section className="workspace-page overview-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>← 원고 작업 공간</Link>
      <header className="page-heading project-heading">
        <p className="eyebrow">작품 정보 · 정본 개요</p>
        <h1>{project?.name ?? "프로젝트"}</h1>
        <p>작품 정보와 승인된 기억만 표시합니다. 검토 전 항목은 정본과 분리됩니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {notice !== null && <p className="source-jump-notice" role="status">{notice}</p>}

      {project !== null && (
        <section className="overview-section" aria-labelledby="brief-heading">
          <div className="overview-heading">
            <div>
              <p className="eyebrow">ProjectBrief · 정본</p>
              <h2 id="brief-heading">작품 시작 정보</h2>
            </div>
            {brief !== null && <span>version {brief.version_number}</span>}
          </div>

          {project.archived && (
            <p className="read-only-note">보관된 프로젝트의 작품 정보는 읽기만 가능합니다.</p>
          )}

          {editing && !project.archived ? (
            <div className="brief-form">
              <label>작품 전제<textarea value={form.premise} onChange={(e) => setForm({ ...form, premise: e.target.value })} /></label>
              <label>장르<input value={form.genre} onChange={(e) => setForm({ ...form, genre: e.target.value })} /></label>
              <label>톤<input value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })} /></label>
              <label>시점(POV)<input value={form.pov} onChange={(e) => setForm({ ...form, pov: e.target.value })} /></label>
              <label>핵심 제약 <span>한 줄에 하나</span><textarea value={form.constraints} onChange={(e) => setForm({ ...form, constraints: e.target.value })} /></label>
              <div className="brief-actions">
                <button type="button" onClick={() => void save(false)} disabled={saving}>저장</button>
                {brief === null ? (
                  <button className="secondary-button" type="button" onClick={() => void save(true)} disabled={saving}>지금은 건너뛰기</button>
                ) : (
                  <button className="secondary-button" type="button" onClick={() => { setForm(briefForm(brief)); setEditing(false); }}>취소</button>
                )}
              </div>
            </div>
          ) : brief === null || [brief.premise, brief.genre, brief.tone, brief.pov].every((value) => value === null) && brief.constraints.length === 0 ? (
            <div className="empty-state">
              <p>아직 작품 정보가 없습니다.</p>
              <span>필수 입력은 없습니다. 필요할 때 점진적으로 채울 수 있습니다.</span>
              {!project.archived && <button type="button" onClick={() => setEditing(true)}>작품 정보 작성</button>}
            </div>
          ) : (
            <>
              <dl className="brief-summary">
                <div><dt>전제</dt><dd>{brief.premise ?? "—"}</dd></div>
                <div><dt>장르</dt><dd>{brief.genre ?? "—"}</dd></div>
                <div><dt>톤</dt><dd>{brief.tone ?? "—"}</dd></div>
                <div><dt>시점</dt><dd>{brief.pov ?? "—"}</dd></div>
                <div><dt>제약</dt><dd>{brief.constraints.length > 0 ? brief.constraints.join(" · ") : "—"}</dd></div>
              </dl>
              {!project.archived && (
                <div className="brief-actions">
                  <button type="button" onClick={() => setEditing(true)}>수정</button>
                  <button className="danger-button" type="button" onClick={() => void save(true)} disabled={saving}>작품 정보 지우기 (이력 보존)</button>
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section className="overview-section" aria-labelledby="canon-heading">
        <div className="overview-heading">
          <div><p className="eyebrow">Canonical only</p><h2 id="canon-heading">승인된 작품 기억</h2></div>
          <Link to={`/projects/${projectId}/review`}>검토 전 {pending}개 →</Link>
        </div>
        {memory.length === 0 ? (
          <div className="empty-state"><p>승인된 작품 기억이 없습니다.</p><span>분석 후보는 검토함에서 승인한 뒤 여기에 표시됩니다.</span></div>
        ) : (
          <ul className="memory-grid">
            {memory.map((item) => (
              <li key={item.id}>
                <span>{MEMORY_LABELS[item.memory_type] ?? item.memory_type} · 정본</span>
                <strong>{memoryTitle(item)}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
