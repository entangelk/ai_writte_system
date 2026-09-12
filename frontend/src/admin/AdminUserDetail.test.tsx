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
  { id: "u1", username: "root", is_admin: true, is_active: true, status: "active", withdrawal_requested_at: null, purge_started_at: null },
  { id: "u2", username: "alice", is_admin: false, is_active: true, status: "active", withdrawal_requested_at: null, purge_started_at: null },
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
      // 관리자 아카이브(2026-08-28) — 사용 중 카드를 보관으로 바꾸는 호출.
      .mockResolvedValueOnce(response({
        id: "p1", name: "사용 중 원고", archived: true, owner_id: "u2",
      }))
      .mockResolvedValueOnce(response(undefined, 204));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();
    const active = (await screen.findByText("사용 중 원고")).closest("article");
    const archived = screen.getByText("보관 원고").closest("article");
    expect(active).not.toBeNull();
    expect(archived).not.toBeNull();
    expect(within(active!).queryByRole("button", { name: "영구 삭제 준비" })).not.toBeInTheDocument();
    // 보관 진입점이 이 카드에 있다 — 종전엔 안내 문구만 있어 purge 도달이
    // 구조적으로 막혀 있었다(2026-08-28).
    const archiveButton = within(active!).getByRole("button", { name: "보관으로 전환" });
    await userEvent.click(archiveButton);
    expect(fetchMock.mock.calls[2][0]).toBe("/api/admin/projects/p1/archive");
    // 보관되면 같은 카드에 purge 면이 열린다.
    expect(await within(active!).findByRole("button", { name: "영구 삭제 준비" }))
      .toBeInTheDocument();

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
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ reason: "고객 삭제 요청" });
    expect(fetchMock.mock.calls[3][0]).toBe("/api/admin/projects/p2/purge");
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
        withdrawal_requested_at: null, purge_started_at: null
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

  // --- 잔여 정리(계정 탈퇴 Slice 4b, 2026-09-12 — 오너 ①ⓐ·②ⓐ·③ⓐ) ----------

  const STALLED_USER = {
    id: "u9", username: "stalled", is_admin: false, is_active: true,
    status: "active",
    withdrawal_requested_at: "2026-08-10T00:00:00Z",
    purge_started_at: "2026-09-10T00:00:00Z",
  };

  it("keeps the reconcile section off accounts without a purge stamp", async () => {
    // over-strict: 파기가 시작되지 않은 계정(유예 중 포함)에 정리 UI 를
    // 제안하면 대상 아닌 계정에서 409 만나는 화면이 된다 — 섹션 자체가 없다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        users: [{ ...USERS[1], withdrawal_requested_at: "2026-09-01T00:00:00Z" }],
      }))
      .mockResolvedValueOnce(response({ projects: [] }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail();

    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
    expect(screen.getByText("탈퇴 유예")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "잔여 정리" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "잔여 조사" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("surveys first, then executes only on the exact username", async () => {
    // ②ⓐ: 조사(파괴 없음) → 결과 확인 → 사유·사용자명 입력 → 실행.
    // under: 확인 절차를 통째로 걷어도 POST 만 남아 초록이 되지 않게, 조사
    // 응답 전에는 실행 버튼이 존재하지 않는 것까지 잠근다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [USERS[0], STALLED_USER] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        leftover_projects: [], has_username_tombstone: true,
      }))
      .mockResolvedValueOnce(response({
        leftover_projects: [],
        swept: { sessions: 2, request_quota_policies: 1 },
        has_username_tombstone: true,
        removed_user_row: true,
      }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail("u9");

    expect(await screen.findByText("파기 진행")).toBeInTheDocument();
    // 조사 전에는 실행 컨트롤이 아직 없다 — 무엇이 지워질지 모르는 실행은 없다.
    expect(screen.queryByRole("button", { name: "잔여 정리 실행" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "잔여 조사" }));

    expect(await screen.findByRole("heading", { name: "조사 결과" })).toBeInTheDocument();
    expect(screen.getByText("남은 프로젝트가 없습니다.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2][0]).toBe("/api/admin/users/u9/reconcile");
    expect(fetchMock.mock.calls[2][1].method).toBeUndefined(); // GET — 파괴 없음

    // 사유만으로는 부족하다 — 확인 입력이 사용자명과 다르면 잠긴 채로 남는다.
    await userEvent.type(screen.getByLabelText("정리 사유"), "데몬 실패 수습");
    const execute = screen.getByRole("button", { name: "잔여 정리 실행" });
    expect(execute).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText(/확인을 위해 stalled 입력/), "stalled",
    );
    expect(screen.getByRole("button", { name: "잔여 정리 실행" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "잔여 정리 실행" }));

    expect(await screen.findByRole("heading", { name: "정리 결과" })).toBeInTheDocument();
    expect(screen.getByText("sessions")).toBeInTheDocument();
    expect(screen.getByText("2건 삭제")).toBeInTheDocument();
    expect(screen.getByText(/계정 행을 삭제했습니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "사용자 목록으로" }))
      .toHaveAttribute("href", "/admin");
    const [url, init] = fetchMock.mock.calls[3];
    expect(url).toBe("/api/admin/users/u9/reconcile");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ reason: "데몬 실패 수습" });
  });

  it("reports leftover projects from the survey instead of hiding them", async () => {
    // 프로젝트가 남아 있으면 계정 행이 유지된다 — 조사가 그 사실을 말해야
    // 관리자가 "실행했는데 왜 계정이 남지"라고 묻지 않는다.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [USERS[0], STALLED_USER] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response({
        leftover_projects: ["p1"], has_username_tombstone: true,
      }));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail("u9");

    await userEvent.click(await screen.findByRole("button", { name: "잔여 조사" }));

    expect(await screen.findByText("p1")).toBeInTheDocument();
    expect(screen.getByText(/프로젝트가 남아 있어 계정 행은 유지됩니다/))
      .toBeInTheDocument();
  });

  it("surfaces a 409 survey answer without offering execution", async () => {
    // 유예 만료 청구 등으로 대상이 아니게 된 순간 서버는 409 — 화면은 그 말을
    // 그대로 전하고 확인 절차를 열지 않는다(H3: detail 분기 금지, 상태코드로).
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ users: [USERS[0], STALLED_USER] }))
      .mockResolvedValueOnce(response({ projects: [] }))
      .mockResolvedValueOnce(response(
        { detail: "purge has not started for this account" }, 409,
      ));
    vi.stubGlobal("fetch", fetchMock);

    renderDetail("u9");

    await userEvent.click(await screen.findByRole("button", { name: "잔여 조사" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /purge has not started/,
    );
    expect(screen.queryByRole("heading", { name: "조사 결과" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "잔여 정리 실행" })).not.toBeInTheDocument();
  });
});
