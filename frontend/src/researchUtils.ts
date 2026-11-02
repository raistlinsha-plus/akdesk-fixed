import type {
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

export interface FredChartQuery {
  seriesIds: string[];
  years: number;
  transform: MacroChartData["transform"];
}

const fredTermsUrl = "https://fred.stlouisfed.org/legal/terms/";
const fredReferenceNotice = "仅保存用户选择的查询参数与应用生成的链接，不保存 FRED 返回的数值、元数据或观测区间。";

export function buildChartEvidence(
  query: FredChartQuery,
  title: string,
  capturedAt = new Date().toISOString(),
) {
  const seriesIds = [...new Set(query.seriesIds.map((id) => id.trim().toUpperCase()))];
  if (!seriesIds.length || seriesIds.length > 6 || seriesIds.some((id) => !/^[A-Z0-9][A-Z0-9._-]{0,39}$/.test(id))) {
    throw new Error("FRED 引用序列标识无效");
  }
  if (!Number.isInteger(query.years) || query.years < 1 || query.years > 50) {
    throw new Error("FRED 引用年份范围无效");
  }
  return {
    evidence_type: "chart" as const,
    title,
    payload: {
      schema_version: 3,
      storage_mode: "reference_only",
      provider: "FRED",
      frozen: false,
      captured_at: capturedAt,
      series: seriesIds.map((id) => ({
        series_id: id,
        source_url: `https://fred.stlouisfed.org/series/${id}`,
      })),
      transform: query.transform,
      years: query.years,
      terms_url: fredTermsUrl,
      notice: fredReferenceNotice,
    },
    source_summary: "FRED · " + seriesIds.join(", "),
    observation_start: null,
    observation_end: null,
  };
}

export function buildMacroReferenceMarkdown(
  query: FredChartQuery,
  capturedAt = new Date().toISOString(),
): string {
  const reference = buildChartEvidence(query, "FRED 查询引用", capturedAt).payload;
  return [
    "# AKDesk Fixed · FRED 查询引用",
    "",
    `- 用户选择的时间范围：最近 ${reference.years} 年`,
    `- 用户选择的变换：${reference.transform}`,
    `- 本地记录时间：${reference.captured_at}`,
    `- [FRED 使用条款](${fredTermsUrl})`,
    "",
    "## 序列链接",
    ...reference.series.map((item) => `- [${item.series_id}](${item.source_url})`),
    "",
    fredReferenceNotice,
    "这不是数据快照；重新查询可能得到修订后的版本。不得把 FRED 内容粘贴进 AI 请求。",
    "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.",
    "",
  ].join("\n");
}
