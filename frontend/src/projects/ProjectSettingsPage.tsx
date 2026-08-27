import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ProjectOverview } from "./ProjectOverview";
import { ProjectExportPanel } from "./ProjectExportPanel";
import { ActivityTimelinePage } from "./ActivityTimelinePage";
import { describeApiError, getProject, type Project } from "../api/client";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    </section>
  );
}
