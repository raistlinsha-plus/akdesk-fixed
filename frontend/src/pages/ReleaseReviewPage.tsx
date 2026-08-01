import { CheckCircle2, Copy, LoaderCircle, Pencil, RefreshCcw, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api";
import { ErrorState, LoadingState, Panel, formatDateTime, formatNumber } from "../components/UI";
import type { MacroCatalogItem, ReleaseEvaluation, ReleaseReview, ResearchProject } from "../types";
import { shanghaiDate } from "../researchUtils";
import { PageHeading } from "./MarketPages";

function today() { return shanghaiDate(); }

const emptyForm = () => ({ title: "", series_id: "CPIAUCSL", release_name: "", release_date: today(), observation_period: today().slice(0, 8) + "01", expected_value: "", expected_unit: "", project_id: "", notes: "" });

export function ReleaseReviewPage() {
  const [reviews, setReviews] = useState<ReleaseReview[]>([]);
  const [catalog, setCatalog] = useState<MacroCatalogItem[]>([]);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<ReleaseEvaluation | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  function load() {
    setLoading(true);
    Promise.all([
      apiGet<ReleaseReview[]>("/release-reviews"),
      apiGet<MacroCatalogItem[]>("/macro/catalog"),
      apiGet<ResearchProject[]>("/research/projects"),
    ]).then(([saved, series, projectRows]) => {
      setReviews(saved); setCatalog(series); setProjects(projectRows);
      setForm((current) => {
        const matched = series.find((item) => item.series_id === current.series_id);
        if (!matched) return current;
        return {
          ...current,
          title: current.title || `${matched.title_zh || matched.title} 发布复盘`,
          release_name: current.release_name || matched.title_zh || matched.title,
          expected_unit: current.expected_unit || matched.units,
        };
      });
      if (!selectedId && saved[0]) setSelectedId(saved[0].id);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "发布复盘加载失败")).finally(() => setLoading(false));
  }
  useEffect(load, []);
  const selected = useMemo(() => reviews.find((item) => item.id === selectedId) || null, [reviews, selectedId]);
  const selectedSeries = useMemo(() => catalog.find((item) => item.series_id === form.series_id) || null, [catalog, form.series_id]);

  function selectSeries(seriesId: string) {
    const series = catalog.find((item) => item.series_id === seriesId);
    setForm((current) => ({
      ...current,
      series_id: seriesId,
      release_name: current.release_name || series?.title_zh || series?.title || "",
      expected_unit: current.expected_unit || series?.units || "",
      title: current.title || (series ? `${series.title_zh || series.title} 发布复盘` : ""),
    }));
  }

  async function saveReview(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const payload = { ...form, expected_value: Number(form.expected_value), project_id: form.project_id ? Number(form.project_id) : null, pre_window_days: 5, post_window_days: 5 };
      const saved = editingId
        ? await apiPatch<ReleaseReview>(`/release-reviews/${editingId}`, payload)
        : await apiPost<ReleaseReview>("/release-reviews", payload);
      setReviews((current) => editingId
        ? current.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...current]);
      setSelectedId(saved.id); setEditingId(null); setForm(emptyForm()); setEvaluation(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "发布复盘保存失败"); }
  }

  function beginEdit(review: ReleaseReview) {
    setEditingId(review.id);
    setForm({ title: review.title, series_id: review.series_id, release_name: review.release_name, release_date: review.release_date, observation_period: review.observation_period, expected_value: String(review.expected_value), expected_unit: review.expected_unit, project_id: review.project_id ? String(review.project_id) : "", notes: review.notes });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function copyReview(review: ReleaseReview) {
    setEditingId(null);
    setForm({ title: `${review.title}（复制）`, series_id: review.series_id, release_name: review.release_name, release_date: review.release_date, observation_period: review.observation_period, expected_value: String(review.expected_value), expected_unit: review.expected_unit, project_id: review.project_id ? String(review.project_id) : "", notes: review.notes });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function evaluate() {
    if (!selected) return; setEvaluating(true); setError(null); setEvaluation(null);
    try { setEvaluation(await apiGet<ReleaseEvaluation>(`/release-reviews/${selected.id}/evaluate`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "实际值请求失败"); }
    finally { setEvaluating(false); }
  }

  async function markReviewed() {
    const realtime = evaluation?.actual.realtime_start; if (!selected || !realtime) return;
    try {
      const saved = await apiPost<ReleaseReview>(`/release-reviews/${selected.id}/mark-reviewed`, { realtime_start: realtime });
      setReviews((current) => current.map((item) => item.id === saved.id ? saved : item));
      setEvaluation((current) => current ? { ...current, revision_status: "unchanged", review: saved } : current);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "版本标记失败"); }
  }

  async function remove() {
    if (!selected || !window.confirm(`确认删除“${selected.title}”？`)) return;
    try {
      await apiDelete(`/release-reviews/${selected.id}`); setReviews((current) => current.filter((item) => item.id !== selected.id)); setSelectedId(null); setEvaluation(null);
      if (editingId === selected.id) { setEditingId(null); setForm(emptyForm()); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "发布复盘删除失败"); }
  }

  return <div className="page-stack">
    <PageHeading eyebrow="DATA RELEASE REVIEW" title="数据发布复盘" description="记录发布前预期，请求级比较实际值，并观察中国市场前后窗口" />
    {error ? <ErrorState message={error} /> : null}
    <div className="release-review-layout">
      <Panel title={editingId ? "编辑发布预期" : "新建发布预期"} eyebrow="EXPECTATION">
        <form className="release-review-form" onSubmit={saveReview}>
          <label><span>标题</span><input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="例如：美国 CPI 发布复盘" /></label>
          <label><span>FRED 序列</span><select value={form.series_id} onChange={(event) => selectSeries(event.target.value)}>{catalog.map((item) => <option value={item.series_id} key={item.series_id}>{item.series_id} · {item.title_zh}</option>)}</select><small>频率：{selectedSeries?.frequency || "待确认"} · 单位：{selectedSeries?.units || "待确认"}</small></label>
          <label><span>发布名称</span><input value={form.release_name} onChange={(event) => setForm({ ...form, release_name: event.target.value })} placeholder="CPI" /></label>
          <label><span>发布日期</span><input type="date" required value={form.release_date} onChange={(event) => setForm({ ...form, release_date: event.target.value })} /></label>
          <label><span>目标观测期</span><input type="date" required value={form.observation_period} onChange={(event) => setForm({ ...form, observation_period: event.target.value })} /></label>
          <label><span>手工预期值</span><input type="number" step="any" required value={form.expected_value} onChange={(event) => setForm({ ...form, expected_value: event.target.value })} /></label>
          <label><span>单位</span><input value={form.expected_unit} onChange={(event) => setForm({ ...form, expected_unit: event.target.value })} placeholder="同比 %" /></label>
          <label><span>关联项目</span><select value={form.project_id} onChange={(event) => setForm({ ...form, project_id: event.target.value })}><option value="">不关联</option>{projects.filter((item) => item.status !== "archived").map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
          <label className="span-2"><span>预期依据</span><textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></label>
          <div className="row-actions"><button className="primary-button">{editingId ? "保存修改" : "保存发布预期"}</button>{editingId ? <button className="secondary-button" type="button" onClick={() => { setEditingId(null); setForm(emptyForm()); }}><X size={14} /> 取消编辑</button> : null}</div>
        </form>
      </Panel>
      <Panel title={`发布复盘 · ${reviews.length}`} eyebrow="SAVED REVIEWS">
        {loading ? <LoadingState /> : null}
        <div className="release-review-list">{reviews.map((item) => <button className={selectedId === item.id ? "active" : undefined} onClick={() => { setSelectedId(item.id); setEvaluation(null); }} key={item.id}><strong>{item.title}</strong><span>{item.series_id} · {item.release_date}</span><small>预期 {item.expected_value} {item.expected_unit}</small></button>)}</div>
        {!loading && reviews.length === 0 ? <div className="empty-state"><RefreshCcw size={28} /><strong>尚无发布复盘</strong><p>先记录发布日期、目标观测期和手工预期；发布后再请求 FRED 官方实际值。</p></div> : null}
      </Panel>
    </div>
    {selected ? <Panel title={selected.title} eyebrow="ACTUAL VS EXPECTED" action={<div className="row-actions"><button className="icon-button" onClick={() => beginEdit(selected)} aria-label="编辑发布复盘"><Pencil size={14} /></button><button className="icon-button" onClick={() => copyReview(selected)} aria-label="复制发布复盘"><Copy size={14} /></button><button className="icon-button danger" onClick={remove} aria-label="删除发布复盘"><Trash2 size={14} /></button></div>}>
      <div className="release-evaluation-toolbar"><span>预期 {selected.expected_value} {selected.expected_unit} · 观测期 {selected.observation_period}</span><button className="primary-button" onClick={evaluate} disabled={evaluating}>{evaluating ? <LoaderCircle className="spin" size={14} /> : <RefreshCcw size={14} />} 请求官方实际值</button></div>
      {evaluation ? <div className="release-evaluation">
        <div className="metrics-grid"><article className="metric-card"><span>预期</span><strong>{selected.expected_value}</strong></article><article className="metric-card"><span>实际</span><strong>{formatNumber(evaluation.actual.value, 4)}</strong></article><article className="metric-card"><span>偏差</span><strong>{formatNumber(evaluation.surprise, 4)}</strong></article><article className="metric-card"><span>版本</span><strong>{evaluation.revision_status === "official_version_changed" ? "官方版本变化" : evaluation.revision_status === "unchanged" ? "未变化" : "未标记"}</strong></article></div>
        <p className="warning-banner">{evaluation.storage_notice}</p>
        <div className="market-window-grid">{evaluation.market_window.series.map((item) => <article key={`${item.adapter}-${item.series_key}-${item.metric}`}><strong>{item.label}</strong><span>{String(item.before?.observation_time || "—")} → {String(item.after?.observation_time || "—")}</span><small>变化 {formatNumber(item.change, 4)}</small></article>)}</div>
        <div className="panel-button-row"><small>vintage {evaluation.actual.realtime_start || "—"} · 请求 {formatDateTime(evaluation.actual.fetched_at)}</small><button className="secondary-button" onClick={markReviewed} disabled={!evaluation.actual.realtime_start}><CheckCircle2 size={14} /> 标记本次版本已复盘</button></div>
      </div> : null}
    </Panel> : null}
  </div>;
}
