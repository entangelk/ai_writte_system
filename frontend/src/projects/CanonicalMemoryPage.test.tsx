import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CanonicalMemoryPage } from "./CanonicalMemoryPage";

/** 테스트용 정본 기억 행 — CanonicalMemory 인터페이스 전 필드. */
function memoryEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: "m1",
    memory_type: "character_observation",
    status: "canonical",
    payload: { name: "아리엘", observation: "폭풍 속에서도 침착하다" },
    version: 1,
    provenance: "source_observed",
    confidence: 0.5,
    source_ref_ids: ["sr-1", "sr-2"],
    analysis_job_id: "job-1",
    source_candidate_id: "cand-1",
    promotion_mode: "manual",
    applied_threshold: null,
    scope: { scope_type: "character", scope_id: "아리엘" },
    supersedes: null,
    ...overrides,
  };
}

function renderPage(archived = false) {
  return render(
    <MemoryRouter initialEntries={["/projects/p1/settings"]}>
      <Routes>
        <Route
          path="/projects/:projectId/settings"
          element={
            <CanonicalMemoryPage projectId="p1" archived={archived} />
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * 작품 기억 탭 (2026-10-06) — 오너 지적 *"어떤 게 승인됐는지 목록을 볼 수 있는
 * 곳이 없어서 수정도 못한다"* 에 대한 답.
 *
 * under-strict: 본문(관찰)·버전·이력 표시나 편집 배선을 빼면 재실패한다.
 * over-strict: 보관 프로젝트에 수정 버튼을 내놓는 과잉도 실패한다(서버는 409).
 */
describe("CanonicalMemoryPage", () => {
  it("lists what was approved — type, version, provenance and the body itself", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ memory: [memoryEntry()] }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("아리엘")).toBeInTheDocument();
    // 제목만이 아니라 관찰 본문이 같이 와야 "무엇이 승인됐는지"가 보인다.
    expect(
      screen.getByText("폭풍 속에서도 침착하다"),
    ).toBeInTheDocument();
    expect(screen.getByText("인물 · v1 · 원문 관찰")).toBeInTheDocument();
  });

  it("expands the detail with payload fields, evidence count and the version chain", async () => {
    const v1 = memoryEntry({
      id: "m1",
      status: "superseded",
      payload: { name: "아리엘", observation: "낡은 관찰" },
      supersedes: null,
    });
    const v2 = memoryEntry({
      id: "m2",
      version: 2,
      provenance: "human_edited",
      payload: { name: "아리엘", observation: "고쳐진 관찰" },
      source_candidate_id: "manual:edit-1",
      supersedes: "m1",
    });
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({ memory: [v1, v2] }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await screen.findByText("고쳐진 관찰");
    expect(screen.queryByText("낡은 관찰")).toBeNull(); // 접힌 상태에선 이력이 보이지 않는다

    await userEvent.click(screen.getByRole("button", { name: "상세·이력" }));

    expect(screen.getByText("이름")).toBeInTheDocument();
    expect(screen.getByText("근거")).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();
    // append-only 사슬 — 옛 버전이 그대로 이력에 남는다.
    expect(screen.getByText("v1 · 보존됨")).toBeInTheDocument();
    expect(screen.getByText("v2 · 현재 정본")).toBeInTheDocument();
    expect(screen.getByText("낡은 관찰")).toBeInTheDocument();
  });

  it("edits an approved memory and sends base_version with the exact payload keys", async () => {
    let listCalls = 0;
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return {
          ok: true,
          status: 200,
          statusText: "",
          json: async () => ({
            memory: memoryEntry({
              version: 2,
              provenance: "human_edited",
              payload: {
                name: "아리엘",
                observation: "조용히 관찰한다",
              },
              source_candidate_id: "manual:k1",
            }),
            idempotent_replay: false,
          }),
        };
      }
      listCalls += 1;
      // 첫 목록은 편집 전 v1, 저장 뒤 재로드는 v2 — 저장이 목록을 다시 읽는지까지 잰다.
      const observation =
        listCalls === 1 ? "폭풍 속에서도 침착하다" : "조용히 관찰한다";
      return {
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({
          memory: [
            listCalls === 1
              ? memoryEntry()
              : memoryEntry({
                  version: 2,
                  provenance: "human_edited",
                  payload: { name: "아리엘", observation },
                }),
          ],
        }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await screen.findByText("폭풍 속에서도 침착하다");

    await userEvent.click(screen.getByRole("button", { name: "수정" }));
    const observation = await screen.findByLabelText("관찰");
    await userEvent.clear(observation);
    await userEvent.type(observation, "조용히 관찰한다");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/p1/memory/m1",
        expect.objectContaining({ method: "PUT" }),
      );
    });
    const [, putInit] = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
    ) as [string, RequestInit];
    const body = JSON.parse(putInit.body as string) as Record<string, unknown>;
    // 낙관 버전 축: 편집을 시작한 version 이 그대로 실린다(낡으면 서버가 409).
    expect(body.base_version).toBe(1);
    expect(body.payload).toEqual({
      name: "아리엘",
      observation: "조용히 관찰한다",
    });
    expect(typeof body.idempotency_key).toBe("string");
    // 저장 뒤: 성공 문구 + 목록 재로드(새 version 이 목록에 산다).
    expect(
      await screen.findByText("기억 version 2을 저장했습니다. 이전 버전은 이력에 보존됩니다."),
    ).toBeInTheDocument();
    expect(await screen.findByText("인물 · v2 · 사람 수정")).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it("blocks an empty field from saving", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ memory: [memoryEntry()] }),
      })),
    );

    renderPage();
    await screen.findByText("아리엘");
    await userEvent.click(screen.getByRole("button", { name: "수정" }));

    const observation = await screen.findByLabelText("관찰");
    await userEvent.clear(observation);

    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("surfaces a stale-base 409 as the error alert", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return {
          ok: false,
          status: 409,
          statusText: "",
          json: async () => ({ detail: "canonical memory base is stale" }),
        };
      }
      return {
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ memory: [memoryEntry()] }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await screen.findByText("아리엘");
    await userEvent.click(screen.getByRole("button", { name: "수정" }));
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "canonical memory base is stale",
      );
    });
  });

  it("keeps an archived project read-only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ memory: [memoryEntry()] }),
      })),
    );

    renderPage(true);

    expect(
      await screen.findByText(
        "보관된 프로젝트의 작품 기억은 읽기만 가능합니다.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "수정" })).toBeNull();
  });

  it("shows the empty state pointing at the review inbox", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ memory: [] }),
      })),
    );

    renderPage();

    expect(
      await screen.findByText("승인된 작품 기억이 없습니다."),
    ).toBeInTheDocument();
  });
});
