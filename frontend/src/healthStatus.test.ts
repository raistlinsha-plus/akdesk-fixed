import { describe, expect, it } from "vitest";
import { marketSessionLabel, researchAvailability } from "./healthStatus";
import type { HealthItem } from "./types";

function health(
  marketStatus: HealthItem["market_status"],
  researchStatus: HealthItem["research_status"] = "ready",
  adapter = "test",
): HealthItem {
  return {
    adapter,
    label: "测试源",
    state: "healthy",
    rows: 1,
    consecutive_failures: 0,
    cache_persisted: false,
    market_status: marketStatus,
    market_status_label: "测试",
    quality_score: 100,
    quality_issues: [],
    trust_level: "trusted",
    suspicious_rows: 0,
    execution_mode: "isolated_process",
    refreshing: false,
    circuit_state: "closed",
    research_status: researchStatus,
  };
}

describe("health presentation", () => {
  it("distinguishes research availability from connection health", () => {
    expect(
      researchAvailability([
        health("daily", "ready"),
        health("daily", "limited"),
        health("daily", "blocked"),
        health("daily", "unchecked"),
      ]),
    ).toEqual({ ready: 1, limited: 1, blocked: 1, unchecked: 1 });
  });

  it("labels pre-open and lunch break without calling them closed", () => {
    expect(marketSessionLabel([health("pre_open")], "market")).toBe("主要市场未开盘");
    expect(marketSessionLabel([health("session_break")], "market")).toBe("主要市场午间休市");
  });

  it("uses provider cadence on macro pages", () => {
    expect(marketSessionLabel([health("closed")], "macro")).toBe("宏观数据按发布更新");
    expect(marketSessionLabel([health("closed")], "sovereign")).toBe("宏观数据按发布更新");
  });

  it("keeps the global FX session separate from the domestic market clock", () => {
    expect(
      marketSessionLabel(
        [health("closed"), health("trading", "limited", "fx_pairs")],
        "dashboard",
      ),
    ).toBe("主要市场已收盘");
    expect(
      marketSessionLabel([health("trading", "limited", "fx_pairs")], "fx"),
    ).toBe("全球外汇交易中");
  });
});
