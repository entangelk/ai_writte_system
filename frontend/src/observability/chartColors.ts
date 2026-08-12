/**
 * 차트가 쓰는 색을 **`:root` 에서 읽어 온다** (Phase 10 Slice 10.3, 2026-08-12).
 *
 * **왜 이 파일이 필요한가.** recharts 는 색을 SVG `fill`/`stroke` **속성**으로
 * 받으므로 `var(--x)` 문자열이 닿지 않는다. 그래서 이 화면만 색을 **JS 리터럴로**
 * 들고 있었고, 10.1 이 팔레트를 갈아엎는 동안 **혼자 옛 크림/벽돌 값에 남았다**
 * (격자 `#d8d0c1` · 축 `#746f65` · 막대 간격 `#f4f0e7` — 마지막 것은 *옛 페이지
 * 배경*이라 새 배경 위에서는 막대마다 크림색 테두리로 보였다).
 *
 * 여기서 `getComputedStyle` 로 읽으면 **정본이 다시 `:root` 하나**가 된다 —
 * D6=ⓑ("다크 팔레트는 안 만들되 `:root` 한 곳으로 테마가 갈리게")가 차트에도
 * 성립한다.
 *
 * ★ **fallback 을 두지 않는다.** `var(--x, 기본값)` 형태가 8.4 의 `.writing-confirm`
 * 을 2026-08-04 부터 조용히 배경 없이 렌더시켰던 그 구조다 — 토큰이 없어도 화면이
 * 그럴듯하게 그려지면 아무도 모른다. 대신 **토큰이 실재하는지를 테스트가 잠근다**
 * ([`chartColors.test.ts`](./chartColors.test.ts)가 아래 목록을 `styles.css` 의
 * `:root` 와 대조한다).
 */

/**
 * 차트가 읽는 토큰 전부. **테스트가 이 목록을 그대로 읽어 `:root` 와 대조하므로
 * 여기에 없는 토큰을 컴포넌트에서 직접 읽으면 안 된다.**
 *
 * 계열색 셋만 차트 전용(`--chart-*`)이고 **나머지 셋은 앱의 일반 토큰**이다 —
 * 격자·축·간격은 차트만의 색이 아니라 *앱의 선과 잉크*이며, 따로 두면 화면과
 * 차트가 서로 다른 회색을 쓰게 된다.
 */
export const CHART_TOKENS = {
  success: "--chart-success",
  providerError: "--chart-provider-error",
  parseError: "--chart-parse-error",
  /** 격자 — 데이터보다 뒤로 물러나야 한다(dataviz: recessive grid). */
  grid: "--border-hairline",
  /** 축과 눈금 글자. */
  axis: "--text-muted",
  /**
   * 쌓인 막대 사이의 **간격**. 색이 아니라 *바탕이 비쳐 보이는 틈*이라서
   * **차트가 앉은 면**과 같아야 한다 — `.chart-frame` 의 배경이 `--surface-raised`
   * 이므로 페이지 배경(`--surface-page`)을 쓰면 틈만 파랗게 뜬다.
   */
  markGap: "--surface-raised",
  /**
   * 툴팁·범례 (독립 검증 H2, 2026-08-12). recharts 는 이 둘을 **자기 기본
   * 스타일**로 그린다 — 흰 배경 + `#ccc` 테두리 + 검은 글자. 우리 코드에
   * 리터럴이 없으니 색 가드는 조용한데 **화면에서는 혼자 다른 계통**이다.
   * 떠 있는 표면이므로 융기면이 아니라 카드면을 쓴다.
   */
  overlaySurface: "--surface-card",
  overlayBorder: "--border-hairline",
  overlayText: "--text-body",
} as const;

export type ChartColors = Record<keyof typeof CHART_TOKENS, string>;

/**
 * `:root` 에서 한 번에 읽는다. `getComputedStyle` 은 스타일 재계산을 강제하므로
 * **호출을 하나로 모으고** 값만 여섯 번 꺼낸다.
 */
export function readChartColors(): ChartColors {
  const root = getComputedStyle(document.documentElement);
  const read = (token: string) => root.getPropertyValue(token).trim();
  return {
    success: read(CHART_TOKENS.success),
    providerError: read(CHART_TOKENS.providerError),
    parseError: read(CHART_TOKENS.parseError),
    grid: read(CHART_TOKENS.grid),
    axis: read(CHART_TOKENS.axis),
    markGap: read(CHART_TOKENS.markGap),
    overlaySurface: read(CHART_TOKENS.overlaySurface),
    overlayBorder: read(CHART_TOKENS.overlayBorder),
    overlayText: read(CHART_TOKENS.overlayText),
  };
}

/**
 * recharts `<Tooltip>` 에 그대로 넘기는 스타일. 컴포넌트가 같은 객체를 두 차트에
 * 쓰므로 여기 한 번만 적는다 — 두 차트가 서로 다른 툴팁을 갖는 것이 H2 의 재발이다.
 */
export function tooltipStyle(color: ChartColors) {
  return {
    background: color.overlaySurface,
    border: `1px solid ${color.overlayBorder}`,
    borderRadius: "0.5rem",
    color: color.overlayText,
  };
}
