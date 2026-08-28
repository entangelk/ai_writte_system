import { useEffect, useRef, useState } from "react";
import JSZip from "jszip";
import {
  describeApiError,
  exportDraftVersion,
  exportProject,
  listChapters,
  type Chapter,
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
  chapterPosition: number | null,
  position: number | null,
  format: ExportFormat,
): string {
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, "_").trim();
  const stem = safeTitle === "" ? draftId : safeTitle;
  const prefix = [chapterPosition, position]
    .map((value) => String(value ?? 0).padStart(2, "0"))
    .join("-");
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

/**
 * 원고 내보내기 (오너 2026-08-27 — 작업 공간에서 설정 탭으로 이관).
 *
 * **작업 공간 첫 화면에서 뺀 것이 이 슬라이스의 요지다.** 원고를 쓰러 들어온
 * 화면 아래에 내보내기 버튼 네 개와 옵션 체크박스가 상시로 깔려 있었다 —
 * 자주 하는 일이 아닌데 자리는 늘 차지했다.
 *
 * **추적 정보(manifest) 옵션도 함께 없앴다**(오너: *"함께 내보내는 건 필요없을
 * 것 같다"*). 묶음(zip) 경로는 **여전히 manifest 를 읽는다** — 무엇이 포함되고
 * 어느 version 인지가 거기 있기 때문이다. 다만 그 파일을 사용자에게 주지
 * 않을 뿐이다. 그 둘을 같은 것으로 보고 manifest 요청까지 지우면 묶음이 무엇을
 * 담을지 알 수 없게 된다.
 */
export function ProjectExportPanel({ projectId }: { projectId: string }) {
  const [chapters, setChapters] = useState<Chapter[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [exporting, setExporting] = useState<
    { kind: ExportKind; format: ExportFormat } | null
  >(null);
  const exportingRef = useRef(false);

  useEffect(() => {
    let active = true;
    listChapters(projectId)
      .then((response) => {
        if (active) setChapters(response.chapters);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      });
    return () => { active = false; };
  }, [projectId]);

  async function runExport(kind: ExportKind, format: ExportFormat) {
    if (exportingRef.current) return;
    exportingRef.current = true;
    setExporting({ kind, format });
    try {
      if (kind === "combined") {
        const exported = await exportProject(projectId, format, {
          includeArchived,
          manifest: false,
        });
        triggerDownload(
          new Blob([exported.body], { type: exported.content_type }),
          exported.filename,
        );
      } else {
        // Bulk: enumerate the exact included units from the delivery manifest,
        // fetch each unit's latest version body verbatim (no heading synthesis),
        // and bundle them as one zip.
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
            bundleEntryName(
              unit.draft_id,
              unit.title,
              unit.chapter_position,
              unit.position,
              format,
            ),
            exported.body,
          );
        }
        const blob = await zip.generateAsync({ type: "blob" });
        triggerDownload(blob, `${projectId}.zip`);
      }
      setError(null);
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      exportingRef.current = false;
      setExporting(null);
    }
  }

  const canExport = chapters !== null && chapters.some((chapter) =>
    chapter.scenes.some((scene) =>
      includeArchived || (!chapter.archived && !scene.archived)
    )
  );
  const hasArchivedContent = chapters !== null && chapters.some((chapter) =>
    chapter.archived || chapter.scenes.some((scene) => scene.archived)
  );

  return (
    <section className="overview-section" aria-labelledby="export-heading">
      <div className="overview-heading">
        <div>
          <p className="eyebrow">전달본</p>
          <h2 id="export-heading">원고 내보내기</h2>
        </div>
      </div>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {chapters === null ? (
        <p className="status-copy">원고를 불러오는 중…</p>
      ) : chapters.every((chapter) => chapter.scenes.length === 0) ? (
        <div className="empty-state"><p>내보낼 원고가 없습니다.</p></div>
      ) : (
        <section className="export-controls" aria-label="원고 내보내기">
          {hasArchivedContent && (
            <div className="export-options">
              <label className="export-option">
                <input
                  type="checkbox"
                  checked={includeArchived}
                  disabled={exporting !== null}
                  onChange={(event) => setIncludeArchived(event.target.checked)}
                />
                보관된 원고 포함
              </label>
            </div>
          )}
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
    </section>
  );
}
