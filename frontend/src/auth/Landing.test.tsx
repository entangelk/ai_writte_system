import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Landing } from "./Landing";

describe("랜딩의 작업실 진입", () => {
  it("connects both login entry points while keeping signup a separate action", async () => {
    // under-strict: 하단 새 진입 버튼의 콜백이 빠지면 실패.
    // over-strict: 로그인과 가입을 같은 콜백으로 합쳐도 실패.
    const onEnter = vi.fn();
    const onSignup = vi.fn();
    render(<MemoryRouter><Landing onEnter={onEnter} onSignup={onSignup} /></MemoryRouter>);
    // ByRole 의 name 문자열 매칭은 전체 일치가 기본이라 nav 의 "로그인" 만 잡는다
    // (하단 진입 버튼 "기존 계정으로 입장" 과는 다른 이름).
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await userEvent.click(screen.getByRole("button", { name: "기존 계정으로 입장" }));
    expect(onEnter).toHaveBeenCalledTimes(2);
    expect(onSignup).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "새 계정 요청" }));
    expect(onSignup).toHaveBeenCalledOnce();
    expect(onEnter).toHaveBeenCalledTimes(2);
  });

  it("gives the overview links a real destination and keeps disclosures before signup", () => {
    // under-strict: 둘러보기 링크 목적지를 지우면 실패.
    // over-strict: 소개를 강조하며 필수 고지를 가입 행동 뒤로 밀어도 실패.
    render(<MemoryRouter><Landing onEnter={() => {}} onSignup={() => {}} /></MemoryRouter>);
    for (const link of screen.getAllByRole("link", { name: /작업실 둘러보기/ })) {
      const target = document.querySelector(link.getAttribute("href")!);
      expect(target).toContainElement(screen.getByRole("heading", { name: /쓰고, 기억하고/ }));
    }
    const notice = screen.getByRole("complementary", { name: "시작하기 전에 알아 둘 것" });
    const signup = screen.getByRole("button", { name: "새 계정 요청" });
    expect(notice.compareDocumentPosition(signup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
