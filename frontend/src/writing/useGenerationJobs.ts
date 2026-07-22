import { useCallback, useEffect, useRef, useState } from "react";
import { getGenerationJob, type WritingGenerationJob } from "../api/client";

// 증분 3 (D6): async medium/long generations run in the background worker. This
// hook tracks the jobs a session started, polls each every 5s WHILE it is still
// running (D6=A: "생성 중일 때만 폴링"), and reports settled jobs so the pad can
// refresh and the tab can show a completion badge. Only in-memory tracking — a
// full page refresh drops the live indicators, but the worker still persists a
// succeeded result to scratch, so it resurfaces there.
export const GENERATION_POLL_INTERVAL_MS = 5000;
const ACTIVE_STATUSES = new Set(["pending", "running"]);

function isActive(job: WritingGenerationJob): boolean {
  return ACTIVE_STATUSES.has(job.status);
}

type Options = {
  // Fired once when a tracked job reaches a terminal state (succeeded OR failed).
  // The editor uses this to re-fetch the scratch list (a succeeded result was
  // appended there by the worker).
  onSettled?: (job: WritingGenerationJob) => void;
};

export type GenerationJobsHandle = {
  // Jobs still pending/running (rendered as "생성 중" in the pad).
  activeJobs: WritingGenerationJob[];
  // Jobs that ended in failure (surfaced so a failure is never silent, D6=A).
  failedJobs: WritingGenerationJob[];
  // Register a freshly enqueued async job to begin polling it.
  track: (job: WritingGenerationJob) => void;
  // Count of jobs that settled but have not been acknowledged (the tab badge).
  settledUnseen: number;
  // Clear the unseen count (the editor calls this when the writing tab is shown).
  acknowledge: () => void;
  // Drop a failed job from the pad (session-local; there is no retry yet).
  dismissFailed: (jobId: string) => void;
};

export function useGenerationJobs(
  projectId: string,
  draftId: string,
  { onSettled }: Options = {},
): GenerationJobsHandle {
  const [jobs, setJobs] = useState<WritingGenerationJob[]>([]);
  const [settledUnseen, setSettledUnseen] = useState(0);

  // The poll effect keys off `hasActive` only, so keep the live job list and the
  // latest onSettled in refs to avoid stale closures / needless effect restarts.
  const jobsRef = useRef<WritingGenerationJob[]>(jobs);
  jobsRef.current = jobs;
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const track = useCallback((job: WritingGenerationJob) => {
    setJobs((current) =>
      current.some((existing) => existing.job_id === job.job_id)
        ? current
        : [job, ...current],
    );
  }, []);

  const acknowledge = useCallback(() => setSettledUnseen(0), []);

  const dismissFailed = useCallback((jobId: string) => {
    setJobs((current) => current.filter((job) => job.job_id !== jobId));
  }, []);

  // Switching drafts abandons the previous draft's tracked jobs (jobs are keyed
  // per (project, draft); the previous draft's badge must not bleed over).
  useEffect(() => {
    setJobs([]);
    setSettledUnseen(0);
  }, [projectId, draftId]);

  const activeJobs = jobs.filter(isActive);
  const failedJobs = jobs.filter((job) => job.status === "failed");
  const hasActive = activeJobs.length > 0;

  useEffect(() => {
    if (!hasActive) return;
    let cancelled = false;

    async function poll() {
      const stillActive = jobsRef.current.filter(isActive);
      await Promise.all(
        stillActive.map(async (job) => {
          let next: WritingGenerationJob;
          try {
            next = await getGenerationJob(projectId, job.job_id);
          } catch {
            // Transient poll failure: leave the job active and retry next tick.
            return;
          }
          if (cancelled) return;
          if (isActive(next)) {
            // Reflect pending → running, but keep the same array reference when
            // nothing changed so the pad does not re-render on every poll.
            setJobs((current) => {
              const index = current.findIndex(
                (entry) => entry.job_id === next.job_id,
              );
              if (index === -1 || current[index].status === next.status) {
                return current;
              }
              const updated = [...current];
              updated[index] = next;
              return updated;
            });
            return;
          }
          setSettledUnseen((count) => count + 1);
          onSettledRef.current?.(next);
          setJobs((current) =>
            next.status === "succeeded"
              ? current.filter((entry) => entry.job_id !== next.job_id)
              : current.map((entry) =>
                  entry.job_id === next.job_id ? next : entry,
                ),
          );
        }),
      );
    }

    const timer = setInterval(() => void poll(), GENERATION_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [hasActive, projectId]);

  return {
    activeJobs,
    failedJobs,
    track,
    settledUnseen,
    acknowledge,
    dismissFailed,
  };
}
