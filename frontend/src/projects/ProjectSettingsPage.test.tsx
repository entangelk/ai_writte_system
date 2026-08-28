import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectSettingsPage } from "./ProjectSettingsPage";

/** 탭이 무엇을 청하든 답한다 — 이 파일이 재는 것은 셸이지 탭 내용이 아니다. */
function stubFetch() {
  const fetchMock = vi.fn(async (url: string) => {
    const body = url.endsWith("/p1")
      ? { id: "p1", name: "겨울 이야기", archived: false }
      : url.includes("/chapters")
        ? { chapters: [] }
      : url.includes("/brief")
        ? { brief: null }
        : url.includes("/memory")
          ? { memory: [] }
          : url.includes("/review")
            ? { project_id: "p1", items: [], gate_findings: [] }
            : url.includes("/activity")
              ? { events: [] }
              : { drafts: [] };
    return { ok: true, status: 200, statusText: "", json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderSettings(path = "/projects/p1/settings") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId/settings" element={<ProjectSettingsPage />} />
        <Route path="/" element={<p data-testid="project-list-marker">목록</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * 프로젝트 설정 셸 (오너 2026-08-27).
 *
 * under-strict: 세 화면 중 하나를 다시 작업 공간 첫 화면으로 빼면 탭이 사라져
 * 재실패한다 — *"너무 어지럽다"* 던 그 상태다.
 * over-strict: 검토함까지 여기로 끌어오는 과대교정도 실패한다. 검토함은 집필
 * 중 수시로 드나드는 작업 흐름이라 설정이 아니다(오너 결정).
 */
describe("ProjectSettingsPage", () => {
  it("gathers the three occasional screens under one tab bar", async () => {
    stubFetch();
    renderSettings();

    expect(await screen.findByRole("heading", { name: "겨울 이야기" }))
      .toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["작품 정보·개요", "원고 내보내기", "활동 타임라인"]);
    expect(screen.queryByRole("tab", { name: "검토함" })).toBeNull();
    expect(screen.getByRole("link", { name: "← 원고 작업 공간" }))
      .toHaveAttribute("href", "/projects/p1");
  });

  it("opens the brief tab by default and switches on click", async () => {
    stubFetch();
    renderSettings();

    await screen.findByRole("heading", { name: "작품 시작 정보" });

    await userEvent.click(screen.getByRole("tab", { name: "원고 내보내기" }));
    expect(await screen.findByRole("heading", { name: "원고 내보내기" }))
      .toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "작품 시작 정보" })).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: "활동 타임라인" }));
    expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
  });

  it("honours ?tab= so a shared link opens where it says", async () => {
    // 탭 상태가 컴포넌트 안에만 있으면 새로고침·공유 링크가 첫 탭으로 되돌아간다.
    stubFetch();
    renderSettings("/projects/p1/settings?tab=activity");

    expect(await screen.findByText(/최근 100건까지 보여줍니다/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "활동 타임라인" }))
      .toHaveAttribute("aria-selected", "true");
  });

  it("falls back to the brief tab for an unknown tab name", async () => {
    stubFetch();
    renderSettings("/projects/p1/settings?tab=nonsense");

    expect(await screen.findByRole("heading", { name: "작품 시작 정보" }))
      .toBeInTheDocument();
  });

  it("keeps the permanent purge behind the exact project name", async () => {
    // 프로젝트 삭제(2026-08-28 오너 결정) — 관리 콘솔 purge 면과 같은 이름 확인
    // 가드. 양방향: 이름이 다르면(under) 절대 활성화되지 않고, 일치하면(over)
    // 2단계(보관 → purge)를 순서대로 부른 뒤 목록으로 나간다.
    const fetchMock = stubFetch();
    renderSettings();
    await screen.findByRole("heading", { name: "겨울 이야기" });

    await userEvent.click(screen.getByRole("button", { name: "프로젝트 삭제…" }));
    const purgeButton = screen.getByRole("button", { name: "영구 삭제" });
    expect(purgeButton).toBeDisabled();

    await userEvent.type(
      screen.getByLabelText(/겨울 이야기.*입력하세요/), "다른 이름",
    );
    expect(purgeButton).toBeDisabled();

    const confirmation = screen.getByLabelText(/겨울 이야기.*입력하세요/);
    await userEvent.clear(confirmation);
    await userEvent.type(confirmation, "겨울 이야기");
    expect(purgeButton).toBeEnabled();
    await userEvent.click(purgeButton);

    // 2단계 순서 — 보관(soft)이 purge 앞에 온다.
    await waitFor(() => {
      const calls = fetchMock.mock.calls as unknown as [
        string, RequestInit | undefined,
      ][];
      const archive = calls.find(([url, init]) =>
        url === "/api/projects/p1" && init?.method === "DELETE");
      const purge = calls.find(([url]) => url === "/api/projects/p1/purge");
      expect(archive).toBeDefined();
      expect(purge).toBeDefined();
      expect(JSON.parse(String(purge![1]?.body))).toEqual({
        reason: "설정 탭에서 소유자 삭제",
      });
      expect(calls.indexOf(archive!)).toBeLessThan(calls.indexOf(purge!));
    });
    expect(await screen.findByTestId("project-list-marker")).toBeInTheDocument();
  });

  it("locks the owner purge behind uncertain on a 503 (D4=A)", async () => {
    // 검증 B5(2026-08-28, 오너 ⓐ) — 파기 단계 503 은 재시도를 제공하지 않는다.
    // 관리자 면과 같은 임계다: 이미 시작된 파기를 재시도로 확정할 수 없어 거짓
    // 안내가 된다. under: 버튼을 되살리면 셀이 실패한다.
    const ok = (body: unknown) => ({
      ok: true, status: 200, statusText: "", json: async () => body,
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/p1/purge")) {
        return {
          ok: false, status: 503, statusText: "",
          json: async () => ({ detail: "storage" }),
        };
      }
      if (url.endsWith("/drafts")) return ok({ drafts: [] });
      if (url.includes("/brief")) return ok({ brief: null });
      if (url.includes("/memory")) return ok({ memory: [] });
      if (url.includes("/review")) return ok({ project_id: "p1", items: [], gate_findings: [] });
      if (url.includes("/activity")) return ok({ events: [] });
      return ok({ id: "p1", name: "겨울 이야기", archived: false });
    }));

    renderSettings();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "프로젝트 삭제…" }));
    const confirmation = screen.getByLabelText(/겨울 이야기.*입력하세요/);
    await userEvent.type(confirmation, "겨울 이야기");
    await userEvent.click(screen.getByRole("button", { name: "영구 삭제" }));

    expect(await screen.findByRole("alert"))
      .toHaveTextContent("다시 시도하지 말고 purge reconciler로");
    // uncertain — 재시도 버튼이 아예 사라지고 취소·입력도 잠긴다.
    expect(screen.queryByRole("button", { name: "영구 삭제" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    expect(confirmation).toBeDisabled();
  });

  it("revives the button when only the archive step failed", async () => {
    // 단계 구분의 반대 방향 — 보관(soft) 실패는 아직 파괴된 것이 없어 재시도가
    // 안전하다. over: 이 실패까지 잠그면 "파괴 없는 실패"에 갇힌다.
    const ok = (body: unknown) => ({
      ok: true, status: 200, statusText: "", json: async () => body,
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      // 보관(DELETE /p1)만 실패한다 — 조회(GET /p1)는 정상이어야 화면이 뜬다.
      if (url.endsWith("/p1") && init?.method === "DELETE") {
        return {
          ok: false, status: 503, statusText: "",
          json: async () => ({ detail: "storage" }),
        };
      }
      if (url.endsWith("/drafts")) return ok({ drafts: [] });
      if (url.includes("/brief")) return ok({ brief: null });
      if (url.includes("/memory")) return ok({ memory: [] });
      if (url.includes("/review")) return ok({ project_id: "p1", items: [], gate_findings: [] });
      if (url.includes("/activity")) return ok({ events: [] });
      return ok({ id: "p1", name: "겨울 이야기", archived: false });
    }));

    renderSettings();
    await screen.findByRole("heading", { name: "겨울 이야기" });
    await userEvent.click(screen.getByRole("button", { name: "프로젝트 삭제…" }));
    const confirmation = screen.getByLabelText(/겨울 이야기.*입력하세요/);
    await userEvent.type(confirmation, "겨울 이야기");
    await userEvent.click(screen.getByRole("button", { name: "영구 삭제" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // 1단계 실패 — 버튼이 살아 있다(재시도 안내가 아니라 그냥 오류).
    expect(screen.getByRole("button", { name: "영구 삭제" })).toBeEnabled();
    expect(screen.queryByText(/다시 시도하지 말고/)).not.toBeInTheDocument();
  });
});
