import type { MarketResearchBrief, MarketResearchSignal } from "./types";

export const MARKET_CHANGE_SNAPSHOT_KEY = "akdesk.market-changes.snapshot.v1";
export const MARKET_CHANGE_FILTER_KEY = "akdesk.market-changes.filters.v1";

export interface MarketChangeSnapshot {
  capturedAt: string;
  signals: Record<string, string>;
}

export interface MarketChangeFilters {
  actionableOnly: boolean;
  minQuality: number;
  severities: Array<MarketResearchSignal["severity"]>;
}

export const DEFAULT_MARKET_CHANGE_FILTERS: MarketChangeFilters = {
  actionableOnly: true,
  minQuality: 60,
  severities: ["high", "watch", "info"],
};

export function signalFingerprint(signal: MarketResearchSignal): string {
  return JSON.stringify([
    signal.value,
    signal.direction,
    signal.severity,
    signal.data_state,
    signal.trust_level,
    signal.quality_score,
  ]);
}

export function snapshotFromBrief(brief: MarketResearchBrief): MarketChangeSnapshot {
  return {
    capturedAt: brief.generated_at,
    signals: Object.fromEntries(
      brief.signals.map((signal) => [signal.id, signalFingerprint(signal)]),
    ),
  };
}

export function parseMarketChangeSnapshot(raw: string | null): MarketChangeSnapshot | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed !== "object" ||
      !("capturedAt" in parsed) ||
      typeof parsed.capturedAt !== "string" ||
      !("signals" in parsed) ||
      !parsed.signals ||
      typeof parsed.signals !== "object"
    ) return null;
    return parsed as MarketChangeSnapshot;
  } catch {
    return null;
  }
}

export function changedSignalIds(
  brief: MarketResearchBrief,
  snapshot: MarketChangeSnapshot | null,
): Set<string> {
  if (!snapshot) return new Set(brief.signals.map((signal) => signal.id));
  return new Set(
    brief.signals
      .filter((signal) => snapshot.signals[signal.id] !== signalFingerprint(signal))
      .map((signal) => signal.id),
  );
}

export function parseMarketChangeFilters(raw: string | null): MarketChangeFilters {
  if (!raw) return DEFAULT_MARKET_CHANGE_FILTERS;
  try {
    const parsed = JSON.parse(raw) as Partial<MarketChangeFilters>;
    const severities = Array.isArray(parsed.severities)
      ? parsed.severities.filter(
        (item): item is MarketResearchSignal["severity"] =>
          item === "high" || item === "watch" || item === "info",
      )
      : DEFAULT_MARKET_CHANGE_FILTERS.severities;
    return {
      actionableOnly: parsed.actionableOnly !== false,
      minQuality:
        typeof parsed.minQuality === "number" && parsed.minQuality >= 0 && parsed.minQuality <= 100
          ? parsed.minQuality
          : DEFAULT_MARKET_CHANGE_FILTERS.minQuality,
      severities: severities.length ? Array.from(new Set(severities)) : [],
    };
  } catch {
    return DEFAULT_MARKET_CHANGE_FILTERS;
  }
}

export function filterMarketSignals(
  signals: MarketResearchSignal[],
  filters: MarketChangeFilters,
): MarketResearchSignal[] {
  const severityOrder = { high: 0, watch: 1, info: 2 };
  return signals
    .filter((signal) => !filters.actionableOnly || signal.actionable)
    .filter((signal) => signal.quality_score >= filters.minQuality)
    .filter((signal) => filters.severities.includes(signal.severity))
    .sort((left, right) =>
      Number(right.actionable) - Number(left.actionable)
      || severityOrder[left.severity] - severityOrder[right.severity]
      || right.quality_score - left.quality_score
      || left.id.localeCompare(right.id),
    );
}

export function marketTaskCopy(marketStatus: string): string {
  if (marketStatus.includes("交易中")) return "先看高优先级异动，再核对来源时点与质量。";
  if (marketStatus.includes("休市") || marketStatus.includes("收盘")) {
    return "适合做收盘确认：保存可信变化，补充反证并安排下一交易日任务。";
  }
  return "先确认数据状态与观测时间，再决定是否写入研究证据。";
}

