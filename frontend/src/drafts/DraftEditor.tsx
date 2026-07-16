import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ApiError,
  describeApiError,
  getDraft,
  getDraftVersion,
  getProject,
  listDraftVersions,
  saveDraft,
  type Draft,
  type Project,
} from "../api/client";

type SaveIntent = {
  key: string;
  rawText: string;
};

const DEFINITIVE_SAVE_FAILURES = new Set([400, 404, 409, 422]);

export function DraftEditor() {
  const { projectId, draftId } = useParams<{
    projectId: string;
    draftId: string;
  }>();
  const [project, setProject] = useState<Project | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [rawText, setRawText] = useState("");
  const [baseline, setBaseline] = useState("");
  const [versionNumber, setVersionNumber] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [forcedReadOnly, setForcedReadOnly] = useState(false);
  const savingRef = useRef(false);
  const intentRef = useRef<SaveIntent | null>(null);

  useEffect(() => {
    if (projectId === undefined || draftId === undefined) {
      setError("원고 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    void Promise.all([
      getProject(projectId),
      getDraft(projectId, draftId),
      listDraftVersions(projectId, draftId),
    ])
      .then(async ([nextProject, nextDraft, { versions }]) => {
        const latest = versions.reduce<(typeof versions)[number] | null>(
          (selected, version) =>
            selected === null || version.version_number > selected.version_number
              ? version
              : selected,
          null,
        );
        const detail = latest === null
          ? null
          : await getDraftVersion(projectId, draftId, latest.id);
        if (!active) return;

        const nextText = detail?.snapshot.raw_text ?? "";
        setProject(nextProject);
        setDraft(nextDraft);
        setRawText(nextText);
        setBaseline(nextText);
        setVersionNumber(detail?.draft_version.version_number ?? null);
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
  }, [projectId, draftId]);

  const dirty = rawText !== baseline;
  const readOnly = forcedReadOnly || project?.archived === true || draft?.archived === true;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (
      projectId === undefined ||
      draftId === undefined ||
      !dirty ||
      readOnly ||
      savingRef.current
    ) {
      return;
    }

    savingRef.current = true;
    setSaving(true);
    setNotice(null);
    const intent = intentRef.current?.rawText === rawText
      ? intentRef.current
      : { key: crypto.randomUUID(), rawText };
    intentRef.current = intent;

    try {
      const result = await saveDraft(projectId, draftId, {
        raw_text: intent.rawText,
        idempotency_key: intent.key,
      });
      setBaseline(intent.rawText);
      setVersionNumber(result.draft_version.version_number);
      setError(null);
      setNotice(
        result.idempotent_replay
          ? `version ${result.draft_version.version_number} 재확인됨`
          : `version ${result.draft_version.version_number} 저장됨`,
      );
      intentRef.current = null;
    } catch (err) {
      setError(describeApiError(err));
      if (err instanceof ApiError && DEFINITIVE_SAVE_FAILURES.has(err.status)) {
        intentRef.current = null;
        if (err.status === 409) setForcedReadOnly(true);
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <section className="workspace-page editor-page page-enter">
      <Link className="back-link" to={`/projects/${projectId ?? ""}`}>
        ← 원고 목록으로 돌아가기
      </Link>

      <header className="page-heading editor-heading">
        <p className="eyebrow">원고 편집기</p>
        <h1>{draft?.title ?? "원고"}</h1>
        <p>{project?.name ?? "프로젝트"}</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {loading ? (
        <p className="status-copy">원고를 불러오는 중…</p>
      ) : project === null || draft === null ? null : (
        <>
          {readOnly && (
            <p className="read-only-note">
              보관된 원고는 읽기 전용입니다. 저장된 본문은 계속 읽을 수 있습니다.
            </p>
          )}
          <form className="editor-form" onSubmit={submit}>
            <div className="editor-meta">
              <label htmlFor="draft-body">원고 본문</label>
              <span>
                {versionNumber === null ? "아직 저장된 version 없음" : `현재 version ${versionNumber}`}
              </span>
            </div>
            <textarea
              id="draft-body"
              value={rawText}
              onChange={(event) => {
                setRawText(event.target.value);
                setNotice(null);
              }}
              readOnly={readOnly}
              spellCheck="true"
              placeholder="이곳에서 원고를 시작하세요."
            />
            <div className="editor-actions">
              <span aria-live="polite">
                {notice ?? (dirty ? "저장하지 않은 변경 사항" : "모든 변경 사항 저장됨")}
              </span>
              {!readOnly && (
                <button type="submit" disabled={!dirty || saving}>
                  {saving ? "저장 중…" : "저장"}
                </button>
              )}
            </div>
          </form>
        </>
      )}
    </section>
  );
}
