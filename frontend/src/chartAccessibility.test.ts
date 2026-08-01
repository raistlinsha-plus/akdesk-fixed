import { describe, expect, it } from "vitest";
import {
  describeLineChart,
  lineChartPrecision,
  summarizeLineChart,
} from "./chartAccessibility";

describe("chart accessibility summaries", () => {
  it("reports latest values and direction while ignoring nulls", () => {
    const categories = ["2026-07-15", "2026-07-16", "2026-07-17"];
    const series = [{ name: "10Y", values: [1.7, null, 1.8] }];
    expect(summarizeLineChart(categories, series)[0]).toMatchObject({
      firstDate: "2026-07-15",
      latestDate: "2026-07-17",
      direction: "上升",
    });
    expect(describeLineChart(categories, series, "%")).toContain("最新 1.8000%");
  });

  it("describes an all-null chart as empty", () => {
    expect(describeLineChart(["2026-07-17"], [{ name: "10Y", values: [null] }], "%"))
      .toContain("暂无有效数值");
  });

  it("keeps narrow market ranges distinguishable on the value axis", () => {
    expect(lineChartPrecision([{ name: "10Y", values: [1.7314, 1.7404, 1.7463] }]))
      .toBe(4);
    expect(lineChartPrecision([{ name: "wide", values: [10, 90] }])).toBe(0);
    expect(lineChartPrecision([{ name: "flat", values: [0.0068, 0.0068] }])).toBe(5);
  });
});
