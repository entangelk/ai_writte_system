import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ApiError, archiveChapter, archiveDraft, createChapter, createDraft,
  describeApiError, getProject, listChapters, purgeChapter, purgeDraft,
  putChapterOrder, putSceneOrder,
  type Chapter, type Draft, type Project,
} from "../api/client";

export function DraftList() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [chapters, setChapters] = useState<Chapter[] | null>(null);
  const [chapterTitle, setChapterTitle] = useState("");
  const [sceneTitles, setSceneTitles] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [scenePurgeTarget, setScenePurgeTarget] = useState<Draft | null>(null);
  const [scenePurgeChecked, setScenePurgeChecked] = useState(false);
  const [chapterPurgeTarget, setChapterPurgeTarget] = useState<Chapter | null>(null);
  const [chapterConfirmTitle, setChapterConfirmTitle] = useState("");
  const [purgeBusy, setPurgeBusy] = useState(false);
  const [purgeError, setPurgeError] = useState<string | null>(null);

  const loadChapters = useCallback(async () => {
    if (projectId !== undefined) {
      setChapters((await listChapters(projectId)).chapters);
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    void Promise.all([getProject(projectId), listChapters(projectId)])
      .then(([nextProject, response]) => {
        if (!active) return;
        setProject(nextProject);
        setChapters(response.chapters);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [projectId]);

  async function addChapter(event: React.FormEvent) {
    event.preventDefault();
    const title = chapterTitle.trim();
    if (projectId === undefined || title === "" || saving || project?.archived) return;
    setSaving(true);
    try {
      await createChapter(projectId, { title });
      setChapterTitle("");
      await loadChapters();
      setError(null);
    } catch (cause: unknown) {
      setError(describeApiError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function addScene(chapter: Chapter, event: React.FormEvent) {
    event.preventDefault();
    const title = (sceneTitles[chapter.id] ?? "").trim();
    if (projectId === undefined || title === "" || saving || chapter.archived) return;
    setSaving(true);
    try {
      await createDraft(projectId, { title, chapter_id: chapter.id });
      setSceneTitles((current) => ({ ...current, [chapter.id]: "" }));
      await loadChapters();
      setError(null);
    } catch (cause: unknown) {
      setError(describeApiError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function moveChapter(index: number, offset: -1 | 1) {
    if (projectId === undefined || chapters === null || saving) return;
    const target = index + offset;
    if (target < 0 || target >= chapters.length) return;
    const reordered = [...chapters];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    setSaving(true);
    try {
      setChapters((await putChapterOrder(projectId, {
        ordered_chapter_ids: reordered.map((chapter) => chapter.id),
      })).chapters);
      setError(null);
    } catch (cause: unknown) {
      setError(describeApiError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function moveScene(chapter: Chapter, index: number, offset: -1 | 1) {
    if (projectId === undefined || saving) return;
    const target = index + offset;
    if (target < 0 || target >= chapter.scenes.length) return;
    const reordered = [...chapter.scenes];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    setSaving(true);
    try {
      const response = await putSceneOrder(projectId, chapter.id, {
        ordered_draft_ids: reordered.map((scene) => scene.id),
      });
      setChapters((current) => current?.map((item) =>
        item.id === chapter.id ? { ...item, scenes: response.scenes } : item
      ) ?? null);
      setError(null);
    } catch (cause: unknown) {
      setError(describeApiError(cause));
    } finally {
      setSaving(false);
    }
  }

  async function deleteScene(scene: Draft) {
    if (projectId === undefined || purgeBusy || !scenePurgeChecked) return;
    setPurgeBusy(true);
    setPurgeError(null);
    try {
      if (!scene.archived) await archiveDraft(projectId, scene.id);
      await purgeDraft(projectId, scene.id);
      setScenePurgeTarget(null);
      setScenePurgeChecked(false);
      await loadChapters();
    } catch (cause: unknown) {
      setPurgeError(describeApiError(cause));
    } finally {
      setPurgeBusy(false);
    }
  }

  async function deleteChapter(chapter: Chapter) {
    if (projectId === undefined || purgeBusy || chapterConfirmTitle !== chapter.title) return;
    setPurgeBusy(true);
    setPurgeError(null);
    try {
      if (!chapter.archived) await archiveChapter(projectId, chapter.id);
      await purgeChapter(projectId, chapter.id);
      setChapterPurgeTarget(null);
      setChapterConfirmTitle("");
      await loadChapters();
    } catch (cause: unknown) {
      setPurgeError(cause instanceof ApiError && cause.status === 503
        ? "삭제 결과를 확정할 수 없습니다. 목록을 새로 확인한 뒤 다시 시도하세요."
        : describeApiError(cause));
    } finally {
      setPurgeBusy(false);
    }
  }

  return <section className="workspace-page page-enter">
    <Link className="back-link" to="/">← 프로젝트로 돌아가기</Link>
    <header className="page-heading project-heading">
      <p className="eyebrow">원고 작업 공간</p>
      <h1>{project?.name ?? "프로젝트"}</h1>
      <p>장은 장면의 집합입니다. 장과 장면의 순서를 각각 관리합니다.</p>
      {projectId !== undefined && <div className="section-links">
        <Link className="section-link" to={`/projects/${projectId}/review`}>검토함 →</Link>
        <Link className="section-link" to={`/projects/${projectId}/settings`}>프로젝트 설정 →</Link>
      </div>}
    </header>

    {error !== null && <p className="alert" role="alert">{error}</p>}
    {loading ? <p className="status-copy">원고를 불러오는 중…</p>
      : project === null || chapters === null ? null : <>
        {!project.archived && <form className="creation-form" onSubmit={addChapter}>
          <div className="form-copy">
            <label htmlFor="chapter-title">새 장 제목</label>
            <span>장을 만든 뒤 그 안에 장면을 추가하세요.</span>
          </div>
          <div className="form-controls">
            <input id="chapter-title" value={chapterTitle}
              onChange={(event) => setChapterTitle(event.target.value)}
              autoComplete="off" placeholder="예: 1장 — 첫눈" />
            <button type="submit" disabled={saving || chapterTitle.trim() === ""}>장 만들기</button>
          </div>
        </form>}

        {scenePurgeTarget !== null && <div className="confirm-panel" role="alertdialog" aria-label="장면 삭제 확인">
          <p><strong>{scenePurgeTarget.title}</strong>과 모든 버전·생성 기록이 영구히 사라집니다.</p>
          {purgeError !== null && <p className="alert" role="alert">{purgeError}</p>}
          <label className="confirm-check"><input type="checkbox" checked={scenePurgeChecked}
            disabled={purgeBusy} onChange={(event) => setScenePurgeChecked(event.target.checked)} />삭제하겠습니다</label>
          <div className="confirm-actions">
            <button type="button" className="danger-button" disabled={purgeBusy || !scenePurgeChecked}
              onClick={() => void deleteScene(scenePurgeTarget)}>영구 삭제</button>
            <button type="button" disabled={purgeBusy} onClick={() => { setScenePurgeTarget(null); setPurgeError(null); }}>취소</button>
          </div>
        </div>}

        {chapterPurgeTarget !== null && <div className="confirm-panel" role="alertdialog" aria-label="장 삭제 확인">
          <p><strong>{chapterPurgeTarget.title}</strong>과 그 안의 모든 장면·버전·생성 기록이 영구히 사라집니다.</p>
          <label htmlFor="chapter-confirm-title">확인을 위해 장 제목을 정확히 입력하세요.</label>
          <input id="chapter-confirm-title" value={chapterConfirmTitle}
            onChange={(event) => setChapterConfirmTitle(event.target.value)} />
          {purgeError !== null && <p className="alert" role="alert">{purgeError}</p>}
          <div className="confirm-actions">
            <button type="button" className="danger-button"
              disabled={purgeBusy || chapterConfirmTitle !== chapterPurgeTarget.title}
              onClick={() => void deleteChapter(chapterPurgeTarget)}>장과 장면 영구 삭제</button>
            <button type="button" disabled={purgeBusy} onClick={() => { setChapterPurgeTarget(null); setChapterConfirmTitle(""); setPurgeError(null); }}>취소</button>
          </div>
        </div>}

        {chapters.length === 0 ? <div className="empty-state"><p>아직 장이 없습니다.</p><span>첫 장을 만들어 작품을 시작하세요.</span></div>
          : <ol className="resource-list chapter-list" aria-label="장 목록">
            {chapters.map((chapter, chapterIndex) => <li className="chapter-group" key={chapter.id}>
              <div className="resource-row chapter-row">
                <strong>{chapter.title}</strong>
                <span className="status-badge">장 순서 {chapter.position}</span>
                {chapter.archived && <span className="status-badge">보관됨</span>}
                <span className="order-controls">
                  {!project.archived && <>
                    <button type="button" aria-label={`${chapter.title} 위로`} disabled={saving || chapterIndex === 0} onClick={() => void moveChapter(chapterIndex, -1)}>↑</button>
                    <button type="button" aria-label={`${chapter.title} 아래로`} disabled={saving || chapterIndex === chapters.length - 1} onClick={() => void moveChapter(chapterIndex, 1)}>↓</button>
                  </>}
                  <button type="button" className="danger-button" aria-label={`${chapter.title} 삭제`}
                    disabled={saving || purgeBusy} onClick={() => { setChapterPurgeTarget(chapter); setChapterConfirmTitle(""); setPurgeError(null); }}>장 삭제</button>
                </span>
              </div>
              {!project.archived && !chapter.archived && <form className="scene-creation-form" onSubmit={(event) => void addScene(chapter, event)}>
                <label htmlFor={`scene-title-${chapter.id}`}>새 장면</label>
                <input id={`scene-title-${chapter.id}`} value={sceneTitles[chapter.id] ?? ""}
                  onChange={(event) => setSceneTitles((current) => ({ ...current, [chapter.id]: event.target.value }))}
                  placeholder="장면 제목" />
                <button type="submit" disabled={saving || (sceneTitles[chapter.id] ?? "").trim() === ""}>장면 만들기</button>
              </form>}
              {chapter.scenes.length === 0 ? <p className="status-copy">아직 장면이 없습니다.</p>
                : <ol className="resource-list scene-list" aria-label={`${chapter.title} 장면 목록`}>
                  {chapter.scenes.map((scene, sceneIndex) => <li className="resource-row draft-row" key={scene.id}>
                    <Link aria-label={scene.title} className="resource-link" to={`/projects/${projectId}/drafts/${scene.id}`}>
                      <span>{scene.title}</span><span className="row-arrow" aria-hidden="true">→</span>
                    </Link>
                    <span className="status-badge">장면 순서 {scene.position}</span>
                    {scene.archived && <span className="status-badge">보관됨</span>}
                    <span className="order-controls">
                      {!project.archived && !chapter.archived && <>
                        <button type="button" aria-label={`${scene.title} 위로`} disabled={saving || sceneIndex === 0} onClick={() => void moveScene(chapter, sceneIndex, -1)}>↑</button>
                        <button type="button" aria-label={`${scene.title} 아래로`} disabled={saving || sceneIndex === chapter.scenes.length - 1} onClick={() => void moveScene(chapter, sceneIndex, 1)}>↓</button>
                      </>}
                      <button type="button" className="danger-button" aria-label={`${scene.title} 삭제`} disabled={saving || purgeBusy}
                        onClick={() => { setScenePurgeTarget(scene); setScenePurgeChecked(false); setPurgeError(null); }}>삭제</button>
                    </span>
                  </li>)}
                </ol>}
            </li>)}
          </ol>}
      </>}
  </section>;
}
