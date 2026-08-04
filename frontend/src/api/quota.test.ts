import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  acceptWriting,
  analyzeVersion,
  describeQuotaError,
  gateWriting,
  generateWriting,
  getMyQuota,
  reviseAndGateWriting,
  type BillableRequestOptions,
  type MyQuota,
} from "./client";

/**
 * Slice 8.4 — quota 계약의 프론트 쪽 (오너 결정 2026-08-04, W2·W4·W7).
 *
 * **W7=B(행동 가드)를 여기서 실행한다.** 유료 client 함수 전수가
 * ① 확인 인자를 받으면 헤더를 싣고 ② 안 받으면 **싣지 않으며** ③ 429를 확인 가능한
 * 사건으로 분류하는지를 fetch mock 으로 잰다. 소스 파싱 가드(선택지 C)를 고르지
 * 않은 이유는 브리프에 있다 — `main.py` 를 정규식으로 읽는 기존 가드 두 개가 지금
 * 라우터 분리를 비싸게 만들고 있고, 같은 부채를 프론트에 복제하지 않는다.
 */

function respond(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function mockFetch(response: Response | ((url: string) => Response)) {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      typeof response === "function" ? response(url) : response.clone(),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * **유료 호출의 헤더**를 본다 — 첫 호출이 아니다. `analyzeVersion` 은 무료 준비
 * 호출(카탈로그·job 생성)을 먼저 하므로, 첫 호출만 보는 가드는 그 경로를 영영
 * 검사하지 못한다(첫 판이 실제로 그렇게 틀렸다).
 */
function billableHeadersOf(
  fetchMock: ReturnType<typeof vi.fn>,
  path: string,
): Headers {
  const call = fetchMock.mock.calls.find(
    ([url]) => typeof url === "string" && url.includes(path),
  );
  if (call === undefined) {
    throw new Error(`유료 경로 ${path} 로 나간 요청이 없다`);
  }
  return new Headers((call[1] as RequestInit).headers as HeadersInit);
}

/** 분석은 무료 준비 호출을 거쳐 `/run` 에 닿는다 — 그 경로를 실제로 흉내 낸다. */
function analysisFetch(url: string): Response {
  if (url.includes("/source-refs")) {
    return respond({ source_refs: [{ start_offset: 0, end_offset: 10 }] });
  }
  if (url.includes("/versions/")) {
    return respond({ blocks: [{ start_offset: 0, end_offset: 10 }] });
  }
  if (url.endsWith("/analysis/jobs")) {
    return respond({ job: { id: "job-1", status: "pending" } });
  }
  return respond({
    job: { id: "job-1", status: "succeeded" }, candidates: [],
  });
}

/** 화면에서 부르는 유료 동작 전수 (8.0 분류 9개 중 프론트 호출부가 있는 5개). */
const BILLABLE_CALLS: {
  action: string;
  path: string;
  fetch?: (url: string) => Response;
  call: (options?: BillableRequestOptions) => Promise<unknown>;
}[] = [
  {
    action: "writing_generate",
    path: "/writing/generate",
    call: (options) =>
      generateWriting("p1", { request_id: "r1" } as never, options),
  },
  {
    action: "writing_gate",
    path: "/writing/gate",
    call: (options) => gateWriting("p1", { request_id: "r1" } as never, options),
  },
  {
    action: "writing_revise_and_gate",
    path: "/writing/revise-and-gate",
    call: (options) =>
      reviseAndGateWriting("p1", { request_id: "r1" } as never, options),
  },
  {
    action: "writing_accept",
    path: "/writing/accept",
    call: (options) =>
      acceptWriting("p1", { request_id: "r1" } as never, options),
  },
  {
    action: "analysis_extract",
    path: "/analysis/jobs/job-1/run",
    fetch: analysisFetch,
    call: (options) => analyzeVersion("p1", "d1", "v1", "s1", options),
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("유료 요청의 확인 헤더 (W4=A · W7=B)", () => {
  it.each(BILLABLE_CALLS)(
    "$action: 확인을 주면 X-Confirm-Duplicate 를 싣는다",
    async ({ call, path, fetch: responder }) => {
      const fetchMock = mockFetch(responder ?? respond({ ok: true }));
      await call({ confirmDuplicate: true }).catch(() => undefined);
      expect(billableHeadersOf(fetchMock, path).get("X-Confirm-Duplicate"))
        .toBe("1");
    },
  );

  it.each(BILLABLE_CALLS)(
    "$action: 확인이 없으면 헤더를 싣지 않는다",
    async ({ call, path, fetch: responder }) => {
      // over-strict 짝이자 이 슬라이스에서 가장 중요한 셀이다 — 헤더를 항상
      // 붙이면 서버의 중복 방어가 통째로 무력화된다(8.2b G4=A 가 "확인은 통과"로
      // 설계돼 있으므로, 상시 확인은 곧 상시 통과다).
      const fetchMock = mockFetch(responder ?? respond({ ok: true }));
      await call().catch(() => undefined);
      expect(billableHeadersOf(fetchMock, path).has("X-Confirm-Duplicate"))
        .toBe(false);
    },
  );

  it("429 를 받아도 클라이언트가 스스로 다시 보내지 않는다", async () => {
    // W4=A 의 핵심. 래퍼가 자동 재시도하면 사용자가 모르는 사이 사용량이 늘고,
    // 확인 대화는 장식이 된다. 요청 수가 정확히 1이어야 한다.
    const fetchMock = mockFetch(
      respond({ detail: "duplicate" }, { status: 429 }),
    );
    await expect(
      generateWriting("p1", { request_id: "r1" } as never),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("Retry-After 가 화면까지 온다 (W2=A)", () => {
  it("숫자 헤더를 초로 싣는다", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: "duplicate" }), {
        status: 429,
        headers: { "Content-Type": "application/json", "Retry-After": "4" },
      }),
    );
    const error = await generateWriting(
      "p1", { request_id: "r1" } as never,
    ).catch((err: unknown) => err as ApiError);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).retryAfterSeconds).toBe(4);
  });

  it("헤더가 없으면 추측하지 않고 null 이다", async () => {
    mockFetch(respond({ detail: "gone" }, { status: 402 }));
    const error = await generateWriting(
      "p1", { request_id: "r1" } as never,
    ).catch((err: unknown) => err as ApiError);
    expect((error as ApiError).retryAfterSeconds).toBeNull();
  });
});

describe("describeQuotaError 는 status 로만 가른다 (W2=A · H3)", () => {
  it("429 는 확인 가능한 중복이다", () => {
    const refusal = describeQuotaError(new ApiError(429, "무슨 문장이든", 3));
    expect(refusal?.kind).toBe("locked");
    expect(refusal?.confirmable).toBe(true);
    expect(refusal?.retryAfterSeconds).toBe(3);
  });

  it("402 는 확인으로 뚫리지 않는다", () => {
    const refusal = describeQuotaError(new ApiError(402, "daily quota"));
    expect(refusal?.kind).toBe("exhausted");
    expect(refusal?.confirmable).toBe(false);
  });

  it("detail 문자열을 바꿔도 분류가 그대로다", () => {
    // H3 계약: 상태코드=기계용, detail=사람용. 서버가 문구를 다듬는 것만으로
    // 화면 동작이 달라지면 그것이 계약 위반이다.
    //
    // ★ **동등성만 단정하면 안 된다**(첫 판의 결함, 뮤테이션이 드러냈다): detail 로
    // 분기하는 구현에서 두 문자열이 **둘 다** 안 걸리면 결과가 나란히 `null` 이라
    // "같다"가 성립해 버린다. 그래서 값 자체를 단정한다.
    for (const detail of [
      "the same request is already in progress",
      "전혀 다른 문장",
      "",
    ]) {
      expect(describeQuotaError(new ApiError(429, detail))?.kind).toBe("locked");
    }
  });

  it("정지(403)는 quota 스냅샷이 정지라고 말할 때만 정지다", () => {
    // 403 은 소유권 거절과 코드가 겹친다(Q5=B 가 알고 받은 대가). 스냅샷 없이
    // 정지로 단정하면 남의 프로젝트를 열었을 때 "계정이 정지됐다"고 말한다.
    const suspended = { status: "suspended" } as MyQuota;
    expect(describeQuotaError(new ApiError(403, "x"), suspended)?.kind).toBe(
      "suspended",
    );
    expect(describeQuotaError(new ApiError(403, "x"), null)).toBeNull();
    expect(
      describeQuotaError(new ApiError(403, "x"), { status: "active" } as MyQuota),
    ).toBeNull();
  });

  it("quota 사건이 아니면 null 이라 기존 서술로 넘어간다", () => {
    expect(describeQuotaError(new ApiError(502, "provider"))).toBeNull();
    expect(describeQuotaError(new Error("network"))).toBeNull();
  });
});

describe("GET /me/quota (W5=B)", () => {
  it("서버가 계산한 통합 잔여를 그대로 읽는다", async () => {
    // 화면이 min(일, 주)를 다시 계산하지 않는다는 것 자체가 계약이다 —
    // 두 번째 계산 자리가 생기면 "3회 남음" 직후 402 가 난다.
    const fetchMock = mockFetch(
      respond({
        remaining: 3, unlimited: false, status: "active",
        daily: { limit: 20, used: 17, remaining: 3,
                 resets_at: "2026-08-04T15:00:00Z" },
        weekly: { limit: 100, used: 40, remaining: 60,
                  resets_at: "2026-08-08T15:00:00Z" },
      }),
    );
    const quota = await getMyQuota();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/me/quota");
    expect(quota.remaining).toBe(3);
  });
});
