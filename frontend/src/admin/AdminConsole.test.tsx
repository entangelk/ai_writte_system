import { render, screen, waitFor, within } from "@testing-library/react";
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
          { id: "u1", username: "root", is_admin: true, is_active: true },
          { id: "u2", username: "alice", is_admin: false, is_active: true },
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
      .mockResolvedValueOnce(response({ events: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "관리" })).toBeInTheDocument();
    expect(screen.getByText("root")).toBeInTheDocument();
    expect(screen.getByText("겨울 이야기")).toBeInTheDocument();
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
    ]);
  });

  it("creates and deactivates users without losing the returned state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true },
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
      .mockResolvedValueOnce(response({
        id: "u2", username: "alice", is_admin: false, is_active: true,
      }))
      .mockResolvedValueOnce(response({
        id: "u2", username: "alice", is_admin: false, is_active: false,
      }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    await screen.findByText("root");

    await userEvent.type(screen.getByLabelText("새 사용자 아이디"), "alice");
    await userEvent.type(screen.getByLabelText("초기 비밀번호"), "temporary-password");
    await userEvent.click(screen.getByRole("button", { name: "사용자 만들기" }));

    const aliceRow = (await screen.findByText("alice")).closest("li");
    expect(aliceRow).not.toBeNull();
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({
      username: "alice", password: "temporary-password", is_admin: false,
    });
    await userEvent.click(within(aliceRow!).getByRole("button", { name: "비활성화" }));
    expect(await within(aliceRow!).findByText(/비활성/)).toBeInTheDocument();
  });

  it("requires a reason, issues a grant, then reads the audited access history", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true },
        { id: "u2", username: "alice", is_admin: false, is_active: true },
      ] }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "겨울 이야기", archived: false, owner_id: "u2" },
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
      .mockResolvedValueOnce(response({ grant: {
        id: "g1", project_id: "p1", admin_user_id: "u1", reason: "지원 요청 확인",
        created_at: "2026-08-02T00:00:00Z", expires_at: "2026-08-02T01:00:00Z",
      } }, 201))
      .mockResolvedValueOnce(response({ entries: [
        {
          grant_id: "g1", admin_user_id: "u1", method: "GET",
          path: "/projects/p1", at: "2026-08-02T00:10:00Z", reason: "지원 요청 확인",
        },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    const project = (await screen.findByText("겨울 이야기")).closest("article");
    expect(project).not.toBeNull();
    const grantButton = within(project!).getByRole("button", { name: "1시간 읽기 권한 발급" });
    expect(grantButton).toBeDisabled();

    await userEvent.type(within(project!).getByLabelText("접근 사유"), "지원 요청 확인");
    await userEvent.click(grantButton);

    expect(await within(project!).findByText(/권한 만료/)).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({ reason: "지원 요청 확인" });
    expect(within(project!).getByRole("link", { name: "프로젝트 열기" })).toHaveAttribute(
      "href", "/projects/p1",
    );

    await userEvent.click(within(project!).getByRole("button", { name: "접근 이력 보기" }));
    expect(await within(project!).findByText("GET /projects/p1")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls[5][0]).toBe("/api/projects/p1/access-log"));
  });

  it("requires archive, reason, and the exact project name before purging", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true },
      ] }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "사용 중 원고", archived: false, owner_id: "u1" },
        { id: "p2", name: "보관 원고", archived: true, owner_id: "u1" },
      ] }))
      .mockResolvedValueOnce(response({
        projects_considered: 2,
        totals: {
          calls: 0, success: 0, provider_error: 0, parse_error: 0,
          total_tokens: 0, tokens_counted_from: 0,
          thin_headroom_calls: 0, headroom_considered: 0,
        },
        sites: [], gate: {}, loop: {},
      }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response(undefined, 204))
      .mockResolvedValueOnce(response({ events: [
        {
          id: "e2", operation_id: "op1", admin_user_id: "u1",
          action: "project_purge", target_type: "project", target_project_id: "p2",
          reason: "고객 삭제 요청", outcome: "succeeded",
          at: "2026-08-02T02:00:00Z", error_kind: null,
        },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    const active = (await screen.findByText("사용 중 원고")).closest("article");
    const archived = screen.getByText("보관 원고").closest("article");
    expect(active).not.toBeNull();
    expect(archived).not.toBeNull();
    expect(within(active!).queryByRole("button", { name: "영구 삭제 준비" })).not.toBeInTheDocument();
    expect(within(active!).getByText(/먼저 프로젝트를 보관/)).toBeInTheDocument();

    await userEvent.click(within(archived!).getByRole("button", { name: "영구 삭제 준비" }));
    // 8.2c N5=A: 경고가 **남는 것**을 말한다. 종전 문구("전체가 삭제")로 되돌리면 여기서
    // 실패한다 — 무엇이 예외인지 안 말하는 경고는 관리자가 확인할 수 없다.
    expect(within(archived!).getByText(/프로젝트 이름은 보관됩니다/)).toBeInTheDocument();
    expect(within(archived!).queryByText(/전체가 삭제되며/)).not.toBeInTheDocument();
    const purgeButton = within(archived!).getByRole("button", { name: "영구 삭제" });
    expect(purgeButton).toBeDisabled();
    await userEvent.type(within(archived!).getByLabelText("삭제 사유"), "고객 삭제 요청");
    await userEvent.type(within(archived!).getByLabelText(/확인을 위해/), "다른 이름");
    expect(purgeButton).toBeDisabled();
    await userEvent.clear(within(archived!).getByLabelText(/확인을 위해/));
    await userEvent.type(within(archived!).getByLabelText(/확인을 위해/), "보관 원고");
    expect(purgeButton).toBeEnabled();
    await userEvent.click(purgeButton);

    expect(await screen.findByRole("status")).toHaveTextContent("영구 삭제했습니다");
    expect(screen.queryByText("보관 원고")).not.toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({ reason: "고객 삭제 요청" });
    expect(fetchMock.mock.calls[4][0]).toBe("/api/admin/projects/p2/purge");
    expect(await screen.findByText("p2")).toBeInTheDocument();
  });

  it("does not offer a retry when a purge returns an ambiguous 503", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [
        { id: "u1", username: "root", is_admin: true, is_active: true },
      ] }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "보관 원고", archived: true, owner_id: "u1" },
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
      .mockResolvedValueOnce(response({ detail: "storage unavailable" }, 503));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><AdminConsole /></MemoryRouter>);
    const project = (await screen.findByText("보관 원고")).closest("article");
    expect(project).not.toBeNull();
    await userEvent.click(within(project!).getByRole("button", { name: "영구 삭제 준비" }));
    await userEvent.type(within(project!).getByLabelText("삭제 사유"), "정리 요청");
    await userEvent.type(within(project!).getByLabelText(/확인을 위해/), "보관 원고");
    await userEvent.click(within(project!).getByRole("button", { name: "영구 삭제" }));

    expect(await within(project!).findByText(/다시 시도하지 말고/)).toBeInTheDocument();
    expect(within(project!).queryByRole("button", { name: "영구 삭제" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });
});
