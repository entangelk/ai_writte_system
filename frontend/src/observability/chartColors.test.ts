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
     * 계열색의 유일한 요구는 **서로 구별되는가**다. 값 자체의 검산(색각 이상 ΔE ·
     * 명도 대역 · 채도 바닥 · 3:1)은 dataviz 검증기가 하고 그 명령과 결과는
     * `styles.css` 주석에 적혀 있다 — 여기서 그것을 다시 구현하지 않는다
     * (구현하면 검증기와 갈리는 두 번째 정본이 생긴다).
     *
     * 대신 **가장 싸고 가장 잘 깨지는 것**을 잠근다: 셋 중 둘이 같은 값이 되는 것.
     * 토큰을 복사·붙여넣기로 늘릴 때 실제로 일어나는 사고이며, 그 순간 두 계열은
     * 그래프에서 **한 덩어리로 보인다**.
     */
    const series = [
      CHART_TOKENS.success,
      CHART_TOKENS.providerError,
      CHART_TOKENS.parseError,
    ].map((token) => {
      const found = new RegExp(`^\\s*${token}\\s*:\\s*([^;]+);`, "m").exec(rootBlock);
      return found?.[1].trim();
    });

    expect(series.every((value) => value !== undefined)).toBe(true);
    expect(new Set(series).size).toBe(series.length);
  });
});
