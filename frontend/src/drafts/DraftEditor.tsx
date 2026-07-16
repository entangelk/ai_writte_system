import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ApiError,
  describeApiError,
  exportDraftVersion,
  getDraft,
  getDraftVersion,
  getProject,
  listDraftVersions,
  saveDraft,
  type Draft,
  type DraftVersion,
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
  const [versions, setVersions] = useState<DraftVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [versionNumber, setVersionNumber] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [exporting, setExporting] = useState<"txt" | "markdown" | null>(null);
  const [forcedReadOnly, setForcedReadOnly] = useState(false);
  const savingRef = useRef(false);
  const selectingRef = useRef(false);
  const exportingRef = useRef(false);
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
        setVersions(versions);
        setSelectedVersionId(detail?.draft_version.id ?? null);
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
      const savedVersion: DraftVersion = {
        id: result.draft_version.id,
        project_id: projectId,
        draft_id: draftId,
        version_number: result.draft_version.version_number,
        snapshot_id: result.draft_version.snapshot_id,
      };
      setVersions((current) => [
        savedVersion,
        ...current.filter((version) => version.id !== savedVersion.id),
      ]);
      setSelectedVersionId(savedVersion.id);
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

  async function selectVersion(version: DraftVersion) {
    if (
      projectId === undefined ||
      draftId === undefined ||
      version.id === selectedVersionId ||
      savingRef.current ||
      selectingRef.current
    ) {
      return;
    }
    if (
      dirty &&
      !window.confirm("저장하지 않은 변경 사항을 버리고 이 version을 여시겠습니까?")
    ) {
      return;
    }

    selectingRef.current = true;
    setSelecting(true);
    try {
      const detail = await getDraftVersion(projectId, draftId, version.id);
      setRawText(detail.snapshot.raw_text);
      setBaseline(detail.snapshot.raw_text);
      setSelectedVersionId(detail.draft_version.id);
      setVersionNumber(detail.draft_version.version_number);
      setError(null);
      setNotice(null);
      intentRef.current = null;
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      selectingRef.current = false;
      setSelecting(false);
    }
  }

  async function download(format: "txt" | "markdown") {
    if (
      projectId === undefined ||
      draftId === undefined ||
      selectedVersionId === null ||
      exportingRef.current
    ) {
      return;
    }

    exportingRef.current = true;
    setExporting(format);
    try {
      const exported = await exportDraftVersion(
        projectId,
        draftId,
        selectedVersionId,
        format,
      );
      const url = URL.createObjectURL(
        new Blob([exported.body], { type: exported.content_type }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = exported.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      exportingRef.current = false;
      setExporting(null);
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
              readOnly={readOnly || selecting}
              aria-busy={selecting}
              spellCheck="true"
              placeholder="이곳에서 원고를 시작하세요."
            />
            <div className="editor-actions">
              <span aria-live="polite">
                {notice ?? (dirty ? "저장하지 않은 변경 사항" : "모든 변경 사항 저장됨")}
              </span>
              {!readOnly && (
                <button type="submit" disabled={!dirty || saving || selecting}>
                  {saving ? "저장 중…" : "저장"}
                </button>
              )}
            </div>
          </form>

          <section className="version-panel" aria-labelledby="version-history-title">
            <div className="version-panel-heading">
              <div>
                <p className="eyebrow">저장 기록</p>
                <h2 id="version-history-title">Version history</h2>
              </div>
              {selectedVersionId !== null && (
                <div className="export-actions" aria-label="선택 version 내보내기">
                  <button
                    type="button"
                    disabled={exporting !== null}
                    onClick={() => void download("txt")}
                  >
                    {exporting === "txt" ? "내보내는 중…" : "TXT 내보내기"}
                  </button>
                  <button
                    type="button"
                    disabled={exporting !== null}
                    onClick={() => void download("markdown")}
                  >
                    {exporting === "markdown" ? "내보내는 중…" : "Markdown 내보내기"}
                  </button>
                </div>
              )}
            </div>

            {versions.length === 0 ? (
              <p className="version-empty">저장하면 첫 version이 여기에 표시됩니다.</p>
            ) : (
              <ul className="version-list" aria-label="버전 기록">
                {[...versions]
                  .sort((left, right) => right.version_number - left.version_number)
                  .map((version) => (
                    <li key={version.id}>
                      <button
                        type="button"
                        aria-current={version.id === selectedVersionId ? "true" : undefined}
                        disabled={saving || selecting}
                        onClick={() => void selectVersion(version)}
                      >
                        version {version.version_number}
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
