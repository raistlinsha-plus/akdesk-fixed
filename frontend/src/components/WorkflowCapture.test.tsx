// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost } from "../api";
import type { MarketResearchSignal, ResearchProject } from "../types";
import { WorkflowCapture } from "./WorkflowCapture";

vi.mock("../api", () => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
  ApiError: class extends Error { status: number; constructor(status: number, message: string) { super(message); this.status = status; } },
}));

const projects = [
  { id: 1, title: "利率观察甲", status: "tracking" },
  { id: 2, title: "利率观察乙", status: "draft" },
  { id: 3, title: "归档项目不可写", status: "archived" },
] as ResearchProject[];
const signal: MarketResearchSignal = {
  id: "curve-10y", category: "curve", severity: "watch", direction: "down", title: "10Y 当前变化", summary: "当前变化待结合原始曲线核验", value: 1.75, unit: "%", adapter: "yield_curves", source: "测试真实来源", source_url: "https://example.com", observation_time: "2026-11-04", fetched_at: "2026-11-04T15:30:00+08:00", trust_level: "trusted", quality_score: 100, data_state: "latest", demo: false, actionable: true, trigger_reason: "达到观察阈值",
};
function result(projectId = 1) { return { project_id: projectId, entry_id: 20, evidence_id: null, deduplicated: false }; }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-11-04T08:00:00+08:00")); vi.mocked(apiGet).mockResolvedValue(projects); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

async function openBrief(note = "自己的待核验判断") {
  const user = userEvent.setup();
  const view = render(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note }} />);
  await user.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
  await screen.findByRole("option", { name: "利率观察甲" });
  await user.selectOptions(screen.getByLabelText("目标研究项目"), "1");
  await user.click(screen.getByRole("button", { name: "预览保存内容" }));
  return { user, ...view };
}

describe("explicit workflow capture", () => {
  it("does not load projects or write until a user opens an eligible capture", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<WorkflowCapture source={{ kind: "market_signal", signal: { ...signal, demo: true } }} />);
    expect((screen.getByRole("button", { name: "关联研究项目" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "关联研究项目" }));
    expect(apiGet).not.toHaveBeenCalled();
    for (const patch of [{ actionable: false }, { trust_level: "partial" as const }, { data_state: "stale" as const }, { observation_time: null }, { value: null }, { observation_time: "2026-10-27" }, { observation_time: "2026-11-05" }, { observation_time: "not a date" }, { source: "FRED" }, { source_url: "https://api.stlouisfed.org/fred/series" }]) {
      rerender(<WorkflowCapture source={{ kind: "market_signal", signal: { ...signal, ...patch } }} />);
      expect((screen.getByRole("button", { name: "关联研究项目" }) as HTMLButtonElement).disabled).toBe(true);
    }
    rerender(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note: "   " }} />);
    expect((screen.getByRole("button", { name: "将人工备注保存为研究笔记" }) as HTMLButtonElement).disabled).toBe(true);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("requires project selection, preview and final confirmation, saving only typed brief text", async () => {
    const { user } = await openBrief("  仅我的人工备注  ");
    expect(apiPost).not.toHaveBeenCalled();
    expect(screen.queryByRole("option", { name: "归档项目不可写" })).toBeNull();
    expect(screen.getByLabelText("即将保存的内容").textContent).toContain("仅我的人工备注");
    vi.mocked(apiPost).mockResolvedValue(result());
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    expect(apiPost).toHaveBeenCalledWith("/research/projects/1/workflow-capture", {
      kind: "brief_note", request_id: expect.stringMatching(/^[0-9a-f-]{36}$/), confirmed: true, note: "仅我的人工备注", report_date: "2026-11-04",
    }, expect.objectContaining({ timeoutMs: 20_000 }));
    expect((await screen.findByRole("status")).textContent).toContain("已保存到「利率观察甲」");
    const body = vi.mocked(apiPost).mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["confirmed", "kind", "note", "report_date", "request_id"]);
  });

  it("retries the identical request ID after response loss, without clearing notes", async () => {
    const { user } = await openBrief();
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(0, "响应丢失"));
    vi.mocked(apiPost).mockResolvedValueOnce({ ...result(), deduplicated: true });
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    expect((await screen.findByRole("alert")).textContent).toContain("响应丢失");
    const first = vi.mocked(apiPost).mock.calls[0][1];
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    expect(vi.mocked(apiPost).mock.calls[1][1]).toEqual(first);
    expect((await screen.findByRole("status")).textContent).toContain("重试已去重");
    expect(screen.getByLabelText("即将保存的内容").textContent).toContain("自己的待核验判断");
  });

  it("sends server-verifiable signal identity rather than client snapshot values", async () => {
    const user = userEvent.setup();
    render(<WorkflowCapture source={{ kind: "market_signal", signal }} />);
    await user.click(screen.getByRole("button", { name: "关联研究项目" }));
    await screen.findByRole("option", { name: "利率观察甲" });
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "2");
    await user.type(screen.getByLabelText("本次研究备注（可选）"), "核验期限分歧");
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    expect(screen.getByLabelText("即将保存的内容").textContent).toContain(signal.fetched_at);
    const pending = deferred<ReturnType<typeof result>>();
    vi.mocked(apiPost).mockReturnValue(pending.promise);
    await user.dblClick(screen.getByRole("button", { name: "确认保存到该项目" }));
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(vi.mocked(apiPost).mock.calls[0][1]).toEqual({ kind: "market_signal", request_id: expect.any(String), confirmed: true, note: "核验期限分歧", signal_id: signal.id, expected_fetched_at: signal.fetched_at });
    expect((screen.getByLabelText("目标研究项目") as HTMLSelectElement).disabled).toBe(true);
    pending.resolve(result(2));
    await screen.findByRole("status");
  });

  it("invalidates preview on project change and uses a new request ID for the changed target", async () => {
    const { user } = await openBrief();
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(0, "结果未确认"));
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    await screen.findByRole("alert");
    const firstId = (vi.mocked(apiPost).mock.calls[0][1] as Record<string, unknown>).request_id;
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "2");
    expect(screen.queryByRole("button", { name: "确认保存到该项目" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    vi.mocked(apiPost).mockResolvedValueOnce(result(2));
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    const secondId = (vi.mocked(apiPost).mock.calls[1][1] as Record<string, unknown>).request_id;
    expect(secondId).not.toBe(firstId);
    expect(vi.mocked(apiPost).mock.calls[1][0]).toBe("/research/projects/2/workflow-capture");
  });

  it("shows a 409 as a refresh-and-review conflict, never as success", async () => {
    const { user } = await openBrief();
    vi.mocked(apiPost).mockRejectedValue(new ApiError(409, "预览已过期"));
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    expect((await screen.findByRole("alert")).textContent).toContain("先刷新来源");
    expect(screen.queryByText(/已保存到/)).toBeNull();
    expect((screen.getByRole("button", { name: "确认保存到该项目" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText("即将保存的内容").textContent).toContain("自己的待核验判断");
  });

  it("does not label a changed brief draft as saved when an earlier submission finishes", async () => {
    const user = userEvent.setup();
    const navigate = vi.fn();
    const view = render(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note: "旧备注" }} navigate={navigate} />);
    await user.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    await screen.findByRole("option", { name: "利率观察甲" });
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "1");
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    const pending = deferred<ReturnType<typeof result>>();
    vi.mocked(apiPost).mockReturnValue(pending.promise);
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    view.rerender(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note: "新备注" }} navigate={navigate} />);
    pending.resolve(result());
    expect((await screen.findByRole("alert")).textContent).toContain("页面内容已变化");
    expect(screen.queryByText(/已保存到「/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "核对上次提交的原项目" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("projects", "1");
  });

  it("invalidates a market preview when source time or trust changes and ignores obsolete loads", async () => {
    const user = userEvent.setup();
    const view = render(<WorkflowCapture source={{ kind: "market_signal", signal }} />);
    await user.click(screen.getByRole("button", { name: "关联研究项目" }));
    await screen.findByRole("option", { name: "利率观察甲" });
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "1");
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    view.rerender(<WorkflowCapture source={{ kind: "market_signal", signal: { ...signal, fetched_at: "2026-11-04T15:31:00+08:00" } }} />);
    expect(screen.queryByRole("button", { name: "确认保存到该项目" })).toBeNull();
    view.rerender(<WorkflowCapture source={{ kind: "market_signal", signal: { ...signal, actionable: false } }} />);
    expect(screen.getByRole("alert").textContent).toContain("不满足保存条件");
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("returns keyboard focus to the trigger when the user cancels a preview", async () => {
    const { user } = await openBrief();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("offers an explicit project-list retry after a read failure and writes nothing", async () => {
    const user = userEvent.setup();
    vi.mocked(apiGet).mockRejectedValueOnce(new Error("读取失败"));
    render(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note: "自己的文字" }} />);
    await user.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    expect((await screen.findByRole("alert")).textContent).toContain("读取失败");
    await user.click(screen.getByRole("button", { name: "重新读取项目" }));
    await screen.findByRole("option", { name: "利率观察甲" });
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("ends a hung project read after 15 seconds and explicitly retries without writes", async () => {
    vi.useFakeTimers();
    let firstSignal: AbortSignal | undefined;
    vi.mocked(apiGet).mockImplementationOnce((_path, options) => { firstSignal = options?.signal; return new Promise(() => {}); });
    render(<WorkflowCapture source={{ kind: "brief_note", reportDate: "2026-11-04", note: "自己的文字" }} />);
    fireEvent.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(firstSignal?.aborted).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("项目列表读取超时");
    expect(screen.queryByText("正在读取可选项目…")).toBeNull();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重新读取项目" })); });
    expect(screen.getByRole("option", { name: "利率观察甲" })).toBeTruthy();
    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("blocks global navigation shortcuts during a pending save and retains the retry identity", async () => {
    const { user } = await openBrief();
    const globalShortcut = vi.fn();
    window.addEventListener("keydown", globalShortcut);
    const pending = deferred<ReturnType<typeof result>>();
    vi.mocked(apiPost).mockReturnValue(pending.promise);
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    const dialog = screen.getByRole("dialog");
    for (const key of ["r", "1", "k"]) {
      expect(fireEvent.keyDown(dialog, { key, metaKey: true })).toBe(false);
      expect(fireEvent.keyDown(dialog, { key, ctrlKey: true })).toBe(false);
    }
    expect(globalShortcut).not.toHaveBeenCalled();
    window.removeEventListener("keydown", globalShortcut);
    pending.resolve(result());
    await screen.findByRole("status");
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it("blocks a retained preview until the project list has finished reloading", async () => {
    const { user } = await openBrief();
    await user.click(screen.getByRole("button", { name: "关闭保存预览" }));
    const pending = deferred<ResearchProject[]>();
    vi.mocked(apiGet).mockReturnValueOnce(pending.promise);
    await user.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    const confirm = screen.getByRole("button", { name: "确认保存到该项目" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await user.click(confirm);
    expect(apiPost).not.toHaveBeenCalled();
    pending.resolve(projects.filter(item => item.id !== 1));
    await act(async () => { await pending.promise; });
    expect(confirm.disabled).toBe(true);
  });
});
