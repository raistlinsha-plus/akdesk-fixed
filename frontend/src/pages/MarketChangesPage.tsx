import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  ChartNoAxesCombined,
  CheckCheck,
  Clock3,
  Database,
  Filter,
  Landmark,
  RefreshCcw,
  ShieldAlert,
  ShieldCheck,
  Waves,
} from "lucide-react";
import { apiGet } from "../api";
import {
  DEFAULT_MARKET_CHANGE_FILTERS,
  MARKET_CHANGE_FILTER_KEY,
  MARKET_CHANGE_SNAPSHOT_KEY,
  changedSignalIds,
  filterMarketSignals,
  marketTaskCopy,
  parseMarketChangeFilters,
  parseMarketChangeSnapshot,
  snapshotFromBrief,
  type MarketChangeFilters,
} from "../marketChanges";
import type { MarketResearchBrief, MarketResearchSignal } from "../types";
import {
  classNames,
  ErrorState,
  formatDateTime,
  LoadingState,
} from "../components/UI";
import { PageHeading } from "./MarketPages";

const categoryCopy: Record<MarketResearchSignal["category"], string> = {
  funding: "资金",
  curve: "曲线",
  future: "期货",
  bond: "现券",
};
const severityCopy = { high: "高优先", watch: "关注", info: "信息" };
const routeByCategory: Record<MarketResearchSignal["category"], string> = {
  funding: "money",
  curve: "curves",
  future: "futures",
  bond: "bonds",
};
const routeCopy: Record<MarketResearchSignal["category"], string> = {
  funding: "资金面",
  curve: "收益率曲线",
  future: "国债期货",
  bond: "现券市场",
};
const trustCopy: Record<MarketResearchSignal["trust_level"], string> = {
  trusted: "可信",
  partial: "部分可信",
  suspicious: "可疑",
  unavailable: "不可用",
};

function CategoryIcon({
  category,
}: {
  category: MarketResearchSignal["category"];
}) {
  if (category === "funding") return <Waves size={18} />;
  if (category === "curve") return <ChartNoAxesCombined size={18} />;
  if (category === "bond") return <Landmark size={18} />;
  return <Activity size={18} />;
}

export function MarketChangesPage({
  refreshSeed,
  navigate,
}: {
  refreshSeed: number;
  navigate: (page: string, query?: string) => void;
}) {
  const [brief, setBrief] = useState<MarketResearchBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState(() =>
    parseMarketChangeSnapshot(window.localStorage.getItem(MARKET_CHANGE_SNAPSHOT_KEY)));
  const [filters, setFilters] = useState<MarketChangeFilters>(() =>
    parseMarketChangeFilters(window.localStorage.getItem(MARKET_CHANGE_FILTER_KEY)));

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiGet<MarketResearchBrief>("/research/market-brief")
      .then((result) => {
        if (active) setBrief(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "市场变化读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [refreshSeed]);

  useEffect(() => {
    try {
      window.localStorage.setItem(MARKET_CHANGE_FILTER_KEY, JSON.stringify(filters));
    } catch {
      // Filtering remains available for this session.
    }
  }, [filters]);

  const changedIds = useMemo(
    () => brief ? changedSignalIds(brief, snapshot) : new Set<string>(),
    [brief, snapshot],
  );
  const visibleSignals = useMemo(
    () => filterMarketSignals(brief?.signals ?? [], filters),
    [brief, filters],
  );

  function markAsRead() {
    if (!brief) return;
    const next = snapshotFromBrief(brief);
    setSnapshot(next);
    try {
      window.localStorage.setItem(MARKET_CHANGE_SNAPSHOT_KEY, JSON.stringify(next));
    } catch {
      // A saved visit is optional; the live brief still works.
    }
  }

  function toggleSeverity(severity: MarketResearchSignal["severity"]) {
    setFilters((current) => ({
      ...current,
      severities: current.severities.includes(severity)
        ? current.severities.filter((item) => item !== severity)
        : [...current.severities, severity],
    }));
  }

  return (
    <div className="page-stack market-changes-page">
      <PageHeading
        eyebrow="MARKET CHANGE CENTER"
        title="市场变化中心"
        description="把“相较上一收盘发生了什么”与“自上次查看后有什么变化”放在同一页，并保留来源、时点和可信边界"
      />
      {loading ? <LoadingState label="正在整理市场变化" /> : null}
      {error ? <ErrorState message={error} /> : null}
      {brief ? (
        <>
          <section className="market-change-overview">
            <div className="market-change-overview-copy">
              <div className="market-change-session-label">
                <Activity size={15} />
                <span>当前观察</span>
                <strong>{brief.market_status}</strong>
              </div>
              <h2>{brief.headline}</h2>
              <p>{marketTaskCopy(brief.market_status)}</p>
            </div>
            <dl className="market-change-metrics">
              <div className="is-primary">
                <dt>可信可行动</dt>
                <dd>
                  {brief.signals.filter((item) => item.actionable).length}
                  <span>/ {brief.signals.length}</span>
                </dd>
                <small>已通过来源、时点与质量门禁</small>
              </div>
              <div>
                <dt>上次查看后</dt>
                <dd>{changedIds.size}</dd>
                <small>{changedIds.size ? "条信号发生变化" : "暂无新增变化"}</small>
              </div>
              <div>
                <dt>最低质量分</dt>
                <dd>{filters.minQuality}</dd>
                <small>当前筛选门槛</small>
              </div>
            </dl>
            <footer className="market-change-overview-footer">
              <span><Clock3 size={13} /> 更新于 {formatDateTime(brief.generated_at)}</span>
              <span>
                {brief.snapshot_eligible ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />}
                {brief.snapshot_eligible ? "当前存在可保存的可信快照" : "当前信号仅供核验"}
              </span>
            </footer>
          </section>

          <section className="market-change-toolbar" aria-label="市场变化筛选">
            <div className="market-change-toolbar-title">
              <Filter size={16} />
              <div>
                <strong>筛选变化</strong>
                <small>显示 {visibleSignals.length}/{brief.signals.length} 条</small>
              </div>
            </div>
            <div className="market-change-filters">
              <label className="market-change-actionable-toggle">
                <input
                  type="checkbox"
                  checked={filters.actionableOnly}
                  onChange={(event) => setFilters({ ...filters, actionableOnly: event.target.checked })}
                />
                <span>仅看可信可行动</span>
              </label>
              <label className="market-change-quality">
                <span>质量门槛</span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={filters.minQuality}
                  onChange={(event) => setFilters({ ...filters, minQuality: Number(event.target.value) })}
                />
                <strong>{filters.minQuality}</strong>
              </label>
              <div className="market-change-severity-filter" role="group" aria-label="变化优先级">
                {(["high", "watch", "info"] as const).map((severity) => (
                  <button
                    type="button"
                    className={filters.severities.includes(severity) ? "active" : undefined}
                    aria-pressed={filters.severities.includes(severity)}
                    onClick={() => toggleSeverity(severity)}
                    key={severity}
                  >
                    {severityCopy[severity]}
                  </button>
                ))}
              </div>
            </div>
            <div className="market-change-toolbar-actions">
              <button className="text-button" onClick={() => setFilters(DEFAULT_MARKET_CHANGE_FILTERS)}>
                <RefreshCcw size={13} /> 恢复默认
              </button>
              <button className="secondary-button" onClick={markAsRead}>
                <CheckCheck size={14} /> 标记本次已读
              </button>
            </div>
          </section>

          <section className="market-change-feed" aria-label="市场变化列表">
            <header className="market-change-feed-heading">
              <div>
                <span className="eyebrow">VERIFIED SIGNAL FEED</span>
                <h2>可核验变化</h2>
              </div>
              <p>按优先级与可行动性排序，先看结论，再核对证据。</p>
            </header>
            <ol className="market-change-list">
              {visibleSignals.map((signal, index) => (
                <li key={signal.id}>
                  <article
                    className={classNames(
                      "market-change-card",
                      `severity-${signal.severity}`,
                      changedIds.has(signal.id) && "is-new",
                    )}
                  >
                    <div className="market-change-rank" aria-hidden="true">
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <CategoryIcon category={signal.category} />
                    </div>
                    <div className="market-change-card-main">
                      <header>
                        <div>
                          <span className={`market-change-severity ${signal.severity}`}>
                            {severityCopy[signal.severity]}
                          </span>
                          <span className="market-change-category">{categoryCopy[signal.category]}</span>
                          {changedIds.has(signal.id) ? <span className="new-change-tag">刚刚变化</span> : null}
                        </div>
                      </header>
                      <h3>{signal.title}</h3>
                      <p>{signal.summary}</p>
                      <small className="market-change-trigger">
                        <Filter size={12} />
                        {signal.trigger_reason}
                      </small>
                    </div>
                    <aside className="market-change-evidence">
                      <div className={classNames("market-change-action-state", signal.actionable && "is-actionable")}>
                        {signal.actionable ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
                        <strong>{signal.actionable ? "可信可行动" : "仅供核验"}</strong>
                      </div>
                      <dl>
                        <div>
                          <dt><Database size={12} /> 来源</dt>
                          <dd>{signal.source}</dd>
                        </div>
                        <div>
                          <dt><Clock3 size={12} /> 时点</dt>
                          <dd>观测 {signal.observation_time || "源未提供"} · 抓取 {formatDateTime(signal.fetched_at)}</dd>
                        </div>
                      </dl>
                      <div className="market-change-quality-line">
                        <span>质量 {signal.quality_score}</span>
                        <span>{trustCopy[signal.trust_level]}</span>
                      </div>
                      <button
                        className="market-change-route-button"
                        onClick={() => navigate(routeByCategory[signal.category], signal.object_id ?? "")}
                      >
                        去{routeCopy[signal.category]}核验 <ArrowRight size={13} />
                      </button>
                    </aside>
                  </article>
                </li>
              ))}
            </ol>
            {!visibleSignals.length ? (
              <div className="market-change-empty">
                <CheckCheck size={22} />
                <strong>当前筛选下没有变化</strong>
                <p>可降低质量阈值或暂时显示仅供核验的数据。</p>
              </div>
            ) : null}
            <footer className="market-change-notice">
              <ShieldCheck size={13} />
              <span>{brief.notice}</span>
            </footer>
          </section>
        </>
      ) : null}
    </div>
  );
}
