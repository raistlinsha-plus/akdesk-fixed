import { describe, expect, it } from "vitest";
import {
  actionableMarketSignalIds,
  buildChartEvidence,
  buildMacroReferenceMarkdown,
  isReviewDue,
  parseResearchTags,
  shanghaiDate,
} from "./researchUtils";
import type { MarketResearchSignal } from "./types";

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

  it("stores only selected query parameters, never FRED metadata or observed ranges", () => {
    const query = {
      seriesIds: ["DGS10"], years: 1, transform: "level" as const,
      // Extra response material cannot enter the explicitly selected output.
      apiResponse: { values: [4.1], notes: "API_NOTES", name: "API_TITLE", dates: ["2026-07-13"] },
    };
    const evidence = buildChartEvidence(
      query,
      "美债研究",
      "2026-07-14T12:30:00Z",
    );
    expect(evidence.observation_start).toBeNull();
    expect(evidence.observation_end).toBeNull();
    expect(evidence.payload).toMatchObject({
      schema_version: 3,
      storage_mode: "reference_only",
      frozen: false,
      series: [{ series_id: "DGS10", source_url: "https://fred.stlouisfed.org/series/DGS10" }],
      transform: "level",
    });
    const serialized = JSON.stringify(evidence);
    for (const absent of ["API_NOTES", "API_TITLE", '"values"', '"dates"', "2026-07-13", "4.1"]) {
      expect(serialized).not.toContain(absent);
    }
    const markdown = buildMacroReferenceMarkdown(query, "2026-07-14T12:30:00Z");
    expect(markdown).toContain("[DGS10](https://fred.stlouisfed.org/series/DGS10)");
    expect(markdown).toContain("最近 1 年");
    expect(markdown).toContain("不保存 FRED 返回的数值、元数据或观测区间");
    expect(markdown).not.toMatch(/API_NOTES|API_TITLE|2026-07-13|4\.1|realtime_start/);
  });

  it("rejects malformed FRED query references before persistence or export", () => {
    expect(() => buildChartEvidence({ seriesIds: ["DGS10?notes=secret"], years: 1, transform: "level" }, "引用")).toThrow("序列标识");
    expect(() => buildMacroReferenceMarkdown({ seriesIds: ["DGS10"], years: 0, transform: "level" })).toThrow("年份范围");
  });
});
