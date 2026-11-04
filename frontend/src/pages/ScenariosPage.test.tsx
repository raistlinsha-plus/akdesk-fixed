// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScenariosPage } from "./ScenariosPage";

beforeEach(() => { vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Casebook must not fetch")))); });
afterEach(() => { cleanup(); expect(fetch).not.toHaveBeenCalled(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("five-minute synthetic scenarios", () => {
  it("shows three task-specific entries and safely falls back from unknown links", async () => {
    const select = vi.fn();
    render(<ScenariosPage selectedId="private-key-unknown" onSelect={select} />);
    expect(screen.getByRole("note").textContent).toContain("不读取或写入研究库");
    expect(screen.getByRole("status").textContent).toContain("没有找到");
    expect(screen.queryByText("private-key-unknown")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "体验跟踪一个利率观点" }));
    expect(select).toHaveBeenCalledExactlyOnceWith("rates");
  });
  it("reuses the existing daily brief and keeps notes only until explicit reset", async () => {
    const user = userEvent.setup();
    render(<ScenariosPage selectedId="daily" onSelect={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "核验数值" }));
    expect(screen.getByText("-2.00 BP")).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("选择样例期限"), "30Y");
    expect(screen.getByText("+1.00 BP")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "带走简报" }));
    const note = screen.getByLabelText(/人工备注/);
    await user.type(note, "本页临时观察");
    await user.click(screen.getByRole("button", { name: "观察变化" }));
    await user.click(screen.getByRole("button", { name: "带走简报" }));
    expect((screen.getByLabelText(/人工备注/) as HTMLTextAreaElement).value).toBe("本页临时观察");
    await user.click(screen.getByRole("button", { name: "重置此案例" }));
    await user.click(screen.getByRole("button", { name: "带走简报" }));
    expect((screen.getByLabelText(/人工备注/) as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByRole("button", { name: "下载 Markdown" })).toBeTruthy();
  });
  it("classifies evidence and exports the selected research draft, not an automatic conclusion", async () => {
    const user = userEvent.setup();
    render(<ScenariosPage selectedId="rates" onSelect={vi.fn()} />);
    await user.clear(screen.getByLabelText("样例研究问题"));
    await user.type(screen.getByLabelText("样例研究问题"), "我的临时研究问题");
    await user.click(screen.getByRole("button", { name: "区分证据" }));
    await user.selectOptions(screen.getByLabelText("曲线样例的研究分类"), "pending");
    await user.click(screen.getByRole("button", { name: "安排验证" }));
    expect(screen.getByLabelText("样例成品预览").textContent).toContain("我的临时研究问题");
    expect(screen.getByLabelText("样例成品预览").textContent).toContain("待核验：10Y");
    fireEvent.change(screen.getByLabelText("样例下次复盘日"), { target: { value: "2026-08-01" } });
    expect(screen.getByRole("alert").textContent).toContain("晚于样例观察日");
    expect((screen.getByRole("button", { name: "下载样例 Markdown" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("previews fixed credit data, keeps failed spreads empty and creates only selected draft tasks", async () => {
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<ScenariosPage selectedId="credit" onSelect={vi.fn()} navigate={navigate} />);
    expect(screen.queryByRole("table")).toBeNull();
    await user.click(screen.getByRole("button", { name: "载入三条合成资料预览" }));
    expect(screen.getByRole("table")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "检查覆盖门禁" }));
    expect(screen.getAllByText("— 不计算利差")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "选择复核任务" }));
    await user.click(screen.getByRole("checkbox", { name: /合成样例乙券/ }));
    expect(screen.getByLabelText("样例成品预览").textContent).toContain("- [ ] 合成样例乙券");
    expect(navigate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "打开本地信用观察 R2" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("credit");
  });
  it("requires explicit feedback choices and never carries the editable question into GitHub", async () => {
    const user = userEvent.setup();
    render(<ScenariosPage selectedId="rates" onSelect={vi.fn()} surface="online" />);
    await user.type(screen.getByLabelText("样例研究问题"), " 不能外发的临时文字");
    await user.click(screen.getByRole("button", { name: "安排验证" }));
    expect((screen.getByRole("button", { name: "预览反馈信息" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("link", { name: /前往 GitHub/ })).toBeNull();
    await user.selectOptions(screen.getByLabelText("这次体验结果"), "browsed");
    await user.selectOptions(screen.getByLabelText("下周是否愿意再试"), "yes");
    await user.click(screen.getByRole("button", { name: "预览反馈信息" }));
    const link = screen.getByRole("link", { name: /前往 GitHub/ });
    const url = new URL(link.getAttribute("href")!);
    expect(url.searchParams.get("result")).toBe("只浏览了案例");
    expect(url.searchParams.get("reuse")).toBe("愿意尝试");
    expect(url.href).not.toContain(encodeURIComponent("不能外发"));
    expect(screen.getByLabelText("反馈预填预览").textContent).not.toContain("不能外发");
    await user.selectOptions(screen.getByLabelText("这次体验结果"), "blocked");
    expect(screen.queryByRole("link", { name: /前往 GitHub/ })).toBeNull();
  });
  it("does not claim clipboard success when unavailable, and shares only a canonical case URL", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    render(<ScenariosPage selectedId="credit" onSelect={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "复制公开案例链接" }));
    expect(screen.getByRole("status").textContent).toContain("不允许复制");
    expect(writeText).toHaveBeenCalledExactlyOnceWith("https://raistlinsha-plus.github.io/akdesk-fixed/#/scenarios?q=credit");
  });
  it("clears research drafts when switching to a different case", async () => {
    const { rerender } = render(<ScenariosPage selectedId="rates" onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("样例研究问题"), { target: { value: "临时问题不得跨案例残留" } });
    rerender(<ScenariosPage selectedId="credit" onSelect={vi.fn()} />);
    rerender(<ScenariosPage selectedId="rates" onSelect={vi.fn()} />);
    expect((screen.getByLabelText("样例研究问题") as HTMLTextAreaElement).value).not.toContain("不得跨案例残留");
  });
});
