import { useEffect, useId, useRef, useState } from "react";
import { CheckCheck, ClipboardCheck, RefreshCcw } from "lucide-react";
import { ApiError, apiGet, apiPost } from "../api";
import { formatDateTime } from "./UI";
import "./projectReviewDelta.css";

export interface ProjectReviewDeltaResult {
  project_id: number;
  fingerprint: string;
  baseline: { reviewed_at: string; entry_id: number } | null;
  counts: {
    new_entries: number;
    updated_entries: number;
    removed_entries: number;
    new_evidence: number;
    updated_evidence: number;
    removed_evidence: number;
    open_tasks: number;
    needs_verification: number;
    project_changed: boolean;
  };
  changes: {
    project_changed: boolean;
    entries: Array<{ id: number; title: string; entry_type: string; status: string; change: "new" | "updated" }>;
    evidence: Array<{ id: number; title: string; evidence_type: string; change: "new" | "updated" }>;
    removed_entry_ids: number[];
    removed_evidence_ids: number[];
  };
  evidence_status: Array<{
    id: number;
    title: string;
    evidence_type: string;
    status: "reference_only" | "missing_time" | "expired" | "snapshot" | "manual_note" | "needs_verification";
    reason: string;
    observation_date: string | null;
    created_at: string;
  }>;
  open_tasks: Array<{ id: number; title: string; due_date: string | null; overdue: boolean }>;
  truncated: { entries: boolean; evidence: boolean; tasks: boolean; removed_entries: boolean; removed_evidence: boolean };
  notice: string;
}

const statusLabels: Record<ProjectReviewDeltaResult["evidence_status"][number]["status"], string> = {
  reference_only: "查询引用 · 非历史数据快照",
  missing_time: "观测日期缺失 · 待核验",
  expired: "超出快照观察窗口 · 待核验",
  snapshot: "近期本地快照 · 仍需核验",
  manual_note: "人工记录 · 不判断数据时效",
  needs_verification: "资料边界待核验",
};

const entryLabels: Record<string, string> = { note: "笔记", counter_evidence: "反证", task: "任务", review: "复盘" };

export function ProjectReviewDelta({
  projectId,
  projectTitle,
  revision,
  onReviewed,
}: {
  projectId: number;
  projectTitle: string;
  revision: string;
  onReviewed: () => void;
}) {
  const [result, setResult] = useState<ProjectReviewDeltaResult | null>(null);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [readError, setReadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [preview, setPreview] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<{ projectId: number; text: string } | null>(null);
  const epoch = useRef(0);
  const inFlight = useRef(false);
  const headingId = useId();
  const noteId = useId();

  useEffect(() => { setNote(""); setMessage(null); }, [projectId]);

  useEffect(() => {
    let active = true;
    const requestEpoch = ++epoch.current;
    const controller = new AbortController();
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15_000);
    setLoading(true);
    setResult(null);
    setReadError("");
    setSaveError("");
    setConflict(false);
    setPreview(false);
    setConfirmed(false);
    setSaving(false);
    inFlight.current = false;
    apiGet<ProjectReviewDeltaResult>(`/research/projects/${projectId}/review-delta`, { signal: controller.signal })
      .then(value => {
        if (!active || epoch.current !== requestEpoch) return;
        if (value.project_id !== projectId || !value.fingerprint) throw new Error("复盘资料与当前项目不一致，请重新读取。");
        setResult(value);
      })
      .catch((reason: unknown) => {
        if (active && epoch.current === requestEpoch) setReadError(timedOut ? "复盘变化读取超时，请确认本地服务并重新读取" : reason instanceof Error ? reason.message : "复盘变化读取失败");
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active && epoch.current === requestEpoch) setLoading(false);
      });
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); ++epoch.current; };
  }, [projectId, revision, reload]);

  const current = result?.project_id === projectId && !loading ? result : null;
  const omitted = current && Object.values(current.truncated).some(Boolean);

  async function markReviewed() {
    if (!current || !confirmed || !preview || conflict || saving || inFlight.current) return;
    const targetProject = projectId;
    const operationEpoch = epoch.current;
    inFlight.current = true;
    setSaving(true);
    setSaveError("");
    try {
      const value = await apiPost<ProjectReviewDeltaResult>(`/research/projects/${targetProject}/review-checkpoint`, {
        confirmed: true,
        expected_fingerprint: current.fingerprint,
        note: note.trim(),
      }, { timeoutMs: 15_000, timeoutMessage: "复盘保存响应超时，请核对连接后重试；服务会核对同一基线，避免重复记录。" });
      if (epoch.current !== operationEpoch) return;
      if (value.project_id !== targetProject || !value.fingerprint) throw new Error("服务已响应，但项目资料不匹配。请重新读取，不要将状态当成已确认。");
      setResult(value);
      setPreview(false);
      setConfirmed(false);
      setNote("");
      setMessage({ projectId: targetProject, text: "本次复盘时点已记录。未完成任务和待核验状态仍保留，不代表数据已经验证。" });
      try { onReviewed(); }
      catch { setMessage({ projectId: targetProject, text: "本次复盘已记录，但项目视图未能刷新。请重新打开项目核对，不必再次提交。" }); }
    } catch (reason) {
      if (epoch.current !== operationEpoch) return;
      if (reason instanceof ApiError && reason.status === 409) {
        setConflict(true);
        setConfirmed(false);
        setSaveError("项目在预览后发生了变化，本次没有覆盖新的资料。请重新读取变更，再核对确认；你的复盘备注仍保留。");
      } else {
        setSaveError(reason instanceof Error ? reason.message : "复盘时点未能确认，请重试。若响应丢失，重试会由服务核对，避免重复记录。");
      }
    } finally {
      if (epoch.current === operationEpoch) { inFlight.current = false; setSaving(false); }
    }
  }

  return <section className="project-review-delta panel" aria-labelledby={headingId}>
    <header className="panel-header"><div><span className="eyebrow">REVIEW · SINCE YOUR LAST CHECKPOINT</span><h2 id={headingId}>这次复盘，先看什么变化</h2></div><button type="button" className="secondary-button" disabled={loading || saving} onClick={() => setReload(value => value + 1)}><RefreshCcw size={14} />重新读取</button></header>
    <div className="panel-body">
      <p className="project-review-target">当前项目：<strong>{projectTitle}</strong> · #{projectId}。只比较已保存的本地资料，表单未保存编辑不计入本次基线。不请求 FRED、行情或 AI；标记复盘须再次确认。</p>
      {loading ? <p role="status">正在整理本项目的复盘变化…</p> : null}
      {readError ? <p className="form-error" role="alert">{readError}。可点击“重新读取”重试；读取操作不会写入复盘标记。</p> : null}
      {message?.projectId === projectId ? <p className="project-review-message" role="status">{message.text}</p> : null}
      {current ? <>
        <p className="project-review-baseline">{current.baseline ? <>上次明确复盘：<time title={current.baseline.reviewed_at}>{formatDateTime(current.baseline.reviewed_at)}</time>。下列变化与该基线比较，不是与上次打开页面比较。</> : <>首次复盘：尚无明确基线。下列为当前已有资料，不把全部存量称为“刚新增”。</>}</p>
        <div className="project-review-counts">
          <ReviewCount label={current.baseline ? "新增记录" : "当前记录"} count={current.counts.new_entries} />
          <ReviewCount label="已修改记录" count={current.counts.updated_entries} />
          <ReviewCount label={current.baseline ? "新增证据" : "当前证据"} count={current.counts.new_evidence} />
          <ReviewCount label="已修改证据" count={current.counts.updated_evidence} />
          <ReviewCount label="证据待核验" count={current.counts.needs_verification} />
          <ReviewCount label="未完成任务" count={current.counts.open_tasks} />
        </div>
        {current.baseline ? <p className="project-review-change-note">项目字段{current.counts.project_changed ? "有变化，请核对当前问题、假设与结论" : "未检测到变化"}；移除记录 {current.counts.removed_entries} 项、移除证据 {current.counts.removed_evidence} 项。移除不等于原资料已被证伪。</p> : null}
        {omitted ? <p className="project-review-warning" role="note">为控制页面体积，本面板每类最多显示 100 项，计数包含全部资料。标记前请在项目的完整记录、证据与任务中核对未显示部分。</p> : null}
        <div className="project-review-sections">
          <details open><summary>记录与证据变化</summary><div className="project-review-scroll">
            {current.changes.entries.length || current.changes.evidence.length ? <ul>{current.changes.entries.map(item => <li key={`entry-${item.id}`}><span>{!current.baseline && item.change === "new" ? "首次纳入" : item.change === "new" ? "新增" : "修改"} · {entryLabels[item.entry_type] ?? "记录"}</span><strong>{item.title}</strong></li>)}{current.changes.evidence.map(item => <li key={`evidence-${item.id}`}><span>{!current.baseline && item.change === "new" ? "首次纳入" : item.change === "new" ? "新增" : "修改"} · 证据</span><strong>{item.title}</strong></li>)}</ul> : <p>没有检测到记录或证据的新增/修改。仍需核对下方时效、缺失和未完成任务。</p>}
          </div></details>
          <details open><summary>证据状态与可信边界</summary><p className="project-review-small">近期快照只是机械时间窗口，不代表实时、正确或已获授权；查询引用不代表保存了官方历史版本。</p><div className="project-review-scroll">{current.evidence_status.length ? <ul>{current.evidence_status.map(item => <li key={item.id} className={`project-evidence-status ${item.status}`}><strong>{item.title}</strong><span className="project-evidence-status-label">{statusLabels[item.status] ?? "资料待核验"}</span><p>{item.reason}</p><small>观测日期 {item.observation_date ?? "未提供，不推定为新鲜"} · 保存于 {formatDateTime(item.created_at)}</small></li>)}</ul> : <p>尚无研究证据；没有证据不表示研究已经得到验证。</p>}</div></details>
          <details open><summary>未完成验证任务</summary><div className="project-review-scroll">{current.open_tasks.length ? <ul>{current.open_tasks.map(item => <li key={item.id}><strong>{item.title}</strong><span>{item.due_date ? `${item.due_date}${item.overdue ? " · 已到期，待处理" : " · 尚未完成"}` : "尚未设置到期日"}</span></li>)}</ul> : <p>当前没有未完成任务；请自行判断是否需要补充反证或下一次验证。</p>}</div></details>
        </div>
        <p className="project-review-small">{current.notice}</p>
        <div className="project-review-explicit-write">
          <button type="button" className="secondary-button" disabled={loading || saving} onClick={() => { setPreview(value => !value); setConfirmed(false); setSaveError(""); }}><ClipboardCheck size={15} />{preview ? "收起确认" : "准备标记本次已复盘"}</button>
          {preview ? <div className="project-review-confirmation">
            <p>确认目标：<strong>{projectTitle}</strong>（#{projectId}）。此操作只保存本地复盘记录与比较基线，不改变结论、证据可信度、任务完成状态或下次复盘日期。</p>
            <label htmlFor={noteId}>自己的复盘备注（可选，不粘贴 FRED 响应或受限内容）</label><textarea id={noteId} value={note} disabled={saving} maxLength={2000} rows={3} onChange={event => setNote(event.target.value)} />
            <label className="project-review-checkbox"><input type="checkbox" checked={confirmed} disabled={saving || conflict} onChange={event => setConfirmed(event.target.checked)} /><span>我已核对本项目的变更、证据边界与未完成任务；有省略时已查看完整项目，只记录复盘时点。</span></label>
            <button type="button" className="primary-button" disabled={!confirmed || saving || loading || conflict} onClick={markReviewed}><CheckCheck size={15} />{saving ? "正在记录…" : "确认记录本次复盘"}</button>
          </div> : null}
          {saveError ? <p className="form-error" role="alert">{saveError}</p> : null}
        </div>
      </> : null}
    </div>
  </section>;
}

function ReviewCount({ label, count }: { label: string; count: number }) {
  return <div><span>{label}</span><strong>{count}</strong></div>;
}
