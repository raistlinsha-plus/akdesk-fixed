import { useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BellRing,
  BookOpenCheck,
  Calculator,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronRight,
  CircleDollarSign,
  Database,
  Gauge,
  FileText,
  Globe2,
  Landmark,
  Layers3,
  LoaderCircle,
  Menu,
  RefreshCcw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Star,
  TableProperties,
  Waves,
  X,
} from "lucide-react";
import { apiGet } from "./api";
import {
  AI_ASSISTANT_OPEN_EVENT,
  type AiAssistantOpenDetail,
} from "./aiBridge";
import { AlertsPanel } from "./components/AlertsPanel";
import { AiAssistantPanel } from "./components/AiAssistantPanel";
import { classNames } from "./components/UI";
import { trapFocus } from "./focus";
import { marketSessionLabel, researchAvailability } from "./healthStatus";
import { startVisibilityPolling } from "./visibilityPolling";
import { CalculatorPage } from "./pages/CalculatorPage";
import { HealthPage } from "./pages/HealthPage";
import { ChartLabPage } from "./pages/ChartLabPage";
import { InvestmentDeskPage } from "./pages/InvestmentDeskPage";
import { MacroPage } from "./pages/MacroPage";
import { MarketChangesPage } from "./pages/MarketChangesPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { CreditPage } from "./pages/CreditPage";
import { ReleaseReviewPage } from "./pages/ReleaseReviewPage";
import { ResearchPage } from "./pages/ResearchPage";
import { SovereignPage } from "./pages/SovereignPage";
import { ForexPage } from "./pages/ForexPage";
import { TopicResearchPage } from "./pages/TopicResearchPage";
import { WeeklyReviewPage } from "./pages/WeeklyReviewPage";
import {
  BondsPage,
  ConvertiblesPage,
  CurvesPage,
  DashboardPage,
  EventsPage,
  FuturesPage,
  MoneyPage,
  WatchlistPage,
} from "./pages/MarketPages";
import type { HealthItem, SearchResult } from "./types";
import {
  DEFAULT_WORKSPACE_MODE_KEY,
  SESSION_WORKSPACE_MODE_KEY,
  pageAfterModeSwitch,
  readWorkspaceMode,
  resolveInitialWorkspaceMode,
  workspaceHome,
  writeWorkspaceMode,
  type WorkspaceMode,
} from "./workspaceMode";
import { recordRecentMarketPage } from "./marketDashboard";
import {
  EXPERIENCE_PROFILES,
  experienceProfile,
  readExperienceProfile,
  writeExperienceProfile,
  type ExperienceProfileId,
} from "./experienceProfiles";

type PageId =
  | "research-desk"
  | "dashboard"
  | "market-changes"
  | "projects"
  | "topics"
  | "macro"
  | "sovereign"
  | "chart-lab"
  | "release-review"
  | "money"
  | "curves"
  | "bonds"
  | "futures"
  | "fx"
  | "credit"
  | "convertibles"
  | "events"
  | "calculator"
  | "report"
  | "weekly-review"
  | "watchlist"
  | "health";

interface NavItem {
  id: PageId;
  label: string;
  hint: string;
  icon: LucideIcon;
  keywords?: string;
}

interface GlobalAiStatus {
  configured: boolean;
  verified: boolean;
  runtime?: {
    task_state: "idle" | "queued" | "running";
    usage: { limit_reached: boolean };
  };
}

const NAV_ITEMS: Record<PageId, NavItem> = {
  "research-desk": { id: "research-desk", label: "研究首页", hint: "", icon: BookOpenCheck, keywords: "投研首页 宏观固收投研工作台" },
  dashboard: { id: "dashboard", label: "今日市场", hint: "", icon: Gauge, keywords: "固收市场 市场首页 今日固收脉搏" },
  "market-changes": { id: "market-changes", label: "市场变化", hint: "", icon: Activity, keywords: "变化 异动 上次查看 可信信号" },
  projects: { id: "projects", label: "研究项目", hint: "", icon: FileText, keywords: "开始一个研究 新建立项 研究问题" },
  topics: { id: "topics", label: "专题投研", hint: "", icon: Layers3, keywords: "专题 主题研究 跨源时间线 证据篮" },
  macro: { id: "macro", label: "美国宏观与利率", hint: "", icon: Globe2, keywords: "FRED 海外利率" },
  sovereign: { id: "sovereign", label: "全球主权比较", hint: "", icon: Globe2, keywords: "World Bank WDI 国家比较" },
  "chart-lab": { id: "chart-lab", label: "图表研究室", hint: "", icon: ChartNoAxesCombined },
  "release-review": { id: "release-review", label: "数据发布复盘", hint: "", icon: CalendarDays },
  money: { id: "money", label: "资金面", hint: "", icon: Waves },
  curves: { id: "curves", label: "收益率曲线", hint: "", icon: ChartNoAxesCombined },
  bonds: { id: "bonds", label: "现券市场", hint: "", icon: Landmark },
  futures: { id: "futures", label: "国债期货", hint: "", icon: Activity },
  fx: { id: "fx", label: "外汇市场", hint: "", icon: CircleDollarSign, keywords: "汇率 人民币 美元 外币对 FX USDCNY USDJPY EURUSD" },
  credit: { id: "credit", label: "信用观察 R2", hint: "", icon: ShieldCheck, keywords: "跟踪信用债 单券 发行人 组合 信用利差" },
  convertibles: { id: "convertibles", label: "可转债", hint: "", icon: TableProperties },
  events: { id: "events", label: "国债发行", hint: "", icon: CalendarDays },
  calculator: { id: "calculator", label: "固收计算器", hint: "", icon: Calculator },
  report: { id: "report", label: "每日复盘", hint: "", icon: FileText },
  "weekly-review": { id: "weekly-review", label: "每周复盘", hint: "", icon: BookOpenCheck, keywords: "做每周复盘 到期研究" },
  watchlist: { id: "watchlist", label: "我的自选", hint: "", icon: Star },
  health: { id: "health", label: "数据健康", hint: "", icon: Database, keywords: "检查数据 为什么不可用 连接 缓存" },
};

const ALL_NAVIGATION = Object.values(NAV_ITEMS);
const INTENT_SHORTCUTS: Array<{
  label: string;
  description: string;
  page: PageId;
  icon: LucideIcon;
}> = [
  { label: "今天市场怎么样", description: "查看资金、曲线、期货与外汇", page: "dashboard", icon: Gauge },
  { label: "开始一个研究", description: "从模板或空白问题立项", page: "projects", icon: FileText },
  { label: "整理一个专题", description: "建立跨源长期观察视图", page: "topics", icon: Layers3 },
  { label: "为什么数据不可用", description: "检查连接、缓存和可信状态", page: "health", icon: Database },
  { label: "跟踪信用债", description: "管理单券、主体和组合", page: "credit", icon: ShieldCheck },
  { label: "做每周复盘", description: "集中处理到期研究任务", page: "weekly-review", icon: BookOpenCheck },
];
const MARKET_HISTORY_PAGES = new Set<PageId>([
  "money", "curves", "bonds", "futures", "fx", "credit", "convertibles", "events",
]);

function item(id: PageId, overrides: Partial<NavItem> = {}): NavItem {
  return { ...NAV_ITEMS[id], ...overrides };
}

function navigationForMode(
  mode: WorkspaceMode,
): Array<{ label: string; items: NavItem[] }> {
  if (mode === "market") {
    return [
      {
        label: "今日",
        items: [
          item("dashboard", { label: "今日市场", hint: "⌘1" }),
          item("market-changes"),
          item("watchlist"),
          item("report"),
        ],
      },
      {
        label: "中国固收",
        items: [
          item("money"),
          item("curves"),
          item("bonds"),
          item("futures"),
          item("credit"),
          item("convertibles"),
          item("events"),
        ],
      },
      {
        label: "全球市场",
        items: [
          item("fx"),
          item("macro"),
          item("sovereign"),
          item("chart-lab"),
          item("release-review"),
        ],
      },
      {
        label: "投研与工具",
        items: [
          item("research-desk"),
          item("topics"),
          item("projects"),
          item("weekly-review"),
          item("calculator"),
          item("health"),
        ],
      },
    ];
  }
  return [
    {
      label: "研究工作台",
      items: [
        item("research-desk", { label: "研究首页", hint: "⌘1" }),
        item("topics"),
        item("projects"),
        item("watchlist"),
        item("weekly-review"),
      ],
    },
    {
      label: "数据研究",
      items: [
        item("chart-lab"),
        item("macro"),
        item("sovereign"),
        item("release-review"),
      ],
    },
    {
      label: "市场观察",
      items: [
        item("market-changes"),
        item("dashboard", { label: "固收市场" }),
        item("fx"),
        item("money"),
        item("curves"),
        item("bonds"),
        item("futures"),
        item("credit"),
        item("convertibles"),
      ],
    },
    {
      label: "复盘与工具",
      items: [
        item("report"),
        item("events"),
        item("calculator"),
        item("health"),
      ],
    },
  ];
}

function currentRoute(defaultPage: PageId): { page: PageId; query: string } {
  const raw = window.location.hash.replace("#/", "");
  const [pagePart, queryPart = ""] = raw.split("?", 2);
  const page = Object.prototype.hasOwnProperty.call(NAV_ITEMS, pagePart)
    ? (pagePart as PageId)
    : defaultPage;
  return {
    page,
    query: new URLSearchParams(queryPart).get("q") ?? "",
  };
}

export default function App() {
  const savedProfileId = readExperienceProfile(window.localStorage);
  const savedProfile = experienceProfile(savedProfileId);
  const savedDefaultMode = readWorkspaceMode(
    window.localStorage,
    DEFAULT_WORKSPACE_MODE_KEY,
  );
  const savedSessionMode = readWorkspaceMode(
    window.sessionStorage,
    SESSION_WORKSPACE_MODE_KEY,
  );
  const initialWorkspaceMode = resolveInitialWorkspaceMode(
    savedDefaultMode ?? savedProfile?.mode ?? null,
    savedSessionMode,
  );
  const initialRoute = currentRoute(
    savedSessionMode
      ? workspaceHome(initialWorkspaceMode)
      : (savedProfile?.landingPage as PageId | undefined) ?? workspaceHome(initialWorkspaceMode),
  );
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(
    initialWorkspaceMode,
  );
  const [experienceProfileId, setExperienceProfileId] =
    useState<ExperienceProfileId | null>(savedProfileId);
  const [onboardingOpen, setOnboardingOpen] = useState(savedProfileId === null);
  const [entrySettingsOpen, setEntrySettingsOpen] = useState(false);
  const [page, setPage] = useState<PageId>(initialRoute.page);
  const [pageQuery, setPageQuery] = useState(initialRoute.query);
  const [refreshSeed, setRefreshSeed] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [instrumentResults, setInstrumentResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const [health, setHealth] = useState<HealthItem[]>([]);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false);
  const [aiAssistantSeed, setAiAssistantSeed] =
    useState<AiAssistantOpenDetail | null>(null);
  const [globalAiStatus, setGlobalAiStatus] = useState<GlobalAiStatus | null>(null);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const searchDialogRef = useRef<HTMLElement>(null);
  const searchTriggerRef = useRef<HTMLElement | null>(null);
  const alertTriggerRef = useRef<HTMLButtonElement>(null);
  const aiAssistantTriggerRef = useRef<HTMLButtonElement>(null);
  const entrySettingsTriggerRef = useRef<HTMLButtonElement>(null);
  const entrySettingsDialogRef = useRef<HTMLElement>(null);
  const onboardingDialogRef = useRef<HTMLElement>(null);
  const onboardingMarketRef = useRef<HTMLButtonElement>(null);
  const navigation = useMemo(
    () => navigationForMode(workspaceMode),
    [workspaceMode],
  );
  const flatNavigation = useMemo(
    () => navigation.flatMap((group) => group.items),
    [navigation],
  );

  function openSearch() {
    searchTriggerRef.current = document.activeElement as HTMLElement | null;
    setSearchOpen(true);
    setActiveSearchIndex(0);
    window.setTimeout(() => searchRef.current?.focus(), 20);
  }

  function closeSearch() {
    setSearchOpen(false);
    setSearch("");
    setInstrumentResults([]);
    window.setTimeout(() => searchTriggerRef.current?.focus(), 20);
  }

  function closeAlerts() {
    setAlertsOpen(false);
    window.setTimeout(() => alertTriggerRef.current?.focus(), 20);
  }

  function closeAiAssistant() {
    setAiAssistantOpen(false);
    setAiAssistantSeed(null);
    window.setTimeout(() => aiAssistantTriggerRef.current?.focus(), 20);
  }

  function closeEntrySettings() {
    setEntrySettingsOpen(false);
    window.setTimeout(() => entrySettingsTriggerRef.current?.focus(), 20);
  }

  function navigate(next: string, query = "") {
    const target = next as PageId;
    if (!Object.prototype.hasOwnProperty.call(NAV_ITEMS, target)) return;
    if (MARKET_HISTORY_PAGES.has(target)) {
      recordRecentMarketPage(window.localStorage, target, NAV_ITEMS[target].label);
    }
    setPage(target);
    setPageQuery(query);
    const nextHash = "#/" + target + (query ? "?q=" + encodeURIComponent(query) : "");
    if (window.location.hash !== nextHash) {
      window.history.pushState(null, "", nextHash);
    }
    setSidebarOpen(false);
    setSearchOpen(false);
    setSearch("");
    setInstrumentResults([]);
  }

  function chooseExperienceProfile(id: ExperienceProfileId, activate: boolean) {
    const profile = experienceProfile(id);
    if (!profile) return;
    writeExperienceProfile(window.localStorage, id);
    writeWorkspaceMode(window.localStorage, DEFAULT_WORKSPACE_MODE_KEY, profile.mode);
    setExperienceProfileId(id);
    if (!activate) return;
    writeWorkspaceMode(window.sessionStorage, SESSION_WORKSPACE_MODE_KEY, profile.mode);
    setWorkspaceMode(profile.mode);
    setOnboardingOpen(false);
    setEntrySettingsOpen(false);
    navigate(profile.landingPage);
  }

  function switchWorkspaceMode(mode: WorkspaceMode) {
    if (mode === workspaceMode) return;
    writeWorkspaceMode(window.sessionStorage, SESSION_WORKSPACE_MODE_KEY, mode);
    setWorkspaceMode(mode);
    const nextPage = pageAfterModeSwitch(page, mode) as PageId;
    if (nextPage !== page) navigate(nextPage);
  }

  useEffect(() => {
    const handleHash = () => {
      const route = currentRoute(workspaceHome(workspaceMode));
      setPage(route.page);
      setPageQuery(route.query);
    };
    window.addEventListener("hashchange", handleHash);
    window.addEventListener("popstate", handleHash);
    return () => {
      window.removeEventListener("hashchange", handleHash);
      window.removeEventListener("popstate", handleHash);
    };
  }, [workspaceMode]);

  useEffect(() => {
    if (onboardingOpen) {
      window.setTimeout(() => onboardingMarketRef.current?.focus(), 20);
    }
  }, [onboardingOpen]);

  useEffect(() => {
    if (entrySettingsOpen) {
      window.setTimeout(
        () => entrySettingsDialogRef.current?.querySelector<HTMLElement>("button, input")?.focus(),
        20,
      );
    }
  }, [entrySettingsOpen]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openSearch();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "r") {
        event.preventDefault();
        setRefreshSeed((value) => value + 1);
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "1") {
        event.preventDefault();
        navigate(workspaceHome(workspaceMode));
      }
      if (event.key === "Escape") {
        if (searchOpen) closeSearch();
        if (alertsOpen) closeAlerts();
        if (aiAssistantOpen) closeAiAssistant();
        if (entrySettingsOpen) closeEntrySettings();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [aiAssistantOpen, alertsOpen, entrySettingsOpen, searchOpen, workspaceMode]);

  useEffect(() => {
    function handleAiOpen(event: Event) {
      const detail = (event as CustomEvent<AiAssistantOpenDetail>).detail;
      setAlertsOpen(false);
      setAiAssistantSeed(detail);
      setAiAssistantOpen(true);
    }
    window.addEventListener(AI_ASSISTANT_OPEN_EVENT, handleAiOpen);
    return () => window.removeEventListener(AI_ASSISTANT_OPEN_EVENT, handleAiOpen);
  }, []);

  useEffect(() => {
    const term = search.trim();
    setActiveSearchIndex(0);
    if (!searchOpen || !term) {
      setInstrumentResults([]);
      setSearchLoading(false);
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearchLoading(true);
      apiGet<SearchResult[]>("/search?q=" + encodeURIComponent(term), {
        signal: controller.signal,
      })
        .then((results) => {
          if (active) setInstrumentResults(results);
        })
        .catch((reason: unknown) => {
          if (
            active &&
            !(reason instanceof DOMException && reason.name === "AbortError")
          ) {
            setInstrumentResults([]);
          }
        })
        .finally(() => {
          if (active) setSearchLoading(false);
        });
    }, 160);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [search, searchOpen]);

  useEffect(() => {
    function loadHealth() {
      apiGet<HealthItem[]>("/sources/health").then(setHealth).catch(() => undefined);
    }
    loadHealth();
    return startVisibilityPolling(loadHealth, 30_000);
  }, [refreshSeed]);

  useEffect(() => {
    function loadUnread() {
      apiGet<{ count: number }>("/alerts/unread-count")
        .then((result) => setUnreadAlerts(result.count))
        .catch(() => undefined);
    }
    loadUnread();
    return startVisibilityPolling(loadUnread, 30_000);
  }, []);

  useEffect(() => {
    function loadAiStatus() {
      apiGet<GlobalAiStatus>("/ai/status")
        .then(setGlobalAiStatus)
        .catch(() => setGlobalAiStatus(null));
    }
    loadAiStatus();
    return startVisibilityPolling(loadAiStatus, 30_000);
  }, [aiAssistantOpen]);

  const current = flatNavigation.find((item) => item.id === page);
  const navigationResults = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return ALL_NAVIGATION;
    return ALL_NAVIGATION.filter((item) =>
      `${item.label} ${item.id} ${item.keywords ?? ""}`.toLowerCase().includes(term),
    );
  }, [search]);
  const searchableItems: Array<NavItem | SearchResult> = [
    ...navigationResults,
    ...instrumentResults,
  ];

  const availability = researchAvailability(health);
  const marketSession = marketSessionLabel(health, page);
  const marketTrading = marketSession.includes("交易中");

  function activateSearchResult() {
    const selected = searchableItems[activeSearchIndex];
    if (!selected) return;
    if ("id" in selected) navigate(selected.id);
    else navigate(selected.page, selected.object_id);
  }

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        跳到主要内容
      </a>
      <aside className={classNames("sidebar", sidebarOpen && "open")}>
        <div className="brand">
          <div className="brand-mark"><span /><span /><span /></div>
          <div>
            <strong>AKDesk</strong>
            <small>{workspaceMode === "market" ? "MARKET · LOCAL" : "RESEARCH · LOCAL"}</small>
          </div>
          <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="关闭菜单">
            <X size={18} />
          </button>
        </div>

        <button className="command-button" onClick={openSearch}>
          <Search size={16} /><span>搜索功能或标的</span><kbd>⌘K</kbd>
        </button>

        <nav>
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span>{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={classNames("nav-item", page === item.id && "active")}
                    onClick={() => navigate(item.id)}
                    aria-current={page === item.id ? "page" : undefined}
                  >
                    <Icon size={17} strokeWidth={1.8} />
                    <span>{item.label}</span>
                    {item.hint ? <small>{item.hint}</small> : null}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button onClick={() => navigate("health")}>
            <span className={classNames(
              "live-dot",
              availability.blocked > 0 && "red",
              availability.blocked === 0 && (availability.limited > 0 || availability.unchecked > 0) && "amber",
            )} />
            <div>
              <strong>
                {availability.blocked > 0
                  ? availability.blocked + " 个数据源不可用于研究"
                  : availability.limited > 0
                    ? availability.limited + " 个数据源受限可用"
                    : availability.unchecked > 0
                      ? "研究可用性待检查"
                      : "研究数据可信可用"}
              </strong>
              <small>查看数据健康</small>
            </div>
            <ChevronRight size={15} />
          </button>
          <p>仅供研究参考，不构成投资建议</p>
        </div>
      </aside>

      {sidebarOpen ? (
        <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-label="关闭侧栏" />
      ) : null}

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="打开菜单">
              <Menu size={19} />
            </button>
            <div className="breadcrumb">
              <span>{workspaceMode === "market" ? "市场模式" : "投研模式"}</span>
              <ChevronRight size={14} />
              <strong>{current?.label}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="workspace-mode-switch" role="group" aria-label="工作模式">
              <button
                className={workspaceMode === "market" ? "active" : undefined}
                onClick={() => switchWorkspaceMode("market")}
                aria-pressed={workspaceMode === "market"}
              >
                市场
              </button>
              <button
                className={workspaceMode === "research" ? "active" : undefined}
                onClick={() => switchWorkspaceMode("research")}
                aria-pressed={workspaceMode === "research"}
              >
                投研
              </button>
              <button
                ref={entrySettingsTriggerRef}
                className="workspace-mode-settings"
                onClick={() => setEntrySettingsOpen(true)}
                aria-label="入口设置"
                title="入口设置"
              >
                <Settings2 size={14} />
              </button>
            </div>
            <span className="market-session">
              <span className={classNames("live-dot", !marketTrading && "amber")} />
              {marketSession}
            </span>
            <button
              ref={aiAssistantTriggerRef}
              className={classNames("ai-assistant-trigger", aiAssistantOpen && "active")}
              title={
                globalAiStatus?.runtime?.task_state === "running"
                  ? "AI 正在生成"
                  : globalAiStatus?.runtime?.usage.limit_reached
                    ? "AI 今日预算已用完"
                    : globalAiStatus?.configured
                      ? "AI 研究助手已配置"
                      : "AI 研究助手未配置"
              }
              aria-label="打开 AI 研究助手"
              aria-expanded={aiAssistantOpen}
              aria-controls="ai-assistant-drawer"
              onClick={() => {
                if (aiAssistantOpen) {
                  closeAiAssistant();
                } else {
                  setAlertsOpen(false);
                  setAiAssistantSeed(null);
                  setAiAssistantOpen(true);
                }
              }}
            >
              <span
                className={classNames(
                  "ai-status-dot",
                  !globalAiStatus?.configured && "unconfigured",
                  globalAiStatus?.runtime?.usage.limit_reached && "limited",
                  globalAiStatus?.runtime?.task_state === "running" && "running",
                )}
                aria-hidden="true"
              />
              <Sparkles size={14} /> AI 助手
            </button>
            <button
              className="icon-button"
              onClick={() => setRefreshSeed((value) => value + 1)}
              title="刷新当前数据（⌘R）"
              aria-label="刷新当前数据"
            >
              <RefreshCcw size={16} />
            </button>
            <button
              ref={alertTriggerRef}
              className={classNames("icon-button", "notification-button", alertsOpen && "active")}
              title="提醒"
              aria-label={unreadAlerts ? `提醒，${unreadAlerts} 条未读` : "提醒"}
              aria-expanded={alertsOpen}
              aria-controls="alert-drawer"
              onClick={() => {
                if (alertsOpen) {
                  closeAlerts();
                } else {
                  setAiAssistantOpen(false);
                  setAlertsOpen(true);
                }
              }}
            >
              <BellRing size={16} />
              {unreadAlerts ? <span className="notification-badge">{Math.min(unreadAlerts, 99)}</span> : null}
            </button>
          </div>
        </header>

        <main className="content" id="main-content" tabIndex={-1}>
          {page === "research-desk" ? <InvestmentDeskPage refreshSeed={refreshSeed} navigate={navigate} /> : null}
          {page === "dashboard" ? <DashboardPage refreshSeed={refreshSeed} navigate={navigate} /> : null}
          {page === "market-changes" ? <MarketChangesPage refreshSeed={refreshSeed} navigate={navigate} /> : null}
          {page === "projects" ? <ProjectsPage initialQuery={pageQuery} navigate={navigate} /> : null}
          {page === "topics" ? <TopicResearchPage initialQuery={pageQuery} /> : null}
          {page === "macro" ? <MacroPage initialQuery={pageQuery} navigate={navigate} /> : null}
          {page === "sovereign" ? <SovereignPage initialQuery={pageQuery} refreshSeed={refreshSeed} /> : null}
          {page === "chart-lab" ? <ChartLabPage initialQuery={pageQuery} /> : null}
          {page === "release-review" ? <ReleaseReviewPage /> : null}
          {page === "money" ? <MoneyPage refreshSeed={refreshSeed} /> : null}
          {page === "curves" ? <CurvesPage refreshSeed={refreshSeed} /> : null}
          {page === "bonds" ? <BondsPage refreshSeed={refreshSeed} initialQuery={pageQuery} /> : null}
          {page === "futures" ? <FuturesPage refreshSeed={refreshSeed} initialQuery={pageQuery} /> : null}
          {page === "fx" ? <ForexPage refreshSeed={refreshSeed} initialQuery={pageQuery} /> : null}
          {page === "credit" ? <CreditPage /> : null}
          {page === "convertibles" ? <ConvertiblesPage refreshSeed={refreshSeed} initialQuery={pageQuery} /> : null}
          {page === "events" ? <EventsPage refreshSeed={refreshSeed} /> : null}
          {page === "report" ? <ResearchPage refreshSeed={refreshSeed} /> : null}
          {page === "weekly-review" ? <WeeklyReviewPage refreshSeed={refreshSeed} /> : null}
          {page === "calculator" ? <CalculatorPage /> : null}
          {page === "watchlist" ? <WatchlistPage navigate={navigate} /> : null}
          {page === "health" ? <HealthPage /> : null}
        </main>
      </div>

      {searchOpen ? (
        <div className="command-overlay" onMouseDown={closeSearch}>
          <section
            ref={searchDialogRef}
            className="command-palette"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => trapFocus(event, searchDialogRef.current)}
            role="dialog"
            aria-modal="true"
            aria-label="全局搜索"
          >
            <div className="command-input">
              <Search size={18} />
              <input
                ref={searchRef}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setActiveSearchIndex((value) => searchableItems.length ? (value + 1) % searchableItems.length : 0);
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setActiveSearchIndex((value) => searchableItems.length ? (value - 1 + searchableItems.length) % searchableItems.length : 0);
                  }
                  if (event.key === "Enter") {
                    event.preventDefault();
                    activateSearchResult();
                  }
                }}
                placeholder="试试：今天市场怎么样、开始一个研究…"
                autoFocus
              />
              <kbd>ESC</kbd>
            </div>
            {!search.trim() ? (
              <div className="command-intent-shortcuts" aria-label="常用任务">
                <span className="eyebrow">常用任务</span>
                <div>
                  {INTENT_SHORTCUTS.map((shortcut) => {
                    const Icon = shortcut.icon;
                    return (
                      <button type="button" onClick={() => navigate(shortcut.page)} key={shortcut.label}>
                        <Icon size={15} />
                        <span><strong>{shortcut.label}</strong><small>{shortcut.description}</small></span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
            <div className="command-results" role="listbox">
              <span className="eyebrow">功能</span>
              {navigationResults.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button
                    className={activeSearchIndex === index ? "active" : undefined}
                    key={item.id}
                    onMouseEnter={() => setActiveSearchIndex(index)}
                    onClick={() => navigate(item.id)}
                    role="option"
                    aria-selected={activeSearchIndex === index}
                  >
                    <Icon size={17} />
                    <div><strong>{item.label}</strong><small>{item.id}</small></div>
                    <ChevronRight size={15} />
                  </button>
                );
              })}

              {search.trim() ? <span className="eyebrow command-group-title">标的</span> : null}
              {instrumentResults.map((item, index) => {
                const Icon = item.object_type === "bond" ? Landmark : item.object_type === "future" ? Activity : item.object_type === "macro" ? Globe2 : item.object_type === "fx" ? CircleDollarSign : item.object_type === "topic" ? Layers3 : TableProperties;
                const combinedIndex = navigationResults.length + index;
                return (
                  <button
                    className={activeSearchIndex === combinedIndex ? "active" : undefined}
                    key={item.object_type + item.object_id}
                    onMouseEnter={() => setActiveSearchIndex(combinedIndex)}
                    onClick={() => navigate(item.page, item.object_id)}
                    role="option"
                    aria-selected={activeSearchIndex === combinedIndex}
                  >
                    <Icon size={17} />
                    <div><strong>{item.name}</strong><small>{item.object_id} · {item.subtitle}</small></div>
                    <ChevronRight size={15} />
                  </button>
                );
              })}
              {searchLoading ? (
                <div className="command-empty"><LoaderCircle className="spin" size={16} /> 正在搜索标的</div>
              ) : null}
              {!searchLoading && search.trim() && !searchableItems.length ? (
                <div className="command-empty">没有找到匹配的功能或标的</div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

      {entrySettingsOpen ? (
        <div className="entry-settings-overlay" onMouseDown={closeEntrySettings}>
          <section
            ref={entrySettingsDialogRef}
            className="entry-settings-dialog"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => trapFocus(event, entrySettingsDialogRef.current)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="entry-settings-title"
          >
            <header>
              <div>
                <span className="eyebrow">WORKSPACE ENTRY</span>
                <h2 id="entry-settings-title">入口设置</h2>
              </div>
              <button className="icon-button" onClick={closeEntrySettings} aria-label="关闭入口设置">
                <X size={16} />
              </button>
            </header>
            <div className="entry-settings-content">
              <div className="entry-settings-current">
                <span>默认使用场景</span>
                <strong>{experienceProfile(experienceProfileId)?.label ?? "尚未选择"}</strong>
                <small>场景只决定默认落地页和导航优先级，不会隐藏功能或拆分数据库。</small>
              </div>
              <fieldset className="default-mode-options">
                <legend>下次启动默认进入</legend>
                {EXPERIENCE_PROFILES.map((profile) => (
                  <label className={experienceProfileId === profile.id ? "active" : undefined} key={profile.id}>
                    <input
                      type="radio"
                      name="default-experience-profile"
                      checked={experienceProfileId === profile.id}
                      onChange={() => chooseExperienceProfile(profile.id, false)}
                    />
                    <div>
                      <strong>{profile.label}</strong>
                      <span>{profile.action} · {profile.mode === "market" ? "市场导航" : "投研导航"}</span>
                    </div>
                  </label>
                ))}
              </fieldset>
              <div className="entry-settings-shortcuts">
                <button
                  className="text-button"
                  onClick={() => {
                    setEntrySettingsOpen(false);
                    navigate("health");
                  }}
                >
                  <Database size={14} /> 检查数据连接
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    setEntrySettingsOpen(false);
                    setAiAssistantSeed({ scenario: "help", focusRuntimeSettings: true });
                    setAiAssistantOpen(true);
                  }}
                >
                  <Sparkles size={14} /> AI 与隐私设置
                </button>
              </div>
              <div className="entry-settings-actions">
                <button
                  className="text-button"
                  onClick={() => {
                    setEntrySettingsOpen(false);
                    setOnboardingOpen(true);
                  }}
                >
                  重新查看入口说明
                </button>
                <button className="secondary-button" onClick={closeEntrySettings}>完成</button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {onboardingOpen ? (
        <div className="workspace-onboarding-overlay">
          <section
            ref={onboardingDialogRef}
            className="workspace-onboarding"
            onKeyDown={(event) => trapFocus(event, onboardingDialogRef.current)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="workspace-onboarding-title"
          >
            <div className="workspace-onboarding-copy">
              <span className="eyebrow">AKDESK FIXED · V1.0.0</span>
              <h1 id="workspace-onboarding-title">你通常先做哪件事？</h1>
              <p>选择一个使用场景即可开始。它只设置默认落地页和导航顺序；全部行情、投研、信用与全球模块仍可随时访问。</p>
            </div>
            <div className="workspace-choice-grid">
              {EXPERIENCE_PROFILES.map((profile, index) => {
                const Icon = profile.id === "market"
                  ? Gauge
                  : profile.id === "rates"
                    ? BookOpenCheck
                    : profile.id === "credit"
                      ? ShieldCheck
                      : Globe2;
                return (
                  <button
                    ref={index === 0 ? onboardingMarketRef : undefined}
                    onClick={() => chooseExperienceProfile(profile.id, true)}
                    key={profile.id}
                  >
                    <span className="workspace-choice-icon"><Icon size={24} /></span>
                    <span className="workspace-choice-kicker">{profile.kicker}</span>
                    <strong>{profile.label}</strong>
                    <p>{profile.description}</p>
                    <span className="workspace-choice-action">{profile.action} <ChevronRight size={16} /></span>
                  </button>
                );
              })}
            </div>
            <div className="workspace-onboarding-path" aria-label="推荐使用路径">
              <span>首次使用建议</span>
              <ol>
                <li><strong>1</strong>检查数据状态</li>
                <li><strong>2</strong>建立自选</li>
                <li><strong>3</strong>创建项目或专题</li>
                <li><strong>4</strong>保存证据并复盘</li>
              </ol>
            </div>
            <footer>
              <ShieldCheck size={15} />
              <span>选择只影响默认首页和导航排序，不会隐藏功能或拆分数据。</span>
            </footer>
          </section>
        </div>
      ) : null}

      <AlertsPanel
        open={alertsOpen}
        onClose={closeAlerts}
        onUnreadChange={setUnreadAlerts}
      />
      <AiAssistantPanel
        open={aiAssistantOpen}
        onClose={closeAiAssistant}
        currentPage={page}
        seed={aiAssistantSeed}
      />
    </div>
  );
}
