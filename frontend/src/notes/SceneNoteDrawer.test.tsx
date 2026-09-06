/**
 * 메모 탭의 드로어 배선 (Slice 4).
 *
 * 이 파일이 `DraftEditor.test.tsx` 가 아니라 여기 있는 이유: 배선이 잠그는 것은
 * **메모 기능**이지 편집기의 기존 축이 아니고, 같은 시기에 다른 세션이 그 파일을
 * 만지고 있었다(병렬 작업 충돌 회피).
 *
 * 잠그는 것 셋: ①탭이 기존 셋을 밀어내지 않고 넷이 된다 ②`?panel=notes` 로 열면
 * 메모 패널이 활성이다 ③다른 탭이 열려 있으면 메모 조회가 나가지 않는다(레일의
 * "마운트는 유지하되 활성 탭만 조회한다" 계약).
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { DraftEditor } from "../drafts/DraftEditor";

afterEach(() => {
  vi.unstubAllGlobals();
});

const PROJECT = { id: "p1", name: "겨울 이야기", archived: false };
const DRAFT = { id: "d1", project_id: "p1", title: "첫 장면", archived: false };
const NOTE_LIST = {
  notes: [{
    draft_id: "d1", scene_title: "첫 장면", scene_archived: false,
    chapter_id: "c1", chapter_title: "1장", chapter_archived: false,
    body_preview: "난로 앞", truncated: false, updated_at: "2026-09-01T02:00:00Z",
  }],
};

function reply(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, statusText: "", json: async () => body });
}

/** 편집기는 마운트에서 여러 표면을 읽는다 — 이 테스트가 보는 것은 메모 축뿐이다. */
function stubEditor() {
  const fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/notes")) return reply(NOTE_LIST);
    if (url.endsWith("/drafts/d1/note")) {
      return reply({ draft_id: "d1", body: "이 장면 메모", updated_at: null });
    }
    if (url.includes("/writing/scratch")) return reply({ project_id: "p1", draft_id: "d1", items: [] });
    if (url.includes("/writing/budget")) {
      return reply({
        project_id: "p1",
        context_budget_tokens: { short: 8192, medium: 8192, long: 8192 },
      });
    }
    if (url.endsWith("/versions")) return reply({ versions: [] });
    if (url.endsWith("/drafts/d1")) return reply(DRAFT);
    if (url.endsWith("/projects/p1")) return reply(PROJECT);
    if (url.includes("/review")) return reply({ items: [], gate_findings: [] });
    return reply({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderEditor(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId/drafts/:draftId" element={<DraftEditor />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("adds the memo tab without displacing the three that were there", async () => {
  stubEditor();

  renderEditor("/projects/p1/drafts/d1?panel=notes");

  await screen.findByLabelText("원고 본문");
  // 드로어가 열려 있으면 독은 a11y 트리에서 숨는다(중복 탭 목록 방지) — 열린
  // 쪽 탭 띠가 넷을 보여야 한다.
  const tabs = screen.getByRole("tablist", { name: "열린 집필 도구 전환" });
  expect(
    within(tabs).getAllByRole("tab").map((tab) => tab.textContent),
  ).toEqual(["이어쓰기", "분석", "검토", "메모"]);
});

it("offers the memo tab from the closed dock too", async () => {
  stubEditor();

  renderEditor("/projects/p1/drafts/d1");

  await screen.findByLabelText("원고 본문");
  const dock = screen.getByRole("tablist", { name: "집필 도구 선택" });
  expect(
    within(dock).getAllByRole("tab").map((tab) => tab.textContent),
  ).toEqual(["이어쓰기", "분석", "검토", "메모"]);
});

it("opens the memo panel from the address and loads this scene's note", async () => {
  stubEditor();

  renderEditor("/projects/p1/drafts/d1?panel=notes");

  // 값으로 기다린다 — textarea 는 조회가 끝나기 전에 이미 그려져 있어서
  // `findByLabelText` 는 빈 상자에서도 곧바로 통과한다.
  expect(await screen.findByDisplayValue("이 장면 메모")).toHaveAttribute(
    "id", "scene-note-body",
  );
});

it("does not fetch notes while another tab is the open one", async () => {
  const fetchMock = stubEditor();

  renderEditor("/projects/p1/drafts/d1?panel=writing");

  await screen.findByLabelText("원고 본문");
  expect(
    fetchMock.mock.calls.map((call) => call[0]).filter((url) => String(url).includes("note")),
  ).toEqual([]);
});
