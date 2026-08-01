import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  ChevronRight,
  Clock3,
  Download,
  Pin,
  RefreshCcw,
  Save,
  SlidersHorizontal,
  Star,
  Trash2,
} from "lucide-react";
import { useWatchlist } from "../components/WatchlistContext";
import { CreateProjectButton } from "../components/CreateProjectButton";
import { AiInsightCard } from "../components/AiInsightCard";
import { GettingStartedGuide } from "../components/GettingStartedGuide";
import { apiGet } from "../api";
import {
  ChangeValue,
  ErrorState,
  formatDateTime,
  formatNumber,
  LoadingState,
  Panel,
  SourceFooter,
  WarningBanner,
  WatchButton,
  classNames,
} from "../components/UI";
import { useDataset } from "../components/useDataset";
import {
  clampPage,
  parseSavedViews,
  serializeSavedViews,
  upsertSavedView,
  type SavedView,
} from "../savedViews";
import type { EnrichedWatchlistItem } from "../types";
import { canWatchItem } from "../marketSafety";
import { buildMarketTodayTasks } from "../experienceGuide";
import {
  DASHBOARD_MODULE_LABELS,
  DASHBOARD_PRESETS,
  readDashboardModules,
  readRecentMarketPages,
  percentileRank,
  writeDashboardModules,
  type DashboardModule,
} from "../marketDashboard";
import type {
  Convertible,
  CurveData,
  FxPairQuote,
  FxRmbReference,
  HistoryResponse,
  MarketEvent,
  RateItem,
  SpotBond,
  TreasuryFuture,
} from "../types";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.LineChart })),
);
const BarChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.BarChart })),
);

const trustLevelLabels: Record<string, string> = {
  trusted: "可信",
  partial: "部分可信",
  suspicious: "可疑",
  unavailable: "不可用",
};

const marketStatusLabels: Record<string, string> = {
  pre_open: "盘前",
  trading: "交易中",
  session_break: "午间休市",
  closed: "已收盘",
  non_trading_day: "非交易日",
  daily: "日频",
  unknown: "状态未知",
};

function ChartFallback({ height }: { height: number }) {
  return <div className="chart-loading skeleton" style={{ height }} />;
}

interface PageProps {
  refreshSeed: number;
  navigate?: (page: string, query?: string) => void;
  initialQuery?: string;
}

interface BondSavedView {
  typeFilter: string;
  minYield: string;
  maxYield: string;
  minMove: string;
  sortBy: string;
}

interface ConvertibleSavedView {
  maxPrice: string;
  maxPremium: string;
  maxDoubleLow: string;
  minYtm: string;
  sortBy: string;
}

function hasStringFields<T extends object>(
  value: unknown,
  fields: Array<keyof T>,
): value is T {
  return Boolean(
    value &&
      typeof value === "object" &&
      fields.every(
        (field) =>
          field in value &&
          typeof (value as Record<PropertyKey, unknown>)[field] === "string",
      ),
  );
}

function isBondSavedView(value: unknown): value is BondSavedView {
  return hasStringFields<BondSavedView>(value, [
    "typeFilter",
    "minYield",
    "maxYield",
    "minMove",
    "sortBy",
  ]);
}

function isConvertibleSavedView(value: unknown): value is ConvertibleSavedView {
  return hasStringFields<ConvertibleSavedView>(value, [
    "maxPrice",
    "maxPremium",
    "maxDoubleLow",
    "minYtm",
    "sortBy",
  ]);
}

function useSavedViews<T>(
  storageKey: string,
  validateValue: (value: unknown) => value is T,
) {
  const [state, setState] = useState<{
    views: Array<SavedView<T>>;
    message: string | null;
  }>(() => {
    try {
      const parsed = parseSavedViews(
        localStorage.getItem(storageKey),
        validateValue,
      );
      return { views: parsed.views, message: parsed.warning };
    } catch {
      return { views: [], message: "无法读取本机保存视图" };
    }
  });

  function persist(next: Array<SavedView<T>>, message: string): boolean {
    try {
      localStorage.setItem(storageKey, serializeSavedViews(next));
      setState({ views: next, message });
      return true;
    } catch {
      setState((current) => ({
        ...current,
        message: "保存失败：浏览器本地存储不可用",
      }));
      return false;
    }
  }

  function save(value: T, rawName: string) {
    const result = upsertSavedView(state.views, value, rawName);
    if (!result) {
      setState((current) => ({ ...current, message: "请先填写视图名称" }));
      return null;
    }
    return persist(
      result.views,
      result.overwritten ? "同名视图已覆盖" : "筛选视图已保存",
    )
      ? result.id
      : null;
  }

  function remove(id: string) {
    return persist(
      state.views.filter((item) => item.id !== id),
      "筛选视图已删除",
    );
  }

  return { views: state.views, message: state.message, save, remove };
}

function SavedViewControls<T>({
  manager,
  value,
  suggestedName,
  onLoad,
}: {
  manager: ReturnType<typeof useSavedViews<T>>;
  value: T;
  suggestedName: string;
  onLoad: (value: T) => void;
}) {
  const [selected, setSelected] = useState("");
  const [name, setName] = useState(suggestedName);
  return (
    <div className="saved-view-controls">
      <input
        aria-label="保存视图名称"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="视图名称"
      />
      <button
        className="secondary-button"
        onClick={() => {
          const id = manager.save(value, name);
          if (id) setSelected(id);
        }}
      >
        <Save size={14} /> 保存
      </button>
      {manager.views.length ? (
        <>
          <select
            aria-label="载入保存视图"
            value={selected}
            onChange={(event) => {
              const id = event.target.value;
              setSelected(id);
              const view = manager.views.find((item) => item.id === id);
              if (view) {
                setName(view.name);
                onLoad(view.value);
              }
            }}
          >
            <option value="">载入视图</option>
            {manager.views.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <button
            className="icon-button danger"
            aria-label="删除当前保存视图"
            disabled={!selected}
            onClick={() => {
              if (!selected) return;
              manager.remove(selected);
              setSelected("");
              setName(suggestedName);
            }}
          >
            <Trash2 size={14} />
          </button>
        </>
      ) : null}
      {manager.message ? (
        <span className="saved-view-status" role="status">
          {manager.message}
        </span>
      ) : null}
    </div>
  );
}

function Pagination({
  page,
  total,
  pageSize,
  onChange,
}: {
  page: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="table-pagination" aria-label="表格分页">
      <span>第 {page}/{pages} 页</span>
      <button className="secondary-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button>
      <button className="secondary-button" disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</button>
    </nav>
  );
}

function DataMessage({
  loading,
  error,
}: {
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  return null;
}

export function DashboardPage({ refreshSeed, navigate }: PageProps) {
  const { items: dashboardWatchlist } = useWatchlist();
  const rates = useDataset<RateItem[]>("/rates", refreshSeed);
  const curves = useDataset<CurveData>("/curves", refreshSeed);
  const futures = useDataset<TreasuryFuture[]>("/futures", refreshSeed);
  const bonds = useDataset<SpotBond[]>("/bonds/spot", refreshSeed);
  const events = useDataset<MarketEvent[]>("/events", refreshSeed);
  const fxPairs = useDataset<FxPairQuote[]>("/fx/pairs", refreshSeed);
  const fxReferences = useDataset<FxRmbReference[]>(
    "/fx/rmb-reference",
    refreshSeed,
  );
  const [visibleModules, setVisibleModules] = useState<DashboardModule[]>(
    () => readDashboardModules(window.localStorage),
  );
  const [recentPages] = useState(() => readRecentMarketPages(window.localStorage));
  const [marketHistories, setMarketHistories] = useState<{
    tenYear: HistoryResponse;
    fdr: HistoryResponse;
  } | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiGet<HistoryResponse>("/history?adapter=yield_curves&metric=yield&series=10Y&days=180"),
      apiGet<HistoryResponse>("/history?adapter=money_fdr&metric=value&series=FDR007&days=180"),
    ])
      .then(([tenYear, fdr]) => {
        if (active) setMarketHistories({ tenYear, fdr });
      })
      .catch(() => {
        if (active) setMarketHistories(null);
      });
    return () => {
      active = false;
    };
  }, [refreshSeed]);

  const hasDemo = [
    rates.dataset,
    curves.dataset,
    futures.dataset,
    bonds.dataset,
    events.dataset,
  ].some((dataset) => dataset?.meta.demo);
  const hasStale = [
    rates.dataset,
    curves.dataset,
    futures.dataset,
    bonds.dataset,
    events.dataset,
  ].some((dataset) => dataset?.meta.stale && !dataset.meta.demo);
  const hasCached = [
    rates.dataset,
    curves.dataset,
    futures.dataset,
    bonds.dataset,
    events.dataset,
  ].some((dataset) => dataset?.meta.data_state === "cached");
  const hasTrustWarning = [
    rates.dataset,
    curves.dataset,
    futures.dataset,
    bonds.dataset,
    events.dataset,
  ].some((dataset) => dataset && dataset.meta.trust_level !== "trusted");
  const marketLabel =
    futures.dataset?.meta.market_status_label ??
    bonds.dataset?.meta.market_status_label ??
    "正在检查市场状态";
  const marketPulse = useMemo(() => {
    const rate =
      rates.dataset?.data.find((item) => item.name === "FDR007") ??
      rates.dataset?.data.find((item) => item.name === "Shibor O/N");
    const curve = curves.dataset?.data;
    const latestCurve = curve?.series.find((item) => item.name.includes("国债") && item.name.includes("最新"));
    const tenYearIndex = curve?.tenors.indexOf("10Y") ?? -1;
    const oneYearIndex = curve?.tenors.indexOf("1Y") ?? -1;
    const tenYear = tenYearIndex >= 0 ? latestCurve?.values[tenYearIndex] : null;
    const oneYear = oneYearIndex >= 0 ? latestCurve?.values[oneYearIndex] : null;
    const spread =
      tenYear != null && oneYear != null
        ? (tenYear - oneYear) * 100
        : null;
    const future = futures.dataset?.data.find((item) => item.product === "T");
    const usdCny = fxReferences.dataset?.data.find(
      (item) => item.code === "USDCNY",
    );
    const usdJpy = fxPairs.dataset?.data.find(
      (item) => item.code === "USDJPY",
    );
    return [
      {
        label: rate?.name ?? "资金利率",
        value: rate?.value,
        digits: 3,
        suffix: "%",
        change: rate?.change_bp,
        changeSuffix: " BP",
      },
      {
        label: "国债 10Y",
        value: tenYear,
        digits: 4,
        suffix: "%",
        change:
          tenYearIndex >= 0 ? curve?.changes[tenYearIndex] : null,
        changeSuffix: " BP",
      },
      {
        label: "10Y–1Y",
        value: spread,
        digits: 2,
        suffix: " BP",
        change: null,
        changeSuffix: "",
      },
      {
        label: future?.contract ?? "T 主力",
        value: future?.price,
        digits: 3,
        suffix: "",
        change: future?.change_pct,
        changeSuffix: "%",
      },
      {
        label: "USD/CNY",
        value: usdCny?.mid,
        digits: 5,
        suffix: "",
        change: usdCny?.change_pct,
        changeSuffix: "%",
      },
      {
        label: "USD/JPY",
        value: usdJpy?.mid,
        digits: 3,
        suffix: "",
        change: null,
        changeSuffix: "",
      },
    ];
  }, [
    curves.dataset,
    futures.dataset,
    fxPairs.dataset,
    fxReferences.dataset,
    rates.dataset,
  ]);
  const marketLens = useMemo(() => {
    const tenYearValues = marketHistories?.tenYear.series[0]?.values ?? [];
    const fdrValues = marketHistories?.fdr.series[0]?.values ?? [];
    const curve = curves.dataset?.data;
    const latestCurve = curve?.series.find((item) => item.name.includes("国债") && item.name.includes("最新"));
    const tenYearIndex = curve?.tenors.indexOf("10Y") ?? -1;
    const oneYearIndex = curve?.tenors.indexOf("1Y") ?? -1;
    const tenYear = tenYearIndex >= 0 ? latestCurve?.values[tenYearIndex] : null;
    const oneYear = oneYearIndex >= 0 ? latestCurve?.values[oneYearIndex] : null;
    const spread = tenYear != null && oneYear != null ? (tenYear - oneYear) * 100 : null;
    const future = futures.dataset?.data.find((item) => item.product === "T");
    const usdCny = fxReferences.dataset?.data.find((item) => item.code === "USDCNY");
    return [
      {
        label: "10Y 历史分位",
        value: percentileRank(tenYearValues, tenYear),
        suffix: "%",
        hint: `${marketHistories?.tenYear.dates.length ?? 0} 个本地交易日`,
      },
      {
        label: "FDR007 历史分位",
        value: percentileRank(fdrValues),
        suffix: "%",
        hint: `${marketHistories?.fdr.dates.length ?? 0} 个本地交易日`,
      },
      {
        label: "10Y–1Y 曲线",
        value: spread,
        suffix: " BP",
        hint: spread == null ? "等待曲线" : spread < 0 ? "曲线倒挂" : spread < 30 ? "曲线偏平" : "曲线正斜率",
      },
      {
        label: "跨市场方向",
        value: future?.change_pct,
        suffix: "%",
        hint: `T 主力；USD/CNY ${usdCny?.change_pct == null ? "—" : `${usdCny.change_pct > 0 ? "+" : ""}${usdCny.change_pct.toFixed(2)}%`}`,
      },
    ];
  }, [curves.dataset, futures.dataset, fxReferences.dataset, marketHistories]);
  const marketTodayTasks = useMemo(() => {
    const sources = [
      rates,
      curves,
      futures,
      bonds,
      events,
      fxPairs,
      fxReferences,
    ];
    const readySources = sources.filter((source) => Boolean(source.dataset)).length;
    const attentionSources = sources.filter(
      (source) =>
        Boolean(source.error) ||
        Boolean(
          source.dataset &&
          (source.dataset.meta.demo || source.dataset.meta.trust_level !== "trusted"),
        ),
    ).length;
    return buildMarketTodayTasks({
      readySources,
      totalSources: sources.length,
      attentionSources,
      watchlistItems: dashboardWatchlist.length,
      recentPages: recentPages.length,
    });
  }, [
    bonds,
    curves,
    dashboardWatchlist.length,
    events,
    futures,
    fxPairs,
    fxReferences,
    rates,
    recentPages.length,
  ]);

  function saveVisibleModules(modules: DashboardModule[]) {
    setVisibleModules(modules);
    writeDashboardModules(window.localStorage, modules);
  }

  function toggleDashboardModule(module: DashboardModule) {
    const next = visibleModules.includes(module)
      ? visibleModules.filter((item) => item !== module)
      : [...visibleModules, module];
    if (next.length) saveVisibleModules(next);
  }

  return (
    <div className="page-stack">
      <section className="hero-strip">
        <div>
          <span className="eyebrow">TODAY'S MARKET</span>
          <h1>今日市场</h1>
          <p>资金、曲线、现券、国债期货与重要事件的一屏市场入口</p>
        </div>
        <div className="hero-status">
          <span className={classNames("live-dot", hasDemo && "amber")} />
          {hasDemo
            ? "部分数据处于演示或降级状态"
            : hasStale
              ? "正在显示最近真实缓存"
              : hasTrustWarning
                ? "部分数据待验证或已隔离异常"
                : hasCached
                  ? `${marketLabel} · 本地缓存可用，正在验证数据源`
              : `${marketLabel} · 数据源连接正常`}
        </div>
      </section>

      <AiInsightCard
        contextType="market"
        title="今日市场 AI 洞察"
        description="把本页变化、可信边界和待验证问题压缩为可复核的短摘要"
        revision={refreshSeed}
      />

      <GettingStartedGuide
        mode="market"
        tasks={marketTodayTasks}
        onNavigate={(target) => navigate?.(target)}
      />

      <section className="market-dashboard-toolbar" aria-label="市场驾驶舱设置">
        <div>
          <span>最近查看</span>
          {recentPages.length ? recentPages.map((item) => (
            <button className="text-button" onClick={() => navigate?.(item.id)} key={item.id}>{item.label}</button>
          )) : <small>访问市场模块后会显示在这里</small>}
        </div>
        <details>
          <summary><SlidersHorizontal size={14} /> 调整驾驶舱</summary>
          <div className="dashboard-customizer">
            <div className="dashboard-presets">
              {Object.entries(DASHBOARD_PRESETS).map(([name, modules]) => (
                <button className="secondary-button" onClick={() => saveVisibleModules(modules)} type="button" key={name}>{name}</button>
              ))}
            </div>
            {Object.entries(DASHBOARD_MODULE_LABELS).map(([module, label]) => (
              <label key={module}>
                <input type="checkbox" checked={visibleModules.includes(module as DashboardModule)} onChange={() => toggleDashboardModule(module as DashboardModule)} />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </details>
      </section>

      <div className="metrics-grid six market-pulse-grid">
        {rates.loading || curves.loading || futures.loading
          ? Array.from({ length: 6 }).map((_, index) => (
              <div className="metric-card skeleton" key={index} />
            ))
          : marketPulse.map((item) => (
              <article className="metric-card" key={item.label}>
                <span>{item.label}</span>
                <strong>{formatNumber(item.value, item.digits)}{item.suffix}</strong>
                {item.change == null ? (
                  <small className="muted">当前快照</small>
                ) : (
                  <ChangeValue value={item.change} suffix={item.changeSuffix} />
                )}
              </article>
            ))}
      </div>

      <section className="market-lens" aria-labelledby="market-lens-title">
        <header>
          <div><span className="eyebrow">CROSS-ASSET LENS</span><h2 id="market-lens-title">利率与汇率联动观察</h2></div>
          <div className="market-lens-actions">
            <small>历史分位仅使用本地可信历史，样本不足时明确显示实际交易日数</small>
            <button className="secondary-button" type="button" onClick={() => navigate?.("research-desk")}>进入投研工作台</button>
          </div>
        </header>
        <div>
          {marketLens.map((item) => (
            <article key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value == null ? "—" : `${formatNumber(item.value, item.suffix === "%" ? 0 : 2)}${item.suffix}`}</strong>
              <small>{item.hint}</small>
            </article>
          ))}
        </div>
      </section>

      <div className="dashboard-grid">
        {visibleModules.includes("curve") ? (
        <Panel
          title="收益率曲线"
          eyebrow="CURVE"
          className="span-8"
          action={
            <button
              className="text-button"
              onClick={() => navigate?.("curves")}
            >
              展开分析 <ChevronRight size={14} />
            </button>
          }
        >
          <DataMessage loading={curves.loading} error={curves.error} />
          {curves.dataset ? (
            <>
              <WarningBanner meta={curves.dataset.meta} />
              <Suspense fallback={<ChartFallback height={284} />}>
                <LineChart
                  categories={curves.dataset.data.tenors}
                  series={curves.dataset.data.series}
                  height={284}
                />
              </Suspense>
              <SourceFooter meta={curves.dataset.meta} />
            </>
          ) : null}
        </Panel>
        ) : null}

        {visibleModules.includes("futures") ? (
        <Panel
          title="国债期货"
          eyebrow="CFFEX"
          className="span-4"
          action={
            <button
              className="text-button"
              onClick={() => navigate?.("futures")}
            >
              全部合约 <ChevronRight size={14} />
            </button>
          }
        >
          <DataMessage loading={futures.loading} error={futures.error} />
          {futures.dataset ? (
            <>
              <WarningBanner meta={futures.dataset.meta} />
              <div className="future-stack">
                {futures.dataset.data.slice(0, 4).map((item) => (
                  <div className="future-row" key={item.product}>
                    <span className="product-badge">{item.product}</span>
                    <div>
                      <strong>{formatNumber(item.price, 3)}</strong>
                      <small>{item.contract}</small>
                    </div>
                    <ChangeValue value={item.change_pct} suffix="%" />
                  </div>
                ))}
              </div>
              <SourceFooter meta={futures.dataset.meta} />
            </>
          ) : null}
        </Panel>
        ) : null}

        {visibleModules.includes("bonds") ? (
        <Panel
          title="活跃现券"
          eyebrow="CASH BOND"
          className="span-8"
          action={
            <button
              className="text-button"
              onClick={() => navigate?.("bonds")}
            >
              查看市场 <ChevronRight size={14} />
            </button>
          }
        >
          <DataMessage loading={bonds.loading} error={bonds.error} />
          {bonds.dataset ? (
            <>
              <WarningBanner meta={bonds.dataset.meta} />
              <div className="table-wrap compact">
                <table>
                  <thead>
                    <tr>
                      <th>债券</th>
                      <th>类型</th>
                      <th className="num">净价</th>
                      <th className="num">最新收益率</th>
                      <th className="num">变动</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {bonds.dataset.data.slice(0, 7).map((item) => (
                      <tr key={item.code + item.name}>
                        <td>
                          <strong>{item.name}</strong>
                          <small>{item.code}</small>
                        </td>
                        <td><span className="tag">{item.type}</span></td>
                        <td className="num mono">{formatNumber(item.price, 3)}</td>
                        <td className="num mono">{formatNumber(item.yield, 4)}%</td>
                        <td className="num">
                          <ChangeValue value={item.change_bp} />
                        </td>
                        <td>
                          {canWatchItem(item.code, item.quality_state) ? (
                            <WatchButton
                              objectType="bond"
                              objectId={item.code}
                              name={item.name}
                            />
                          ) : (
                            <span className="tag muted-tag">
                              {item.quality_state === "suspicious" ? "异常隔离" : "不可自选"}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <SourceFooter meta={bonds.dataset.meta} />
            </>
          ) : null}
        </Panel>
        ) : null}

        {visibleModules.includes("events") ? (
        <Panel
          title="今日事件"
          eyebrow="CALENDAR"
          className="span-4"
          action={
            <button
              className="text-button"
              onClick={() => navigate?.("events")}
            >
              日历 <ChevronRight size={14} />
            </button>
          }
        >
          <DataMessage loading={events.loading} error={events.error} />
          {events.dataset ? (
            <>
              <WarningBanner meta={events.dataset.meta} />
              <div className="event-list">
                {events.dataset.data.slice(0, 6).map((item, index) => (
                  <div className="event-item" key={item.date + item.title + index}>
                    <span className={"importance " + item.importance} />
                    <div>
                      <small>{item.date} · {item.type}</small>
                      <strong>{item.title}</strong>
                    </div>
                  </div>
                ))}
              </div>
              <SourceFooter meta={events.dataset.meta} />
            </>
          ) : null}
        </Panel>
        ) : null}

        {visibleModules.includes("fx") ? (
        <Panel
          title="跨市场外汇"
          eyebrow="GLOBAL FX"
          className="span-12"
          action={
            <button className="text-button" onClick={() => navigate?.("fx")}>
              外汇市场 <ChevronRight size={14} />
            </button>
          }
        >
          {fxPairs.loading || fxReferences.loading ? (
            <LoadingState label="正在读取外汇市场" />
          ) : null}
          {fxPairs.error && fxReferences.error ? (
            <ErrorState message="人民币参考价与外币对即时询价暂时都不可用" />
          ) : null}
          <div className="fx-dashboard-strip">
            {fxReferences.dataset?.data.slice(0, 3).map((item) => (
              <div key={item.code}>
                <span>{item.code.replace("CNY", "/CNY")}</span>
                <strong>{formatNumber(item.mid, item.code === "JPYCNY" ? 4 : 5)}</strong>
                <ChangeValue value={item.change_pct} suffix="%" />
              </div>
            ))}
            {fxPairs.dataset?.data.slice(0, 4).map((item) => (
              <div key={item.code}>
                <span>{item.pair}</span>
                <strong>{formatNumber(item.mid, item.code.endsWith("JPY") ? 3 : 5)}</strong>
                <small>买 {formatNumber(item.bid, item.code.endsWith("JPY") ? 3 : 5)} · 卖 {formatNumber(item.ask, item.code.endsWith("JPY") ? 3 : 5)}</small>
              </div>
            ))}
          </div>
          <SourceFooter meta={fxReferences.dataset?.meta ?? fxPairs.dataset?.meta} />
        </Panel>
        ) : null}
      </div>
    </div>
  );
}

export function MoneyPage({ refreshSeed }: PageProps) {
  const rates = useDataset<RateItem[]>("/rates", refreshSeed);
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="LIQUIDITY"
        title="资金面"
        description="Shibor、FR/FDR 与政策利率的统一观察"
      />
      <DataMessage loading={rates.loading} error={rates.error} />
      {rates.dataset ? (
        <>
          <WarningBanner meta={rates.dataset.meta} />
          <div className="metrics-grid six">
            {rates.dataset.data.map((item) => (
              <article className="metric-card tall" key={item.name}>
                <span>{item.name}</span>
                <strong>{formatNumber(item.value, 4)}%</strong>
                <ChangeValue value={item.change_bp} />
                <small>期限 {item.tenor}</small>
              </article>
            ))}
          </div>
          <Panel title="最新定盘数据" eyebrow="FIXING">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>期限</th>
                    <th className="num">最新值</th>
                    <th className="num">日变动</th>
                    <th>判断</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.dataset.data.map((item) => (
                    <tr key={item.name}>
                      <td><strong>{item.name}</strong></td>
                      <td>{item.tenor}</td>
                      <td className="num mono">{formatNumber(item.value, 4)}%</td>
                      <td className="num">
                        <ChangeValue value={item.change_bp} />
                      </td>
                      <td>
                        <span className="tag">
                          {(item.change_bp ?? 0) > 2
                            ? "边际收紧"
                            : (item.change_bp ?? 0) < -2
                              ? "边际转松"
                              : "变化有限"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <SourceFooter meta={rates.dataset.meta} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}

export function CurvesPage({ refreshSeed }: PageProps) {
  const curves = useDataset<CurveData>("/curves", refreshSeed);
  const [historyDays, setHistoryDays] = useState(90);
  const [spreadHistory, setSpreadHistory] = useState<HistoryResponse | null>(null);
  useEffect(() => {
    if (!curves.dataset) return;
    let active = true;
    apiGet<HistoryResponse>(
      `/history?adapter=yield_curves&metric=spread_bp&series=10Y-1Y,10Y-5Y,30Y-10Y&days=${historyDays}`,
    )
      .then((value) => {
        if (!active) return;
        const embedded = curves.dataset?.data.history ?? [];
        if (!value.dates.length && embedded.length) {
          const keys = ["10Y-1Y", "10Y-5Y", "30Y-10Y"];
          setSpreadHistory({
            adapter: "yield_curves",
            metric: "spread_bp",
            unit: "BP",
            dates: embedded.map((item) => item.date),
            series: keys.map((key) => ({
              key,
              name: key,
              values: embedded.map((item) => item.spreads_bp[key] ?? null),
            })),
          });
        } else {
          setSpreadHistory(value);
        }
      })
      .catch(() => {
        if (active) setSpreadHistory(null);
      });
    return () => {
      active = false;
    };
  }, [curves.dataset?.meta.fetched_at, historyDays]);
  const curveMetrics = useMemo(() => {
    const data = curves.dataset?.data;
    if (!data) return [];
    const government = data.series.find(
      (series) => series.name.includes("国债") && series.name.includes("最新"),
    );
    if (!government) return [];
    const value = (tenor: string) => {
      const index = data.tenors.indexOf(tenor);
      return index >= 0 ? government.values[index] : null;
    };
    const spread = (longTenor: string, shortTenor: string) => {
      const longValue = value(longTenor);
      const shortValue = value(shortTenor);
      return longValue !== null && longValue !== undefined && shortValue !== null && shortValue !== undefined
        ? (longValue - shortValue) * 100
        : null;
    };
    const tenYearIndex = data.tenors.indexOf("10Y");
    return [
      { label: "10Y–1Y", value: spread("10Y", "1Y"), hint: "期限利差" },
      { label: "10Y–5Y", value: spread("10Y", "5Y"), hint: "中长端斜率" },
      { label: "30Y–10Y", value: spread("30Y", "10Y"), hint: "超长端斜率" },
      {
        label: "10Y 日变动",
        value: tenYearIndex >= 0 ? data.changes[tenYearIndex] : null,
        hint: "较前值",
      },
    ];
  }, [curves.dataset]);
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="TERM STRUCTURE"
        title="收益率曲线"
        description="对比国债与政策性金融债曲线，观察关键期限 BP 变化"
      />
      <DataMessage loading={curves.loading} error={curves.error} />
      {curves.dataset ? (
        <>
          <WarningBanner meta={curves.dataset.meta} />
          <div className="metrics-grid">
            {curveMetrics.map((metric) => (
              <article className="metric-card" key={metric.label}>
                <span>{metric.label}</span>
                <strong>{formatNumber(metric.value, 2)} BP</strong>
                <small>{metric.hint}</small>
              </article>
            ))}
          </div>
          <div className="two-column">
            <Panel title="曲线对比" eyebrow="YIELD">
              <Suspense fallback={<ChartFallback height={360} />}>
                <LineChart
                  categories={curves.dataset.data.tenors}
                  series={curves.dataset.data.series}
                  height={360}
                />
              </Suspense>
            </Panel>
            <Panel title="国债曲线变动" eyebrow="DAILY CHANGE">
              <Suspense fallback={<ChartFallback height={360} />}>
                <BarChart
                  categories={curves.dataset.data.tenors}
                  values={curves.dataset.data.changes}
                  height={360}
                />
              </Suspense>
            </Panel>
          </div>
          <Panel
            title="曲线利差历史"
            eyebrow="SPREAD HISTORY"
            action={
              <div className="history-range-control">
                {spreadHistory?.dates.length ? (
                  <small>
                    实际覆盖 {spreadHistory.dates[0]} 至 {spreadHistory.dates[spreadHistory.dates.length - 1]} · {spreadHistory.dates.length} 个交易日
                  </small>
                ) : null}
                <select
                  aria-label="曲线历史范围"
                  className="compact-select"
                  value={historyDays}
                  onChange={(event) => setHistoryDays(Number(event.target.value))}
                >
                  <option value={30}>近 30 天</option>
                  <option value={90}>近 90 天</option>
                  <option value={365}>近 1 年</option>
                </select>
              </div>
            }
          >
            {spreadHistory?.dates.length ? (
              <Suspense fallback={<ChartFallback height={300} />}>
                <LineChart
                  categories={spreadHistory.dates}
                  series={spreadHistory.series}
                  height={300}
                  unit=" BP"
                />
              </Suspense>
            ) : (
              <div className="empty-state compact-empty">
                <strong>正在积累可信历史序列</strong>
                <p>真实曲线更新后会自动回填最近可用交易日。</p>
              </div>
            )}
          </Panel>
          <Panel title="关键期限矩阵" eyebrow="CURVE MATRIX">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>曲线</th>
                    {curves.dataset.data.tenors.map((tenor) => (
                      <th className="num" key={tenor}>{tenor}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {curves.dataset.data.series.map((series) => (
                    <tr key={series.name}>
                      <td><strong>{series.name}</strong></td>
                      {series.values.map((value, index) => (
                        <td className="num mono" key={index}>
                          {formatNumber(value, 4)}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr>
                    <td><strong>国债日变动</strong></td>
                    {curves.dataset.data.changes.map((value, index) => (
                      <td className="num" key={index}>
                        <ChangeValue value={value} suffix="" />
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <SourceFooter meta={curves.dataset.meta} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}

export function BondsPage({ refreshSeed, initialQuery = "" }: PageProps) {
  const bonds = useDataset<SpotBond[]>("/bonds/spot", refreshSeed);
  const [query, setQuery] = useState(initialQuery);
  const [typeFilter, setTypeFilter] = useState("全部类型");
  const [minYield, setMinYield] = useState("");
  const [maxYield, setMaxYield] = useState("");
  const [minMove, setMinMove] = useState("");
  const [sortBy, setSortBy] = useState("volume_desc");
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const savedViews = useSavedViews<BondSavedView>(
    "akdesk-bond-views-v1",
    isBondSavedView,
  );
  useEffect(() => setQuery(initialQuery), [initialQuery]);
  const bondTypes = useMemo(
    () => ["全部类型", ...new Set((bonds.dataset?.data ?? []).map((item) => item.type))],
    [bonds.dataset],
  );
  const filtered = useMemo(() => {
    const rows = (bonds.dataset?.data ?? []).filter((item) => {
        const text = (item.code + item.name + item.type).toLowerCase();
        const yieldValue = item.yield;
        const moveValue = Math.abs(item.change_bp ?? 0);
        return (
          text.includes(query.trim().toLowerCase()) &&
          (typeFilter === "全部类型" || item.type === typeFilter) &&
          (!minYield || (yieldValue !== null && yieldValue >= Number(minYield))) &&
          (!maxYield || (yieldValue !== null && yieldValue <= Number(maxYield))) &&
          (!minMove || moveValue >= Number(minMove))
        );
      });
    return rows.sort((left, right) => {
      if (sortBy === "yield_desc") return (right.yield ?? -Infinity) - (left.yield ?? -Infinity);
      if (sortBy === "yield_asc") return (left.yield ?? Infinity) - (right.yield ?? Infinity);
      if (sortBy === "move_desc") return Math.abs(right.change_bp ?? 0) - Math.abs(left.change_bp ?? 0);
      return (right.volume ?? 0) - (left.volume ?? 0);
    });
  }, [bonds.dataset, maxYield, minMove, minYield, query, sortBy, typeFilter]);
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => setPage(1), [maxYield, minMove, minYield, query, sortBy, typeFilter]);
  useEffect(
    () => setPage((current) => clampPage(current, filtered.length, pageSize)),
    [filtered.length],
  );

  function exportCsv() {
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const rows = [
      ["债券代码", "代码状态", "债券名称", "类型", "成交净价", "最新收益率", "变动BP", "交易量"],
      ...filtered.map((item) => [
        item.code,
        item.code_verified === false ? "标准简称规则推导·需核验" : item.code ? "源提供" : "不可用",
        item.name,
        item.type,
        item.price,
        item.yield,
        item.change_bp,
        item.volume,
      ]),
    ];
    const blob = new Blob(
      ["\uFEFF" + rows.map((row) => row.map(escape).join(",")).join("\n")],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-现券-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="CASH BOND"
        title="现券市场"
        description="公开现券成交观察，不等同于银行间全市场实时成交"
      />
      <div className="filter-bar">
        <input
          aria-label="搜索债券代码、名称或类型"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索债券代码、名称或类型"
        />
        <select aria-label="债券类型" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          {bondTypes.map((type) => <option key={type}>{type}</option>)}
        </select>
        <input aria-label="最低收益率百分比" className="number-filter" type="number" step="0.01" value={minYield} onChange={(event) => setMinYield(event.target.value)} placeholder="最低收益率%" />
        <input aria-label="最高收益率百分比" className="number-filter" type="number" step="0.01" value={maxYield} onChange={(event) => setMaxYield(event.target.value)} placeholder="最高收益率%" />
        <input aria-label="最小绝对异动BP" className="number-filter" type="number" step="0.1" value={minMove} onChange={(event) => setMinMove(event.target.value)} placeholder="最小异动BP" />
        <select aria-label="现券排序方式" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          <option value="volume_desc">成交量优先</option>
          <option value="move_desc">异动优先</option>
          <option value="yield_desc">收益率从高到低</option>
          <option value="yield_asc">收益率从低到高</option>
        </select>
        <SavedViewControls
          manager={savedViews}
          value={{ typeFilter, minYield, maxYield, minMove, sortBy }}
          suggestedName={typeFilter === "全部类型" ? "我的现券筛选" : typeFilter}
          onLoad={(value) => {
            setTypeFilter(value.typeFilter);
            setMinYield(value.minYield);
            setMaxYield(value.maxYield);
            setMinMove(value.minMove);
            setSortBy(value.sortBy);
          }}
        />
        <button
          className="text-button"
          onClick={() => {
            setTypeFilter("全部类型");
            setMinYield("");
            setMaxYield("");
            setMinMove("");
            setSortBy("volume_desc");
          }}
        >
          重置筛选
        </button>
        <button className="secondary-button" onClick={exportCsv} disabled={!filtered.length}>
          <Download size={14} /> 导出 CSV
        </button>
        <span>{filtered.length} 条</span>
      </div>
      <DataMessage loading={bonds.loading} error={bonds.error} />
      {bonds.dataset ? (
        <Panel title="现券成交" eyebrow="PUBLIC DEALS">
          <WarningBanner meta={bonds.dataset.meta} />
          <div className="table-wrap large">
            <table>
              <thead>
                <tr>
                  <th>债券</th>
                  <th>类型</th>
                  <th className="num">成交净价</th>
                  <th className="num">最新收益率</th>
                  <th className="num">变动 BP</th>
                  <th className="num">交易量</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {paged.map((item) => (
                  <tr className={item.quality_state === "suspicious" ? "suspicious-row" : undefined} key={item.code + item.name}>
                    <td>
                      <strong>{item.name}</strong>
                      <small>
                        {item.code || "代码未提供"}
                        {item.code_verified === false ? " · 标准简称规则推导，需核验" : ""}
                      </small>
                    </td>
                    <td><span className="tag">{item.type}</span></td>
                    <td className="num mono">{formatNumber(item.price, 4)}</td>
                    <td className="num mono">{formatNumber(item.yield, 4)}%</td>
                    <td className="num"><ChangeValue value={item.change_bp} /></td>
                    <td className="num mono">{formatNumber(item.volume, 2)}</td>
                    <td>
                      {canWatchItem(item.code, item.quality_state) && item.code_verified !== false ? (
                        <div className="row-actions">
                          <WatchButton objectType="bond" objectId={item.code} name={item.name} />
                          <CreateProjectButton objectType="bond" objectId={item.code} objectName={item.name} source={bonds.dataset?.meta.source || ""} observationTime={bonds.dataset?.meta.observation_time} />
                        </div>
                      ) : (
                        <span className="tag muted-tag">
                          {item.quality_state === "suspicious"
                            ? "异常隔离"
                            : item.code_verified === false
                              ? "推导代码·需核验"
                              : "不可自选"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} total={filtered.length} pageSize={pageSize} onChange={setPage} />
          <SourceFooter meta={bonds.dataset.meta} />
        </Panel>
      ) : null}
    </div>
  );
}

export function FuturesPage({ refreshSeed, initialQuery = "" }: PageProps) {
  const futures = useDataset<TreasuryFuture[]>("/futures", refreshSeed);
  const filtered = useMemo(
    () =>
      (futures.dataset?.data ?? []).filter((item) =>
        (item.product + item.contract)
          .toLowerCase()
          .includes(initialQuery.trim().toLowerCase()),
      ),
    [futures.dataset, initialQuery],
  );
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="CFFEX"
        title="国债期货"
        description="TS、TF、T、TL 近季合约行情与期限结构观察"
      />
      <DataMessage loading={futures.loading} error={futures.error} />
      {futures.dataset ? (
        <>
          <WarningBanner meta={futures.dataset.meta} />
          <div className="futures-card-grid">
            {filtered.map((item) => (
              <article className="contract-card" key={item.product}>
                <header>
                  <span className="product-badge large">{item.product}</span>
                  <small>{item.contract}</small>
                  <WatchButton
                    objectType="future"
                    objectId={item.product}
                    name={item.contract}
                  />
                  <CreateProjectButton objectType="future" objectId={item.product} objectName={item.contract} source={futures.dataset?.meta.source || ""} observationTime={futures.dataset?.meta.observation_time} />
                </header>
                <strong>{formatNumber(item.price, 3)}</strong>
                <ChangeValue value={item.change_pct} suffix="%" />
                <dl>
                  <div><dt>成交量</dt><dd>{item.volume.toLocaleString()}</dd></div>
                  <div><dt>持仓量</dt><dd>{item.open_interest.toLocaleString()}</dd></div>
                </dl>
              </article>
            ))}
          </div>
          <Panel title="期限结构" eyebrow="CONTRACT MATRIX">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>品种</th>
                    <th>合约</th>
                    <th className="num">最新价</th>
                    <th className="num">涨跌幅</th>
                    <th className="num">成交量</th>
                    <th className="num">持仓量</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr key={item.product + item.contract}>
                      <td><span className="product-badge">{item.product}</span></td>
                      <td>{item.contract}</td>
                      <td className="num mono">{formatNumber(item.price, 3)}</td>
                      <td className="num">
                        <ChangeValue value={item.change_pct} suffix="%" />
                      </td>
                      <td className="num mono">{item.volume.toLocaleString()}</td>
                      <td className="num mono">{item.open_interest.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <SourceFooter meta={futures.dataset.meta} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}

export function ConvertiblesPage({ refreshSeed, initialQuery = "" }: PageProps) {
  const convertibles = useDataset<Convertible[]>("/convertibles", refreshSeed);
  const [query, setQuery] = useState(initialQuery);
  const [maxPrice, setMaxPrice] = useState("");
  const [maxPremium, setMaxPremium] = useState("");
  const [maxDoubleLow, setMaxDoubleLow] = useState("");
  const [minYtm, setMinYtm] = useState("");
  const [sortBy, setSortBy] = useState("double_low_asc");
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const savedViews = useSavedViews<ConvertibleSavedView>(
    "akdesk-convertible-views-v1",
    isConvertibleSavedView,
  );
  useEffect(() => setQuery(initialQuery), [initialQuery]);
  const filtered = useMemo(() => {
    const rows = (convertibles.dataset?.data ?? []).filter((item) =>
      (item.code + item.name + item.stock_name)
          .toLowerCase()
          .includes(query.trim().toLowerCase()) &&
      (!maxPrice || (item.price !== null && item.price <= Number(maxPrice))) &&
      (!maxPremium || (item.premium_pct !== null && item.premium_pct <= Number(maxPremium))) &&
      (!maxDoubleLow || (item.double_low !== null && item.double_low <= Number(maxDoubleLow))) &&
      (!minYtm || (item.ytm_pct !== null && item.ytm_pct >= Number(minYtm))),
    );
    return rows.sort((left, right) => {
      if (sortBy === "premium_asc") return (left.premium_pct ?? Infinity) - (right.premium_pct ?? Infinity);
      if (sortBy === "ytm_desc") return (right.ytm_pct ?? -Infinity) - (left.ytm_pct ?? -Infinity);
      if (sortBy === "price_asc") return (left.price ?? Infinity) - (right.price ?? Infinity);
      return (left.double_low ?? Infinity) - (right.double_low ?? Infinity);
    });
  }, [convertibles.dataset, maxDoubleLow, maxPremium, maxPrice, minYtm, query, sortBy]);
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => setPage(1), [maxDoubleLow, maxPremium, maxPrice, minYtm, query, sortBy]);
  useEffect(
    () => setPage((current) => clampPage(current, filtered.length, pageSize)),
    [filtered.length],
  );

  function exportCsv() {
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const rows = [
      ["转债代码", "数据层级", "转债名称", "正股", "现价", "涨跌幅", "转股价值", "溢价率", "双低", "YTM", "强赎状态"],
      ...filtered.map((item) => [
        item.code, item.data_tier === "price_only" ? "仅价格" : item.data_tier === "partial_comparison" ? "部分比价" : "完整比价", item.name, item.stock_name, item.price, item.change_pct,
        item.convert_value, item.premium_pct, item.double_low, item.ytm_pct, item.redeem_status,
      ]),
    ];
    const blob = new Blob(
      ["\uFEFF" + rows.map((row) => row.map(escape).join(",")).join("\n")],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-可转债-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="CONVERTIBLE"
        title="可转债"
        description="价格、转股溢价、双低与强赎风险观察"
      />
      <div className="filter-bar">
        <input
          aria-label="搜索转债代码、名称或正股"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索转债代码、名称或正股"
        />
        <input aria-label="最高转债价格" className="number-filter" type="number" step="0.1" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="最高价格" />
        <input aria-label="最高转股溢价率百分比" className="number-filter" type="number" step="0.1" value={maxPremium} onChange={(event) => setMaxPremium(event.target.value)} placeholder="最高溢价率%" />
        <input aria-label="最高双低值" className="number-filter" type="number" step="0.1" value={maxDoubleLow} onChange={(event) => setMaxDoubleLow(event.target.value)} placeholder="最高双低" />
        <input aria-label="最低到期收益率百分比" className="number-filter" type="number" step="0.1" value={minYtm} onChange={(event) => setMinYtm(event.target.value)} placeholder="最低YTM%" />
        <select aria-label="可转债排序方式" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          <option value="double_low_asc">双低从低到高</option>
          <option value="premium_asc">溢价率从低到高</option>
          <option value="ytm_desc">YTM 从高到低</option>
          <option value="price_asc">价格从低到高</option>
        </select>
        <SavedViewControls
          manager={savedViews}
          value={{ maxPrice, maxPremium, maxDoubleLow, minYtm, sortBy }}
          suggestedName="我的可转债筛选"
          onLoad={(value) => {
            setMaxPrice(value.maxPrice);
            setMaxPremium(value.maxPremium);
            setMaxDoubleLow(value.maxDoubleLow);
            setMinYtm(value.minYtm);
            setSortBy(value.sortBy);
          }}
        />
        <button
          className="text-button"
          onClick={() => {
            setMaxPrice("");
            setMaxPremium("");
            setMaxDoubleLow("");
            setMinYtm("");
            setSortBy("double_low_asc");
          }}
        >
          重置筛选
        </button>
        <button className="secondary-button" onClick={exportCsv} disabled={!filtered.length}>
          <Download size={14} /> 导出 CSV
        </button>
        <span>{filtered.length} 条</span>
      </div>
      <DataMessage loading={convertibles.loading} error={convertibles.error} />
      {convertibles.dataset ? (
        <Panel title="可转债比价" eyebrow="COMPARISON">
          <WarningBanner meta={convertibles.dataset.meta} />
          <div className="table-wrap large">
            <table>
              <thead>
                <tr>
                  <th>转债</th>
                  <th>正股</th>
                  <th className="num">现价</th>
                  <th className="num">涨跌幅</th>
                  <th className="num">转股价值</th>
                  <th className="num">溢价率</th>
                  <th className="num">双低</th>
                  <th className="num">YTM</th>
                  <th>强赎</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {paged.map((item) => (
                  <tr className={item.quality_state === "suspicious" ? "suspicious-row" : undefined} key={item.code}>
                    <td>
                      <strong>{item.name}</strong>
                      <small>{item.code} · {item.data_tier === "price_only" ? "仅价格" : item.data_tier === "partial_comparison" ? "部分比价" : "完整比价"}</small>
                    </td>
                    <td>{item.stock_name}</td>
                    <td className="num mono">{formatNumber(item.price, 3)}</td>
                    <td className="num">
                      <ChangeValue value={item.change_pct} suffix="%" />
                    </td>
                    <td className="num mono">{formatNumber(item.convert_value, 3)}</td>
                    <td className="num mono">{formatNumber(item.premium_pct, 2)}%</td>
                    <td className="num mono">{formatNumber(item.double_low, 2)}</td>
                    <td className="num mono">{formatNumber(item.ytm_pct, 2)}%</td>
                    <td>
                      <span className={classNames(
                        "tag",
                        item.redeem_status.includes("关注") && "warning",
                      )}>
                        {item.redeem_status}
                      </span>
                    </td>
                    <td>
                      {canWatchItem(item.code, item.quality_state) ? (
                        <div className="row-actions">
                          <WatchButton objectType="convertible" objectId={item.code} name={item.name} />
                          {item.research_eligible !== false ? (
                            <CreateProjectButton objectType="convertible" objectId={item.code} objectName={item.name} source={convertibles.dataset?.meta.source || ""} observationTime={convertibles.dataset?.meta.observation_time} />
                          ) : (
                            <span className="tag muted-tag">
                              {item.data_tier === "price_only" ? "仅价格" : "字段不全"}·不立项
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="tag muted-tag">异常隔离</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} total={filtered.length} pageSize={pageSize} onChange={setPage} />
          <SourceFooter meta={convertibles.dataset.meta} />
        </Panel>
      ) : null}
    </div>
  );
}

export function EventsPage({ refreshSeed }: PageProps) {
  const events = useDataset<MarketEvent[]>("/events", refreshSeed);
  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="EVENTS"
        title="发行与事件"
        description="国债发行、缴款、上市与关键数据日程"
      />
      <DataMessage loading={events.loading} error={events.error} />
      {events.dataset ? (
        <Panel title="事件时间线" eyebrow="CALENDAR">
          <WarningBanner meta={events.dataset.meta} />
          <div className="timeline">
            {events.dataset.data.map((item, index) => (
              <article className="timeline-item" key={item.date + item.title + index}>
                <div className="timeline-date">
                  <CalendarDays size={17} />
                  <strong>{item.date}</strong>
                </div>
                <div className="timeline-content">
                  <span className={"importance " + item.importance} />
                  <div>
                    <span className="tag">{item.type}</span>
                    <h3>{item.title}</h3>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <SourceFooter meta={events.dataset.meta} />
        </Panel>
      ) : null}
    </div>
  );
}

export function WatchlistPage({ navigate }: { navigate: (page: string, query?: string) => void }) {
  const { items, loading, remove, update } = useWatchlist();
  const [enriched, setEnriched] = useState<EnrichedWatchlistItem[]>([]);
  const [groupFilter, setGroupFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  useEffect(() => {
    if (!items.length) { setEnriched([]); return; }
    apiGet<EnrichedWatchlistItem[]>("/watchlists/enriched")
      .then(setEnriched)
      .catch(() => setEnriched([]));
  }, [items]);
  const groups = useMemo(
    () => Array.from(new Set(items.map((item) => item.group_name))).sort(),
    [items],
  );
  const visible = groupFilter
    ? items.filter((item) => item.group_name === groupFilter)
    : items;

  async function revise(itemId: number, values: Record<string, unknown>) {
    setSavingId(itemId);
    setError(null);
    try {
      await update(itemId, values);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自选研究信息保存失败");
    } finally {
      setSavingId(null);
    }
  }

  async function removeItem(itemId: number, name: string) {
    if (!window.confirm(`确认将“${name}”移出自选研究？`)) return;
    setSavingId(itemId);
    setError(null);
    try {
      await remove(itemId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自选移除失败");
    } finally {
      setSavingId(null);
    }
  }

  const objectTypeLabels = {
    bond: "现券",
    future: "国债期货",
    convertible: "可转债",
    macro: "宏观指标",
    fx: "外汇",
  };

  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="WATCHLIST"
        title="自选研究工作台"
        description="统一管理证券与宏观指标，记录分组、状态和复盘计划"
      />
      {error ? <ErrorState message={error} /> : null}
      <Panel
        title="统一自选"
        eyebrow="LOCAL RESEARCH"
        action={
          groups.length ? (
            <select className="compact-select" value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)} aria-label="按自选分组筛选">
              <option value="">全部分组</option>
              {groups.map((group) => <option value={group} key={group}>{group}</option>)}
            </select>
          ) : null
        }
      >
        {loading ? <LoadingState /> : null}
        {!loading && items.length === 0 ? (
          <div className="empty-state">
            <Star size={28} />
            <strong>还没有研究自选</strong>
            <p>可从证券列表或宏观数据库加入自选。</p>
          </div>
        ) : null}
        {visible.length ? (
          <div className="research-watch-grid">
            {visible.map((item) => (
              <article className={classNames("research-watch-card", item.pinned && "pinned")} key={item.id}>
                <header>
                  <div>
                    <span className="tag">{objectTypeLabels[item.object_type]}</span>
                    <strong>{item.name}</strong>
                    <small>{item.object_id} · 更新 {formatDateTime(item.updated_at)}</small>
                  </div>
                  <div className="watch-card-actions">
                    <CreateProjectButton objectType={item.object_type} objectId={item.object_id} objectName={item.name} source={enriched.find((value) => value.id === item.id)?.source_meta?.source} observationTime={enriched.find((value) => value.id === item.id)?.source_meta?.observation_time} />
                    <button
                      className={classNames("icon-button", item.pinned && "active")}
                      onClick={() => revise(item.id, { pinned: !item.pinned })}
                      aria-label={item.pinned ? "取消置顶" : "置顶"}
                      disabled={savingId === item.id}
                    ><Pin size={14} /></button>
                    <button className="icon-button danger" onClick={() => removeItem(item.id, item.name)} aria-label="移除自选" disabled={savingId === item.id}><Trash2 size={14} /></button>
                  </div>
                </header>
                {(() => {
                  const live = enriched.find((value) => value.id === item.id);
                  return (
                    <div className="watch-quote-strip">
                      {live?.quote ? <><strong>{live.quote.primary_label} {formatNumber(live.quote.primary_value, 4)}{live.quote.primary_unit}</strong><span>{live.quote.change_label} {formatNumber(live.quote.change_value, 3)}{live.quote.change_unit}</span></> : <span>{live?.quote_status === "request_required" ? "宏观数据按需请求" : "当前缓存未匹配行情"}</span>}
                      <small>{live?.source_meta ? `${marketStatusLabels[live.source_meta.market_status] || live.source_meta.market_status} · ${trustLevelLabels[live.source_meta.trust_level] || live.source_meta.trust_level} · ${live.source_meta.observation_time || "时间待确认"}` : "研究行情状态待检查"}</small>
                      <button className="text-button" onClick={() => navigate(live?.page || (item.object_type === "bond" ? "bonds" : item.object_type === "future" ? "futures" : item.object_type === "convertible" ? "convertibles" : item.object_type === "fx" ? "fx" : "macro"), item.object_id)}>查看详情 <ChevronRight size={13} /></button>
                    </div>
                  );
                })()}
                <div className="watch-research-fields">
                  <label><span>分组</span><input key={`group-${item.updated_at}`} defaultValue={item.group_name} onBlur={(event) => event.target.value.trim() && event.target.value.trim() !== item.group_name ? revise(item.id, { group_name: event.target.value.trim() }) : undefined} /></label>
                  <label><span>研究状态</span><select value={item.research_status} onChange={(event) => revise(item.id, { research_status: event.target.value })}>
                    <option value="draft">待研究</option><option value="tracking">跟踪中</option><option value="formed">已形成观点</option><option value="review">待复盘</option><option value="archived">已归档</option>
                  </select></label>
                  <label><span>下次复盘</span><input type="date" value={item.next_review_date || ""} onChange={(event) => revise(item.id, { next_review_date: event.target.value || null })} /></label>
                  <label><span>标签</span><input key={`tags-${item.updated_at}`} defaultValue={item.tags.join("，")} placeholder="重点，通胀" onBlur={(event) => revise(item.id, { tags: event.target.value.split(/[，,]/).map((value) => value.trim()).filter(Boolean) })} /></label>
                  <label className="span-2"><span>研究备注</span><textarea key={`note-${item.updated_at}`} defaultValue={item.note} placeholder="记录关注原因或待验证问题" onBlur={(event) => event.target.value !== item.note ? revise(item.id, { note: event.target.value }) : undefined} /></label>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="market-clock">
        <Clock3 size={15} />
        <span>{new Date().toLocaleDateString("zh-CN")}</span>
      </div>
    </header>
  );
}

export function InlineRefresh({ onClick }: { onClick: () => void }) {
  return (
    <button className="icon-button" onClick={onClick} title="刷新">
      <RefreshCcw size={15} />
    </button>
  );
}
