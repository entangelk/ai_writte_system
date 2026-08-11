/**
 * 제품명은 **사용자에게 보이는 모든 자리에서 하나여야 한다** (Phase 10 D5).
 *
 * **왜 별도 파일인가 — 렌더 테스트가 원리적으로 못 보는 자리가 있다.** 10.0 은
 * 헤더와 로그인 화면을 "에-라잇" 으로 통일하고 `queryByText("AI Writing System")`
 * 로 잠갔는데, **그 단정은 `<head>` 를 못 본다** — vitest 는 `index.html` 을 읽지
 * 않고 빈 jsdom 문서에 컴포넌트를 마운트하므로 **브라우저 탭 타이틀은 렌더 테스트의
 * 사정거리 밖**이다. 실제로 `index.html` 의 `<title>` 이 옛 이름으로 남아 있었고
 * 289셀이 전부 green 이었다(2026-08-11 독립 검증 H1 이 잡았다).
 *
 * 그래서 이 가드는 DOM 이 아니라 **파일을 읽는다**. 같은 병이 또 나오는 자리는
 * `<head>` 의 다른 태그(`og:title`·`apple-mobile-web-app-title`·manifest)이며,
 * 아래 스윕이 그것들도 함께 덮는다.
 *
 * **양방향**:
 * - under-strict — 탭 타이틀을 옛 이름으로 되돌리면 첫 셀이 실패한다.
 * - over-strict/완전성 — 렌더에 안 잡히는 **어느 소스 파일에든** 옛 이름이
 *   되살아나면 두 번째 셀이 실패한다. 테스트 파일은 제외한다 — 부재를 단정하려면
 *   그 문자열을 적어야 하기 때문이다(이 파일 자신이 그 예다).
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** 오너가 2026-08-10 에 명명한 정본. */
const PRODUCT_NAME = "에-라잇";
/** 그 전의 작업 제목. 사용자에게 보이는 자리에 남아 있으면 안 된다. */
const RETIRED_NAME = "AI Writing System";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      // 빌드 산출물·의존성은 소스가 아니다. dist 는 .gitignore 대상이며
      // index.html 을 고치면 다음 빌드에 따라온다.
      return entry === "node_modules" || entry === "dist" ? [] : sourceFiles(path);
    }
    return /\.(tsx?|html|css)$/.test(entry) && !/\.test\.tsx?$/.test(entry)
      ? [path]
      : [];
  });
}

describe("제품명 (Phase 10 D5)", () => {
  it("names the browser tab, which no render test can reach", () => {
    const html = readFileSync(join(FRONTEND_ROOT, "index.html"), "utf8");

    expect(html).toContain(`<title>${PRODUCT_NAME}</title>`);
    expect(html).not.toContain(RETIRED_NAME);
  });

  it("leaves the retired working title in no user-visible source", () => {
    const offenders = sourceFiles(join(FRONTEND_ROOT, "src"))
      .concat(join(FRONTEND_ROOT, "index.html"))
      .filter((path) => readFileSync(path, "utf8").includes(RETIRED_NAME))
      .map((path) => path.slice(FRONTEND_ROOT.length + 1));

    expect(offenders).toEqual([]);
  });
});
