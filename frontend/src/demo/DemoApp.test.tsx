// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_BRIEF, DEMO_CURVE } from "./demoData";
import { briefMarkdown } from "../brief";
import { BarChart, LineChart } from "../components/Charts";

vi.mock("../components/Charts", async (importOriginal) => {
  const charts = await importOriginal<typeof import("../components/Charts")>();
  // Replace the actual exports too: concurrent lazy imports can receive the
  // original namespace from Vitest while another import resolves its mock.
  return {
    ...charts,
    LineChart: vi.spyOn(charts, "LineChart").mockImplementation(({ series }) => <div role="img" aria-label="示例曲线图">{series.map((item) => item.name).join(" / ")}</div>),
    BarChart: vi.spyOn(charts, "BarChart").mockImplementation(() => <div role="img" aria-label="示例变动图" />),
  };
});

let DemoApp: typeof import("./DemoApp")["DemoApp"];

beforeAll(async () => {
  // Resolve the mocked module before DemoApp creates its two lazy chart imports.
  // Otherwise a pending chart import can outlive a fast route change in jsdom.
  expect(BarChart).toBeDefined();
  expect(LineChart).toBeDefined();
  const chartModules = await Promise.all([import("../components/Charts"), import("../components/Charts")]);
  chartModules.forEach((module) => expect(module.BarChart).toBe(BarChart));
  ({ DemoApp } = await import("./DemoApp"));
});

beforeEach(() => {
  window.history.replaceState(null, "", "/akdesk-fixed/#/overview");
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Demo must not request a backend"))));
});
afterEach(async () => {
  cleanup();
  await vi.dynamicImportSettled();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});
afterAll(() => vi.restoreAllMocks());

describe("static GitHub demo", () => {
  it("completes the sample workflow without calling any backend", async () => {
    const user = userEvent.setup();
    render(<DemoApp />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("带走一页研究底稿");
    expect(screen.getByRole("note").textContent).toContain("固定合成示例，非实时行情");
    expect(screen.getByRole("link", { name: "下载视频" }).getAttribute("href")).toMatch(/\/akdesk-demo-60s\.mp4$/);
    await user.click(screen.getByRole("button", { name: "开始 3 步体验" }));
    await screen.findByRole("heading", { name: "市场变化" });
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "曲线" }));
    expect(screen.getByRole("heading", { name: "10Y 国债收益率下行 2.00 BP" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "短端资金分化，隔夜利率下行" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "核验收益率曲线" }));
    await screen.findByRole("heading", { name: "曲线核验" });
    // Exercise both lightweight chart replacements, never ECharts/canvas effects.
    await screen.findByRole("img", { name: "示例曲线图" });
    await screen.findByRole("img", { name: "示例变动图" });
    await user.selectOptions(screen.getByLabelText("查看曲线"), "policy");
    await waitFor(() => expect(screen.getByLabelText("示例曲线图").textContent).toContain("国开债 · 固定样例"));
    expect((screen.getByRole("checkbox", { name: "对照国债前值" }) as HTMLInputElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "生成一页简报" }));
    await screen.findByRole("heading", { level: 1, name: "一页固收简报" });
    expect(screen.getByRole("button", { name: "下载 Markdown" })).toBeTruthy();
    expect(screen.getByText("示例数据 · 非实时", { exact: true })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("opens hash links, responds to history events and resets temporary notes", async () => {
    window.history.replaceState(null, "", "/akdesk-fixed/#/brief");
    const user = userEvent.setup();
    render(<DemoApp />);
    expect(screen.getByRole("heading", { level: 1, name: "一页固收简报" })).toBeTruthy();
    await user.click(screen.getByRole("link", { name: "跳到主要内容" }));
    expect(window.location.hash).toBe("#/brief");
    expect(document.activeElement).toBe(screen.getByRole("main"));
    const note = screen.getByRole("textbox");
    await user.type(note, "临时核验问题");
    await user.click(screen.getByRole("button", { name: "重置体验" }));
    await screen.findByRole("heading", { level: 1, name: "看懂一组市场变化，带走一页研究底稿。" });
    window.history.replaceState(null, "", "/akdesk-fixed/#/brief");
    fireEvent(window, new PopStateEvent("popstate"));
    await screen.findByRole("heading", { level: 1, name: "一页固收简报" });
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps synthetic provenance and curve calculations in exported samples", () => {
    expect(DEMO_BRIEF.sources.every((source) => source.demo === true && source.dataState === "demo")).toBe(true);
    expect(DEMO_BRIEF.sources.some((source) => source.trustLevel === "trusted")).toBe(false);
    expect(DEMO_CURVE.government[7] - DEMO_CURVE.previous[7]).toBeCloseTo(-0.02);
    expect((DEMO_CURVE.government[7] - DEMO_CURVE.government[2]) * 100).toBeCloseTo(DEMO_BRIEF.curve.spreadsBp["10Y-1Y"]!);
    const markdown = briefMarkdown(DEMO_BRIEF);
    expect(markdown).toContain("2026-08-03");
    expect(markdown).toContain("非实时");
    expect(markdown).toContain("AKDesk 内置合成样例");
  });
});
