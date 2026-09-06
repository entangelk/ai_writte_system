import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import {
  describeApiError,
  listSceneNotes,
  type SceneNoteListItem,
} from "../api/client";

type Props = {
  projectId: string;
  /**
   * 드로어가 쓰는 자리 — 주면 행이 **선택 버튼**이 되고, 없으면 행은 그 장면의
   * 편집기로 가는 **링크**다(별도 화면). 두 화면이 같은 검색·같은 목록을 쓰되
   * 행이 하는 일만 다르다(브리프 D1=C+A).
   */
  onSelect?: (note: SceneNoteListItem) => void;
  /** 선택 표시. `onSelect` 가 있을 때만 의미가 있다. */
  selectedDraftId?: string | null;
  /** 드로어 탭이 닫혀 있으면 조회하지 않는다(`WorkspaceReviewPanel` 선례). */
  active?: boolean;
  /** 저장 뒤 목록의 미리보기를 갱신시키는 신호. */
  refreshKey?: number;
};

/**
 * 장면 메모 검색 + 목록. 별도 화면(Slice 3)과 편집기 드로어(Slice 4)가 이 한
 * 컴포넌트를 공유한다 — 목록·검색이 갈리면 "같은 검색 결과를 본다"는 완료 기준
 * 1이 화면마다 다른 사실을 말하게 된다.
 *
 * **검색은 서버가 한다.** 화면은 입력을 `?query=` 로 넘기고 받은 목록을 그대로
 * 그린다. 브라우저에서 다시 거르면 본문에서 매치돼 올라온 행이 제목 필터에 걸려
 * 사라진다(서버는 매치 중심 스니펫까지 만들어 준다).
 */
export function SceneNoteSearch({
  projectId, onSelect, selectedDraftId = null, active = true, refreshKey = 0,
}: Props) {
  const [notes, setNotes] = useState<SceneNoteListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  /** 마지막으로 **서버가 적용한** 검색어. 입력 중인 글자가 아니다. */
  const [appliedQuery, setAppliedQuery] = useState("");

  const load = useCallback(
    async (query: string) => {
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
    if (!active) return;
    void load(appliedQuery);
    // appliedQuery 는 의존성이 아니다 — 검색은 제출로만 다시 나간다(입력 중 매
    // 글자 요청을 보내지 않는다). 갱신 신호는 refreshKey 이고, 그때는 **마지막
    // 검색어를 유지한 채** 다시 읽는다(저장 뒤 목록이 전체로 튀지 않게).
  }, [load, active, refreshKey]);

  return (
    <div className="note-search">
      <form
        className="note-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          void load(input);
        }}
      >
        <label htmlFor="note-search-input">메모 검색</label>
        {/* 입력과 버튼은 `.form-controls` 를 그대로 쓴다 — 기본 동작 버튼의
            겉모습을 정하는 자리는 하나여야 하고(buttonAppearance.test.ts),
            새 자리를 만들면 세 규칙(base·hover·disabled)에 모두 등재해야 한다. */}
        <div className="form-controls">
          <input
            id="note-search-input"
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
                {onSelect === undefined ? (
                  <Link
                    aria-label={note.scene_title}
                    className="resource-link"
                    to={`/projects/${projectId}/drafts/${note.draft_id}`}
                  >
                    <span>{note.scene_title}</span>
                    <span className="row-arrow" aria-hidden="true">→</span>
                  </Link>
                ) : (
                  <button
                    type="button"
                    className="note-select"
                    aria-pressed={selectedDraftId === note.draft_id}
                    onClick={() => onSelect(note)}
                  >
                    {note.scene_title}
                  </button>
                )}
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
    </div>
  );
}
