import type {
  Dataset,
  MacroChartData,
  MarketResearchSignal,
  ResearchStatus,
} from "./types";

export function actionableMarketSignalIds(
  signals: MarketResearchSignal[],
): string[] {
  return signals
    .filter((signal) => signal.actionable && !signal.demo && signal.quality_score >= 60)
    .map((signal) => signal.id)
    .slice(0, 20);
}

export function parseResearchTags(value: string): string[] {
  return Array.from(
    new Set(value.split(/[，,]/).map((item) => item.trim()).filter(Boolean)),
  ).slice(0, 30);
}

export function isReviewDue(
  nextReviewDate: string | null | undefined,
  status: ResearchStatus,
  today: string,
): boolean {
  return status !== "archived" && Boolean(nextReviewDate && nextReviewDate <= today);
}

export function shanghaiDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function buildChartEvidence(
  chart: Dataset<MacroChartData>,
  seriesIds: string[],
  title: string,
  capturedAt = new Date().toISOString(),
) {
  return {
    evidence_type: "chart" as const,
    title,
    payload: {
      schema_version: 2,
      storage_mode: "reference_only",
      provider: "FRED",
      frozen: false,
      captured_at: capturedAt,
      series: chart.data.series.map((item) => ({
        series_id: item.key,
        name: item.name,
        units: item.units,
        frequency: item.frequency,
        attribution: item.attribution,
        source_url: item.source_url,
        source_organization: item.source_organization,
        original_source_url: item.original_source_url,
        last_updated: item.last_updated,
      })),
      transform: chart.data.transform,
      transform_source: chart.data.transform_source,
      years: chart.data.years,
      terms_url: chart.data.terms_url,
      notice: "FRED 证据只保存序列与变换引用；重新打开时会实时获取当前版本。",
    },
    source_summary: "FRED · " + seriesIds.join(", "),
    observation_start: chart.data.dates[0] || null,
    observation_end: chart.data.dates[chart.data.dates.length - 1] || null,
  };
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

export function buildMacroCsv(chart: Dataset<MacroChartData>): string {
  const rows: unknown[][] = [
    ["# AKDesk Fixed FRED personal research export"],
    ["# generated_at", chart.meta.fetched_at],
    ["# transform", chart.data.transform],
    ["# transform_source", chart.data.transform_source],
    ["# storage_mode", "user_requested_export"],
    ["# notice", "Uses the FRED API; not endorsed or certified by the Federal Reserve Bank of St. Louis."],
    ["# terms", chart.data.terms_url],
  ];
  chart.data.series.forEach((item) => {
    rows.push([
      "# series",
      item.key,
      item.name,
      item.units || "",
      item.frequency || "",
      item.source_organization || "",
      item.attribution || "",
      item.source_url || "",
      item.original_source_url || "",
      item.last_updated || "",
      item.fetched_at || "",
    ]);
  });
  rows.push([
    "date",
    ...chart.data.series.flatMap((item) => [
      item.key,
      `${item.key}_realtime_start`,
      `${item.key}_realtime_end`,
    ]),
  ]);
  chart.data.dates.forEach((observed, index) => {
    rows.push([
      observed,
      ...chart.data.series.flatMap((item) => [
        item.values[index] ?? "",
        item.realtime_start?.[index] ?? "",
        item.realtime_end?.[index] ?? "",
      ]),
    ]);
  });
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
