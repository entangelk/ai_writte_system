/**
 * 디자인 토큰 시스템의 무결성 (Phase 10 Slice 10.1, D2=ⓑ · D6=ⓑ).
 *
 * **왜 이 파일이 필요한가 — CSS 에는 가드가 하나도 없었다.** 2026-08-11 실측:
 * `toHaveClass` **0** · `ByTestId` **0**. 즉 스타일은 무엇을 어떻게 바꿔도 회귀가
 * 침묵한다. 10.1 이 색 **178곳**을 토큰으로 옮기고 하드코딩 **45곳**을 흡수했는데,
 * 그 규모의 기계적 치환에서 오타 하나는 `var(--typo)` 로 남고 **CSS 는 조용히
 * 아무것도 그리지 않는다**(잘못된 커스텀 프로퍼티는 에러가 아니라 무효값이다).
 * 빌드도 통과하고 테스트도 통과하고 화면만 깨진다.
 *
 * 그래서 여기서 **스타일시트를 파싱해서** 잰다. DOM 을 안 쓰므로 렌더 테스트가
 * 못 보는 자리를 본다 — `productName.test.ts` 와 같은 계열이다.
 *
 * **양방향**:
 * - under-strict — 정의되지 않은 토큰을 쓰면(오타·삭제) 첫 셀이 실패한다.
 * - over-strict — 토큰 체계를 우회해 색을 직접 박으면 두 번째 셀이 실패한다.
 *   (D6=ⓑ 의 실체다: 다크 팔레트는 안 만들되 **모든 색이 토큰 뒤에** 있어야
 *   나중에 `:root` 한 곳만 바꿔 테마를 얻는다. 하나라도 새면 그 자리는 안 따라온다.)
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const STYLESHEET = resolve(
  dirname(fileURLToPath(import.meta.url)), "styles.css",
);
const css = readFileSync(STYLESHEET, "utf8");

/** `:root { … }` 선언 블록. 여기가 값이 사는 유일한 자리다. */
const rootBlock = css.slice(0, css.indexOf("\n}\n") + 2);
/** 나머지 전부 — 화면 규칙. 여기에는 리터럴 색이 없어야 한다. */
const rules = css.slice(css.indexOf("\n}\n") + 2);

describe("디자인 토큰 (Phase 10 Slice 10.1)", () => {
  it("defines every custom property it consumes", () => {
    const defined = new Set(
      [...rootBlock.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((m) => m[1]),
    );
    const consumed = new Set(
      // ★ fallback 이 있는 `var(--x, y)` 도 반드시 센다. 그 형태는 토큰이
      // 없어도 **조용히 fallback 으로 렌더**돼서, 정확히 그렇게 결함이 숨었다 —
      // 8.4 의 `.writing-confirm` 이 `var(--surface-muted, transparent)` 로
      // 2026-08-04 부터 배경 없이 그려지고 있었고 아무도 몰랐다(초판 정규식이
      // `)` 로 끝나는 형태만 봐서 이 셀조차 놓칠 뻔했다).
      [...css.matchAll(/var\(\s*(--[a-z0-9-]+)\s*[,)]/g)].map((m) => m[1]),
    );

    const undefinedTokens = [...consumed].filter((t) => !defined.has(t)).sort();

    expect(undefinedTokens).toEqual([]);
  });

  it("keeps every colour behind a token, so one block can retheme the app", () => {
    // 규칙부에 남은 리터럴 색 = 토큰 체계를 우회한 자리.
    const literals = [
      ...rules.matchAll(/#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)/g),
    ].map((m) => m[0]);

    expect(literals).toEqual([]);
  });

  it("keeps colour out of the TypeScript sources too", () => {
    /**
     * **위 셀의 사각지대**(Slice 10.3 에서 실제로 당했다): 그것은 `styles.css` 만
     * 읽으므로 **TS 가 들고 있는 색은 안 보인다.** 관측 대시보드가 정확히 그
     * 자리였다 — recharts 가 색을 SVG **속성**으로 받아 `var(--)` 가 안 닿는다는
     * 이유로 색을 JS 리터럴로 들고 있었고, 10.1 이 팔레트를 통째로 가는 동안
     * **혼자 옛 크림/벽돌 값에 남아** 막대마다 크림색 테두리를 그렸다. CSS 가드는
     * 전부 green 이었다.
     *
     * 처방은 `chartColors.ts` 의 `getComputedStyle` 이고, 이 셀은 **그 처방이
     * 우회되지 않는지**를 잠근다. 색이 다시 TS 로 새면 그 자리는 테마를 안 따라온다.
     *
     * 주석은 판정에서 뺀다 — 옛 값을 *설명하는* 문장(`chartColors.ts` 머리말)까지
     * 결함으로 세면 기록을 못 남긴다. 테스트 파일도 뺀다(단정이 색을 적는 것은 정당).
     */
    const root = resolve(dirname(fileURLToPath(import.meta.url)));
    const sources: string[] = [];
    const walk = (directory: string) => {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (/\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)) {
          sources.push(path);
        }
      }
    };
    walk(root);

    // 목록이 비면 아래 단정이 공허하게 통과한다.
    expect(sources.length).toBeGreaterThan(0);

    const leaked = sources.flatMap((path) => {
      const code = readFileSync(path, "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      return [...code.matchAll(/#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)/g)].map(
        (match) => `${relative(root, path)}: ${match[0]}`,
      );
    });

    expect(leaked).toEqual([]);
  });

  it("routes screens through semantic tokens, not raw primitives", () => {
    /**
     * primitive(`--blue-600`)는 **값이 이름**이라 화면이 직접 쓰면 의도가 사라지고,
     * 팔레트를 갈 때 그 자리만 남는다. 화면은 semantic(`--action-primary`)만 본다.
     * primitive 는 `:root` 안에서 semantic 이 참조할 때만 등장한다.
     */
    const PRIMITIVE = /var\((--(?:blue|slate|danger|warn|ok)-\d+)\)/g;
    const leaked = [...rules.matchAll(PRIMITIVE)].map((m) => m[1]);

    expect([...new Set(leaked)].sort()).toEqual([]);
  });
});
