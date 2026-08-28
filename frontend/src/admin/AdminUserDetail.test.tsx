import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminUserDetail } from "./AdminUserDetail";

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

function renderDetail(userId = "u2") {
  return render(
    <MemoryRouter initialEntries={[`/admin/users/${userId}`]}>
      <Routes>
        <Route path="/admin/users/:userId" element={<AdminUserDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

const USERS = [
  { id: "u1", username: "root", is_admin: true, is_active: true, status: "active" },
  { id: "u2", username: "alice", is_admin: false, is_active: true, status: "active" },
];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AdminUserDetail", () => {
  it("shows only this user's projects and filters them by name", async () => {
    // 오너 2026-08-27: 전 프로젝트 평면 목록을 사람 단위로 쪼갠 자리다.
    // under-strict: 소유자 필터를 잃으면 남의 프로젝트가 여기 뜬다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "겨울 이야기", archived: false, owner_id: "u2" },
        { id: "p2", name: "여름 이야기", archived: false, owner_id: "u2" },
        { id: "p3", name: "남의 원고", archived: false, owner_id: "u1" },
        { id: "p4", name: "주인 없는 원고", archived: false, owner_id: null },
      ] }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();

    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "alice" }).closest("section"))
      .toHaveClass("admin-user-detail");
    expect(screen.getByText("겨울 이야기")).toBeInTheDocument();
    expect(screen.getByText("여름 이야기")).toBeInTheDocument();
    expect(screen.queryByText("남의 원고")).not.toBeInTheDocument();
    expect(screen.queryByText("주인 없는 원고")).not.toBeInTheDocument();
    expect(screen.getByText("겨울 이야기").closest(".admin-projects"))
      .toHaveClass("admin-user-project-list");
    expect(screen.getByRole("button", { name: "비활성화" }).closest(".row-actions"))
      .toHaveClass("admin-user-account-actions");

    await userEvent.type(screen.getByLabelText("프로젝트 검색"), "겨울");
    expect(screen.getByText("겨울 이야기")).toBeInTheDocument();
    expect(screen.queryByText("여름 이야기")).not.toBeInTheDocument();
    // 검색은 화면만 좁힌다 — 서버를 다시 치지 않는다.
    expect(fetchMock).toHaveBeenCalledTimes(2);

    expect(screen.getByRole("link", { name: "← 관리로 돌아가기" }))
      .toHaveAttribute("href", "/admin");
  });

  it("requires a reason, issues a grant, then reads the audited access history", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "겨울 이야기", archived: false, owner_id: "u2" },
      ] }))
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

    renderDetail();
    const project = (await screen.findByText("겨울 이야기")).closest("article");
    expect(project).not.toBeNull();
    const grantButton = within(project!).getByRole("button", { name: "1시간 읽기 권한 발급" });
    expect(grantButton).toBeDisabled();

    await userEvent.type(within(project!).getByLabelText("접근 사유"), "지원 요청 확인");
    await userEvent.click(grantButton);

    expect(await within(project!).findByText(/권한 만료/)).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ reason: "지원 요청 확인" });
    expect(within(project!).getByRole("link", { name: "프로젝트 열기" })).toHaveAttribute(
      "href", "/projects/p1",
    );

    await userEvent.click(within(project!).getByRole("button", { name: "접근 이력 보기" }));
    expect(await within(project!).findByText("GET /projects/p1")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls[3][0]).toBe("/api/projects/p1/access-log"));
  });

  it("requires archive, reason, and the exact project name before purging", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "사용 중 원고", archived: false, owner_id: "u2" },
        { id: "p2", name: "보관 원고", archived: true, owner_id: "u2" },
      ] }))
      .mockResolvedValueOnce(response(undefined, 204));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();
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
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ reason: "고객 삭제 요청" });
    expect(fetchMock.mock.calls[2][0]).toBe("/api/admin/projects/p2/purge");
  });

  it("does not offer a retry when a purge returns an ambiguous 503", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [
        { id: "p1", name: "보관 원고", archived: true, owner_id: "u2" },
      ] }))
      .mockResolvedValueOnce(response({ detail: "storage unavailable" }, 503));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();
    const project = (await screen.findByText("보관 원고")).closest("article");
    expect(project).not.toBeNull();
    await userEvent.click(within(project!).getByRole("button", { name: "영구 삭제 준비" }));
    await userEvent.type(within(project!).getByLabelText("삭제 사유"), "정리 요청");
    await userEvent.type(within(project!).getByLabelText(/확인을 위해/), "보관 원고");
    await userEvent.click(within(project!).getByRole("button", { name: "영구 삭제" }));

    expect(await within(project!).findByText(/다시 시도하지 말고/)).toBeInTheDocument();
    expect(within(project!).queryByRole("button", { name: "영구 삭제" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("deactivates the account and keeps the returned state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        id: "u2", username: "alice", is_admin: false, is_active: false,
        status: "active",
      }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();
    await screen.findByRole("heading", { name: "alice" });
    expect(screen.getByText("활성")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "비활성화" }));

    expect(await screen.findByText("비활성")).toBeInTheDocument();
    // 단방향(D6): 비활성화된 계정에는 그 버튼이 다시 보이지 않는다.
    expect(screen.queryByRole("button", { name: "비활성화" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/admin/users/u2/deactivate");
  });

  it("says so plainly when the user id is unknown", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: USERS }))
      .mockResolvedValueOnce(response({ projects: [] }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail("ghost");

    expect(await screen.findByText("그런 사용자가 없습니다.")).toBeInTheDocument();
  });
});
