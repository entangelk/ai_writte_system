import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ObservabilityDashboard } from "./ObservabilityDashboard";

/**
 * This screen's real job is not "show numbers" — it is to keep three values
 * from being misread (SoT v1.7.48). Each defence is locked below, because a
 * plain render of the same payload would look correct and mean the wrong thing.
 */

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

function site(overrides: Record<string, unknown> = {}) {
  return {
    call_site: "writing_gate",
    calls: 4,
    success: 3,
    provider_error: 1,
    parse_error: 0,
    total_tokens: 900,
    tokens_counted_from: 3,
    avg_latency_ms: 820,
    correlations: 3,
    multi_call_correlations: 1,
    ...overrides,
  };
}

function kpiBody(overrides: Record<string, unknown> = {}) {
  return {
    project_id: "p1",
    totals: {
      calls: 4,
      success: 3,
      provider_error: 1,
      parse_error: 0,
      total_tokens: 900,
      tokens_counted_from: 3,
    },
    sites: [site()],
    gate: { scored_calls: 3, avg_quality_score: 0.8 },
    loop: { runs_considered: 2, non_convergence_rate: 0.5 },
    ...overrides,
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/projects/p1/observability"]}>
      <Routes>
        <Route
          path="/projects/:projectId/observability"
          element={<ObservabilityDashboard />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ObservabilityDashboard", () => {
  it("reads the KPI endpoint through the single /api origin", async () => {
    const fetchMock = mockFetch({ body: kpiBody() });
    renderDashboard();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p1/observability/kpi");
  });

  it("renders the summary and one row per call site", async () => {
    mockFetch({
      body: kpiBody({
        sites: [site({ call_site: "compare_judge" }), site()],
      }),
    });
    renderDashboard();

    expect(await screen.findByText("작성 게이트")).toBeInTheDocument();
    expect(screen.getByText("비교 판정")).toBeInTheDocument();
    const summary = screen.getByLabelText("전체 요약");
    expect(within(summary).getByText("75%")).toBeInTheDocument();
  });

  it("labels a null gate score as unmeasured, never as zero", async () => {
    // Defence 1. A bare render would print 0 (or an empty cell) and the owner
    // would read "the gate rates every draft as worthless".
    mockFetch({
      body: kpiBody({ gate: { scored_calls: 0, avg_quality_score: null } }),
    });
    renderDashboard();

    expect(await screen.findByText("측정된 호출 없음")).toBeInTheDocument();
    const summary = screen.getByLabelText("전체 요약");
    expect(within(summary).queryByText("0.00")).not.toBeInTheDocument();
  });

  it("says the loop audit is off rather than showing a zero rate", async () => {
    // Defence 2, and the load-bearing one: the loop audit is opt-in and off by
    // default, so this is the normal state of a default deployment. Printing
    // 0% here would claim the loop never failed to converge.
    mockFetch({
      body: kpiBody({
        loop: { runs_considered: 0, non_convergence_rate: null },
      }),
    });
    renderDashboard();

    expect(
      await screen.findByText("루프 감사가 꺼져 있어 측정되지 않음"),
    ).toBeInTheDocument();
    const summary = screen.getByLabelText("전체 요약");
    expect(within(summary).queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows the token denominator next to the token total", async () => {
    // Defence 3: provider errors carry no usable token count and are excluded,
    // so the total is over fewer rows than `calls`.
    mockFetch({ body: kpiBody() });
    renderDashboard();

    expect(
      await screen.findByText("3건 기준 (응답 없는 호출 제외)"),
    ).toBeInTheDocument();
  });

  it("does not call the extra-call column a retry count", async () => {
    // The column that is a repair count at repair-shaped sites but a designed
    // round inside the writing loop. Naming it "재시도" would report normal
    // loop rounds as failures.
    mockFetch({ body: kpiBody() });
    renderDashboard();

    expect(
      await screen.findByText("여러 번 호출된 워크플로"),
    ).toBeInTheDocument();
    expect(screen.queryByText("재시도")).not.toBeInTheDocument();
  });

  it("keeps the server's site order instead of re-sorting", async () => {
    // The API guarantees the order (SoT v1.7.48); re-sorting here would make
    // the screen disagree with the contract the dashboard is built on.
    mockFetch({
      body: kpiBody({
        sites: [
          site({ call_site: "writing_gate" }),
          site({ call_site: "compare_judge" }),
        ],
      }),
    });
    renderDashboard();

    await screen.findByText("작성 게이트");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("작성 게이트");
    expect(rows[1]).toHaveTextContent("비교 판정");
  });

  it("renders every numeric column the API returns", async () => {
    mockFetch({ body: kpiBody() });
    renderDashboard();

    await screen.findByText("작성 게이트");
    const row = screen.getAllByRole("row")[1];
    for (const value of ["4", "3", "1", "0", "900", "820"]) {
      expect(within(row).getAllByText(value).length).toBeGreaterThan(0);
    }
  });

  it("shows an empty state instead of charts when nothing was recorded", async () => {
    mockFetch({
      body: kpiBody({
        sites: [],
        totals: {
          calls: 0,
          success: 0,
          provider_error: 0,
          parse_error: 0,
          total_tokens: 0,
          tokens_counted_from: 0,
        },
        gate: { scored_calls: 0, avg_quality_score: null },
        loop: { runs_considered: 0, non_convergence_rate: null },
      }),
    });
    renderDashboard();

    expect(
      await screen.findByText("아직 기록된 LLM 호출이 없습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("surfaces an API failure instead of rendering an empty dashboard", async () => {
    mockFetch({ status: 404, body: { detail: "project not found" } });
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "project not found",
    );
    expect(screen.queryByLabelText("전체 요약")).not.toBeInTheDocument();
  });
});
