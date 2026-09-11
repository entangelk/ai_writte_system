import { Link } from "react-router";

/**
 * 공개 표면의 푸터 — 약관 · 방침 · 문의 (브리프 `landing-page-scope`, 오너 2026-09-07:
 * *"`[문의 연락처]` 는 랜딩 푸터에 들어간다"*).
 *
 * **여기 있는 세 자리가 공개 전 법적 요건의 도달 경로다.** 약관·방침은 주소를
 * 치는 것 말고는 들어갈 길이 없었고(라우트 자체가 없었다), 문의 연락처는 저장소
 * 문서 안에만 있었다.
 *
 * **붙는 자리는 인증 밖 화면들**이다 — 정문(로그인·세션 상태)과 약관·방침 페이지,
 * 그리고 랜딩(착수 순서 ③). 작업 화면(앱 셸)에는 달지 않는다: 매일 쓰는 도구의
 * 화면마다 법적 링크 줄이 따라다닐 이유가 없고, 그 결정은 화면 문법을 작업 도구로
 * 통일한 10.4 와 같은 방향이다.
 *
 * **★ 연락처는 개인 이메일이고 이 자리가 여덟 번째 사본이다**(나머지 일곱은
 * `docs/legal/`). 폼·별칭으로 바꾸는 날 치환 지점이 그만큼이며, 가드
 * (`legalSource.test.ts`)가 이 자리와 문서가 같은 주소를 말하는지 잠근다.
 */
export const CONTACT_EMAIL = "kdtyohan@gmail.com";

/** 약관 제1조가 정한 운영 주체 표기. */
export const OPERATOR = "entangelk";

export function LegalFooter() {
  return (
    <footer className="legal-footer">
      <nav aria-label="법적 고지">
        <Link to="/terms">이용약관</Link>
        <Link to="/privacy">개인정보처리방침</Link>
        <a href={`mailto:${CONTACT_EMAIL}`}>문의 {CONTACT_EMAIL}</a>
      </nav>
      <p>운영자 {OPERATOR} · 개인 프로젝트</p>
    </footer>
  );
}
