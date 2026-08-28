import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminConsole } from "./AdminConsole";

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AdminConsole", () => {
  it("loads users, project metadata, and the deployment KPI", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        users: [
          { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
          { id: "u2", username: "alice", is_admin: false, is_active: true, status: "active" },
        ],
      }))
      .mockResolvedValueOnce(response({
        projects: [
          { id: "p1", name: "겨울 이야기", archived: false, owner_id: "u2" },
          { id: "p2", name: "보관 원고", archived: true, owner_id: null },
        ],
      }))
      .mockResolvedValueOnce(response({
        projects_considered: 2,
        totals: {
          calls: 12, success: 10, provider_error: 1, parse_error: 1,
          total_tokens: 100, tokens_counted_from: 10,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록(사용자 섹션 뒤에 렌더).
      .mockResolvedValueOnce(response({ policies: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "관리" })).toBeInTheDocument();
    // 오너 요청(2026-08-24): 관리 화면에서 서비스로 들어가는 명시적 출구.
    // H2(2026-08-24 검증 보강): 존재·href만 잠그면 header 안으로 옮겨져도 green이다
    // (.page-heading > p:last-child 소개 문단 스타일이 깨지는 그 배치) — 머리글의
    // 바로 다음 형제라는 위치까지 잠근다.
    const serviceLink = screen.getByRole("link", { name: "작업장으로 이동 →" });
    expect(serviceLink).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("heading", { name: "관리" }).closest("header")!
        .nextElementSibling,
    ).toBe(serviceLink);
    expect(await screen.findByRole("heading", { name: "회원 사용량 한도" }))
      .toBeInTheDocument();
    expect(await screen.findByText("활성 회원이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("root")).toBeInTheDocument();
    // 오너 2026-08-27: 소유자 있는 프로젝트는 이 화면에 더 이상 쌓이지 않는다 —
    // 사용자 상세로 들어간다. 여기 남는 것은 거기로 갈 수 없는 것뿐이다.
    expect(screen.queryByText("겨울 이야기")).not.toBeInTheDocument();
    const aliceRow = screen.getByText("alice").closest("li")!;
    // 오너 2026-08-28: 별도 액션보다 사용자 아이디 자체가 상세 진입점인 것이
    // 일반적이다. under-strict: 아이디를 평문으로 되돌리면 실패한다.
    // over-strict: 라벨을 없애 목적이 불분명해져도 accessible name이 달라져 실패한다.
    expect(within(aliceRow).getByRole("link", { name: "alice 상세 보기 →" }))
      .toHaveAttribute("href", "/admin/users/u2");
    expect(within(aliceRow).queryByRole("link", { name: "사용자 상세 보기 →" }))
      .not.toBeInTheDocument();
    expect(within(aliceRow).getByText(/프로젝트 1개/)).toBeInTheDocument();
    expect(screen.getByText(/보관됨/)).toBeInTheDocument();
    expect(screen.getByText(/소유자 없음/)).toBeInTheDocument();
    const orphanProject = screen.getByText("보관 원고").closest("article");
    expect(orphanProject).not.toBeNull();
    expect(
      within(orphanProject!).queryByRole("button", { name: "1시간 읽기 권한 발급" }),
    ).not.toBeInTheDocument();
    expect(
      within(orphanProject!).queryByRole("button", { name: "접근 이력 보기" }),
    ).not.toBeInTheDocument();
    expect(within(orphanProject!).getByText(/승격으로 열 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/admin/users",
      "/api/admin/projects",
      "/api/admin/observability/kpi",
      "/api/admin/audit-events",
      "/api/admin/signup-requests",
      "/api/admin/quota-policies",
    ]);
  });

  it("creates and deactivates users without losing the returned state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록(사용자 섹션 뒤에 렌더).
      .mockResolvedValueOnce(response({ policies: [] }))
      .mockResolvedValueOnce(response({
        id: "u2", username: "alice", is_admin: false, is_active: true,
        status: "active",
      }))
      .mockResolvedValueOnce(response({
        id: "u2", username: "alice", is_admin: false, is_active: false,
        status: "active",
      }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    await screen.findByText("root");

    await userEvent.type(screen.getByLabelText("새 사용자 아이디"), "alice");
    await userEvent.type(screen.getByLabelText("초기 비밀번호"), "temporary-password");
    await userEvent.click(screen.getByRole("button", { name: "사용자 만들기" }));

    const aliceRow = (await screen.findByText("alice")).closest("li");
    expect(aliceRow).not.toBeNull();
    expect(JSON.parse(fetchMock.mock.calls[6][1].body)).toEqual({
      username: "alice", password: "temporary-password", is_admin: false,
    });
    await userEvent.click(within(aliceRow!).getByRole("button", { name: "비활성화" }));
    expect(await within(aliceRow!).findByText(/비활성/)).toBeInTheDocument();
  });

  it("tells a pending signup apart from an active account", async () => {
    // 오너 2026-08-27(dogfood): 가입 요청 행은 is_active=True 로 저장되므로
    // 활성 플래그만 읽으면 **로그인조차 못 하는 계정이 "활성"으로 보인다**.
    // under-strict: status 를 다시 무시하면 bob 이 "활성"이 되어 재실패한다.
    // over-strict: 대기 행을 비활성으로 "고치는" 과대교정도 여기서 실패한다 —
    // 비활성화는 단방향(D6)이고 대기와는 다른 축이라 라벨이 달라야 한다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
        { id: "u2", username: "bob", is_admin: false, is_active: true, status: "pending" },
        { id: "u3", username: "carol", is_admin: false, is_active: false, status: "active" },
        { id: "u4", username: "dave", is_admin: false, is_active: false, status: "rejected" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록(사용자 섹션 뒤에 렌더).
      .mockResolvedValueOnce(response({ policies: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);

    const bobRow = (await screen.findByText("bob")).closest("li")!;
    expect(within(bobRow).getByText(/승인 대기/)).toBeInTheDocument();
    expect(within(bobRow).queryByText(/· 활성/)).not.toBeInTheDocument();
    expect(within(screen.getByText("root").closest("li")!).getByText(/· 활성/))
      .toBeInTheDocument();
    // 비활성화는 승인 축보다 앞선다: 거절된 뒤 비활성화된 계정은 "비활성"이다.
    expect(within(screen.getByText("carol").closest("li")!).getByText(/비활성/))
      .toBeInTheDocument();
    expect(within(screen.getByText("dave").closest("li")!).getByText(/비활성/))
      .toBeInTheDocument();
  });

  it("filters the user list by username", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
        { id: "u2", username: "alice", is_admin: false, is_active: true, status: "active" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록(사용자 섹션 뒤에 렌더).
      .mockResolvedValueOnce(response({ policies: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    await screen.findByText("alice");

    await userEvent.type(screen.getByLabelText("사용자 검색"), "ali");

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByText("root")).not.toBeInTheDocument();
    // 검색은 화면만 좁힌다 — 서버를 다시 치지 않는다.
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("purges an orphan project and re-reads the audit log", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "주인 잃은 원고", archived: true, owner_id: null },
      ] }))
      .mockResolvedValueOnce(response({
        projects_considered: 1,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [] }))
      .mockResolvedValueOnce(response({ policies: [] }))
      .mockResolvedValueOnce(response(undefined, 204))
      .mockResolvedValueOnce(response({ events: [
        {
          id: "e2", operation_id: "op1", admin_user_id: "u1",
          action: "project_purge", target_type: "project", target_project_id: "p1",
          reason: "정리", outcome: "succeeded",
          at: "2026-08-27T02:00:00Z", error_kind: null,
        },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    const project = (await screen.findByText("주인 잃은 원고")).closest("article")!;
    // 소유자 없는 프로젝트는 승격으로 열 수 없다 — 그래도 파기는 여기서 한다.
    expect(within(project).queryByRole("button", { name: "1시간 읽기 권한 발급" }))
      .not.toBeInTheDocument();

    await userEvent.click(within(project).getByRole("button", { name: "영구 삭제 준비" }));
    await userEvent.type(within(project).getByLabelText("삭제 사유"), "정리");
    await userEvent.type(within(project).getByLabelText(/확인을 위해/), "주인 잃은 원고");
    await userEvent.click(within(project).getByRole("button", { name: "영구 삭제" }));

    expect(await screen.findByRole("status")).toHaveTextContent("영구 삭제했습니다");
    expect(screen.queryByText("주인 잃은 원고")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[6][0]).toBe("/api/admin/projects/p1/purge");
    expect(await screen.findByText("p1")).toBeInTheDocument();
  });

  it("lists signup requests and approves one", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [
        { id: "s1", username: "bob", requested_at: "2026-08-22T09:00:00Z" },
      ] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록.
      .mockResolvedValueOnce(response({ policies: [] }))
      .mockResolvedValueOnce(response({
        id: "s1", username: "bob", requested_at: "2026-08-22T09:00:00Z",
      }))
      .mockResolvedValueOnce(response({ requests: [] }))
      // 승인은 그 행의 상태를 대기 → 활성으로 바꾼다. 사용자 목록도 함께 다시 읽는다.
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
        { id: "s1", username: "bob", is_admin: false, is_active: true, status: "active" },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);

    expect(await screen.findByText("bob")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "승인" }));

    expect(await screen.findByText("bob 계정을 승인했습니다.")).toBeInTheDocument();
    // 처리된 요청은 큐에서 사라진다 — 목록을 다시 읽었기 때문이다.
    expect(screen.queryByRole("button", { name: "승인" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[6][0]).toBe("/api/admin/signup-requests/s1/approve");
    expect(fetchMock.mock.calls[6][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[7][0]).toBe("/api/admin/signup-requests");
  });

  it("rejects a signup and stays honest when the request was already resolved", async () => {
    // 409(다른 관리자가 먼저 처리)여도 목록을 다시 읽어 서버 상태를 따른다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
      ] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        projects_considered: 0,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ requests: [
        { id: "s1", username: "bob", requested_at: "2026-08-22T09:00:00Z" },
      ] }))
      // 6번째 마운트 fetch — MemberQuotaSection 목록.
      .mockResolvedValueOnce(response({ policies: [] }))
      .mockResolvedValueOnce(response({ detail: "signup request already resolved" }, 409))
      .mockResolvedValueOnce(response({ requests: [] }))
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);

    expect(await screen.findByText("bob")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "거절" }));

    // 오류는 보이되, 큐는 서버가 말하는 대로(비었다) 갱신된다.
    expect(await screen.findByText(/409: signup request already resolved/)).toBeInTheDocument();
    expect(screen.queryByText("bob")).not.toBeInTheDocument();
  });
});
