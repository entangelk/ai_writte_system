/**
 * 약관·방침 페이지와 공개 푸터 (브리프 `landing-page-scope` 착수 순서 ②, 2026-09-11).
 *
 * 여기서 잠그는 것 넷:
 * 1. **인증 밖이다** — 세션이 없어도 뜨고, 마운트에 어떤 조회도 내지 않는다. 가입하기
 *    전에 읽는 문서이므로 `AuthGate` 안으로 들어가면 그 자체로 계약 위반이다.
 * 2. **문서가 실제로 그려진다** — 조 제목·표·중첩 목록·고지 상자. 렌더러가 조용히
 *    한 문법을 빠뜨리면 본문 한 절이 사라지는데, 파일 대조 가드는 그것을 못 본다.
 * 3. **링크 둘만 앱 주소다** — 저장소 문서끼리의 참조는 링크가 아니라 문자다.
 * 4. **푸터는 공개 표면에만 붙는다** — 정문·약관·방침에는 있고 **작업 화면에는 없다.**
 *    (양방향: 빠지면 1·4번이, 앱 셸까지 번지면 마지막 셀이 실패한다.)
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { renderLegalDocument } from "./markdown";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, statusText: "", json: async () => body };
}

function stubFetch(...responses: Array<{ body: unknown; status?: number }>) {
  const fetchMock = vi.fn();
  for (const next of responses) {
    fetchMock.mockResolvedValueOnce(response(next.body, next.status));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("약관·방침 페이지", () => {
  it("serves the terms outside the session gate, asking nothing about the viewer", async () => {
    const fetchMock = stubFetch();

    renderAt("/terms");

    expect(
      await screen.findByRole("heading", { level: 1, name: "이용약관" }),
    ).toBeInTheDocument();
    // 세션 확인이 끼면 "세션을 확인하는 중…" 이 먼저 뜨고, 서버가 없는 환경에서는
    // 오류 화면으로 떨어진다 — 가입 전 독자에게는 둘 다 문서가 아니다.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("세션을 확인하는 중…")).not.toBeInTheDocument();
  });

  it("serves the privacy policy with the disclosure that matters most", async () => {
    stubFetch();

    renderAt("/privacy");

    expect(
      await screen.findByRole("heading", { level: 1, name: "개인정보처리방침" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "제4조 (제3자 처리 — ★ 원고가 외부로 전송됩니다)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("이것이 이 서비스에서 가장 중요한 고지입니다.")).toBeInTheDocument();
  });

  it("renders the markdown shapes the documents actually use", async () => {
    stubFetch();

    renderAt("/privacy");

    // 표(방침 제1조) — 렌더러가 표를 모르면 `| 구분 | 항목 |` 이 문단으로 떨어진다.
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "구분" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: /복원 불가능한 해시/ })).toBeInTheDocument();
    // 고지 상자(머리말 인용) — 문서가 자기 지위를 말하는 자리다.
    expect(
      screen.getByText(/이 문서는 법률 전문가의 검토를 받지 않았다/),
    ).toBeInTheDocument();
  });

  it("keeps a nested limit list nested under the clause that introduces it", async () => {
    stubFetch();

    renderAt("/terms");

    const clause = await screen.findByText(/계정 정보에는 다음 제한이 있습니다/);
    expect(
      within(clause.closest("li") as HTMLElement).getByText(/사용자명: 최대/),
    ).toBeInTheDocument();
  });

  it("degrades an unsupported construct to text instead of hanging the page", () => {
    /**
     * 렌더러는 부분집합이고 **그 경계 밖에서 멈추지 않아야 한다.** 지원하지 않는
     * 표제 단계(`### …`)는 `startsBlock` 이 블록이라고 말하지만 받아 줄 분기가
     * 없는 줄이다 — 현재 줄을 먹지 않으면 `cursor` 가 제자리에 머물러 **무한
     * 루프**이고, 화면은 "느리다"가 아니라 **탭이 멈춘다**. 실측으로 드러났다:
     * 표 분기를 지운 변이(ML-4)가 실패가 아니라 **OOM 으로 죽었다.**
     *
     * under-strict: 현재 줄을 먹는 문장을 지우면 이 셀이 **영영 끝나지 않는다.**
     * ★ 실측(ML-8)은 *타임아웃 실패*가 아니라 **워커가 OOM 으로 죽는 것**이다 —
     * 동기 렌더 안의 무한 루프는 `testTimeout` 이 끊지 못하고 블록 배열이 힙을
     * 먼저 먹는다. 기명 셀 하나가 빨개지는 모양이 아니므로, 이 셀의 신호는
     * **전수가 완주하지 못한다**는 것이다(원래 결함도 그 모양으로 드러났다).
     * over-strict: 지원 문법을 문단으로 떨어뜨리는 과잉 교정은 위 표·목록·인용
     * 셀들이 잡는다.
     */
    render(
      <MemoryRouter>
        <article>{renderLegalDocument("## 제1조 (목적)\n\n### 소제목\n\n본문.\n")}</article>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "제1조 (목적)" })).toBeInTheDocument();
    expect(screen.getByText("### 소제목")).toBeInTheDocument();
    expect(screen.getByText("본문.")).toBeInTheDocument();
  });

  it("strips the editorial head line without eating a body line that starts the same way", () => {
    /**
     * **H3 폐쇄**(독립 검증 2026-09-11). 접두 규칙(`근거:` 걷기 · `상태`·`작성`·`버전`
     * 한 줄씩)은 **머리말에만** 적용된다. 종전에는 문서 전체를 훑어서 본문 한가운데
     * 같은 모양의 줄이 오면 **조용히 사라졌다** — 약관 조항이 통째로 없어지는데
     * 화면도 전수도 아무 말을 하지 않는다(검증이 관찰로만 기록한 축이다).
     *
     * 양방향: 범위를 문서 전체로 되돌리면 본문 줄 단정이 실패하고(조용한 삭제),
     * 걷기를 아예 없애면 머리말 단정이 실패한다(편집용 메타가 공개면에 뜬다).
     */
    render(
      <MemoryRouter>
        <article>
          {renderLegalDocument(
            "# 이용약관\n\n근거: 머리말의 편집용 메타\n\n---\n\n" +
            "## 제1조 (목적)\n\n근거: 본문 한가운데의 같은 모양\n",
          )}
        </article>
      </MemoryRouter>,
    );

    expect(screen.queryByText(/머리말의 편집용 메타/)).not.toBeInTheDocument();
    expect(screen.getByText("근거: 본문 한가운데의 같은 모양")).toBeInTheDocument();
  });

  it("links the two documents to each other and leaves repository paths as plain text", async () => {
    stubFetch();

    renderAt("/terms");

    // 본문 안에서 센다 — 푸터도 같은 이름의 링크를 들고 있고, 여기서 재는 것은
    // **약관 제6조 3항이 방침을 가리키는가**다.
    const body = within(await screen.findByRole("article"));
    const crossLinks = body.getAllByRole("link", { name: "개인정보처리방침" });
    // 약관은 세 자리에서 방침을 가리킨다(제1조·제6조 3항·제9조) — 하나만 바뀌어도
    // 나머지가 죽은 링크가 되므로 전부 센다.
    expect(crossLinks).toHaveLength(3);
    for (const link of crossLinks) {
      expect(link).toHaveAttribute("href", "/privacy");
    }
    // 저장소 안에서만 뜻이 있는 주소는 링크로 만들지 않는다 — 독자가 따라갈 수 없다.
    expect(screen.queryByRole("link", { name: "README.md" })).not.toBeInTheDocument();
    // 편집용 머리말(`근거:`)은 화면에 없다.
    expect(screen.queryByText(/service-policy-contract/)).not.toBeInTheDocument();
    // 남는 메타는 **한 줄씩** 선다 — 마크다운 기본 접합대로 붙이면 판본이
    // *"상태: … 작성: … 버전: …"* 한 문장 속에 숨는다.
    const meta = body.getAllByText(
      (_, element) => element?.classList.contains("legal-meta") ?? false,
    );
    expect(meta.map((element) => element.textContent)).toEqual([
      "상태: 시행 — 2026-09-08 · 법률 전문가 검토 전",
      "작성: 2026-09-07",
      "버전: 1.0",
    ]);
  });
});

describe("공개 푸터", () => {
  it("hangs the legal links off the front door, where there is no app shell yet", async () => {
    stubFetch({ status: 401, body: { detail: "not authenticated" } });

    renderAt("/");

    await screen.findByLabelText("아이디");
    const footer = screen.getByRole("navigation", { name: "법적 고지" });
    expect(within(footer).getByRole("link", { name: "이용약관" })).toHaveAttribute("href", "/terms");
    expect(within(footer).getByRole("link", { name: "개인정보처리방침" }))
      .toHaveAttribute("href", "/privacy");
    expect(within(footer).getByRole("link", { name: /kdtyohan@gmail.com/ }))
      .toHaveAttribute("href", "mailto:kdtyohan@gmail.com");
  });

  it("hangs the footer off every public face of the front door, not just the form", async () => {
    /**
     * **LB1 폐쇄**(독립 검증 2026-09-11, 세션 59). SoT v1.8.56 은 장착 지점을
     * *"정문 세 얼굴과 약관·방침 페이지"* 로 **열거**했지만, 셀이 지나는 얼굴은
     * **로그인 폼 하나**였다 — `AuthStatus`(세션 확인·오류)와 가입 접수 얼굴은
     * 각각만 지워도 `legal` 14 + `App` 29 셀이 전건 초록이었다(MO-6a·6b).
     *
     * **세션 56 B1(배너 장착 지점)과 같은 실패 형태가 한 슬라이스 만에 재발했다**:
     * 계약이 *어디에 걸리는가* 를 말하면 셀이 **그 자리를 지나야** 한다. 열거가
     * 셋이면 셀도 셋을 본다.
     *
     * 한 셀에 세 얼굴을 담고 사이를 `unmount()` 로 끊는다 — 얼굴마다 셀을 쪼개면
     * 같은 계약이 세 자리에서 갈라지고, 하나가 빠지는 것이 다시 조용해진다.
     *
     * 양방향: 어느 한 얼굴에서 `<LegalFooter />` 를 지우면 이 셀이 **그 얼굴의
     * 이름과 함께** 실패한다(MO-6a·6b 가 각각 이 셀을 문다) · 푸터를 앱 셸까지
     * 번지게 하는 과잉은 아래 작업 화면 셀이 잡는다.
     */
    const legalNav = () => screen.queryByRole("navigation", { name: "법적 고지" });

    // ① 세션을 확인하는 중 — 응답이 아직 없다(영원히 pending 한 fetch).
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    let face = render(
      <MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>,
    );
    expect(await screen.findByText("세션을 확인하는 중…")).toBeInTheDocument();
    expect(legalNav(), "세션 확인 얼굴에 법적 고지가 없다").not.toBeNull();
    face.unmount();

    // ② 세션을 확인하지 못했다 — 401 이 아닌 실패(서버가 죽었을 때의 얼굴).
    vi.unstubAllGlobals();
    stubFetch({ status: 500, body: { detail: "boom" } });
    face = render(
      <MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>,
    );
    expect(
      await screen.findByText("세션을 확인하지 못했습니다."),
    ).toBeInTheDocument();
    expect(legalNav(), "세션 오류 얼굴에 법적 고지가 없다").not.toBeNull();
    face.unmount();

    // ③ 가입 요청이 접수되었다 — 세션이 없는 채로 머무는 얼굴이다.
    vi.unstubAllGlobals();
    stubFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { status: 201, body: { username: "bob", status: "pending" } },
    );
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    await screen.findByLabelText("아이디");
    await userEvent.click(
      screen.getByRole("button", { name: "계정이 없나요? 새 계정 요청" }),
    );
    await userEvent.type(screen.getByLabelText("아이디"), "bob");
    await userEvent.type(screen.getByLabelText("비밀번호"), "long-enough-pw");
    await userEvent.type(screen.getByLabelText("비밀번호 확인"), "long-enough-pw");
    await userEvent.click(screen.getByRole("button", { name: "가입 요청 보내기" }));
    expect(
      await screen.findByRole("heading", { name: "가입 요청이 접수되었습니다" }),
    ).toBeInTheDocument();
    expect(legalNav(), "가입 접수 얼굴에 법적 고지가 없다").not.toBeNull();
  });

  it("walks an anonymous visitor from the login screen into the terms and back", async () => {
    // 401 이 둘인 이유: 돌아온 루트는 **보호 구간을 다시 마운트**하므로 세션 확인이
    // 한 번 더 나간다(약관 페이지는 확인 자체를 안 한다 — 위 첫 셀이 그것을 잠근다).
    stubFetch(
      { status: 401, body: { detail: "not authenticated" } },
      { status: 401, body: { detail: "not authenticated" } },
    );

    renderAt("/");

    await screen.findByLabelText("아이디");
    await userEvent.click(
      within(screen.getByRole("navigation", { name: "법적 고지" }))
        .getByRole("link", { name: "이용약관" }),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "이용약관" }),
    ).toBeInTheDocument();
    // 약관 페이지의 유일한 퇴로. 세션이 없으므로 브랜드는 정문으로 떨어진다.
    await userEvent.click(screen.getByRole("link", { name: "에-라잇" }));
    expect(await screen.findByLabelText("아이디")).toBeInTheDocument();
  });

  it("carries the footer on the legal pages themselves", async () => {
    stubFetch();

    renderAt("/privacy");

    await screen.findByRole("heading", { level: 1, name: "개인정보처리방침" });
    expect(screen.getByRole("navigation", { name: "법적 고지" })).toBeInTheDocument();
    expect(screen.getByText(/운영자 entangelk/)).toBeInTheDocument();
  });

  it("leaves the working screens alone — the footer is public chrome, not app chrome", async () => {
    const fetchMock = stubFetch(
      { body: { id: "u1", username: "alice", is_admin: false } },
      { body: { projects: [] } },
    );

    renderAt("/");

    await screen.findByRole("heading", { name: "프로젝트" });
    await waitFor(() => expect(fetchMock.mock.calls).toHaveLength(2));
    expect(screen.queryByRole("navigation", { name: "법적 고지" })).not.toBeInTheDocument();
  });
});
