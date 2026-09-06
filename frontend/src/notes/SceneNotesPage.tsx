import { Link, useParams } from "react-router";
import { SceneNoteSearch } from "./SceneNoteSearch";

/**
 * 프로젝트의 모든 장면 메모를 한 화면에서 찾는 정문(브리프 D1=C).
 *
 * 검색·목록은 [`SceneNoteSearch`](./SceneNoteSearch.tsx) 한 벌이고 편집기 드로어
 * (Slice 4)가 같은 것을 쓴다 — 여기서 행은 그 장면의 편집기로 가는 링크다.
 * 목록은 미리보기만 싣는다(전문은 단건 GET 몫).
 */
export function SceneNotesPage() {
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>← 원고 작업 공간</Link>
      <header className="page-heading">
        <p className="eyebrow">장면 메모</p>
        <h1>메모</h1>
        <p>장면마다 남긴 메모를 한곳에서 찾습니다. 메모는 원고 본문·버전·내보내기에 섞이지 않습니다.</p>
      </header>

      {projectId === undefined ? (
        <p className="alert" role="alert">프로젝트 경로가 올바르지 않습니다.</p>
      ) : (
        <SceneNoteSearch projectId={projectId} />
      )}
    </section>
  );
}
