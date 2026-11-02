import { safeSourceUrl } from "./brief";
import { DATA_USAGE_NOTICE } from "./dataUsage";
import type { SourceMeta } from "./types";

function escapeCsv(value: unknown): string {
  let text = String(value ?? "");
  if (typeof value === "string" && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildMarketCsv(headers: string[], rows: unknown[][], meta?: SourceMeta): string {
  const provenance = [
    meta?.source ?? "来源待核验",
    safeSourceUrl(meta?.source_url) ?? "",
    meta?.observation_time ?? "未提供",
    meta?.fetched_at ?? "未提供",
    meta?.demo ? "合成示例·非实时" : meta?.data_state ?? "unknown",
    DATA_USAGE_NOTICE,
  ];
  return "\uFEFF" + [
    [...headers, "数据来源", "来源链接", "观测时间", "抓取时间", "数据状态", "使用边界"],
    ...rows.map((row) => [...row, ...provenance]),
  ].map((row) => row.map(escapeCsv).join(",")).join("\r\n");
}
