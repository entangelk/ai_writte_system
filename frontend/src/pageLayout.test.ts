/**
 * 페이지 컨테이너의 **한 규칙성** (Phase 10 Slice 10.4).
 *
 * **왜 필요한가 — 이 저장소는 이미 한 번 여기서 어긋났다.** 10.4 전까지 페이지
 * 컨테이너는 폭이 **세 종류**였다(`.workspace-page` 52rem · `.admin-page` 62rem ·
 * `.editor-page` 68rem). 어느 문서에도 그 규칙이 적혀 있지 않았고, 결과는 실측으로
 * 이렇게 나왔다(1440×900): 왼쪽은 셋 다 208px 로 맞는데 **오른쪽 끝이 1033 · 1193 ·
 * 1225 로 제각각**이었고 헤더 밑줄만 1257 까지 뻗어 **한쪽으로 삐져나와** 보였다.
 *
 * 아무도 그것을 "결함"으로 부르지 않은 이유는 **어떤 테스트도 배치를 안 보기 때문**
 * 이다(`toHaveClass` 0 · `ByTestId` 0). 화면 슬라이스가 자기 화면에 폭을 하나 더
 * 얹으면 그 순간 조용히 네 종류가 된다.
 *
 * 그래서 여기서 재는 것은 **값이 아니라 규칙성**이다 — "폭이 68rem 인가"가 아니라
 * **"폭을 정하는 자리가 하나인가"**. 값은 디자인 판단이라 바뀔 수 있지만, 자리가
 * 여럿이 되는 것은 언제나 결함이다.
 *
 * **양방향**:
 * - under-strict — 화면 하나에 폭을 따로 주면 첫 셀이 실패한다.
 * - over-strict — 컨테이너 폭과 `main` 의 폭 상한을 서로 다르게 두면 둘째 셀이
 *   실패한다(그 둘이 갈리면 오른쪽 끝이 다시 어긋난다).
 *
 * 실측 재현: `bash docs/plans/10_layout_probe.sh`
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, "styles.css"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));

type Rule = { selector: string; body: string };
const rules: Rule[] = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
  selector: match[1].trim().replace(/\s+/g, " "),
  body: match[2],
}));

/**
 * **인증 화면은 이 규칙의 대상이 아니다.** 로그인은 `<main class="auth-shell">`
 * 이라는 **다른 껍데기** 안에서 그려지고 그 껍데기는 `max-width: none` 에 뷰포트
 * 전체를 쓰는 grid 다 — 앱 셸(`main`, 68rem)의 오른쪽 정렬 규칙이 적용될 자리가
 * 아니고, 폼 한 장이라 31rem 이 맞다. 값이 아니라 **소속이 다르다.**
 */
const AUTH_SHELL = /login-page|auth-status/;

/** 페이지 **뿌리** 클래스 — 앱 셸 안에서 화면 전체를 감싸는 것. */
const PAGE_ROOTS = ["workspace-page", "admin-page"];

/**
 * 뿌리와 **같은 요소에** 함께 붙는 수식자를 마크업에서 읽는다
 * (`workspace-page editor-page`, `workspace-page overview-page`).
 *
 * ★ 초판은 *"이름이 `-page` 로 끝나는 클래스"* 로 셌다가 두 번 틀렸다 —
 * `editor-page` 를 뿌리로 오해했고(실은 수식자다), `access-log-page`(화면 안쪽
 * 블록)까지 페이지로 셌다. **이름 모양이 아니라 마크업에서의 자리**가 기준이다.
 */
function modifiersOnPageRoots(): string[] {
  const modifiers = new Set<string>();
  const walk = (directory: string) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".tsx") && !entry.name.includes(".test.")) {
        for (const match of readFileSync(path, "utf8").matchAll(/className=\{?"([^"]*)"/g)) {
          const classes = match[1].split(/\s+/).filter(Boolean);
          if (!classes.some((name) => PAGE_ROOTS.includes(name))) continue;
          for (const name of classes) {
            if (!PAGE_ROOTS.includes(name)) modifiers.add(name);
          }
        }
      }
    }
  };
  walk(here);
  return [...modifiers].sort();
}

/** 주어진 클래스들을 **직접** 겨냥해 그 속성을 선언하는 규칙들. */
function rulesDeclaring(property: string, classes: string[]): Rule[] {
  return rules.filter(
    (rule) =>
      !AUTH_SHELL.test(rule.selector) &&
      classes.some((name) =>
        new RegExp(`\\.${name}(?![a-z0-9-])\\s*(,|$)`).test(rule.selector),
      ) &&
      new RegExp(`(^|;|\\s)${property}:`).test(rule.body),
  );
}

describe("페이지 배치 (Phase 10 Slice 10.4)", () => {
  it("sets the page width in exactly one place", () => {
    const widthRules = rulesDeclaring("width", PAGE_ROOTS);

    // 0개면 "한 곳" 조건이 공허하게 만족된다 — 폭이 사라진 것도 결함이다.
    expect(widthRules.length).toBe(1);
    // 그 한 자리가 뿌리를 **모두** 덮어야 한다. 빠진 화면은 `main` 의 폭을
    // 그대로 써서 오른쪽 끝이 다시 어긋난다(10.4 전 실측: 192px).
    for (const root of PAGE_ROOTS) {
      expect(widthRules[0].selector, `${root} 가 공통 폭 규칙에서 빠졌다`).toMatch(
        new RegExp(`\\.${root}(?![a-z0-9-])`),
      );
    }
  });

  it("lets no page modifier override that width", () => {
    /**
     * ★ **이 셀이 10.4 자신의 누락을 잡았다.** 컨테이너를 통일해 놓고
     * `.overview-page { width: min(100%, 62rem) }` 를 남겨 둬서 프로젝트 개요
     * 화면만 여전히 62rem 이었다 — 통일했다고 적은 커밋이 실제로는 한 화면을
     * 빠뜨린 상태였고, 사람 눈으로는 그 화면을 안 열면 모른다.
     */
    const offenders = rulesDeclaring("width", modifiersOnPageRoots()).map(
      (rule) => rule.selector,
    );

    expect(offenders).toEqual([]);
  });

  it("keeps the container width equal to the shell it sits in", () => {
    /**
     * 오른쪽 끝이 맞는다는 것의 정체: **컨테이너 폭 = `main` 의 폭 상한**.
     * 둘이 갈리면 콘텐츠가 껍데기 안에서 한쪽으로 쏠리고, 헤더 밑줄만 더 길어진다
     * (10.4 전에 실제로 그랬다 — 오른쪽으로 192px).
     */
    const container = rulesDeclaring("width", PAGE_ROOTS)[0];
    const width = /(?:^|;|\s)width:\s*min\(100%,\s*([\d.]+rem)\)/.exec(container.body);
    expect(width, "공통 컨테이너 폭을 못 읽었다").not.toBeNull();

    const shell = rules.find((rule) => rule.selector === "main");
    const shellWidth = shell && /max-width:\s*([\d.]+rem)/.exec(shell.body);
    expect(shellWidth, "main 의 max-width 를 못 읽었다").toBeTruthy();

    expect(width![1]).toBe(shellWidth![1]);
  });
});

describe("원고 생성 폼 배치", () => {
  it("centers the unit label with its controls and lets the explanation use the full form width", () => {
    // under-strict: 설명을 다시 46rem로 제한하거나 한 grid 열에 가두면 오른쪽 절반이
    // 빈다. over-strict: 중앙정렬을 없애면 노출 라벨이 컨트롤 위쪽에 붙는다.
    const controlAlignments = rules
      .filter((rule) => rule.selector === ".form-controls")
      .flatMap((rule) => [...rule.body.matchAll(/align-items:\s*([^;]+);/g)])
      .map((match) => match[1].trim());
    expect(controlAlignments).toEqual(["center"]);

    const help = rules.find(
      (rule) => rule.selector === ".creation-form .unit-kind-help",
    );
    expect(help?.body).toMatch(/grid-column:\s*1\s*\/\s*-1/);
    expect(help?.body).not.toMatch(/max-width\s*:/);
  });
});

describe("관리 상세와 편집기 도구 독 배치", () => {
  it("separates account actions and the project list from the content above them", () => {
    const spacing = rules.find(
      (rule) =>
        rule.selector.includes(".admin-user-account-actions") &&
        rule.selector.includes(".admin-user-project-list"),
    );

    expect(spacing?.body).toMatch(/margin-top:\s*var\(--space-4\)/);
  });

  it("gives every fixed tool tab a large target and a visible selected state", () => {
    // under-strict: 종전 0.5rem padding+meta 글꼴로 돌아가면 크기 단정이 실패한다.
    // over-strict: 크기만 키우고 선택 강조를 없애도 selected 단정이 실패한다.
    const button = rules.find((rule) => rule.selector === ".rail-dock button");
    expect(button?.body).toMatch(/min-width:\s*5\.5rem/);
    expect(button?.body).toMatch(/min-height:\s*4\.25rem/);
    expect(button?.body).toMatch(/font-size:\s*var\(--type-base\)/);

    const selected = rules.find(
      (rule) => rule.selector === '.rail-dock button[aria-selected="true"]',
    );
    expect(selected?.body).toMatch(/color:\s*var\(--text-on-accent\)/);
    expect(selected?.body).toMatch(/background:\s*var\(--action-primary\)/);
  });
});
