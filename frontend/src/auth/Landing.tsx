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
 * - Phase N: 집필 사진과 작업 순서로 소개를 구성한다. 사진은 기능 화면이 아니다.
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
    <main className="landing-shell">
      <nav className="landing-nav" aria-label="소개 페이지">
        <a className="landing-logo" href="#top">에-라잇<span aria-hidden="true">.</span></a>
        <div>
          <a href="#workflow">작업실 둘러보기</a>
          <button className="auth-submit" type="button" onClick={onEnter}>로그인</button>
        </div>
      </nav>
      <section className="landing-hero" id="top" aria-labelledby="landing-title">
        <img className="landing-photo" src="/images/writing-desk.webp" alt="" fetchPriority="high" width="1536" height="1024" />
        <header className="landing-hero-copy">
          <p className="eyebrow">이야기가 쌓이는 곳</p>
          <p className="landing-wordmark">에-라잇<span aria-hidden="true">.</span></p>
          <h1 id="landing-title">쓴 것을 기억하는 집필 작업실</h1>
          <p>
            설정과 인물, 지난 원고를 기억하며 이어 쓰세요.
            다음 문장의 결정은 언제나 작가의 몫입니다.
          </p>
          <a className="landing-explore" href="#workflow">작업실 둘러보기 <span aria-hidden="true">↘</span></a>
        </header>
        <span className="landing-hero-caption" aria-hidden="true">한 문장에서, 하나의 세계로.</span>
      </section>
      <div className="landing-page">
        <section className="landing-workflow" id="workflow" aria-labelledby="workflow-title">
          <header className="landing-section-heading">
            <p className="eyebrow">집필의 흐름</p>
            <h2 id="workflow-title">쓰고, 기억하고.<br />다시, 이어 쓰고.</h2>
            <p>흩어진 설정과 원고를 한 작업실에서 다룹니다.</p>
          </header>
          <div className="landing-blocks">
          <section>
            <h3>장편을 위한 원고 구조</h3>
            <p>
              작품은 장과 장면으로 쌓습니다. 저장할 때마다 버전이 남아 언제든
              이전 모습으로 돌아갈 수 있습니다.
            </p>
          </section>
          <section>
            <h3>쓴 것이 기억이 되는 구조</h3>
            <p>
              저장된 원고에서 인물·사건·열린 질문을 관찰로 남기고, 글을 쓸 때
              필요한 기억만 근거 위치와 함께 찾아 줍니다. 기억은 임의로 지워지지
              않고 버전을 쌓습니다.
            </p>
          </section>
          <section>
            <h3>AI 출력은 곧 원고가 아니다</h3>
            <p>
              이어쓰기 후보는 정본에 바로 들어가지 않습니다. 연속성·시점·설정의
              지적과 함께 돌아오고, 사람이 검토해 채택할 때만 원고가 됩니다.
            </p>
          </section>
          <section>
            <h3>호출마다 기록이 남는다</h3>
            <p>
              AI 호출은 건마다 감사 기록으로 남고 프로젝트별 화면에서 성공·실패와
              사용량을 볼 수 있습니다.
            </p>
          </section>
          </div>
        </section>

        <aside className="landing-limits" id="start" aria-label="시작하기 전에 알아 둘 것">
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
          <div className="landing-start-copy">
            <p className="eyebrow">당신의 다음 원고</p>
            <h2>이제, 이야기를 시작하세요.</h2>
          </div>
          <button className="auth-submit" type="button" onClick={onEnter}>
            기존 계정으로 입장
          </button>
          <button className="auth-switch" type="button" onClick={onSignup}>
            새 계정 요청
          </button>
        </div>
      </div>
      <LegalFooter />
    </main>
  );
}
