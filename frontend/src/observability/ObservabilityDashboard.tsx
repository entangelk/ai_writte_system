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
//
// The amber and the failure colour move together (verification 2026-07-26 H-3):
// darkening amber alone for contrast margin pulled it *into* the brick red
// (normal-vision ΔE 14.0, below the 15 floor), trading a passing contrast for a
// failing separation. Re-stepping the failure hue to a crimson keeps every check
// passing and lifts the weakest contrast from 3.55 to 4.14.
const OUTCOME_COLORS = {
  success: "#1a6d99",
  providerError: "#8c1f4a",
  parseError: "#9a6a24",
} as const;

function percent(part: number, whole: number): string {
  if (whole === 0) return "—";
  return `${Math.round((part / whole) * 1000) / 10}%`;
}

function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

// The API already computed this rate; the screen only formats it. Re-deriving
// it from `rate * runs / runs` was arithmetically equal but re-entered the
// division the contract owns (verification 2026-07-26 H-1).
function rate(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
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
  // Nothing measured at all — neither an LLM call nor a loop run. The summary
  // would be five cards of zeros next to a message that already says it. Loop
  // runs are counted separately on purpose: an older project can hold loop
  // audits from before per-call instrumentation existed, and that rate is still
  // worth showing even with no call rows.
  const nothingRecorded =
    kpi !== null && kpi.totals.calls === 0 && kpi.loop.runs_considered === 0;

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
          {!nothingRecorded && (
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
            {/* K-3 창 헤드룸 경고(오너 2026-07-30). 거부는 서버 가드가 하고 화면은
                **넘지는 않지만 빠듯한** 호출을 보여준다 — 다음 번 입력이 조금만 커지면
                거부로 바뀔 호출이 그것이다. 분모를 함께 쓰는 이유는 0건이 "빠듯한 호출이
                없었다"인지 "창을 아는 호출이 없었다"인지 다르기 때문이다. */}
            <div>
              <dt>컨텍스트 여유 경고</dt>
              <dd>{kpi.totals.thin_headroom_calls}</dd>
              <p className="kpi-note">
                {kpi.totals.headroom_considered === 0
                  ? "창 크기를 아는 호출이 없어 측정되지 않음"
                  : `${kpi.totals.headroom_considered}건 기준 (여유가 창의 10% 미만)`}
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
              <dd>{rate(kpi.loop.non_convergence_rate)}</dd>
              <p className="kpi-note">
                {kpi.loop.non_convergence_rate === null
                  ? "루프 감사가 꺼져 있어 측정되지 않음"
                  : `${kpi.loop.runs_considered}회 기준`}
              </p>
            </div>
          </dl>
          )}

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
                    <th scope="col">여유 경고</th>
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
                      <td>
                        {site.headroom_considered === 0
                          ? "—"
                          : `${site.thin_headroom_calls} / ${site.headroom_considered}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="kpi-note">
                “여유 경고”는 <strong>입력 + 출력 상한</strong>이 컨텍스트 창의 90%를 넘은
                호출 수 / 창 크기를 알 수 있었던 호출 수입니다. 창을 넘긴 요청은 서버가
                모델을 부르기 전에 거부하므로, 이 숫자는 <strong>아직 통과하지만 다음이
                위험한</strong> 호출부를 가리킵니다. “—”는 창 크기를 모르는 상태입니다.
              </p>
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
