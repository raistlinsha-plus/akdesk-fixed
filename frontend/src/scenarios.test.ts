import { describe, expect, it } from "vitest";
import { CREDIT_SAMPLE, DEFAULT_QUESTION, DEFAULT_REVIEW_DATE, DEFAULT_ROLES, DEFAULT_TASK, SCENARIOS, creditSampleCsv, creditSampleMarkdown, ratesSampleMarkdown, sampleCurvePoint, scenarioById, validReviewDate } from "./scenarios";

describe("synthetic casebook contracts", () => {
  it("only resolves fixed cases and preserves the existing market sample calculations", () => {
    expect(SCENARIOS).toHaveLength(3);
    expect(scenarioById("https://private.example?key=secret")).toBeUndefined();
    expect(sampleCurvePoint("10Y")).toEqual({ tenor: "10Y", value: 1.8, previous: 1.82, changeBp: -2 });
    expect(sampleCurvePoint("30Y")?.changeBp).toBe(1);
    expect(sampleCurvePoint("unknown")).toBeNull();
  });
  it("rejects impossible, missing and non-future review dates against the fixed sample day", () => {
    for (const value of ["", "2026-08-03", "2026-02-31", "2026-13-01", "tomorrow"]) expect(validReviewDate(value)).toBe(false);
    expect(validReviewDate(DEFAULT_REVIEW_DATE)).toBe(true);
  });
  it("exports a bounded synthetic research draft without official API data", () => {
    const output = ratesSampleMarkdown(DEFAULT_QUESTION, DEFAULT_ROLES, DEFAULT_TASK, DEFAULT_REVIEW_DATE);
    expect(output).toContain("合成样例 · 非真实行情");
    expect(output).toContain("反证 / 分歧：短端资金分化");
    expect(output).toContain("支持线索：10Y");
    expect(output).toContain("不自动创建项目");
    expect(output).not.toContain("api.stlouisfed");
    expect(ratesSampleMarkdown("<script>alert(1)</script>", {}, "", "bad")).not.toContain("<script>");
    expect(ratesSampleMarkdown("", {}, "", "bad")).toContain("待填写有效日期");
  });
  it("keeps gated rows missing rather than zero, without accepting arbitrary task IDs", () => {
    const output = creditSampleMarkdown(["DEMO-CREDIT-B", "unknown-private-id"]);
    expect(output).toContain("100.00 BP");
    expect(output).toContain("—（缺失不是 0）");
    expect(output).toContain("- [ ] 合成样例乙券");
    expect(output).not.toContain("- [ ] 合成样例甲券");
    expect(output).not.toContain("unknown-private-id");
    expect(creditSampleMarkdown([])).toContain("没有选择不表示无需复核");
  });
  it("exports an importable fixed CSV with explicit fictional provenance and missing rating", () => {
    const csv = creditSampleCsv();
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv.split("\r\n")).toHaveLength(4);
    expect(csv).toContain('"bond_code","bond_name","issuer"');
    expect(csv).toContain('"DEMO-CREDIT-B"');
    expect(csv).toContain('"","2026-07-01"');
    expect(CREDIT_SAMPLE.items.every(item => item.observation.source_note.includes("合成样例"))).toBe(true);
  });
});
