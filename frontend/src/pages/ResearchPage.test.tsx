// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost } from "../api";
import type { DailyReport } from "../types";
import { ResearchPage } from "./ResearchPage";

vi.mock("../api", () => ({ apiGet: vi.fn(), apiPost: vi.fn(), ApiError: class extends Error { status: number; constructor(status: number, message: string) { super(message); this.status = status; } } }));
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
  it("explicitly transfers only manual notes to a project and retains them on failure and success", async () => {
    vi.mocked(apiGet).mockImplementation(async path => {
      if (path === "/research/daily-reports") return [];
      if (path === "/research/projects") return [{ id: 9, title: "我的研究", status: "tracking" }];
      return report("2026-07-27");
    });
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError(0, "响应未知"));
    vi.mocked(apiPost).mockResolvedValueOnce({ project_id: 9, entry_id: 7, evidence_id: null, deduplicated: true });
    const user = userEvent.setup();
    render(<ResearchPage refreshSeed={0} navigate={vi.fn()} />);
    await user.type(await screen.findByRole("textbox"), "只记录自己对期限分化的疑问");
    await user.click(screen.getByRole("button", { name: "将人工备注保存为研究笔记" }));
    await screen.findByRole("option", { name: "我的研究" });
    await user.selectOptions(screen.getByLabelText("目标研究项目"), "9");
    await user.click(screen.getByRole("button", { name: "预览保存内容" }));
    expect(apiPost).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    await screen.findByRole("alert");
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("只记录自己对期限分化的疑问");
    await user.click(screen.getByRole("button", { name: "确认保存到该项目" }));
    await screen.findByText(/已保存到「我的研究」/);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("只记录自己对期限分化的疑问");
    expect(vi.mocked(apiPost).mock.calls[0][1]).toEqual({ kind: "brief_note", request_id: expect.any(String), confirmed: true, note: "只记录自己对期限分化的疑问", report_date: "2026-07-27" });
    expect(vi.mocked(apiPost).mock.calls[1][1]).toEqual(vi.mocked(apiPost).mock.calls[0][1]);
  });
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
