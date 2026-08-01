import type { FxPairQuote, FxRmbReference } from "./types";

const CORE_PAIR_ORDER = [
  "EURUSD",
  "USDJPY",
  "GBPUSD",
  "AUDUSD",
  "USDHKD",
  "USDSGD",
];

export function fxQuoteDigits(code: string): number {
  return code.endsWith("JPY") || code.startsWith("JPY") ? 3 : 5;
}

export function sortFxPairs(rows: FxPairQuote[]): FxPairQuote[] {
  const priority = new Map(
    CORE_PAIR_ORDER.map((code, index) => [code, index]),
  );
  return [...rows].sort(
    (left, right) =>
      (priority.get(left.code) ?? 100) -
        (priority.get(right.code) ?? 100) ||
      left.code.localeCompare(right.code),
  );
}

export function filterFxPairs(
  rows: FxPairQuote[],
  query: string,
): FxPairQuote[] {
  const term = query.trim().toLowerCase().replace("/", "");
  if (!term) return sortFxPairs(rows);
  return sortFxPairs(rows).filter((item) =>
    `${item.code} ${item.pair} ${item.name}`
      .toLowerCase()
      .replace("/", "")
      .includes(term),
  );
}

export function fxReferenceLabel(item: FxRmbReference): string {
  return `${item.display_basis} ${item.base}`;
}

