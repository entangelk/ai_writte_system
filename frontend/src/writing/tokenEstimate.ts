// K-4 (프론트 글자수 표시·경고): 입력 텍스트를 토큰으로 추정해 카운터·소프트 경고에 쓴다.
//
// **1.7은 서버 회계 상수의 미러다** —
// services/application/app/context_search/service.py:558 의 KOREAN_CHARS_PER_TOKEN 과 같은
// 값이어야 카운터가 서버 예산(R-a 유도, GET /writing/budget)과 같은 단위를 말한다. 서버가 이
// 상수를 바꾸면 여기도 맞춘다. **불일치가 영향을 주는 것은 표시되는 경고뿐**이며, 실제 창 초과는
// 서버의 K-3 가드(real tokenization)가 막으므로 여기의 추정 오차는 표시의 미세한 어긋남으로만
// 나타난다.
export const KOREAN_CHARS_PER_TOKEN = 1.7;

/**
 * 글자수(Unicode code point)를 1.7 자/tok 로 토큰 추정한다. 서버 estimate_tokens(len/1.7) 과
 * 같은 식이다. `[...text].length` 로 code point 를 세는 것은 Python 의 len(text) 를 미러링하기
 * 때문이다(서로게이트 페어를 한 글자로 센다).
 */
export function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil([...text].length / KOREAN_CHARS_PER_TOKEN));
}

/** 지시문 카운터 표기: "X자 (≈Y 토큰)". */
export function formatInstructionCount(text: string): string {
  const chars = [...text].length;
  return `${chars.toLocaleString("ko-KR")}자 (≈${estimateTokens(text).toLocaleString("ko-KR")} 토큰)`;
}

/** 원고 본문 표기: "X자". 창과 무관(브리프 §6 — /writing/generate 에 본문이 안 실린다). */
export function formatCharCount(text: string): string {
  return `${[...text].length.toLocaleString("ko-KR")}자`;
}
