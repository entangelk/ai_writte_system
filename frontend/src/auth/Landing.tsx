import { Link } from "react-router";
import { LegalFooter } from "../legal/LegalFooter";

/**
 * 루트의 익명 얼굴 — 랜딩 (브리프 `landing-page-scope` D1=ⓒ, 오너 2026-09-08).
 *
 * *"소개 + 정직한 한계"*: 무엇을 하는 도구인지를 먼저 말하되, 승인제 가입 ·
 * 원고의 외부 전송 · 개인 프로젝트라는 세 가지 사실을 **가입 절차 앞에** 밝힌다.
 * 고지를 화면 구석이 아니라 들어오는 문에 둔다는 동의 게이트 결정과 같은 방향이
 * 고 이 순서를 만든 결정이다.
 *
 * - **스크린샷은 없다** — 육안 확인 목록이 닫힌 뒤 붙인다(브리프 추천 그대로).
 * - **문구의 정본은 [`docs/product-overview.md`](../../../docs/product-overview.md)
 *   §1·§3** 이지 `abstract.md` 가 아니다(초안에서 달라진 다섯이 있다).
 * - 한계의 셋째 문장(**외부 추론 서비스**)에 벤더 이름을 박지 않는다 — 어느
 *   사업자인가는 배포 구성이 정하는 값이라 방침 제4조 3항이 그 정본이다.
 *   여기에 이름을 쓰면 벤더를 바꿀 때 이 화면과 방침이 함께 안 움직이면 거짓이
 *   된다.
 */
export function Landing({
  onEnter,
  onSignup,
}: {
  onEnter: () => void;
  onSignup: () => void;
}) {
  return (
    <main className="auth-shell">
      <section className="landing-page page-enter">
        <header className="login-heading">
          <p className="eyebrow">에-라잇</p>
          <h1>쓴 것을 기억하는 집필 작업실</h1>
          <p>
            설정과 인물, 지난 원고를 AI가 기억한 채로 이어서 씁니다. 무엇을 하는
            도구인지, 그리고 무엇을 감수해야 하는지 먼저 말합니다.
          </p>
        </header>

        <div className="landing-blocks">
          <section>
            <h2>장편을 위한 원고 구조</h2>
            <p>
              작품은 장과 장면으로 쌓습니다. 저장할 때마다 버전이 남아 언제든
              이전 모습으로 돌아갈 수 있습니다.
            </p>
          </section>
          <section>
            <h2>쓴 것이 기억이 되는 구조</h2>
            <p>
              저장된 원고에서 인물·사건·열린 질문을 관찰로 남기고, 글을 쓸 때
              필요한 기억만 근거 위치와 함께 찾아 줍니다. 기억은 임의로 지워지지
              않고 버전을 쌓습니다.
            </p>
          </section>
          <section>
            <h2>AI 출력은 곧 원고가 아니다</h2>
            <p>
              이어쓰기 후보는 정본에 바로 들어가지 않습니다. 연속성·시점·설정의
              지적과 함께 돌아오고, 사람이 검토해 채택할 때만 원고가 됩니다.
            </p>
          </section>
          <section>
            <h2>호출마다 기록이 남는다</h2>
            <p>
              AI 호출은 건마다 감사 기록으로 남고 프로젝트별 화면에서 성공·실패와
              사용량을 볼 수 있습니다.
            </p>
          </section>
        </div>

        <aside className="landing-limits" aria-label="시작하기 전에 알아 둘 것">
          <h2>시작하기 전에</h2>
          <ul>
            <li>
              <strong>가입은 승인제입니다.</strong> 요청만으로는 로그인할 수
              없고, 운영자가 승인한 뒤에 계정이 열립니다.
            </li>
            <li>
              <strong>원고가 외부로 전송됩니다.</strong> AI 생성·분석·검색 색인
              과정에서 원고 본문이 외부 추론 서비스로 전송됩니다. 무엇이 어디로
              가는지는{" "}
              <Link to="/privacy">개인정보처리방침 제4조</Link>가 자세히
              적습니다.
            </li>
            <li>
              <strong>개인 프로젝트입니다.</strong> 한 사람이 만들고 운영합니다.
            </li>
          </ul>
        </aside>

        <div className="landing-actions">
          {/* ★ 버튼 이름은 "작업실 입장"이 될 수 없다 — 그 이름은 로그인 폼의
              제출 버튼이다. 두 얼굴은 동시에 뜨지 않지만 셀의 역할 질의는
              문구로 가리므로 겹치면 이름으로 화면을 찾는 셀이 전부 흔들린다. */}
          <button className="auth-submit" type="button" onClick={onEnter}>
            로그인
          </button>
          <button className="auth-switch" type="button" onClick={onSignup}>
            새 계정 요청
          </button>
        </div>
      </section>
      <LegalFooter />
    </main>
  );
}
