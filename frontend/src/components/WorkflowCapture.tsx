import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, CheckCircle2, FilePlus2, LoaderCircle, X } from "lucide-react";
import { ApiError, apiGet, apiPost } from "../api";
import { trapFocus } from "../focus";
import { shanghaiDate } from "../researchUtils";
import type { MarketResearchSignal, ResearchProject } from "../types";
import "./workflowCapture.css";

export type WorkflowCaptureSource =
  | { kind: "market_signal"; signal: MarketResearchSignal }
  | { kind: "asset_reference"; asset: { id: string; name: string } }
  | { kind: "brief_note"; reportDate: string; note: string };

interface CaptureBody {
  kind: WorkflowCaptureSource["kind"];
  request_id: string;
  confirmed: true;
  note: string;
  signal_id?: string;
  expected_fetched_at?: string;
  report_date?: string;
  asset_id?: string;
}

interface CaptureResult {
  project_id: number;
  entry_id: number;
  evidence_id: number | null;
  deduplicated: boolean;
}

interface Preview {
  projectId: number;
  projectTitle: string;
  signature: string;
  body: CaptureBody;
}

function recentObservation(value: string | null | undefined): boolean {
  if (!value) return false;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const stamp = new Date(dateOnly ? `${value}T00:00:00Z` : /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}+08:00`);
  if (!Number.isFinite(stamp.getTime())) return false;
  const observed = dateOnly ? stamp.toISOString().slice(0, 10) : shanghaiDate(stamp);
  if (dateOnly && observed !== value) return false;
  const days = (Date.parse(`${shanghaiDate()}T00:00:00Z`) - Date.parse(`${observed}T00:00:00Z`)) / 86_400_000;
  return days >= 0 && days <= 7;
}

function fredSource(signal: MarketResearchSignal): boolean {
  function isFredUrl(value: string): boolean {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase().replace(/\.$/, "");
      return ["http:", "https:"].includes(url.protocol) && (host === "stlouisfed.org" || host.endsWith(".stlouisfed.org"));
    } catch { return false; }
  }
  return [signal.source, signal.adapter].some(value => {
    const urls = value.match(/https?:\/\/[^\s<>]+/gi) ?? [];
    const label = value.replace(/https?:\/\/[^\s<>]+/gi, "").trim();
    return urls.some(isFredUrl) || /(?:^|[^A-Za-z0-9_])fred(?:$|[^A-Za-z0-9_])/i.test(label)
      || /^fred_(?:macro|chart|reference|series|release|release_review|api)$/i.test(label);
  }) || isFredUrl(signal.source_url ?? "");
}

function eligible(source: WorkflowCaptureSource): boolean {
  if (source.kind === "asset_reference") return Boolean(source.asset.id);
  if (source.kind === "brief_note") return Boolean(source.note.trim()) && source.note.trim().length <= 8000;
  const signal = source.signal;
  return signal.actionable && signal.trust_level === "trusted" && signal.demo === false
    && ["live", "latest", "cached"].includes(signal.data_state)
    && recentObservation(signal.observation_time) && Boolean(signal.fetched_at) && !fredSource(signal)
    && signal.value !== null && Number.isFinite(signal.value);
}

/** No drafts are persisted in browser storage or included in a URL. */
export function WorkflowCapture({ source, navigate }: {
  source: WorkflowCaptureSource;
  navigate?: (page: string, query?: string) => void;
}) {
  const key = source.kind === "market_signal" ? `market:${source.signal.id}` : source.kind === "asset_reference" ? `asset:${source.asset.id}` : `brief:${source.reportDate}`;
  return <CaptureSession key={key} source={source} navigate={navigate} />;
}

function CaptureSession({ source, navigate }: {
  source: WorkflowCaptureSource;
  navigate?: (page: string, query?: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saved, setSaved] = useState<{ result: CaptureResult; projectTitle: string } | null>(null);
  const [uncertainProject, setUncertainProject] = useState<number | null>(null);
  const [needsRecheck, setNeedsRecheck] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const identity = useRef<{ signature: string; requestId: string } | null>(null);
  const headingId = useId();
  const canCapture = eligible(source);
  const text = source.kind === "brief_note" ? source.note.trim() : note.trim();
  const signature = JSON.stringify({ source, projectId, note: text });
  const latestSignature = useRef(signature);
  const selectedProject = projects.find(project => String(project.id) === projectId);

  useLayoutEffect(() => { latestSignature.current = signature; }, [signature]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    setPreview(null);
    setSaved(null);
    identity.current = null;
    setError("");
    setNeedsRecheck(false);
  }, [signature]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = window.setTimeout(() => {
      if (!active) return;
      active = false;
      controller.abort();
      setProjects([]);
      setLoading(false);
      setError("项目列表读取超时，请确认本地服务可用后重新读取；尚未提交任何内容。");
    }, 15_000);
    apiGet<ResearchProject[]>("/research/projects", { signal: controller.signal })
      .then(items => { if (active) setProjects(items.filter(item => item.status !== "archived")); })
      .catch(reason => {
        if (active && !(reason instanceof Error && reason.name === "AbortError")) {
          setProjects([]);
          setError(reason instanceof Error ? reason.message : "项目列表暂时不可用，请重试。");
        }
      })
      .finally(() => { window.clearTimeout(timer); if (active) setLoading(false); });
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [open, retry]);

  useEffect(() => {
    if (open) dialogRef.current?.querySelector<HTMLElement>("button, select")?.focus();
  }, [open]);

  function close() {
    if (inFlight.current) return;
    setOpen(false);
    buttonRef.current?.focus();
  }

  function prepare() {
    if (!selectedProject || !canCapture || busy || loading || needsRecheck) return;
    setError("");
    setUncertainProject(null);
    if (!identity.current || identity.current.signature !== signature) {
      if (typeof crypto.randomUUID !== "function") {
        setError("当前浏览器不支持安全的请求标识，请使用新版浏览器；尚未提交任何内容。");
        return;
      }
      identity.current = { signature, requestId: crypto.randomUUID() };
    }
    const body: CaptureBody = {
      kind: source.kind, request_id: identity.current.requestId, confirmed: true, note: text,
      ...(source.kind === "market_signal"
        ? { signal_id: source.signal.id, expected_fetched_at: source.signal.fetched_at }
        : source.kind === "asset_reference" ? { asset_id: source.asset.id } : { report_date: source.reportDate }),
    };
    setPreview({ projectId: selectedProject.id, projectTitle: selectedProject.title, signature, body });
  }

  async function confirm() {
    if (!preview || inFlight.current || loading || !canCapture || !selectedProject || needsRecheck || preview.signature !== signature) return;
    const submitting = preview;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await apiPost<CaptureResult>(`/research/projects/${submitting.projectId}/workflow-capture`, submitting.body, {
        timeoutMs: 20_000,
        timeoutMessage: "保存响应超时，结果尚未确认。请保留同一预览重试以按请求去重，或先到原项目核对。",
      });
      if (!mounted.current) return;
      if (latestSignature.current !== submitting.signature) {
        setUncertainProject(submitting.projectId);
        setError("页面内容已变化，之前的请求可能已保存到原项目。请先核对，不把旧结果当作当前草稿已保存。");
        return;
      }
      if (result.project_id !== submitting.projectId || !Number.isInteger(result.entry_id) || result.entry_id <= 0) {
        throw new Error("保存结果暂时无法确认。请保留同一预览重试或先核对原项目。");
      }
      setSaved({ result, projectTitle: submitting.projectTitle });
    } catch (reason) {
      if (!mounted.current) return;
      if (latestSignature.current !== submitting.signature) {
        setUncertainProject(submitting.projectId);
        setError("页面内容已变化，之前请求的结果未确认，请先到原项目核对后再保存新内容。");
      } else if (reason instanceof ApiError && reason.status === 409) {
        setNeedsRecheck(true);
        setError(`${reason.message} 请先刷新来源、核对项目后重新预览；不要直接覆盖旧信息。`);
      } else {
        if (!(reason instanceof ApiError) || reason.status === 0) setUncertainProject(submitting.projectId);
        setError(reason instanceof Error ? reason.message : "保存失败；请保留同一预览重试以按请求去重。");
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  const title = source.kind === "market_signal" ? "关联研究项目" : source.kind === "asset_reference" ? "保存查询引用到项目" : "将人工备注保存为研究笔记";
  const entryTitle = Array.from(source.kind === "market_signal" ? `市场变化 · ${source.signal.title}` : source.kind === "asset_reference" ? `跨资产查询 · ${source.asset.name}` : `简报备注 · ${source.reportDate}`).slice(0, 160).join("");
  return <>
    <button ref={buttonRef} className="workflow-capture-trigger" type="button" disabled={!canCapture} onClick={() => setOpen(true)} title={!canCapture ? (source.kind === "market_signal" ? "仅可信、可行动、非演示且观测日为近7天的非FRED信号可关联；请先回原模块核验。" : "先在简报中填写自己的备注；不自动复制报告数据。") : undefined}><FilePlus2 size={14} />{title}</button>
    {open ? createPortal(<div className="workflow-capture-overlay" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
      <section ref={dialogRef} className="workflow-capture-dialog" role="dialog" aria-modal="true" aria-labelledby={headingId} tabIndex={-1} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && ["r", "1", "k"].includes(event.key.toLowerCase())) { event.preventDefault(); event.stopPropagation(); return; } trapFocus(event, dialogRef.current); if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
        <header><div><span className="eyebrow">PREVIEW · CONFIRM · SAVE</span><h2 id={headingId}>{title}</h2></div><button type="button" className="icon-button" aria-label="关闭保存预览" disabled={busy} onClick={close}><X size={18} /></button></header>
        <p className="workflow-capture-boundary">只写入所选项目；不会自动创建项目、评级或投资结论。{source.kind === "market_signal" ? "服务端重新核对当前一条信号及抓取时点，不接受浏览器提交的行情数值。" : source.kind === "asset_reference" ? "只保存资产查询标识、来源链接与自己的备注，不保存行情数值或观测日期，不向AI发送该引用。" : "仅保存你手工填写的备注与报告日期引用，不复制简报正文、行情或 FRED 响应。"}请先核验数据使用权限；手工内容也不要包含密钥、受限原文或 FRED API 内容。</p>
        {!canCapture ? <p role="alert">当前内容已变化或不满足保存条件，请先核验来源/备注后重新预览。</p> : null}
        {loading ? <p role="status"><LoaderCircle size={14} className="spin" />正在读取可选项目…</p> : null}
        <fieldset disabled={busy || loading || !canCapture}>
          <label>目标研究项目<select value={projectId} disabled={busy || loading || !canCapture} onChange={event => setProjectId(event.target.value)}><option value="">请选择已有项目</option>{projects.map(project => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label>
          {!loading && !projects.length ? <div className="workflow-capture-empty"><p>暂无可选项目，或读取失败。先建立项目，再返回保存；不会自动立项。</p><button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>重新读取项目</button>{navigate ? <button type="button" className="text-button" onClick={() => { close(); navigate("projects"); }}>打开研究项目 <ArrowRight size={13} /></button> : null}</div> : null}
          {source.kind !== "brief_note" ? <label>本次研究备注（可选）<textarea value={note} disabled={busy || loading || !canCapture} maxLength={8000} rows={3} onChange={event => setNote(event.target.value)} placeholder="只记录自己的判断、分歧或下一步核验，不要粘贴受限内容。" /></label> : null}
          {!saved ? <button type="button" className="secondary-button" onClick={prepare} disabled={!selectedProject || !canCapture || loading || busy || needsRecheck}>预览保存内容</button> : null}
        </fieldset>
        {preview && preview.signature === signature ? <div className="workflow-capture-preview" aria-label="即将保存的内容">
          <h3>即将保存到：{preview.projectTitle}</h3>
          <dl>
            <div><dt>研究记录标题</dt><dd>{entryTitle}</dd></div>
            {source.kind === "market_signal" ? <>
              <div><dt>当前信号（服务端保存前再次校验）</dt><dd>{source.signal.summary}</dd></div>
              <div><dt>数值和状态</dt><dd>{source.signal.value} {source.signal.unit} · {source.signal.data_state} · 质量 {source.signal.quality_score}</dd></div>
              <div><dt>来源</dt><dd>{source.signal.source}</dd></div>
              <div><dt>观测 / 抓取</dt><dd>{source.signal.observation_time} / {source.signal.fetched_at}</dd></div>
            </> : source.kind === "asset_reference" ? <div><dt>资产查询引用（无行情数值）</dt><dd>{source.asset.id} · {source.asset.name}</dd></div> : <div><dt>报告日期（仅引用）</dt><dd>{source.reportDate}</dd></div>}
          </dl>
          <h4>人工备注正文</h4><pre>{preview.body.note || (source.kind === "asset_reference" ? "（未填写；仅保存查询引用，不是价格证据）" : "（未填写；仅保存当前一条信号的来源快照）")}</pre>
          <p>这不是全市场或完整简报快照。网络中断后可保留同一预览重试；变更项目或内容需重新预览，并先核对原项目是否已保存。</p>
          {saved ? <div className="workflow-capture-success" role="status"><CheckCircle2 size={16} /><span>已保存到「{saved.projectTitle}」{saved.result.deduplicated ? "（重试已去重）" : ""}。原简报备注仍保留，不自动清空。</span></div> : <button className="primary-button" type="button" disabled={busy || loading || !canCapture || !selectedProject || needsRecheck} onClick={confirm}>{busy ? <LoaderCircle size={14} className="spin" /> : <FilePlus2 size={14} />}{busy ? "正在保存，请稍候" : "确认保存到该项目"}</button>}
          {saved && navigate ? <button className="text-button" type="button" onClick={() => { close(); navigate("projects", String(saved.result.project_id)); }}>打开已保存的研究项目 <ArrowRight size={13} /></button> : null}
        </div> : null}
        {error ? <p className="workflow-capture-error" role="alert">{error}</p> : null}
        {preview && preview.signature === signature && source.kind === "market_signal" ? <details className="workflow-capture-source-fields"><summary>核对当前一条信号的完整字段</summary><pre>{JSON.stringify(source.signal, null, 2)}</pre><p>仅此条来源字段；服务端保存前会再次校验，时点变化会拒绝旧预览。不是整个市场或宏观响应的副本。</p></details> : null}
        {uncertainProject && navigate ? <button className="text-button" type="button" disabled={busy} onClick={() => { close(); navigate("projects", String(uncertainProject)); }}>核对上次提交的原项目 <ArrowRight size={13} /></button> : null}
      </section>
    </div>, document.body) : null}
  </>;
}
