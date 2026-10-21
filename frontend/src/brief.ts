import type { DailyReport } from "./types";

export type BriefMode = "example" | "live" | "mixed" | "unknown";

export interface BriefSource {
  adapter: string;
  label: string;
  source: string;
  sourceUrl?: string | null;
  observationTime?: string | null;
  fetchedAt?: string | null;
  dataState: string;
  trustLevel: string;
  demo: boolean | null;
}

export interface BriefDocument {
  date: string;
  generatedAt: string;
  marketStatus: string;
  headline: string;
  mode: BriefMode;
  funding: {
    tone: string;
    averageChangeBp: number | null;
    items: Array<{ name: string; value: number | null; changeBp: number | null }>;
  };
  curve: {
    tenYear: number | null;
    tenYearChangeBp: number | null;
    spreadsBp: Record<string, number | null>;
  };
  futures: Array<{
    product: string;
    contract: string;
    price: number | null;
    changePct: number | null;
  }>;
  sources: BriefSource[];
  notes: string[];
}

function finite(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** A sample source always takes precedence over a caller's mode label. */
export function briefMode(document: BriefDocument): BriefMode {
  const sample = document.sources.some((source) => source.demo === true || source.dataState === "demo");
  const real = document.sources.some(
    (source) => source.demo === false && !["unavailable", "demo"].includes(source.dataState),
  );
  if (document.mode === "mixed" || (sample && real)) return "mixed";
  if (document.mode === "example" || sample) return "example";
  if (document.mode === "live" && real) return "live";
  return "unknown";
}

export function briefModeLabel(mode: BriefMode): string {
  return {
    example: "示例数据 · 非实时",
    mixed: "含示例数据 · 不作为真实市场简报",
    live: "真实数据 · 请核对各来源时点",
    unknown: "来源信息不完整 · 待核验",
  }[mode];
}

export function briefSourceState(source: BriefSource): string {
  if (source.demo === true || source.dataState === "demo") return "示例 · 非实时";
  const state: Record<string, string> = {
    live: "最新请求",
    latest: "最近快照",
    cached: "缓存",
    stale: "过期缓存",
    unavailable: "不可用",
  };
  const trust: Record<string, string> = {
    trusted: "已通过质量门禁",
    partial: "部分可用",
    suspicious: "需核验异常",
    unavailable: "不可用于研究",
  };
  return `${state[source.dataState] ?? "状态未知"} · ${trust[source.trustLevel] ?? "待核验"}`;
}

export function briefNumber(
  value: number | null | undefined,
  digits = 2,
  suffix = "",
  signed = false,
): string {
  const number = finite(value);
  if (number === null) return "—";
  return `${signed && number > 0 ? "+" : ""}${number.toFixed(digits)}${suffix}`;
}

/** Preserve the supplied timestamp rather than silently changing time zones. */
export function briefTime(value: string | null | undefined): string {
  if (!value) return "未提供";
  return value.replace("T", " ").replace(/\.\d+(?=Z|[+-]\d{2}:?\d{2}|$)/, "");
}

export function briefObservationRange(document: BriefDocument): string {
  const dates = [...new Set(document.sources.flatMap((source) => {
    const date = source.observationTime?.slice(0, 10);
    return date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? [date] : [];
  }))].sort();
  if (!dates.length) return "未提供，待核验";
  return dates.length === 1 ? dates[0] : `${dates[0]} 至 ${dates[dates.length - 1]}`;
}

export function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    // Provenance links do not need query parameters that might carry credentials.
    url.search = "";
    url.hash = "";
    return url.href;
  } catch {
    return null;
  }
}

export function reportToBrief(report: DailyReport): BriefDocument {
  const sources: BriefSource[] = (report.data_sources ?? []).map((source) => ({
    adapter: source.adapter,
    label: source.label,
    source: source.source || "尚未取得来源数据",
    sourceUrl: safeSourceUrl(source.source_url),
    observationTime: source.observation_time,
    fetchedAt: source.fetched_at,
    dataState: source.data_state,
    trustLevel: source.trust_level,
    demo: source.demo,
  }));
  const hasSample = sources.some((source) => source.demo === true || source.dataState === "demo");
  const hasReal = sources.some((source) => source.demo === false && !["unavailable", "demo"].includes(source.dataState));
  const mode: BriefMode = hasSample ? (hasReal ? "mixed" : "example") : hasReal ? "live" : "unknown";
  const notes = [...report.data_notes];
  if (!sources.length) notes.unshift("该历史归档没有逐源出处信息，请重新生成当日简报后核验。");
  if (finite(report.curve.tenors["10Y"]) === null) notes.push("10Y 国债收益率缺失，长端变化暂不判断。");
  if (finite(report.curve.ten_year_change_bp) === null) notes.push("10Y 国债日变动缺失，方向暂不判断。");
  if (finite(report.funding.average_change_bp) === null) notes.push("资金利率变动缺失，资金方向暂不判断。");
  if (!report.futures.length) notes.push("国债期货数据缺失，请在数据健康中检查来源。");
  const fundingMissing = finite(report.funding.average_change_bp) === null;
  const curveMissing = finite(report.curve.tenors["10Y"]) === null || finite(report.curve.ten_year_change_bp) === null;
  const curveChange = finite(report.curve.ten_year_change_bp);
  const headline = fundingMissing || curveMissing
    ? `${fundingMissing ? "资金面变动待核验" : `资金面${report.funding.tone}`}，${curveMissing ? "长端变动待核验" : (curveChange ?? 0) > 0.5 ? "长端收益率上行" : (curveChange ?? 0) < -0.5 ? "长端收益率下行" : "长端窄幅波动"}`
    : report.headline;
  return {
    date: report.report_date,
    generatedAt: report.generated_at,
    marketStatus: report.market_status,
    headline,
    mode,
    funding: {
      tone: finite(report.funding.average_change_bp) === null ? "待核验" : report.funding.tone,
      averageChangeBp: finite(report.funding.average_change_bp),
      items: report.funding.items.map((item) => ({
        name: item.name,
        value: finite(item.value),
        changeBp: finite(item.change_bp),
      })),
    },
    curve: {
      tenYear: finite(report.curve.tenors["10Y"]),
      tenYearChangeBp: finite(report.curve.ten_year_change_bp),
      spreadsBp: Object.fromEntries(
        Object.entries(report.curve.spreads_bp).map(([key, value]) => [key, finite(value)]),
      ),
    },
    futures: report.futures.map((item) => ({
      product: item.product,
      contract: item.contract,
      price: finite(item.price),
      changePct: finite(item.change_pct),
    })),
    sources,
    notes: [...new Set(notes)],
  };
}

function markdownText(value: string): string {
  return value.replace(/\r/g, "").replace(/([\\`*_[\]<>|])/g, "\\$1");
}

export function briefMarkdown(document: BriefDocument, notes = ""): string {
  const mode = briefMode(document);
  const lines = [
    `# AKDesk 一页固收简报${mode === "example" || mode === "mixed" ? "（示例）" : ""} · ${document.date}`,
    "",
    `> ${briefModeLabel(mode)}`,
    `> ${markdownText(document.headline)}`,
    `> 市场状态：${markdownText(document.marketStatus)}；生成时间：${briefTime(document.generatedAt)}`,
    `> 观测区间：${briefObservationRange(document)}（按各来源观测日期汇总）`,
    "",
    "## 资金面",
    "",
    `- 观察：${markdownText(document.funding.tone)}`,
    `- 平均变动：${briefNumber(document.funding.averageChangeBp, 2, " BP", true)}`,
    ...document.funding.items.map((item) => `- ${markdownText(item.name)}：${briefNumber(item.value, 4, "%")}；变动 ${briefNumber(item.changeBp, 2, " BP", true)}`),
    "",
    "## 收益率曲线",
    "",
    `- 10Y 国债：${briefNumber(document.curve.tenYear, 4, "%")}`,
    `- 10Y 日变动：${briefNumber(document.curve.tenYearChangeBp, 2, " BP", true)}`,
    ...["10Y-1Y", "10Y-5Y", "30Y-10Y"].map((key) => `- ${key} 利差：${briefNumber(document.curve.spreadsBp[key], 2, " BP")}`),
    "",
    "## 国债期货",
    "",
    ...(document.futures.length ? document.futures.map((item) => `- ${markdownText(item.product)} / ${markdownText(item.contract)}：${briefNumber(item.price, 3)}；日变动 ${briefNumber(item.changePct, 3, "%", true)}`) : ["- 暂无可用数据"]),
    "",
    "## 待核验事项与数据缺口",
    "",
    ...(document.notes.length ? document.notes.map((note) => `- ${markdownText(note)}`) : ["- 暂无额外缺口；使用前仍需核对来源与时点。"]),
    "",
    "## 来源与时点",
    "",
    ...(document.sources.length ? document.sources.map((source) => {
      const url = safeSourceUrl(source.sourceUrl);
      return `- ${markdownText(source.label)}：${markdownText(source.source)}${url ? `（${url}）` : ""}；观测 ${briefTime(source.observationTime)}；抓取 ${briefTime(source.fetchedAt)}；${briefSourceState(source)}`;
    }) : ["- 未提供逐源出处，当前简报待核验。"]),
  ];
  if (notes.trim()) lines.push("", "## 人工备注", "", markdownText(notes.trim()));
  lines.push("", "仅供个人研究参考，不构成投资建议。", "");
  return lines.join("\n");
}

export function downloadBrief(document: BriefDocument, notes = ""): void {
  const blob = new Blob([briefMarkdown(document, notes)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = `AKDesk-${briefMode(document) === "example" || briefMode(document) === "mixed" ? "示例-" : ""}固收简报-${document.date}.md`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function printBriefElement(element: HTMLElement): void {
  const ancestors: HTMLElement[] = [];
  let parent = element.parentElement;
  while (parent && parent !== window.document.body) {
    ancestors.push(parent);
    parent.classList.add("ak-brief-print-ancestor");
    parent = parent.parentElement;
  }
  element.classList.add("ak-brief-print-target");
  window.document.body.dataset.akdeskBriefPrint = "true";
  const cleanup = () => {
    element.classList.remove("ak-brief-print-target");
    for (const ancestor of ancestors) ancestor.classList.remove("ak-brief-print-ancestor");
    delete window.document.body.dataset.akdeskBriefPrint;
  };
  window.addEventListener("afterprint", cleanup, { once: true });
  try {
    window.print();
  } catch {
    cleanup();
  }
}
