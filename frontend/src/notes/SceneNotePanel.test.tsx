/**
 * 편집기 드로어의 메모 패널 (Slice 4 — 브리프 D1=A, D4=A).
 *
 * 잠그는 계약:
 *
 * 1. **드로어와 별도 화면은 같은 검색·같은 목록을 쓴다**(완료 기준 1). 여기서는
 *    행이 링크가 아니라 선택 버튼이라는 것만 다르다.
 * 2. **편집 대상은 현재 Scene 이다**(D1=A "집필 맥락 보존"). 다른 장면을 고르면
 *    전문을 읽기 전용으로 보여 주고, 장면을 옮기면 편집 대상이 따라간다.
 * 3. **명시적 저장**(D4=A) — 요청 중 버튼을 잠그되 **같은 값 재저장은 막지 않는다.**
 *    오너가 "같은 값을 다시 저장해도 행을 남긴다"를 골랐으므로, 변경이 없다고
 *    버튼을 잠그면 그 결정이 화면에서 도달 불가가 된다(연타만 서버 창이 접는다).
 * 4. **쓰기가 막히는 축은 화면이 말한다** — 보관(409)과 grant 읽기 전용(403).
 *    소유자 여부는 payload 에 없으므로(2c 유예) 403 을 받은 뒤에 읽기 전용으로
 *    내려온다 — 원고 편집기의 `forcedReadOnly` 와 같은 선례다.
 * 5. **12000자 상한**(SoT v1.8.11)은 경고 + 저장 차단이지 잘라내기가 아니다.
 * 6. **"더 보기"는 목록의 것이므로 두 화면에 똑같이 있다**(완료 기준 1) — 그리고 그것을
 *    눌러도 **편집 대상은 바뀌지 않는다**: 행 제목(선택)과 "더 보기"(펼침)는 다른 일이다.
 * 7. **행 꼬리줄도 목록의 것이다** — 수정 시각이 여기에도 있어야 한다. 컴포넌트를
 *    공유한다는 사실은 잠금이 아니다(v1.8.37 B1 이 같은 종의 공백이었다).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SceneNotePanel } from "./SceneNotePanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

type Reply = { body: unknown; status?: number };

function response({ body, status = 200 }: Reply) {
  return { ok: status >= 200 && status < 300, status, statusText: "", json: async () => body };
}

const LIST = {
  notes: [
    {
      draft_id: "d1", scene_title: "첫눈", scene_archived: false,
      chapter_id: "c1", chapter_title: "1장 겨울", chapter_archived: false,
      body_preview: "난로 앞", truncated: false, updated_at: "2026-09-01T02:00:00Z",
    },
    {
      draft_id: "d2", scene_title: "두 번째 밤", scene_archived: false,
      chapter_id: "c1", chapter_title: "1장 겨울", chapter_archived: false,
      body_preview: "두 번째 메모", truncated: false, updated_at: "2026-09-01T03:00:00Z",
    },
  ],
};

/**
 * URL 로 응답을 고르는 stub. 순서 기반 mock 을 쓰지 않는 이유는 목록 GET 과 단건
 * GET 이 같은 커밋에서 나가 순서가 React 의 effect 순서에 달리기 때문이다 —
 * 그것은 이 화면의 계약이 아니다.
 */
function stubRoutes(routes: Array<[RegExp, Reply | ((init?: RequestInit) => Reply)]>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    for (const [pattern, reply] of routes) {
      if (pattern.test(url)) {
        return Promise.resolve(
          response(typeof reply === "function" ? reply(init) : reply),
        );
      }
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPanel(props: Partial<Parameters<typeof SceneNotePanel>[0]> = {}) {
  return render(
    <MemoryRouter>
      <SceneNotePanel projectId="p1" draftId="d1" tabActive {...props} />
    </MemoryRouter>,
  );
}

describe("메모 드로어 패널", () => {
  it("reads the same list contract as the notes screen and loads the current scene's note", async () => {
    const fetchMock = stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
    ]);

    renderPanel();

    // 값으로 기다린다 — 상자는 조회가 끝나기 전에 이미 그려져 있어서 라벨로
    // 기다리면 빈 상자에서도 곧바로 통과한다.
    expect(await screen.findByDisplayValue("현재 장면 메모")).toHaveAttribute(
      "id", "scene-note-body",
    );
    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls).toContain("/api/projects/p1/notes");
    expect(urls).toContain("/api/projects/p1/drafts/d1/note");
    // 목록은 미리보기만 읽는다 — 전문은 단건 GET 이 준다.
    expect(screen.getByText("두 번째 메모")).toBeInTheDocument();
  });

  it("stays quiet until its drawer tab is open", async () => {
    const fetchMock = stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: null, updated_at: null } }],
    ]);

    const view = renderPanel({ tabActive: false });
    expect(fetchMock).not.toHaveBeenCalled();

    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d1" tabActive />
      </MemoryRouter>,
    );

    expect(await screen.findByLabelText("이 장면 메모")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBeGreaterThan(0);
  });

  it("saves the exact body once and keeps the button locked while the request is in flight", async () => {
    let release: ((value: unknown) => void) | undefined;
    const pending = new Promise((resolve) => { release = resolve; });
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (/\/note$/.test(url) && init?.method === "PUT") return pending;
      if (/\/notes$/.test(url)) return Promise.resolve(response({ body: LIST }));
      return Promise.resolve(
        response({ body: { draft_id: "d1", body: "옛 메모", updated_at: null } }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    // 먼저 서버 값이 실렸는지 기다린다 — 조회가 늦게 끝나면 타이핑을 덮어쓴다.
    const editor = await screen.findByDisplayValue("옛 메모");
    await userEvent.clear(editor);
    await userEvent.type(editor, "새 메모");
    await userEvent.click(screen.getByRole("button", { name: "메모 저장" }));

    expect(screen.getByRole("button", { name: "저장 중…" })).toBeDisabled();

    release?.(response({ body: { draft_id: "d1", body: "새 메모", updated_at: "2026-09-06T00:00:00Z" } }));
    expect(await screen.findByText("메모를 저장했습니다.")).toBeInTheDocument();

    const put = fetchMock.mock.calls.find((call) => (call[1] as RequestInit)?.method === "PUT");
    expect(put?.[0]).toBe("/api/projects/p1/drafts/d1/note");
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ body: "새 메모" });
    expect(
      fetchMock.mock.calls.filter((call) => (call[1] as RequestInit)?.method === "PUT"),
    ).toHaveLength(1);
  });

  it("re-reads the list after a save so the preview stops contradicting the editor", async () => {
    const fetchMock = stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, { body: { draft_id: "d1", body: "옛 메모", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("옛 메모");
    const listCallsBefore = fetchMock.mock.calls.filter(
      (call) => String(call[0]).endsWith("/notes"),
    ).length;

    await userEvent.click(screen.getByRole("button", { name: "메모 저장" }));
    await screen.findByText("메모를 저장했습니다.");

    // 목록의 미리보기는 방금 저장한 본문에서 만들어진다 — 다시 읽지 않으면 같은
    // 화면 안에서 목록과 편집기가 서로 다른 본문을 말한다.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/notes")).length,
      ).toBe(listCallsBefore + 1),
    );
  });

  it("does not lock saving an unchanged body — the owner chose to count the act, not the value", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, { body: { draft_id: "d1", body: "그대로", updated_at: null } }],
    ]);

    renderPanel();

    await screen.findByLabelText("이 장면 메모");
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeEnabled();
  });

  it("shows another scene's note read-only and comes back to the current scene", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "다른 장면 전문", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByLabelText("이 장면 메모");

    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));

    expect(await screen.findByText("다른 장면 전문")).toBeInTheDocument();
    // 다른 장면은 읽기만 한다 — 편집 대상은 현재 Scene 하나다(D1=A).
    expect(screen.queryByLabelText("이 장면 메모")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "두 번째 밤 열기 →" })).toHaveAttribute(
      "href", "/projects/p1/drafts/d2",
    );
    // 선택 표시는 고른 행 하나뿐이다 — 목록이 무엇을 보여 주고 있는지의 유일한 단서다.
    expect(screen.getByRole("button", { name: "두 번째 밤" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "첫눈" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: "← 현재 장면 메모" }));
    expect(await screen.findByDisplayValue("현재 장면 메모")).toBeInTheDocument();
  });

  it("carries the row metadata into the drawer list too", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");

    // 실행 머신의 시간대에 기대 문자열이 달리므로 같은 변환을 기대값으로 쓴다.
    const rows = screen.getAllByRole("listitem");
    expect(
      within(rows[0]).getByText(
        `수정 ${new Date(LIST.notes[0].updated_at).toLocaleString("ko-KR")}`,
      ),
    ).toBeInTheDocument();
    expect(
      within(rows[1]).getByText(
        `수정 ${new Date(LIST.notes[1].updated_at).toLocaleString("ko-KR")}`,
      ),
    ).toBeInTheDocument();
  });

  /**
   * 오너 실사용 관측(2026-09-07): *"저장된 메모를 눌렀을 때 메모가 안 보였다."*
   * 읽기면이 `body: null`(메모 없음)과 `""`(빈 메모 저장됨)을 **둘 다 빈 문단**으로
   * 그려 화면이 아무 말도 안 했다. 편집면은 이미 그 둘을 가르고, **SoT v1.8.11 이
   * 그 구분을 계약으로 박아 뒀다.**
   */
  async function openOtherSceneWith(body: string | null) {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body, updated_at: null } }],
    ]);
    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));
  }

  it("says a scene has no memo instead of showing an empty panel", async () => {
    await openOtherSceneWith(null);

    expect(await screen.findByText("아직 메모가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("빈 메모가 저장돼 있습니다.")).not.toBeInTheDocument();
  });

  it("distinguishes a saved empty memo from having no memo", async () => {
    await openOtherSceneWith("");

    expect(await screen.findByText("빈 메모가 저장돼 있습니다.")).toBeInTheDocument();
    expect(screen.queryByText("아직 메모가 없습니다.")).not.toBeInTheDocument();
  });

  it("shows another scene's saved memo as body text, not as a status line", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "다른 장면 전문", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));

    // over-strict 방향: 내용이 있는 메모를 "없음/빈 메모" 문구로 바꾸면 안 된다.
    const shown = await screen.findByText("다른 장면 전문");
    expect(shown).toHaveClass("note-body");
    expect(screen.queryByText("아직 메모가 없습니다.")).not.toBeInTheDocument();
    expect(screen.queryByText("빈 메모가 저장돼 있습니다.")).not.toBeInTheDocument();
  });

  it("expands a cut preview in place without moving the editing target", async () => {
    stubRoutes([
      [/\/notes$/, {
        body: {
          notes: [
            { ...LIST.notes[0], truncated: false },
            { ...LIST.notes[1], truncated: true },
          ],
        },
      }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "두 번째 메모 그리고 잘려 있던 뒷부분", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");

    // 드로어의 목록도 같은 컴포넌트이므로 같은 자리가 있어야 한다(완료 기준 1).
    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));

    expect(await screen.findByText("두 번째 메모 그리고 잘려 있던 뒷부분")).toBeInTheDocument();
    // over-strict 방향: "더 보기"를 선택(`onSelect`)에 물리면 편집 대상이 d2 로
    // 옮겨 가 현재 장면의 편집 상자가 사라진다 — 그러면 여기서 걸린다.
    expect(screen.getByDisplayValue("현재 장면 메모")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "두 번째 밤" })).toHaveAttribute(
      "aria-pressed", "false",
    );
  });

  it("follows the editor to another scene", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "첫 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "두 번째 장면 메모", updated_at: null } }],
    ]);

    const view = renderPanel();
    expect(await screen.findByDisplayValue("첫 장면 메모")).toBeInTheDocument();

    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d2" tabActive />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByLabelText("이 장면 메모")).toHaveValue("두 번째 장면 메모"),
    );
  });

  it("returns to the new scene's note when the editor moves while another note is selected", async () => {
    // 변이 MN-8 이 찾은 빈 칸: 다른 장면을 고른 채 편집기가 장면을 옮기면, 선택을
    // 그대로 두는 순간 패널이 **옛 장면의 메모를 읽으면서 새 장면을 저장 대상으로**
    // 들고 있게 된다(D1=A "편집 대상은 현재 Scene" 위반).
    // ★ 고른 장면과 옮겨 간 장면이 **다른** 경우여야 한다 — d2 를 고른 채 d2 로
    // 옮기면 선택이 우연히 현재 장면과 같아져 초기화 없이도 통과한다(첫 시도의
    // 셀이 그 모양이라 변이를 못 물었다).
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "첫 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "두 번째 장면 메모", updated_at: null } }],
      [/\/drafts\/d3\/note$/, { body: { draft_id: "d3", body: "세 번째 장면 메모", updated_at: null } }],
    ]);

    const view = renderPanel();
    await screen.findByDisplayValue("첫 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));
    expect(await screen.findByText("두 번째 장면 메모")).toBeInTheDocument();

    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d3" tabActive />
      </MemoryRouter>,
    );

    expect(await screen.findByDisplayValue("세 번째 장면 메모")).toHaveAttribute(
      "id", "scene-note-body",
    );
    expect(screen.queryByText("두 번째 장면 메모")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "← 현재 장면 메모" })).not.toBeInTheDocument();
  });

  it("does not clobber unsaved note text when the tab is closed and reopened", async () => {
    const fetchMock = stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, { body: { draft_id: "d1", body: "서버 본문", updated_at: null } }],
    ]);

    const view = renderPanel();
    const editor = await screen.findByDisplayValue("서버 본문");
    await userEvent.type(editor, " + 아직 저장 안 한 글");
    const readsBefore = fetchMock.mock.calls.filter(
      (call) => String(call[0]).endsWith("/drafts/d1/note"),
    ).length;

    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d1" tabActive={false} />
      </MemoryRouter>,
    );
    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d1" tabActive />
      </MemoryRouter>,
    );

    // ★ 값만 보면 덮어쓰기 **전에** 통과한다(응답이 오기 전 첫 폴에서 초록).
    // 그래서 "다시 읽지 않았다"를 요청 수로 단정한다 — 이 화면이 미저장 글을
    // 지키는 방법이 곧 재조회를 하지 않는 것이다.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/notes")).length,
      ).toBeGreaterThan(1),
    );
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/drafts/d1/note")).length,
    ).toBe(readsBefore);
    expect(screen.getByLabelText("이 장면 메모")).toHaveValue("서버 본문 + 아직 저장 안 한 글");
  });

  it("keeps the selection while the drawer is closed and reopened", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "다른 장면 전문", updated_at: null } }],
    ]);

    const view = renderPanel();
    await screen.findByLabelText("이 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));
    expect(await screen.findByText("다른 장면 전문")).toBeInTheDocument();

    // 드로어가 닫혀도 패널은 마운트를 유지한다(레일 계약) — 다시 열었을 때
    // 고른 장면이 그대로여야 "닫았다 열면 처음으로 돌아가는" 결손이 없다.
    const closed = (
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d1" tabActive={false} />
      </MemoryRouter>
    );
    view.rerender(closed);
    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d1" tabActive />
      </MemoryRouter>,
    );

    expect(await screen.findByText("다른 장면 전문")).toBeInTheDocument();
    expect(screen.queryByLabelText("이 장면 메모")).not.toBeInTheDocument();
  });

  it("turns a refused write into a read-only surface instead of a dead button", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, (init) =>
        init?.method === "PUT"
          ? { body: { detail: "project access is read-only" }, status: 403 }
          : { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "메모 저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("project access is read-only");
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "메모 저장" })).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("이 장면 메모")).toHaveAttribute("readonly");
  });

  it("keeps an archived scene readable without offering a save", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, { body: { draft_id: "d1", body: "보관된 장면 메모", updated_at: null } }],
    ]);

    renderPanel({ readOnly: true });

    expect(await screen.findByLabelText("이 장면 메모")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "메모 저장" })).not.toBeInTheDocument();
  });

  it("blocks a body past the 12000 limit but leaves a body under it saveable", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, { body: { draft_id: "d1", body: "", updated_at: null } }],
    ]);

    renderPanel();
    const editor = await screen.findByLabelText("이 장면 메모");
    // 빈 메모라 기다릴 값이 없다 — 글자 수 줄로 조회 완료를 기다린다.
    await screen.findByText("0자");

    // over-strict 방향: 상한 아래에서는 잠그면 안 된다.
    await userEvent.type(editor, "짧은 메모");
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeEnabled();

    // 경계값: 정확히 상한이면 저장할 수 있다(off-by-one 과잉 교정 방어).
    await userEvent.clear(editor);
    await userEvent.paste("가".repeat(12_000));
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeEnabled();

    // 상한 아래에서는 초과 경고가 뜨면 안 된다(경고 축의 over-strict).
    expect(screen.getByRole("status").textContent).not.toContain("상한");

    await userEvent.clear(editor);
    await userEvent.paste("가".repeat(12_001));
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeDisabled();
    // SoT ⑧ 은 "경고 + 저장 차단" 둘을 함께 말한다 — 차단만 남기고 경고를 지우면
    // 사용자는 버튼이 왜 잠겼는지 모른 채 남는다(검증 변이 MV-C 가 연 자리).
    expect(screen.getByRole("status").textContent).toContain(
      `상한 ${(12_000).toLocaleString("ko-KR")}자 초과 — 저장할 수 없습니다`,
    );
    // ★ 잘라내기가 아니다 — 붙여넣은 본문은 그대로 남아 있어야 한다.
    expect(editor).toHaveValue("가".repeat(12_001));
    expect(editor).not.toHaveAttribute("maxlength");
  });

  it("says a scene has no note yet instead of showing an empty saved memo", async () => {
    stubRoutes([
      [/\/notes$/, { body: { notes: [] } }],
      [/\/note$/, { body: { draft_id: "d1", body: null, updated_at: null } }],
    ]);

    renderPanel();

    const editor = await screen.findByLabelText("이 장면 메모");
    expect(editor).toHaveValue("");
    expect(within(screen.getByRole("status")).getByText("아직 메모가 없습니다.")).toBeInTheDocument();
  });

  it("tells an empty saved memo apart from a scene with no memo row", async () => {
    // 계약(SoT v1.8.11)이 `body === null`(메모 없음)과 `body === ""`(빈 메모가
    // 저장됨)을 구분하므로 읽기면도 구분해야 한다. 둘 다 빈 상자로 보이지만
    // 상태 줄이 다른 사실을 말한다.
    stubRoutes([
      [/\/notes$/, { body: { notes: [] } }],
      [/\/note$/, { body: { draft_id: "d1", body: "", updated_at: "2026-09-06T00:00:00Z" } }],
    ]);

    renderPanel();

    const status = await screen.findByRole("status");
    await waitFor(() => expect(status).toHaveTextContent("0자"));
    expect(screen.queryByText("아직 메모가 없습니다.")).not.toBeInTheDocument();
  });
  it("hands the drawer's search box to the server too — the same contract as the notes screen", async () => {
    // 완료 기준 1: **두 화면이 같은 검색 결과를 읽는다.** 한 컴포넌트를 공유한다는
    // 사실은 구현이지 잠금이 아니다 — 드로어 쪽에서 제목으로 한 번 더 거르면 본문
    // 매치로 올라온 행이 **드로어에서만** 사라지는데(리터럴 ① 금지) 화면 셀은 그것을
    // 못 본다(독립 검증 변이 MV-A 가 연 자리).
    let listCall = 0;
    const fetchMock = vi.fn((url: string) => {
      // ★ `$` 로 끝을 묶으면 안 된다 — 검색 요청은 `/notes?query=…` 라 끝이 다르다.
      if (url.includes("/notes")) {
        listCall += 1;
        return Promise.resolve(response({
          body: listCall === 1
            ? LIST
            : { notes: [{ ...LIST.notes[1], body_preview: "…편지를 태우는…" }] },
        }));
      }
      return Promise.resolve(
        response({ body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");

    await userEvent.type(screen.getByLabelText("메모 검색"), "편지");
    await userEvent.click(screen.getByRole("button", { name: "검색" }));

    expect(await screen.findByText("…편지를 태우는…")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toContain(
      "/api/projects/p1/notes?query=%ED%8E%B8%EC%A7%80",
    );
    // over-strict: 제목에 검색어가 없고 **본문에만** 있는 행이 드로어에서 사라지면 안 된다.
    expect(screen.getByRole("button", { name: "두 번째 밤" })).toBeInTheDocument();
  });

  it("keeps the save button after a refusal that is not about permission", async () => {
    // 보관된 장·장면의 저장은 **409** 다(계약 Slice 2 의 archived 3축). 읽기 전용으로
    // 승격해야 하는 것은 403 하나뿐이고, 모든 오류를 승격하면 화면이 "grant 읽기
    // 전용"이라는 **틀린 이유**로 저장 버튼을 영구히 걷어낸다(변이 MV-B 가 연 자리).
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/note$/, (init) =>
        init?.method === "PUT"
          ? { body: { detail: "draft is archived" }, status: 409 }
          : { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
    ]);

    renderPanel();
    await screen.findByDisplayValue("현재 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "메모 저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("draft is archived");
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeInTheDocument();
    expect(screen.getByLabelText("이 장면 메모")).not.toHaveAttribute("readonly");
  });

  it("lets the editor guard cancel the link into another scene", async () => {
    // 이 링크는 편집기를 떠난다 — 원고에 미저장 편집이 있으면 편집기의 확인을
    // 거쳐야 한다(`WorkspaceReviewPanel`·`AnalysisTrigger` 와 같은 선례).
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "현재 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "다른 장면 전문", updated_at: null } }],
    ]);
    const onBeforeNavigateAway = vi.fn(() => false);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <SceneNotePanel
                projectId="p1"
                draftId="d1"
                tabActive
                onBeforeNavigateAway={onBeforeNavigateAway}
              />
            }
          />
          <Route path="/projects/:projectId/drafts/:draftId" element={<p>다른 장면 route</p>} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByDisplayValue("현재 장면 메모");
    await userEvent.click(screen.getByRole("button", { name: "두 번째 밤" }));
    await screen.findByText("다른 장면 전문");

    await userEvent.click(screen.getByRole("link", { name: "두 번째 밤 열기 →" }));

    expect(onBeforeNavigateAway).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("다른 장면 route")).toBeNull();
    expect(screen.getByRole("heading", { name: "메모" })).toBeInTheDocument();
  });
});
