import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemberQuotaSection } from "./MemberQuotaSection";

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

function windowPayload(limit: number | null, used: number, resetsAt: string) {
  return {
    limit,
    used,
    remaining: limit === null ? null : Math.max(0, limit - used),
    resets_at: resetsAt,
  };
}

const DAY_RESET = "2026-08-25T15:00:00Z";
const WEEK_RESET = "2026-08-31T15:00:00Z";

/** 회원 4종 — bounded(예약 있음) · 기본 한도(정책 행 없음) · 무제한 · 정지. */
const writerRow = {
  user_id: "u1", username: "writer", is_active: true, status: "active",
  unlimited: false, remaining: 15, has_pending: true,
  daily: windowPayload(20, 5, DAY_RESET),
  weekly: windowPayload(100, 41, WEEK_RESET),
};
const starterRow = {
  user_id: "u2", username: "starter", is_active: true, status: "active",
  unlimited: false, remaining: 20, has_pending: false,
  daily: windowPayload(20, 0, DAY_RESET),
  weekly: windowPayload(100, 0, WEEK_RESET),
};
const vipRow = {
  user_id: "u3", username: "vip", is_active: true, status: "active",
  unlimited: true, remaining: null, has_pending: false,
  daily: windowPayload(null, 3, DAY_RESET),
  weekly: windowPayload(null, 9, WEEK_RESET),
};
const blockedRow = {
  user_id: "u4", username: "blocked", is_active: true, status: "suspended",
  unlimited: false, remaining: 8, has_pending: false,
  daily: windowPayload(20, 12, DAY_RESET),
  weekly: windowPayload(100, 80, WEEK_RESET),
};

const writerDetail = {
  ...writerRow, has_pending: false,
  stored_daily_limit: 20, stored_weekly_limit: 100,
  pending: {
    daily_limit: 10, weekly_limit: 50, status: "active",
    effective_at: "2026-08-25T15:00:00Z",
  },
  updated_at: "2026-08-24T09:00:00Z",
};
const starterDetail = {
  ...starterRow,
  stored_daily_limit: null, stored_weekly_limit: null,
  pending: null, updated_at: null,
};
/** 한도 변경(30/120) 성공 응답 — 사용량은 그대로, 한도만 움직인다. */
const changedDetail = {
  ...writerRow, remaining: 25, has_pending: false,
  daily: windowPayload(30, 5, DAY_RESET),
  weekly: windowPayload(120, 41, WEEK_RESET),
  stored_daily_limit: 30, stored_weekly_limit: 120,
  pending: null, updated_at: "2026-08-24T11:00:00Z",
};
const suspendedDetail = {
  ...writerRow, status: "suspended", has_pending: false,
  stored_daily_limit: 20, stored_weekly_limit: 100,
  pending: null, updated_at: "2026-08-24T11:00:00Z",
};

function listResponse() {
  return response({ policies: [writerRow, starterRow, vipRow, blockedRow] });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("MemberQuotaSection", () => {
  it("renders member rows with limits, usage, suspension, and pending wording", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(listResponse()));

    render(<MemberQuotaSection />);

    expect(await screen.findByText("writer")).toBeInTheDocument();
    expect(screen.getByText("남은 사용 15회")).toBeInTheDocument();
    expect(screen.getByText("일 5/20 · 주 41/100")).toBeInTheDocument();
    expect(screen.getByText("남은 사용 20회")).toBeInTheDocument();
    expect(screen.getByText("무제한")).toBeInTheDocument();
    expect(screen.getByText("정지됨")).toBeInTheDocument();
    expect(screen.getByText("변경 예약됨")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "한도·정지 관리" }).length,
    ).toBe(4);
  });

  it("loads the member detail on open and shows the pending reservation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail))
      .mockResolvedValueOnce(response(starterDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const writerRowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(writerRowEl).getByRole("button", { name: "한도·정지 관리" }),
    );

    expect(await within(writerRowEl).findByText(/축소 예약: 일 10 · 주 50/))
      .toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe("/api/admin/quota-policies/u1");
    expect(within(writerRowEl).getByLabelText("일일 한도")).toHaveValue("20");
    expect(within(writerRowEl).getByLabelText("주간 한도")).toHaveValue("100");

    const starterRowEl = screen.getByText("starter").closest("li")!;
    await userEvent.click(
      within(starterRowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    expect(await within(starterRowEl)
      .findByText("저장된 정책 없음 — 기본 한도로 운영 중입니다."))
      .toBeInTheDocument();

    // 닫으면 그 회원의 패널만 사라진다(starter 패널은 그대로).
    await userEvent.click(
      within(writerRowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    expect(within(writerRowEl).queryByLabelText("일일 한도"))
      .not.toBeInTheDocument();
    expect(within(starterRowEl).getByLabelText("일일 한도"))
      .toBeInTheDocument();
  });

  it("sends both windows on a limit change and applies the response", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail))
      .mockResolvedValueOnce(response(changedDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const rowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    const daily = await within(rowEl).findByLabelText("일일 한도");
    await userEvent.clear(daily);
    await userEvent.type(daily, "30");
    await userEvent.type(within(rowEl).getByLabelText("사유"), "이벤트 완화");
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도 변경" }),
    );

    // 대체 의미론 가드: 한 창만 바꿔도 두 창이 모두 실린다(weekly=100 프리필).
    expect(fetchMock.mock.calls[2][0]).toBe("/api/admin/quota-policies/u1/limits");
    expect(fetchMock.mock.calls[2][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      daily_limit: 30, weekly_limit: 100, reason: "이벤트 완화",
    });
    expect(await within(rowEl).findByText("일 5/30 · 주 41/120"))
      .toBeInTheDocument();
    expect(within(rowEl).getByLabelText("일일 한도")).toHaveValue("30");
  });

  it("disables submission for blank reason, unparsable limits, or both unlimited", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const rowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    const daily = await within(rowEl).findByLabelText("일일 한도");
    const change = () => within(rowEl).getByRole("button", { name: "한도 변경" });
    const suspend = () => within(rowEl).getByRole("button", { name: "정지" });

    // 사유 없음 — 정지·한도 변경 둘 다 막힌다.
    expect(change()).toBeDisabled();
    expect(suspend()).toBeDisabled();

    await userEvent.type(within(rowEl).getByLabelText("사유"), "정산");
    expect(change()).toBeEnabled();
    expect(suspend()).toBeEnabled();

    // 일일 한도가 빈 칸이면 한도 변경만 막힌다(정지는 한도와 무관).
    await userEvent.clear(daily);
    expect(change()).toBeDisabled();
    expect(suspend()).toBeEnabled();
    expect(within(rowEl)
      .getByText("창마다 숫자 한도를 하나 이상 입력해야 합니다."))
      .toBeInTheDocument();

    // 해석 불가 숫자도 같은 자리에서 걸린다.
    await userEvent.type(daily, "abc");
    expect(change()).toBeDisabled();

    // 둘 다 무제한이면 본문이 {null, null} 이 되므로 제출할 수 없다.
    await userEvent.clear(daily);
    await userEvent.click(within(rowEl).getByLabelText("일일 무제한"));
    await userEvent.click(within(rowEl).getByLabelText("주간 무제한"));
    expect(change()).toBeDisabled();

    await userEvent.click(within(rowEl).getByLabelText("일일 무제한"));
    await userEvent.type(daily, "20");
    expect(change()).toBeEnabled();
  });

  it("shows a server 422 and re-reads the member after a failed change", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail))
      .mockResolvedValueOnce(
        response({ detail: "Input should be a valid integer" }, 422),
      )
      .mockResolvedValueOnce(response(writerDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const rowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    // 소수는 클라이언트를 통과한다 — 타입 오류(StrictInt)는 서버의 것이다.
    const daily = await within(rowEl).findByLabelText("일일 한도");
    await userEvent.clear(daily);
    await userEvent.type(daily, "7.5");
    await userEvent.type(within(rowEl).getByLabelText("사유"), "시험");
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도 변경" }),
    );

    expect(await within(rowEl)
      .findByText("422: Input should be a valid integer"))
      .toBeInTheDocument();
    // H2: 감사 쓰기 실패와 달리 422 는 적용 안 됐을 것이지만, 화면은 다시 읽는다.
    expect(fetchMock.mock.calls[3][0]).toBe("/api/admin/quota-policies/u1");
    expect(within(rowEl).getByLabelText("일일 한도")).toHaveValue("20");
  });

  it("suspends and re-activates a member with the audit reason", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail))
      .mockResolvedValueOnce(response(suspendedDetail))
      .mockResolvedValueOnce(response(writerDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const rowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    await userEvent.type(
      await within(rowEl).findByLabelText("사유"),
      "약관 위반",
    );
    await userEvent.click(within(rowEl).getByRole("button", { name: "정지" }));

    expect(fetchMock.mock.calls[2][0])
      .toBe("/api/admin/quota-policies/u1/suspend");
    expect(JSON.parse(fetchMock.mock.calls[2][1].body))
      .toEqual({ reason: "약관 위반" });
    expect(await within(rowEl).findByText("정지됨")).toBeInTheDocument();

    const release = await within(rowEl)
      .findByRole("button", { name: "정지 해제" });
    await userEvent.click(release);
    expect(fetchMock.mock.calls[3][0])
      .toBe("/api/admin/quota-policies/u1/activate");
    expect(JSON.parse(fetchMock.mock.calls[3][1].body))
      .toEqual({ reason: "약관 위반" });
    expect(await within(rowEl).findByText("남은 사용 15회"))
      .toBeInTheDocument();
  });

  it("shows the server's self-suspend rejection and re-reads the member", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(listResponse())
      .mockResolvedValueOnce(response(writerDetail))
      .mockResolvedValueOnce(response(
        { detail: "administrators cannot suspend their own quota" }, 400,
      ))
      .mockResolvedValueOnce(response(writerDetail));
    vi.stubGlobal("fetch", fetchMock);

    render(<MemberQuotaSection />);
    const rowEl = (await screen.findByText("writer")).closest("li")!;
    await userEvent.click(
      within(rowEl).getByRole("button", { name: "한도·정지 관리" }),
    );
    await userEvent.type(
      await within(rowEl).findByLabelText("사유"),
      "셀프",
    );
    await userEvent.click(within(rowEl).getByRole("button", { name: "정지" }));

    expect(await within(rowEl).findByText(
      "400: administrators cannot suspend their own quota",
    )).toBeInTheDocument();
    expect(fetchMock.mock.calls[3][0]).toBe("/api/admin/quota-policies/u1");
  });
});
