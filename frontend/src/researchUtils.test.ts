import { describe, expect, it } from "vitest";
import {
  actionableMarketSignalIds,
  buildChartEvidence,
  buildMacroCsv,
  isReviewDue,
  parseResearchTags,
  shanghaiDate,
} from "./researchUtils";
import type { Dataset, MacroChartData, MarketResearchSignal } from "./types";

describe("research workflow helpers", () => {
  it("normalizes and deduplicates research tags", () => {
    expect(parseResearchTags("美债， 通胀,美债,, 久期")).toEqual([
      "美债",
      "通胀",
      "久期",
    ]);
  });

  it("does not report archived work as due", () => {
    expect(isReviewDue("2026-07-10", "tracking", "2026-07-14")).toBe(true);
    expect(isReviewDue("2026-07-10", "archived", "2026-07-14")).toBe(false);
    expect(isReviewDue(null, "review", "2026-07-14")).toBe(false);
  });

  it("uses the Shanghai calendar date around UTC midnight", () => {
    expect(shanghaiDate(new Date("2026-07-13T16:30:00Z"))).toBe("2026-07-14");
  });

  it("selects only actionable non-demo market signals", () => {
    const signal = (values: Partial<MarketResearchSignal>): MarketResearchSignal => ({
      id: "signal",
      category: "curve",
      severity: "info",
      direction: "neutral",
      title: "测试信号",
      summary: "测试",
      value: 1,
      unit: "BP",
      adapter: "yield_curves",
      source: "测试源",
      fetched_at: "2026-07-15T09:00:00",
      trust_level: "trusted",
      quality_score: 100,
      data_state: "live",
      demo: false,
      actionable: true,
      trigger_reason: "测试阈值说明",
      ...values,
    });
    expect(actionableMarketSignalIds([
      signal({ id: "trusted" }),
      signal({ id: "demo", demo: true }),
      signal({ id: "low-quality", quality_score: 59 }),
      signal({ id: "blocked", actionable: false }),
    ])).toEqual(["trusted"]);
  });

  it("stores FRED chart evidence as a value-free reference", () => {
    const chart = {
      data: {
        dates: ["2026-07-13", "2026-07-14"],
        series: [{
          key: "DGS10",
          name: "美国国债 10Y",
          values: [4.1, 4.2],
          frequency: "Daily",
          units: "Percent",
          source_organization: "Board of Governors",
          attribution: "Board of Governors; retrieved via FRED (DGS10)",
          source_url: "https://fred.stlouisfed.org/series/DGS10",
          realtime_start: ["2026-07-14", "2026-07-14"],
          realtime_end: ["9999-12-31", "9999-12-31"],
        }],
        transform: "level",
        years: 1,
        transform_source: "AKDesk local",
        storage_mode: "request_scoped",
        terms_url: "https://fred.stlouisfed.org/legal/terms/",
      },
      meta: {
        source: "FRED",
        fetched_at: "2026-07-14T12:00:00",
        stale: false,
        demo: false,
        warnings: [],
        market_status: "daily",
        market_status_label: "按发布更新",
        data_state: "live",
        quality_score: 100,
        quality_issues: [],
        trust_level: "trusted",
        suspicious_rows: 0,
      },
    } satisfies Dataset<MacroChartData>;

    const evidence = buildChartEvidence(
      chart,
      ["DGS10"],
      "美债研究",
      "2026-07-14T12:30:00",
    );
    expect(evidence.observation_start).toBe("2026-07-13");
    expect(evidence.observation_end).toBe("2026-07-14");
    expect(evidence.payload).toMatchObject({
      storage_mode: "reference_only",
      frozen: false,
      series: [{ series_id: "DGS10" }],
      transform: "level",
    });
    expect(JSON.stringify(evidence.payload)).not.toContain('"values"');
    expect(JSON.stringify(evidence.payload)).not.toContain('"dates"');

    const csv = buildMacroCsv(chart);
    expect(csv).toContain("Board of Governors");
    expect(csv).toContain("DGS10_realtime_start");
    expect(csv).toContain("2026-07-14");
    expect(csv).toContain("not endorsed or certified");
  });
});
