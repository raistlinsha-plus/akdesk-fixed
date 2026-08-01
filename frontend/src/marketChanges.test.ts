import { describe, expect, it } from "vitest";
import type { MarketResearchBrief, MarketResearchSignal } from "./types";
import {
  changedSignalIds,
  filterMarketSignals,
  parseMarketChangeFilters,
  snapshotFromBrief,
} from "./marketChanges";

function signal(
  id: string,
  overrides: Partial<MarketResearchSignal> = {},
): MarketResearchSignal {
  return {
    id,
    category: "curve",
    severity: "info",
    direction: "neutral",
    title: id,
    summary: id,
    value: 1,
    unit: "BP",
    adapter: "yield_curves",
    source: "test",
    fetched_at: "2026-07-28T09:00:00+08:00",
    trust_level: "trusted",
    quality_score: 90,
    data_state: "latest",
    demo: false,
    actionable: true,
    trigger_reason: "test",
    ...overrides,
  };
}

function brief(signals: MarketResearchSignal[]): MarketResearchBrief {
  return {
    generated_at: "2026-07-28T09:00:00+08:00",
    market_status: "交易中",
    headline: "test",
    signals,
    sources: [],
    eligible_signal_ids: signals.filter((item) => item.actionable).map((item) => item.id),
    snapshot_eligible: true,
    notice: "test",
    settings: {
      funding_change_bp: 1,
      curve_change_bp: 1,
      curve_spread_bp: 1,
      futures_change_pct: 1,
      bond_change_bp: 1,
    },
  };
}

describe("market change center", () => {
  it("finds new or materially changed signals since the saved visit", () => {
    const before = brief([signal("a"), signal("b")]);
    const after = brief([signal("a"), signal("b", { value: 2 }), signal("c")]);
    expect([...changedSignalIds(after, snapshotFromBrief(before))]).toEqual(["b", "c"]);
  });

  it("repairs filters and orders trustworthy severe changes first", () => {
    const filters = parseMarketChangeFilters(
      '{"actionableOnly":false,"minQuality":70,"severities":["watch","high","bad"]}',
    );
    const values = filterMarketSignals([
      signal("info"),
      signal("watch", { severity: "watch", quality_score: 85 }),
      signal("high", { severity: "high", quality_score: 80 }),
      signal("low", { severity: "high", quality_score: 40 }),
    ], filters);
    expect(values.map((item) => item.id)).toEqual(["high", "watch"]);
  });
});

