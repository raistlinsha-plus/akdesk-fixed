import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  CalendarClock,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  Database,
  Inbox,
  Layers3,
  LoaderCircle,
  Pin,
  Save,
  Star,
} from "lucide-react";
import { apiGet, apiPatch, apiPost } from "../api";
import { CreateProjectButton } from "../components/CreateProjectButton";
import { GettingStartedGuide } from "../components/GettingStartedGuide";
import { useWatchlist } from "../components/WatchlistContext";
import { ErrorState, LoadingState, Panel, formatDateTime } from "../components/UI";
import type {
  MarketResearchBrief,
  ResearchEvidence,
  ResearchOverview,
  ResearchProject,
  ResearchSignalSettings,
  ResearchStatus,
} from "../types";
import { actionableMarketSignalIds, isReviewDue, shanghaiDate } from "../researchUtils";
import { activeWorkflowStep } from "../researchWorkflow";
import { buildResearchTodayTasks } from "../experienceGuide";
import { PageHeading } from "./MarketPages";

const statusLabels: Record<ResearchStatus, string> = {
  draft: "草稿",
  tracking: "跟踪中",
  formed: "已形成观点",
  review: "待复盘",
  archived: "已归档",
};

const signalSettingLabels: Record<keyof ResearchSignalSettings, string> = {
  funding_change_bp: "资金利率变动阈值（BP）",
  curve_change_bp: "曲线单点变动阈值（BP）",
  curve_spread_bp: "期限利差阈值（BP）",
  futures_change_pct: "国债期货变动阈值（%）",
  bond_change_bp: "现券收益率变动阈值（BP）",
};

export function InvestmentDeskPage({
  refreshSeed,
  navigate,
}: {
  refreshSeed: number;
  navigate: (page: string, query?: string) => void;
}) {
  const [overview, setOverview] = useState<ResearchOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [marketBrief, setMarketBrief] = useState<MarketResearchBrief | null>(null);
  const [marketLoading, setMarketLoading] = useState(true);
  const [marketError, setMarketError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedSignalIds, setSelectedSignalIds] = useState<string[]>([]);
  const [snapshotNote, setSnapshotNote] = useState("");
  const [snapshotSaving, setSnapshotSaving] = useState(false);
  const [snapshotMessage, setSnapshotMessage] = useState<string | null>(null);
  const [signalSettings, setSignalSettings] = useState<ResearchSignalSettings | null>(null);
  const { items } = useWatchlist();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiGet<ResearchOverview>("/research/overview")
      .then((value) => {
        if (active) setOverview(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "投研工作台加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSeed]);

  useEffect(() => {
    let active = true;
    setMarketLoading(true);
    setMarketError(null);
    Promise.all([
      apiGet<MarketResearchBrief>("/research/market-brief"),
      apiGet<ResearchProject[]>("/research/projects"),
    ])
      .then(([brief, projectItems]) => {
        if (!active) return;
        setMarketBrief(brief);
        setSignalSettings(brief.settings);
        setProjects(projectItems);
        setSelectedSignalIds(actionableMarketSignalIds(brief.signals));
        const activeProjects = projectItems.filter((item) => item.status !== "archived");
        setSelectedProjectId((current) =>
          current && activeProjects.some((item) => item.id === current)
            ? current
            : activeProjects[0]?.id ?? null,
        );
      })
      .catch((reason: unknown) => {
        if (active) {
          setMarketError(reason instanceof Error ? reason.message : "市场研究线索加载失败");
        }
      })
      .finally(() => {
        if (active) setMarketLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSeed]);

  const dueWatchlist = useMemo(() => {
    const today = shanghaiDate();
    return items.filter(
      (item) =>
        item.pinned ||
        isReviewDue(item.next_review_date, item.research_status, today) ||
        item.research_status === "review",
    );
  }, [items]);
  const activeProjects = useMemo(
    () => projects.filter((item) => item.status !== "archived"),
    [projects],
  );
  const workflowActive = overview
    ? activeWorkflowStep({
        signals: marketBrief?.signals.filter((item) => item.actionable).length ?? 0,
        projects: overview.projects.active,
        evidence: overview.projects.evidence,
        conclusions: overview.projects.with_conclusion,
        due: overview.projects.due,
      })
    : 0;
  const workflowSteps = [
    { label: "发现线索", hint: `${marketBrief?.signals.filter((item) => item.actionable).length ?? 0} 条可用`, page: "dashboard" },
    { label: "创建研究", hint: `${overview?.projects.active ?? 0} 个进行中`, page: "projects" },
    { label: "收集证据", hint: `${overview?.projects.evidence ?? 0} 项已归档`, page: "chart-lab" },
    { label: "更新观点", hint: `${overview?.projects.with_conclusion ?? 0} 个有结论`, page: "projects" },
    { label: "定期复盘", hint: `${overview?.projects.due ?? 0} 个到期`, page: "weekly-review" },
  ];
  const researchTodayTasks = overview
    ? buildResearchTodayTasks({
        activeProjects: overview.projects.active,
        topics: overview.topics.total,
        evidence: overview.projects.evidence,
        evidenceBasket: overview.evidence_basket.total,
        dueReviews: Math.max(overview.projects.due, dueWatchlist.length),
      })
    : [];

  function toggleSignal(signalId: string) {
    setSnapshotMessage(null);
    setSelectedSignalIds((current) =>
      current.includes(signalId)
        ? current.filter((item) => item !== signalId)
        : [...current, signalId],
    );
  }

  async function saveSignalSettings() {
    if (!signalSettings) return;
    try {
      await apiPatch<ResearchSignalSettings>("/research/signal-settings", signalSettings);
      const brief = await apiGet<MarketResearchBrief>("/research/market-brief");
      setMarketBrief(brief);
      setSelectedSignalIds(actionableMarketSignalIds(brief.signals));
      setSnapshotMessage("线索敏感度已更新");
    } catch (reason) {
      setMarketError(reason instanceof Error ? reason.message : "线索设置保存失败");
    }
  }

  async function saveMarketSnapshot() {
    if (!selectedProjectId || !selectedSignalIds.length) return;
    setSnapshotSaving(true);
    setSnapshotMessage(null);
    setMarketError(null);
    try {
      const saved = await apiPost<ResearchEvidence>(
        `/research/projects/${selectedProjectId}/market-snapshot`,
        { signal_ids: selectedSignalIds, note: snapshotNote.trim() },
      );
      setSnapshotNote("");
      setSnapshotMessage(`已保存“${saved.title}”`);
    } catch (reason) {
      setMarketError(reason instanceof Error ? reason.message : "市场快照保存失败");
    } finally {
      setSnapshotSaving(false);
    }
  }

  async function addMarketSnapshotToBasket() {
    if (!selectedSignalIds.length) return;
    setSnapshotSaving(true);
    setSnapshotMessage(null);
    setMarketError(null);
    try {
      const saved = await apiPost<ResearchEvidence>(
        "/research/evidence-basket/market-snapshot",
        { signal_ids: selectedSignalIds, note: snapshotNote.trim() },
      );
      setSnapshotNote("");
      setSnapshotMessage(`已将“${saved.title}”加入证据篮`);
    } catch (reason) {
      setMarketError(reason instanceof Error ? reason.message : "加入证据篮失败");
    } finally {
      setSnapshotSaving(false);
    }
  }

  return (
    <div className="page-stack research-desk-page">
      <PageHeading
        eyebrow="RESEARCH DESK"
        title="宏观固收投研工作台"
        description="围绕观点、证据和复盘组织行情、宏观指标与自选研究"
      />

      <section className="research-workflow-hero">
        <div>
          <span className="eyebrow">RESEARCH LOOP</span>
          <h2>发现问题，保存证据，持续验证观点</h2>
          <p>研究项目保存序列、变换与来源引用；重新打开时明确获取当前官方版本，不把历史值静默伪装成冻结数据。</p>
        </div>
        <div className="research-workflow-actions">
          <button className="primary-button" onClick={() => navigate("topics")}>
            <Layers3 size={15} /> 打开专题投研
          </button>
          <button className="primary-button" onClick={() => navigate("projects")}>
            <BookOpenCheck size={15} /> 新建研究项目
          </button>
          <button className="secondary-button" onClick={() => navigate("chart-lab")}>
            <ChartNoAxesCombined size={15} /> 打开图表研究室
          </button>
        </div>
      </section>

      <nav className="research-workflow-steps" aria-label="推荐研究流程">
        {workflowSteps.map((step, index) => (
          <button
            className={index === workflowActive ? "active" : index < workflowActive ? "done" : undefined}
            onClick={() => navigate(step.page)}
            key={step.label}
          >
            <span>{index < workflowActive ? <CheckCircle2 size={15} /> : index + 1}</span>
            <strong>{step.label}</strong>
            <small>{step.hint}</small>
          </button>
        ))}
      </nav>

      {overview ? (
        <GettingStartedGuide
          mode="research"
          tasks={researchTodayTasks}
          onNavigate={(target) => navigate(target)}
        />
      ) : null}

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState message={error} /> : null}
      {overview ? (
        <>
          <div className="metrics-grid research-metrics">
            <article className="metric-card">
              <span>进行中项目</span>
              <strong>{overview.projects.active}</strong>
              <small>{overview.projects.total} 个研究项目</small>
            </article>
            <article className="metric-card">
              <span>专题工作台</span>
              <strong>{overview.topics.active}</strong>
              <small>{overview.topics.review} 个待专题复盘</small>
            </article>
            <article className="metric-card">
              <span>证据篮</span>
              <strong>{overview.evidence_basket.total}</strong>
              <small>跨页面收集，批量归档</small>
            </article>
            <article className="metric-card">
              <span>待复盘</span>
              <strong>{overview.projects.due}</strong>
              <small>已到复盘日期</small>
            </article>
            <article className="metric-card">
              <span>统一自选</span>
              <strong>{overview.watchlist.total}</strong>
              <small>{overview.watchlist.macro} 个宏观指标 · {overview.watchlist.securities} 个证券</small>
            </article>
            <article className="metric-card">
              <span>海外宏观</span>
              <strong>{overview.fred.verified ? "已验证" : overview.fred.configured ? "待验证" : "待配置"}</strong>
              <small>FRED 请求级 · World Bank 缓存 {overview.world_bank.points} 点</small>
            </article>
          </div>

          <Panel
            title="市场研究线索"
            eyebrow="MARKET TO RESEARCH"
            action={
              <button className="text-button" onClick={() => navigate("dashboard")}>
                查看完整市场 <ArrowRight size={14} />
              </button>
            }
          >
            {marketLoading ? <LoadingState /> : null}
            {marketError ? <ErrorState message={marketError} /> : null}
            {marketBrief ? (
              <div className="market-research-brief">
                <div className="market-brief-summary">
                  <div>
                    <span>{marketBrief.market_status}</span>
                    <strong>{marketBrief.headline}</strong>
                    <small>生成于 {formatDateTime(marketBrief.generated_at)}</small>
                  </div>
                  <span className={marketBrief.snapshot_eligible ? "trust-pill trusted" : "trust-pill unavailable"}>
                    {marketBrief.snapshot_eligible ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}
                    {marketBrief.snapshot_eligible ? "可保存可信快照" : "当前仅供查看"}
                  </span>
                </div>

                {marketBrief.signals.length ? (
                  <div className="market-signal-grid">
                    {marketBrief.signals.map((signal) => (
                      <label
                        className={`market-signal-card ${signal.severity} ${signal.actionable ? "" : "disabled"}`}
                        key={signal.id}
                      >
                        <input
                          type="checkbox"
                          checked={selectedSignalIds.includes(signal.id)}
                          disabled={!signal.actionable}
                          onChange={() => toggleSignal(signal.id)}
                        />
                        <div>
                          <span className="signal-meta">
                            <span className={`signal-severity ${signal.severity}`}>
                              {signal.severity === "high" ? "显著" : signal.severity === "watch" ? "关注" : "信息"}
                            </span>
                            {signal.observation_time || "观察时间待确认"}
                          </span>
                          <strong>{signal.title}</strong>
                          <p>{signal.summary}</p>
                          <small>{signal.source} · 质量 {signal.quality_score}</small>
                          <small>{signal.trigger_reason}</small>
                          <span onClick={(event) => event.preventDefault()}>
                            <CreateProjectButton objectType={signal.object_type === "bond" || signal.object_type === "future" || signal.object_type === "convertible" || signal.object_type === "macro" ? signal.object_type : undefined} objectId={signal.object_id} objectName={signal.object_name || signal.title} source={signal.source} observationTime={signal.observation_time} question={`如何解释：${signal.summary}`} />
                          </span>
                        </div>
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state compact-empty">
                    <CircleAlert size={25} />
                    <strong>市场数据正在准备</strong>
                    <p>等待本地行情预热完成后刷新当前页。</p>
                  </div>
                )}

                {signalSettings ? <details className="signal-settings"><summary>调整线索敏感度</summary><div>{Object.entries(signalSettings).map(([field, value]) => <label key={field}><span>{signalSettingLabels[field as keyof ResearchSignalSettings]}</span><input aria-label={signalSettingLabels[field as keyof ResearchSignalSettings]} type="number" step="0.1" value={value} onChange={(event) => setSignalSettings({ ...signalSettings, [field]: Number(event.target.value) })} /></label>)}<button className="secondary-button" onClick={saveSignalSettings}>保存敏感度</button></div></details> : null}

                <div className="market-snapshot-composer">
                  {activeProjects.length ? (
                    <>
                      <label>
                        <span>保存到研究项目</span>
                        <select
                          value={selectedProjectId ?? ""}
                          onChange={(event) => setSelectedProjectId(Number(event.target.value) || null)}
                        >
                          {activeProjects.map((project) => (
                            <option value={project.id} key={project.id}>{project.title}</option>
                          ))}
                        </select>
                      </label>
                      <label className="snapshot-note-field">
                        <span>快照备注（可选）</span>
                        <input
                          value={snapshotNote}
                          maxLength={1000}
                          onChange={(event) => setSnapshotNote(event.target.value)}
                          placeholder="例如：关注长端上行是否延续"
                        />
                      </label>
                      <button
                        className="primary-button"
                        disabled={!marketBrief.snapshot_eligible || !selectedSignalIds.length || snapshotSaving}
                        onClick={saveMarketSnapshot}
                      >
                        {snapshotSaving ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}
                        保存 {selectedSignalIds.length} 项市场证据
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!marketBrief.snapshot_eligible || !selectedSignalIds.length || snapshotSaving}
                        onClick={addMarketSnapshotToBasket}
                      >
                        <Inbox size={14} /> 加入证据篮
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="primary-button" onClick={() => navigate("projects")}>
                        <BookOpenCheck size={14} /> 先创建研究项目
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!marketBrief.snapshot_eligible || !selectedSignalIds.length || snapshotSaving}
                        onClick={addMarketSnapshotToBasket}
                      >
                        <Inbox size={14} /> 先加入证据篮
                      </button>
                    </>
                  )}
                </div>
                <div className="market-brief-notice">
                  <span>{marketBrief.notice}</span>
                  {snapshotMessage ? (
                    <button
                      className="text-button"
                      onClick={() => navigate("projects", String(selectedProjectId ?? ""))}
                    >
                      {snapshotMessage} · 查看项目 <ArrowRight size={13} />
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </Panel>

          <div className="two-column research-desk-grid">
            <Panel
              title="最近研究项目"
              eyebrow="PROJECTS"
              action={
                <button className="text-button" onClick={() => navigate("projects")}>
                  查看全部 <ArrowRight size={14} />
                </button>
              }
            >
              {overview.projects.recent.length ? (
                <div className="research-project-list compact-project-list">
                  {overview.projects.recent.map((project) => (
                    <button key={project.id} onClick={() => navigate("projects", String(project.id))}>
                      <span className={`research-status ${project.status}`}>{statusLabels[project.status]}</span>
                      <div>
                        <strong>{project.title}</strong>
                        <small>{project.question || "尚未填写研究问题"}</small>
                      </div>
                      <span className="confidence-number">{project.confidence}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state compact-empty">
                  <BookOpenCheck size={26} />
                  <strong>还没有研究项目</strong>
                  <p>从一个可验证的研究问题开始。</p>
                </div>
              )}
            </Panel>

            <Panel
              title="需要处理的自选"
              eyebrow="FOCUS"
              action={
                <button className="text-button" onClick={() => navigate("watchlist")}>
                  管理自选 <ArrowRight size={14} />
                </button>
              }
            >
              {dueWatchlist.length ? (
                <div className="focus-watchlist">
                  {dueWatchlist.slice(0, 6).map((item) => (
                    <article key={item.id}>
                      {item.pinned ? <Pin size={14} /> : <CalendarClock size={14} />}
                      <div>
                        <strong>{item.name}</strong>
                        <small>
                          {item.group_name} · {statusLabels[item.research_status]}
                          {item.next_review_date ? ` · ${item.next_review_date}` : ""}
                        </small>
                      </div>
                      <span className="tag">{item.object_type === "macro" ? "指标" : "证券"}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state compact-empty">
                  <Star size={26} />
                  <strong>暂时没有到期待办</strong>
                  <p>置顶自选或设置下次复盘日期后会显示在这里。</p>
                </div>
              )}
            </Panel>
          </div>

          <Panel title="数据研究准备度" eyebrow="DATA READINESS">
            <div className="data-readiness-grid">
              <article>
                <Database size={18} />
                <div><strong>FRED 存储边界</strong><span>观测值不持久化</span></div>
              </article>
              <article>
                <ChartNoAxesCombined size={18} />
                <div><strong>研究证据</strong><span>保存引用，不保存 FRED 数值</span></div>
              </article>
              <article>
                <CalendarClock size={18} />
                <div><strong>最近更新</strong><span>{formatDateTime(overview.projects.recent[0]?.updated_at)}</span></div>
              </article>
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
