/**
 * 계정 탈퇴 화면 — Slice 4 (오너 결정 2026-09-10: D1=ⓐ 전역 배너 · D2=ⓐ 4b 분리).
 *
 * **무엇을 잠그는가.** 이 슬라이스가 옮긴 계약은 셋이고 전부 *조용히 어긋날 수 있는*
 * 것들이다:
 *
 * 1. **배너는 앱 셸에 있다**(D1=ⓐ). D1=ⓒ 가 쓰기를 전 화면에서 403 으로 막으므로,
 *    배너를 `/me` 안으로 옮기면 편집기의 403 이 다시 정체불명이 된다.
 * 2. **남은 일수는 서버의 `purge_due_at` 에서만 나온다.** 프런트가 30 을 박으면 두
 *    번째 정본이 생기고, 상수를 고친 날 화면만 다른 날을 말한다.
 * 3. **상태는 한 벌이다.** `/me` 의 취소가 셸의 배너를 끈다 — 두 자리가 각자
 *    조회하면 취소한 뒤에도 배너가 남는다.
 *
 * **양방향**:
 * - under-strict — 배너를 화면 안으로 옮기면 "다른 경로에서도 뜬다" 셀이 실패한다 ·
 *   남은 일수를 30 으로 박으면 "서버가 준 날짜만 말한다" 셀이 실패한다(픽스처가
 *   일부러 **3일** 뒤다) · 상태를 두 벌로 나누면 "취소가 배너를 끈다" 셀이 실패한다.
 * - over-strict — 확인 입력이 맞아도 계속 잠가 두면 "사용자명을 맞추면 열린다" 셀이
 *   실패하고, 409 를 오류로 말하면 "마지막 관리자 409 는 사람 말로" · "취소 409 는
 *   오류가 아니다" 두 셀이 각각 실패한다. **409 를 전부 같은 말로 뭉개도** 그 둘이
 *   서로를 문다(요청 409 = 마지막 관리자 · 취소 409 = 취소할 것이 없음).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthUserContext } from "../auth/AuthGate";
import { PersonalHubPage } from "./PersonalHubPage";
import {
  WithdrawalBanner,
  WithdrawalProvider,
  remainingGraceDays,
  resetWithdrawal,
  seedWithdrawal,
} from "./withdrawal";
import { resetMemberQuota, seedMemberQuota } from "../quota/useMemberQuota";

const USER = { id: "u1", username: "alice", is_admin: false };

/** 서버가 준 파기 예정 시각 — **30일이 아니라 3일 뒤**다(상수 박기 방지). */
const DUE_IN_THREE_DAYS = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
const WITHDRAWING = {
  withdrawal_requested_at: "2026-09-10T01:00:00Z",
  purge_due_at: DUE_IN_THREE_DAYS,
};
const NOT_WITHDRAWING = { withdrawal_requested_at: null, purge_due_at: null };

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, statusText: "", json: async () => body };
}

/**
 * `/projects`·`/me/activity` 는 허브가 마운트에 부르는 보조 조회다 — 기록된
 * 시퀀스를 건드리지 않게 가로채고, 나머지만 mock 이 센다(`App.test.tsx` 선례).
 */
function stubFetch(...queued: Array<{ body: unknown; status?: number }>) {
  const fetchMock = vi.fn();
  for (const next of queued) {
    fetchMock.mockResolvedValueOnce(response(next.body, next.status));
  }
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const target = String(url);
    if (target.includes("/me/activity")) return Promise.resolve(response({ events: [] }));
    if (target.endsWith("/projects")) return Promise.resolve(response({ projects: [] }));
    return fetchMock(url, init);
  });
  return fetchMock;
}

beforeEach(() => {
  seedMemberQuota({
    remaining: 7, unlimited: false, status: "active",
    daily: { limit: 20, used: 13, remaining: 7, resets_at: null },
    weekly: { limit: 100, used: 41, remaining: 59, resets_at: null },
  } as never);
});

afterEach(() => {
  resetMemberQuota();
  resetWithdrawal();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** 앱 셸의 모양 — 배너는 화면 **밖**, 라우팅되는 화면은 그 안이다. */
function renderShell(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthUserContext.Provider value={USER}>
        <WithdrawalProvider>
          <WithdrawalBanner />
          <Routes>
            <Route path="/me" element={<PersonalHubPage />} />
            <Route path="/projects/:projectId" element={<p>원고 작업 공간</p>} />
          </Routes>
        </WithdrawalProvider>
      </AuthUserContext.Provider>
    </MemoryRouter>,
  );
}

describe("남은 일수 (서버 purge_due_at 만이 정본)", () => {
  it("counts the days left from the server's due date, never from a hard-coded 30", () => {
    const now = new Date("2026-09-10T00:00:00Z");
    expect(remainingGraceDays(
      { withdrawal_requested_at: "2026-09-10T00:00:00Z", purge_due_at: "2026-09-13T00:00:00Z" },
      now,
    )).toBe(3);
    // 같은 요청 시각인데 예정일만 다르다 — 30 을 박으면 둘이 같은 수가 되어 실패한다.
    expect(remainingGraceDays(
      { withdrawal_requested_at: "2026-09-10T00:00:00Z", purge_due_at: "2026-10-10T00:00:00Z" },
      now,
    )).toBe(30);
  });

  it("rounds up so the last partial day still reads as a day left to cancel", () => {
    const now = new Date("2026-09-10T00:00:00Z");
    // 0.2일 남았어도 서버 판정은 `now >= purge_due_at` 이라 아직 파기 전이다.
    expect(remainingGraceDays(
      { withdrawal_requested_at: "x", purge_due_at: "2026-09-10T05:00:00Z" }, now,
    )).toBe(1);
  });

  it("never goes negative, and says nothing at all when the account is not withdrawing", () => {
    const now = new Date("2026-09-10T00:00:00Z");
    expect(remainingGraceDays(
      { withdrawal_requested_at: "x", purge_due_at: "2026-09-01T00:00:00Z" }, now,
    )).toBe(0);
    expect(remainingGraceDays(NOT_WITHDRAWING, now)).toBeNull();
    expect(remainingGraceDays(null, now)).toBeNull();
  });
});

describe("전역 배너 (D1=ⓐ)", () => {
  it("says why writing is blocked on a screen that is not the personal hub", async () => {
    seedWithdrawal(WITHDRAWING);
    stubFetch();

    renderShell("/projects/p1");

    // ★ 이 셀이 D1=ⓐ 를 잠근다 — 배너를 `/me` 안으로 옮기면 여기서 사라진다.
    expect(await screen.findByRole("status")).toHaveTextContent("저장·생성이 되지 않습니다");
    expect(screen.getByRole("status")).toHaveTextContent("남은 기간 3일");
    expect(screen.getByRole("button", { name: "탈퇴 취소" })).toBeInTheDocument();
  });

  it("stays out of the way when the account is not withdrawing", () => {
    seedWithdrawal(NOT_WITHDRAWING);
    stubFetch();

    renderShell("/projects/p1");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reads the grace state once on mount when nothing was seeded", async () => {
    resetWithdrawal();
    const fetchMock = stubFetch({ body: WITHDRAWING });

    renderShell("/projects/p1");

    expect(await screen.findByRole("status")).toHaveTextContent("남은 기간 3일");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/me/withdrawal");
  });
});

describe("탈퇴 요청 (`/me`)", () => {
  it("keeps the irreversible action shut until the username is typed back", async () => {
    seedWithdrawal(NOT_WITHDRAWING);
    stubFetch();
    const user = userEvent.setup();

    renderShell("/me");

    await user.click(await screen.findByRole("button", { name: "계정 탈퇴…" }));
    const confirm = screen.getByRole("button", { name: "탈퇴 요청" });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(/사용자명/), "alic");
    expect(confirm).toBeDisabled();

    // over-strict 방향: 맞게 입력해도 잠겨 있으면 여기서 실패한다.
    await user.type(screen.getByLabelText(/사용자명/), "e");
    expect(confirm).toBeEnabled();
  });

  it("turns the request into the shell banner without a second read", async () => {
    seedWithdrawal(NOT_WITHDRAWING);
    const fetchMock = stubFetch({ body: WITHDRAWING });
    const user = userEvent.setup();

    renderShell("/me");

    await user.click(await screen.findByRole("button", { name: "계정 탈퇴…" }));
    await user.type(screen.getByLabelText(/사용자명/), "alice");
    await user.click(screen.getByRole("button", { name: "탈퇴 요청" }));

    expect(await screen.findByRole("status")).toHaveTextContent("남은 기간 3일");
    // 응답을 그대로 상태에 밀어 넣는다 — POST 하나뿐이고 뒤따르는 GET 이 없다.
    await waitFor(() => expect(fetchMock.mock.calls).toHaveLength(1));
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("puts the last-administrator refusal in words instead of leaking the status code", async () => {
    seedWithdrawal(NOT_WITHDRAWING);
    stubFetch({ body: { detail: "cannot deactivate the last active administrator" }, status: 409 });
    const user = userEvent.setup();

    renderShell("/me");

    await user.click(await screen.findByRole("button", { name: "계정 탈퇴…" }));
    await user.type(screen.getByLabelText(/사용자명/), "alice");
    await user.click(screen.getByRole("button", { name: "탈퇴 요청" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("마지막 활성 관리자");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("탈퇴 취소", () => {
  it("clears the shell banner when the hub cancels — one state, not two", async () => {
    seedWithdrawal(WITHDRAWING);
    stubFetch({ body: NOT_WITHDRAWING });
    const user = userEvent.setup();

    renderShell("/me");

    expect(await screen.findByRole("status")).toBeInTheDocument();
    // 허브 절의 취소를 누른다(배너의 것과 이름이 같으므로 마지막 것을 고른다).
    const buttons = screen.getAllByRole("button", { name: "탈퇴 취소" });
    await user.click(buttons[buttons.length - 1]);

    // ★ 상태가 두 벌이면 배너가 남는다.
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: "계정 탈퇴…" })).toBeInTheDocument();
  });

  it("treats a 409 as nothing left to cancel, not as an error", async () => {
    seedWithdrawal(WITHDRAWING);
    // 다른 탭이 먼저 취소했다 — DELETE 409 뒤에 서버의 지금 상태를 다시 읽는다.
    stubFetch(
      { body: { detail: "withdrawal was not requested" }, status: 409 },
      { body: NOT_WITHDRAWING },
    );
    const user = userEvent.setup();

    renderShell("/me");

    const banner = await screen.findByRole("status");
    await user.click(within(banner).getByRole("button", { name: "탈퇴 취소" }));

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    // 오류로 말하지 않는다 — 409 를 `describeApiError` 로 넘기면 여기서 실패한다.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
