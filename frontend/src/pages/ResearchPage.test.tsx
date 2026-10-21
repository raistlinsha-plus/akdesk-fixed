// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "../api";
import type { DailyReport } from "../types";
import { ResearchPage } from "./ResearchPage";

vi.mock("../api", () => ({ apiGet: vi.fn() }));
vi.mock("./MarketPages", () => ({ PageHeading: ({ title }: { title: string }) => <h1>{title}</h1> }));

function report(date: string): DailyReport {
  return {
    generated_at: `${date}T16:30:00+08:00`, report_date: date,
    report_mode: "close", market_status: "固定场景", headline: "资金变化有限，长端窄幅波动",
    funding: { tone: "变化有限", average_change_bp: 0, items: [] },
    curve: { tenors: { "10Y": 1.8 }, spreads_bp: { "10Y-1Y": 40 }, ten_year_change_bp: 0 },
    futures: [], bond_movers: [], active_bonds: [], events: [],
    event_groups: { upcoming: [], recent: [] },
    confidence: { level: "low", score: 0, message: "仅示例", trusted_sources: 0, suspicious_rows: 0 },
    data_health: { healthy: 0, cached: 0, available: 0, total: 0, history: { points: 0, adapters: 0, oldest: null, newest: null } },
    data_notes: [],
    data_sources: [{ adapter: "yield_curves", label: "曲线", source: "合成示例", source_url: null, observation_time: date, fetched_at: `${date}T16:00:00+08:00`, data_state: "demo", trust_level: "unavailable", demo: true }],
  };
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("ResearchPage temporary notes", () => {
  it("preserves the current date's notes through full-view checks and keeps other dates separate", async () => {
    vi.mocked(apiGet).mockImplementation(async (path) => {
      if (path === "/research/daily-reports") return [{ report_date: "2026-07-28", report_mode: "close", confidence_level: "low", updated_at: "2026-07-28" }];
      return report(path.includes("date=2026-07-28") ? "2026-07-28" : "2026-07-27");
    });
    const user = userEvent.setup();
    render(<ResearchPage refreshSeed={0} />);
    const notes = await screen.findByRole("textbox");
    await user.type(notes, "核验后保留这条观察");
    await user.click(screen.getByRole("button", { name: "完整复盘" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "一页简报" }));
    expect((await screen.findByRole("textbox") as HTMLTextAreaElement).value).toBe("核验后保留这条观察");

    await user.selectOptions(screen.getByRole("combobox"), "2026-07-28");
    await waitFor(() => expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe(""));
    await user.type(screen.getByRole("textbox"), "另一日期的备注");
    await user.selectOptions(screen.getByRole("combobox"), "");
    await waitFor(() => expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("核验后保留这条观察"));
    expect(window.localStorage.length).toBe(0);
  });
});
