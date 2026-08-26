/**
 * 애드센스 로더는 **렌더 테스트가 원리적으로 못 보는 자리**에 산다 — `index.html` 의
 * `<head>` 안인데, vitest 는 `index.html` 을 읽지 않고 빈 jsdom 문서에 컴포넌트를
 * 마운트한다(`productName.test.ts` 가 같은 이유로 파일을 읽는 선례 — Phase 10 D5).
 *
 * 이 스크립트가 조용히 사라져도 앱엔 아무 에러가 안 뜬다 — 매출만 조용히 0 이
 * 된다. 그래서 존재 단정을 파일 가드로 잠근다.
 *
 * **양방향**:
 * - under-strict — 로더 스크립트(또는 client 파라미터)를 지우거나 고치면 실패한다.
 * - over-strict — 무해한 재포맷(속성 순서·줄바꿈)에는 실패하지 않는다: 단정은
 *   URL+client 파라미터·`crossorigin`·`<head>` 배치의 본질만 본다. SRI(`integrity`)
 *   를 요구하지 않는 것도 의도다 — `adsbygoogle.js` 는 Google 이 실험 단위로 내용을
 *   바꿔 serve 하므로 해시 고정이 오히려 로딩을 깬다(공식 스니펫에도 없다).
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** 오너 애드센스 계정의 퍼블리셔 ID — 모든 페이지 HTML 에 노출되는 공개 값. */
const ADSENSE_LOADER =
  'src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6325442421128026"';

describe("애드센스 로더 (2026-08-26)", () => {
  it("loads the AdSense script from <head>, which no render test can reach", () => {
    const html = readFileSync(join(FRONTEND_ROOT, "index.html"), "utf8");
    const head = html.slice(html.indexOf("<head>"), html.indexOf("</head>"));

    expect(head).toContain(ADSENSE_LOADER);
    expect(head).toContain('crossorigin="anonymous"');
  });
});
