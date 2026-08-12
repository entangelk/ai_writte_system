/**
 * 차트가 읽는 토큰이 **실재하는지** (Phase 10 Slice 10.3).
 *
 * **왜 이 파일이 필요한가 — 여기가 다른 어떤 가드도 안 보는 자리다.**
 *
 * - [`designTokens.test.ts`](../designTokens.test.ts)의 *"소비하는 커스텀
 *   프로퍼티를 전부 정의하는가"* 셀은 **`styles.css` 안의 `var(...)` 만** 센다.
 *   차트는 `getComputedStyle` 로 **TS 에서** 읽으므로 그 그물에 안 걸린다.
 * - 렌더 테스트도 못 본다. jsdom 은 `styles.css` 를 로드하지 않아 읽기가 전부
 *   빈 문자열을 내는데, recharts 는 `fill=""` 를 받고도 **예외 없이 그린다**.
 *   그 화면의 15셀은 문구·역할을 단정하므로 **전부 green 이다.**
 *
 * 즉 토큰 이름을 하나 오타 내면 **배포에서만 색이 사라진다** — 8.4 의
 * `.writing-confirm` 이 2026-08-04 부터 배경 없이 렌더되던 것과 같은 구조이며,
 * `chartColors.ts` 가 fallback 을 두지 않기로 한 이유가 이 셀의 존재다.
 *
 * **양방향**:
 * - under-strict — 토큰 이름을 오타 내거나 `:root` 에서 지우면 첫 셀이 실패한다.
 * - over-strict — 차트가 안 읽는 `--chart-*` 을 `:root` 에 남겨 두면 둘째 셀이
 *   실패한다(죽은 토큰. `typeScale.test.ts` 와 같은 규율).
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { CHART_TOKENS } from "./chartColors";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, "..", "styles.css"), "utf8");
/** 값이 사는 유일한 자리. `designTokens.test.ts` 와 같은 방식으로 자른다. */
const rootBlock = css.slice(0, css.indexOf("\n}\n") + 2);

const declared = new Set(
  [...rootBlock.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((match) => match[1]),
);

/** `:root` 에 적힌 그대로의 선언값(`var(--blue-600)` 이면 그 문자열). */
function declarationOf(token: string): string | undefined {
  return new RegExp(`^\\s*${token}\\s*:\\s*([^;]+);`, "m").exec(rootBlock)?.[1].trim();
}

/** primitive 참조를 한 겹 따라가 최종 hex 를 낸다. */
function resolveToken(token: string): string | undefined {
  const value = declarationOf(token);
  const alias = value === undefined ? null : /^var\((--[a-z0-9-]+)\)$/.exec(value);
  return alias === null ? value : declarationOf(alias[1]);
}

const SERIES_TOKENS = [
  CHART_TOKENS.success,
  CHART_TOKENS.providerError,
  CHART_TOKENS.parseError,
];

describe("차트 색 토큰 (Phase 10 Slice 10.3)", () => {
  it("resolves every token the chart reads at runtime", () => {
    const requested = Object.values(CHART_TOKENS);

    // 목록 자체가 비면 위 단정이 공허하게 통과한다(M5 에서 배운 형태).
    expect(requested.length).toBeGreaterThan(0);
    expect(requested.filter((token) => !declared.has(token))).toEqual([]);
  });

  it("leaves no chart-only token that the chart stopped reading", () => {
    const chartOnly = [...declared].filter((token) => token.startsWith("--chart-"));
    const read = new Set<string>(Object.values(CHART_TOKENS));

    expect(chartOnly.filter((token) => !read.has(token)).sort()).toEqual([]);
  });

  it("keeps the series colours distinct from one another", () => {
    /**
     * 가장 싸고 가장 잘 깨지는 것: 셋 중 둘이 같은 값이 되는 것. 토큰을
     * 복사·붙여넣기로 늘릴 때 실제로 일어나는 사고이며, 그 순간 두 계열은
     * 그래프에서 **한 덩어리로 보인다**.
     */
    const series = SERIES_TOKENS.map((token) => declarationOf(token));

    expect(series.every((value) => value !== undefined)).toBe(true);
    expect(new Set(series).size).toBe(series.length);
  });

  it("still holds the exact palette the recorded validation covered", () => {
    /**
     * ★ **독립 검증 H1 (2026-08-12) — 이 셀이 그것을 닫는다.**
     *
     * 위 셀은 셋이 *서로 다른지*만 본다. 그래서 **검증기가 FAIL 하는 조합으로
     * 바꿔도 전부 green 이었다** — 실측: `--chart-parse-error` 를 `#7b5100` 로
     * 바꾸면 dataviz 검증기는 채도 바닥 미달로 FAIL 인데 가드 7셀이 모두 통과했고
     * `styles.css` 주석만 조용히 낡았다.
     *
     * **그렇다고 ΔE 를 여기서 다시 구현하지는 않는다** — 그러면 검증기와 갈리는
     * 두 번째 정본이 생긴다(그 판단은 유지한다). 대신 **"지금 값이 그때 검산한
     * 바로 그 값인가"** 를 잠근다. 10.1 팔레트·10.3 타이포가 쓴 것과 같은
     * *출처 연결* 처방이다.
     *
     * 잠그는 연결 셋 — **어느 하나만 움직여도 실패한다**:
     *
     * 1. `:root` 의 계열색 셋 **↔** 주석에 적힌 검산 명령의 팔레트 인자
     * 2. 검산에 쓴 표면 **↔** `--surface-raised` 의 실제 값
     * 3. 그 토큰 **↔** `.chart-frame` 이 실제로 그리는 배경
     *
     * 3번이 브리프의 *"표면을 바꾸면 검산을 다시 돌린다"* 를 **강제하는 자리**다.
     * 종전에는 그 문장을 아무도 집행하지 않았다.
     *
     * 실패하면 할 일은 하나: **주석의 명령을 그대로 다시 돌리고**, 통과하면 값과
     * 주석을 함께 옮긴다.
     */
    const command = /validate_palette\.js\s+"([^"]+)"[\s\S]{0,120}?--surface\s+"(#[0-9a-f]{6})"/i
      .exec(css);
    expect(command, "styles.css 주석의 검산 명령을 못 찾았다").not.toBeNull();

    const [, documentedPalette, documentedSurface] = command!;

    // 1. 계열색 — primitive 참조는 한 겹 따라간다(`--chart-success: var(--blue-600)`).
    const resolved = SERIES_TOKENS.map((token) => resolveToken(token));
    expect(resolved).toEqual(documentedPalette.split(",").map((hex) => hex.trim()));

    // 2·3. 검산 표면 = `.chart-frame` 이 실제로 그리는 배경.
    const frame = /\.chart-frame\s*\{[^}]*background:\s*var\((--[a-z0-9-]+)\)/.exec(css);
    expect(frame, ".chart-frame 의 배경 선언을 못 찾았다").not.toBeNull();
    expect(resolveToken(frame![1])).toEqual(documentedSurface);
  });
});
