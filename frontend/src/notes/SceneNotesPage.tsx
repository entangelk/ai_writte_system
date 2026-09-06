import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  describeApiError,
  listSceneNotes,
  type SceneNoteListItem,
} from "../api/client";

/**
 * 프로젝트의 모든 장면 메모를 한 화면에서 찾는 정문(브리프 D1=C).
 *
 * **검색은 서버가 한다**(Slice 1 확정). 화면은 입력을 `?query=` 로 넘기고 받은
 * 목록을 그대로 그린다 — 브라우저에서 다시 거르면 서버의 매치 중심 스니펫과
 * 화면의 행 집합이 서로 다른 사실을 말하게 된다(본문에서 잡힌 행이 제목 필터에
 * 걸려 사라진다).
 *
 * 목록은 미리보기만 싣는다. 전문은 편집기 드로어(Slice 4)의 단건 GET 이 준다.
 */
export function SceneNotesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [notes, setNotes] = useState<SceneNoteListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  /** 마지막으로 **서버가 적용한** 검색어. 입력 중인 글자가 아니다. */
  const [appliedQuery, setAppliedQuery] = useState("");

  const load = useCallback(
    async (query: string) => {
      if (projectId === undefined) {
        setError("프로젝트 경로가 올바르지 않습니다.");
        return;
      }
      try {
        const result = await listSceneNotes(projectId, query);
        setNotes(result);
        setAppliedQuery(query.trim());
        setError(null);
      } catch (cause: unknown) {
        // 실패한 검색이 이미 떠 있는 목록을 지우지 않는다 — 지우면 사용자는
        // "그 검색어에 결과가 없다"로 읽는다.
        setError(describeApiError(cause));
      }
    },
    [projectId],
  );

  useEffect(() => {
    void load("");
  }, [load]);

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>← 원고 작업 공간</Link>
      <header className="page-heading">
        <p className="eyebrow">장면 메모</p>
        <h1>메모</h1>
        <p>장면마다 남긴 메모를 한곳에서 찾습니다. 메모는 원고 본문·버전·내보내기에 섞이지 않습니다.</p>
      </header>

      <form
        className="creation-form"
        onSubmit={(event) => {
          event.preventDefault();
          void load(input);
        }}
      >
        <div className="form-copy">
          <label htmlFor="note-search">메모 검색</label>
          <span>장면 제목과 메모 본문에서 찾습니다. 비우고 검색하면 전체를 봅니다.</span>
        </div>
        <div className="form-controls">
          <input
            id="note-search"
            type="search"
            value={input}
            placeholder="찾을 말"
            onChange={(event) => setInput(event.target.value)}
          />
          <button type="submit">검색</button>
        </div>
      </form>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {notes === null && error === null && (
        <p className="status-copy">메모를 불러오는 중…</p>
      )}
      {notes !== null && notes.length === 0 && (
        <div className="empty-state">
          <p>
            {appliedQuery === ""
              ? "아직 저장된 메모가 없습니다."
              : "검색과 일치하는 메모가 없습니다."}
          </p>
        </div>
      )}
      {notes !== null && notes.length > 0 && (
        <ul className="resource-list note-list" aria-label="장면 메모 목록">
          {notes.map((note) => (
            <li className="resource-row note-row" key={note.draft_id}>
              <div className="note-row-heading">
                <Link
                  aria-label={note.scene_title}
                  className="resource-link"
                  to={`/projects/${projectId}/drafts/${note.draft_id}`}
                >
                  <span>{note.scene_title}</span>
                  <span className="row-arrow" aria-hidden="true">→</span>
                </Link>
                <span className="status-badge">{note.chapter_title}</span>
                {/* 보관은 두 축이고 쓰기는 둘 다에서 막힌다 — 한 축만 보이면
                    화면이 "읽기 전용"의 이유를 잘못 말한다. */}
                {note.scene_archived && <span className="status-badge">장면 보관됨</span>}
                {note.chapter_archived && <span className="status-badge">장 보관됨</span>}
              </div>
              <p className="note-preview">{note.body_preview}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
