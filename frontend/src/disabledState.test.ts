/**
 * 비활성 겉모습의 **한 값** (Phase 10 부채 ④ 폐쇄 · 오너 결정 D-2026-08-21-e).
 *
 * **왜 갈라졌는지부터** — 버튼의 `:disabled` 농도가 네 자리에서 **0.42 · 0.45 ·
 * 0.35 · 0.5** 로 흩어져 있었다. 10.5 가 통일한 것은 accent 기본 버튼 7선택자
 * 하나뿐이고, 그 밖의 버튼은 자기 값을 들고 있었다. 어떤 테스트도 겉모습을 보지
 * 않으므로(`toHaveClass` 0 · `ByTestId` 0) **다섯 번째 값이 생겨도 조용하다** —
 * [`buttonAppearance.test.ts`](./buttonAppearance.test.ts)가 hover·accent 면에 대해
 * 하는 일을 이 파일이 **비활성 농도**에 대해 한다.
 *
 * **★ 이 파일이 잠그는 것은 "네 자리가 같아 보인다" 가 아니다.** 실제로 안 같다 —
 * `opacity` 는 요소를 배경과 합성하는데 네 자리의 **글자색이 다르기 때문**이고,
 * 같은 0.45 에서 실효 대비는 1.99 · 2.21 · 2.75 · 2.02 로 흩어진다
 * (`python3 docs/plans/10_disabled_contrast.py`). 오너가 그것을 알고 골랐다:
 * **규칙 하나가 읽기 쉽고, 진짜 문제는 대비가 아니라 색 선택**이기 때문이다.
 * 그 축(위험·일반·특수 카테고리별 색 실측)은 별도 작업으로 추적 부채에 있다.
 * 그래서 여기서 재는 것은 **값이 아니라 자리의 수**다.
 *
 * **양방향**:
 * - under-strict — 새 비활성 버튼이 리터럴을 들고 오면 1번이 실패한다.
 * - under-strict — 토큰을 지우거나 둘로 늘리면 2번이 실패한다.
 * - over-strict — **의도된 예외 둘**을 "통일한다며" 토큰으로 접으면 3번이 실패한다.
 *   `.session-menu button:disabled` 는 `cursor: wait` 로 **진행 중**을 뜻하는 다른
 *   상태이고, `.login-form input:disabled` 는 **버튼이 아니다**(입력은 글자색까지
 *   함께 죽인다). 둘 다 접는 순간 뜻이 사라지는데 화면을 열기 전에는 안 보인다.
 * - over-strict — 예외를 몰래 하나 더 만들어도 **같은 3번**이 실패한다. 목록을
 *   손으로 들지 않고 스타일시트에서 유도하기 때문이다.
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

/** `:disabled` 상태를 그리는 규칙. `:not(:disabled)` 는 hover 쪽이라 뺀다. */
const disabledRules = rules.filter((rule) =>
  rule.selectors.some((one) => /:disabled\s*$/.test(one)),
);

const opacityOf = (rule: Rule) =>
  rule.body.match(/(^|;)\s*opacity:\s*([^;]+)\s*;/)?.[2].trim();

/**
 * 뜻이 다른 두 자리. **목록이 아니라 근거를 적는다** — 여기 이름을 더하려면
 * "왜 다른 상태인가" 를 함께 적어야 한다.
 */
const INTENTIONAL = new Map([
  // 진행 중(`cursor: wait`)이다. 못 누르는 이유가 "지금 하고 있어서" 라 다른 상태다.
  [".session-menu button:disabled", "0.55"],
  // 버튼이 아니다. 입력은 글자색(`--text-muted`)까지 함께 죽이므로 농도만으로 안 된다.
  [".login-form input:disabled", "0.7"],
]);

describe("비활성 겉모습 (Phase 10 부채 ④)", () => {
  it("dims every disabled button through the one token", () => {
    const offenders = disabledRules
      .filter((rule) => rule.selectors.some((one) => !INTENTIONAL.has(one)))
      .filter((rule) => opacityOf(rule) !== undefined)
      .filter((rule) => opacityOf(rule) !== "var(--disabled-opacity)")
      .map((rule) => rule.selectors.join(", "));

    expect(offenders).toEqual([]);
  });

  it("declares that token exactly once, as a number", () => {
    const declared = [...css.matchAll(/--disabled-opacity:\s*([^;]+);/g)].map(
      (match) => match[1].trim(),
    );

    // 0개면 위 셀이 공허하게 만족된다(아무도 토큰을 안 쓰면 위반도 없다).
    // 2개면 테마·미디어 쿼리마다 값이 갈리기 시작한 것이고, 그것이 원래 병이다.
    expect(declared).toHaveLength(1);
    expect(Number(declared[0])).toBeGreaterThan(0);
    expect(Number(declared[0])).toBeLessThan(1);
  });

  it("leaves the two states that mean something else alone", () => {
    const literal = new Map(
      disabledRules
        .filter((rule) => {
          const value = opacityOf(rule);
          return value !== undefined && value !== "var(--disabled-opacity)";
        })
        .map((rule) => [rule.selectors.join(", "), opacityOf(rule)!]),
    );

    expect(Object.fromEntries(literal)).toEqual(Object.fromEntries(INTENTIONAL));
    // 진행 중은 커서로도 말한다 — 농도만 남으면 "못 누른다" 와 구별되지 않는다.
    const waiting = disabledRules.find((rule) =>
      rule.selectors.includes(".session-menu button:disabled"),
    );
    expect(waiting?.body).toMatch(/cursor:\s*wait\s*;/);
  });
});
