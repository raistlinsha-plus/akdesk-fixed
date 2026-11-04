// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost } from "../api";
import { ProjectReviewDelta, type ProjectReviewDeltaResult } from "./ProjectReviewDelta";

vi.mock("../api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api")>(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

function fixture(projectId = 1, baseline = true): ProjectReviewDeltaResult {
  return {
    project_id: projectId,
    fingerprint: `fingerprint-${projectId}`,
    baseline: baseline ? { reviewed_at: "2026-11-01T12:00:00+08:00", entry_id: 10 } : null,
    counts: { new_entries: 2, updated_entries: 1, removed_entries: 1, new_evidence: 2, updated_evidence: 1, removed_evidence: 0, open_tasks: 1, needs_verification: 2, project_changed: false },
    changes: {
      project_changed: false,
      entries: [{ id: 20, title: `项目${projectId}的新反证`, entry_type: "counter_evidence", status: "open", change: "new" }],
      evidence: [{ id: 21, title: "资金样例快照", evidence_type: "snapshot", change: "updated" }],
      removed_entry_ids: [17], removed_evidence_ids: [],
    },
    evidence_status: [
      { id: 1, title: "FRED 查询引用", evidence_type: "chart", status: "reference_only", reason: "只保存用户查询参数，不比较官方版本。", observation_date: null, created_at: "2026-11-01T10:00:00+08:00" },
      { id: 2, title: "旧资金快照", evidence_type: "snapshot", status: "expired", reason: "超出机械7天观察窗口", observation_date: "2026-10-01", created_at: "2026-10-01T10:00:00+08:00" },
      { id: 3, title: "日期缺失快照", evidence_type: "snapshot", status: "missing_time", reason: "未提供观测日期，不能以保存日当成行情时点", observation_date: null, created_at: "2026-11-04T10:00:00+08:00" },
      { id: 4, title: "近期快照", evidence_type: "snapshot", status: "snapshot", reason: "在机械观察窗口内，仍需核验", observation_date: "2026-11-03", created_at: "2026-11-03T10:00:00+08:00" },
    ],
    open_tasks: [{ id: 8, title: "核对新增反证", due_date: "2026-11-03", overdue: true }],
    truncated: { entries: false, evidence: false, tasks: false, removed_entries: false, removed_evidence: false },
    notice: "只整理本地研究变化，不自动生成结论。",
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.mocked(apiGet).mockResolvedValue(fixture());
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

describe("explicit project review delta", () => {
  it("only reads on load and distinguishes references, missing dates and recent snapshots", async () => {
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByText("项目1的新反证");
    expect(apiGet).toHaveBeenCalledExactlyOnceWith("/research/projects/1/review-delta", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(apiPost).not.toHaveBeenCalled();
    expect(screen.getByText("查询引用 · 非历史数据快照")).toBeTruthy();
    expect(screen.getByText("观测日期缺失 · 待核验")).toBeTruthy();
    expect(screen.getByText("近期本地快照 · 仍需核验")).toBeTruthy();
    expect(screen.getByText("超出快照观察窗口 · 待核验")).toBeTruthy();
    expect(screen.getByText("核对新增反证")).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("treats no baseline as first review instead of claiming every record was newly added", async () => {
    vi.mocked(apiGet).mockResolvedValue(fixture(1, false));
    render(<ProjectReviewDelta projectId={1} projectTitle="首次项目" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByText(/首次复盘：尚无明确基线/);
    expect(screen.getByText("当前记录")).toBeTruthy();
    expect(screen.getByText("当前证据")).toBeTruthy();
    expect(screen.queryByText("新增记录")).toBeNull();
    expect(screen.getByText("首次纳入 · 反证")).toBeTruthy();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("requires preparation and an unchecked acknowledgement before storing the viewed fingerprint", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    const updated = fixture();
    updated.fingerprint = "after-checkpoint";
    vi.mocked(apiPost).mockResolvedValue(updated);
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={onReviewed} />);
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    expect((screen.getByRole("button", { name: "确认记录本次复盘" }) as HTMLButtonElement).disabled).toBe(true);
    await user.type(screen.getByRole("textbox"), "只记录自己的核验过程");
    expect(apiPost).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "确认记录本次复盘" }));
    await screen.findByText(/本次复盘时点已记录/);
    expect(apiPost).toHaveBeenCalledExactlyOnceWith("/research/projects/1/review-checkpoint", { confirmed: true, expected_fingerprint: "fingerprint-1", note: "只记录自己的核验过程" }, expect.objectContaining({ timeoutMs: 15_000 }));
    expect(onReviewed).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("preserves the note after a failed write and allows a deliberate idempotent retry", async () => {
    const user = userEvent.setup();
    vi.mocked(apiPost).mockRejectedValueOnce(new Error("服务连接中断")).mockResolvedValueOnce(fixture());
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    await user.type(screen.getByRole("textbox"), "保留备注");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "确认记录本次复盘" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "服务连接中断");
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("保留备注");
    await user.click(screen.getByRole("button", { name: "确认记录本次复盘" }));
    await screen.findByText(/本次复盘时点已记录/);
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(vi.mocked(apiPost).mock.calls[0]).toEqual(vi.mocked(apiPost).mock.calls[1]);
  });

  it("requires rereading and reconfirming a 409 rather than silently marking unseen changes reviewed", async () => {
    const user = userEvent.setup();
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(409, "项目发生变化"));
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    await user.type(screen.getByRole("textbox"), "核验备注保留");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "确认记录本次复盘" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("项目在预览后发生了变化"));
    expect((screen.getByRole("button", { name: "确认记录本次复盘" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    const next = fixture(); next.fingerprint = "new-version";
    vi.mocked(apiGet).mockResolvedValueOnce(next);
    await user.click(screen.getByRole("button", { name: "重新读取" }));
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("核验备注保留");
    expect((screen.getByRole("button", { name: "确认记录本次复盘" }) as HTMLButtonElement).disabled).toBe(true);
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it("ignores a late GET from the previous project, clears draft confirmation, and rejects a wrong-project response", async () => {
    const first = deferred<ProjectReviewDeltaResult>();
    const second = deferred<ProjectReviewDeltaResult>();
    vi.mocked(apiGet).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { rerender } = render(<ProjectReviewDelta projectId={1} projectTitle="旧项目" revision="r1" onReviewed={vi.fn()} />);
    rerender(<ProjectReviewDelta projectId={2} projectTitle="新项目" revision="r2" onReviewed={vi.fn()} />);
    await act(async () => { second.resolve(fixture(2)); });
    expect(screen.getByText("项目2的新反证")).toBeTruthy();
    await act(async () => { first.resolve(fixture(1)); });
    expect(screen.queryByText("项目1的新反证")).toBeNull();
    expect(screen.getByText("项目2的新反证")).toBeTruthy();
    vi.mocked(apiGet).mockResolvedValueOnce(fixture(99));
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("与当前项目不一致"));
    expect(screen.queryByRole("button", { name: "准备标记本次已复盘" })).toBeNull();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("does not apply a late checkpoint response or callback to a different selected project", async () => {
    const user = userEvent.setup();
    const pending = deferred<ProjectReviewDeltaResult>();
    const onReviewed = vi.fn();
    vi.mocked(apiPost).mockReturnValueOnce(pending.promise);
    const { rerender } = render(<ProjectReviewDelta projectId={1} projectTitle="旧项目" revision="r1" onReviewed={onReviewed} />);
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    await user.type(screen.getByRole("textbox"), "旧项目备注");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "确认记录本次复盘" }));
    expect((screen.getByRole("button", { name: "正在记录…" }) as HTMLButtonElement).disabled).toBe(true);
    vi.mocked(apiGet).mockResolvedValueOnce(fixture(2));
    rerender(<ProjectReviewDelta projectId={2} projectTitle="新项目" revision="r2" onReviewed={onReviewed} />);
    await screen.findByText("项目2的新反证");
    await act(async () => { pending.resolve(fixture(1)); });
    expect(onReviewed).not.toHaveBeenCalled();
    expect(screen.queryByText(/本次复盘时点已记录/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    expect(vi.mocked(apiPost).mock.calls[0][0]).toBe("/research/projects/1/review-checkpoint");
  });

  it("shows bounded-list omissions and permits read retries without automatic writes", async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockRejectedValueOnce(new Error("本地服务断开"));
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByRole("alert");
    const response = fixture(); response.truncated.evidence = true;
    vi.mocked(apiGet).mockResolvedValueOnce(response);
    await user.click(screen.getByRole("button", { name: "重新读取" }));
    await screen.findByText("项目1的新反证");
    expect(screen.getByRole("note").textContent).toContain("计数包含全部资料");
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("times out a stalled read without saving and allows an explicit retry", async () => {
    vi.useFakeTimers();
    vi.mocked(apiGet).mockImplementationOnce((_path, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(screen.getByRole("alert").textContent).toContain("读取超时");
    expect((screen.getByRole("button", { name: "重新读取" }) as HTMLButtonElement).disabled).toBe(false);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("invalidates an open confirmation when the saved project revision changes", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r1" onReviewed={vi.fn()} />);
    await screen.findByText("项目1的新反证");
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    await user.type(screen.getByRole("textbox"), "自己的备注仍需保留");
    await user.click(screen.getByRole("checkbox"));
    const next = fixture(); next.fingerprint = "new-saved-revision";
    vi.mocked(apiGet).mockResolvedValueOnce(next);
    rerender(<ProjectReviewDelta projectId={1} projectTitle="利率问题" revision="r2" onReviewed={vi.fn()} />);
    await screen.findByText("项目1的新反证");
    expect(screen.queryByRole("checkbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "准备标记本次已复盘" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("自己的备注仍需保留");
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
