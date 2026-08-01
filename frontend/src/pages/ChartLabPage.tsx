import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  BookOpenCheck,
  Check,
  CirclePlus,
  Database,
  Download,
  Inbox,
  LoaderCircle,
  Save,
  X,
} from "lucide-react";
import { apiGet, apiPost } from "../api";
import { ErrorState, LoadingState, Panel, SourceFooter } from "../components/UI";
import type {
  Dataset,
  MacroCatalogItem,
  MacroChartData,
  ResearchEvidence,
  ResearchProject,
} from "../types";
import { buildChartEvidence, buildMacroCsv } from "../researchUtils";
import { PageHeading } from "./MarketPages";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.LineChart })),
);

const transformLabels: Record<MacroChartData["transform"], string> = {
  level: "原值",
  change: "单期变化",
  yoy: "同比 %",
  normalize: "基期归一化 = 100",
  zscore: "区间 Z-Score",
};

export function ChartLabPage({ initialQuery }: { initialQuery?: string }) {
  const initialSeries = (initialQuery || "DGS10")
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 6);
  const [catalog, setCatalog] = useState<MacroCatalogItem[]>([]);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [selected, setSelected] = useState<string[]>(initialSeries);
  const [candidate, setCandidate] = useState("T10Y2Y");
  const [years, setYears] = useState(10);
  const [transform, setTransform] = useState<MacroChartData["transform"]>("level");
  const [chart, setChart] = useState<Dataset<MacroChartData> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [basketSaved, setBasketSaved] = useState(false);

  useEffect(() => {
    Promise.all([
      apiGet<MacroCatalogItem[]>("/macro/catalog"),
      apiGet<ResearchProject[]>("/research/projects"),
    ])
      .then(([items, nextProjects]) => {
        setCatalog(items);
        setProjects(nextProjects);
        if (nextProjects.length) setProjectId(String(nextProjects[0].id));
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!selected.length) {
      setChart(null);
      setLoading(false);
      return;
    }
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSaved(false);
    setBasketSaved(false);
    const path = `/macro/chart?series=${encodeURIComponent(selected.join(","))}&years=${years}&transform=${transform}`;
    apiGet<Dataset<MacroChartData>>(path, { signal: controller.signal })
      .then((value) => {
        if (active) setChart(value);
      })
      .catch((reason: unknown) => {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setChart(null);
          setError(reason instanceof Error ? reason.message : "研究图表加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [selected, transform, years]);

  const available = useMemo(
    () => catalog.filter((item) => !selected.includes(item.series_id)),
    [catalog, selected],
  );

  function addSeries() {
    if (!candidate || selected.includes(candidate) || selected.length >= 6) return;
    setSelected((current) => [...current, candidate]);
    const next = available.find((item) => item.series_id !== candidate);
    setCandidate(next?.series_id || "");
  }

  async function saveEvidence() {
    if (!chart || !projectId) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost<ResearchEvidence>(
        `/research/projects/${projectId}/evidence`,
        buildChartEvidence(
          chart,
          selected,
          `${selected.join(" / ")} · ${transformLabels[transform]}`,
        ),
      );
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究证据保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function addToBasket() {
    if (!chart) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost<ResearchEvidence>("/research/evidence-basket", {
        ...buildChartEvidence(
          chart,
          selected,
          `${selected.join(" / ")} · ${transformLabels[transform]}`,
        ),
        origin_page: "chart-lab",
      });
      setBasketSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入证据篮失败");
    } finally {
      setSaving(false);
    }
  }

  function exportCsv() {
    if (!chart) return;
    const csv = buildMacroCsv(chart);
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-宏观研究-${selected.join("-")}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page-stack chart-lab-page">
      <PageHeading
        eyebrow="CHART LAB"
        title="图表研究室"
        description="组合宏观序列、记录变换链，并保存为可复盘的引用证据"
      />

      <Panel title="研究参数" eyebrow="INPUTS">
        <div className="chart-lab-controls">
          <div className="series-picker">
            <span>研究序列（最多 6 条）</span>
            <div className="selected-series-list">
              {selected.map((seriesId) => {
                const item = catalog.find((entry) => entry.series_id === seriesId);
                return (
                  <span key={seriesId}>
                    <strong>{seriesId}</strong> {item?.title_zh || ""}
                    <button onClick={() => setSelected((current) => current.filter((value) => value !== seriesId))} aria-label={`移除 ${seriesId}`}>
                      <X size={12} />
                    </button>
                  </span>
                );
              })}
            </div>
            <div className="series-add-row">
              <select value={candidate} onChange={(event) => setCandidate(event.target.value)} aria-label="添加宏观序列">
                <option value="">选择指标</option>
                {available.map((item) => <option value={item.series_id} key={item.series_id}>{item.series_id} · {item.title_zh}</option>)}
              </select>
              <button className="secondary-button" onClick={addSeries} disabled={!candidate || selected.length >= 6}>
                <CirclePlus size={14} /> 添加
              </button>
            </div>
          </div>
          <label>
            <span>时间范围</span>
            <select value={years} onChange={(event) => setYears(Number(event.target.value))}>
              <option value={1}>1 年</option><option value={5}>5 年</option><option value={10}>10 年</option><option value={20}>20 年</option><option value={50}>全部可用</option>
            </select>
          </label>
          <label>
            <span>变换方法</span>
            <select value={transform} onChange={(event) => setTransform(event.target.value as MacroChartData["transform"])}>
              {Object.entries(transformLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
        </div>
        <p className="method-note">缺失日期保持为空；同比使用 FRED 官方 pc1 口径。FRED 观测值只在当前请求中处理，不写入本地数据库。</p>
      </Panel>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState message={error} /> : null}
      {chart ? (
        <Panel
          title={transformLabels[chart.data.transform]}
          eyebrow="RESEARCH CHART"
          action={
            <div className="chart-export-actions">
              <button className="secondary-button" onClick={exportCsv}><Download size={14} /> CSV</button>
              <button className="secondary-button" onClick={addToBasket} disabled={saving}>
                {basketSaved ? <Check size={14} /> : <Inbox size={14} />}
                {basketSaved ? "已加入证据篮" : "加入证据篮"}
              </button>
              {projects.length ? (
                <>
                  <select value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="保存到研究项目">
                    {projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}
                  </select>
                  <button className="primary-button" onClick={saveEvidence} disabled={saving || !projectId}>
                    {saving ? <LoaderCircle className="spin" size={14} /> : saved ? <Check size={14} /> : <Save size={14} />}
                    {saved ? "已保存引用" : "保存引用证据"}
                  </button>
                </>
              ) : null}
            </div>
          }
        >
          <Suspense fallback={<div className="chart-loading skeleton" style={{ height: 390 }} />}>
            <LineChart categories={chart.data.dates} series={chart.data.series} height={390} unit={transform === "yoy" ? "%" : ""} />
          </Suspense>
          <div className="chart-provenance">
            <Database size={15} />
            <div>
              <strong>数据与变换可追溯 · 当前请求实时获取</strong>
              <span>{chart.data.dates[0]} 至 {chart.data.dates[chart.data.dates.length - 1]} · {chart.data.series.length} 条序列 · {transformLabels[transform]} · 本地不持久化观测值</span>
            </div>
          </div>
          <div className="attribution-list">
            {chart.data.series.map((item) => (
              <a href={item.source_url} target="_blank" rel="noreferrer" key={item.key}>
                <strong>{item.key}</strong><span>{item.attribution || "Retrieved via FRED；原始来源见序列页"}</span>
              </a>
            ))}
          </div>
          <SourceFooter meta={chart.meta} />
        </Panel>
      ) : null}

      {!projects.length ? (
        <div className="chart-project-hint">
          <BookOpenCheck size={18} />
          <span>创建研究项目后，可保存当前序列、变换与来源引用；重新打开时会获取最新数据版本。</span>
        </div>
      ) : null}
    </div>
  );
}
