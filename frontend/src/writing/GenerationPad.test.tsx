import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GenerationPad } from "./GenerationPad";
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
    status: "running",
    created_at: "2026-07-22T00:00:00Z",
    result_scratch_id: null,
    failure_reason: null,
    failure_detail: null,
    ...overrides,
  };
}

describe("GenerationPad (증분 3 D6)", () => {
  it("renders nothing when there are no active or failed jobs", () => {
    const { container } = render(
      <GenerationPad activeJobs={[]} failedJobs={[]} onDismissFailed={vi.fn()} onRetryFailed={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an in-progress count and per-job status for active jobs", () => {
    render(
      <GenerationPad
        activeJobs={[
          job({ job_id: "a", status: "running", output_length: "medium" }),
          job({ job_id: "b", status: "pending", output_length: "long" }),
        ]}
        failedJobs={[]}
        onDismissFailed={vi.fn()}
        onRetryFailed={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/백그라운드 생성 2건 진행 중/),
    ).toBeInTheDocument();
    expect(screen.getByText(/중간부터 이어쓰기 · 생성 중/)).toBeInTheDocument();
    expect(screen.getByText(/전체 작성 · 대기 중/)).toBeInTheDocument();
  });

  it("surfaces a failed job with human copy so failure is never silent", () => {
    render(
      <GenerationPad
        activeJobs={[]}
        failedJobs={[job({ status: "failed", failure_reason: "provider_timeout" })]}
        onDismissFailed={vi.fn()}
        onRetryFailed={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/생성 모델 응답이 시간 내에 오지 않았습니다/),
    ).toBeInTheDocument();
  });

  it("falls back to the raw reason for an unknown failure reason", () => {
    render(
      <GenerationPad
        activeJobs={[]}
        failedJobs={[job({ status: "failed", failure_reason: "brand_new_reason" })]}
        onDismissFailed={vi.fn()}
        onRetryFailed={vi.fn()}
      />,
    );
    expect(screen.getByText(/brand_new_reason/)).toBeInTheDocument();
  });

  it("dismisses a failed job by id", async () => {
    const onDismissFailed = vi.fn();
    render(
      <GenerationPad
        activeJobs={[]}
        failedJobs={[job({ job_id: "gone", status: "failed", failure_reason: "internal" })]}
        onDismissFailed={onDismissFailed}
        onRetryFailed={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onDismissFailed).toHaveBeenCalledWith("gone");
  });

  it("retries a failed job by id (재시도 슬라이스)", async () => {
    const onRetryFailed = vi.fn();
    render(
      <GenerationPad
        activeJobs={[]}
        failedJobs={[job({ job_id: "again", status: "failed", failure_reason: "internal" })]}
        onDismissFailed={vi.fn()}
        onRetryFailed={onRetryFailed}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetryFailed).toHaveBeenCalledWith("again");
  });
});
