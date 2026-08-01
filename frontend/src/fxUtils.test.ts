import { describe, expect, it } from "vitest";
import {
  filterFxPairs,
  fxQuoteDigits,
  fxReferenceLabel,
  sortFxPairs,
} from "./fxUtils";
import type { FxPairQuote, FxRmbReference } from "./types";

const rows: FxPairQuote[] = [
  {
    code: "USDCHF",
    pair: "USD/CHF",
    name: "美元/瑞郎",
    bid: 0.8,
    ask: 0.81,
    mid: 0.805,
    spread_pips: 100,
    change_pct: null,
  },
  {
    code: "EURUSD",
    pair: "EUR/USD",
    name: "欧元/美元",
    bid: 1.1,
    ask: 1.11,
    mid: 1.105,
    spread_pips: 100,
    change_pct: null,
  },
];

describe("FX presentation", () => {
  it("keeps core pairs ahead of the remaining market", () => {
    expect(sortFxPairs(rows).map((item) => item.code)).toEqual([
      "EURUSD",
      "USDCHF",
    ]);
  });

  it("matches codes, slash pairs and Chinese names", () => {
    expect(filterFxPairs(rows, "EUR/USD")).toHaveLength(1);
    expect(filterFxPairs(rows, "瑞郎")[0].code).toBe("USDCHF");
  });

  it("uses suitable quote precision and display basis", () => {
    expect(fxQuoteDigits("USDJPY")).toBe(3);
    expect(fxQuoteDigits("EURUSD")).toBe(5);
    expect(
      fxReferenceLabel({
        code: "JPYCNY",
        name: "日元/人民币",
        base: "JPY",
        quote: "CNY",
        display_basis: 100,
        mid: 4.18,
        bid: 4.17,
        ask: 4.19,
        change_pct: 0.1,
        observation_date: "2026-07-16",
        reference_type: "央行中间价",
        history: [],
      } satisfies FxRmbReference),
    ).toBe("100 JPY");
  });
});

