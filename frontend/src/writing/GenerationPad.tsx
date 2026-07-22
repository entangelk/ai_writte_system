import { type WritingGenerationJob } from "../api/client";

// 증분 3 (D6): the in-progress half of the result pad. Completed results live in
// the scratch list (ScratchRecovery renders them); this shows the async jobs that
// are still running plus any that failed — so a background failure is never
// silent. Read-only: the writer copies from the completed pad, never from here.

const LENGTH_LABEL: Record<string, string> = {
  medium: "중간부터 이어쓰기",
  long: "전체 작성",
};

// Mirrors WritingGenerationJobFailureReason (generation_job.py). Falls back to the
// raw reason so a new backend reason still surfaces rather than showing nothing.
const FAILURE_COPY: Record<string, string> = {
  invalid_request: "요청이 올바르지 않아 생성하지 못했습니다.",
  invalid_report: "생성 결과의 근거 보고서를 해석하지 못했습니다.",
  context_budget_exceeded: "근거 예산을 초과해 생성이 중단됐습니다.",
  context_search_failed: "근거 검색에 실패했습니다.",
  provider_error: "생성 모델 호출에 실패했습니다.",
  provider_timeout: "생성 모델 응답이 시간 내에 오지 않았습니다.",
  internal: "내부 오류로 생성에 실패했습니다.",
};

type GenerationPadProps = {
  activeJobs: WritingGenerationJob[];
  failedJobs: WritingGenerationJob[];
  onDismissFailed: (jobId: string) => void;
  onRetryFailed: (jobId: string) => void;
};

export function GenerationPad(props: GenerationPadProps) {
  const { activeJobs, failedJobs, onDismissFailed, onRetryFailed } = props;
  if (activeJobs.length === 0 && failedJobs.length === 0) return null;

  return (
    <section className="generation-pad" aria-label="백그라운드 생성 상태">
      {activeJobs.length > 0 && (
        <div className="generation-pad-active">
          <p className="generation-pad-lead" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            백그라운드 생성 {activeJobs.length}건 진행 중… 완료되면 아래 결과 목록에 표시됩니다.
          </p>
          <ul className="generation-pad-list">
            {activeJobs.map((job) => (
              <li key={job.job_id}>
                {LENGTH_LABEL[job.output_length] ?? job.output_length} ·{" "}
                {job.status === "pending" ? "대기 중" : "생성 중"}
              </li>
            ))}
          </ul>
        </div>
      )}
      {failedJobs.map((job) => (
        <p key={job.job_id} className="generation-pad-failed" role="alert">
          <span>
            백그라운드 생성 실패:{" "}
            {FAILURE_COPY[job.failure_reason ?? ""] ??
              job.failure_reason ??
              "알 수 없는 오류"}
          </span>
          <span className="generation-pad-failed-actions">
            <button type="button" onClick={() => onRetryFailed(job.job_id)}>
              다시 시도
            </button>
            <button type="button" onClick={() => onDismissFailed(job.job_id)}>
              닫기
            </button>
          </span>
        </p>
      ))}
    </section>
  );
}
