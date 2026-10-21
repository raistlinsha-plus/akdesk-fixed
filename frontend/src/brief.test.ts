import { describe, expect, it } from "vitest";
import {
  briefMarkdown,
  briefMode,
  briefNumber,
  briefTime,
  reportToBrief,
  safeSourceUrl,
  type BriefDocument,
} from "./brief";
import type { DailyReport } from "./types";

function fixture(): BriefDocument {
  return {
    date: "2026-07-27",
    generatedAt: "2026-07-27T16:30:00+08:00",
    marketStatus: "固定场景",
    headline: "资金变化有限，长端收益率下行",
    mode: "example",
    funding: { tone: "变化有限", averageChangeBp: 0, items: [{ name: "Shibor O/N", value: 1.425, changeBp: -2.1 }] },
    curve: { tenYear: 1.8, tenYearChangeBp: -2, spreadsBp: { "10Y-1Y": 40, "10Y-5Y": 16, "30Y-10Y": 18 } },
    futures: [{ product: "T", contract: "T示例", price: 108.055, changePct: 0.12 }],
    sources: [{ adapter: "money_rates", label: "资金", source: "合成示例", sourceUrl: null, observationTime: "2026-07-27", fetchedAt: "2026-07-27T16:20:00+08:00", dataState: "demo", trustLevel: "unavailable", demo: true }],
    notes: ["示例不代表真实市场。"],
  };
}

function reportFixture(): DailyReport {
  return {
    generated_at: "2026-07-27T16:30:00+08:00",
    report_date: "2026-07-27",
    report_mode: "close",
    market_status: "已收盘",
    headline: "资金变化有限",
    funding: { tone: "变化有限", average_change_bp: 0, items: [{ name: "Shibor O/N", tenor: "O/N", value: null, change_bp: 0 }] },
    curve: { tenors: { "10Y": null }, spreads_bp: { "10Y-1Y": null }, ten_year_change_bp: null },
    futures: [], bond_movers: [], active_bonds: [], events: [],
    event_groups: { upcoming: [], recent: [] },
    confidence: { level: "low", score: 0, message: "数据不足", trusted_sources: 0, suspicious_rows: 0 },
    data_health: { healthy: 0, cached: 0, available: 0, total: 0, history: { points: 0, adapters: 0, oldest: null, newest: null } },
    data_notes: [],
  };
}

describe("one-page fixed-income brief", () => {
  it("keeps sample mode, fixed date, provenance and units in the exported document", () => {
    const text = briefMarkdown(fixture(), "核对利差计算。");
    expect(text).toContain("一页固收简报（示例） · 2026-07-27");
    expect(text).toContain("示例数据 · 非实时");
    expect(text).toContain("1.4250%");
    expect(text).toContain("-2.10 BP");
    expect(text).toContain("40.00 BP");
    expect(text).toContain("+0.120%");
    expect(text).toContain("观测 2026-07-27");
    expect(text).toContain("抓取 2026-07-27 16:20:00+08:00");
    expect(text).toContain("## 人工备注");
    expect(text).toContain("核对利差计算。");
  });

  it("does not allow a live label to hide a sample source", () => {
    const document = { ...fixture(), mode: "live" as const };
    expect(briefMode(document)).toBe("example");
    expect(briefMarkdown(document)).toContain("示例数据 · 非实时");
    document.sources.push({ ...document.sources[0], adapter: "yield_curves", demo: false, dataState: "cached" });
    expect(briefMode(document)).toBe("mixed");
    expect(briefMarkdown(document)).toContain("含示例数据");
  });

  it("preserves true zero and missing/non-finite values distinctly", () => {
    expect(briefNumber(0, 2, " BP", true)).toBe("0.00 BP");
    expect(briefNumber(null, 2, "%")).toBe("—");
    expect(briefNumber(undefined)).toBe("—");
    expect(briefNumber(Number.NaN)).toBe("—");
    expect(briefNumber(Infinity)).toBe("—");
    const result = reportToBrief(reportFixture());
    expect(result.curve.tenYear).toBeNull();
    expect(result.funding.averageChangeBp).toBe(0);
    expect(result.funding.items[0].value).toBeNull();
    expect(result.notes.join(" ")).toContain("10Y 国债收益率缺失");
    expect(briefMarkdown(result)).toContain("10Y 国债：—");
  });

  it("marks older archives as unknown rather than implying real or live provenance", () => {
    const result = reportToBrief(reportFixture());
    expect(result.mode).toBe("unknown");
    expect(result.notes.join(" ")).toContain("历史归档没有逐源出处");
    expect(briefMarkdown(result)).toContain("来源信息不完整 · 待核验");
  });

  it("does not repeat directional claims from older archives when core values are missing", () => {
    const report = reportFixture();
    report.headline = "资金面变化有限，长端窄幅波动";
    report.funding.average_change_bp = null;
    const result = reportToBrief(report);
    expect(result.headline).toBe("资金面变动待核验，长端变动待核验");
    expect(briefMarkdown(result)).not.toContain("资金面变化有限，长端窄幅波动");
    report.funding.average_change_bp = 0;
    report.curve.tenors["10Y"] = 1.8;
    report.curve.ten_year_change_bp = 0;
    expect(reportToBrief(report).headline).toBe("资金面变化有限，长端窄幅波动");
  });

  it("uses per-source metadata and respects mixed mode during report conversion", () => {
    const report = reportFixture();
    report.data_sources = [
      { adapter: "money_rates", label: "资金面", source: "AKShare / Shibor", source_url: "https://example.com/rates?token=private#secret", observation_time: "2026-07-27", fetched_at: "2026-07-27T16:00:00+08:00", data_state: "cached", trust_level: "partial", demo: false },
      { adapter: "yield_curves", label: "曲线", source: "合成示例", source_url: null, observation_time: "2026-07-27", fetched_at: "2026-07-27T16:00:00+08:00", data_state: "demo", trust_level: "unavailable", demo: true },
    ];
    const result = reportToBrief(report);
    expect(result.mode).toBe("mixed");
    expect(result.sources[0].sourceUrl).toBe("https://example.com/rates");
    const markdown = briefMarkdown(result);
    expect(markdown).toContain("AKShare / Shibor");
    expect(markdown).toContain("缓存 · 部分可用");
    expect(markdown).not.toContain("private");
    expect(markdown).not.toContain("#secret");
  });

  it("accepts only http provenance links and preserves original timestamp time zones", () => {
    expect(safeSourceUrl("javascript:alert(1)")).toBeNull();
    expect(safeSourceUrl("https://name:password@example.com/rates")).toBeNull();
    expect(safeSourceUrl("/api/local")).toBeNull();
    expect(briefTime("2026-07-27T16:00:00.123456+08:00")).toBe("2026-07-27 16:00:00+08:00");
    expect(briefTime(null)).toBe("未提供");
  });
});
