// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { CrossAssetWeekPage } from "./CrossAssetWeekPage";
import { SAMPLE_END, SAMPLE_WEEK, type WeekDraft } from "../crossAssetWeek";
import { apiGet } from "../api";
import { downloadScenarioFile } from "../scenarios";

vi.mock("../api", () => ({ apiGet: vi.fn() }));
vi.mock("../researchUtils", () => ({ shanghaiDate: () => "2026-08-01" }));
vi.mock("../scenarios", () => ({ downloadScenarioFile: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const mockBond = {
  adapter: "yield_curves", metric: "yield",
  dates: SAMPLE_WEEK.bond.points.map(point => point.date),
  series: [{ key: "10Y", values: SAMPLE_WEEK.bond.points.map(point => point.value) }],
};

function card(name: string) {
  return within(screen.getByRole("heading", { name }).closest("article")!);
}

it("renders and downloads a purely synthetic week without contacting any API", () => {
  render(<CrossAssetWeekPage sample />);
  expect(screen.getByText("-3.00 BP")).toBeTruthy();
  expect(screen.getByText("前期观测 缺失")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("我的判断与下周待核验事项"), { target: { value: "下周继续核对日期" } });
  fireEvent.click(screen.getByRole("button", { name: "下载合成周复盘" }));
  expect(downloadScenarioFile).toHaveBeenCalledWith(expect.stringContaining("下周继续核对日期"), `AKDesk-股债金汇周复盘-${SAMPLE_END}-合成样例.md`);
  expect(apiGet).not.toHaveBeenCalled();
});

it("keeps failed, locally missing and stale rows separate; live download is reference-only", async () => {
  vi.mocked(apiGet).mockImplementation(async path => {
    if (path.includes("CSI")) throw new Error("source failed");
    if (path.includes("SGE")) return {
      asset: { id: "SGE:Au99.99" }, demo: false, state: "stale",
      data: SAMPLE_WEEK.gold.points.map(point => ({ date: point.date, close: point.value })),
    };
    if (path.includes("yield_curves")) return mockBond;
    return { adapter: "fx_rmb_reference", metric: "mid", dates: [], series: [] };
  });
  render(<CrossAssetWeekPage />);
  expect(apiGet).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "读取本周" }));
  expect(await screen.findByText("读取失败或超时")).toBeTruthy();
  expect(screen.getByText("旧缓存 · 来源可能不可用")).toBeTruthy();
  expect(screen.getByText("-3.00 BP")).toBeTruthy();
  expect(within(screen.getByText("美元兑人民币参考中间价").closest("article")!).getByText("本期观测 缺失")).toBeTruthy();
  expect(apiGet).toHaveBeenCalledTimes(4);
  fireEvent.click(screen.getByRole("button", { name: "下载查询引用底稿" }));
  const content = vi.mocked(downloadScenarioFile).mock.calls[0][0];
  expect(content).not.toMatch(/-3\.00 BP|\+1\.00%|2026-07-30/);
  expect(content).toContain("不包含行情数值、派生变化、观测日期");
  fireEvent.change(screen.getByLabelText("周结束日"), { target: { value: "2026-07-25" } });
  expect(screen.queryByRole("button", { name: "下载查询引用底稿" })).toBeNull();
});

it("shows completed rows while another source is pending and retries only the selected row", async () => {
  let fxCalls = 0;
  vi.mocked(apiGet).mockImplementation(async path => {
    if (path.includes("yield_curves")) return mockBond;
    if (path.includes("fx_rmb_reference")) {
      fxCalls++;
      return {
        adapter: "fx_rmb_reference", metric: "mid",
        dates: ["2026-07-24", "2026-07-31"],
        series: [{ key: "USDCNY", values: [fxCalls === 1 ? null : 7, 7.07] }],
      };
    }
    if (path.includes("SGE")) return new Promise(() => {});
    return { asset: { id: "CSI:000300" }, demo: true, state: "demo", data: [] };
  });
  render(<CrossAssetWeekPage />);
  fireEvent.click(screen.getByRole("button", { name: "读取本周" }));
  expect(await screen.findByText("-3.00 BP")).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain("1 项读取中，其余可先看");
  expect(card("黄金 Au99.99").getByText("正在读取")).toBeTruthy();
  expect(card("沪深300指数").getByText("当前服务为演示模式")).toBeTruthy();
  expect(card("美元兑人民币参考中间价").getByText(/前期没有本地观测/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "仅重读美元兑人民币参考中间价" }));
  expect(await card("美元兑人民币参考中间价").findByText("+1.00%")).toBeTruthy();
  expect(vi.mocked(apiGet).mock.calls.map(([path]) => path.split("?")[0])).toEqual([
    "/cross-assets/history", "/history", "/cross-assets/history", "/history", "/history",
  ]);
});

it("aborts a previous week's requests and ignores responses that arrive anyway", async () => {
  let resolveBond!: (value: typeof mockBond) => void;
  let oldSignal: AbortSignal | undefined;
  let bondCalls = 0;
  vi.mocked(apiGet).mockImplementation(async (path, options) => {
    if (!path.includes("yield_curves")) return {};
    bondCalls++;
    if (bondCalls === 1) {
      oldSignal = options?.signal;
      return new Promise(resolve => { resolveBond = resolve; });
    }
    return mockBond;
  });
  render(<CrossAssetWeekPage />);
  fireEvent.click(screen.getByRole("button", { name: "读取本周" }));
  fireEvent.click(screen.getByRole("button", { name: "前一周" }));
  expect(oldSignal?.aborted).toBe(true);
  expect((screen.getByLabelText("周结束日") as HTMLInputElement).value).toBe("2026-07-24");
  expect(apiGet).toHaveBeenCalledTimes(4);
  fireEvent.click(screen.getByRole("button", { name: "读取本周" }));
  await card("10年期国债收益率").findByText("本期观测 2026-07-24");
  await act(async () => resolveBond({
    ...mockBond, dates: ["2026-07-17", "2026-07-24"], series: [{ key: "10Y", values: [1.8, 1.9] }],
  }));
  expect(card("10年期国债收益率").getByText("前期观测 缺失")).toBeTruthy();
  expect(screen.queryByText("+10.00 BP")).toBeNull();
});

it("keeps the draft on source navigation and can read only the checked source when returning", async () => {
  vi.mocked(apiGet).mockImplementation(async path => path.includes("yield_curves") ? mockBond : {});
  function Harness() {
    const [draft, setDraft] = useState<WeekDraft | null>(null);
    const [source, setSource] = useState("");
    return source
      ? <button onClick={() => setSource("")}>返回 {source}</button>
      : <CrossAssetWeekPage draft={draft} onDraftChange={setDraft} onSource={link => setSource(link.page)} />;
  }
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "读取本周" }));
  await screen.findByText("-3.00 BP");
  fireEvent.change(screen.getByLabelText("我的判断与下周待核验事项"), { target: { value: "只保留在标签页" } });
  fireEvent.click(card("10年期国债收益率").getByRole("button", { name: "到原模块核验" }));
  fireEvent.click(screen.getByRole("button", { name: "返回 curves" }));
  expect((screen.getByLabelText("我的判断与下周待核验事项") as HTMLTextAreaElement).value).toBe("只保留在标签页");
  expect(vi.mocked(apiGet)).toHaveBeenCalledTimes(4);
  fireEvent.click(screen.getByRole("button", { name: "仅重读10年期国债收益率" }));
  expect(await screen.findByText("-3.00 BP")).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain("3 项尚未读取");
  expect(vi.mocked(apiGet)).toHaveBeenCalledTimes(5);
  fireEvent.click(screen.getByRole("button", { name: "下载查询引用底稿" }));
  expect(downloadScenarioFile).toHaveBeenCalledWith(expect.stringContaining("只保留在标签页"), expect.stringContaining(SAMPLE_END));
});
