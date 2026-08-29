/**
 * 보조 이동 링크의 발견성 (2026-08-29 도그푸드 UI).
 *
 * 버튼 면은 작업을 실행하는 주 동작에만 쓴다. 반면 결과 안내·메타 행·권한 발급 뒤의
 * 화면 이동은 문장 속 보조 동작이므로, 모두 같은 밑줄 링크로 보이게 한다. 목록 행,
 * 뒤로 가기, 계정 메뉴는 각각 행/방향/메뉴라는 문맥이 있어 이 규칙의 대상이 아니다.
 *
 * 양방향:
 * - under-strict: 보조 이동 한 곳에서 클래스를 빼면 해당 파일이 실패한다.
 * - over-strict: 목록 행·뒤로 가기·계정 메뉴까지 이 클래스로 합치면 대상 집합이
 *   달라져 실패한다. 서로 다른 이동 문맥을 한 외양으로 뭉개지 않는다.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, "styles.css"), "utf8");

const SECONDARY_NAVIGATION = [
  "review/AnalysisTrigger.tsx",
  "projects/ProjectOverview.tsx",
  "projects/ActivityTimelinePage.tsx",
  "me/PersonalHubPage.tsx",
  "admin/AdminProjectCard.tsx",
];

function sourcesUsingSharedTreatment(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourcesUsingSharedTreatment(path);
    if (!entry.name.endsWith(".tsx") || entry.name.includes(".test.")) return [];
    return /className="[^"]*\binline-navigation-link\b/.test(readFileSync(path, "utf8"))
      ? [relative(here, path)] : [];
  });
}

describe("보조 이동 링크", () => {
  it("gives every plain secondary navigation link the shared treatment", () => {
    const missing = SECONDARY_NAVIGATION.filter((path) => {
      const source = readFileSync(resolve(here, path), "utf8");
      return !source.includes('className="inline-navigation-link"');
    });

    expect(missing).toEqual([]);
    expect(sourcesUsingSharedTreatment(here).sort()).toEqual(SECONDARY_NAVIGATION.slice().sort());
  });

  it("uses an underlined, high-emphasis link without turning it into a button", () => {
    const rule = css.match(/\.inline-navigation-link\s*\{([^}]*)\}/)?.[1] ?? "";

    expect(rule).toMatch(/font-weight:\s*700\s*;/);
    expect(rule).toMatch(/text-decoration-line:\s*underline\s*;/);
    expect(rule).not.toMatch(/background\s*:/);
    expect(rule).not.toMatch(/padding\s*:/);
  });
});
