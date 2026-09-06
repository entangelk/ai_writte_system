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
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
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

    expect(await screen.findByLabelText("이 장면 메모")).toHaveValue("현재 장면 메모");
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
    const editor = await screen.findByLabelText("이 장면 메모");
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

    await userEvent.click(screen.getByRole("button", { name: "← 현재 장면 메모" }));
    expect(await screen.findByLabelText("이 장면 메모")).toHaveValue("현재 장면 메모");
  });

  it("follows the editor to another scene", async () => {
    stubRoutes([
      [/\/notes$/, { body: LIST }],
      [/\/drafts\/d1\/note$/, { body: { draft_id: "d1", body: "첫 장면 메모", updated_at: null } }],
      [/\/drafts\/d2\/note$/, { body: { draft_id: "d2", body: "두 번째 장면 메모", updated_at: null } }],
    ]);

    const view = renderPanel();
    expect(await screen.findByLabelText("이 장면 메모")).toHaveValue("첫 장면 메모");

    view.rerender(
      <MemoryRouter>
        <SceneNotePanel projectId="p1" draftId="d2" tabActive />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByLabelText("이 장면 메모")).toHaveValue("두 번째 장면 메모"),
    );
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
    await screen.findByLabelText("이 장면 메모");
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

    // over-strict 방향: 상한 아래에서는 잠그면 안 된다.
    await userEvent.type(editor, "짧은 메모");
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeEnabled();

    await userEvent.clear(editor);
    await userEvent.paste("가".repeat(12_001));
    expect(screen.getByRole("button", { name: "메모 저장" })).toBeDisabled();
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
});
