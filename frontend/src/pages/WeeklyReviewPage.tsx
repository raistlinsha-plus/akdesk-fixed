import { Download, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { apiDownload, apiGet } from "../api";
import { ErrorState, LoadingState, Panel, formatDateTime } from "../components/UI";
import type { WeeklyReport } from "../types";
import { shanghaiDate } from "../researchUtils";
import { PageHeading } from "./MarketPages";

export function WeeklyReviewPage({ refreshSeed }: { refreshSeed: number }) {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [endDate, setEndDate] = useState(shanghaiDate);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    apiGet<WeeklyReport>(`/research/weekly-report${endDate ? `?end=${endDate}` : ""}`)
      .then(setReport)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "周报加载失败"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [refreshSeed, endDate]);

  return (
    <div className="page-stack weekly-review-page">
      <PageHeading eyebrow="WEEKLY REVIEW" title="每周研究复盘" description="汇总项目更新、反证、任务、发布复盘和待复盘事项" />
      <div className="filter-bar">
        <label><span>周结束日</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <button className="secondary-button" onClick={load}><RefreshCcw size={14} /> 刷新</button>
        <button className="secondary-button" onClick={() => apiDownload(`/research/weekly-report?format=markdown${endDate ? `&end=${endDate}` : ""}`, "akdesk-weekly.md")}><Download size={14} /> Markdown</button>
      </div>
      <p className="filter-context-note">当前报告按 {endDate} 作为周结束日；修改日期后会立即重新生成。</p>
      {loading ? <LoadingState /> : null}
      {error ? <ErrorState message={error} /> : null}
      {report ? (
        <>
          <div className="metrics-grid six">
            <Metric label="活跃项目" value={report.summary.active_projects} />
            <Metric label="本周更新" value={report.summary.projects_updated} />
            <Metric label="研究笔记" value={report.summary.notes} />
            <Metric label="新增反证" value={report.summary.counter_evidence} />
            <Metric label="完成任务" value={report.summary.tasks_done} />
            <Metric label="未完成任务" value={report.summary.tasks_open} />
          </div>
          <Panel title={`复盘区间 · ${report.start_date} 至 ${report.end_date}`} eyebrow="RESEARCH CADENCE">
            <div className="weekly-review-grid">
              <section><h3>待复盘项目</h3>{report.due_projects.length ? report.due_projects.map((item) => <article key={String(item.id)}><strong>{String(item.title)}</strong><span>置信度 {String(item.confidence)} · {String(item.next_review_date)}</span></article>) : <p>本周没有到期项目。</p>}</section>
              <section><h3>研究活动</h3>{report.activity.length ? report.activity.slice(0, 20).map((item) => <article key={String(item.id)}><strong>{String(item.project_title)}</strong><span>{String(item.summary)}</span><small>{formatDateTime(String(item.created_at))}</small></article>) : <p>本周尚无项目活动。</p>}</section>
              <section><h3>发布复盘</h3>{report.release_reviews.length ? report.release_reviews.map((item) => <article key={String(item.id)}><strong>{String(item.title)}</strong><span>{String(item.series_id)} · {String(item.release_date)}</span></article>) : <p>本周没有发布复盘。</p>}</section>
            </div>
          </Panel>
          <Panel title="观点与下一步" eyebrow="THESIS · NEXT WEEK">
            <div className="weekly-review-grid">
              <section>
                <h3>本周观点</h3>
                {report.conclusion_updates.length ? report.conclusion_updates.map((item) => (
                  <article key={String(item.id)}><strong>{String(item.title)}</strong><span>{String(item.conclusion)}</span></article>
                )) : <p>本周尚未更新明确结论。</p>}
              </section>
              <section>
                <h3>下周待验证</h3>
                {report.open_tasks.length ? report.open_tasks.map((item) => (
                  <article key={String(item.id)}><strong>{String(item.project_title)}</strong><span>{String(item.title)}</span><small>{item.due_date ? `到期 ${String(item.due_date)}` : "尚未设置到期日"}</small></article>
                )) : <p>当前没有未完成研究任务。</p>}
              </section>
              <section>
                <h3>下次复盘</h3>
                {report.next_reviews.length ? report.next_reviews.map((item) => (
                  <article key={String(item.id)}><strong>{String(item.title)}</strong><span>{String(item.next_review_date)}</span></article>
                )) : <p>尚未设置项目复盘日期。</p>}
              </section>
            </div>
          </Panel>
          <p className="compliance-note compact-note">{report.notice}</p>
        </>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong></article>;
}
