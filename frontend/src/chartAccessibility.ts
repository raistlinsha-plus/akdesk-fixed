import type { CurveSeries } from "./types";

export interface LineChartSummaryRow {
  name: string;
  firstDate: string;
  firstValue: number;
  latestDate: string;
  latestValue: number;
  change: number;
  direction: "上升" | "下降" | "持平";
}

export function lineChartPrecision(series: CurveSeries[]): number {
  const values = series.flatMap((item) =>
    item.values.filter(
      (value): value is number => typeof value === "number" && Number.isFinite(value),
    ),
  );
  if (!values.length) return 2;
  const range = Math.max(...values) - Math.min(...values);
  if (range === 0) {
    const magnitude = Math.abs(values[0]);
    return magnitude < 0.1 ? 5 : magnitude < 1 ? 4 : magnitude < 10 ? 3 : 2;
  }
  const approximateTick = range / 5;
  if (approximateTick >= 10) return 0;
  if (approximateTick >= 1) return 1;
  if (approximateTick >= 0.1) return 2;
  if (approximateTick >= 0.01) return 3;
  if (approximateTick >= 0.001) return 4;
  return 5;
}

export function summarizeLineChart(
  categories: string[],
  series: CurveSeries[],
): LineChartSummaryRow[] {
  return series.flatMap((item) => {
    const points = item.values.flatMap((value, index) =>
      typeof value === "number" && Number.isFinite(value)
        ? [{ index, value }]
        : [],
    );
    if (!points.length) return [];
    const first = points[0];
    const latest = points[points.length - 1];
    const change = latest.value - first.value;
    return [{
      name: item.name,
      firstDate: categories[first.index] || "起点",
      firstValue: first.value,
      latestDate: categories[latest.index] || "最新",
      latestValue: latest.value,
      change,
      direction: change > 0 ? "上升" : change < 0 ? "下降" : "持平",
    }];
  });
}

export function describeLineChart(
  categories: string[],
  series: CurveSeries[],
  unit: string,
): string {
  const rows = summarizeLineChart(categories, series);
  if (!rows.length) return "时间序列折线图，暂无有效数值";
  const period = categories.length
    ? `${categories[0]} 至 ${categories[categories.length - 1]}`
    : "观察区间未知";
  const details = rows.map((row) =>
    `${row.name} 最新 ${row.latestValue.toFixed(4)}${unit}（${row.latestDate}），较首个有效值${row.direction}`,
  ).join("；");
  return `时间序列折线图，${period}，共 ${categories.length} 个时间点；${details}`;
}
