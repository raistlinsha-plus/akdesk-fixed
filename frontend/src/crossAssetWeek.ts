import { apiGet } from "./api";
import type { CrossHistory } from "./crossAssets";
import { shanghaiDate } from "./researchUtils";
import type { HistoryResponse } from "./types";

const DAY = 86_400_000;
export const SAMPLE_END = "2026-07-31";
export const WEEK_NOTE_LIMIT = 2000;

export const WEEK_SERIES = [
  {
    id: "stock", label: "股", name: "沪深300指数", unit: "点", changeUnit: "%",
    method: "指数价格变化，不含总回报", asset: "CSI:000300", page: "cross-assets",
    source: "新浪日线 / AKShare", url: "https://finance.sina.com.cn/",
  },
  {
    id: "bond", label: "债", name: "10年期国债收益率", unit: "%", changeUnit: "BP",
    method: "收益率之差，1 个百分点 = 100 BP；不是债券价格回报", page: "curves",
    adapter: "yield_curves", metric: "yield", series: "10Y",
    source: "AKDesk 本地曲线历史 / 中债", url: "https://www.chinabond.com.cn/",
  },
  {
    id: "gold", label: "金", name: "黄金 Au99.99", unit: "元/克", changeUnit: "%",
    method: "交易所现货价格变化，不是黄金 ETF 回报", asset: "SGE:Au99.99", page: "cross-assets",
    source: "上金所日线 / AKShare", url: "https://www.sge.com.cn/sjzx/mrhq",
  },
  {
    id: "fx", label: "汇", name: "美元兑人民币参考中间价", unit: "元/美元", changeUnit: "%",
    method: "人民币/美元报价变化；正值表示每美元对应更多人民币，不是成交回报", page: "fx",
    adapter: "fx_rmb_reference", metric: "mid", series: "USDCNY",
    source: "AKDesk 本地人民币参考价历史 / AKShare", url: "https://www.chinamoney.com.cn/",
  },
] as const;

export type WeekSeries = typeof WEEK_SERIES[number];
export type WeekSeriesId = WeekSeries["id"];
export type WeekPoint = { date: string; value: number };
export type WeekResult = {
  state: "latest" | "cached" | "stale" | "local" | "sample" | "demo-only" | "unavailable" | "failed" | "not-read";
  points: WeekPoint[];
};
export type WeekRows = Record<WeekSeriesId, WeekResult>;
export type WeekDraft = { date: string; notes: Record<string, string>; reviewedSource?: WeekSeriesId };

export function validWeekDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const stamp = Date.parse(value + "T00:00:00Z");
  return Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 10) === value;
}

export function shiftWeekDate(date: string, days: number) {
  return new Date(Date.parse(date + "T00:00:00Z") + days * DAY).toISOString().slice(0, 10);
}

export function lastCompletedFriday(today = shanghaiDate()) {
  const weekday = new Date(today + "T00:00:00Z").getUTCDay();
  return shiftWeekDate(today, -((weekday + 2) % 7 || 7));
}

export function weeklyWindow(end: string) {
  return { start: shiftWeekDate(end, -6), previousStart: shiftWeekDate(end, -13), previousEnd: shiftWeekDate(end, -7) };
}

export function weeklyChange(spec: WeekSeries, points: WeekPoint[], end: string) {
  const { start, previousStart, previousEnd } = weeklyWindow(end);
  // Reject ambiguous duplicate dates; never pick an arbitrary conflicting value.
  const unique = new Map<string, WeekPoint>();
  const duplicates = new Set<string>();
  for (const point of points) {
    if (typeof point?.date !== "string" || point.date < previousStart || point.date > end || !validWeekDate(point.date) ||
        !Number.isFinite(point.value) || (spec.id !== "bond" && point.value <= 0)) continue;
    const known = unique.get(point.date);
    if (known && known.value !== point.value) duplicates.add(point.date);
    unique.set(point.date, point);
  }
  const valid = [...unique.values()].filter(point => !duplicates.has(point.date))
    .sort((a, b) => b.date.localeCompare(a.date));
  const previous = valid.find(point => point.date >= previousStart && point.date <= previousEnd);
  const current = valid.find(point => point.date >= start && point.date <= end);
  const diff = previous && current
    ? (spec.id === "bond" ? current.value - previous.value : current.value / previous.value - 1) * 100
    : null;
  return { previous, current, change: diff !== null && Number.isFinite(diff) ? diff : null };
}

export async function readWeekSeries(spec: WeekSeries, signal: AbortSignal): Promise<WeekResult> {
  if ("asset" in spec) {
    const response = await apiGet<CrossHistory>(`/cross-assets/history?asset_id=${encodeURIComponent(spec.asset)}`, { signal });
    if (response.asset?.id === spec.asset && response.demo === true) return { state: "demo-only", points: [] };
    if (response.asset?.id !== spec.asset || response.demo !== false ||
        !["latest", "cached", "stale"].includes(response.state)) {
      return { state: "unavailable", points: [] };
    }
    return {
      state: response.state as "latest" | "cached" | "stale",
      points: response.data.map(row => ({ date: row.date, value: row.close })),
    };
  }
  const response = await apiGet<HistoryResponse>(`/history?adapter=${spec.adapter}&metric=${spec.metric}&series=${spec.series}&days=110`, { signal });
  if (response.adapter !== spec.adapter || response.metric !== spec.metric) return { state: "unavailable", points: [] };
  const series = response.series.find(row => row.key === spec.series);
  return {
    state: "local",
    points: response.dates.flatMap((date, index) => {
      const value = series?.values[index];
      return typeof value === "number" ? [{ date, value }] : [];
    }),
  };
}

export const SAMPLE_WEEK: WeekRows = {
  stock: { state: "sample", points: [{ date: "2026-07-24", value: 4000 }, { date: "2026-07-31", value: 4040 }] },
  bond: { state: "sample", points: [{ date: "2026-07-24", value: 1.85 }, { date: "2026-07-31", value: 1.82 }] },
  gold: { state: "sample", points: [{ date: "2026-07-24", value: 780 }, { date: "2026-07-30", value: 787.8 }] },
  fx: { state: "sample", points: [{ date: "2026-07-30", value: 7 }] },
};

export function formatWeekChange(value: number | null, unit: string) {
  if (value === null) return "—";
  const rounded = Number(value.toFixed(2));
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(2)}${unit === "%" ? "%" : " BP"}`;
}

export function weekMarkdown(end: string, rows: Partial<WeekRows>, note: string, sample: boolean) {
  const { start } = weeklyWindow(end);
  const text = note.trim().slice(0, WEEK_NOTE_LIMIT).replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replace(/[\\`*_{}[\]()#!|]/g, "\\$&")
    .split(/\r\n|\n|\r/).map(line => `> ${line}`).join("\n");
  return [
    "# AKDesk · 股债金汇周复盘", "",
    sample ? "**固定合成样例 · 非真实行情**" : "查询引用版 · 不包含行情数值、派生变化、观测日期或行情快照。", "",
    `用户选择的复盘区间：${start} 至 ${end}。`, "",
    ...WEEK_SERIES.map(spec => {
      const result = rows[spec.id];
      if (sample) {
        const change = weeklyChange(spec, result?.state === "sample" ? result.points : [], end);
        return `- ${spec.name}：${change.change === null ? "区间观测不足" : formatWeekChange(change.change, spec.changeUnit)}（合成；${spec.method}）`;
      }
      return `- ${spec.name}：[${spec.source}](${spec.url})；${spec.method}。`;
    }),
    "", "## 我的判断与下周待核验事项", text || "> 尚未填写", "",
    "各资产按独立观测区间计算，不合成总分、组合回报或因果判断。不调用 AI，不自动保存至项目；非投资建议。", "",
  ].join("\n");
}
