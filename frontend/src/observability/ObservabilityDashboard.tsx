import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  describeApiError,
  getObservabilityKpi,
  type ObservabilityKpi,
  type ObservabilityKpiSite,
} from "../api/client";

// The KPI payload carries three values that are misread when drawn naively, and
// the contract (SoT v1.7.48) states each of them. The screen inherits that
// defence — a dashboard that renders them as plain numbers visualises the
// misreading:
//
// 1. `gate.avg_quality_score === null` is "no call carried a score", not
//    "quality is zero". Its denominator is `scored_calls`, which excludes gate
//    calls made inside the revise loop.
// 2. `loop.non_convergence_rate === null` is "the loop audit is off", not "the
//    loop never diverged" — that audit is opt-in and off by default, so null is
//    the normal state of a default deployment.
// 3. `multi_call_correlations` is not a retry count. At a repair-shaped site it
//    is one; inside the writing loop the extra calls are designed rounds
//    (the gate runs up to three times per request).
//
// Ordering and rounding are guaranteed by the API, so nothing here re-sorts or
// re-rounds.

const SITE_LABELS: Record<string, string> = {
  analysis_extractor: "분석 추출",
  compare_judge: "비교 판정",
  query_planner: "검색 계획",
  writing_gate: "작성 게이트",
  writing_generation: "본문 생성",
  writing_report: "자기 보고",
  writing_retrieval_planner: "루프 검색 계획",
  writing_revision: "본문 수정",
};

function siteLabel(callSite: string): string {
  return SITE_LABELS[callSite] ?? callSite;
}

// Validated against this app's paper surface (#f4f0e7) with the dataviz
// validator: lightness band, chroma floor, all-pairs CVD separation, normal
// vision floor and 3:1 contrast all pass. Green was the intuitive pick for
// "success" but green↔amber collapses under protanopia (ΔE 2.4), so success
// takes the blue slot. Identity is never colour alone — every series is in the
// legend and repeated in the table below.
const OUTCOME_COLORS = {
  success: "#1a6d99",
  providerError: "#9d2f2f",
  parseError: "#a8742a",
} as const;

function percent(part: number, whole: number): string {
  if (whole === 0) return "—";
  return `${Math.round((part / whole) * 1000) / 10}%`;
}

function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

type ChartRow = {
  site: string;
  성공: number;
  provider_error: number;
  parse_error: number;
  tokens: number;
};

function chartRows(sites: ObservabilityKpiSite[]): ChartRow[] {
  return sites.map((site) => ({
    site: siteLabel(site.call_site),
    성공: site.success,
    provider_error: site.provider_error,
    parse_error: site.parse_error,
    tokens: site.total_tokens,
  }));
}

export function ObservabilityDashboard() {
  const { projectId } = useParams<{ projectId: string }>();
  const [kpi, setKpi] = useState<ObservabilityKpi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (projectId === undefined) return;
    let cancelled = false;
    setLoading(true);
    getObservabilityKpi(projectId)
      .then((response) => {
        if (!cancelled) setKpi(response);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const rows = kpi === null ? [] : chartRows(kpi.sites);

  return (
    <section className="workspace-page page-enter">
      <Link className="back-link" to={`/projects/${projectId}`}>
        ← 원고 목록
      </Link>
      <header className="page-heading">
        <p className="eyebrow">파이프라인 관측</p>
        <h1>LLM 호출 지표</h1>
      </header>

      {error !== null && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {loading && <p className="status-copy">지표를 불러오는 중…</p>}

      {kpi !== null && !loading && (
        <>
          <dl className="kpi-summary" aria-label="전체 요약">
            <div>
              <dt>LLM 호출</dt>
              <dd>{kpi.totals.calls}</dd>
            </div>
            <div>
              <dt>성공률</dt>
              <dd>{percent(kpi.totals.success, kpi.totals.calls)}</dd>
            </div>
            <div>
              <dt>토큰 합계</dt>
              <dd>{kpi.totals.total_tokens}</dd>
              {/* The denominator is part of the number's meaning: provider
                  errors carry no usable token count and are excluded. */}
              <p className="kpi-note">
                {kpi.totals.tokens_counted_from}건 기준 (응답 없는 호출 제외)
              </p>
            </div>
            <div>
              <dt>게이트 판정 점수</dt>
              <dd>{score(kpi.gate.avg_quality_score)}</dd>
              <p className="kpi-note">
                {kpi.gate.avg_quality_score === null
                  ? "측정된 호출 없음"
                  : `${kpi.gate.scored_calls}건 기준 (루프 내부 호출 제외)`}
              </p>
            </div>
            <div>
              <dt>루프 미수렴율</dt>
              <dd>
                {kpi.loop.non_convergence_rate === null
                  ? "—"
                  : percent(
                      kpi.loop.non_convergence_rate * kpi.loop.runs_considered,
                      kpi.loop.runs_considered,
                    )}
              </dd>
              <p className="kpi-note">
                {kpi.loop.non_convergence_rate === null
                  ? "루프 감사가 꺼져 있어 측정되지 않음"
                  : `${kpi.loop.runs_considered}회 기준`}
              </p>
            </div>
          </dl>

          {kpi.sites.length === 0 ? (
            <div className="empty-state">
              <p>아직 기록된 LLM 호출이 없습니다.</p>
            </div>
          ) : (
            <>
              <h2 className="section-title">호출부별 결과</h2>
              <div className="chart-frame" role="img" aria-label="호출부별 호출 결과 분포">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={rows}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#d8d0c1" vertical={false} />
                    <XAxis dataKey="site" stroke="#746f65" tickLine={false} />
                    <YAxis allowDecimals={false} stroke="#746f65" tickLine={false} axisLine={false} />
                    <Tooltip />
                    <Legend />
                    <Bar
                      dataKey="성공"
                      stackId="outcome"
                      fill={OUTCOME_COLORS.success}
                      stroke="#f4f0e7"
                      strokeWidth={2}
                    />
                    <Bar
                      dataKey="provider_error"
                      stackId="outcome"
                      name="응답 실패"
                      fill={OUTCOME_COLORS.providerError}
                      stroke="#f4f0e7"
                      strokeWidth={2}
                    />
                    <Bar
                      dataKey="parse_error"
                      stackId="outcome"
                      name="응답 거부"
                      fill={OUTCOME_COLORS.parseError}
                      stroke="#f4f0e7"
                      strokeWidth={2}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <h2 className="section-title">호출부별 토큰</h2>
              <div className="chart-frame" role="img" aria-label="호출부별 토큰 사용량">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={rows}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#d8d0c1" vertical={false} />
                    <XAxis dataKey="site" stroke="#746f65" tickLine={false} />
                    <YAxis allowDecimals={false} stroke="#746f65" tickLine={false} axisLine={false} />
                    <Tooltip />
                    {/* One series: the heading names it, so no legend box. */}
                    <Bar
                      dataKey="tokens"
                      name="토큰"
                      fill={OUTCOME_COLORS.success}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <h2 className="section-title">호출부 상세</h2>
              <table className="kpi-table">
                <thead>
                  <tr>
                    <th scope="col">호출부</th>
                    <th scope="col">호출</th>
                    <th scope="col">성공</th>
                    <th scope="col">응답 실패</th>
                    <th scope="col">응답 거부</th>
                    <th scope="col">토큰</th>
                    <th scope="col">토큰 기준 건수</th>
                    <th scope="col">평균 지연(ms)</th>
                    <th scope="col">워크플로</th>
                    <th scope="col">여러 번 호출된 워크플로</th>
                  </tr>
                </thead>
                <tbody>
                  {kpi.sites.map((site) => (
                    <tr key={site.call_site}>
                      <th scope="row">{siteLabel(site.call_site)}</th>
                      <td>{site.calls}</td>
                      <td>{site.success}</td>
                      <td>{site.provider_error}</td>
                      <td>{site.parse_error}</td>
                      <td>{site.total_tokens}</td>
                      <td>{site.tokens_counted_from}</td>
                      <td>{site.avg_latency_ms}</td>
                      <td>{site.correlations}</td>
                      <td>{site.multi_call_correlations}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="kpi-note">
                “여러 번 호출된 워크플로”는 재시도 횟수가 아닙니다. 분석 추출·비교
                판정·검색 계획에서는 응답이 거부돼 다시 부른 것이지만, 작성 루프는
                게이트·수정·보고를 설계상 여러 번 부릅니다.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
