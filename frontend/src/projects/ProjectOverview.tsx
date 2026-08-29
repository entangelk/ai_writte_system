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
  styleRules: string;
  preferredPatterns: string;
  forbiddenPatterns: string;
  styleExamples: string[];
};

const EMPTY_FORM: BriefForm = {
  premise: "",
  genre: "",
  tone: "",
  pov: "",
  constraints: "",
  styleRules: "",
  preferredPatterns: "",
  forbiddenPatterns: "",
  styleExamples: [""],
};

const BRIEF_SCALAR_MAX_CHARS = 1000;
const BRIEF_SCALAR_WARN_CHARS = Math.floor(BRIEF_SCALAR_MAX_CHARS * 0.9);

function codePointLength(value: string): number {
  return [...value].length;
}

function BriefScalarCount({ value }: { value: string }) {
  const count = codePointLength(value);
  const className = count > BRIEF_SCALAR_MAX_CHARS
    ? "brief-char-count limit-over"
    : count >= BRIEF_SCALAR_WARN_CHARS
      ? "brief-char-count limit-near"
      : "brief-char-count";
  return <span className={className} aria-hidden="true">{count} / {BRIEF_SCALAR_MAX_CHARS}자</span>;
}

function hasOversizedScalar(form: BriefForm): boolean {
  return [form.premise, form.genre, form.tone, form.pov]
    .some((value) => codePointLength(value) > BRIEF_SCALAR_MAX_CHARS);
}

function briefForm(brief: ProjectBrief | null): BriefForm {
  if (brief === null) return EMPTY_FORM;
  return {
    premise: brief.premise ?? "",
    genre: brief.genre ?? "",
    tone: brief.tone ?? "",
    pov: brief.pov ?? "",
    constraints: brief.constraints.join("\n"),
    styleRules: brief.style_rules.join("\n"),
    preferredPatterns: brief.preferred_patterns.join("\n"),
    forbiddenPatterns: brief.forbidden_patterns.join("\n"),
    styleExamples: brief.style_examples.length > 0 ? [...brief.style_examples] : [""],
  };
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function lines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function examples(values: string[]): string[] {
  return values.map((value) => value.trim()).filter(Boolean);
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
  const scalarOverLimit = hasOversizedScalar(form);

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
        constraints: lines(next.constraints),
        style_rules: lines(next.styleRules),
        preferred_patterns: lines(next.preferredPatterns),
        forbidden_patterns: lines(next.forbiddenPatterns),
        style_examples: examples(next.styleExamples),
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
    return <p className="status-copy">작품 정보를 불러오는 중…</p>;
  }

  return (
    <>
      <p className="form-hint">
        작품 정보와 승인된 기억만 표시합니다. 검토 전 항목은 정본과 분리됩니다.
      </p>

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
              <label><span className="brief-field-heading"><span>작품 전제</span><BriefScalarCount value={form.premise} /></span><textarea aria-label="작품 전제" aria-invalid={codePointLength(form.premise) > BRIEF_SCALAR_MAX_CHARS} value={form.premise} onChange={(e) => setForm({ ...form, premise: e.target.value })} /></label>
              <label><span className="brief-field-heading"><span>장르</span><BriefScalarCount value={form.genre} /></span><input aria-label="장르" aria-invalid={codePointLength(form.genre) > BRIEF_SCALAR_MAX_CHARS} value={form.genre} onChange={(e) => setForm({ ...form, genre: e.target.value })} /></label>
              <label><span className="brief-field-heading"><span>톤</span><BriefScalarCount value={form.tone} /></span><input aria-label="톤" aria-invalid={codePointLength(form.tone) > BRIEF_SCALAR_MAX_CHARS} value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })} /></label>
              <label><span className="brief-field-heading"><span>시점(POV)</span><BriefScalarCount value={form.pov} /></span><input aria-label="시점(POV)" aria-invalid={codePointLength(form.pov) > BRIEF_SCALAR_MAX_CHARS} value={form.pov} onChange={(e) => setForm({ ...form, pov: e.target.value })} /></label>
              <label>핵심 제약 <span>한 줄에 하나</span><textarea value={form.constraints} onChange={(e) => setForm({ ...form, constraints: e.target.value })} /></label>
              <label>문체 규칙 <span>한 줄에 하나</span><textarea value={form.styleRules} onChange={(e) => setForm({ ...form, styleRules: e.target.value })} /></label>
              <label>선호 표현 <span>한 줄에 하나</span><textarea value={form.preferredPatterns} onChange={(e) => setForm({ ...form, preferredPatterns: e.target.value })} /></label>
              <label>피할 표현 <span>한 줄에 하나</span><textarea value={form.forbiddenPatterns} onChange={(e) => setForm({ ...form, forbiddenPatterns: e.target.value })} /></label>
              <fieldset className="brief-style-examples">
                <legend>문체 예시 <span>예시 안의 줄바꿈 유지 · 기본 최대 3개</span></legend>
                {form.styleExamples.map((example, index) => (
                  <div key={index}>
                    <label htmlFor={`style-example-${index}`}>문체 예시 {index + 1}</label>
                    <textarea
                      id={`style-example-${index}`}
                      value={example}
                      onChange={(event) => setForm({
                        ...form,
                        styleExamples: form.styleExamples.map((value, itemIndex) =>
                          itemIndex === index ? event.target.value : value),
                      })}
                    />
                    {form.styleExamples.length > 1 && (
                      <button
                        className="secondary-button"
                        type="button"
                        aria-label={`문체 예시 ${index + 1} 삭제`}
                        onClick={() => setForm({
                          ...form,
                          styleExamples: form.styleExamples.filter((_, itemIndex) => itemIndex !== index),
                        })}
                      >삭제</button>
                    )}
                  </div>
                ))}
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setForm({ ...form, styleExamples: [...form.styleExamples, ""] })}
                >문체 예시 추가</button>
              </fieldset>
              <div className="brief-actions">
                <button type="button" onClick={() => void save(false)} disabled={saving || scalarOverLimit}>저장</button>
                {brief === null ? (
                  <button className="secondary-button" type="button" onClick={() => void save(true)} disabled={saving}>지금은 건너뛰기</button>
                ) : (
                  <button className="secondary-button" type="button" onClick={() => { setForm(briefForm(brief)); setEditing(false); }}>취소</button>
                )}
              </div>
            </div>
          ) : brief === null || [brief.premise, brief.genre, brief.tone, brief.pov].every((value) => value === null) && [brief.constraints, brief.style_rules, brief.preferred_patterns, brief.forbidden_patterns, brief.style_examples].every((value) => value.length === 0) ? (
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
                <div><dt>문체 규칙</dt><dd>{brief.style_rules.length > 0 ? brief.style_rules.join(" · ") : "—"}</dd></div>
                <div><dt>선호 표현</dt><dd>{brief.preferred_patterns.length > 0 ? brief.preferred_patterns.join(" · ") : "—"}</dd></div>
                <div><dt>피할 표현</dt><dd>{brief.forbidden_patterns.length > 0 ? brief.forbidden_patterns.join(" · ") : "—"}</dd></div>
                <div><dt>문체 예시</dt><dd>{brief.style_examples.length > 0 ? brief.style_examples.join(" / ") : "—"}</dd></div>
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
          <Link className="inline-navigation-link" to={`/projects/${projectId}/review`}>검토 전 {pending}개 →</Link>
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
    </>
  );
}
