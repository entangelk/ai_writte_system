/**
 * 타이포 축의 무결성 (Phase 10 Slice 10.3).
 *
 * **왜 필요한가 — 스케일은 세우는 것보다 지키는 것이 어렵다.** 10.3 은
 * `DraftEditor` 화면의 font-size **18종을 8종으로** 줄였다. 그런데 CSS 는
 * `font-size: 0.83rem` 한 줄을 아무 저항 없이 받아 주고, `toHaveClass` 단정이
 * **0개**라 회귀는 전부 green 이다(10.1 이 `designTokens.test.ts` 를 만든 것과
 * 같은 이유이며, 같은 계열의 파일이다). 스케일은 **다음 한 줄부터** 무너진다.
 *
 * 여기서 재는 것 셋:
 *
 * 1. **램프의 출처** — 값이 `1.125^n` 계산 결과와 같은가. 지수는 `:root` 주석에
 *    적혀 있고 이 셀이 그 주장과 값을 대조한다.
 * 2. **이관 목록** — 10.3 이 옮긴 규칙이 토큰을 쓰는가(리터럴로 되돌아가지
 *    않았는가).
 * 3. **죽은 토큰 없음** — 선언한 계단을 아무도 안 쓰면 스케일이 아니라 장식이다.
 *
 * **양방향**:
 * - under-strict — 값을 손으로 고치면(0.889 → 0.9) 1번이 실패한다.
 * - over-strict — 비율을 바꾸겠다고 지수만 고치고 값을 안 옮겨도 **같은 셀**이
 *   실패한다. 그리고 이관된 규칙에 리터럴을 되박으면 2번이 실패한다.
 *
 * ★ **다른 화면은 아직 리터럴이고 그것은 결함이 아니다**(D1=ⓒ 점진). 화면
 * 슬라이스가 자기 차례에 옮기고 **그 화면의 선택자를 아래 목록에 더한다** — 목록에
 * 없는 선택자는 이 파일이 보지 않는다.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const STYLESHEET = resolve(dirname(fileURLToPath(import.meta.url)), "styles.css");
const css = readFileSync(STYLESHEET, "utf8");

/** 규칙을 셀 때 주석 안의 `{`·`font-size` 가 섞이지 않도록 **자리를 유지한 채** 지운다. */
const blanked = css.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));

/** 선택자(공백 정규화) → 그 규칙이 선언한 font-size 값. */
const declaredFontSize = new Map<string, string>();
for (const rule of blanked.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
  const size = /font-size:\s*([^;]+);/.exec(rule[2]);
  if (size === null) continue;
  declaredFontSize.set(rule[1].trim().replace(/\s+/g, " "), size[1].trim());
}

/**
 * 10.3 이 타이포 축으로 옮긴 규칙 — `DraftEditor` 화면(레일의 이어쓰기·분석·검토
 * 패널 포함)이 실제로 그리는 자리 전부다.
 */
const MIGRATED: Record<string, string> = {
  ".tab-badge": "micro",
  ".rail-section-heading span, .rail-review-list small": "micro",
  ".rail-source-list button span": "micro",
  ".rail-detail-fields dt": "micro",
  ".eyebrow": "micro",
  ".candidate-model": "micro",

  ".workspace-status": "meta",
  ".source-jump-notice": "meta",
  ".editor-meta": "meta",
  ".writing-counter": "meta",
  ".editor-actions": "meta",
  ".writing-form label": "meta",
  ".loop-status, .loop-action, .loop-counts, .loop-error": "meta",
  ".loop-stages li": "meta",
  ".candidate-accept-note": "meta",
  ".generation-pad-list": "meta",
  ".generation-pad-failed button": "meta",
  ".writing-retry": "meta",
  ".writing-quota": "meta",
  ".writing-confirm-actions button": "meta",
  ".candidate-summary": "meta",

  ".back-link": "small",
  ".version-empty": "small",
  ".empty-state span, .status-copy, .read-only-note": "small",
  ".alert": "small",
  ".writing-block, .writing-hint": "small",
  ".writing-notice": "small",
  ".gate-decision": "small",
  ".gate-empty": "small",
  ".gate-finding": "small",
  ".section-link": "small",
  ".writing-progress": "small",
  ".generation-pad-lead": "small",
  ".generation-pad-failed": "small",
  ".writing-confirm p": "small",
  ".review-link": "small",

  ".page-heading > p:last-child": "base",

  ".editor-form textarea": "reading",
  ".candidate-text": "reading",

  ".rail-section-heading h2": "subhead",
  ".version-panel-heading h2": "panel",

  // 10.4 — 화면 제목은 전 표면이 한 계단을 쓴다. 종전에는 `.page-heading h1`
  // clamp(2.8~5.4rem) · `.project-heading h1` clamp(2.5~4.7rem) · `.editor-heading h1`
  // 셋으로 갈려 있었고, 앞의 둘은 첫 화면의 절반을 먹었다(실측 근거는 styles.css).
  ".page-heading h1, .workspace-page > h1": "title",
  // 로그인은 작업 화면이 아니라 정문이라 한 계단 위를 쓴다 — 램프 밖으로 나가지는 않는다.
  ".login-heading h1": "display",
};

describe("타이포 축 (Phase 10 Slice 10.3)", () => {
  it("derives every step from the 1.125 ramp it claims to follow", () => {
    // 선언 줄에서 **값과 지수를 함께** 읽는다(`--type-small: 0.889rem;` 뒤에 붙은
    // `1.125^-1` 주석). 둘을 따로 두면 어느 한쪽만 고쳐도 조용히 통과한다.
    const steps = [
      ...css.matchAll(
        /^\s*(--type-[a-z]+):\s*([\d.]+)rem;\s*\/\*\s*1\.125\^(-?\d+)/gm,
      ),
    ];

    /**
     * ★ **정규식이 놓친 토큰은 검사도 안 받는다**(독립 검증 H1, M6 탐침으로 실증
     * 2026-08-12): 위 패턴은 `1.125^n` 주석이 **붙어 있는 줄만** 잡으므로,
     * 주석 없이 선언한 `--type-*` 은 램프 검사를 **조용히 통과**한다. 그러면
     * "값은 계산 결과다" 라는 이 파일의 주장이 새 토큰에는 성립하지 않는데
     * 아무도 모른다 — M5(가드는 목록이 부른 이름만 본다)와 **같은 계열의 맹점**이다.
     *
     * 그래서 **선언된 토큰 전부가 출처를 달고 있는지**를 먼저 잠근다. 이것이
     * `steps.length > 0` 보다 강하다(0건뿐 아니라 **일부 누락**도 잡는다).
     */
    const declared = [...css.matchAll(/^\s*(--type-[a-z]+)\s*:/gm)].map((m) => m[1]);
    const documented = new Set(steps.map((m) => m[1]));

    expect(declared.filter((token) => !documented.has(token))).toEqual([]);
    expect(declared.length).toBeGreaterThan(0);

    const drifted = steps
      .map(([, token, value, exponent]) => ({
        token,
        declared: Number(value),
        computed: Math.round(1.125 ** Number(exponent) * 1000) / 1000,
      }))
      .filter(({ declared, computed }) => declared !== computed);

    expect(drifted).toEqual([]);
  });

  it("leaves no step declared that nothing draws with", () => {
    // 아무도 안 쓰는 계단은 스케일이 아니라 장식이고, 다음 사람이 "이건 뭐에
    // 쓰는 거지" 하고 아무 데나 쓰기 시작하는 자리다.
    const declared = new Set(
      [...css.matchAll(/^\s*(--type-[a-z]+)\s*:/gm)].map((m) => m[1]),
    );
    const consumed = new Set(
      [...css.matchAll(/var\(\s*(--type-[a-z]+)\s*[,)]/g)].map((m) => m[1]),
    );

    expect([...declared].filter((t) => !consumed.has(t)).sort()).toEqual([]);
  });

  it("keeps the migrated rules on the scale instead of raw literals", () => {
    const offenders = Object.entries(MIGRATED)
      .map(([selector, step]) => ({
        selector,
        expected: `var(--type-${step})`,
        actual: declaredFontSize.get(selector) ?? "(규칙 또는 font-size 선언 없음)",
      }))
      .filter(({ expected, actual }) => expected !== actual);

    expect(offenders).toEqual([]);
  });
});
