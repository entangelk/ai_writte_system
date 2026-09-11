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
