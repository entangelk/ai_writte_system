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
 * 유닛 본문 글자수 상한 — 오너 결정 D5-2(2026-08-27, "전 경로 4000자"). 서버 기본값
 * `DRAFT_RAW_TEXT_MAX_CHARS`(app/env.py)의 미러다: 서버는 이 상한을 저장 스키마(422)와
 * accept 합성(400, provider 호출 앞) 둘 다에 시행하므로, 여기의 경고·저장 차단은 사용자가
 * 서버 거부를 만나기 *전에* 알게 하는 사전 안내일 뿐 최후 방어가 아니다. ★ 잘라내기로
 * 시행하지 않는다 — textarea maxLength 는 붙여넣기를 몰래 잘라 정본을 손상시킨다.
 *
 * 근거(2026-08-27 실측 정정): 원고는 매 생성마다 검색 조각으로 프롬프트에 실린다 —
 * 현재 장면 문단 전부(제목 없는 유닛이면 유닛 전체)+직전 문단 5개를 꺼내 예산(요청 상한
 * 8192)까지 편집해 넣는다. 4000자 ≈ 2,353 tok = 예산의 ~29%라 온전히 들어가고, 유닛이
 * 길어지면 다른 조각이 밀려 이어쓰기가 직전 흐름·기억을 잃는다(조용한 품질 저하).
 */
export const RAW_TEXT_MAX_CHARS = 4000;

/** 상한 임박 안내를 켜는 시점(상한의 90%). */
export const RAW_TEXT_WARN_CHARS = Math.floor(RAW_TEXT_MAX_CHARS * 0.9);

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

/**
 * 원고 본문 표기: "X자". 본문은 생성 프롬프트에 검색 조각(현재 장면+직전 5문단)으로
 * 실린다(2026-08-27 정정 — 종전 "안 실린다" 주석은 잘못이었다). 카운터의 역할은
 * RAW_TEXT_MAX_CHARS 상한 안내뿐, 토큰 환산은 하지 않는다.
 */
export function formatCharCount(text: string): string {
  return `${[...text].length.toLocaleString("ko-KR")}자`;
}
