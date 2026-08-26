/**
 * 스크래치 패드 본문 개행 (2026-08-26 도그푸드) — **렌더 테스트가 원리적으로 못
 * 보는 자리**에 산다: `white-space` 는 CSS 의 계산값이라 jsdom 에서 굴러보지 않는다
 * (`adsense.test.ts` 와 같은 이유로 파일을 읽는 가드).
 *
 * 이 슬라이스의 직접 동기: `<pre class="scratch-recovery-text">` 에 스타일이 없어
 * 브라우저 기본 `white-space: pre` 로 동작 — 긴 문단이 가로로 뻗어 가로 스크롤로만
 * 읽을 수 있었고 검토 자체가 불가능했다. 이 규칙이 조용히 사라져도 앱엔 아무 에러가
 * 안 뜬다 — 패드가 다시 읽을 수 없게 될 뿐이다.
 *
 * **양방향**:
 * - under-strict — `white-space: pre-wrap`(또는 `overflow-wrap`)을 지우면 실패한다.
 * - over-strict — 무해한 재포맷(순서·줄바꿈·다른 속성 추가)에는 실패하지 않는다:
 *   단정은 두 선언의 존재만 본다. 정확한 폰트·크기는 typeScale 이관 목록이 잠근다.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "styles.css"),
  "utf8",
);

const rule = css.match(/\.scratch-recovery-text\s*\{([^}]*)\}/)?.[1] ?? "";

describe("스크래치 패드 본문 개행 (2026-08-26)", () => {
  it("wraps long paragraphs instead of horizontal-scrolling them", () => {
    expect(rule).not.toBe(""); // the rule itself must exist
    expect(rule).toMatch(/white-space:\s*pre-wrap\s*;/);
    expect(rule).toMatch(/overflow-wrap:\s*break-word\s*;/);
  });
});
