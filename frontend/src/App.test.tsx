import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { acceptWriting, reviseAndGateWriting } from "./api/client";
import { AuthGate } from "./auth/AuthGate";

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
  // The draft editor's unaccepted-candidate recovery banner (ScratchRecovery)
  // fetches its own list on mount. That call is orthogonal to the routing these
  // tests pin, so it is served an empty list *outside* the recorded mock —
  // otherwise the expected request sequences below would gain a stray entry.
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (typeof url === "string" && url.includes("/writing/scratch")) {
      return Promise.resolve(
        response({ project_id: "p1", draft_id: "d1", items: [] }),
      );
    }
    // K-4: WritingPanel 마운트 시 /writing/budget GET 이 발생 — 기록된 시퀀스를 건드리지
    // 않게 자동 응답한다(scratch 가로채기와 같은 패턴).
    if (typeof url === "string" && url.includes("/writing/budget")) {
      return Promise.resolve(
        response({
          project_id: "p1",
          context_budget_tokens: { short: 8192, medium: 8192, long: 8192 },
        }),
      );
    }
    return fetchMock(url, init);
  });
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App routes", () => {
  it("renders the project index at the root route", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { projects: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls).toHaveLength(2));
    for (const [, init] of fetchMock.mock.calls) {
      expect(init.credentials).toBe("same-origin");
    }
  });

  it("renders a directly addressed project workspace", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/me",
      "/api/projects/p1",
      "/api/projects/p1/drafts",
    ]);
  });

  it("renders a directly addressed draft editor", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      {
        body: {
          id: "d1",
          project_id: "p1",
          title: "첫 장면",
          archived: false,
        },
      },
      { body: { versions: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1/drafts/d1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "첫 장면" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/me",
      "/api/projects/p1",
      "/api/projects/p1/drafts/d1",
      "/api/projects/p1/drafts/d1/versions",
    ]);
  });

  it("keeps an unknown route inside the product shell", async () => {
    mockFetch({ body: { id: "u1", username: "alice", is_admin: false } });

    render(
      <MemoryRouter initialEntries={["/missing"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "이 작업 공간은 없습니다." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "프로젝트로 돌아가기" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("renders no protected route before the session check completes", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("세션을 확인하는 중…")).toBeInTheDocument();
    expect(screen.queryByText("로그인")).not.toBeInTheDocument();
    expect(screen.queryByText("불러오는 중…")).not.toBeInTheDocument();
  });

  it("keeps the addressed route while logging in and returns there after success", async () => {
    const fetchMock = mockFetch(
      { status: 401, body: { detail: "not authenticated" } },
      {
        body: {
          user: { id: "u1", username: "alice", is_admin: false },
        },
      },
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByLabelText("아이디");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(["/api/auth/me"]);

    await userEvent.type(screen.getByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("비밀번호"), "pw123");
    await userEvent.click(screen.getByRole("button", { name: "작업실 입장" }));

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/me",
      "/api/auth/login",
      "/api/projects/p1",
      "/api/projects/p1/drafts",
    ]);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      credentials: "same-origin",
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      username: "alice",
      password: "pw123",
    });
  });

  it("sends an administrator to the console when they log in at the root", async () => {
    // 9.2 P5=ⓐ. 관리자에게 첫 화면은 관리 화면이다.
    mockFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { body: { user: { id: "a1", username: "root", is_admin: true } } },
      { body: { users: [] } },
      { body: { projects: [] } },
      { body: { events: [] } },
      { body: { sites: [], totals: {} } },
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByLabelText("아이디");
    await userEvent.type(screen.getByLabelText("아이디"), "root");
    await userEvent.type(screen.getByLabelText("비밀번호"), "pw123");
    await userEvent.click(screen.getByRole("button", { name: "작업실 입장" }));

    expect(
      await screen.findByRole("heading", { name: "관리", level: 1 }),
    ).toBeInTheDocument();
  });

  it("does not swallow an administrator's deep link", async () => {
    // ★ P5 의 딥링크 지적. 이 게이트는 URL 을 바꾸지 않고 제자리에서 로그인
    // 화면을 그리므로, 관리자가 `/projects/p1` 로 들어왔으면 **그 화면을 받아야**
    // 한다. 무조건 `/admin` 으로 옮기면 의도한 도착지가 사라진다.
    //
    // ★ 이 성질 덕분에 `?next=` 가 필요 없고, 그래서 **open redirect 표면(S-2)이
    // 아예 생기지 않는다** — 없는 것을 검증할 수는 없으므로 이 셀이 그 자리다.
    mockFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { body: { user: { id: "a1", username: "root", is_admin: true } } },
      { body: { id: "p1", name: "겨울 이야기", archived: false } },
      { body: { drafts: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByLabelText("아이디");
    await userEvent.type(screen.getByLabelText("아이디"), "root");
    await userEvent.type(screen.getByLabelText("비밀번호"), "pw123");
    await userEvent.click(screen.getByRole("button", { name: "작업실 입장" }));

    expect(
      await screen.findByRole("heading", { name: "겨울 이야기" }),
    ).toBeInTheDocument();
  });

  it("keeps the personal hub behind the session gate", async () => {
    // ★ S-1. 지금은 `AuthGate` 가 `<Routes>` 전체를 감싸 이것이 구조적으로 참이지만,
    // **공개 랜딩(F10)을 열면서 그 보호를 좁히는 순간 `/me` 가 딸려 나갈 수 있다**.
    // 그 변경이 오기 전에 셀을 놓아 둔다 — 진짜 방어는 백엔드 401 이고(`/me/activity`·
    // `/me/quota` 는 인증 전용 tier) 이것은 화면이 새지 않는지만 본다.
    mockFetch({ status: 401, body: { detail: "not authenticated" } });

    render(
      <MemoryRouter initialEntries={["/me"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByLabelText("아이디")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "내 작업" })).toBeNull();
  });

  it("uses one generic message for every rejected login", async () => {
    mockFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { status: 401, body: { detail: "invalid credentials" } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.type(await screen.findByLabelText("아이디"), "ghost");
    await userEvent.type(screen.getByLabelText("비밀번호"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "작업실 입장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "아이디 또는 비밀번호를 확인해 주세요.",
    );
    expect(screen.queryByText("invalid credentials")).not.toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호")).toHaveValue("");
  });

  it("replaces an administrator-set password before creating a session", async () => {
    const fetchMock = mockFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { status: 409, body: { detail: "password replacement required" } },
      {
        body: {
          user: { id: "u1", username: "alice", is_admin: false },
        },
      },
      { body: { projects: [] } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.type(await screen.findByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("비밀번호"), "temporary-password");
    await userEvent.click(screen.getByRole("button", { name: "작업실 입장" }));

    expect(await screen.findByRole("heading", { name: "새 비밀번호 설정" })).toBeInTheDocument();
    expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument();
    expect(screen.getByLabelText("새 비밀번호 확인")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("새 비밀번호"), "short-pass1");
    await userEvent.type(screen.getByLabelText("새 비밀번호 확인"), "short-pass1");
    expect(screen.getByRole("button", { name: "비밀번호 바꾸고 입장" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("새 비밀번호"));
    await userEvent.clear(screen.getByLabelText("새 비밀번호 확인"));

    await userEvent.type(screen.getByLabelText("새 비밀번호"), "new-password");
    await userEvent.type(screen.getByLabelText("새 비밀번호 확인"), "different-one");
    expect(screen.getByRole("button", { name: "비밀번호 바꾸고 입장" })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("새 비밀번호 확인"));
    await userEvent.type(screen.getByLabelText("새 비밀번호 확인"), "new-password");
    await userEvent.click(screen.getByRole("button", { name: "비밀번호 바꾸고 입장" }));

    expect(await screen.findByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      username: "alice",
      password: "temporary-password",
      new_password: "new-password",
    });
  });

  it("does not expose the admin route or call admin APIs for a non-admin", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
    );

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "관리자 권한이 필요합니다." }),
    ).toBeInTheDocument();
    // 10.0: 닫힌 채로 없는 것은 약하다 — **열어서** 없음을 본다.
    await userEvent.click(screen.getByRole("button", { name: "alice" }));
    expect(screen.queryByRole("link", { name: "관리" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "내 작업" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(["/api/auth/me"]);
  });

  it("exposes the guarded admin route to an administrator", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "root", is_admin: true } },
      { body: { users: [] } },
      { body: { projects: [] } },
      { body: {
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      } },
      { body: { events: [] } },
    );

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "관리" })).toBeInTheDocument();
    // 10.0: 관리 링크는 계정 메뉴 안으로 들어갔다(D4 ⓐ+ⓒ).
    await userEvent.click(screen.getByRole("button", { name: "root" }));
    expect(screen.getByRole("link", { name: "관리" })).toHaveAttribute("href", "/admin");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/me",
      "/api/admin/users",
      "/api/admin/projects",
      "/api/admin/observability/kpi",
      "/api/admin/audit-events",
    ]);
  });

  it("returns to login when a protected request reports an expired session", async () => {
    mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { status: 401, body: { detail: "not authenticated" } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("세션이 만료되었습니다.")).toBeInTheDocument();
    expect(screen.getByLabelText("아이디")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "프로젝트" })).not.toBeInTheDocument();
  });

  it("also expires the session for partial-envelope requests that bypass JSON request()", async () => {
    mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { status: 401, body: { detail: "not authenticated" } },
    );

    function PartialEnvelopeCaller() {
      return (
        <button
          type="button"
          onClick={() => {
            void acceptWriting("p1", {} as Parameters<typeof acceptWriting>[1]).catch(
              () => undefined,
            );
          }}
        >
          채택
        </button>
      );
    }

    render(
      <MemoryRouter>
        <AuthGate>
          <PartialEnvelopeCaller />
        </AuthGate>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "채택" }));

    expect(await screen.findByText("세션이 만료되었습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "채택" })).not.toBeInTheDocument();
  });

  it("also expires the session for revise-and-gate partial-envelope requests", async () => {
    mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { status: 401, body: { detail: "not authenticated" } },
    );

    function ReviseAndGateCaller() {
      return (
        <button
          type="button"
          onClick={() => {
            void reviseAndGateWriting(
              "p1",
              {} as Parameters<typeof reviseAndGateWriting>[1],
            ).catch(() => undefined);
          }}
        >
          부분 수정
        </button>
      );
    }

    render(
      <MemoryRouter>
        <AuthGate>
          <ReviseAndGateCaller />
        </AuthGate>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "부분 수정" }));

    expect(await screen.findByText("세션이 만료되었습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "부분 수정" })).not.toBeInTheDocument();
  });

  it("keeps the protected UI mounted until server logout succeeds", async () => {
    let resolveLogout!: (response: unknown) => void;
    const pendingLogout = new Promise((resolve) => {
      resolveLogout = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        response({ id: "u1", username: "alice", is_admin: false }),
      )
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockReturnValueOnce(pendingLogout);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "alice" }));
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(screen.getByRole("button", { name: "나가는 중…" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
    expect(screen.queryByLabelText("아이디")).not.toBeInTheDocument();

    resolveLogout(response({ ok: true }));

    expect(await screen.findByLabelText("아이디")).toBeInTheDocument();
  });

  it("keeps the authenticated workspace and shows an error when server logout fails", async () => {
    mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { projects: [] } },
      { status: 503, body: { detail: "storage unavailable" } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "alice" }));
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "로그아웃하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    );
    expect(screen.getByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByLabelText("아이디")).not.toBeInTheDocument();
  });

  it("revokes the server session before returning to the login surface", async () => {
    const fetchMock = mockFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { projects: [] } },
      { body: { ok: true } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "alice" }));
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(await screen.findByLabelText("아이디")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/auth/logout");
    expect(fetchMock.mock.calls[2][1]).toMatchObject({
      method: "POST",
      credentials: "same-origin",
    });
  });

  it("offers a retry instead of misreporting a session-check outage as logout", async () => {
    const fetchMock = mockFetch(
      { status: 503, body: { detail: "storage unavailable" } },
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { projects: [] } },
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "세션을 확인하지 못했습니다.",
    );
    expect(screen.queryByLabelText("비밀번호")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByRole("heading", { name: "프로젝트" })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });
  describe("계정 메뉴 (Phase 10 Slice 10.0, D4 = ⓐ+ⓒ)", () => {
    /**
     * **`/me` 로 가는 링크가 저장소 전체에 하나도 없었다** — route 는 9.2 에 있었으나
     * 진입점이 없어 주소를 직접 쳐야 도달했다(2026-08-11 육안 확인). 여기가 그
     * 진입점을 잠그는 자리다.
     *
     * `role="menu"` 가 아니라 **disclosure** 인 이유는 `AuthGate.tsx` 의
     * `SessionMenu` docstring 에 있다.
     */

    it("puts the personal hub behind the username, closed until asked", async () => {
      mockFetch(
        { body: { id: "u1", username: "alice", is_admin: false } },
        { body: { projects: [] } },
      );

      render(
        <MemoryRouter>
          <App />
        </MemoryRouter>,
      );

      const trigger = await screen.findByRole("button", { name: "alice" });
      // 닫혀 있을 때는 항목이 DOM 에 없다 — "보이지만 감춰짐" 이 아니다.
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("link", { name: "내 작업" })).not.toBeInTheDocument();

      await userEvent.click(trigger);

      expect(trigger).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByRole("link", { name: "내 작업" })).toHaveAttribute("href", "/me");
    });

    it("closes on Escape and gives focus back to the trigger", async () => {
      mockFetch(
        { body: { id: "u1", username: "alice", is_admin: false } },
        { body: { projects: [] } },
      );

      render(
        <MemoryRouter>
          <App />
        </MemoryRouter>,
      );

      const trigger = await screen.findByRole("button", { name: "alice" });
      await userEvent.click(trigger);
      expect(screen.getByRole("link", { name: "내 작업" })).toBeInTheDocument();

      await userEvent.keyboard("{Escape}");

      expect(screen.queryByRole("link", { name: "내 작업" })).not.toBeInTheDocument();
      // 포커스를 안 돌려주면 키보드 사용자가 메뉴를 닫은 자리에서 길을 잃는다.
      expect(trigger).toHaveFocus();
    });

    it("keeps the logout progress visible instead of closing the panel", async () => {
      /**
       * over-strict 방향: 로그아웃 클릭에 `setOpen(false)` 를 넣으면 "나가는 중…"·
       * `disabled` 가 그 즉시 사라져 **진행 중이라는 유일한 신호를 잃는다.**
       * 초판이 실제로 그렇게 썼다가 이 성질 때문에 고쳤다.
       */
      let resolveLogout!: (value: unknown) => void;
      const pending = new Promise((resolve) => { resolveLogout = resolve; });
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(
          response({ id: "u1", username: "alice", is_admin: false }),
        )
        .mockResolvedValueOnce(response({ projects: [] }))
        .mockReturnValueOnce(pending);
      vi.stubGlobal("fetch", fetchMock);

      render(
        <MemoryRouter>
          <App />
        </MemoryRouter>,
      );

      await userEvent.click(await screen.findByRole("button", { name: "alice" }));
      await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

      expect(screen.getByRole("button", { name: "나가는 중…" })).toBeDisabled();

      resolveLogout(response({ ok: true }));
      expect(await screen.findByLabelText("아이디")).toBeInTheDocument();
    });

    it("names the product 에-라잇 in the header, not the old working title", async () => {
      // D5. 로그인 화면은 9.2 부터 "에-라잇" 인데 헤더만 옛 이름으로 남아 있었다.
      mockFetch(
        { body: { id: "u1", username: "alice", is_admin: false } },
        { body: { projects: [] } },
      );

      render(
        <MemoryRouter>
          <App />
        </MemoryRouter>,
      );

      expect(await screen.findByRole("link", { name: "에-라잇" })).toHaveAttribute("href", "/");
      expect(screen.queryByText("AI Writing System")).not.toBeInTheDocument();
    });
  });
});
