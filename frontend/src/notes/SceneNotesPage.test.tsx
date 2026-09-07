/**
 * 장면 메모 화면 (Slice 3 — 브리프 D1=C 의 "정문").
 *
 * 이 화면이 잠그는 계약 넷:
 *
 * 1. **검색은 서버가 한다**(Slice 1 확정) — 입력을 `?query=` 로 넘기고, 화면은
 *    받은 목록을 그대로 그린다. 클라이언트가 다시 거르면 서버의 매치 중심
 *    스니펫과 화면의 목록이 서로 다른 사실을 말한다.
 * 2. **목록은 미리보기만 싣는다**(`SceneNoteListItemPayload`) — 전문은 단건 GET 이
 *    준다. 화면이 목록에서 전문을 기대하면 12000자 × 장면 수가 목록 응답에 들어와야
 *    한다(그래서 계약이 일부러 안 싣는다).
 * 3. **보관은 두 축이다** — 장면 보관과 장 보관은 따로 움직이는데 쓰기는 둘 다에서
 *    막힌다. 한 축만 표시하면 화면이 "읽기 전용"을 잘못 말한다.
 * 4. 행은 **그 장면의 편집기**로 간다(Slice 3 범위의 유일한 이동).
 * 5. **`truncated` 가 "더 보기"를 낸다**(오너 2026-09-06) — 참인 행에만 나오고, 눌렀을
 *    때 전문을 가져오는 것은 **단건 GET** 이다. 목록이 전문을 싣기 시작하면 12000자 ×
 *    장면 수가 목록 응답에 들어온다(2번과 같은 계약의 반대편).
 * 6. **행마다 자기 수정 시각을 싣는다**(오너 2026-09-06) — payload 에 이미 있던
 *    `updated_at` 이고, 어느 메모가 최근 것인지는 목록에서만 답할 수 있다.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SceneNotesPage } from "./SceneNotesPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

function mockFetch(...responses: Array<{ body: unknown; status?: number }>) {
  const fetchMock = vi.fn();
  for (const next of responses) {
    fetchMock.mockResolvedValueOnce(response(next.body, next.status));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const NOTE = {
  draft_id: "d1",
  scene_title: "첫눈",
  scene_archived: false,
  chapter_id: "c1",
  chapter_title: "1장 겨울",
  chapter_archived: false,
  body_preview: "난로 앞에서 편지를 태우는 장면을 여기서 시작한다.",
  truncated: false,
  updated_at: "2026-09-01T02:00:00Z",
};

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/projects/p1/notes"]}>
      <Routes>
        <Route path="/projects/:projectId/notes" element={<SceneNotesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("장면 메모 화면", () => {
  it("lists every note once and points each row at that scene's editor", async () => {
    const fetchMock = mockFetch({
      body: {
        notes: [
          NOTE,
          { ...NOTE, draft_id: "d2", scene_title: "두 번째 밤", body_preview: "두 번째" },
        ],
      },
    });

    renderPage();

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("1장 겨울")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText("난로 앞에서 편지를 태우는 장면을 여기서 시작한다."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "첫눈" })).toHaveAttribute(
      "href",
      "/projects/p1/drafts/d1",
    );
    expect(screen.getByRole("link", { name: "두 번째 밤" })).toHaveAttribute(
      "href",
      "/projects/p1/drafts/d2",
    );
    // 첫 조회는 필터 없는 전체 목록이다 — 빈 query 를 붙이면 서버가 같은 결과를
    // 주더라도 "검색 중"과 "전체 보기"가 URL 에서 구분되지 않는다.
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p1/notes");
  });

  it("hands the search box to the server instead of filtering in the browser", async () => {
    const fetchMock = mockFetch(
      { body: { notes: [NOTE, { ...NOTE, draft_id: "d2", scene_title: "두 번째 밤" }] } },
      { body: { notes: [{ ...NOTE, body_preview: "…편지를 태우는…" }] } },
    );

    renderPage();
    await screen.findByRole("link", { name: "첫눈" });

    await userEvent.type(screen.getByLabelText("메모 검색"), "편지");
    await userEvent.click(screen.getByRole("button", { name: "검색" }));

    expect(await screen.findByText("…편지를 태우는…")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/notes?query=%ED%8E%B8%EC%A7%80");
    // over-strict 방향: 서버가 준 행을 브라우저가 다시 거르면 안 된다. 두 번째
    // 응답이 한 행이므로 화면도 한 행이어야 하고, 제목이 검색어를 포함하지 않는
    // 행(본문 매치)이 사라져서도 안 된다.
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "첫눈" })).toBeInTheDocument();
  });

  it("says the search found nothing without pretending the project has no notes", async () => {
    mockFetch(
      { body: { notes: [NOTE] } },
      { body: { notes: [] } },
    );

    renderPage();
    await screen.findByRole("link", { name: "첫눈" });

    await userEvent.type(screen.getByLabelText("메모 검색"), "없는말");
    await userEvent.click(screen.getByRole("button", { name: "검색" }));

    expect(
      await screen.findByText("검색과 일치하는 메모가 없습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByText("아직 저장된 메모가 없습니다.")).not.toBeInTheDocument();
  });

  it("distinguishes an empty project from an empty search result", async () => {
    mockFetch({ body: { notes: [] } });

    renderPage();

    expect(
      await screen.findByText("아직 저장된 메모가 없습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByText("검색과 일치하는 메모가 없습니다.")).not.toBeInTheDocument();
  });

  it("shows scene archiving and chapter archiving as the two axes they are", async () => {
    mockFetch({
      body: {
        notes: [
          { ...NOTE, scene_archived: true },
          {
            ...NOTE,
            draft_id: "d2",
            scene_title: "두 번째 밤",
            chapter_title: "2장 봄",
            chapter_archived: true,
          },
          { ...NOTE, draft_id: "d3", scene_title: "세 번째 밤" },
        ],
      },
    });

    renderPage();

    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText("장면 보관됨")).toBeInTheDocument();
    expect(within(rows[0]).queryByText("장 보관됨")).not.toBeInTheDocument();
    expect(within(rows[1]).getByText("장 보관됨")).toBeInTheDocument();
    expect(within(rows[1]).queryByText("장면 보관됨")).not.toBeInTheDocument();
    // over-strict 방향: 보관되지 않은 행에 표시가 붙으면 안 된다.
    expect(within(rows[2]).queryByText("장면 보관됨")).not.toBeInTheDocument();
    expect(within(rows[2]).queryByText("장 보관됨")).not.toBeInTheDocument();
  });

  it("shows each row its own last-modified time", async () => {
    mockFetch({
      body: {
        notes: [
          NOTE,
          {
            ...NOTE,
            draft_id: "d2",
            scene_title: "두 번째 밤",
            updated_at: "2026-09-03T09:30:00Z",
          },
        ],
      },
    });

    renderPage();

    const rows = await screen.findAllByRole("listitem");
    // 실행 머신의 시간대에 기대 문자열이 달리므로 **같은 변환**을 기대값으로 쓴다 —
    // 잠그는 것은 시각 문자열 자체가 아니라 "그 행의 `updated_at` 에서 왔는가"다.
    const first = new Date(NOTE.updated_at).toLocaleString("ko-KR");
    const second = new Date("2026-09-03T09:30:00Z").toLocaleString("ko-KR");
    expect(first).not.toBe(second);
    expect(within(rows[0]).getByText(`수정 ${first}`)).toBeInTheDocument();
    expect(within(rows[1]).getByText(`수정 ${second}`)).toBeInTheDocument();
    // over-strict 방향: 한 행의 시각을 모든 행에 찍으면(또는 목록 하나의 시각을
    // 쓰면) 여기서 걸린다.
    expect(within(rows[0]).queryByText(`수정 ${second}`)).not.toBeInTheDocument();
  });

  it("offers 더 보기 only where the server said the preview was cut", async () => {
    mockFetch({
      body: {
        notes: [
          { ...NOTE, truncated: true },
          { ...NOTE, draft_id: "d2", scene_title: "두 번째 밤", truncated: false },
        ],
      },
    });

    renderPage();

    const rows = await screen.findAllByRole("listitem");
    // under-strict 방향: 신호를 읽지 않으면(버튼을 아예 안 내면) 첫 줄이 실패한다.
    expect(within(rows[0]).getByRole("button", { name: "더 보기" })).toBeInTheDocument();
    // over-strict 방향: `truncated` 를 무시하고 모든 행에 내면(미리보기가 이미
    // 전문인 행에서 "더 보기"는 같은 글을 다시 가져오는 헛 요청이다) 둘째 줄이
    // 실패한다.
    expect(within(rows[1]).queryByRole("button", { name: "더 보기" })).not.toBeInTheDocument();
  });

  it("pulls the full body from the single-note GET and folds back to the preview", async () => {
    const fetchMock = mockFetch(
      { body: { notes: [{ ...NOTE, truncated: true }] } },
      {
        body: {
          draft_id: "d1",
          body: "난로 앞에서 편지를 태우는 장면을 여기서 시작한다. 그리고 미리보기 뒤에 남아 있던 나머지 전문.",
          updated_at: NOTE.updated_at,
        },
      },
    );

    renderPage();
    await screen.findByRole("link", { name: "첫눈" });

    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));

    expect(await screen.findByText(/미리보기 뒤에 남아 있던 나머지 전문/)).toBeInTheDocument();
    // 목록이 전문을 실은 것이 아니다 — 두 번째 요청이 단건 GET 이어야 한다.
    expect(fetchMock.mock.calls[1][0]).toBe("/api/projects/p1/drafts/d1/note");

    await userEvent.click(screen.getByRole("button", { name: "접기" }));

    expect(screen.getByText(NOTE.body_preview)).toBeInTheDocument();
    expect(screen.queryByText(/미리보기 뒤에 남아 있던 나머지 전문/)).not.toBeInTheDocument();
  });

  it("keeps the preview on screen when the full body cannot be read", async () => {
    mockFetch(
      { body: { notes: [{ ...NOTE, truncated: true }] } },
      { body: { detail: "note not found" }, status: 404 },
    );

    renderPage();
    await screen.findByRole("link", { name: "첫눈" });

    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("note not found");
    // 미리보기가 남고, 다시 시도할 자리도 남는다.
    expect(screen.getByText(NOTE.body_preview)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
  });

  it("surfaces a refused list without emptying the screen silently", async () => {
    mockFetch({ body: { detail: "project not found" }, status: 404 });

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("project not found");
    expect(screen.queryByText("아직 저장된 메모가 없습니다.")).not.toBeInTheDocument();
  });

  it("keeps a failed search from erasing the list that is already on screen", async () => {
    mockFetch(
      { body: { notes: [NOTE] } },
      { body: { detail: "migration required" }, status: 503 },
    );

    renderPage();
    await screen.findByRole("link", { name: "첫눈" });

    await userEvent.type(screen.getByLabelText("메모 검색"), "편지");
    await userEvent.click(screen.getByRole("button", { name: "검색" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("migration required");
    expect(screen.getByRole("link", { name: "첫눈" })).toBeInTheDocument();
  });
});
