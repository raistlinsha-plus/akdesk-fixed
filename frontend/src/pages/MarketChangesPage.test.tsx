// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost } from "../api";
import type { MarketResearchBrief, MarketResearchSignal } from "../types";
import { MarketChangesPage } from "./MarketChangesPage";

vi.mock("../api", () => ({ apiGet: vi.fn(), apiPost: vi.fn(), ApiError: class extends Error {} }));
vi.mock("./MarketPages", () => ({ PageHeading: ({ title }: { title: string }) => <h1>{title}</h1> }));

const signal: MarketResearchSignal = {
  id: "funding-change", category: "funding", severity: "high", direction: "up", title: "资金利率整体变化", summary: "资金利率平均变动 +3 BP", value: 3, unit: "BP", adapter: "money_rates", source: "AKShare / Shibor", observation_time: "2026-11-04", fetched_at: "2026-11-04T10:00:00+08:00", trust_level: "trusted", quality_score: 100, data_state: "latest", demo: false, actionable: true, trigger_reason: "变动达到观察阈值",
};
function brief(signals = [signal]): MarketResearchBrief {
  return { generated_at: "2026-11-04T10:00:00+08:00", market_status: "交易中", headline: "资金面待核验", signals, sources: [], eligible_signal_ids: [signal.id], snapshot_eligible: true, notice: "仅供研究参考", settings: { funding_change_bp: 1, curve_change_bp: 2, curve_spread_bp: 20, futures_change_pct: 0.1, bond_change_bp: 1 } };
}

beforeEach(() => { window.localStorage.clear(); vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-11-04T10:30:00+08:00")); });
afterEach(() => { cleanup(); window.localStorage.clear(); vi.useRealTimers(); vi.resetAllMocks(); });

describe("market-to-project integration", () => {
  it("requires explicit preview and confirmation and routes to the saved project", async () => {
    vi.mocked(apiGet).mockImplementation(async path => path === "/research/projects" ? [{ id: 8, title: "资金面跟踪", status: "tracking" }] : brief());
    vi.mocked(apiPost).mockResolvedValue({ project_id: 8, entry_id: 21, evidence_id: 22, deduplicated: false });
    const navigate = vi.fn();
    const user = userEvent.setup();
    render(<MarketChangesPage refreshSeed={0} navigate={navigate} />);
    await screen.findByRole("heading", { name: signal.title });
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(apiPost).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "关联研究项目" }));
    await screen.findByRole("option", { name: "资金面跟踪" });
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "8");
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    expect(apiPost).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    await screen.findByText(/已保存到「资金面跟踪」/);
    expect(vi.mocked(apiPost).mock.calls[0][1]).toEqual({ kind: "market_signal", request_id: expect.any(String), confirmed: true, note: "", signal_id: signal.id, expected_fetched_at: signal.fetched_at });
    await user.click(screen.getByRole("button", { name: "打开已保存的研究项目" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("projects", "8");
  });

  it("keeps verification-only signals visible when requested but disables capture", async () => {
    vi.mocked(apiGet).mockResolvedValue(brief([{ ...signal, trust_level: "partial", actionable: false }]));
    const user = userEvent.setup();
    render(<MarketChangesPage refreshSeed={0} navigate={vi.fn()} />);
    await screen.findByText("当前筛选下没有变化");
    await user.click(screen.getByRole("checkbox", { name: "仅看可信可行动" }));
    const card = (await screen.findByRole("heading", { name: signal.title })).closest("article")!;
    const capture = within(card).getByRole("button", { name: "关联研究项目" }) as HTMLButtonElement;
    expect(capture.disabled).toBe(true);
    await user.click(capture);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
