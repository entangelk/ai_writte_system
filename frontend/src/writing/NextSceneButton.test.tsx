import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NextSceneButton } from "./NextSceneButton";

const seed = { requestId: "wr1", title: "다음 장면", text: "생성문" };

describe("NextSceneButton", () => {
  it("prevents duplicate creation while pending and after completion, allowing retry after failure", async () => {
    // Under-strict: rapid clicks must not create duplicates. Over-strict:
    // a failed request must remain retryable with its error next to the button.
    let reject!: (reason: Error) => void;
    const onCreate = vi.fn().mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }))
      .mockResolvedValueOnce(true);
    render(<NextSceneButton seed={seed} onCreate={onCreate} disabled={false} />);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("button"));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button")).toBeDisabled();
    reject(new Error("장면 생성 실패"));
    expect(await screen.findByRole("alert")).toHaveTextContent("장면 생성 실패");
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("새 장면을 열었습니다"));
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(onCreate).toHaveBeenCalledTimes(2);
  });

  it("disables scene creation for a read-only source", () => {
    const onCreate = vi.fn();
    render(<NextSceneButton seed={seed} onCreate={onCreate} disabled />);
    fireEvent.click(screen.getByRole("button"));
    expect(onCreate).not.toHaveBeenCalled();
  });
});
