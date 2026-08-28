import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DraftList } from "./DraftList";

/** Queue one JSON response per fetch call, in order. */
function mockFetch(...responses: Array<{ status?: number; body: unknown }>) {
  const fetchMock = vi.fn();
  for (const { status = 200, body } of responses) {
    fetchMock.mockResolvedValueOnce({
      ok: status >= 200 && status < 300,
      status,
      statusText: "",
      json: async () => body,
    });
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderDraftList(path = "/projects/p1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>프로젝트 홈</p>} />
        <Route path="/projects/:projectId" element={<DraftList />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DraftList", () => {
  it("loads the selected project and only that project's drafts", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "scene", position: 1,
            },
            {
              id: "d2", project_id: "p1", title: "묵은 장면", archived: true,
              unit_kind: "other", position: 2,
            },
          ],
        },
      },
    );

    renderDraftList();

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
    expect(screen.getByText("첫 장면")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "첫 장면" })).toHaveAttribute(
      "href",
      "/projects/p1/drafts/d1",
    );
    expect(screen.getByText("묵은 장면")).toBeInTheDocument();
    expect(screen.getByText("정본 순서 1 · 장면")).toBeInTheDocument();
    expect(screen.getByText("정본 순서 2 · 기타")).toBeInTheDocument();
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/projects/p1",
      "/api/projects/p1/drafts",
    ]);
  });

  it("does not offer the admin access log to the project owner", async () => {
    // 오너 결정(2026-08-10): **관리자 접근 이력은 관리자가 보는 것**이다 — 문의가 들어오면
    // 관리자가 그것을 보고 답한다. 소유자 화면에 두는 것은 오너의 의도가 아니었고,
    // 그 통로는 관리자 콘솔에 이미 있다(AdminConsole "접근 이력 보기").
    //
    // ★ 링크만 뗐다 — route 도 API(operation 73)도 그대로다. 계약을 축소하지 않은 것은
    // 되돌리기를 공짜로 두기 위해서이고, D8-5f C-4 의 "소유자가 본다" 근거를 다시 볼지는
    // 별도 결정으로 남아 있다. 이 셀은 링크가 **조용히 되살아나는 것**만 막는다.
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList();

    await screen.findByRole("heading", { name: "겨울 이야기" });
    expect(screen.queryByRole("link", { name: /관리자 접근 이력/ })).toBeNull();
    // ★ 9.2 P7=ⓑ — 관측도 뗐다(운영 질문이라 `/me` 로 갔다). **활동은 남는다** —
    // "이 원고에서 무슨 일이 있었나"는 저작 중의 질문이라 여기가 자연스럽다.
    // 뭉뚱그려 지우는 과잉 교정은 아래 단정이 막는다.
    expect(screen.queryByRole("link", { name: /파이프라인 관측/ })).toBeNull();
    // ★ 오너 2026-08-27: 활동·작품 정보·개요는 사라진 것이 아니라 **프로젝트 설정
    // 탭 아래로 모였다**(작업 공간 첫 화면이 어지러웠다). 여기 남는 링크는 집필 중
    // 수시로 드나드는 검토함과, 그 설정 입구 둘뿐이다.
    expect(screen.queryByRole("link", { name: /활동 타임라인/ })).toBeNull();
    expect(screen.getByRole("link", { name: /검토함/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /프로젝트 설정/ }))
      .toHaveAttribute("href", "/projects/p1/settings");
  });

  it("supports a direct project URL and shows an empty draft state", async () => {
    mockFetch(
      { body: { id: "deep-link", name: "직접 진입", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList("/projects/deep-link");

    expect(await screen.findByText(/아직 원고가 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "직접 진입" })).toBeInTheDocument();
  });

  it("posts a new draft and reloads the server-owned draft list", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      {
        body: {
          id: "d1", project_id: "p1", title: "첫 장면", archived: false,
          unit_kind: "scene", position: 1,
        },
      },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "scene", position: 1,
            },
          ],
        },
      },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");
    await userEvent.selectOptions(screen.getByLabelText("원고 단위"), "scene");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    expect(await screen.findByText("첫 장면")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/drafts");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ title: "첫 장면", unit_kind: "scene" });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("reorders the complete server-owned draft permutation", async () => {
    const one = {
      id: "d1", project_id: "p1", title: "첫 장", archived: false,
      unit_kind: "chapter", position: 1,
    };
    const two = {
      id: "d2", project_id: "p1", title: "둘째 장면", archived: true,
      unit_kind: "scene", position: 2,
    };
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [one, two] } },
      { body: { drafts: [{ ...two, position: 1 }, { ...one, position: 2 }] } },
    );

    renderDraftList();
    await screen.findByText("첫 장");
    await userEvent.click(screen.getByRole("button", { name: "첫 장 아래로" }));

    await waitFor(() => {
      const rows = screen.getAllByRole("listitem");
      expect(rows[0]).toHaveTextContent("둘째 장면");
      expect(rows[1]).toHaveTextContent("첫 장");
    });
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe("/api/projects/p1/draft-order");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ ordered_draft_ids: ["d2", "d1"] });
  });

  it("trims a normal title but never posts a whitespace-only title", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      {
        body: {
          id: "d1", project_id: "p1", title: "첫 장면", archived: false,
          unit_kind: "other", position: 1,
        },
      },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "other", position: 1,
            },
          ],
        },
      },
    );

    const { container } = renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    const field = screen.getByLabelText("새 원고 제목");
    await userEvent.type(field, "   ");
    expect(screen.getByRole("button", { name: "원고 만들기" })).toBeDisabled();
    const form = container.querySelector("form");
    if (form === null) {
      throw new Error("form is missing");
    }
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await userEvent.clear(field);
    await userEvent.type(field, "  첫 장면  ");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    await waitFor(() => expect(field).toHaveValue(""));
    // 단위를 안 고르면 "장"으로 간다(오너 2026-08-27) — 종전 기본 "기타"는
    // 서버가 값 없는 요청에 채우는 값이었지 사람이 고르는 첫 값이 아니었다.
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      title: "첫 장면",
      unit_kind: "chapter",
    });
  });

  it("does not mint two drafts while the first create is in flight", async () => {
    let releasePost!: (response: unknown) => void;
    const pendingPost = new Promise((resolve) => {
      releasePost = resolve;
    });
    const fetchMock = vi.fn();
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ id: "p1", name: "겨울 이야기", archived: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ drafts: [] }),
      })
      .mockReturnValueOnce(pendingPost)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({
          drafts: [
            {
              id: "d1", project_id: "p1", title: "첫 장면", archived: false,
              unit_kind: "other", position: 1,
            },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);
    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");

    const form = container.querySelector("form");
    if (form === null) {
      throw new Error("form is missing");
    }
    fireEvent.submit(form);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    releasePost({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({
        id: "d1", project_id: "p1", title: "첫 장면", archived: false,
        unit_kind: "other", position: 1,
      }),
    });

    expect(await screen.findByText("첫 장면")).toBeInTheDocument();
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts).toHaveLength(1);
  });

  it("keeps an archived project readable but prevents an over-strict write", async () => {
    const fetchMock = mockFetch(
      { body: { id: "p1", name: "보관 작품", archived: true } },
      {
        body: {
          drafts: [
            {
              id: "d1", project_id: "p1", title: "남은 원고", archived: false,
              unit_kind: "other", position: 1,
            },
          ],
        },
      },
    );

    renderDraftList();

    expect(await screen.findByText("남은 원고")).toBeInTheDocument();
    expect(screen.getByText(/보관된 프로젝트에서는 새 원고를 만들 수 없습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText("새 원고 제목")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("surfaces a draft list failure without leaking another project", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { status: 404, body: { detail: "project not found" } },
    );

    renderDraftList();

    expect(await screen.findByRole("alert")).toHaveTextContent("404: project not found");
    expect(screen.queryByText("첫 장면")).not.toBeInTheDocument();
  });

  it("surfaces create failure and keeps the title for retry", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
      { status: 409, body: { detail: "project is archived" } },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);
    await userEvent.type(screen.getByLabelText("새 원고 제목"), "첫 장면");
    await userEvent.click(screen.getByRole("button", { name: "원고 만들기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "409: project is archived",
    );
    expect(screen.getByLabelText("새 원고 제목")).toHaveValue("첫 장면");
  });

  it("returns to the project list through browser navigation", async () => {
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(
      screen.getByRole("link", { name: /프로젝트로 돌아가기/ }),
    );

    expect(await screen.findByText("프로젝트 홈")).toBeInTheDocument();
  });

  it("defaults the unit to 장 and explains that the three are labels, not a hierarchy", async () => {
    // 오너 2026-08-27(dogfood): ① 첫 값이 늘 "기타"였다 ② 장·장면을 섞어 쓸 때
    // 무엇이 달라지는지 화면이 말하지 않았다.
    //
    // ★ 설명문은 **실제 동작**을 적는다. `unit_kind` 는 평면 ordered unit 의
    // 이름표이고(SoT D2=A) 계층이 아니다 — 프롬프트에도, export heading 에도,
    // 부모-자식 관계에도 쓰이지 않는다. under-strict: 계층이 있는 것처럼 다시
    // 쓰면 "계층은 없습니다" 단정이 실패한다.
    mockFetch(
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    renderDraftList();
    await screen.findByText(/아직 원고가 없습니다/);

    expect(screen.getByLabelText("원고 단위")).toHaveValue("chapter");
    const help = screen.getByText(/이름표입니다/).closest("p")!;
    expect(help).toHaveClass("unit-kind-help");
    expect(help.textContent).toContain("계층은 없습니다");
    expect(screen.getByText("원고 단위")).toHaveClass("unit-kind-label");
    // over-strict 가드: 설명을 넣었다고 선택지를 줄이면 안 된다 — 셋 다 남는다.
    const options = Array.from(
      screen.getByLabelText("원고 단위").querySelectorAll("option"),
    ).map((option) => option.textContent);
    expect(options).toEqual(["장", "장면", "기타"]);
  });
});
