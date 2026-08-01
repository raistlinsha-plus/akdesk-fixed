import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Archive,
  BookOpenCheck,
  CirclePlus,
  Clock3,
  Download,
  ExternalLink,
  Inbox,
  Layers3,
  Link2,
  LoaderCircle,
  Newspaper,
  RefreshCcw,
  Save,
  Settings2,
  Trash2,
} from "lucide-react";
import {
  apiDelete,
  apiDownload,
  apiGet,
  apiGetShared,
  apiPatch,
  apiPost,
} from "../api";
import {
  ErrorState,
  LoadingState,
  Panel,
  formatDateTime,
  formatNumber,
} from "../components/UI";
import { AiInsightCard } from "../components/AiInsightCard";
import { parseResearchTags } from "../researchUtils";
import {
  addTopicComponent,
  filterEvidenceBasket,
  filterTopicLibrary,
  filterTopicTimeline,
  hasTimeSeriesData,
  isRemoteTopicComponent,
  mergeTopicTimeline,
  toggleNumericId,
  topicEvidenceEvents,
  type EvidenceBasketScope,
  type EvidenceBasketSource,
  type TopicLibraryStatus,
  type TopicTimelineCategory,
} from "../topicResearch";
import type {
  Dataset,
  EvidenceBasketItem,
  GdeltEventItem,
  GdeltEventRadarData,
  HistoryResponse,
  MacroChartData,
  MarketResearchBrief,
  ResearchProject,
  ResearchProjectSummary,
  ResearchTopic,
  ResearchTopicComponent,
  ResearchTopicStatus,
  ResearchTopicTemplate,
  ResearchTopicTimelineCursor,
  ResearchTopicTimelineItem,
  ResearchTopicTimelinePage,
  ResearchTopicWorkspace,
  SovereignComparison,
} from "../types";
import { PageHeading } from "./MarketPages";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.LineChart })),
);

const topicStatusLabels: Record<ResearchTopicStatus, string> = {
  active: "持续跟踪",
  review: "待专题复盘",
  archived: "已归档",
};

const timelineLabels: Record<string, string> = {
  market_snapshot: "市场快照",
  sovereign_update: "主权比较",
  fred_reference: "FRED 引用",
  gdelt_clue: "GDELT 线索",
  evidence: "研究证据",
  note: "研究笔记",
  counter_evidence: "反证",
  task: "任务",
  review: "复盘",
  release_review: "发布复盘",
  project_created: "项目创建",
  project_updated: "观点变化",
  project_imported: "项目导入",
};

const componentPresets: ResearchTopicComponent[] = [
  {
    id: "market",
    component_type: "market_pulse",
    title: "当前市场脉搏",
    config: {},
    order: 10,
  },
  {
    id: "china-curve",
    component_type: "market_history",
    title: "中国国债期限结构",
    config: {
      adapter: "yield_curves",
      metric: "yield",
      series: ["1Y", "5Y", "10Y", "30Y"],
      days: 120,
      unit: "%",
    },
    order: 20,
  },
  {
    id: "rmb-reference",
    component_type: "market_history",
    title: "人民币参考价",
    config: {
      adapter: "fx_rmb_reference",
      metric: "mid",
      series: ["USDCNY", "EURCNY", "JPYCNY"],
      days: 120,
      unit: "CNY",
    },
    order: 30,
  },
  {
    id: "us-rates",
    component_type: "fred_chart",
    title: "美国名义与实际利率",
    config: {
      series: ["DGS10", "DFII10", "T10YIE"],
      years: 5,
      transform: "level",
    },
    order: 40,
  },
  {
    id: "us-inflation",
    component_type: "fred_chart",
    title: "美国通胀",
    config: {
      series: ["CPIAUCSL", "CPILFESL"],
      years: 10,
      transform: "yoy",
    },
    order: 50,
  },
  {
    id: "global-growth",
    component_type: "sovereign_compare",
    title: "主要经济体增长",
    config: {
      countries: ["CHN", "USA", "JPN", "DEU"],
      indicator: "NY.GDP.MKTP.KD.ZG",
      start_year: new Date().getFullYear() - 10,
      end_year: new Date().getFullYear(),
      view: "level",
    },
    order: 60,
  },
  {
    id: "event-radar",
    component_type: "event_radar",
    title: "外部事件雷达",
    config: {
      query: "sovereign debt",
      days: 7,
      limit: 20,
      sort: "datedesc",
    },
    order: 65,
  },
  {
    id: "summary",
    component_type: "project_summary",
    title: "关联项目摘要",
    config: {},
    order: 70,
  },
  {
    id: "evidence",
    component_type: "recent_evidence",
    title: "最近证据",
    config: {},
    order: 80,
  },
];

function configStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map(String).map((item) => item.trim()).filter(Boolean)
    : [];
}

function ComponentShell({
  title,
  children,
  wide = false,
  action,
}: {
  title: string;
  children: ReactNode;
  wide?: boolean;
  action?: ReactNode;
}) {
  return (
    <Panel
      title={title}
      eyebrow="SAVED TOPIC VIEW"
      className={`topic-component-panel${wide ? " topic-component-panel-wide" : ""}`}
      action={action}
    >
      {children}
    </Panel>
  );
}

function useTopicComponentData<T>(
  path: string,
  errorMessage: string,
  refreshToken: number,
  ttlMs = 30_000,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiGetShared<T>(path, { ttlMs, force: refreshToken > 0 })
      .then((value) => active && setData(value))
      .catch((reason: unknown) =>
        active && setError(reason instanceof Error ? reason.message : errorMessage),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [errorMessage, path, refreshToken, ttlMs]);
  return { data, error, loading };
}

function ComponentRefreshButton({
  loading,
  onRefresh,
}: {
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <button
      type="button"
      className="icon-button topic-component-refresh"
      onClick={onRefresh}
      disabled={loading}
      aria-label={loading ? "组件正在刷新" : "刷新组件"}
      title={loading ? "正在刷新" : "刷新组件"}
    >
      <RefreshCcw className={loading ? "spin" : undefined} size={14} />
    </button>
  );
}

interface RemoteTopicComponentProps {
  component: ResearchTopicComponent;
  refreshToken: number;
  onRefresh: () => void;
  topicId?: number;
  onEvidenceAdded?: (item: EvidenceBasketItem) => void;
}

function MarketPulseComponent({ component, refreshToken, onRefresh }: RemoteTopicComponentProps) {
  const { data: brief, error, loading } = useTopicComponentData<MarketResearchBrief>(
    "/research/market-brief",
    "市场脉搏加载失败",
    refreshToken,
    15_000,
  );
  return (
    <ComponentShell
      title={component.title}
      wide
      action={<ComponentRefreshButton loading={loading} onRefresh={onRefresh} />}
    >
      {error ? <ErrorState message={error} /> : null}
      {!brief && loading ? <LoadingState /> : null}
      {brief ? (
        <div className="topic-market-pulse">
          <div>
            <span>{brief.market_status}</span>
            <strong>{brief.headline}</strong>
            <small>{formatDateTime(brief.generated_at)}</small>
          </div>
          <div>
            {brief.signals.slice(0, 6).map((signal) => (
              <article key={signal.id}>
                <span className={`signal-severity ${signal.severity}`}>
                  {signal.severity === "high" ? "显著" : signal.severity === "watch" ? "关注" : "信息"}
                </span>
                <strong>{signal.title}</strong>
                <small>{signal.summary}</small>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </ComponentShell>
  );
}

function MarketHistoryComponent({ component, refreshToken, onRefresh }: RemoteTopicComponentProps) {
  const adapter = String(component.config.adapter || "");
  const metric = String(component.config.metric || "");
  const series = configStrings(component.config.series);
  const days = Number(component.config.days || 120);
  const unit = String(component.config.unit || "");
  const path =
    `/history?adapter=${encodeURIComponent(adapter)}` +
    `&metric=${encodeURIComponent(metric)}` +
    `&series=${encodeURIComponent(series.join(","))}&days=${days}`;
  const { data: history, error, loading } = useTopicComponentData<HistoryResponse>(
    path,
    "本地历史加载失败",
    refreshToken,
  );
  const hasHistory = history ? hasTimeSeriesData(history.dates, history.series) : false;
  return (
    <ComponentShell
      title={component.title}
      action={<ComponentRefreshButton loading={loading} onRefresh={onRefresh} />}
    >
      {error ? <ErrorState message={error} /> : null}
      {!history && loading ? <LoadingState /> : null}
      {history && !hasHistory ? (
        <div className="empty-state compact-empty topic-component-empty" role="status">
          <Archive size={24} />
          <strong>尚未积累可绘制的本地历史</strong>
          <p>先在对应市场页面获取可信数据；后续快照会逐步形成历史序列，也可以点击右上角刷新重试。</p>
        </div>
      ) : null}
      {history && hasHistory ? (
        <>
          <Suspense fallback={<div className="chart-loading skeleton" style={{ height: 300 }} />}>
            <LineChart
              categories={history.dates}
              series={history.series}
              height={300}
              unit={unit ? ` ${unit}` : ""}
            />
          </Suspense>
          <p className="method-note">
            本地可信历史 · {history.dates[0] || "—"} 至 {history.dates[history.dates.length - 1] || "—"} · 缺失日期保持为空
          </p>
        </>
      ) : null}
    </ComponentShell>
  );
}

function FredChartComponent({ component, refreshToken, onRefresh }: RemoteTopicComponentProps) {
  const series = configStrings(component.config.series);
  const years = Number(component.config.years || 5);
  const transform = String(component.config.transform || "level");
  const path =
    `/macro/chart?series=${encodeURIComponent(series.join(","))}` +
    `&years=${years}&transform=${encodeURIComponent(transform)}`;
  const { data: chart, error, loading } = useTopicComponentData<Dataset<MacroChartData>>(
    path,
    "FRED 组件加载失败",
    refreshToken,
  );
  return (
    <ComponentShell
      title={component.title}
      action={<ComponentRefreshButton loading={loading} onRefresh={onRefresh} />}
    >
      {error ? <ErrorState message={error} /> : null}
      {!chart && loading ? <LoadingState /> : null}
      {chart ? (
        <>
          <Suspense fallback={<div className="chart-loading skeleton" style={{ height: 300 }} />}>
            <LineChart
              categories={chart.data.dates}
              series={chart.data.series}
              height={300}
              unit={transform === "yoy" ? " %" : ""}
            />
          </Suspense>
          <p className="method-note">
            FRED 请求级读取 · {chart.data.transform_source} · 专题仅保存序列与变换配置，不持久化观测值
          </p>
        </>
      ) : null}
    </ComponentShell>
  );
}

function SovereignComponent({ component, refreshToken, onRefresh }: RemoteTopicComponentProps) {
  const countries = configStrings(component.config.countries);
  const indicator = String(component.config.indicator || "NY.GDP.MKTP.KD.ZG");
  const startYear = Number(component.config.start_year || new Date().getFullYear() - 10);
  const endYear = Number(component.config.end_year || new Date().getFullYear());
  const view = String(component.config.view || "level");
  const path =
    `/sovereign/compare?countries=${encodeURIComponent(countries.join(","))}` +
    `&indicator=${encodeURIComponent(indicator)}` +
    `&start_year=${startYear}&end_year=${endYear}&view=${view}`;
  const { data: comparison, error, loading } = useTopicComponentData<Dataset<SovereignComparison>>(
    path,
    "主权组件加载失败",
    refreshToken,
  );
  return (
    <ComponentShell
      title={component.title}
      action={<ComponentRefreshButton loading={loading} onRefresh={onRefresh} />}
    >
      {error ? <ErrorState message={error} /> : null}
      {!comparison && loading ? <LoadingState /> : null}
      {comparison ? (
        <>
          <div className="topic-sovereign-metrics">
            <div><span>指标</span><strong>{comparison.data.indicator.title_zh}</strong></div>
            <div><span>共同年份</span><strong>{comparison.data.latest_comparable_year || "无"}</strong></div>
            <div><span>覆盖率</span><strong>{formatNumber(comparison.data.coverage.ratio * 100, 1)}%</strong></div>
          </div>
          <Suspense fallback={<div className="chart-loading skeleton" style={{ height: 300 }} />}>
            <LineChart
              categories={comparison.data.years}
              series={comparison.data.series}
              height={300}
              unit={comparison.data.indicator.unit ? ` ${comparison.data.indicator.unit}` : ""}
            />
          </Suspense>
          <p className="method-note">{comparison.data.comparison_notice}</p>
        </>
      ) : null}
    </ComponentShell>
  );
}

function EventRadarComponent({
  component,
  refreshToken,
  onRefresh,
  topicId,
  onEvidenceAdded,
}: RemoteTopicComponentProps) {
  const query = String(component.config.query || "");
  const days = Number(component.config.days || 7);
  const limit = Number(component.config.limit || 20);
  const sort = String(component.config.sort || "datedesc");
  const path =
    `/gdelt/events?query=${encodeURIComponent(query)}` +
    `&days=${days}&limit=${limit}&sort=${encodeURIComponent(sort)}` +
    `&refresh=${refreshToken > 0 ? "true" : "false"}`;
  const { data: radar, error, loading } = useTopicComponentData<Dataset<GdeltEventRadarData>>(
    path,
    "GDELT 事件线索加载失败",
    refreshToken,
    12 * 60 * 60 * 1_000,
  );
  const [adding, setAdding] = useState<string | null>(null);
  const [added, setAdded] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function addClue(article: GdeltEventItem) {
    setAdding(article.id);
    setSaveError(null);
    try {
      const saved = await apiPost<EvidenceBasketItem>("/research/evidence-basket", {
        evidence_type: "note",
        title: article.title,
        payload: {
          provider: "GDELT",
          storage_mode: "reference_only",
          verification_status: "unverified_clue",
          query,
          article_url: article.url,
          domain: article.domain,
          seen_at: article.seen_at,
          language: article.language,
          source_country: article.source_country,
          retrieved_at: radar?.meta.fetched_at,
          attribution: radar?.data.attribution || "The GDELT Project",
          terms_url: radar?.data.license_url,
        },
        source_summary: `GDELT 事件线索（待核验） · ${article.domain || "未知来源"}`,
        observation_start: article.seen_at?.slice(0, 10) || null,
        observation_end: article.seen_at?.slice(0, 10) || null,
        origin_page: "topic-research",
        topic_id: topicId || null,
      });
      setAdded((current) => [...current, article.id]);
      onEvidenceAdded?.(saved);
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "线索加入证据篮失败");
    } finally {
      setAdding(null);
    }
  }

  return (
    <ComponentShell
      title={component.title}
      wide
      action={<ComponentRefreshButton loading={loading} onRefresh={onRefresh} />}
    >
      {error ? <ErrorState message={error} /> : null}
      {saveError ? <p className="warning-banner" role="alert">{saveError}</p> : null}
      {!radar && loading ? <LoadingState /> : null}
      {radar ? (
        <>
          <div className="event-radar-summary">
            <div><span>检索词</span><strong>{radar.data.query}</strong></div>
            <div><span>线索</span><strong>{radar.data.article_count}</strong></div>
            <div><span>来源</span><strong>{radar.data.source_count}</strong></div>
            <div><span>来源国家</span><strong>{radar.data.country_count || "—"}</strong></div>
          </div>
          {radar.data.articles.length ? (
            <div className="event-radar-list" role="list" aria-label={`${component.title}事件线索`}>
              {radar.data.articles.map((article) => {
                const isAdded = added.includes(article.id);
                return (
                  <article role="listitem" key={article.id}>
                    <Newspaper size={15} />
                    <div>
                      <a href={article.url} target="_blank" rel="noreferrer">
                        {article.title} <ExternalLink size={11} />
                      </a>
                      <small>
                        {article.domain || "未知来源"}
                        {article.source_country ? ` · ${article.source_country}` : ""}
                        {article.language ? ` · ${article.language}` : ""}
                        {article.seen_at ? ` · 本机 ${formatDateTime(article.seen_at)}` : ""}
                      </small>
                    </div>
                    <button
                      type="button"
                      className="secondary-button compact"
                      onClick={() => addClue(article)}
                      disabled={adding === article.id || isAdded}
                    >
                      {adding === article.id ? <LoaderCircle className="spin" size={13} /> : <Inbox size={13} />}
                      {isAdded ? "已加入证据篮" : "加入证据篮"}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty-state compact-empty">
              <Newspaper size={24} />
              <strong>当前窗口没有匹配线索</strong>
              <p>可在专题设置中调整检索词、时间范围或排序方式。</p>
            </div>
          )}
          <p className="method-note">
            {radar.data.notice} · {radar.meta.data_state === "cached" ? "本地元数据缓存" : "本次按需请求"} · {radar.data.attribution}
          </p>
        </>
      ) : null}
    </ComponentShell>
  );
}

function ProjectSummaryComponent({
  component,
  summaries,
}: {
  component: ResearchTopicComponent;
  summaries: ResearchProjectSummary[];
}) {
  return (
    <ComponentShell title={component.title} wide>
      {summaries.length ? (
        <div className="topic-project-summaries">
          {summaries.map((summary) => (
            <article key={summary.project_id}>
              <header>
                <div><strong>{summary.title}</strong><span>置信度 {summary.confidence}</span></div>
                <span className={`research-status ${summary.status}`}>{summary.status}</span>
              </header>
              <p>{summary.question || "尚未填写研究问题"}</p>
              <div className="topic-summary-columns">
                <div><span>当前结论</span><strong>{summary.conclusion || "尚未形成结论"}</strong></div>
                <div><span>支持证据</span><strong>{summary.supporting_evidence.length} 项</strong></div>
                <div><span>反证</span><strong>{summary.counter_evidence.length} 项</strong></div>
                <div><span>未完成任务</span><strong>{summary.open_tasks.length} 项</strong></div>
              </div>
              {summary.gaps.length ? <small>待补齐：{summary.gaps.join("；")}</small> : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state compact-empty">
          <BookOpenCheck size={24} />
          <strong>尚未关联研究项目</strong>
          <p>在专题设置中选择项目后，这里会按固定规则整理问题、证据、反证与任务。</p>
        </div>
      )}
    </ComponentShell>
  );
}

function RecentEvidenceComponent({
  component,
  timeline,
}: {
  component: ResearchTopicComponent;
  timeline: ResearchTopicTimelineItem[];
}) {
  const evidence = topicEvidenceEvents(timeline);
  return (
    <ComponentShell title={component.title}>
      {evidence.length ? (
        <div className="topic-recent-evidence">
          {evidence.slice(0, 8).map((item) => (
            <article key={item.id}>
              <span>{timelineLabels[item.event_type] || item.event_type}</span>
              <strong>{item.title}</strong>
              <small>{item.project_title} · {item.observation_time || formatDateTime(item.event_time)}</small>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state compact-empty"><Layers3 size={24} /><strong>尚无专题证据</strong></div>
      )}
    </ComponentShell>
  );
}

function TopicComponentView({
  component,
  summaries,
  timeline,
  refreshToken,
  onRefresh,
  topicId,
  onEvidenceAdded,
}: {
  component: ResearchTopicComponent;
  summaries: ResearchProjectSummary[];
  timeline: ResearchTopicTimelineItem[];
  refreshToken: number;
  onRefresh: () => void;
  topicId: number;
  onEvidenceAdded: (item: EvidenceBasketItem) => void;
}) {
  if (component.component_type === "market_pulse") {
    return <MarketPulseComponent component={component} refreshToken={refreshToken} onRefresh={onRefresh} />;
  }
  if (component.component_type === "market_history") {
    return <MarketHistoryComponent component={component} refreshToken={refreshToken} onRefresh={onRefresh} />;
  }
  if (component.component_type === "fred_chart") {
    return <FredChartComponent component={component} refreshToken={refreshToken} onRefresh={onRefresh} />;
  }
  if (component.component_type === "sovereign_compare") {
    return <SovereignComponent component={component} refreshToken={refreshToken} onRefresh={onRefresh} />;
  }
  if (component.component_type === "event_radar") {
    return <EventRadarComponent component={component} refreshToken={refreshToken} onRefresh={onRefresh} topicId={topicId} onEvidenceAdded={onEvidenceAdded} />;
  }
  if (component.component_type === "project_summary") {
    return <ProjectSummaryComponent component={component} summaries={summaries} />;
  }
  return <RecentEvidenceComponent component={component} timeline={timeline} />;
}

function DeferredTopicComponent({
  component,
  summaries,
  timeline,
  topicId,
  onEvidenceAdded,
}: {
  component: ResearchTopicComponent;
  summaries: ResearchProjectSummary[];
  timeline: ResearchTopicTimelineItem[];
  topicId: number;
  onEvidenceAdded: (item: EvidenceBasketItem) => void;
}) {
  const anchor = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(!isRemoteTopicComponent(component));
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (visible || !isRemoteTopicComponent(component)) return;
    const element = anchor.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [component, visible]);

  const wide = ["market_pulse", "event_radar", "project_summary"].includes(
    component.component_type,
  );
  return (
    <div
      ref={anchor}
      className={wide ? "topic-component-deferred-wide" : undefined}
    >
      {visible ? (
        <TopicComponentView
          component={component}
          summaries={summaries}
          timeline={timeline}
          refreshToken={refreshToken}
          onRefresh={() => setRefreshToken((value) => value + 1)}
          topicId={topicId}
          onEvidenceAdded={onEvidenceAdded}
        />
      ) : (
        <ComponentShell title={component.title} wide={wide}>
          <div className="topic-component-placeholder" aria-busy="true">
            <LoaderCircle size={18} />
            <span>滚动到此组件时加载数据</span>
          </div>
        </ComponentShell>
      )}
    </div>
  );
}

function TopicComponentEditor({
  component,
  onChange,
  onRemove,
}: {
  component: ResearchTopicComponent;
  onChange: (component: ResearchTopicComponent) => void;
  onRemove: () => void;
}) {
  function updateConfig(key: string, value: unknown) {
    onChange({
      ...component,
      config: { ...component.config, [key]: value },
    });
  }

  const series = configStrings(component.config.series).join(", ");
  const countries = configStrings(component.config.countries).join(", ");
  return (
    <article className="topic-component-editor">
      <details>
        <summary>
          <span><Layers3 size={12} /> {component.title}</span>
          <small>{component.component_type}</small>
        </summary>
        <div className="topic-component-editor-fields">
          <label className="span-2">
            <span>组件标题</span>
            <input
              value={component.title}
              onChange={(event) => onChange({ ...component, title: event.target.value })}
            />
          </label>
          {component.component_type === "market_history" ? (
            <>
              <label><span>本地数据源</span><select value={String(component.config.adapter || "yield_curves")} onChange={(event) => updateConfig("adapter", event.target.value)}><option value="yield_curves">中国国债曲线</option><option value="fx_rmb_reference">人民币参考价</option></select></label>
              <label><span>指标字段</span><input value={String(component.config.metric || "yield")} onChange={(event) => updateConfig("metric", event.target.value)} /></label>
              <label className="span-2"><span>序列（逗号分隔）</span><input value={series} onChange={(event) => updateConfig("series", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} /></label>
              <label><span>历史天数</span><input type="number" min={7} max={3650} value={Number(component.config.days || 120)} onChange={(event) => updateConfig("days", Number(event.target.value))} /></label>
              <label><span>单位</span><input value={String(component.config.unit || "")} onChange={(event) => updateConfig("unit", event.target.value)} /></label>
            </>
          ) : null}
          {component.component_type === "fred_chart" ? (
            <>
              <label className="span-2"><span>FRED 序列（逗号分隔）</span><input value={series} onChange={(event) => updateConfig("series", event.target.value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean))} /></label>
              <label><span>时间范围</span><input type="number" min={1} max={30} value={Number(component.config.years || 5)} onChange={(event) => updateConfig("years", Number(event.target.value))} /></label>
              <label><span>变换</span><select value={String(component.config.transform || "level")} onChange={(event) => updateConfig("transform", event.target.value)}><option value="level">原值</option><option value="change">变化</option><option value="yoy">同比</option><option value="normalize">标准化起点</option><option value="zscore">Z-Score</option></select></label>
            </>
          ) : null}
          {component.component_type === "sovereign_compare" ? (
            <>
              <label className="span-2"><span>经济体代码（逗号分隔）</span><input value={countries} onChange={(event) => updateConfig("countries", event.target.value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean))} /></label>
              <label className="span-2"><span>World Bank 指标</span><input value={String(component.config.indicator || "NY.GDP.MKTP.KD.ZG")} onChange={(event) => updateConfig("indicator", event.target.value.toUpperCase())} /></label>
              <label><span>起始年份</span><input type="number" min={1960} max={2100} value={Number(component.config.start_year || 2016)} onChange={(event) => updateConfig("start_year", Number(event.target.value))} /></label>
              <label><span>结束年份</span><input type="number" min={1960} max={2100} value={Number(component.config.end_year || new Date().getFullYear())} onChange={(event) => updateConfig("end_year", Number(event.target.value))} /></label>
              <label><span>比较方式</span><select value={String(component.config.view || "level")} onChange={(event) => updateConfig("view", event.target.value)}><option value="level">水平值</option><option value="change">单年变化</option><option value="rank">排名</option><option value="zscore">Z-Score</option></select></label>
            </>
          ) : null}
          {component.component_type === "event_radar" ? (
            <>
              <label className="span-2">
                <span>GDELT 检索词</span>
                <input
                  value={String(component.config.query || "")}
                  onChange={(event) => updateConfig("query", event.target.value)}
                  placeholder={'例如："issuer name" OR default'}
                  maxLength={200}
                />
              </label>
              <label>
                <span>回看天数</span>
                <input type="number" min={1} max={90} value={Number(component.config.days || 7)} onChange={(event) => updateConfig("days", Number(event.target.value))} />
              </label>
              <label>
                <span>最多线索</span>
                <input type="number" min={5} max={50} value={Number(component.config.limit || 20)} onChange={(event) => updateConfig("limit", Number(event.target.value))} />
              </label>
              <label>
                <span>排序</span>
                <select value={String(component.config.sort || "datedesc")} onChange={(event) => updateConfig("sort", event.target.value)}>
                  <option value="datedesc">最新优先</option>
                  <option value="hybridrel">相关性优先</option>
                </select>
              </label>
              <p className="method-note">建议使用主体英文名、明确短语或 GDELT 查询操作符；结果只作为待核验线索。</p>
            </>
          ) : null}
          {!Object.keys(component.config).length ? (
            <p className="span-2 method-note">该组件使用专题本地项目与时间线，无需额外数据配置。</p>
          ) : null}
        </div>
      </details>
      <button type="button" className="icon-button danger" onClick={onRemove} aria-label={`移除 ${component.title}`}><Trash2 size={14} /></button>
    </article>
  );
}

export function TopicResearchPage({ initialQuery }: { initialQuery?: string }) {
  const topicHeroRef = useRef<HTMLElement | null>(null);
  const [topics, setTopics] = useState<ResearchTopic[]>([]);
  const [templates, setTemplates] = useState<ResearchTopicTemplate[]>([]);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [basket, setBasket] = useState<EvidenceBasketItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(
    initialQuery && Number.isFinite(Number(initialQuery)) ? Number(initialQuery) : null,
  );
  const [selected, setSelected] = useState<ResearchTopic | null>(null);
  const [timeline, setTimeline] = useState<ResearchTopicTimelineItem[]>([]);
  const [timelineTotal, setTimelineTotal] = useState(0);
  const [timelineHasMore, setTimelineHasMore] = useState(false);
  const [timelineNextCursor, setTimelineNextCursor] = useState<ResearchTopicTimelineCursor | null>(null);
  const [timelineLoadingMore, setTimelineLoadingMore] = useState(false);
  const [summaries, setSummaries] = useState<ResearchProjectSummary[]>([]);
  const [templateId, setTemplateId] = useState<ResearchTopicTemplate["id"]>("china_rates");
  const [draft, setDraft] = useState({
    title: "",
    question: "",
    description: "",
    status: "active" as ResearchTopicStatus,
    tags: "",
  });
  const [linkedProjectIds, setLinkedProjectIds] = useState<number[]>([]);
  const [componentId, setComponentId] = useState(componentPresets[0].id);
  const [selectedBasketIds, setSelectedBasketIds] = useState<number[]>([]);
  const [basketProjectId, setBasketProjectId] = useState("");
  const [basketScope, setBasketScope] = useState<EvidenceBasketScope>("all");
  const [basketSource, setBasketSource] = useState<EvidenceBasketSource>("all");
  const [basketDateFrom, setBasketDateFrom] = useState("");
  const [topicQuery, setTopicQuery] = useState("");
  const [topicStatus, setTopicStatus] = useState<TopicLibraryStatus>("all");
  const [timelineCategory, setTimelineCategory] = useState<TopicTimelineCategory>("all");
  const [timelineProjectId, setTimelineProjectId] = useState("");
  const [timelineQuery, setTimelineQuery] = useState("");
  const [timelineVisible, setTimelineVisible] = useState(20);
  const [detailNonce, setDetailNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  function loadBase(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    Promise.all([
      apiGet<ResearchTopic[]>("/research/topics?limit=500"),
      apiGet<ResearchTopicTemplate[]>("/research/topic-templates"),
      apiGet<ResearchProject[]>("/research/projects"),
      apiGet<EvidenceBasketItem[]>("/research/evidence-basket"),
    ])
      .then(([topicItems, templateItems, projectItems, basketItems]) => {
        setTopics(topicItems);
        setTemplates(templateItems);
        setProjects(projectItems);
        setBasket(basketItems);
        setSelectedId((current) =>
          preferredId !== undefined
            ? preferredId
            : current && topicItems.some((item) => item.id === current)
              ? current
              : topicItems[0]?.id ?? null,
        );
        setBasketProjectId((current) => {
          if (current) return current;
          const active = projectItems.find((item) => item.status !== "archived");
          return active ? String(active.id) : "";
        });
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "专题工作台加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadBase();
  }, []);

  useEffect(() => {
    const nextId = Number(initialQuery);
    if (initialQuery && Number.isFinite(nextId)) {
      setSelectedId(nextId);
    }
  }, [initialQuery]);

  useEffect(() => {
    setSettingsOpen(false);
    if (!selectedId) {
      setSelected(null);
      setTimeline([]);
      setTimelineTotal(0);
      setTimelineHasMore(false);
      setTimelineNextCursor(null);
      setSummaries([]);
      return;
    }
    let active = true;
    setTimeline([]);
    setTimelineTotal(0);
    setTimelineHasMore(false);
    setTimelineNextCursor(null);
    apiGet<ResearchTopicWorkspace>(`/research/topics/${selectedId}/workspace?timeline_limit=100`)
      .then((workspace) => {
        if (!active) return;
        const topic = workspace.topic;
        setSelected(topic);
        setTimeline(workspace.timeline);
        setTimelineTotal(workspace.timeline_total ?? workspace.timeline.length);
        setTimelineHasMore(workspace.timeline_has_more ?? false);
        setTimelineNextCursor(workspace.timeline_next_cursor ?? null);
        setSummaries(workspace.project_summaries);
        setDraft({
          title: topic.title,
          question: topic.question,
          description: topic.description,
          status: topic.status,
          tags: topic.tags.join("，"),
        });
        setLinkedProjectIds(topic.projects.map((project) => project.id));
        setBasketProjectId((current) =>
          current || (topic.projects[0] ? String(topic.projects[0].id) : ""),
        );
      })
      .catch((reason: unknown) =>
        active && setError(reason instanceof Error ? reason.message : "专题详情加载失败"),
      );
    return () => {
      active = false;
    };
  }, [detailNonce, selectedId]);

  useEffect(() => {
    setTimelineVisible(20);
  }, [selectedId, timelineCategory, timelineProjectId, timelineQuery]);

  useEffect(() => {
    if (selected) topicHeroRef.current?.focus({ preventScroll: true });
  }, [selected?.id]);

  const availablePresets = useMemo(
    () =>
      componentPresets.filter(
        (preset) => !selected?.components.some((item) => item.id === preset.id),
      ),
    [selected],
  );
  const filteredBasket = useMemo(
    () =>
      filterEvidenceBasket(basket, {
        scope: basketScope,
        source: basketSource,
        dateFrom: basketDateFrom,
        topicId: selected?.id ?? null,
      }),
    [basket, basketDateFrom, basketScope, basketSource, selected?.id],
  );
  const visibleTopics = useMemo(
    () => filterTopicLibrary(topics, topicQuery, topicStatus),
    [topicQuery, topicStatus, topics],
  );
  const filteredTimeline = useMemo(
    () =>
      filterTopicTimeline(timeline, {
        category: timelineCategory,
        projectId: timelineProjectId ? Number(timelineProjectId) : null,
        query: timelineQuery,
      }),
    [timeline, timelineCategory, timelineProjectId, timelineQuery],
  );
  const displayedTimeline = filteredTimeline.slice(0, timelineVisible);

  async function loadOlderTimeline() {
    if (!selectedId || !timelineHasMore || !timelineNextCursor || timelineLoadingMore) return;
    setTimelineLoadingMore(true);
    setError(null);
    try {
      const cursor = timelineNextCursor;
      const path =
        `/research/topics/${selectedId}/timeline?limit=100&paged=true` +
        `&before_time=${encodeURIComponent(cursor.event_time)}` +
        `&before_id=${encodeURIComponent(cursor.id)}`;
      const page = await apiGet<ResearchTopicTimelinePage>(path);
      setTimeline((current) => mergeTopicTimeline(current, page.items));
      setTimelineTotal(page.total);
      setTimelineHasMore(page.has_more);
      setTimelineNextCursor(page.next_cursor);
      setTimelineVisible((value) => value + page.items.length);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更早时间线加载失败");
    } finally {
      setTimelineLoadingMore(false);
    }
  }

  async function createTopic() {
    setSaving(true);
    setError(null);
    try {
      const topic = await apiPost<ResearchTopic>("/research/topics/from-template", {
        template_id: templateId,
        project_ids: [],
      });
      setMessage(`已创建“${topic.title}”`);
      loadBase(topic.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "专题创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function createStarterTopic() {
    const existing = topics.find(
      (topic) => topic.research_object.object_key === "china-rates",
    );
    if (existing) {
      setSelectedId(existing.id);
      setTopicQuery("");
      setTopicStatus("all");
      setMessage(`已打开现有示例专题“${existing.title}”`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const topic = await apiPost<ResearchTopic>("/research/topics/from-template", {
        template_id: "china_rates",
        project_ids: [],
      });
      setMessage(`已创建示例专题“${topic.title}”，可以直接刷新组件或关联研究项目`);
      loadBase(topic.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "示例专题创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveTopic(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await apiPatch<ResearchTopic>(`/research/topics/${selected.id}`, {
        ...draft,
        tags: parseResearchTags(draft.tags),
        project_ids: linkedProjectIds,
        components: selected.components,
      });
      setSelected(updated);
      setTopics((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setDetailNonce((value) => value + 1);
      setMessage("专题设置已保存");
      setSettingsOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "专题保存失败");
    } finally {
      setSaving(false);
    }
  }

  function addComponent() {
    if (!selected) return;
    const preset = availablePresets.find((item) => item.id === componentId)
      || availablePresets[0];
    if (!preset || selected.components.some((item) => item.id === preset.id)) return;
    setSelected({
      ...selected,
      components: addTopicComponent(selected.components, preset),
    });
  }

  function removeComponent(id: string) {
    if (!selected) return;
    setSelected({
      ...selected,
      components: selected.components.filter((item) => item.id !== id),
    });
  }

  function updateComponent(next: ResearchTopicComponent) {
    if (!selected) return;
    setSelected({
      ...selected,
      components: selected.components.map((item) =>
        item.id === next.id ? next : item,
      ),
    });
  }

  async function deleteTopic() {
    if (!selected || !window.confirm(`确认删除专题“${selected.title}”？关联项目和证据不会被删除。`)) return;
    try {
      await apiDelete(`/research/topics/${selected.id}`);
      setSelected(null);
      setSelectedId(null);
      loadBase();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "专题删除失败");
    }
  }

  async function commitBasket() {
    if (!selectedBasketIds.length || !basketProjectId) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost("/research/evidence-basket/commit", {
        project_id: Number(basketProjectId),
        item_ids: selectedBasketIds,
        topic_id: selected?.id || null,
      });
      setMessage(`已将 ${selectedBasketIds.length} 项证据写入研究项目`);
      setSelectedBasketIds([]);
      loadBase(selected?.id);
      setDetailNonce((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "证据篮提交失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeBasketItem(item: EvidenceBasketItem) {
    try {
      await apiDelete(`/research/evidence-basket/${item.id}`);
      setBasket((current) => current.filter((entry) => entry.id !== item.id));
      setSelectedBasketIds((current) => current.filter((id) => id !== item.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "证据篮项目删除失败");
    }
  }

  async function removeSelectedBasketItems() {
    const itemIds = selectedBasketIds.filter((id) =>
      filteredBasket.some((item) => item.id === id),
    );
    if (!itemIds.length || !window.confirm(`确认从证据篮批量移除 ${itemIds.length} 项？`)) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost("/research/evidence-basket/batch-delete", { item_ids: itemIds });
      setBasket((current) => current.filter((item) => !itemIds.includes(item.id)));
      setSelectedBasketIds((current) => current.filter((id) => !itemIds.includes(id)));
      setMessage(`已从证据篮移除 ${itemIds.length} 项`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "证据篮批量清理失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-stack topic-research-page">
      <PageHeading
        eyebrow="TOPIC RESEARCH"
        title="专题投研工作台"
        description="围绕研究对象保存跨市场视图，把证据、项目与观点变化组织在同一条研究时间线上"
      />
      {error ? <ErrorState message={error} /> : null}
      {message ? <p className="success-banner" role="status">{message}</p> : null}
      {loading ? <LoadingState /> : null}

      <details className="research-relationship-guide" open={!topics.length && !loading}>
        <summary>专题、项目、证据和复盘分别做什么？</summary>
        <div>
          <article><Layers3 size={17} /><strong>专题</strong><p>长期观察一个研究对象，组合行情、宏观、事件与项目进展。</p></article>
          <article><BookOpenCheck size={17} /><strong>项目</strong><p>回答一个可验证的问题，持续记录假设、反证和结论。</p></article>
          <article><Inbox size={17} /><strong>证据</strong><p>保存带来源和时点的数据；证据篮是跨页面的临时收集区。</p></article>
          <article><RefreshCcw size={17} /><strong>复盘</strong><p>到期后检查观点是否仍成立，并安排下一步任务。</p></article>
        </div>
      </details>

      <div className="topic-workspace-layout">
        <aside className="topic-library">
          <Panel title="专题库" eyebrow="LOCAL TOPICS">
            <div className="topic-create-row">
              <select
                value={templateId}
                onChange={(event) => setTemplateId(event.target.value as ResearchTopicTemplate["id"])}
                aria-label="专题模板"
              >
                {templates.map((template) => (
                  <option value={template.id} key={template.id}>{template.name}</option>
                ))}
              </select>
              <button className="primary-button" onClick={createTopic} disabled={saving || !templates.length}>
                {saving ? <LoaderCircle className="spin" size={14} /> : <CirclePlus size={14} />} 新建专题
              </button>
              <small>{templates.find((item) => item.id === templateId)?.description}</small>
            </div>
            <div className="topic-library-filters">
              <label>
                <span>搜索专题</span>
                <input
                  type="search"
                  value={topicQuery}
                  onChange={(event) => setTopicQuery(event.target.value)}
                  placeholder="标题、对象或标签"
                />
              </label>
              <label>
                <span>专题状态</span>
                <select
                  value={topicStatus}
                  onChange={(event) => setTopicStatus(event.target.value as TopicLibraryStatus)}
                >
                  <option value="all">全部状态</option>
                  {Object.entries(topicStatusLabels).map(([value, label]) => (
                    <option value={value} key={value}>{label}</option>
                  ))}
                </select>
              </label>
              <small role="status" aria-live="polite">显示 {visibleTopics.length}/{topics.length} 个专题</small>
            </div>
            <div className="topic-list" role="list" aria-label="专题列表">
              {visibleTopics.map((topic) => (
                <div role="listitem" key={topic.id}>
                  <button
                    type="button"
                    className={selectedId === topic.id ? "active" : undefined}
                    onClick={() => setSelectedId(topic.id)}
                    aria-pressed={selectedId === topic.id}
                  >
                    <span className={`topic-status ${topic.status}`}>{topicStatusLabels[topic.status]}</span>
                    <strong>{topic.title}</strong>
                    <small>{topic.research_object.name} · {topic.projects.length} 个项目</small>
                  </button>
                </div>
              ))}
              {!topics.length && !loading ? (
                <div className="empty-state compact-empty">
                  <Layers3 size={24} />
                  <strong>还没有专题</strong>
                  <p>可先创建中国利率示例专题，直接体验一套可持续刷新的研究视图。</p>
                  <button className="secondary-button" type="button" onClick={createStarterTopic} disabled={saving}>
                    <CirclePlus size={14} /> 创建示例专题
                  </button>
                </div>
              ) : null}
              {topics.length && !visibleTopics.length ? (
                <div className="empty-state compact-empty"><Layers3 size={24} /><strong>没有符合条件的专题</strong><p>可清空搜索词或切换状态。</p></div>
              ) : null}
            </div>
          </Panel>
        </aside>

        <div className="topic-main">
          {selected ? (
            <>
              <section
                className="topic-hero"
                ref={topicHeroRef}
                tabIndex={-1}
                aria-labelledby="selected-topic-title"
              >
                <div>
                  <span className="eyebrow">{selected.research_object.object_type.replaceAll("_", " ")}</span>
                  <h2 id="selected-topic-title">{selected.title}</h2>
                  <p>{selected.question || selected.description}</p>
                </div>
                <div className="topic-hero-meta">
                  <span>{topicStatusLabels[selected.status]}</span>
                  <strong>{selected.components.length} 个组件</strong>
                  <small>{selected.projects.length} 个关联项目 · 已加载 {timeline.length}/{timelineTotal} 条时间线记录</small>
                  <div className="topic-hero-actions">
                    <button className="text-button" onClick={() => setSettingsOpen((value) => !value)} aria-expanded={settingsOpen}>
                      <Settings2 size={13} /> {settingsOpen ? "返回阅读" : "编辑专题"}
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        apiDownload(
                          `/research/topics/${selected.id}/export`,
                          `akdesk-topic-${selected.id}.md`,
                        )
                      }
                    >
                      <Download size={13} /> 导出专题
                    </button>
                  </div>
                </div>
              </section>

              <AiInsightCard
                contextType="topic"
                topicId={selected.id}
                title="跨源专题 AI 综述"
                description="只汇总专题、项目、证据标题与时间线元数据，明确来源分歧和待核验缺口"
                revision={`${selected.updated_at}:${timelineTotal}:${timeline[0]?.event_time ?? ""}`}
              />

              <div className="topic-component-grid">
                {selected.components.map((component) => (
                  <DeferredTopicComponent
                    component={component}
                    summaries={summaries}
                    timeline={timeline}
                    topicId={selected.id}
                    onEvidenceAdded={(item) => {
                      setBasket((current) => [item, ...current]);
                      setMessage("GDELT 线索已加入证据篮，提交到项目后才会进入研究时间线。");
                    }}
                    key={`${selected.id}-${component.id}`}
                  />
                ))}
              </div>

              <Panel title="跨源研究时间线" eyebrow="MARKET · FRED · WORLD BANK · GDELT · NOTES">
                {timeline.length ? (
                  <>
                    <div className="topic-timeline-filters">
                      <label><span>搜索记录</span><input type="search" value={timelineQuery} onChange={(event) => setTimelineQuery(event.target.value)} placeholder="标题、摘要或项目" /></label>
                      <label><span>记录类型</span><select value={timelineCategory} onChange={(event) => setTimelineCategory(event.target.value as TopicTimelineCategory)}><option value="all">全部类型</option><option value="evidence">数据与证据</option><option value="research">笔记、反证与任务</option><option value="project">项目变化</option><option value="release">发布复盘</option></select></label>
                      <label><span>研究项目</span><select value={timelineProjectId} onChange={(event) => setTimelineProjectId(event.target.value)}><option value="">全部项目</option>{selected.projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label>
                      <small role="status" aria-live="polite">
                        显示 {Math.min(displayedTimeline.length, filteredTimeline.length)}/{filteredTimeline.length} 条匹配记录
                        {timelineHasMore ? ` · 共 ${timelineTotal} 条，筛选范围为已加载记录` : ` · 已加载完整 ${timelineTotal} 条`}
                      </small>
                    </div>
                    {filteredTimeline.length ? (
                      <>
                        <div className="topic-timeline" role="list" aria-label="研究时间线">
                          {displayedTimeline.map((item) => (
                            <article key={item.id} role="listitem">
                              <span className="topic-timeline-dot" />
                              <div>
                                <span>{timelineLabels[item.event_type] || item.event_type}</span>
                                <strong>{item.title}</strong>
                                {item.summary ? <p>{item.summary}</p> : null}
                                <small>
                                  {item.project_title} · 记录 {formatDateTime(item.event_time)}
                                  {item.observation_time ? ` · 观察 ${item.observation_time}` : ""}
                                </small>
                              </div>
                            </article>
                          ))}
                        </div>
                        {displayedTimeline.length < filteredTimeline.length ? (
                          <button
                            type="button"
                            className="secondary-button topic-timeline-more"
                            onClick={() => setTimelineVisible((value) => value + 20)}
                          >
                            再显示 {Math.min(20, filteredTimeline.length - displayedTimeline.length)} 条
                          </button>
                        ) : null}
                        {timelineHasMore ? (
                          <button
                            type="button"
                            className="secondary-button topic-timeline-more"
                            onClick={loadOlderTimeline}
                            disabled={timelineLoadingMore}
                          >
                            {timelineLoadingMore ? <LoaderCircle className="spin" size={14} /> : <Clock3 size={14} />}
                            {timelineLoadingMore ? "正在加载更早记录" : `加载更早记录（已加载 ${timeline.length}/${timelineTotal}）`}
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <div className="empty-state compact-empty">
                        <Clock3 size={24} /><strong>已加载记录中没有符合筛选条件的内容</strong>
                        {timelineHasMore ? <button type="button" className="secondary-button" onClick={loadOlderTimeline}>继续加载更早记录</button> : null}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="empty-state compact-empty"><Clock3 size={24} /><strong>关联项目尚无研究活动</strong></div>
                )}
              </Panel>

              <Panel title={`证据篮 · ${filteredBasket.length}/${basket.length}`} eyebrow="FILTER · SELECT · COMMIT">
                {basket.length ? (
                  <>
                    <div className="evidence-basket-filters">
                      <label><span>归属</span><select value={basketScope} onChange={(event) => setBasketScope(event.target.value as EvidenceBasketScope)}><option value="all">全部证据</option><option value="topic">当前专题</option><option value="unassigned">尚未归属</option></select></label>
                      <label><span>来源</span><select value={basketSource} onChange={(event) => setBasketSource(event.target.value as EvidenceBasketSource)}><option value="all">全部来源</option><option value="fred">FRED</option><option value="world_bank">World Bank</option><option value="gdelt">GDELT</option><option value="market">市场与其他</option></select></label>
                      <label><span>起始日期</span><input type="date" value={basketDateFrom} onChange={(event) => setBasketDateFrom(event.target.value)} /></label>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => {
                          const visibleIds = filteredBasket.map((item) => item.id);
                          const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedBasketIds.includes(id));
                          setSelectedBasketIds((current) =>
                            allSelected
                              ? current.filter((id) => !visibleIds.includes(id))
                              : Array.from(new Set([...current, ...visibleIds])),
                          );
                        }}
                        disabled={!filteredBasket.length}
                      >
                        {filteredBasket.length && filteredBasket.every((item) => selectedBasketIds.includes(item.id)) ? "取消全选" : "全选结果"}
                      </button>
                    </div>
                    <div className="evidence-basket-list">
                      {filteredBasket.map((item) => (
                        <article key={item.id}>
                          <label>
                            <input
                              type="checkbox"
                              checked={selectedBasketIds.includes(item.id)}
                              onChange={() => setSelectedBasketIds((current) => toggleNumericId(current, item.id))}
                            />
                            <div>
                              <strong>{item.title}</strong>
                              <span>{item.source_summary || item.evidence_type}</span>
                              <small>{item.origin_page || "研究页面"} · {formatDateTime(item.created_at)}</small>
                            </div>
                          </label>
                          <button
                            className="icon-button danger"
                            onClick={() => removeBasketItem(item)}
                            aria-label="移出证据篮"
                          >
                            <Trash2 size={14} />
                          </button>
                        </article>
                      ))}
                      {!filteredBasket.length ? (
                        <div className="empty-state compact-empty"><Inbox size={24} /><strong>没有符合筛选条件的证据</strong></div>
                      ) : null}
                    </div>
                    <div className="evidence-basket-actions">
                      <button
                        className="secondary-button danger-text"
                        disabled={!selectedBasketIds.some((id) => filteredBasket.some((item) => item.id === id)) || saving}
                        onClick={removeSelectedBasketItems}
                      >
                        <Trash2 size={14} /> 批量移除
                      </button>
                      <select
                        value={basketProjectId}
                        onChange={(event) => setBasketProjectId(event.target.value)}
                        aria-label="证据篮目标项目"
                      >
                        <option value="">选择目标项目</option>
                        {projects.filter((project) => project.status !== "archived").map((project) => (
                          <option value={project.id} key={project.id}>{project.title}</option>
                        ))}
                      </select>
                      <button
                        className="primary-button"
                        disabled={!selectedBasketIds.length || !basketProjectId || saving}
                        onClick={commitBasket}
                      >
                        {saving ? <LoaderCircle className="spin" size={14} /> : <Inbox size={14} />}
                        提交 {selectedBasketIds.length} 项到项目
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="empty-state compact-empty">
                    <Inbox size={24} />
                    <strong>证据篮为空</strong>
                    <p>可从研究首页、图表研究室、全球主权比较或事件雷达先收集证据，再在这里批量归档。</p>
                  </div>
                )}
              </Panel>

              {settingsOpen ? <Panel
                title="专题设置"
                eyebrow="OBJECT · PROJECTS · COMPONENTS"
                action={<button className="icon-button danger" onClick={deleteTopic} aria-label="删除专题"><Trash2 size={15} /></button>}
              >
                <form className="topic-settings-form" onSubmit={saveTopic}>
                  <label className="span-2"><span>专题标题</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} required /></label>
                  <label className="span-2"><span>研究问题</span><textarea value={draft.question} onChange={(event) => setDraft({ ...draft, question: event.target.value })} /></label>
                  <label className="span-2"><span>专题说明</span><textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
                  <label><span>状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as ResearchTopicStatus })}>{Object.entries(topicStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  <label><span>标签</span><input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} /></label>

                  <fieldset className="span-2 topic-project-picker">
                    <legend>关联研究项目</legend>
                    {projects.filter((project) => project.status !== "archived").map((project) => (
                      <label key={project.id}>
                        <input
                          type="checkbox"
                          checked={linkedProjectIds.includes(project.id)}
                          onChange={() => setLinkedProjectIds((current) => toggleNumericId(current, project.id))}
                        />
                        <span>{project.title}</span>
                      </label>
                    ))}
                  </fieldset>

                  <div className="span-2 topic-component-manager">
                    <span>保存的专题组件</span>
                    <div>
                      {selected.components.map((component) => (
                        <TopicComponentEditor
                          component={component}
                          onChange={updateComponent}
                          onRemove={() => removeComponent(component.id)}
                          key={component.id}
                        />
                      ))}
                    </div>
                    <div className="topic-component-add">
                      <select
                        value={
                          availablePresets.some((preset) => preset.id === componentId)
                            ? componentId
                            : availablePresets[0]?.id || ""
                        }
                        onChange={(event) => setComponentId(event.target.value)}
                      >
                        {availablePresets.map((preset) => <option value={preset.id} key={preset.id}>{preset.title}</option>)}
                      </select>
                      <button type="button" className="secondary-button" onClick={addComponent} disabled={!availablePresets.length}>
                        <CirclePlus size={14} /> 添加组件
                      </button>
                    </div>
                  </div>

                  <div className="span-2 topic-settings-actions">
                    <span><Link2 size={13} /> 研究对象：{selected.research_object.name}</span>
                    <button className="primary-button" disabled={saving}>
                      {saving ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />} 保存专题
                    </button>
                  </div>
                </form>
              </Panel> : null}
            </>
          ) : !loading ? (
            <Panel title="从一个专题模板开始" eyebrow="START">
              <div className="topic-onboarding-empty">
                <Archive size={30} />
                <div>
                  <strong>把分散页面组织成持续研究视图</strong>
                  <p>专题负责长期观察一个主题；研究项目负责验证一个具体问题；证据篮用于暂存跨页面资料。</p>
                </div>
                <ol>
                  <li><span>1</span>选择专题模板</li>
                  <li><span>2</span>关联或新建研究项目</li>
                  <li><span>3</span>从市场与图表页收集证据</li>
                  <li><span>4</span>更新观点并进入定期复盘</li>
                </ol>
                <div className="topic-onboarding-actions">
                  <button className="primary-button" onClick={createStarterTopic} disabled={saving}>
                    {saving ? <LoaderCircle className="spin" size={14} /> : <CirclePlus size={14} />} 创建中国利率示例专题
                  </button>
                  <button className="secondary-button" onClick={createTopic} disabled={saving || !templates.length}>
                    用当前模板创建
                  </button>
                </div>
              </div>
            </Panel>
          ) : null}
        </div>
      </div>
    </div>
  );
}
