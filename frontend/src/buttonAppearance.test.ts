/**
 * 기본 동작 버튼의 **한 규칙성** (Phase 10 Slice 10.5).
 *
 * **왜 필요한가 — 사본이 다섯이면 갈라지는 것이 조용하다.** 10.5 전까지 accent
 * 버튼의 겉모습은 **다섯 벌**로 흩어져 있었다(`.auth-submit` · `.form-controls
 * button` · `.editor-actions button` · `.writing-actions button` 묶음 ·
 * `.row-actions button`). 그리고 이미 갈라져 있었다 — `.editor-actions button`
 * 만 `transition` 이 없어 배경이 툭 바뀌었고, hover 시 살짝 뜨는 효과는 다섯 중
 * **둘**에만 있었다(2026-08-13 실측).
 *
 * 아무도 그것을 결함으로 부르지 않은 이유는 **어떤 테스트도 겉모습을 안 보기
 * 때문**이다(`toHaveClass` 0 · `ByTestId` 0). 새 표면이 다섯 중 어디에도 안
 * 들어가면 그냥 조용하다.
 *
 * 그래서 재는 것은 **값이 아니라 규칙성**이다 — "버튼이 파란가"가 아니라
 * **"겉모습을 정하는 자리가 하나인가"**. 색·모션은 디자인 판단이라 바뀔 수
 * 있지만, 자리가 여럿이 되는 것은 언제나 결함이다([`pageLayout.test.ts`](./pageLayout.test.ts)
 * 가 폭에 대해 하는 것과 같은 방식이며, 목록을 손으로 들지 않고 **스타일시트에서
 * 유도**하는 것도 같다).
 *
 * **양방향**:
 * - under-strict — 여섯 번째 사본을 만들면 1번이 실패한다.
 * - under-strict — base 에만 자리를 더하고 hover·disabled 에 안 더하면(그 버튼은
 *   accent 색은 얻고 반응은 못 얻는다 — 화면을 열기 전에는 안 보인다) 2·3번이
 *   실패한다.
 * - over-strict — 통합한다며 **패딩까지** 합치면 4번이 실패한다. 패딩은 자리마다
 *   다르고(0.78/1.35 · 0.72/1.1 · 0.72/1.5 · 0.5/1.1) 합치는 순간 시각이 바뀐다.
 *
 * ★ **`.row-actions button.ghost` 는 대상이 아니다** — 같은 자리에 앉지만 accent
 * 면을 **벗는** 변형이라 특이도로 덮는다(그래서 base 규칙에 없다). *"버튼이면
 * 전부"* 로 세면 이것이 위반으로 잡히는데, 위반이 아니라 설계다.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "styles.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));

type Rule = { selectors: string[]; body: string };
const rules: Rule[] = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
  selectors: match[1].split(",").map((one) => one.trim().replace(/\s+/g, " ")),
  body: match[2],
}));

const declares = (rule: Rule, property: string, value: string) =>
  new RegExp(`(^|;)\\s*${property}:\\s*${value}\\s*;`).test(rule.body);

/**
 * **기본 동작 버튼의 정체 = accent 면 + 손가락 커서.** 이 둘을 함께 선언하는
 * 규칙이 "겉모습을 정하는 자리"다. accent 면만 보면 배지·구분점(`.tab-badge`,
 * 날짜 표식)이 섞이고, 커서만 보면 탭·링크형 버튼이 섞인다 — **둘을 함께** 세는
 * 것이 이 화면에서 버튼을 고르는 유일하게 정확한 기준이다.
 */
const identityRules = rules.filter(
  (rule) =>
    declares(rule, "background", "var\\(--action-primary\\)") &&
    declares(rule, "cursor", "pointer"),
);

/** `.auth-submit:hover:not(:disabled)` → `.auth-submit` */
const stem = (selector: string) => selector.replace(/(:[a-z-]+(\([^)]*\))?)+$/, "");

describe("기본 동작 버튼 (Phase 10 Slice 10.5)", () => {
  it("declares the button appearance in exactly one place", () => {
    // 0개면 "한 곳" 조건이 공허하게 만족된다 — 겉모습이 사라진 것도 결함이다.
    expect(identityRules.map((rule) => rule.selectors)).toHaveLength(1);
  });

  it("gives every one of those places the same hover response", () => {
    const hoverRules = rules.filter((rule) =>
      declares(rule, "background", "var\\(--action-primary-hover\\)"),
    );
    expect(hoverRules).toHaveLength(1);

    const responded = [...new Set(hoverRules[0].selectors.map(stem))].sort();
    expect(responded).toEqual([...identityRules[0].selectors].sort());
  });

  it("gives every one of those places the same disabled response", () => {
    const wanted = new Set(identityRules[0].selectors.map((one) => `${one}:disabled`));
    const disabledRules = rules.filter((rule) =>
      rule.selectors.some((one) => wanted.has(one)),
    );

    // 한 규칙이 전부를 덮어야 한다 — 둘로 쪼개지는 순간 다시 갈라질 자리가 생긴다.
    expect(disabledRules).toHaveLength(1);
    expect([...disabledRules[0].selectors].sort()).toEqual([...wanted].sort());
  });

  it("leaves the padding to each site instead of folding it in", () => {
    // 크기는 자리가 정한다. 공통 규칙이 패딩을 잡으면 네 표면의 버튼 크기가 한꺼번에
    // 바뀌는데, 그것은 통합이 아니라 재디자인이다.
    expect(/(^|;)\s*padding:/.test(identityRules[0].body)).toBe(false);

    const unsized = identityRules[0].selectors.filter(
      (one) =>
        !rules.some(
          (rule) =>
            rule !== identityRules[0] &&
            rule.selectors.includes(one) &&
            /(^|;)\s*padding:/.test(rule.body),
        ),
    );
    expect(unsized).toEqual([]);
  });
});
