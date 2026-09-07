import { useEffect, useState, type MouseEvent } from "react";
import { Link } from "react-router";
import {
  ApiError,
  describeApiError,
  getSceneNote,
  putSceneNote,
  type SceneNoteListItem,
} from "../api/client";
import { formatCharCount } from "../writing/tokenEstimate";
import { SceneNoteSearch } from "./SceneNoteSearch";

/**
 * 메모 본문 상한. 서버 `core_sot.service.SCENE_NOTE_MAX_CHARS`(오너 2026-08-31,
 * SoT v1.8.11)의 미러다 — 서버는 요청 모델의 `field_validator` 로 422 를 내고,
 * 여기의 경고·저장 차단은 그 거부를 만나기 전에 알려 주는 사전 안내다.
 * ★ 잘라내기로 시행하지 않는다(textarea `maxLength` 금지) — 붙여넣기가 몰래
 * 잘리면 사용자가 쓴 것이 소리 없이 사라진다. 원고 본문 상한과 같은 관례다.
 */
export const SCENE_NOTE_MAX_CHARS = 12000;

type Props = {
  projectId: string;
  draftId: string;
  /** 드로어 탭이 열려 있을 때만 조회한다(`WorkspaceReviewPanel` 선례). */
  tabActive?: boolean;
  /** 보관된 프로젝트·장·장면. 읽기는 열려 있고 쓰기만 막힌다. */
  readOnly?: boolean;
  onBeforeNavigateAway?: () => boolean;
};

/**
 * 편집기 드로어의 메모 탭(브리프 D1=A).
 *
 * **편집 대상은 현재 Scene 하나다** — 목록에서 다른 장면을 고르면 전문을 읽기
 * 전용으로 보여 주고, 편집기가 다른 장면으로 옮겨 가면 대상이 따라간다. 그래야
 * 집필 맥락을 잃지 않으면서 프로젝트 전체 메모를 뒤질 수 있다.
 *
 * **소유자 여부는 payload 에 없다**(2c 유예). 그래서 쓰기 권한은 미리 알 수 없고,
 * grant 읽기 전용은 PUT 이 403 을 준 뒤에야 드러난다 — 원고 편집기가 저장 409 를
 * 읽기 전용으로 바꾸는 것과 같은 선례를 따른다.
 */
export function SceneNotePanel({
  projectId, draftId, tabActive = true, readOnly = false, onBeforeNavigateAway,
}: Props) {
  const [selected, setSelected] = useState<SceneNoteListItem | null>(null);
  const [body, setBody] = useState("");
  /** 서버가 이 장면에 아직 메모 행이 없다고 답했는가(`body === null`). */
  const [missing, setMissing] = useState(false);
  /** 본문을 이미 읽어 둔 장면. 되돌아올 때 편집 중인 글자를 덮어쓰지 않는다. */
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [otherBody, setOtherBody] = useState<string | null>(null);
  /**
   * 고른 장면에 **메모 행이 없다**(`body === null`)는 뜻. `""`(빈 메모 저장됨)과
   * 구분해야 한다 — SoT v1.8.11 이 그 둘을 계약으로 가르고, 편집면은 이미 가른다.
   * 안 가르면 **둘 다 빈 문단이 되어 화면이 아무 말도 안 한다**(오너 실사용 관측
   * 2026-09-07: *"저장된 메모를 눌렀을 때 메모가 안 보였다"*).
   */
  const [otherMissing, setOtherMissing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forcedReadOnly, setForcedReadOnly] = useState(false);
  const [listRefresh, setListRefresh] = useState(0);

  const viewingCurrent = selected === null || selected.draft_id === draftId;
  const writable = !readOnly && !forcedReadOnly;
  const overLimit = [...body].length > SCENE_NOTE_MAX_CHARS;

  // 편집기가 다른 장면으로 옮겨 가면 편집 대상도 따라간다(D1=A).
  useEffect(() => {
    setSelected(null);
    setOtherBody(null);
    setOtherMissing(false);
    setNotice(null);
  }, [draftId]);

  useEffect(() => {
    if (!tabActive) return;
    let active = true;
    if (viewingCurrent) {
      if (loadedFor === draftId) return;
      void getSceneNote(projectId, draftId)
        .then((note) => {
          if (!active) return;
          setBody(note.body ?? "");
          setMissing(note.body === null);
          setLoadedFor(draftId);
          setError(null);
        })
        .catch((cause: unknown) => { if (active) setError(describeApiError(cause)); });
    } else {
      void getSceneNote(projectId, selected!.draft_id)
        .then((note) => {
          if (!active) return;
          setOtherBody(note.body ?? "");
          setOtherMissing(note.body === null);
          setError(null);
        })
        .catch((cause: unknown) => { if (active) setError(describeApiError(cause)); });
    }
    return () => { active = false; };
  }, [projectId, draftId, tabActive, viewingCurrent, selected, loadedFor]);

  async function save(): Promise<void> {
    if (saving || overLimit || !writable) return;
    setSaving(true);
    setNotice(null);
    try {
      const saved = await putSceneNote(projectId, draftId, body);
      setBody(saved.body ?? "");
      setMissing(false);
      setNotice("메모를 저장했습니다.");
      setError(null);
      // 목록의 미리보기는 방금 저장한 본문에서 만들어진다 — 갱신하지 않으면
      // 같은 화면 안에서 목록과 편집기가 서로 다른 본문을 말한다.
      setListRefresh((count) => count + 1);
    } catch (cause: unknown) {
      setError(describeApiError(cause));
      // 403 = grant 읽기 전용(이 화면이 미리 알 수 없는 유일한 이유).
      if (cause instanceof ApiError && cause.status === 403) setForcedReadOnly(true);
    } finally {
      setSaving(false);
    }
  }

  function guardNavigation(event: MouseEvent<HTMLAnchorElement>): void {
    if (onBeforeNavigateAway?.() === false) event.preventDefault();
  }

  return (
    <div className="scene-note-panel">
      <div className="rail-section-heading">
        <h2>메모</h2>
        <span>{viewingCurrent ? "이 장면" : selected?.scene_title}</span>
      </div>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      {viewingCurrent ? (
        <>
          <label className="rail-note-label" htmlFor="scene-note-body">이 장면 메모</label>
          <textarea
            id="scene-note-body"
            className="rail-note-editor"
            value={body}
            readOnly={!writable}
            spellCheck="true"
            placeholder="이 장면에 대한 메모를 남기세요. 메모는 원고에 섞이지 않습니다."
            onChange={(event) => {
              setBody(event.target.value);
              setNotice(null);
            }}
          />
          <p className="rail-note-status" role="status">
            {notice ?? (missing ? "아직 메모가 없습니다." : formatCharCount(body))}
            {overLimit && ` / 상한 ${SCENE_NOTE_MAX_CHARS.toLocaleString("ko-KR")}자 초과 — 저장할 수 없습니다`}
          </p>
          {writable && (
            <div className="row-actions rail-actions">
              <button type="button" disabled={saving || overLimit} onClick={() => void save()}>
                {saving ? "저장 중…" : "메모 저장"}
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <button className="rail-back" type="button" onClick={() => setSelected(null)}>
            ← 현재 장면 메모
          </button>
          {otherBody === null ? (
            <p className="status-copy">메모를 불러오는 중…</p>
          ) : otherMissing ? (
            <p className="status-copy">아직 메모가 없습니다.</p>
          ) : otherBody === "" ? (
            <p className="status-copy">빈 메모가 저장돼 있습니다.</p>
          ) : (
            <p className="note-body">{otherBody}</p>
          )}
          <Link
            className="section-link"
            to={`/projects/${projectId}/drafts/${selected!.draft_id}`}
            onClick={guardNavigation}
          >{selected!.scene_title} 열기 →</Link>
        </>
      )}

      <SceneNoteSearch
        projectId={projectId}
        active={tabActive}
        refreshKey={listRefresh}
        selectedDraftId={selected?.draft_id ?? draftId}
        onSelect={(note) => {
          setOtherBody(null);
          setOtherMissing(false);
          setSelected(note.draft_id === draftId ? null : note);
        }}
      />
    </div>
  );
}
