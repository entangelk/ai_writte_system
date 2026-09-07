import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import {
  describeApiError,
  getSceneNote,
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
  /** "더 보기"로 펼친 행. 한 번에 하나다. */
  const [expandedId, setExpandedId] = useState<string | null>(null);
  /** 펼친 행의 전문. `null` 은 단건 GET 이 아직 안 돌아왔다는 뜻이다. */
  const [expandedBody, setExpandedBody] = useState<string | null>(null);

  const load = useCallback(
    async (query: string) => {
      try {
        const result = await listSceneNotes(projectId, query);
        setNotes(result);
        setAppliedQuery(query.trim());
        // 목록이 새로 오면 펼침을 접는다 — 저장 뒤 갱신(`refreshKey`)에서 펼친
        // 전문만 옛 본문으로 남으면 같은 행의 미리보기와 다른 사실을 말한다.
        setExpandedId(null);
        setExpandedBody(null);
        setError(null);
      } catch (cause: unknown) {
        // 실패한 검색이 이미 떠 있는 목록을 지우지 않는다 — 지우면 사용자는
        // "그 검색어에 결과가 없다"로 읽는다.
        setError(describeApiError(cause));
      }
    },
    [projectId],
  );

  /**
   * "더 보기" — 전문은 **단건 GET 이** 준다. 목록 행이 전문을 싣지 않는 것은
   * 계약이다(12000자 × 장면 수). 그래서 펼치는 것은 새 요청 하나다.
   */
  async function expand(note: SceneNoteListItem): Promise<void> {
    setExpandedId(note.draft_id);
    setExpandedBody(null);
    try {
      const full = await getSceneNote(projectId, note.draft_id);
      setExpandedBody(full.body ?? "");
      setError(null);
    } catch (cause: unknown) {
      // 전문을 못 읽었다고 미리보기를 걷어내지 않는다 — 걷어내면 사용자는 메모가
      // 사라진 것으로 읽는다.
      setExpandedId(null);
      setError(describeApiError(cause));
    }
  }

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
              {/* 펼친 행만 전문을 싣는다. 나머지는 서버가 만든 미리보기(200자,
                  검색어가 잡히면 매치 중심 스니펫)를 그대로 보여 준다. */}
              <p className="note-preview">
                {expandedId === note.draft_id && expandedBody !== null
                  ? expandedBody
                  : note.body_preview}
              </p>
              <div className="note-row-meta">
                <time dateTime={note.updated_at}>
                  수정 {new Date(note.updated_at).toLocaleString("ko-KR")}
                </time>
                {/* `truncated` 는 본문이 미리보기보다 길다는 서버의 신호다. 거짓인
                    행에서는 미리보기가 이미 전문이라 펼칠 것이 없다. */}
                {note.truncated && (
                  expandedId === note.draft_id ? (
                    <button
                      type="button"
                      className="note-expand"
                      disabled={expandedBody === null}
                      onClick={() => { setExpandedId(null); setExpandedBody(null); }}
                    >
                      {expandedBody === null ? "불러오는 중…" : "접기"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="note-expand"
                      onClick={() => void expand(note)}
                    >
                      더 보기
                    </button>
                  )
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
