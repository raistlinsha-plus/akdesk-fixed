import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CircleAlert,
  Download,
  Globe2,
  Inbox,
  LoaderCircle,
  RefreshCcw,
  Save,
} from "lucide-react";
import { apiGet, apiPost } from "../api";
import { CreateProjectButton } from "../components/CreateProjectButton";
import {
  ErrorState,
  LoadingState,
  Panel,
  SourceFooter,
  formatNumber,
} from "../components/UI";
import type {
  Dataset,
  ResearchEvidence,
  ResearchProject,
  SovereignCatalog,
  SovereignComparison,
} from "../types";
import { shouldForceSovereignRefresh } from "../sovereignUtils";
import { PageHeading } from "./MarketPages";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.LineChart })),
);

const currentYear = new Date().getFullYear();
const viewLabels: Record<SovereignComparison["view"], string> = {
  level: "水平值",
  change: "单年变化",
  rank: "横截面数值排名",
  zscore: "横截面 Z-Score",
};

export function SovereignPage({
  initialQuery,
  refreshSeed = 0,
}: {
  initialQuery?: string;
  refreshSeed?: number;
}) {
  const [catalog, setCatalog] = useState<SovereignCatalog | null>(null);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [countries, setCountries] = useState(["CHN", "USA", "JPN", "DEU"]);
  const [indicator, setIndicator] = useState(initialQuery || "NY.GDP.MKTP.KD.ZG");
  const [startYear, setStartYear] = useState(currentYear - 10);
  const [endYear, setEndYear] = useState(currentYear);
  const [view, setView] = useState<SovereignComparison["view"]>("level");
  const [comparison, setComparison] = useState<Dataset<SovereignComparison> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [consumedRefreshNonce, setConsumedRefreshNonce] = useState(0);
  const [projectId, setProjectId] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [basketSaved, setBasketSaved] = useState(false);
  const seenRefreshSeed = useRef(refreshSeed);

  useEffect(() => {
    if (refreshSeed === seenRefreshSeed.current) return;
    seenRefreshSeed.current = refreshSeed;
    setRefreshNonce((value) => value + 1);
  }, [refreshSeed]);

  useEffect(() => {
    Promise.all([
      apiGet<SovereignCatalog>("/sovereign/catalog"),
      apiGet<ResearchProject[]>("/research/projects"),
    ])
      .then(([nextCatalog, nextProjects]) => {
        setCatalog(nextCatalog);
        setProjects(nextProjects);
        const active = nextProjects.find((item) => item.status !== "archived");
        if (active) setProjectId(String(active.id));
        if (
          initialQuery
          && nextCatalog.indicators.some((item) => item.indicator_id === initialQuery)
        ) {
          setIndicator(initialQuery);
        }
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "主权指标目录加载失败"),
      );
  }, [initialQuery]);

  useEffect(() => {
    if (countries.length < 2 || startYear > endYear) return;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSaved(false);
    setBasketSaved(false);
    setComparison(null);
    const forceRefresh = shouldForceSovereignRefresh(
      refreshNonce,
      consumedRefreshNonce,
    );
    const path =
      `/sovereign/compare?countries=${encodeURIComponent(countries.join(","))}` +
      `&indicator=${encodeURIComponent(indicator)}` +
      `&start_year=${startYear}&end_year=${endYear}&view=${view}` +
      `&refresh=${forceRefresh ? "true" : "false"}`;
    apiGet<Dataset<SovereignComparison>>(path, { signal: controller.signal })
      .then((result) => {
        if (active) setComparison(result);
      })
      .catch((reason: unknown) => {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setComparison(null);
          setError(reason instanceof Error ? reason.message : "主权比较加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          if (forceRefresh) setConsumedRefreshNonce(refreshNonce);
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [countries, endYear, indicator, refreshNonce, startYear, view]);

  const groupedIndicators = useMemo(() => {
    const groups = new Map<string, SovereignCatalog["indicators"]>();
    for (const item of catalog?.indicators || []) {
      groups.set(item.topic, [...(groups.get(item.topic) || []), item]);
    }
    return Array.from(groups.entries());
  }, [catalog]);

  function toggleCountry(code: string) {
    setCountries((current) => {
      if (current.includes(code)) {
        return current.length > 2 ? current.filter((item) => item !== code) : current;
      }
      return current.length < 8 ? [...current, code] : current;
    });
  }

  async function saveEvidence() {
    if (!comparison || !projectId) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost<ResearchEvidence>(
        `/research/projects/${projectId}/sovereign-snapshot`,
        {
          country_codes: countries,
          indicator_id: indicator,
          start_year: startYear,
          end_year: endYear,
          view,
          note,
        },
      );
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "主权比较证据保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function addToBasket() {
    if (!comparison) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost("/research/evidence-basket/sovereign-snapshot", {
        country_codes: countries,
        indicator_id: indicator,
        start_year: startYear,
        end_year: endYear,
        view,
        note,
      });
      setBasketSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入证据篮失败");
    } finally {
      setSaving(false);
    }
  }

  function exportCsv() {
    if (!comparison) return;
    const header = [
      "年份",
      ...comparison.data.series.flatMap((item) =>
        view === "level"
          ? [`${item.name} · 原值`]
          : [`${item.name} · 原值`, `${item.name} · ${viewLabels[view]}`],
      ),
    ];
    const rows = comparison.data.years.map((year, index) => [
      year,
      ...comparison.data.series.flatMap((item) =>
        view === "level"
          ? [item.raw_values[index] ?? ""]
          : [item.raw_values[index] ?? "", item.values[index] ?? ""],
      ),
    ]);
    const metadata = [
      [],
      ["指标", comparison.data.indicator.indicator_id],
      ["名称", comparison.data.indicator.title_zh],
      ["显示方式", viewLabels[view]],
      ["来源", comparison.data.source],
      ["许可", comparison.data.license],
      ["署名", comparison.data.attribution],
      ["说明", comparison.data.comparison_notice],
    ];
    const csv = [...[header], ...rows, ...metadata]
      .map((row) =>
        row
          .map((value) => `"${String(value).replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-主权比较-${indicator}-${startYear}-${endYear}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const displayUnit =
    view === "rank"
      ? "名"
      : view === "zscore"
        ? ""
        : comparison?.data.indicator.unit || "";

  return (
    <div className="page-stack sovereign-page">
      <PageHeading
        eyebrow="SOVEREIGN COMPARISON"
        title="全球主权比较"
        description="基于 World Bank 官方低频指标，比较增长、财政、外部平衡与结构变量"
      />

      <Panel title="比较范围" eyebrow="WORLD BANK WDI">
        <div className="sovereign-controls">
          <label className="sovereign-indicator-field">
            <span>精选指标</span>
            <select
              value={indicator}
              onChange={(event) => setIndicator(event.target.value)}
            >
              {groupedIndicators.map(([topic, items]) => (
                <optgroup label={topic} key={topic}>
                  {items.map((item) => (
                    <option value={item.indicator_id} key={item.indicator_id}>
                      {item.title_zh} · {item.indicator_id}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label>
            <span>起始年份</span>
            <input
              type="number"
              min={1960}
              max={endYear}
              value={startYear}
              onChange={(event) => setStartYear(Number(event.target.value))}
            />
          </label>
          <label>
            <span>结束年份</span>
            <input
              type="number"
              min={startYear}
              max={currentYear}
              value={endYear}
              onChange={(event) => setEndYear(Number(event.target.value))}
            />
          </label>
          <label>
            <span>显示方式</span>
            <select
              value={view}
              onChange={(event) =>
                setView(event.target.value as SovereignComparison["view"])
              }
            >
              {(catalog?.views || []).map((item) => (
                <option value={item.id} key={item.id}>{item.label}</option>
              ))}
            </select>
          </label>
          <button
            className="icon-button"
            onClick={() => setRefreshNonce((value) => value + 1)}
            aria-label="刷新 World Bank 官方数据"
            title="刷新 World Bank 官方数据"
          >
            <RefreshCcw size={14} />
          </button>
        </div>
        <div className="sovereign-country-picker" aria-label="选择比较经济体">
          {(catalog?.countries || []).map((item) => {
            const checked = countries.includes(item.country_code);
            return (
              <label className={checked ? "active" : undefined} key={item.country_code}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={checked ? countries.length <= 2 : countries.length >= 8}
                  onChange={() => toggleCountry(item.country_code)}
                />
                <strong>{item.name_zh}</strong>
                <small>{item.country_code}</small>
              </label>
            );
          })}
        </div>
        <p className="method-note">
          请选择 2–8 个经济体。缺失年份保持为空，不向前或向后填充，也不把不同年份冒充为同一期。
        </p>
      </Panel>

      {loading ? <LoadingState label="正在读取 World Bank 主权数据" /> : null}
      {error ? <ErrorState message={error} /> : null}

      {comparison ? (
        <>
          <div className="metrics-grid">
            <article className="metric-card">
              <span>数据覆盖</span>
              <strong>{formatNumber(comparison.data.coverage.ratio * 100, 1)}%</strong>
            </article>
            <article className="metric-card">
              <span>最新共同年份</span>
              <strong>{comparison.data.latest_comparable_year || "无"}</strong>
            </article>
            <article className="metric-card">
              <span>最新可用年份</span>
              <strong>{comparison.data.latest_available_year || "无"}</strong>
            </article>
            <article className="metric-card">
              <span>本地状态</span>
              <strong>
                {comparison.meta.stale
                  ? "过期缓存"
                  : comparison.meta.data_state === "latest"
                    ? "官方最新"
                    : "可用缓存"}
              </strong>
            </article>
          </div>

          <Panel
            title={`${comparison.data.indicator.title_zh} · ${viewLabels[view]}`}
            eyebrow="ALIGNED ANNUAL SERIES"
            action={
              <div className="row-actions">
                <CreateProjectButton
                  objectType="macro"
                  objectId={`WDI:${indicator}`}
                  objectName={`${comparison.data.indicator.title_zh}主权比较`}
                  source={comparison.data.source}
                  observationTime={comparison.meta.observation_time}
                  templateId="sovereign_comparison"
                  onCreated={(project) => {
                    setProjects((current) =>
                      current.some((item) => item.id === project.id)
                        ? current
                        : [project, ...current],
                    );
                    setProjectId(String(project.id));
                  }}
                />
                <button className="secondary-button" onClick={exportCsv}>
                  <Download size={14} /> CSV
                </button>
              </div>
            }
          >
            <Suspense
              fallback={<div className="chart-loading skeleton" style={{ height: 360 }} />}
            >
              <LineChart
                categories={comparison.data.years}
                series={comparison.data.series}
                height={360}
                unit={displayUnit ? ` ${displayUnit}` : ""}
              />
            </Suspense>
            <div className="sovereign-comparison-table-wrap">
              <table className="data-table sovereign-comparison-table">
                <thead>
                  <tr>
                    <th>经济体</th>
                    <th>比较年份</th>
                    <th>原值</th>
                    <th>显示值</th>
                    <th>数值排名</th>
                    <th>覆盖</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.data.latest_rows.map((item) => {
                    const coverage =
                      comparison.data.coverage.by_country[item.country_code];
                    return (
                      <tr key={item.country_code}>
                        <td><strong>{item.country_name}</strong><small>{item.country_code}</small></td>
                        <td>{comparison.data.summary_year || "—"}</td>
                        <td>{formatNumber(item.value, 3)} {comparison.data.indicator.unit}</td>
                        <td>{formatNumber(item.display_value, 3)} {displayUnit}</td>
                        <td>{item.rank ? `第 ${item.rank}` : "—"}</td>
                        <td>{coverage?.available || 0}/{coverage?.total || 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="warning-banner">
              <CircleAlert size={15} /> {comparison.data.comparison_notice}
            </p>
            <SourceFooter meta={comparison.meta} />
          </Panel>

          <Panel title="保存到研究项目" eyebrow="RESEARCH EVIDENCE">
            {projects.filter((item) => item.status !== "archived").length ? (
              <div className="sovereign-save-row">
                <label>
                  <span>目标项目</span>
                  <select
                    value={projectId}
                    onChange={(event) => setProjectId(event.target.value)}
                  >
                    {projects
                      .filter((item) => item.status !== "archived")
                      .map((project) => (
                        <option value={project.id} key={project.id}>
                          {project.title}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  <span>证据备注</span>
                  <input
                    value={note}
                    maxLength={1000}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="记录比较目的、异常年份或待验证问题"
                  />
                </label>
                <button
                  className="primary-button"
                  onClick={saveEvidence}
                  disabled={saving || !projectId || comparison.meta.stale}
                >
                  {saving ? (
                    <LoaderCircle className="spin" size={14} />
                  ) : saved ? (
                    <Check size={14} />
                  ) : (
                    <Save size={14} />
                  )}
                  {saved ? "已保存证据" : "保存主权比较证据"}
                </button>
                <button
                  className="secondary-button"
                  onClick={addToBasket}
                  disabled={saving || comparison.meta.stale}
                >
                  {basketSaved ? <Check size={14} /> : <Inbox size={14} />}
                  {basketSaved ? "已加入证据篮" : "加入证据篮"}
                </button>
              </div>
            ) : (
              <div className="empty-state compact-empty">
                <Globe2 size={26} />
                <strong>尚无可用研究项目</strong>
                <p>可以先加入证据篮，稍后在专题投研工作台批量归档。</p>
                <button
                  className="secondary-button"
                  onClick={addToBasket}
                  disabled={saving || comparison.meta.stale}
                >
                  {basketSaved ? <Check size={14} /> : <Inbox size={14} />}
                  {basketSaved ? "已加入证据篮" : "加入证据篮"}
                </button>
              </div>
            )}
          </Panel>

          <Panel title="指标口径与许可" eyebrow="METADATA & LICENSE">
            <div className="sovereign-metadata-grid">
              <div><span>指标代码</span><strong>{comparison.data.indicator.indicator_id}</strong></div>
              <div><span>官方更新时间</span><strong>{comparison.data.indicator.last_updated || "未提供"}</strong></div>
              <div><span>原始机构</span><strong>{comparison.data.indicator.source_organization || "World Bank"}</strong></div>
              <div><span>许可</span><strong>{comparison.data.license}</strong></div>
            </div>
            {comparison.data.indicator.source_note ? (
              <p className="method-note">{comparison.data.indicator.source_note}</p>
            ) : null}
            <p className="method-note">
              署名：{comparison.data.attribution}。导出和研究证据保留来源、指标代码、年份与许可信息。
              <a href={comparison.data.license_url} target="_blank" rel="noreferrer"> 查看许可</a>
            </p>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
