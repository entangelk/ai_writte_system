import { describe, expect, it } from "vitest";
import {
  estimateTokens,
  formatCharCount,
  formatInstructionCount,
  KOREAN_CHARS_PER_TOKEN,
} from "./tokenEstimate";

describe("estimateTokens", () => {
  it("빈 문자열은 최소 1 토큰(0이 되면 예산이 0으로 보여 거짓 경고)", () => {
    expect(estimateTokens("")).toBe(1);
  });

  it("1.7 자/tok 로 추정 — 1700자 = 1000 토큰(서버 estimate_tokens 와 같은 식)", () => {
    expect(estimateTokens("가".repeat(1700))).toBe(1000);
  });

  it("code point 단위로 센다(서로게이트 페어 = 1글자) — Python len(text) 미러", () => {
    // "😀"는 1 code point 지만 UTF-16 surrogate pair 2개. [...text].length === 1.
    expect(estimateTokens("😀")).toBe(
      Math.max(1, Math.ceil(1 / KOREAN_CHARS_PER_TOKEN)),
    );
  });
});

describe("formatInstructionCount", () => {
  it("'X자 (≈Y 토큰)' 형태 — 170자 ≈ 100 토큰", () => {
    expect(formatInstructionCount("가".repeat(170))).toBe("170자 (≈100 토큰)");
  });
});

describe("formatCharCount", () => {
  it("'X자' 형태(토큰 추정 없음 — 브리프 §6, 창과 무관)", () => {
    expect(formatCharCount("가나다라마")).toBe("5자");
  });
});
