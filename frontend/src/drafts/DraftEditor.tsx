import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import {
  ApiError,
  describeApiError,
  exportDraftVersion,
  getDraft,
  getDraftVersion,
  getProject,
  listDrafts,
  listDraftVersions,
  saveDraft,
  type Draft,
  type DraftVersion,
  type Project,
  type ReviewSourcePointer,
} from "../api/client";
import { WritingPanel } from "../writing/WritingPanel";
import { ScratchRecovery } from "../writing/ScratchRecovery";
import { GenerationPad } from "../writing/GenerationPad";
import { useGenerationJobs } from "../writing/useGenerationJobs";
import { AnalysisTrigger } from "../review/AnalysisTrigger";
import { WorkspaceReviewPanel } from "../review/WorkspaceReviewPanel";

type SaveIntent = {
  key: string;
  rawText: string;
};

const DEFINITIVE_SAVE_FAILURES = new Set([400, 404, 409, 422]);

function latestOf(versions: DraftVersion[]): DraftVersion | null {
  return versions.reduce<DraftVersion | null>(
    (selected, version) =>
      selected === null || version.version_number > selected.version_number
        ? version
        : selected,
    null,
  );
}

function codePointSpan(rawText: string, start: number, end: number) {
  const points = Array.from(rawText);
  if (start < 0 || end <= start || end > points.length) return null;
  return {
    quote: points.slice(start, end).join(""),
    start: points.slice(0, start).join("").length,
    end: points.slice(0, end).join("").length,
  };
}

export function DraftEditor() {
  const { projectId, draftId } = useParams<{
    projectId: string;
    draftId: string;
  }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPanel = searchParams.get("panel");
  const activePanel = requestedPanel === "analysis" || requestedPanel === "review"
    ? requestedPanel
    : "writing";
  const [project, setProject] = useState<Project | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [rawText, setRawText] = useState("");
  const [baseline, setBaseline] = useState("");
  const [versions, setVersions] = useState<DraftVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedContentHash, setSelectedContentHash] = useState<string | null>(null);
  const [versionNumber, setVersionNumber] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [exporting, setExporting] = useState<"txt" | "markdown" | null>(null);
  const [forcedReadOnly, setForcedReadOnly] = useState(false);
  // Bumped after a successful accept so the scratch-recovery banner re-fetches
  // and clears (the accept dropped the draft's scratch server-side).
  const [scratchRefresh, setScratchRefresh] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState<
    "idle" | "running" | "failed" | "complete"
  >("idle");
  const [pendingReviewCount, setPendingReviewCount] = useState<number | null>(null);
  const [sourceNotice, setSourceNotice] = useState<string | null>(null);
  const [pendingSelection, setPendingSelection] = useState<{
    start: number;
    end: number;
  } | null>(null);
  const savingRef = useRef(false);
  const selectingRef = useRef(false);
  const exportingRef = useRef(false);
  const intentRef = useRef<SaveIntent | null>(null);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);

  // 증분 3 (D6): track async (medium/long) generations. Polling lives here (not in
  // WritingPanel) so it survives tab switches and drives the tab completion badge.
  // A settled job re-fetches the scratch list — the worker appended a succeeded
  // result there, so the result pad (ScratchRecovery) resurfaces it.
  const {
    activeJobs: generationJobs,
    failedJobs: failedGenerationJobs,
    track: trackGenerationJob,
    settledUnseen: unseenGenerationJobs,
    acknowledge: acknowledgeGenerationJobs,
    dismissFailed: dismissGenerationJob,
    retry: retryGenerationJob,
  } = useGenerationJobs(projectId ?? "", draftId ?? "", {
    onSettled: () => setScratchRefresh((count) => count + 1),
  });

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
        const latest = latestOf(versions);
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
        setSelectedContentHash(detail?.snapshot.content_hash ?? null);
        setVersionNumber(detail?.draft_version.version_number ?? null);
        setSourceNotice(null);
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
  const latest = latestOf(versions);
  const latestVersionId = latest?.id ?? null;
  const latestSnapshotId = latest?.snapshot_id ?? null;
  const onLatest = selectedVersionId !== null && selectedVersionId === latestVersionId;
  const allowNavigationAway = useCallback(
    () => !dirty || window.confirm("저장하지 않은 변경 사항을 버리고 페이지를 이동하시겠습니까?"),
    [dirty],
  );

  useEffect(() => {
    setAnalysisStatus("idle");
  }, [latestSnapshotId]);

  // Viewing the writing tab counts as seeing the completed generations, so clear
  // the tab badge. Completions that land while another tab is open keep it lit.
  useEffect(() => {
    if (activePanel === "writing" && unseenGenerationJobs > 0) {
      acknowledgeGenerationJobs();
    }
  }, [activePanel, unseenGenerationJobs, acknowledgeGenerationJobs]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (pendingSelection === null) return;
    const editor = editorRef.current;
    if (editor === null) return;
    editor.focus();
    editor.setSelectionRange(pendingSelection.start, pendingSelection.end);
    setPendingSelection(null);
  }, [pendingSelection, rawText]);

  function selectPanel(panel: "writing" | "analysis" | "review"): void {
    const next = new URLSearchParams(searchParams);
    next.set("panel", panel);
    if (panel !== "review") {
      next.delete("candidate");
      next.delete("source");
    }
    setSearchParams(next);
  }

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
      setSelectedContentHash(result.snapshot.content_hash);
      setVersionNumber(result.draft_version.version_number);
      setSourceNotice(null);
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
      setSelectedContentHash(detail.snapshot.content_hash);
      setVersionNumber(detail.draft_version.version_number);
      setSourceNotice(null);
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

  const openSource = useCallback(async (source: ReviewSourcePointer) => {
    if (
      projectId === undefined ||
      draftId === undefined ||
      source.snapshot_id === undefined ||
      source.start_offset === undefined ||
      source.end_offset === undefined ||
      savingRef.current ||
      selectingRef.current
    ) return;

    let targetDraftId = draftId;
    let targetVersions = versions;
    let target = targetVersions.find(
      (version) => version.snapshot_id === source.snapshot_id,
    );

    try {
      if (target === undefined) {
        const { drafts } = await listDrafts(projectId);
        for (const candidateDraft of drafts) {
          if (candidateDraft.id === draftId) continue;
          const listed = await listDraftVersions(projectId, candidateDraft.id);
          const matched = listed.versions.find(
            (version) => version.snapshot_id === source.snapshot_id,
          );
          if (matched !== undefined) {
            targetDraftId = candidateDraft.id;
            targetVersions = listed.versions;
            target = matched;
            break;
          }
        }
      }

      if (target === undefined) {
        setError("이 근거가 가리키는 원고 version을 찾을 수 없습니다.");
        return;
      }

      if (targetDraftId !== draftId) {
        if (
          dirty &&
          !window.confirm("저장하지 않은 변경 사항을 버리고 다른 원고의 근거를 여시겠습니까?")
        ) return;
        const next = new URLSearchParams(searchParams);
        next.set("panel", "review");
        next.set("source", source.source_ref_id);
        navigate(
          `/projects/${projectId}/drafts/${targetDraftId}?${next.toString()}`,
        );
        return;
      }

      if (
        dirty &&
        target.id !== selectedVersionId &&
        !window.confirm("저장하지 않은 변경 사항을 버리고 근거 version을 여시겠습니까?")
      ) return;

      selectingRef.current = true;
      setSelecting(true);
      const detail = target.id === selectedVersionId
        ? null
        : await getDraftVersion(projectId, targetDraftId, target.id);
      const targetText = detail?.snapshot.raw_text ?? rawText;
      const targetHash = detail?.snapshot.content_hash ?? selectedContentHash;
      const span = codePointSpan(targetText, source.start_offset, source.end_offset);
      if (
        span === null ||
        (source.quote !== undefined && span.quote !== source.quote) ||
        (source.content_hash !== undefined && targetHash !== undefined &&
          source.content_hash !== targetHash)
      ) {
        setError("근거의 offset 또는 내용이 저장된 version과 일치하지 않습니다.");
        return;
      }

      if (detail !== null) {
        setRawText(targetText);
        setBaseline(targetText);
        setSelectedVersionId(detail.draft_version.id);
        setSelectedContentHash(detail.snapshot.content_hash);
        setVersionNumber(detail.draft_version.version_number);
        intentRef.current = null;
      }
      const newest = latestOf(targetVersions);
      setSourceNotice(
        target.id === newest?.id
          ? `최신 version ${target.version_number} 근거 · 선택 영역 ${source.start_offset}–${source.end_offset}`
          : `과거 version ${target.version_number} 근거 · 현재 최신 원고가 아님 · 선택 영역 ${source.start_offset}–${source.end_offset}`,
      );
      setPendingSelection({ start: span.start, end: span.end });
      setError(null);
      setNotice(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      selectingRef.current = false;
      setSelecting(false);
    }
  }, [
    dirty,
    draftId,
    navigate,
    projectId,
    rawText,
    searchParams,
    selectedContentHash,
    selectedVersionId,
    versions,
  ]);

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

  // After a Writing candidate is accepted (a new version is saved, including the
  // 502-partial case where only the Analysis job failed), reload the latest from
  // the server so the editor baseline/history reflect the new version.
  async function reloadLatest() {
    if (projectId === undefined || draftId === undefined) return;
    try {
      const { versions: nextVersions } = await listDraftVersions(projectId, draftId);
      const latest = latestOf(nextVersions);
      const detail = latest === null
        ? null
        : await getDraftVersion(projectId, draftId, latest.id);
      const nextText = detail?.snapshot.raw_text ?? "";
      setRawText(nextText);
      setBaseline(nextText);
      setVersions(nextVersions);
      setSelectedVersionId(detail?.draft_version.id ?? null);
      setSelectedContentHash(detail?.snapshot.content_hash ?? null);
      setVersionNumber(detail?.draft_version.version_number ?? null);
      setSourceNotice(null);
      setNotice(null);
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    }
  }

  return (
    <section className="workspace-page editor-page page-enter">
      <Link
        className="back-link"
        to={`/projects/${projectId ?? ""}`}
        onClick={(event) => {
          if (!allowNavigationAway()) event.preventDefault();
        }}
      >
        ← 원고 목록으로 돌아가기
      </Link>

      <header className="page-heading editor-heading">
        <div>
          <p className="eyebrow">원고 편집기</p>
          <h1>{draft?.title ?? "원고"}</h1>
          <p>{project?.name ?? "프로젝트"}</p>
        </div>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {loading || (draft !== null && draft.id !== draftId) ? (
        <p className="status-copy">원고를 불러오는 중…</p>
      ) : project === null || draft === null ? null : (
        <>
          <div className="workspace-status" aria-label="작업 상태">
            <span>{dirty ? "저장 안 됨" : "저장됨"}</span>
            <span>분석 {analysisStatus === "idle" ? "미실행" : analysisStatus === "running" ? "진행 중" : analysisStatus === "failed" ? "실패" : "완료"}</span>
            <span>검토 대기 {pendingReviewCount === null ? "—" : `${pendingReviewCount}건`}</span>
          </div>
          <div className="split-workspace">
            <div className="editor-canvas">
              {readOnly && (
                <p className="read-only-note">
                  보관된 원고는 읽기 전용입니다. 저장된 본문은 계속 읽을 수 있습니다.
                </p>
              )}
              {sourceNotice !== null && (
                <p className="source-jump-notice" role="status">{sourceNotice}</p>
              )}
              <form className="editor-form" onSubmit={submit}>
            <div className="editor-meta">
              <label htmlFor="draft-body">원고 본문</label>
              <span>
                {versionNumber === null ? "아직 저장된 version 없음" : `현재 version ${versionNumber}`}
              </span>
            </div>
            <textarea
              ref={editorRef}
              id="draft-body"
              value={rawText}
              onChange={(event) => {
                setRawText(event.target.value);
                setNotice(null);
                setSourceNotice(null);
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
            </div>

            {projectId !== undefined && draftId !== undefined && (
              <aside className="workspace-rail" aria-label="집필 도구">
                <div className="rail-tabs" role="tablist" aria-label="집필 도구 선택">
                  {(["writing", "analysis", "review"] as const).map((panel) => (
                    <button
                      key={panel}
                      type="button"
                      role="tab"
                      aria-selected={activePanel === panel}
                      onClick={() => selectPanel(panel)}
                    >
                      {panel === "writing" ? "이어쓰기" : panel === "analysis" ? "분석" : "검토"}
                      {panel === "writing" && unseenGenerationJobs > 0 && (
                        <span
                          className="tab-badge"
                          aria-label={`백그라운드 생성 완료 ${unseenGenerationJobs}건`}
                        >
                          {unseenGenerationJobs}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
                <div className="rail-panel" role="tabpanel">
                  {/* Layer tabs (dogfood 결손 수정): panels stay MOUNTED and only the
                      inactive ones are hidden, so WritingPanel input state and the
                      background GenerationPad/ScratchRecovery conduit survive tab
                      switches. The active panel is selected by the `panel` query
                      param (selectPanel) — unchanged. */}
                  <div
                    className={
                      activePanel === "writing" ? "rail-layer" : "rail-layer hidden"
                    }
                    aria-hidden={activePanel !== "writing"}
                  >
                    <GenerationPad
                      activeJobs={generationJobs}
                      failedJobs={failedGenerationJobs}
                      onDismissFailed={dismissGenerationJob}
                      onRetryFailed={(jobId) => void retryGenerationJob(jobId)}
                    />
                    <ScratchRecovery
                      projectId={projectId}
                      draftId={draftId}
                      refreshKey={scratchRefresh}
                    />
                    <WritingPanel
                      projectId={projectId}
                      draftId={draftId}
                      latestVersionId={latestVersionId}
                      onLatest={onLatest}
                      dirty={dirty}
                      hasVersions={versions.length > 0}
                      readOnly={readOnly}
                      onAccepted={() => {
                        setScratchRefresh((n) => n + 1);
                        void reloadLatest();
                      }}
                      onAsyncJobStarted={trackGenerationJob}
                    />
                  </div>
                  <div
                    className={
                      activePanel === "analysis" ? "rail-layer" : "rail-layer hidden"
                    }
                    aria-hidden={activePanel !== "analysis"}
                  >
                    <AnalysisTrigger
                      projectId={projectId}
                      draftId={draftId}
                      latestVersionId={latestVersionId}
                      latestSnapshotId={latestSnapshotId}
                      readOnly={readOnly}
                      dirty={dirty}
                      onStatusChange={setAnalysisStatus}
                      onBeforeNavigateAway={allowNavigationAway}
                    />
                  </div>
                  <div
                    className={
                      activePanel === "review" ? "rail-layer" : "rail-layer hidden"
                    }
                    aria-hidden={activePanel !== "review"}
                  >
                    <WorkspaceReviewPanel
                      key={draftId}
                      projectId={projectId}
                      tabActive={activePanel === "review"}
                      onSourceSelect={(source) => void openSource(source)}
                      onPendingCountChange={setPendingReviewCount}
                      onBeforeNavigateAway={allowNavigationAway}
                    />
                  </div>
                </div>
              </aside>
            )}
          </div>
        </>
      )}
    </section>
  );
}
