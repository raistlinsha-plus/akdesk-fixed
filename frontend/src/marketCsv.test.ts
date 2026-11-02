import { describe, expect, it } from "vitest";
import { buildMarketCsv } from "./marketCsv";
import { DATA_USAGE_NOTICE } from "./dataUsage";

describe("market CSV provenance", () => {
  it("retains source, timestamps, state and usage boundary on every data row", () => {
    const text = buildMarketCsv(["名称", "价格"], [["示例", 0]], {
      source: "合成示例", source_url: "https://example.com/?token=private", fetched_at: "2026-11-02T10:00:00", observation_time: "2026-11-02", demo: true,
    } as import("./types").SourceMeta);
    expect(text).toContain("数据来源");
    expect(text).toContain('"示例","0","合成示例","https://example.com/"');
    expect(text).toContain("合成示例·非实时");
    expect(text).toContain(DATA_USAGE_NOTICE);
    expect(text).not.toContain("private");
  });
  it("escapes spreadsheet formula strings without altering numeric negatives", () => {
    const text = buildMarketCsv(["名称", "变动"], [['=HYPERLINK("bad")', -1.5]]);
    expect(text).toContain('"\'=HYPERLINK(""bad"")","-1.5"');
    expect(text).toContain("来源待核验");
  });
});
