import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import JSZip from "jszip";
import {
  createDraft,
  describeApiError,
  exportDraftVersion,
  exportProject,
  getProject,
  listDrafts,
  putDraftOrder,
  type CreateDraftRequest,
  type Draft,
  type Project,
} from "../api/client";

type ExportFormat = "txt" | "markdown";
type ExportKind = "combined" | "bundle";

const EXTENSION: Record<ExportFormat, string> = { txt: "txt", markdown: "md" };

// Zip entry names are a presentation concern, not a canonical contract: order
// by canonical position (zero-padded) and carry the human title, sanitizing the
// characters a filesystem/zip path cannot hold. Falls back to the draft id when
// a title sanitizes to empty.
function bundleEntryName(
  draftId: string,
  title: string,
  position: number | null,
  format: ExportFormat,
): string {
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, "_").trim();
  const stem = safeTitle === "" ? draftId : safeTitle;
  const prefix = String(position ?? 0).padStart(2, "0");
  return `${prefix}-${stem}.${EXTENSION[format]}`;
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function DraftList() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [title, setTitle] = useState("");
  const [unitKind, setUnitKind] = useState<CreateDraftRequest["unit_kind"]>("other");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState<{ kind: ExportKind; format: ExportFormat } | null>(
    null,
  );
  const [includeArchived, setIncludeArchived] = useState(false);
  const [withManifest, setWithManifest] = useState(false);
  const exportingRef = useRef(false);

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
      await createDraft(projectId, { title: trimmed, unit_kind: unitKind });
      setTitle("");
      setError(null);
      await loadDrafts();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function moveDraft(index: number, offset: -1 | 1) {
    if (projectId === undefined || drafts === null || saving || project?.archived) {
      return;
    }
    const target = index + offset;
    if (target < 0 || target >= drafts.length) {
      return;
    }
    const reordered = [...drafts];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    setSaving(true);
    try {
      const response = await putDraftOrder(projectId, {
        ordered_draft_ids: reordered.map((draft) => draft.id),
      });
      setDrafts(response.drafts);
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function runExport(kind: ExportKind, format: ExportFormat) {
    if (projectId === undefined || exportingRef.current) {
      return;
    }
    exportingRef.current = true;
    setExporting({ kind, format });
    try {
      if (kind === "combined") {
        const exported = await exportProject(projectId, format, {
          includeArchived,
          manifest: withManifest,
        });
        triggerDownload(
          new Blob([exported.body], { type: exported.content_type }),
          exported.filename,
        );
        if (withManifest && exported.manifest !== null) {
          triggerDownload(
            new Blob([JSON.stringify(exported.manifest, null, 2)], {
              type: "application/json",
            }),
            `${projectId}.manifest.json`,
          );
        }
      } else {
        // Bulk: enumerate the exact included units from the delivery manifest,
        // fetch each unit's latest version body verbatim (no heading synthesis),
        // and bundle them (plus the manifest when requested) as one zip.
        const { manifest } = await exportProject(projectId, format, {
          includeArchived,
          manifest: true,
        });
        if (manifest === null) {
          return;
        }
        const zip = new JSZip();
        for (const unit of manifest.units) {
          const exported = await exportDraftVersion(
            projectId,
            unit.draft_id,
            unit.version_id,
            format,
          );
          zip.file(
            bundleEntryName(unit.draft_id, unit.title, unit.position, format),
            exported.body,
          );
        }
        if (withManifest) {
          zip.file("manifest.json", JSON.stringify(manifest, null, 2));
        }
        const blob = await zip.generateAsync({ type: "blob" });
        triggerDownload(blob, `${projectId}.zip`);
      }
      setError(null);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      exportingRef.current = false;
      setExporting(null);
    }
  }

  // At least one unit would actually be exported under the current archived
  // toggle. Archived units are excluded unless the user opts them in, so an
  // archived-only project can only export once "보관된 원고 포함" is on.
  const canExport =
    drafts !== null && drafts.some((draft) => includeArchived || !draft.archived);

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
            <Link
              className="section-link"
              to={`/projects/${projectId}/observability`}
            >
              파이프라인 관측 →
            </Link>
            <Link className="section-link" to={`/projects/${projectId}/access-log`}>
              관리자 접근 이력 →
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
                <label className="sr-only" htmlFor="draft-unit-kind">원고 단위</label>
                <select
                  id="draft-unit-kind"
                  value={unitKind}
                  onChange={(event) => setUnitKind(event.target.value as CreateDraftRequest["unit_kind"])}
                >
                  <option value="chapter">장</option>
                  <option value="scene">장면</option>
                  <option value="other">기타</option>
                </select>
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
              {drafts.map((draft, index) => (
                <li className="resource-row draft-row" key={draft.id}>
                  <Link
                    aria-label={draft.title}
                    className="resource-link"
                    to={`/projects/${projectId}/drafts/${draft.id}`}
                  >
                    <span>{draft.title}</span>
                    <span className="row-arrow" aria-hidden="true">→</span>
                  </Link>
                  <span className="status-badge">
                    정본 순서 {draft.position} · {draft.unit_kind === "chapter"
                      ? "장"
                      : draft.unit_kind === "scene" ? "장면" : "기타"}
                  </span>
                  {draft.archived && <span className="status-badge">(보관됨)</span>}
                  {!project.archived && (
                    <span className="order-controls">
                      <button
                        aria-label={`${draft.title} 위로`}
                        disabled={saving || index === 0}
                        onClick={() => void moveDraft(index, -1)}
                        type="button"
                      >↑</button>
                      <button
                        aria-label={`${draft.title} 아래로`}
                        disabled={saving || index === drafts.length - 1}
                        onClick={() => void moveDraft(index, 1)}
                        type="button"
                      >↓</button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}

          {drafts.length > 0 && (
            <section className="export-controls" aria-label="원고 내보내기">
              <div className="export-options">
                {drafts.some((draft) => draft.archived) && (
                  <label className="export-option">
                    <input
                      type="checkbox"
                      checked={includeArchived}
                      disabled={exporting !== null}
                      onChange={(event) => setIncludeArchived(event.target.checked)}
                    />
                    보관된 원고 포함
                  </label>
                )}
                <label className="export-option">
                  <input
                    type="checkbox"
                    checked={withManifest}
                    disabled={exporting !== null}
                    onChange={(event) => setWithManifest(event.target.checked)}
                  />
                  추적 정보(manifest) 함께
                </label>
              </div>
              <div className="export-group">
                <p className="export-label">전체 원고를 한 파일로</p>
                <div className="export-buttons">
                  <button
                    type="button"
                    disabled={exporting !== null || !canExport}
                    onClick={() => void runExport("combined", "txt")}
                  >
                    {exporting?.kind === "combined" && exporting.format === "txt"
                      ? "내보내는 중…"
                      : "TXT로 내보내기"}
                  </button>
                  <button
                    type="button"
                    disabled={exporting !== null || !canExport}
                    onClick={() => void runExport("combined", "markdown")}
                  >
                    {exporting?.kind === "combined" && exporting.format === "markdown"
                      ? "내보내는 중…"
                      : "Markdown으로 내보내기"}
                  </button>
                </div>
              </div>
              <div className="export-group">
                <p className="export-label">회차별 개별 파일 (ZIP)</p>
                <div className="export-buttons">
                  <button
                    type="button"
                    disabled={exporting !== null || !canExport}
                    onClick={() => void runExport("bundle", "txt")}
                  >
                    {exporting?.kind === "bundle" && exporting.format === "txt"
                      ? "묶는 중…"
                      : "TXT ZIP"}
                  </button>
                  <button
                    type="button"
                    disabled={exporting !== null || !canExport}
                    onClick={() => void runExport("bundle", "markdown")}
                  >
                    {exporting?.kind === "bundle" && exporting.format === "markdown"
                      ? "묶는 중…"
                      : "Markdown ZIP"}
                  </button>
                </div>
              </div>
              <p className="export-note">
                {canExport
                  ? includeArchived
                    ? "보관된 원고를 포함해 정본 순서대로 내보냅니다."
                    : "보관된 원고는 제외됩니다."
                  : "내보낼 원고가 없습니다. 보관된 원고만 있어요 — ‘보관된 원고 포함’을 켜세요."}
              </p>
            </section>
          )}
        </>
      )}
    </section>
  );
}
