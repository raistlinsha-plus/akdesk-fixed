import {
  Building2,
  CalendarDays,
  CheckCircle2,
  Download,
  History,
  Layers3,
  LoaderCircle,
  Newspaper,
  Pencil,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { apiDelete, apiDownload, apiGet, apiPatch, apiPost, apiPostFile } from "../api";
import { CreateProjectButton } from "../components/CreateProjectButton";
import { AiInsightCard } from "../components/AiInsightCard";
import { ErrorState, LoadingState, Panel, formatNumber } from "../components/UI";
import {
  CREDIT_BOND_PAGE_SIZE,
  buildCreditImportPath,
  calculateCreditWorkspaceScrollTop,
  filterCreditIssuers,
  filterCreditItems,
  filterCreditPortfolioMembers,
  nextCreditVisibleCount,
  toggleCreditMember,
} from "../creditR2";
import type {
  CreditCandidates,
  CreditCoverageItem,
  CreditImportPreview,
  CreditPortfolio,
  CreditWorkspace,
  ResearchProject,
} from "../types";
import { PageHeading } from "./MarketPages";

const emptyForm = {
  bond_code: "",
  bond_name: "",
  issuer: "",
  canonical_issuer: "",
  sector: "",
  region: "",
  issuer_type: "",
  maturity_date: "",
  put_date: "",
  rating: "",
  rating_date: "",
  yield_pct: "",
  yield_observation_date: "",
  benchmark_tenor: "5Y",
  benchmark_yield_pct: "",
  benchmark_observation_date: "",
  source_note: "",
  next_review_date: "",
  watch_status: "active",
};

const primaryCreditFields = [
  ["bond_code", "债券代码"],
  ["bond_name", "债券名称"],
  ["issuer", "发行人原名"],
  ["maturity_date", "到期日"],
  ["rating", "债项评级"],
  ["rating_date", "评级日期"],
  ["yield_pct", "到期收益率 %"],
  ["yield_observation_date", "收益率日期"],
  ["benchmark_yield_pct", "基准收益率 %"],
  ["benchmark_observation_date", "基准日期"],
  ["source_note", "来源说明"],
] as const;

const advancedCreditFields = [
  ["canonical_issuer", "主体归一名"],
  ["sector", "行业"],
  ["region", "地区"],
  ["issuer_type", "主体类型"],
  ["put_date", "回售日"],
  ["next_review_date", "下次复盘日"],
] as const;

const creditFieldLabels: Record<string, string> = {
  bond_code: "债券代码",
  bond_name: "债券名称",
  issuer: "发行人原名",
  canonical_issuer: "主体归一名",
  sector: "行业",
  region: "地区",
  issuer_type: "主体类型",
  maturity_date: "到期日",
  put_date: "回售日",
  rating: "债项评级",
  rating_date: "评级日期",
  yield_pct: "到期收益率",
  yield_observation_date: "收益率日期",
  benchmark_tenor: "基准期限",
  benchmark_yield_pct: "基准收益率",
  benchmark_observation_date: "基准日期",
  source_note: "来源说明",
  next_review_date: "下次复盘日",
  watch_status: "观察状态",
};

const trustLabels: Record<string, string> = {
  trusted: "可信",
  partial: "部分可信",
  suspicious: "可疑",
  unavailable: "不可用",
};

const statusLabels: Record<string, string> = {
  active: "正常观察",
  watch: "重点关注",
  review: "待复盘",
  archived: "已归档",
};

const eventLabels: Record<string, string> = {
  rating_review: "评级复核",
  put: "回售",
  maturity: "到期",
  review: "研究复盘",
};

type CreditView = "bonds" | "issuers" | "portfolios";
const creditViews: CreditView[] = ["bonds", "issuers", "portfolios"];

function formatSpreadRange(
  range?: { minimum: number; maximum: number; count: number } | null,
) {
  if (!range) return "—";
  const values = range.minimum === range.maximum
    ? `${formatNumber(range.minimum, 2)} BP`
    : `${formatNumber(range.minimum, 2)}–${formatNumber(range.maximum, 2)} BP`;
  return `${values} · ${range.count} 只`;
}

export function CreditPage() {
  const [workspace, setWorkspace] = useState<CreditWorkspace | null>(null);
  const [candidates, setCandidates] = useState<CreditCandidates | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [view, setView] = useState<CreditView>("bonds");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [visibleBondCount, setVisibleBondCount] = useState(CREDIT_BOND_PAGE_SIZE);
  const [scrollResetRequest, setScrollResetRequest] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<CreditImportPreview | null>(null);
  const [importMapping, setImportMapping] = useState<Record<string, string>>({});
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [portfolioName, setPortfolioName] = useState("");
  const [portfolioDescription, setPortfolioDescription] = useState("");
  const [portfolioMembers, setPortfolioMembers] = useState<number[]>([]);
  const [portfolioMemberSearch, setPortfolioMemberSearch] = useState("");
  const [portfolioSelectedOnly, setPortfolioSelectedOnly] = useState(false);
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [signalComposerId, setSignalComposerId] = useState<string | null>(null);
  const [signalNote, setSignalNote] = useState("");
  const [signalProjectId, setSignalProjectId] = useState("");
  const [openingIssuer, setOpeningIssuer] = useState<string | null>(null);
  const maintenanceRef = useRef<HTMLDetailsElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const activePanelRef = useRef<HTMLDivElement>(null);
  const bondTabRef = useRef<HTMLButtonElement>(null);
  const issuerTabRef = useRef<HTMLButtonElement>(null);
  const portfolioTabRef = useRef<HTMLButtonElement>(null);

  function load() {
    setLoading(true);
    Promise.all([
      apiGet<CreditWorkspace>("/credit/workspace"),
      apiGet<CreditCandidates>("/credit/candidates"),
      apiGet<ResearchProject[]>("/research/projects"),
    ])
      .then(([saved, assisted, availableProjects]) => {
        setWorkspace(saved);
        setCandidates(assisted);
        setProjects(availableProjects);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "信用观察加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const filteredItems = useMemo(() => {
    return filterCreditItems(workspace?.items || [], search, statusFilter);
  }, [search, statusFilter, workspace]);

  const filteredIssuers = useMemo(() => {
    return filterCreditIssuers(workspace?.issuers || [], search);
  }, [search, workspace]);

  const visibleItems = useMemo(
    () => filteredItems.slice(0, visibleBondCount),
    [filteredItems, visibleBondCount],
  );

  const filteredPortfolioMembers = useMemo(
    () => filterCreditPortfolioMembers(
      workspace?.items || [],
      portfolioMemberSearch,
      portfolioSelectedOnly,
      portfolioMembers,
    ),
    [portfolioMemberSearch, portfolioMembers, portfolioSelectedOnly, workspace],
  );

  function requestWorkspaceScrollReset() {
    setScrollResetRequest((current) => current + 1);
  }

  function selectView(nextView: CreditView, focusTab = false) {
    setView(nextView);
    setVisibleBondCount(CREDIT_BOND_PAGE_SIZE);
    requestWorkspaceScrollReset();
    if (focusTab) {
      window.requestAnimationFrame(() => {
        const refs = {
          bonds: bondTabRef,
          issuers: issuerTabRef,
          portfolios: portfolioTabRef,
        };
        refs[nextView].current?.focus();
      });
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentView: CreditView) {
    const currentIndex = creditViews.indexOf(currentView);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (currentIndex + 1) % creditViews.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (currentIndex - 1 + creditViews.length) % creditViews.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = creditViews.length - 1;
    }
    if (nextIndex == null) return;
    event.preventDefault();
    selectView(creditViews[nextIndex], true);
  }

  useEffect(() => {
    if (!scrollResetRequest) return;
    const frame = window.requestAnimationFrame(() => {
      const panel = activePanelRef.current;
      const toolbar = toolbarRef.current;
      const container = panel?.closest<HTMLElement>(".content");
      if (!panel || !toolbar || !container) return;
      const panelRect = panel.getBoundingClientRect();
      const toolbarRect = toolbar.getBoundingClientRect();
      const target = calculateCreditWorkspaceScrollTop({
        currentScrollTop: container.scrollTop,
        panelTop: panelRect.top,
        toolbarBottom: toolbarRect.bottom,
      });
      container.scrollTo({ top: target, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [scrollResetRequest]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setStatusMessage(null);
    const optionalNumber = (value: string) => (value === "" ? null : Number(value));
    try {
      const payload = {
        ...form,
        maturity_date: form.maturity_date || null,
        put_date: form.put_date || null,
        rating_date: form.rating_date || null,
        yield_pct: optionalNumber(form.yield_pct),
        yield_observation_date: form.yield_observation_date || null,
        benchmark_yield_pct: optionalNumber(form.benchmark_yield_pct),
        benchmark_observation_date: form.benchmark_observation_date || null,
        next_review_date: form.next_review_date || null,
      };
      if (editingId) {
        const update = Object.fromEntries(
          Object.entries(payload).filter(([field]) => !["bond_code", "bond_name"].includes(field)),
        );
        await apiPatch(`/credit/observations/${editingId}`, update);
        setStatusMessage("信用观察已更新，新的人工快照已进入历史时间线。");
      } else {
        await apiPost("/credit/observations", payload);
        setStatusMessage("信用观察已保存并通过质量门检查。");
      }
      setEditingId(null);
      setForm(emptyForm);
      setMaintenanceOpen(false);
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用观察保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(`确认删除“${name}”及其本地信用历史？`)) return;
    try {
      await apiDelete(`/credit/observations/${id}`);
      if (editingId === id) {
        setEditingId(null);
        setForm(emptyForm);
      }
      setStatusMessage(`已删除“${name}”。`);
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用观察删除失败");
    }
  }

  function beginEdit(item: CreditCoverageItem) {
    setEditingId(item.id);
    setForm({
      bond_code: item.bond_code,
      bond_name: item.bond_name,
      issuer: item.issuer,
      canonical_issuer: item.canonical_issuer,
      sector: item.sector,
      region: item.region,
      issuer_type: item.issuer_type,
      maturity_date: item.maturity_date || "",
      put_date: item.put_date || "",
      rating: item.rating,
      rating_date: item.rating_date || "",
      yield_pct: item.yield_pct == null ? "" : String(item.yield_pct),
      yield_observation_date: item.yield_observation_date || "",
      benchmark_tenor: item.benchmark_tenor || "5Y",
      benchmark_yield_pct: item.benchmark_yield_pct == null ? "" : String(item.benchmark_yield_pct),
      benchmark_observation_date: item.benchmark_observation_date || "",
      source_note: item.source_note,
      next_review_date: item.next_review_date || "",
      watch_status: item.watch_status,
    });
    setMaintenanceOpen(true);
    window.requestAnimationFrame(() => maintenanceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function applyCandidate(code: string) {
    const item = candidates?.candidates.find((value) => value.bond_code === code);
    if (!item) return;
    setForm((current) => ({
      ...current,
      bond_code: item.bond_code,
      bond_name: item.bond_name,
      yield_pct: String(item.yield_pct),
      yield_observation_date: item.yield_observation_date || "",
    }));
  }

  function applyBenchmark() {
    const value = candidates?.benchmark_curve.values[form.benchmark_tenor];
    if (value === undefined) return;
    setForm((current) => ({
      ...current,
      benchmark_yield_pct: String(value),
      benchmark_observation_date: candidates?.benchmark_curve.observation_date || "",
    }));
  }

  function importPath(commit: boolean, mapping = importMapping) {
    if (!importFile) return "";
    return buildCreditImportPath(importFile.name, commit, mapping);
  }

  async function previewImport(file: File, mapping?: Record<string, string>) {
    setSaving(true);
    setError(null);
    try {
      const activeMapping = mapping || {};
      const preview = await apiPostFile<CreditImportPreview>(buildCreditImportPath(file.name, false, activeMapping), file);
      setImportFile(file);
      setImportPreview(preview);
      setImportMapping(preview.mapping);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用文件预览失败");
    } finally {
      setSaving(false);
    }
  }

  function chooseImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      setMaintenanceOpen(true);
      void previewImport(file);
    }
  }

  async function commitImport() {
    if (!importFile || !importPreview || importPreview.errors.length) return;
    if (!window.confirm(`确认导入 ${importPreview.valid_rows} 行？同一债券的多日期记录会保存为历史快照。`)) return;
    setSaving(true);
    setError(null);
    try {
      const result = await apiPostFile<CreditImportPreview>(importPath(true), importFile);
      setStatusMessage(`已导入 ${result.imported_rows || 0} 行，更新 ${result.observations || 0} 只债券。`);
      setImportFile(null);
      setImportPreview(null);
      setImportMapping({});
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用文件导入失败");
    } finally {
      setSaving(false);
    }
  }

  async function confirmSignal(signalId: string) {
    setSaving(true);
    setError(null);
    try {
      await apiPost(`/credit/signals/${signalId}/confirm`, {
        note: signalNote.trim(),
        project_id: signalProjectId ? Number(signalProjectId) : null,
      });
      setStatusMessage(signalProjectId
        ? "风险信号已确认并写入研究项目复盘记录；确认不代表投资结论。"
        : "风险信号已人工确认；确认不代表投资结论。");
      setSignalComposerId(null);
      setSignalNote("");
      setSignalProjectId("");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信号确认失败");
    } finally {
      setSaving(false);
    }
  }

  function registerProject(project: ResearchProject) {
    setProjects((current) => current.some((item) => item.id === project.id)
      ? current
      : [project, ...current]);
  }

  async function openIssuerEvents(issuer: string) {
    setOpeningIssuer(issuer);
    setError(null);
    try {
      const topic = await apiPost<{ id: number }>("/research/topics/from-issuer-events", { issuer });
      window.location.assign(`#/topics?q=${topic.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发行人事件专题创建失败");
    } finally {
      setOpeningIssuer(null);
    }
  }

  function editPortfolio(portfolio: CreditPortfolio) {
    setPortfolioId(portfolio.id);
    setPortfolioName(portfolio.name);
    setPortfolioDescription(portfolio.description);
    setPortfolioMembers(portfolio.observation_ids);
    setPortfolioMemberSearch("");
    setPortfolioSelectedOnly(false);
    selectView("portfolios");
  }

  function resetPortfolio() {
    setPortfolioId(null);
    setPortfolioName("");
    setPortfolioDescription("");
    setPortfolioMembers([]);
    setPortfolioMemberSearch("");
    setPortfolioSelectedOnly(false);
  }

  async function savePortfolio(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: portfolioName,
        description: portfolioDescription,
        observation_ids: portfolioMembers,
      };
      if (portfolioId) await apiPatch(`/credit/portfolios/${portfolioId}`, payload);
      else await apiPost("/credit/portfolios", payload);
      setStatusMessage(portfolioId ? "信用组合已更新。" : "信用组合已创建。");
      resetPortfolio();
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用组合保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function deletePortfolio(portfolio: CreditPortfolio) {
    if (!window.confirm(`确认删除组合“${portfolio.name}”？单券观察不会被删除。`)) return;
    try {
      await apiDelete(`/credit/portfolios/${portfolio.id}`);
      if (portfolioId === portfolio.id) resetPortfolio();
      setStatusMessage(`已删除组合“${portfolio.name}”。`);
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "信用组合删除失败");
    }
  }

  return (
    <div className="page-stack credit-r2-page">
      <PageHeading
        eyebrow="CREDIT OBSERVATION R2"
        title="信用观察 R2"
        description="把人工核验字段组织成单券、主体与组合三级观察，并保留历史、来源和确认边界"
      />
      {error ? <ErrorState message={error} /> : null}
      {statusMessage ? <p className="success-banner" role="status">{statusMessage}</p> : null}
      {loading ? <LoadingState /> : null}

      {workspace ? (
        <>
          <div className="metrics-grid credit-r2-metrics">
            <article className="metric-card"><span>观察单券</span><strong>{workspace.total}</strong></article>
            <article className="metric-card"><span>发行主体</span><strong>{workspace.summary.issuers}</strong></article>
            <article className="metric-card"><span>可信历史点</span><strong>{workspace.summary.history_points}</strong></article>
            <article className="metric-card"><span>通过门槛</span><strong>{workspace.eligible}</strong></article>
            <article className="metric-card"><span>待确认信号</span><strong>{workspace.summary.unconfirmed_signals}</strong></article>
            <article className="metric-card"><span>自定义组合</span><strong>{workspace.summary.portfolios}</strong></article>
          </div>
        </>
      ) : null}

      {workspace ? (
        <AiInsightCard
          contextType="credit"
          title="信用观察 AI 洞察"
          description="汇总规则信号、数据缺口与人工复核任务，不生成评级或违约概率"
          revision={`${workspace.as_of}-${workspace.summary.unconfirmed_signals}-${workspace.summary.history_points}`}
        />
      ) : null}

      <details
        className="credit-maintenance-details"
        open={maintenanceOpen}
        onToggle={(event) => setMaintenanceOpen(event.currentTarget.open)}
        ref={maintenanceRef}
      >
        <summary>
          <span><Upload size={15} /> 数据维护</span>
          <small>批量导入、新增或编辑单券；默认收起，避免遮挡日常观察</small>
        </summary>
        <div className="credit-maintenance-stack">
      <Panel title="批量导入与字段映射" eyebrow="CSV · EXCEL · PREVIEW FIRST">
        <div className="credit-import-toolbar">
          <label className="secondary-button">
            <Upload size={14} /> 选择 CSV / Excel
            <input className="visually-hidden" type="file" accept=".csv,.xlsx,.xlsm" onChange={chooseImport} />
          </label>
          <button className="text-button" onClick={() => apiDownload("/credit/import/template", "akdesk-credit-r2-template.csv")}><Download size={14} /> 下载标准模板</button>
          <small>先预览和调整映射，再确认导入；单次最多 500 行、10 MB。</small>
        </div>
        {importPreview ? (
          <div className="credit-import-preview">
            <header>
              <div><strong>{importPreview.filename}</strong><small>有效 {importPreview.valid_rows} · 错误 {importPreview.invalid_rows}</small></div>
              <div className="row-actions">
                <button className="secondary-button compact" disabled={!importFile || saving} onClick={() => importFile && previewImport(importFile, importMapping)}>按当前映射重检</button>
                <button className="primary-button compact" disabled={saving || Boolean(importPreview.errors.length) || !importPreview.valid_rows} onClick={commitImport}>{saving ? <LoaderCircle className="spin" size={14} /> : <Upload size={14} />} 确认导入</button>
                <button className="icon-button" aria-label="关闭导入预览" onClick={() => { setImportFile(null); setImportPreview(null); }}><X size={14} /></button>
              </div>
            </header>
            <div className="credit-mapping-grid">
              {importPreview.fields.map((field) => (
                <label key={field.field}>
                  <span>{field.label}{field.required ? " *" : ""}</span>
                  <select value={importMapping[field.field] || ""} onChange={(event) => setImportMapping((current) => ({ ...current, [field.field]: event.target.value }))}>
                    <option value="">不导入</option>
                    {importPreview.headers.map((header) => <option key={header} value={header}>{header}</option>)}
                  </select>
                </label>
              ))}
            </div>
            {importPreview.errors.length ? <div className="credit-import-errors">{importPreview.errors.map((item) => <p key={`${item.row}-${item.message}`}>第 {item.row} 行：{item.message}</p>)}</div> : null}
            <div className="credit-import-rows">
              {importPreview.preview_rows.map((row) => (
                <article className={row.eligible ? "eligible" : "blocked"} key={`${row.row}-${row.bond_code}`}>
                  <strong>{row.bond_name}</strong><span>{row.bond_code} · {row.issuer || "主体待补"}</span><small>{row.eligible ? "可计算机械利差" : row.quality_notes.join("；")}</small>
                </article>
              ))}
            </div>
            <p className="credit-r2-policy">{importPreview.notice}</p>
          </div>
        ) : null}
      </Panel>

      <Panel title={editingId ? "编辑单券观察" : "新增单券观察"} eyebrow="VERIFIED INPUT · HISTORY SNAPSHOT">
        <div className="credit-assist-bar">
          <label><span>从可信现券缓存带入候选</span><select defaultValue="" disabled={!candidates?.candidate_source.eligible} onChange={(event) => applyCandidate(event.target.value)}><option value="">{candidates?.candidate_source.eligible ? "选择代码与收益率" : "当前无可信候选"}</option>{candidates?.candidates.map((item) => <option value={item.bond_code} key={item.bond_code}>{item.bond_code} · {item.bond_name} · {formatNumber(item.yield_pct, 4)}%</option>)}</select></label>
          <div><span>本地国债曲线 · {candidates?.benchmark_curve.observation_date || "日期待确认"}</span><button className="secondary-button" type="button" onClick={applyBenchmark} disabled={!candidates?.benchmark_curve.eligible || candidates?.benchmark_curve.values[form.benchmark_tenor] === undefined}>带入 {form.benchmark_tenor} 基准</button></div>
          <small>{candidates ? `现券：${trustLabels[candidates.candidate_source.trust_level] || candidates.candidate_source.trust_level}（${candidates.candidate_source.quality_score} 分）；曲线：${trustLabels[candidates.benchmark_curve.trust_level] || candidates.benchmark_curve.trust_level}（${candidates.benchmark_curve.quality_score} 分）。` : "行情候选正在准备。"} 自动带入只覆盖行情字段，主体、评级、日期和来源仍须人工核验。</small>
        </div>
        <form className="credit-form credit-r2-form" onSubmit={save}>
          {primaryCreditFields.map(([field, label]) => (
            <label className={field === "source_note" ? "span-2" : undefined} key={field}>
              <span>{label}</span>
              <input disabled={Boolean(editingId) && ["bond_code", "bond_name"].includes(field)} required={["bond_code", "bond_name"].includes(field)} type={field.includes("date") ? "date" : field.includes("pct") ? "number" : "text"} step={field.includes("pct") ? "any" : undefined} value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
            </label>
          ))}
          <label><span>基准期限</span><select value={form.benchmark_tenor} onChange={(event) => setForm({ ...form, benchmark_tenor: event.target.value })}>{["1Y", "3Y", "5Y", "7Y", "10Y"].map((item) => <option key={item}>{item}</option>)}</select></label>
          <label><span>观察状态</span><select value={form.watch_status} onChange={(event) => setForm({ ...form, watch_status: event.target.value })}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <details className="credit-advanced-fields span-2">
            <summary>主体属性、回售与复盘设置（高级）</summary>
            <div>
              {advancedCreditFields.map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <input type={field.includes("date") ? "date" : "text"} value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
                </label>
              ))}
            </div>
          </details>
          <div className="row-actions span-2"><button className="primary-button" disabled={saving}>{saving ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />} {editingId ? "保存新快照" : "保存并校验"}</button>{editingId ? <button className="secondary-button" type="button" onClick={() => { setEditingId(null); setForm(emptyForm); }}><X size={14} /> 取消编辑</button> : null}</div>
        </form>
      </Panel>
        </div>
      </details>

      <div className="credit-workspace-toolbar" ref={toolbarRef}>
        <div className="segmented-control" role="tablist" aria-label="信用观察层级">
          <button ref={bondTabRef} id="credit-tab-bonds" role="tab" tabIndex={view === "bonds" ? 0 : -1} aria-selected={view === "bonds"} aria-controls="credit-panel-bonds" className={view === "bonds" ? "active" : ""} onClick={() => selectView("bonds")} onKeyDown={(event) => handleTabKeyDown(event, "bonds")}><ShieldCheck size={13} /> 单券</button>
          <button ref={issuerTabRef} id="credit-tab-issuers" role="tab" tabIndex={view === "issuers" ? 0 : -1} aria-selected={view === "issuers"} aria-controls="credit-panel-issuers" className={view === "issuers" ? "active" : ""} onClick={() => selectView("issuers")} onKeyDown={(event) => handleTabKeyDown(event, "issuers")}><Building2 size={13} /> 发行人</button>
          <button ref={portfolioTabRef} id="credit-tab-portfolios" role="tab" tabIndex={view === "portfolios" ? 0 : -1} aria-selected={view === "portfolios"} aria-controls="credit-panel-portfolios" className={view === "portfolios" ? "active" : ""} onClick={() => selectView("portfolios")} onKeyDown={(event) => handleTabKeyDown(event, "portfolios")}><Layers3 size={13} /> 自定义组合</button>
        </div>
        <label className="credit-search"><Search size={13} /><input aria-label="搜索信用观察" value={search} onChange={(event) => { setSearch(event.target.value); setVisibleBondCount(CREDIT_BOND_PAGE_SIZE); requestWorkspaceScrollReset(); }} placeholder="搜索代码、债券、主体或地区" /></label>
        {view === "bonds" ? <select aria-label="观察状态筛选" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setVisibleBondCount(CREDIT_BOND_PAGE_SIZE); requestWorkspaceScrollReset(); }}><option value="all">全部状态</option>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select> : null}
        <button className="secondary-button compact" onClick={() => apiDownload("/credit/export", "akdesk-credit-observations.csv")}><Download size={14} /> 导出当前观察</button>
        <button className="secondary-button compact" onClick={() => apiDownload("/credit/export?scope=history", "akdesk-credit-history.csv")}><History size={14} /> 导出多期历史</button>
      </div>

      {view === "bonds" ? (
        <div id="credit-panel-bonds" role="tabpanel" aria-labelledby="credit-tab-bonds" ref={activePanelRef}>
        <Panel title={`单券观察 · ${filteredItems.length}/${workspace?.total || 0}`} eyebrow="BOND · SPREAD HISTORY">
          <div className="credit-list credit-r2-list">
            {visibleItems.map((item) => (
              <article className={item.eligible ? "eligible" : "blocked"} key={item.id}>
                <header>
                  <div><strong>{item.bond_name}</strong><small>{item.bond_code} · {item.normalized_issuer || "主体待补"} · {statusLabels[item.watch_status]}</small></div>
                  <div><CreateProjectButton objectType="bond" objectId={item.bond_code} objectName={item.bond_name} templateId="credit_observation" source={item.source_note} observationTime={item.yield_observation_date} /><button className="icon-button" onClick={() => beginEdit(item)} aria-label={`编辑${item.bond_name}`}><Pencil size={14} /></button><button className="icon-button danger" onClick={() => remove(item.id, item.bond_name)} aria-label={`删除${item.bond_name}`}><Trash2 size={14} /></button></div>
                </header>
                <div className="credit-result credit-r2-result"><span>评级 {item.rating || "—"}</span><span>剩余期限 {formatNumber(item.remaining_years, 2)} 年</span><span>基准 {item.benchmark_tenor || "—"}</span><span>历史 {item.history_points || 0} 期</span><span>分位 {item.spread_percentile == null ? "—" : `${formatNumber(item.spread_percentile, 1)}%`}</span><span>较上期 {item.spread_change_bp == null ? "—" : `${item.spread_change_bp >= 0 ? "+" : ""}${formatNumber(item.spread_change_bp, 2)} BP`}</span><strong>{item.eligible ? `${formatNumber(item.spread_bp, 2)} BP` : "不计算"}</strong></div>
                {item.missing_fields.length || item.gate_reasons.length ? <p>{[...item.missing_fields.map((field) => `缺少 ${creditFieldLabels[field] || field}`), ...item.gate_reasons].join("；")}</p> : <p>{item.calculation_notice}</p>}
                {item.history?.length ? <details className="credit-history"><summary><History size={13} /> 查看历史与评级时间线</summary><div>{[...item.history].reverse().map((history) => <article key={history.history_id}><time>{history.yield_observation_date || history.recorded_at.slice(0, 10)}</time><span>{history.rating || "评级待补"}</span><span>{history.eligible ? `${formatNumber(history.spread_bp, 2)} BP` : "未通过门槛"}</span><small>{history.source_note || "来源待补"}</small></article>)}</div></details> : null}
              </article>
            ))}
          </div>
          {visibleItems.length ? <p className="credit-list-count" role="status">已显示 {visibleItems.length}/{filteredItems.length} 只单券</p> : null}
          {visibleItems.length < filteredItems.length ? (
            <div className="credit-list-pagination">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setVisibleBondCount((current) => nextCreditVisibleCount(current, filteredItems.length))}
              >
                再显示 {Math.min(CREDIT_BOND_PAGE_SIZE, filteredItems.length - visibleItems.length)} 只
              </button>
              <small>剩余 {filteredItems.length - visibleItems.length} 只；分段加载避免长列表拖慢滚动。</small>
            </div>
          ) : null}
          {!filteredItems.length ? <div className="empty-state"><ShieldCheck size={28} /><strong>没有符合条件的单券</strong><p>可手工新增，或先用 CSV / Excel 批量导入并检查字段映射。</p></div> : null}
        </Panel>
        </div>
      ) : null}

      {view === "issuers" ? (
        <div id="credit-panel-issuers" role="tabpanel" aria-labelledby="credit-tab-issuers" ref={activePanelRef}>
        <Panel title={`发行人主档 · ${filteredIssuers.length}`} eyebrow="ISSUER MASTER · NO AUTO RATING">
          <div className="credit-issuer-grid">
            {filteredIssuers.map((issuer) => (
              <article key={issuer.issuer}>
                <header>
                  <Building2 size={17} />
                  <div><strong>{issuer.issuer}</strong><small>{[issuer.issuer_type, issuer.sector, issuer.region].filter(Boolean).join(" · ") || "主体属性待补"}</small></div>
                  <div className="credit-issuer-actions">
                    <CreateProjectButton objectType="issuer" objectId={issuer.issuer} objectName={issuer.issuer} templateId="credit_observation" source="信用观察 R2 · 用户核验字段" observationTime={workspace?.as_of} question={`哪些可核验变化会改变对${issuer.issuer}的信用观察？`} onCreated={registerProject} />
                    <button className="icon-button" onClick={() => openIssuerEvents(issuer.issuer)} disabled={openingIssuer === issuer.issuer} aria-label={`打开${issuer.issuer}事件观察`}>
                      {openingIssuer === issuer.issuer ? <LoaderCircle className="spin" size={14} /> : <Newspaper size={14} />}
                    </button>
                  </div>
                </header>
                <dl><div><dt>观察债券</dt><dd>{issuer.bond_count}</dd></div><div><dt>通过门槛</dt><dd>{issuer.eligible_count}</dd></div><div><dt>评级记录</dt><dd>{issuer.ratings.join(" / ") || "—"}</dd></div><div><dt>可比单券利差范围</dt><dd>{formatSpreadRange(issuer.spread_range_bp)}</dd></div></dl>
                <p>{issuer.next_event ? `下一事件：${issuer.next_event.date} · ${issuer.next_event.title}` : "尚未设置未来到期、回售或复盘事件"}</p>
              </article>
            ))}
          </div>
          {!filteredIssuers.length ? <div className="empty-state"><Building2 size={28} /><strong>尚无发行人主档</strong><p>保存单券后会按人工确认的主体归一名自动聚合。</p></div> : null}
        </Panel>
        </div>
      ) : null}

      {view === "portfolios" ? (
        <div id="credit-panel-portfolios" role="tabpanel" aria-labelledby="credit-tab-portfolios" className="credit-portfolio-layout" ref={activePanelRef}>
          <Panel title={portfolioId ? "编辑信用组合" : "新建信用组合"} eyebrow="CUSTOM GROUP · LOCAL ONLY">
            <form className="credit-portfolio-form" onSubmit={savePortfolio}>
              <label><span>组合名称</span><input required value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} /></label>
              <label><span>用途说明</span><textarea value={portfolioDescription} onChange={(event) => setPortfolioDescription(event.target.value)} /></label>
              <div className="credit-portfolio-member-tools">
                <label className="credit-search"><Search size={13} /><input aria-label="筛选组合成员" value={portfolioMemberSearch} onChange={(event) => setPortfolioMemberSearch(event.target.value)} placeholder="筛选代码、债券或主体" /></label>
                <label className="credit-selected-only"><input type="checkbox" checked={portfolioSelectedOnly} onChange={(event) => setPortfolioSelectedOnly(event.target.checked)} /><span>仅看已选（{portfolioMembers.length}）</span></label>
              </div>
              <fieldset>
                <legend>选择单券 · 已选 {portfolioMembers.length} · 当前 {filteredPortfolioMembers.length}/{workspace?.items.length || 0}</legend>
                {filteredPortfolioMembers.map((item) => <label key={item.id}><input type="checkbox" checked={portfolioMembers.includes(item.id)} onChange={(event) => setPortfolioMembers((current) => toggleCreditMember(current, item.id, event.target.checked))} /><span>{item.bond_name}</span><small>{item.bond_code} · {item.normalized_issuer}</small></label>)}
                {!filteredPortfolioMembers.length ? <p className="credit-portfolio-empty">没有符合条件的单券。</p> : null}
              </fieldset>
              <div className="credit-portfolio-actions row-actions"><button className="primary-button" disabled={saving || !portfolioName.trim()}><Layers3 size={14} /> {portfolioId ? "保存组合" : "创建组合"}</button>{portfolioId ? <button type="button" className="secondary-button" onClick={resetPortfolio}>取消编辑</button> : null}</div>
            </form>
          </Panel>
          <Panel title={`组合观察 · ${workspace?.portfolios.length || 0}`} eyebrow="PORTFOLIO VIEW">
            <div className="credit-portfolio-list">{workspace?.portfolios.map((portfolio) => <article key={portfolio.id}><header><div><strong>{portfolio.name}</strong><small>{portfolio.description || "无说明"}</small></div><div><button className="icon-button" onClick={() => editPortfolio(portfolio)} aria-label={`编辑${portfolio.name}`}><Pencil size={14} /></button><button className="icon-button danger" onClick={() => deletePortfolio(portfolio)} aria-label={`删除${portfolio.name}`}><Trash2 size={14} /></button></div></header><div><span>{portfolio.members.length} 只债券</span><span>{portfolio.issuer_count} 个主体</span><span>{portfolio.eligible_count} 只通过门槛</span><strong>{formatSpreadRange(portfolio.spread_range_bp)}</strong></div><p>{portfolio.members.map((item) => item.bond_name).join(" · ") || "尚未添加单券"}</p></article>)}</div>
            {!workspace?.portfolios.length ? <div className="empty-state"><Layers3 size={28} /><strong>尚无自定义组合</strong><p>组合只用于本地观察聚合，不计算仓位、收益或自动评级。</p></div> : null}
          </Panel>
        </div>
      ) : null}

      {workspace ? (
        <Panel title={`风险与日程信号 · ${workspace.signals.length}`} eyebrow="TRACEABLE · MANUAL CONFIRM">
          <p className="credit-r2-policy">{workspace.r2_policy}</p>
          <div className="credit-signal-list">
            {workspace.signals.slice(0, 12).map((signal) => (
              <article className={`${signal.level} ${signal.confirmation ? "confirmed" : ""}`} key={signal.id}>
                <ShieldAlert size={16} />
                <div>
                  <strong>{signal.title}</strong>
                  <p>{signal.detail}</p>
                  <small>{signal.source_note || "来源待补"} · {signal.observation_date || "观察日期待补"}</small>
                  {signal.confirmation?.note ? <small className="signal-confirmed-note">确认备注：{signal.confirmation.note}</small> : null}
                  {signalComposerId === signal.id ? (
                    <div className="credit-signal-review">
                      <label><span>确认备注</span><textarea value={signalNote} onChange={(event) => setSignalNote(event.target.value)} placeholder="记录核验动作、依据或后续待办" maxLength={1000} /></label>
                      <label><span>同步到研究项目（可选）</span><select value={signalProjectId} onChange={(event) => setSignalProjectId(event.target.value)}><option value="">仅确认信号</option>{projects.filter((project) => project.status !== "archived").map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label>
                      <div className="row-actions"><button className="primary-button compact" disabled={saving} onClick={() => confirmSignal(signal.id)}>确认并保存</button><button className="text-button" onClick={() => { setSignalComposerId(null); setSignalNote(""); setSignalProjectId(""); }}>取消</button></div>
                    </div>
                  ) : null}
                </div>
                {signal.confirmation ? (
                  <span className="signal-confirmed"><CheckCircle2 size={13} /> 已确认</span>
                ) : (
                  <button className="secondary-button compact" aria-label={`人工确认：${signal.title}`} onClick={() => { setSignalComposerId(signal.id); setSignalNote(""); setSignalProjectId(""); }}>人工确认</button>
                )}
              </article>
            ))}
            {!workspace.signals.length ? <div className="empty-state compact"><ShieldCheck size={24} /><strong>当前没有规则信号</strong><p>没有信号不代表没有信用风险，仍需按原始资料复核。</p></div> : null}
          </div>
        </Panel>
      ) : null}

      <Panel title={`信用事件日历 · ${workspace?.calendar.length || 0}`} eyebrow="MATURITY · PUT · RATING · REVIEW">
        <div className="credit-calendar-grid">
          {workspace?.calendar.slice(0, 36).map((event, index) => <article className={event.overdue ? "overdue" : ""} key={`${event.kind}-${event.bond_code}-${event.date}-${index}`}><CalendarDays size={15} /><time>{event.date}</time><div><strong>{event.title}</strong><small>{eventLabels[event.kind]} · {event.issuer}</small></div>{event.overdue ? <span>已到期/逾期</span> : null}</article>)}
        </div>
        {!workspace?.calendar.length ? <div className="empty-state compact"><CalendarDays size={24} /><strong>尚无信用日程</strong><p>补充到期日、回售日、评级日期或复盘日后会自动汇总。</p></div> : null}
      </Panel>

      {workspace?.total ? <details className="credit-coverage-details"><summary>查看字段覆盖率与严格计算门禁</summary><div className="credit-coverage-grid">{Object.entries(workspace.field_coverage).map(([field, item]) => <article key={field}><span>{creditFieldLabels[field] || field}</span><strong>{item.covered}/{item.total}</strong><small>{formatNumber(item.ratio * 100, 1)}%</small></article>)}</div><p className="warning-banner">{workspace.policy}</p></details> : null}
    </div>
  );
}
