/**
 * **두 정본을 묶는 가드** (브리프 `landing-page-scope` D2=ⓐ, 2026-09-11).
 *
 * D2 는 약관·방침 본문을 프런트에 싣기로 하면서 그 단점을 분명히 적었다 — *"본문이
 * 두 곳(`docs/legal/` 과 프런트)이 된다 — 갱신 시 갈라진다"*. 그리고 **가드가 그
 * 단점의 값**이라고 못 박았다: *"없으면 ⓐ 의 단점이 그대로 실현된다."* 이 파일이
 * 그 가드다.
 *
 * 렌더 테스트로는 이 자리를 볼 수 없다 — 프런트 사본만 고치면 화면은 새 문장을
 * 보여 주고 전수는 초록인데, **회원이 동의한 문서와 저장소가 보관하는 문서가
 * 달라진다**. 그래서 DOM 이 아니라 파일을 읽는다(`productName.test.ts` 선례).
 *
 * **양방향**:
 * - under-strict — 어느 한쪽만 고치면 첫 셀이 **그 파일 이름과 함께** 실패한다.
 * - over-strict — 사본을 지우거나 파일 목록을 줄이면(= 감시를 줄이면) 같은 셀이
 *   실패한다. 짝이 비는 것도 불일치다.
 *
 * **버전 문자열은 핀이다.** `1.0` 은 계약 리터럴이고(가입 동의 게이트가 동의 시각과
 * 함께 저장한다 — HANDOFF 10번) 정본이 문서뿐이라 상징 참조로는 못 잠근다. 백엔드
 * 핀 셀(`tests/test_service_policy_contract.py::...test_both_documents_carry_the_enforced_version_and_date`)
 * 과 **같은 값을 여기서도 직접 든다** — 게이트가 상수를 만드는 날 둘이 그 상수를
 * 가리키게 바꾼다.
 */

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CONTACT_EMAIL, OPERATOR, TERMS_VERSION } from "./LegalFooter";

const here = dirname(fileURLToPath(import.meta.url));
const CANONICAL = resolve(here, "../../../docs/legal");

/** 프런트 사본 ↔ 저장소 정본. 파일명이 다른 것은 정본이 `*-draft.md` 경로를 지키기 때문이다. */
const BUNDLED = {
  "terms-of-service.md": "terms-of-service-draft.md",
  "privacy-policy.md": "privacy-policy-draft.md",
} as const;

/**
 * 시행 판본의 버전 문자열 — 동의 게이트(가입 폼)가 요청에 실어 보내고 서버가
 * 저장하는 값. 동의 게이트(2026-09-12)가 프런트 상수를 만들었으므로 이 핀은
 * 그 상수와 문서를 묶는다(백엔드 핀은 `tests/test_service_policy_contract.py`
 * 가 `auth/users.py::TERMS_VERSION` 과 묶는다).
 */
const ENFORCED_VERSION = TERMS_VERSION;

describe("법적 문서 사본 (브리프 landing-page-scope D2=ⓐ)", () => {
  it("keeps every bundled copy byte-identical to the canonical document", () => {
    for (const [copy, canonical] of Object.entries(BUNDLED)) {
      expect(
        readFileSync(join(here, copy), "utf8"),
        `${copy} 가 docs/legal/${canonical} 와 갈라졌다 — 한쪽만 고쳤다`,
      ).toBe(readFileSync(join(CANONICAL, canonical), "utf8"));
    }
  });

  it("bundles every canonical document, so the guard cannot shrink quietly", () => {
    // 정본이 셋째 문서를 얻었는데 싣지 않으면 푸터가 가리킬 곳이 없고, 위 셀은
    // **아는 짝만** 보므로 조용히 통과한다. 목록 자체를 디스크와 대조한다
    // (`typeScale.test.ts` 4번이 같은 맹점을 닫은 방식이다).
    const canonicalDocuments = readdirSync(CANONICAL)
      .filter((name) => name.endsWith(".md") && name !== "README.md")
      .sort();

    expect(canonicalDocuments).toEqual(Object.values(BUNDLED).slice().sort());
  });

  it("pins the enforced version string both documents and the consent gate share", () => {
    for (const copy of Object.keys(BUNDLED)) {
      const lines = readFileSync(join(here, copy), "utf8").split("\n");
      expect(lines, `${copy}: 머리말 버전`).toContain(`버전: \`${ENFORCED_VERSION}\``);
      expect(
        lines.some((line) => line.startsWith("- 이 ") && line.endsWith(`버전: \`${ENFORCED_VERSION}\``)),
        `${copy}: 부칙 버전 줄이 머리말과 다른 판본을 말한다`,
      ).toBe(true);
    }
  });

  it("shows the same contact address and operator the documents carry", () => {
    // 연락처는 개인 이메일이고 푸터가 **여덟 번째 사본**이다. 폼·별칭으로 바꾸는
    // 날 한 자리만 고치면 화면과 약관이 서로 다른 주소를 말한다.
    for (const copy of Object.keys(BUNDLED)) {
      expect(readFileSync(join(here, copy), "utf8")).toContain(CONTACT_EMAIL);
    }
    expect(readFileSync(join(here, "terms-of-service.md"), "utf8")).toContain(
      `**${OPERATOR}**(이하 "운영자")`,
    );
  });
});
