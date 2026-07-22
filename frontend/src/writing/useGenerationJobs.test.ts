import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  GENERATION_POLL_INTERVAL_MS,
  useGenerationJobs,
} from "./useGenerationJobs";
import type { WritingGenerationJob } from "../api/client";

function job(overrides: Partial<WritingGenerationJob> = {}): WritingGenerationJob {
  return {
    job_id: "wgj-1",
    request_id: "uuid-1",
    project_id: "p1",
    draft_id: "d1",
    version_id: "v1",
    task_type: "continue_scene",
    output_length: "medium",
    status: "pending",
    created_at: "2026-07-22T00:00:00Z",
    result_scratch_id: null,
    failure_reason: null,
    failure_detail: null,
    ...overrides,
  };
}

function httpResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  };
}

// Maps a polled job_id to the payload the server currently reports for it. The
// test mutates `state` to advance a job from pending → succeeded/failed between
// ticks; a jobId not in `state` is served as a rejected fetch (transient error).
function stubJobFetch(state: Map<string, { status?: number; body: unknown }>) {
  const fetchMock = vi.fn((url: string) => {
    const match = /generation-jobs\/([^/?]+)/.exec(url);
    if (match === null) return Promise.reject(new Error(`unexpected ${url}`));
    const entry = state.get(decodeURIComponent(match[1]));
    if (entry === undefined) return Promise.reject(new Error("network"));
    return Promise.resolve(httpResponse(entry.status ?? 200, entry.body));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(GENERATION_POLL_INTERVAL_MS);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useGenerationJobs — 5s polling while active (증분 3 D6)", () => {
  it("does not poll when no job is tracked (over-strict: idle draft never fetches)", async () => {
    const fetchMock = stubJobFetch(new Map());
    renderHook(() => useGenerationJobs("p1", "d1", {}));
    await tick();
    await tick();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls a tracked job every interval and surfaces it as active", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "running" }) }],
    ]);
    const fetchMock = stubJobFetch(state);
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));

    act(() => result.current.track(job({ status: "pending" })));
    expect(result.current.activeJobs).toHaveLength(1);
    expect(fetchMock).not.toHaveBeenCalled(); // no immediate poll; first tick at 5s

    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.activeJobs[0].status).toBe("running");
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(2); // still active → keeps polling
  });

  it("reports a succeeded job, drops it from active, and stops polling it", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "succeeded", result_scratch_id: "sc-1" }) }],
    ]);
    const fetchMock = stubJobFetch(state);
    const onSettled = vi.fn();
    const { result } = renderHook(() =>
      useGenerationJobs("p1", "d1", { onSettled }),
    );

    act(() => result.current.track(job()));
    await tick();

    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled.mock.calls[0][0].status).toBe("succeeded");
    expect(result.current.activeJobs).toHaveLength(0);
    expect(result.current.failedJobs).toHaveLength(0);
    expect(result.current.settledUnseen).toBe(1);

    // Under-strict guard: a settled job must not keep polling forever.
    const callsAfterSettle = fetchMock.mock.calls.length;
    await tick();
    await tick();
    expect(fetchMock.mock.calls.length).toBe(callsAfterSettle);
  });

  it("reports a failed job (never silent), keeping it in the pad", async () => {
    const state = new Map<string, { body: unknown }>([
      [
        "wgj-1",
        { body: job({ status: "failed", failure_reason: "provider_timeout" }) },
      ],
    ]);
    stubJobFetch(state);
    const onSettled = vi.fn();
    const { result } = renderHook(() =>
      useGenerationJobs("p1", "d1", { onSettled }),
    );

    act(() => result.current.track(job()));
    await tick();

    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(result.current.activeJobs).toHaveLength(0);
    expect(result.current.failedJobs).toHaveLength(1);
    expect(result.current.failedJobs[0].failure_reason).toBe("provider_timeout");
    expect(result.current.settledUnseen).toBe(1);
  });

  it("leaves a job active and retries when a poll fetch fails transiently", async () => {
    const state = new Map<string, { body: unknown }>(); // no entry → fetch rejects
    const fetchMock = stubJobFetch(state);
    const onSettled = vi.fn();
    const { result } = renderHook(() =>
      useGenerationJobs("p1", "d1", { onSettled }),
    );

    act(() => result.current.track(job({ status: "running" })));
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.activeJobs).toHaveLength(1); // still active
    expect(onSettled).not.toHaveBeenCalled();

    // Recovery: the next tick sees a terminal state and settles.
    state.set("wgj-1", { body: job({ status: "succeeded" }) });
    await tick();
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(result.current.activeJobs).toHaveLength(0);
  });

  it("acknowledge clears the unseen count", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "succeeded" }) }],
    ]);
    stubJobFetch(state);
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    act(() => result.current.track(job()));
    await tick();
    expect(result.current.settledUnseen).toBe(1);
    act(() => result.current.acknowledge());
    expect(result.current.settledUnseen).toBe(0);
  });

  it("dismissFailed removes a failed job from the pad", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "failed", failure_reason: "internal" }) }],
    ]);
    stubJobFetch(state);
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    act(() => result.current.track(job()));
    await tick();
    expect(result.current.failedJobs).toHaveLength(1);
    act(() => result.current.dismissFailed("wgj-1"));
    expect(result.current.failedJobs).toHaveLength(0);
  });

  it("resets tracked jobs when the draft changes", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "running" }) }],
    ]);
    const fetchMock = stubJobFetch(state);
    const { result, rerender } = renderHook(
      ({ draftId }: { draftId: string }) =>
        useGenerationJobs("p1", draftId, {}),
      { initialProps: { draftId: "d1" } },
    );
    act(() => result.current.track(job()));
    expect(result.current.activeJobs).toHaveLength(1);

    rerender({ draftId: "d2" });
    expect(result.current.activeJobs).toHaveLength(0);
    // The abandoned d1 job must not keep polling under the new draft.
    const callsBefore = fetchMock.mock.calls.length;
    await tick();
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  // H-1 (verification 2026-07-22): pin the exact 5s cadence the owner fixed
  // (decisions brief D6, "10초도 괜찮다"를 5초로 확정). Uses literal 5000, not the
  // exported constant, so bumping GENERATION_POLL_INTERVAL_MS re-fails this test.
  it("polls on the owner-fixed 5-second cadence — not before, exactly at 5000ms (H-1)", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ status: "running" }) }],
    ]);
    const fetchMock = stubJobFetch(state);
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    act(() => result.current.track(job({ status: "pending" })));

    // under-strict (guards a shorter interval): nothing polls before 5s.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4999);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    // over-strict (guards a longer interval): the first poll lands at exactly 5000ms.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // H-2 (verification 2026-07-22): pin the `if (!hasActive) return` guard itself,
  // not just its observable "no fetch while idle" effect — removing the guard would
  // arm a permanent setInterval even with zero jobs. Spying on setInterval pins it.
  it("arms an interval only when a job is active, never while idle (H-2)", () => {
    stubJobFetch(new Map());
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    expect(setIntervalSpy).not.toHaveBeenCalled(); // idle → no interval armed
    act(() => result.current.track(job({ status: "running" })));
    expect(setIntervalSpy).toHaveBeenCalledTimes(1); // active → interval armed
  });

  // H-3 (verification 2026-07-22): the poll fans out over ALL active jobs in one
  // tick (Promise.all) and settles them independently — previously only a single
  // job was driven through. Locks succeeded-drop + failed-keep in the same tick.
  it("retry resets a failed job and resumes polling to completion (재시도 슬라이스)", async () => {
    // A job fails on the first poll; retry resets it server-side to pending, so it
    // becomes active again and the next poll drives it to succeeded.
    let phase = "failing";
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/retry")) {
        return Promise.resolve(
          httpResponse(200, job({ status: "pending", failure_reason: null })),
        );
      }
      return Promise.resolve(
        httpResponse(
          200,
          phase === "failing"
            ? job({ status: "failed", failure_reason: "provider_error" })
            : job({ status: "succeeded" }),
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSettled = vi.fn();
    const { result } = renderHook(() =>
      useGenerationJobs("p1", "d1", { onSettled }),
    );

    act(() => result.current.track(job({ status: "pending" })));
    await tick();
    expect(result.current.failedJobs).toHaveLength(1);
    expect(result.current.activeJobs).toHaveLength(0);

    phase = "succeeding";
    await act(async () => {
      await result.current.retry("wgj-1");
    });
    expect(result.current.activeJobs).toHaveLength(1); // pending again → active
    expect(result.current.failedJobs).toHaveLength(0);

    await tick(); // polling resumed → succeeded
    expect(result.current.activeJobs).toHaveLength(0);
    expect(onSettled).toHaveBeenCalledTimes(2); // failed once, then succeeded
  });

  it("retry leaves the job failed when the retry request fails (재시도 슬라이스)", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/retry")) return Promise.reject(new Error("boom"));
      return Promise.resolve(
        httpResponse(200, job({ status: "failed", failure_reason: "internal" })),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    act(() => result.current.track(job({ status: "pending" })));
    await tick();
    expect(result.current.failedJobs).toHaveLength(1);

    await act(async () => {
      await result.current.retry("wgj-1");
    });
    // Retry POST failed → the job stays failed (the user can try again).
    expect(result.current.failedJobs).toHaveLength(1);
    expect(result.current.activeJobs).toHaveLength(0);
  });

  it("retry is a no-op for a job that is not failed (guard)", async () => {
    const fetchMock = stubJobFetch(
      new Map([["wgj-1", { body: job({ status: "running" }) }]]),
    );
    const { result } = renderHook(() => useGenerationJobs("p1", "d1", {}));
    act(() => result.current.track(job({ status: "running" })));

    await act(async () => {
      await result.current.retry("wgj-1");
    });
    // No /retry request is issued for an active job — only FAILED jobs retry.
    expect(
      fetchMock.mock.calls.some(
        (call) => typeof call[0] === "string" && call[0].includes("/retry"),
      ),
    ).toBe(false);
  });

  it("polls every active job in one tick and settles them independently (H-3)", async () => {
    const state = new Map<string, { body: unknown }>([
      ["wgj-1", { body: job({ job_id: "wgj-1", status: "succeeded" }) }],
      [
        "wgj-2",
        {
          body: job({
            job_id: "wgj-2",
            status: "failed",
            failure_reason: "provider_error",
          }),
        },
      ],
    ]);
    const fetchMock = stubJobFetch(state);
    const onSettled = vi.fn();
    const { result } = renderHook(() =>
      useGenerationJobs("p1", "d1", { onSettled }),
    );
    act(() => result.current.track(job({ job_id: "wgj-1", status: "running" })));
    act(() => result.current.track(job({ job_id: "wgj-2", status: "running" })));
    expect(result.current.activeJobs).toHaveLength(2);

    await tick();

    expect(fetchMock).toHaveBeenCalledTimes(2); // both polled in the one tick
    expect(onSettled).toHaveBeenCalledTimes(2); // both settled
    expect(result.current.activeJobs).toHaveLength(0);
    expect(result.current.failedJobs.map((entry) => entry.job_id)).toEqual([
      "wgj-2",
    ]); // succeeded dropped, failed kept
    expect(result.current.settledUnseen).toBe(2);
  });
});
