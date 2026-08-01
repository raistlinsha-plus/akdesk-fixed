import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  ChartNoAxesCombined,
  CirclePlus,
  DatabaseBackup,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  Globe2,
  History,
  ListTodo,
  LoaderCircle,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { apiDelete, apiDownload, apiGet, apiPatch, apiPost, apiPostFile } from "../api";
import { AiInsightCard } from "../components/AiInsightCard";
import { ResearchActionPanel } from "../components/ResearchActionPanel";
import { ErrorState, LoadingState, Panel, formatDateTime } from "../components/UI";
import type {
  ResearchEntryType,
  ResearchEvidence,
  ResearchProject,
  ResearchStatus,
  ResearchTemplate,
} from "../types";
import { parseResearchTags } from "../researchUtils";
import { activityDetailLines } from "../researchActivity";
import { projectProgress } from "../researchWorkflow";
import { PageHeading } from "./MarketPages";

const statusLabels: Record<ResearchStatus, string> = {
  draft: "草稿",
  tracking: "跟踪中",
  formed: "已形成观点",
  review: "待复盘",
  archived: "已归档",
};

const entryTypeLabels: Record<ResearchEntryType, string> = {
  note: "研究笔记",
  counter_evidence: "反证",
  task: "任务",
  review: "复盘",
};

interface ProjectDraft {
  title: string;
  question: string;
  hypothesis: string;
  status: ResearchStatus;
  confidence: number;
  horizon: string;
  tags: string;
  next_review_date: string;
  conclusion: string;
}

interface BackupStatus {
  enabled: boolean;
  running: boolean;
  retention: number;
  latest: { name: string; size_bytes: number; created_at: string } | null;
  next_due_at: string | null;
  last_error: string | null;
}

function projectDraft(project: ResearchProject): ProjectDraft {
  return {
    title: project.title,
    question: project.question,
    hypothesis: project.hypothesis,
    status: project.status,
    confidence: project.confidence,
    horizon: project.horizon,
    tags: project.tags.join("，"),
    next_review_date: project.next_review_date || "",
    conclusion: project.conclusion,
  };
}

function evidenceSeries(item: ResearchEvidence): Array<Record<string, unknown>> {
  return Array.isArray(item.payload.series)
    ? item.payload.series.filter((value): value is Record<string, unknown> => Boolean(value && typeof value === "object"))
    : [];
}

function marketEvidenceSignals(item: ResearchEvidence): Array<Record<string, unknown>> {
  return Array.isArray(item.payload.signals)
    ? item.payload.signals.filter((value): value is Record<string, unknown> => Boolean(value && typeof value === "object"))
    : [];
}

export function ProjectsPage({
  initialQuery,
  navigate,
}: {
  initialQuery?: string;
  navigate: (page: string, query?: string) => void;
}) {
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(
    initialQuery && Number.isFinite(Number(initialQuery)) ? Number(initialQuery) : null,
  );
  const [selected, setSelected] = useState<ResearchProject | null>(null);
  const [draft, setDraft] = useState<ProjectDraft | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newQuestion, setNewQuestion] = useState("");
  const [templates, setTemplates] = useState<ResearchTemplate[]>([]);
  const [templateId, setTemplateId] = useState<ResearchTemplate["id"]>("rates_direction");
  const [newEntry, setNewEntry] = useState<{ entry_type: ResearchEntryType; title: string; content: string; due_date: string }>({
    entry_type: "note",
    title: "",
    content: "",
    due_date: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [expandedEvidenceId, setExpandedEvidenceId] = useState<number | null>(null);
  const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null);
  const projectImportRef = useRef<HTMLInputElement>(null);
  const backupRestoreRef = useRef<HTMLInputElement>(null);

  function loadProjects(preferredId?: number) {
    setLoading(true);
    apiGet<ResearchProject[]>("/research/projects")
      .then((items) => {
        setProjects(items);
        const nextId = preferredId ?? selectedId ?? items[0]?.id ?? null;
        setSelectedId(nextId);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "研究项目加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadProjects();
    apiGet<ResearchTemplate[]>("/research/templates")
      .then(setTemplates)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "研究模板加载失败"));
    apiGet<BackupStatus>("/research/backups")
      .then(setBackupStatus)
      .catch(() => setBackupStatus(null));
  }, []);

  useEffect(() => {
    const nextId = Number(initialQuery);
    if (initialQuery && Number.isFinite(nextId)) setSelectedId(nextId);
  }, [initialQuery]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      setDraft(null);
      return;
    }
    let active = true;
    setError(null);
    apiGet<ResearchProject>(`/research/projects/${selectedId}`)
      .then((project) => {
        if (active) {
          setSelected(project);
          setDraft(projectDraft(project));
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "研究项目加载失败");
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const grouped = useMemo(
    () => ({
      active: projects.filter((item) => item.status !== "archived"),
      archived: projects.filter((item) => item.status === "archived"),
    }),
    [projects],
  );

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (!newTitle.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const project = await apiPost<ResearchProject>("/research/projects", {
        title: newTitle.trim(),
        question: newQuestion.trim(),
        hypothesis: "",
        status: "draft",
        confidence: 50,
      });
      setNewTitle("");
      setNewQuestion("");
      loadProjects(project.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究项目创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveProject(event: FormEvent) {
    event.preventDefault();
    if (!selected || !draft) return;
    setSaving(true);
    setError(null);
    setStatusMessage(null);
    try {
      const updated = await apiPatch<ResearchProject>(`/research/projects/${selected.id}`, {
        ...draft,
        tags: parseResearchTags(draft.tags),
        next_review_date: draft.next_review_date || null,
      });
      setSelected(updated);
      setDraft(projectDraft(updated));
      setProjects((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setStatusMessage("研究项目已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究项目保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function createTemplateProject() {
    setSaving(true);
    setError(null);
    try {
      const project = await apiPost<ResearchProject>("/research/projects/from-template", {
        template_id: templateId,
      });
      setStatusMessage(`已从“${templates.find((item) => item.id === templateId)?.name || "模板"}”创建项目`);
      loadProjects(project.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "模板项目创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function addEntry(event: FormEvent) {
    event.preventDefault();
    if (!selected || !newEntry.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost(`/research/projects/${selected.id}/entries`, {
        ...newEntry,
        title: newEntry.title.trim(),
        content: newEntry.content.trim(),
        due_date: newEntry.due_date || null,
      });
      const refreshed = await apiGet<ResearchProject>(`/research/projects/${selected.id}`);
      setSelected(refreshed);
      setProjects((current) => current.map((item) => (item.id === refreshed.id ? refreshed : item)));
      setNewEntry({ entry_type: "note", title: "", content: "", due_date: "" });
      setStatusMessage("研究记录已添加");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究记录添加失败");
    } finally {
      setSaving(false);
    }
  }

  async function toggleEntry(entryId: number, currentStatus: "open" | "done") {
    if (!selected) return;
    try {
      await apiPatch(`/research/entries/${entryId}`, { status: currentStatus === "open" ? "done" : "open" });
      const refreshed = await apiGet<ResearchProject>(`/research/projects/${selected.id}`);
      setSelected(refreshed);
      setProjects((current) => current.map((item) => (item.id === refreshed.id ? refreshed : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究记录更新失败");
    }
  }

  async function deleteEntry(entryId: number, title: string) {
    if (!selected || !window.confirm(`确认删除“${title}”？`)) return;
    try {
      await apiDelete(`/research/entries/${entryId}`);
      const refreshed = await apiGet<ResearchProject>(`/research/projects/${selected.id}`);
      setSelected(refreshed);
      setProjects((current) => current.map((item) => (item.id === refreshed.id ? refreshed : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究记录删除失败");
    }
  }

  async function importProject(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    try {
      const bundle = JSON.parse(await file.text()) as Record<string, unknown>;
      const project = await apiPost<ResearchProject>("/research/import", bundle);
      setStatusMessage(`已导入“${project.title}”`);
      loadProjects(project.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目文件无法导入");
    }
  }

  async function restoreBackup(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !window.confirm("恢复备份将以备份内容覆盖当前本地研究库。系统会先自动保存当前库，确认继续？")) return;
    setSaving(true);
    setError(null);
    try {
      const result = await apiPostFile<{ ok: boolean; safety_backup: string }>("/research/backup/restore", file);
      setSelectedId(null);
      setSelected(null);
      setDraft(null);
      setStatusMessage(`备份已恢复；恢复前副本：${result.safety_backup}`);
      loadProjects();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "备份恢复失败");
    } finally {
      setSaving(false);
    }
  }

  async function createSafetyBackup() {
    setSaving(true);
    setError(null);
    try {
      const result = await apiPost<{ backup: string; status: BackupStatus }>(
        "/research/backup/auto",
      );
      setBackupStatus(result.status);
      setStatusMessage(`已创建安全备份：${result.backup}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "安全备份创建失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProject() {
    if (!selected) return;
    if (!window.confirm(`确认删除“${selected.title}”及其全部研究证据？此操作无法撤销。`)) return;
    try {
      await apiDelete(`/research/projects/${selected.id}`);
      setSelected(null);
      setDraft(null);
      setSelectedId(null);
      loadProjects();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究项目删除失败");
    }
  }

  async function deleteEvidence(evidenceId: number) {
    if (!selected) return;
    const evidence = selected.evidence.find((item) => item.id === evidenceId);
    if (!window.confirm(`确认删除“${evidence?.title || "该研究证据"}”？此操作无法撤销。`)) return;
    try {
      await apiDelete(`/research/evidence/${evidenceId}`);
      const refreshed = await apiGet<ResearchProject>(`/research/projects/${selected.id}`);
      setSelected(refreshed);
      setDraft(projectDraft(refreshed));
      setProjects((current) => current.map((item) => (item.id === refreshed.id ? refreshed : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究证据删除失败");
    }
  }

  return (
    <div className="page-stack projects-page">
      <PageHeading
        eyebrow="RESEARCH PROJECTS"
        title="研究项目"
        description="记录问题、假设、证据、结论与下一次复盘日期"
      />
      {error ? <ErrorState message={error} /> : null}

      <div className="projects-layout">
        <Panel title="项目列表" eyebrow="LOCAL RESEARCH" className="project-list-panel">
          <div className="project-template-bar">
            <select value={templateId} onChange={(event) => setTemplateId(event.target.value as ResearchTemplate["id"])} aria-label="研究模板">
              {templates.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select>
            <button className="secondary-button" onClick={createTemplateProject} disabled={saving || !templates.length}><CirclePlus size={14} /> 模板立项</button>
            <small>{templates.find((item) => item.id === templateId)?.description}</small>
          </div>
          <details className="project-progressive-section">
            <summary>不用模板，自定义空白项目</summary>
            <form className="new-project-form" onSubmit={createProject}>
              <input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="研究标题" maxLength={160} required />
              <textarea value={newQuestion} onChange={(event) => setNewQuestion(event.target.value)} placeholder="希望验证的研究问题（可稍后补充）" maxLength={2000} />
              <button className="primary-button" disabled={saving}>
                {saving ? <LoaderCircle className="spin" size={14} /> : <CirclePlus size={14} />} 创建项目
              </button>
            </form>
          </details>
          <details className="project-progressive-section maintenance">
            <summary>导入、备份与恢复</summary>
            <div className="project-library-tools">
              <button className="text-button" onClick={() => projectImportRef.current?.click()}><Upload size={13} /> 导入项目</button>
              <button className="text-button" onClick={() => apiDownload("/research/backup", "akdesk-research.db")}><DatabaseBackup size={13} /> 备份研究库</button>
              <button className="text-button" onClick={() => backupRestoreRef.current?.click()}><Upload size={13} /> 恢复备份</button>
              <button className="text-button" onClick={createSafetyBackup} disabled={saving}><DatabaseBackup size={13} /> 立即安全备份</button>
              <input ref={projectImportRef} className="visually-hidden" type="file" tabIndex={-1} aria-hidden="true" accept="application/json,.json" onChange={importProject} />
              <input ref={backupRestoreRef} className="visually-hidden" type="file" tabIndex={-1} aria-hidden="true" accept=".db,application/vnd.sqlite3,application/octet-stream" onChange={restoreBackup} />
            </div>
          </details>
          {backupStatus ? (
            <div className={backupStatus.last_error ? "backup-status warning" : "backup-status"}>
              <DatabaseBackup size={14} />
              <span>
                自动备份{backupStatus.running ? "运行中" : "待启动"} · 保留 {backupStatus.retention} 份 ·
                {backupStatus.latest ? ` 最近 ${formatDateTime(backupStatus.latest.created_at)}` : " 尚无备份"}
              </span>
              {backupStatus.last_error ? <strong>{backupStatus.last_error}</strong> : null}
            </div>
          ) : null}
          {loading ? <LoadingState /> : null}
          <div className="research-project-list">
            {grouped.active.map((project) => (
              <button className={selectedId === project.id ? "active" : undefined} key={project.id} onClick={() => setSelectedId(project.id)}>
                <span className={`research-status ${project.status}`}>{statusLabels[project.status]}</span>
                <div><strong>{project.title}</strong><small>{project.next_review_date ? `复盘 ${project.next_review_date}` : formatDateTime(project.updated_at)}</small></div>
                <span className="confidence-number">{project.confidence}</span>
              </button>
            ))}
            {grouped.archived.length ? <span className="project-group-label">已归档</span> : null}
            {grouped.archived.map((project) => (
              <button className={selectedId === project.id ? "active" : undefined} key={project.id} onClick={() => setSelectedId(project.id)}>
                <span className={`research-status ${project.status}`}>{statusLabels[project.status]}</span>
                <div><strong>{project.title}</strong><small>{formatDateTime(project.updated_at)}</small></div>
                <span className="confidence-number">{project.confidence}</span>
              </button>
            ))}
          </div>
        </Panel>

        <div className="project-detail-stack">
          {selected && draft ? (
            <>
              {(() => {
                const progress = projectProgress(selected);
                return (
                  <section className="project-progress" aria-label="研究项目完成度">
                    <div>
                      <span>研究闭环 {progress.completed}/{progress.total}</span>
                      <strong>{progress.percent}%</strong>
                    </div>
                    <progress max={100} value={progress.percent}>{progress.percent}%</progress>
                    <p><CalendarClock size={14} /> 下一步：{progress.nextStep}</p>
                  </section>
                );
              })()}
              <AiInsightCard
                contextType="project"
                projectId={selected.id}
                title="项目证据 AI 洞察"
                description="检查当前证据、反证与下一步验证缺口，不替你改写研究结论"
                revision={selected.updated_at}
              />
              <ResearchActionPanel
                projectId={selected.id}
                revision={selected.updated_at}
                onProjectChanged={async () => {
                  const refreshed = await apiGet<ResearchProject>(`/research/projects/${selected.id}`);
                  setSelected(refreshed);
                  setDraft(projectDraft(refreshed));
                  setProjects((current) => current.map((item) => item.id === refreshed.id ? refreshed : item));
                }}
              />
              <Panel
                title={selected.title}
                eyebrow="THESIS"
                action={<div className="panel-button-row compact"><button className="text-button" onClick={() => apiDownload(`/research/projects/${selected.id}/export?format=markdown`, `akdesk-project-${selected.id}.md`)}><Download size={13} /> Markdown</button><button className="text-button" onClick={() => apiDownload(`/research/projects/${selected.id}/export?format=json`, `akdesk-project-${selected.id}.json`)}><Download size={13} /> JSON</button><button className="icon-button danger" onClick={deleteProject} aria-label="删除研究项目"><Trash2 size={15} /></button></div>}
              >
                <form className="project-editor" onSubmit={saveProject}>
                  <label className="span-2"><span>标题</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} required /></label>
                  <label className="span-2"><span>研究问题</span><textarea value={draft.question} onChange={(event) => setDraft({ ...draft, question: event.target.value })} /></label>
                  <label><span>状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as ResearchStatus })}>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  <label><span>主观置信度（{draft.confidence}）</span><input type="range" min="0" max="100" value={draft.confidence} onChange={(event) => setDraft({ ...draft, confidence: Number(event.target.value) })} /></label>
                  <label className="span-2"><span>当前结论与风险点</span><textarea className="conclusion-input" value={draft.conclusion} onChange={(event) => setDraft({ ...draft, conclusion: event.target.value })} /></label>
                  <details className="project-advanced-fields span-2">
                    <summary>假设、期限、复盘与标签</summary>
                    <div>
                      <label className="span-2"><span>初始假设</span><textarea value={draft.hypothesis} onChange={(event) => setDraft({ ...draft, hypothesis: event.target.value })} /></label>
                      <label><span>研究期限</span><input value={draft.horizon} onChange={(event) => setDraft({ ...draft, horizon: event.target.value })} placeholder="例如：未来 1–3 个月" /></label>
                      <label><span>下次复盘</span><input type="date" value={draft.next_review_date} onChange={(event) => setDraft({ ...draft, next_review_date: event.target.value })} /></label>
                      <label className="span-2"><span>标签（逗号分隔）</span><input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder="美债，通胀，久期" /></label>
                    </div>
                  </details>
                  <div className="project-editor-actions span-2">
                    {statusMessage ? <span role="status">{statusMessage}</span> : null}
                    <button className="primary-button" disabled={saving}>{saving ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />} 保存项目</button>
                  </div>
                </form>
              </Panel>

              <Panel title={`研究记录 · ${selected.entries.length}`} eyebrow="NOTES · COUNTER-EVIDENCE · TASKS">
                <form className="research-entry-form" onSubmit={addEntry}>
                  <select aria-label="研究记录类型" value={newEntry.entry_type} onChange={(event) => setNewEntry({ ...newEntry, entry_type: event.target.value as ResearchEntryType })}>{Object.entries(entryTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>
                  <input value={newEntry.title} onChange={(event) => setNewEntry({ ...newEntry, title: event.target.value })} placeholder="标题" maxLength={160} required />
                  <input type="date" value={newEntry.due_date} onChange={(event) => setNewEntry({ ...newEntry, due_date: event.target.value })} aria-label="到期日期" />
                  <textarea value={newEntry.content} onChange={(event) => setNewEntry({ ...newEntry, content: event.target.value })} placeholder="记录判断依据、反证、待办或复盘结论" />
                  <button className="secondary-button" disabled={saving}><CirclePlus size={14} /> 添加记录</button>
                </form>
                {selected.entries.length ? <div className="research-entry-list">{selected.entries.map((entry) => <article className={entry.status === "done" ? "done" : undefined} key={entry.id}>
                  <button className="entry-status-button" onClick={() => toggleEntry(entry.id, entry.status)} aria-label={entry.status === "done" ? "重新打开" : "标记完成"}>{entry.status === "done" ? <CheckCircle2 size={16} /> : <ListTodo size={16} />}</button>
                  <div><span className={`entry-type ${entry.entry_type}`}>{entryTypeLabels[entry.entry_type]}</span><strong>{entry.title}</strong>{entry.content ? <p>{entry.content}</p> : null}<small>{entry.due_date ? `到期 ${entry.due_date} · ` : ""}{formatDateTime(entry.updated_at)}</small></div>
                  <button className="icon-button danger" onClick={() => deleteEntry(entry.id, entry.title)} aria-label="删除研究记录"><Trash2 size={14} /></button>
                </article>)}</div> : <div className="empty-state compact-empty"><ListTodo size={25} /><strong>尚无研究记录</strong><p>用笔记、反证、任务和复盘形成可追踪的研究过程。</p></div>}
              </Panel>

              <Panel title={`观点轨迹 · ${selected.activity.length}`} eyebrow="THESIS HISTORY">
                {selected.activity.length ? (
                  <div className="research-activity-list">
                    {selected.activity.map((event) => {
                      const detailLines = activityDetailLines(event);
                      return (
                        <article key={event.id}>
                          <History size={15} />
                          <div>
                            <strong>{event.summary}</strong>
                            {detailLines.map((line) => <span key={line}>{line}</span>)}
                            <small>{formatDateTime(event.created_at)}</small>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="empty-state compact-empty"><History size={25} /><strong>尚无观点变更</strong></div>
                )}
              </Panel>

              <Panel
                title={`研究证据 · ${selected.evidence.length}`}
                eyebrow="EVIDENCE"
                action={<button className="secondary-button" onClick={() => navigate("chart-lab")}><ChartNoAxesCombined size={14} /> 添加图表证据</button>}
              >
                {selected.evidence.length ? (
                  <div className="evidence-list">
                    {selected.evidence.map((item) => {
                      const series = evidenceSeries(item);
                      const marketSignals = marketEvidenceSignals(item);
                      const isMarketSnapshot = item.payload.snapshot_type === "market_brief";
                      const isSovereignSnapshot =
                        item.payload.snapshot_type === "world_bank_sovereign_comparison";
                      const expanded = expandedEvidenceId === item.id;
                      const seriesIds = series.map((entry) => String(entry.series_id || "")).filter(Boolean);
                      return (
                        <article className={expanded ? "expanded" : undefined} key={item.id}>
                          <FileCheck2 size={17} />
                          <div>
                            <strong>{item.title}</strong>
                            <span>{item.source_summary || item.evidence_type}</span>
                            <small>{item.observation_start || "—"} 至 {item.observation_end || "—"} · 保存于 {formatDateTime(item.created_at)}</small>
                          </div>
                          <div className="evidence-actions">
                            <button className="icon-button" onClick={() => setExpandedEvidenceId(expanded ? null : item.id)} aria-label={expanded ? "收起研究证据" : "查看研究证据"}><Eye size={14} /></button>
                            <button className="icon-button danger" onClick={() => deleteEvidence(item.id)} aria-label="删除研究证据"><Trash2 size={14} /></button>
                          </div>
                          {expanded ? (
                            <div className="evidence-detail">
                              <div><span>保存方式</span><strong>{item.payload.storage_mode === "reference_only" ? "引用证据 · 不保存 FRED 观测值" : "本地快照"}</strong></div>
                              {isMarketSnapshot ? (
                                <>
                                  <div><span>市场状态</span><strong>{String(item.payload.market_status || "—")}</strong></div>
                                  <div><span>快照时间</span><strong>{formatDateTime(String(item.payload.generated_at || item.created_at))}</strong></div>
                                  <div><span>信号数量</span><strong>{marketSignals.length} 项</strong></div>
                                </>
                              ) : isSovereignSnapshot ? (
                                <>
                                  <div><span>指标</span><strong>{String((item.payload.indicator as Record<string, unknown> | undefined)?.title_zh || "—")}</strong></div>
                                  <div><span>显示方式</span><strong>{String(item.payload.view || "level")}</strong></div>
                                  <div><span>比较年份</span><strong>{String(item.payload.summary_year || "无共同年份")}</strong></div>
                                  <div><span>许可</span><strong>{String(item.payload.license || "CC BY 4.0")}</strong></div>
                                </>
                              ) : (
                                <>
                                  <div><span>变换</span><strong>{String(item.payload.transform || "原值")}</strong></div>
                                  <div><span>区间</span><strong>{item.payload.years ? `${item.payload.years} 年` : "—"}</strong></div>
                                </>
                              )}
                              {item.payload.notice ? <p>{String(item.payload.notice)}</p> : null}
                              {item.payload.note ? <p className="evidence-note"><strong>研究备注：</strong>{String(item.payload.note)}</p> : null}
                              {isMarketSnapshot && marketSignals.length ? (
                                <div className="market-evidence-signals">
                                  {marketSignals.map((signal) => (
                                    <article key={String(signal.id)}>
                                      <strong>{String(signal.title || signal.id)}</strong>
                                      <span>{String(signal.summary || "")}</span>
                                      <small>{String(signal.observation_time || "观察时间待确认")} · {String(signal.source || "来源待确认")}</small>
                                    </article>
                                  ))}
                                </div>
                              ) : null}
                              {isSovereignSnapshot && Array.isArray(item.payload.countries) ? (
                                <div className="evidence-series-links">
                                  {(item.payload.countries as Array<Record<string, unknown>>).map((country) => (
                                    <span key={String(country.country_code)}>
                                      <Globe2 size={12} /> {String(country.name_zh || country.name || country.country_code)}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {series.length ? (
                                <div className="evidence-series-links">
                                  {series.map((entry) => (
                                    <a href={String(entry.source_url || "https://fred.stlouisfed.org/")} target="_blank" rel="noreferrer" key={String(entry.series_id)}>
                                      <ExternalLink size={12} /> {String(entry.series_id)} · {String(entry.name || "")}
                                    </a>
                                  ))}
                                </div>
                              ) : null}
                              {seriesIds.length ? <button className="secondary-button" onClick={() => navigate("chart-lab", seriesIds.join(","))}><ChartNoAxesCombined size={14} /> 以当前官方版本重新打开</button> : null}
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="empty-state compact-empty"><BookOpenCheck size={26} /><strong>还没有研究证据</strong><p>在图表研究室保存序列、变换与来源引用。</p></div>
                )}
              </Panel>
            </>
          ) : (
            <Panel title="选择或创建研究项目" eyebrow="START">
              <div className="empty-state"><CalendarClock size={28} /><strong>从一个可验证的问题开始</strong><p>研究项目会记录每次观点和证据的演进。</p></div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
