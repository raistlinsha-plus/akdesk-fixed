import { useEffect, useRef } from "react";
import { BarChart as EChartsBar, LineChart as EChartsLine } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { CurveSeries } from "../types";
import {
  describeLineChart,
  lineChartPrecision,
  summarizeLineChart,
} from "../chartAccessibility";

echarts.use([
  EChartsBar,
  EChartsLine,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const palette = [
  "#5eead4",
  "#60a5fa",
  "#fbbf24",
  "#c084fc",
  "#fb7185",
  "#34d399",
  "#f97316",
  "#a3e635",
];

export interface LineChartProps {
  categories: string[];
  series: CurveSeries[];
  height?: number;
  unit?: string;
}

export function LineChart({
  categories,
  series,
  height = 280,
  unit = "%",
}: LineChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const summary = summarizeLineChart(categories, series);
  const description = describeLineChart(categories, series, unit);
  const precision = lineChartPrecision(series);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    chart.setOption({
      animationDuration: reduceMotion ? 0 : 350,
      color: palette,
      grid: { left: 44, right: 18, top: 42, bottom: 32 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0d1b2c",
        borderColor: "#24364c",
        textStyle: { color: "#dce8f5" },
        valueFormatter: (value: unknown) =>
          typeof value === "number" ? value.toFixed(Math.max(precision, 2)) + unit : "—",
      },
      legend: {
        top: 4,
        left: 6,
        textStyle: { color: "#8da2b8", fontSize: 11 },
        itemWidth: 14,
        itemHeight: 2,
      },
      xAxis: {
        type: "category",
        data: categories,
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#26384d" } },
        axisLabel: { color: "#7890a8", fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: "#172a3f", type: "dashed" } },
        axisLabel: {
          color: "#7890a8",
          fontSize: 10,
          formatter: (value: number) => value.toFixed(precision),
        },
      },
      series: series.map((item, index) => ({
        name: item.name,
        type: "line",
        data: item.values,
        showSymbol: true,
        symbolSize: index === 0 ? 6 : 4,
        lineStyle: { width: index === 0 ? 2.4 : 1.5 },
        emphasis: { focus: "series" },
        connectNulls: false,
      })),
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [categories, precision, series, unit]);

  if (!summary.length) {
    return <div className="chart-empty-state" style={{ minHeight: height }} role="status">暂无可绘制的数据</div>;
  }

  return (
    <figure className="chart-frame">
      <div ref={ref} style={{ height }} role="img" aria-label={description} />
      <details className="chart-data-summary">
        <summary>查看图表数据摘要</summary>
        <div className="chart-table-wrap">
          <table>
            <thead><tr><th>序列</th><th>首个有效值</th><th>最新值</th><th>区间变化</th></tr></thead>
            <tbody>
              {summary.map((row) => (
                <tr key={row.name}>
                  <th scope="row">{row.name}</th>
                  <td>{row.firstValue.toFixed(4)}{unit}<small>{row.firstDate}</small></td>
                  <td>{row.latestValue.toFixed(4)}{unit}<small>{row.latestDate}</small></td>
                  <td>{row.change > 0 ? "+" : ""}{row.change.toFixed(4)}{unit} · {row.direction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

export interface BarChartProps {
  categories: string[];
  values: Array<number | null>;
  height?: number;
}

export function BarChart({
  categories,
  values,
  height = 220,
}: BarChartProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    chart.setOption({
      animationDuration: reduceMotion ? 0 : 300,
      grid: { left: 38, right: 14, top: 18, bottom: 30 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0d1b2c",
        borderColor: "#24364c",
        textStyle: { color: "#dce8f5" },
        valueFormatter: (value: unknown) =>
          typeof value === "number" ? value.toFixed(2) + " BP" : "—",
      },
      xAxis: {
        type: "category",
        data: categories,
        axisLine: { lineStyle: { color: "#26384d" } },
        axisLabel: { color: "#7890a8", fontSize: 10 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#172a3f", type: "dashed" } },
        axisLabel: { color: "#7890a8", fontSize: 10 },
      },
      series: [
        {
          type: "bar",
          data: values.map((value) => ({
            value,
            itemStyle: { color: (value ?? 0) >= 0 ? "#f06a73" : "#45c486" },
          })),
          barMaxWidth: 28,
          itemStyle: { borderRadius: [3, 3, 0, 0] },
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [categories, values]);

  return (
    <div
      ref={ref}
      style={{ height }}
      role="img"
      aria-label={`收益率变化柱状图，共 ${categories.length} 个数据点`}
    />
  );
}
