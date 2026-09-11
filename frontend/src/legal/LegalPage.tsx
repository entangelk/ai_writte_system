import { Link } from "react-router";
import privacyPolicySource from "./privacy-policy.md?raw";
import termsOfServiceSource from "./terms-of-service.md?raw";
import { renderLegalDocument } from "./markdown";
import { LegalFooter } from "./LegalFooter";

/**
 * 약관·방침 페이지 (브리프 `landing-page-scope` D2=ⓐ, 착수 순서 ②).
 *
 * **인증 밖 라우트다.** 가입하기 전에 읽어야 하는 문서이므로 세션이 없어도 떠야
 * 하고, 그래서 이 페이지는 `AuthGate` 바깥에 걸린다(`App.tsx`) — 마운트할 때 어떤
 * 조회도 내지 않는다. **API 가 느는 것은 아니다**: 공개 API 표면은 그대로 넷이고
 * 프런트 라우트만 둘 늘었다.
 *
 * **본문은 여기서 쓰지 않는다** — `docs/legal/*.md` 의 사본을 그대로 싣고
 * `renderLegalDocument` 가 읽을 때 변환한다. 사본과 정본이 같은지는
 * `legalSource.test.ts` 가 바이트로 잠근다(D2=ⓐ 의 단점에 대한 처방).
 *
 * **셸은 앱 셸의 규칙을 그대로 빌린다**(`app-shell`·`app-header`) — 같은 제품의
 * 같은 머리이고, 폭·밑줄을 다시 정하면 화면마다 폭이 생기는 그 결함이다(10.4).
 * 다만 **계정 메뉴도 유예 배너도 없다**: 세션을 모르는 자리이므로 들 수 있는 것이
 * 없다. 브랜드 링크가 유일한 퇴로이고, 로그인 여부에 따라 프로젝트 목록이나
 * 정문으로 떨어진다.
 */
const DOCUMENTS = {
  terms: termsOfServiceSource,
  privacy: privacyPolicySource,
} as const;

export type LegalDocumentName = keyof typeof DOCUMENTS;

export function LegalPage({ name }: { name: LegalDocumentName }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="brand" to="/">에-라잇</Link>
      </header>
      <main>
        <article className="legal-document page-enter">
          {renderLegalDocument(DOCUMENTS[name])}
        </article>
        <LegalFooter />
      </main>
    </div>
  );
}
