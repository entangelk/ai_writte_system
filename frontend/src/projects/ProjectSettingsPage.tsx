import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ProjectOverview } from "./ProjectOverview";
import { ProjectExportPanel } from "./ProjectExportPanel";
import { ActivityTimelinePage } from "./ActivityTimelinePage";
import {
  archiveProject,
  describeApiError,
  getProject,
  purgeProject,
  type Project,
} from "../api/client";

const TABS = [
  { id: "brief", label: "작품 정보·개요" },
  { id: "export", label: "원고 내보내기" },
  { id: "activity", label: "활동 타임라인" },
] as const;

type TabId = (typeof TABS)[number]["id"];

/**
 * 프로젝트 설정 `/projects/:projectId/settings` (오너 2026-08-27).
 *
 * **작업 공간 첫 화면을 비우려고 만든 자리다.** 종전에는 원고 목록 위에 "작품
 * 정보·개요 / 검토함 / 활동 타임라인" 링크가 나란히 있고 목록 아래에는 내보내기
 * 버튼 네 개가 상시로 깔려 있었다 — 오너 표현으로 *"너무 어지럽다"*. 자주 하지
 * 않는 일을 한자리에 모아 그 화면에서 뺀다.
 *
 * **검토함은 여기 들어오지 않는다**(오너 결정): 집필 중 수시로 드나드는 작업
 * 흐름이라 설정이 아니고, 편집기 드로어에도 같은 이름의 탭이 있다.
 *
 * 탭 상태는 `?tab=` 이다 — 관리자가 보낸 링크나 새로고침이 같은 탭으로 열려야
 * 하고, 세 화면이 각자 제 데이터를 읽으므로 되돌아왔을 때 다시 읽는 편이 맞다.
 */
export function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 프로젝트 삭제(2026-08-28 오너 결정) — 이름 확인 가드. 관리 콘솔의 purge 면과
  // 같은 패턴이다: 이 버튼은 영구 파기(원고·버전·기억·활동 전부)를 부른다.
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const requested = searchParams.get("tab");
  const activeTab: TabId = TABS.some((tab) => tab.id === requested)
    ? (requested as TabId)
    : "brief";

  useEffect(() => {
    if (projectId === undefined) return;
    let active = true;
    getProject(projectId)
      .then((next) => {
        if (active) setProject(next);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      });
    return () => { active = false; };
  }, [projectId]);

  if (projectId === undefined) {
    return (
      <section className="workspace-page page-enter">
        <p className="alert" role="alert">프로젝트 경로가 올바르지 않습니다.</p>
      </section>
    );
  }

  async function deleteProject() {
    if (projectId === undefined || project === null || deleteBusy
        || confirmation !== project.name) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      // 보관(soft)이 먼저다 — purge 는 보관된 프로젝트만 받는다(2단계 강제).
      // 사유는 파기 감사 원장에 남는다. 이름 확인이 진짜 가드이므로 화면은
      // 사유를 따로 묻지 않는다(오너 2026-08-28 지시).
      if (!project.archived) {
        await archiveProject(projectId);
      }
      await purgeProject(projectId, "설정 탭에서 소유자 삭제");
      navigate("/");
    } catch (cause: unknown) {
      setDeleteError(describeApiError(cause));
      setDeleteBusy(false);
    }
  }

  return (
    <section className="workspace-page overview-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>← 원고 작업 공간</Link>

      <header className="page-heading project-heading">
        <p className="eyebrow">프로젝트 설정</p>
        <h1>{project?.name ?? "프로젝트"}</h1>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      <nav className="settings-tabs" role="tablist" aria-label="프로젝트 설정 탭">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setSearchParams({ tab: tab.id }, { replace: true })}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "brief" && <ProjectOverview />}
      {activeTab === "export" && <ProjectExportPanel projectId={projectId} />}
      {activeTab === "activity" && <ActivityTimelinePage />}

      {/* 프로젝트 삭제(2026-08-28) — 설정의 마지막 자리. 되돌릴 수 없는 일은
          자주 하는 일과 같은 눈높이에 두지 않는다(관리 콘솔 purge 면과 같은
          이름 확인 가드). */}
      <section className="hub-section project-delete-section">
        <h2 className="section-title">프로젝트 삭제</h2>
        <p className="status-copy">
          프로젝트와 모든 원고·버전·기억·활동 기록이 영구히 사라집니다. 되돌릴 수
          없습니다.
        </p>
        {deleteError !== null && (
          <p className="alert" role="alert">{deleteError}</p>
        )}
        {!deleteOpen ? (
          <button type="button" onClick={() => setDeleteOpen(true)}>
            프로젝트 삭제…
          </button>
        ) : (
          <div className="confirm-panel">
            <label htmlFor="project-delete-confirmation">
              삭제를 원하면 프로젝트 이름 <strong>{project?.name ?? ""}</strong> 을(를)
              입력하세요
            </label>
            <input
              id="project-delete-confirmation"
              value={confirmation}
              autoComplete="off"
              disabled={deleteBusy}
              onChange={(event) => setConfirmation(event.target.value)}
            />
            <div className="confirm-actions">
              <button
                type="button"
                className="danger-button"
                disabled={deleteBusy || confirmation !== (project?.name ?? "")}
                onClick={() => void deleteProject()}
              >
                {deleteBusy ? "삭제 중…" : "영구 삭제"}
              </button>
              <button
                type="button"
                disabled={deleteBusy}
                onClick={() => {
                  setDeleteOpen(false);
                  setConfirmation("");
                  setDeleteError(null);
                }}
              >
                취소
              </button>
            </div>
          </div>
        )}
      </section>
    </section>
  );
}
