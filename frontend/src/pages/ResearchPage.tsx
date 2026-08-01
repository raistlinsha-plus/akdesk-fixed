import { useEffect, useState } from "react";
import { BookOpenCheck, CalendarClock, Download, FileText, Printer } from "lucide-react";
import { apiGet } from "../api";
import {
  ChangeValue,
  ErrorState,
  LoadingState,
  Panel,
  formatDateTime,
  formatNumber,
} from "../components/UI";
import type { DailyReport, DailyReportArchiveItem, HealthItem } from "../types";
import { PageHeading } from "./MarketPages";

function reportMarkdown(report: DailyReport) {
  const lines = [
    `# AKDesk 固收复盘 · ${report.report_date}`,
    "",
    `> ${report.headline}（${report.market_status}）`,
    `> 可信度：${report.confidence.score} / 100，${report.confidence.message}`,
    "",
    "## 资金面",
    "",
    `- 判断：${report.funding.tone}`,
    `- 平均变动：${formatNumber(report.funding.average_change_bp, 2)} BP`,
    ...report.funding.items.map(
      (item) => `- ${item.name}：${formatNumber(item.value, 4)}%，${formatNumber(item.change_bp, 2)} BP`,
    ),
    "",
    "## 收益率曲线",
    "",
    `- 10Y：${formatNumber(report.curve.tenors["10Y"], 4)}%`,
    `- 10Y–1Y：${formatNumber(report.curve.spreads_bp["10Y-1Y"], 2)} BP`,
    `- 30Y–10Y：${formatNumber(report.curve.spreads_bp["30Y-10Y"], 2)} BP`,
    `- 10Y 日变动：${formatNumber(report.curve.ten_year_change_bp, 2)} BP`,
    "",
    "## 国债期货",
    "",
    ...report.futures.map(
      (item) => `- ${item.contract}：${formatNumber(item.price, 3)}，${formatNumber(item.change_pct, 3)}%`,
    ),
    "",
    "## 活跃现券",
    "",
    ...report.active_bonds.slice(0, 5).map(
      (item) => `- ${item.name}：收益率 ${formatNumber(item.yield, 4)}%，变动 ${formatNumber(item.change_bp, 2)} BP`,
    ),
  ];
  if (report.data_notes.length) {
    lines.push("", "## 数据说明", "", ...report.data_notes.map((item) => `- ${item}`));
  }
  if (report.research_workflow) {
    lines.push(
      "",
      "## 投研工作流",
      "",
      `- 进行中项目：${report.research_workflow.active_projects}`,
      `- 待复盘项目：${report.research_workflow.due_projects}`,
      `- 自选宏观指标：${report.research_workflow.macro_watchlist}`,
      ...report.research_workflow.recent_projects.map(
        (item) => `- ${item.title}：${item.status}，置信度 ${item.confidence}`,
      ),
    );
  }
  lines.push("", "仅供个人研究参考，不构成投资建议。");
  return lines.join("\n");
}

export function ResearchPage({ refreshSeed }: { refreshSeed: number }) {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [archives, setArchives] = useState<DailyReportArchiveItem[]>([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<DailyReportArchiveItem[]>("/research/daily-reports")
      .then(setArchives)
      .catch(() => setArchives([]));
  }, [refreshSeed]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setReport(null);
    const query = selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : "";
    apiGet<DailyReport>("/research/daily-report" + query)
      .then((value) => {
        if (active) {
          setReport(value);
          if (!selectedDate) {
            apiGet<DailyReportArchiveItem[]>("/research/daily-reports")
              .then(setArchives)
              .catch(() => undefined);
          }
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "复盘加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSeed, selectedDate]);

  function exportMarkdown() {
    if (!report) return;
    const blob = new Blob([reportMarkdown(report)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-固收复盘-${report.report_date}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page-stack report-page">
      <PageHeading
        eyebrow="DAILY RESEARCH"
        title="每日固收复盘"
        description="自动汇总资金、曲线、期货、活跃现券与数据可信状态"
      />
      <div className="report-archive-bar">
        <label>
          <span>复盘日期</span>
          <select value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)}>
            <option value="">今天 · 自动更新</option>
            {archives.filter((item) => item.report_date !== localIsoDate()).map((item) => (
              <option value={item.report_date} key={item.report_date}>
                {item.report_date} · {reportModeLabel(item.report_mode)} · {confidenceLabel(item.confidence_level)}
              </option>
            ))}
          </select>
        </label>
        <span>归档保存在本机 SQLite，可离线回看。</span>
      </div>
      {loading ? <LoadingState /> : null}
      {error ? (
        <div className="report-error" role="alert">
          <ErrorState message={error} />
          {selectedDate ? (
            <button className="secondary-button" onClick={() => setSelectedDate("")}>
              返回今日复盘
            </button>
          ) : null}
        </div>
      ) : null}
      {report ? (
        <>
          <section className="report-hero">
            <div>
              <span className="eyebrow">{reportModeLabel(report.report_mode).toUpperCase()} BRIEF</span>
              <h2>{report.headline}</h2>
              <p>{report.market_status} · {report.report_date} · 生成于 {formatDateTime(report.generated_at)}</p>
              <div className={`confidence-strip ${report.confidence.level}`}>
                <strong>可信度 {report.confidence.score}</strong>
                <span>{report.confidence.message}</span>
              </div>
              {report.confidence.source_breakdown?.length ? (
                <details className="confidence-detail">
                  <summary>查看核心数据贡献</summary>
                  <div className="confidence-source-grid">
                    {report.confidence.source_breakdown.map((item) => (
                      <div key={item.adapter}>
                        <span>{item.label}</span>
                        <strong>{item.contribution}/{item.weight}</strong>
                        <small>{healthStateLabel(item.state)} · {trustStateLabel(item.trust_level)}</small>
                      </div>
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
            <div className="report-actions">
              <button className="secondary-button" onClick={exportMarkdown}>
                <Download size={15} /> 导出 Markdown
              </button>
              <button className="secondary-button" onClick={() => window.print()}>
                <Printer size={15} /> 打印/PDF
              </button>
            </div>
          </section>

          <div className="metrics-grid">
            <article className="metric-card">
              <span>资金判断</span><strong>{report.funding.tone}</strong>
              <ChangeValue value={report.funding.average_change_bp} />
            </article>
            <article className="metric-card">
              <span>10Y 国债</span><strong>{formatNumber(report.curve.tenors["10Y"], 4)}%</strong>
              <ChangeValue value={report.curve.ten_year_change_bp} />
            </article>
            <article className="metric-card">
              <span>10Y–1Y</span><strong>{formatNumber(report.curve.spreads_bp["10Y-1Y"], 2)} BP</strong>
              <small>期限利差</small>
            </article>
            <article className="metric-card">
              <span>数据可用性</span><strong>{report.data_health.available}/{report.data_health.total}</strong>
              <small>{report.data_health.cached} 个缓存待实时验证 · {report.data_health.history.points.toLocaleString()} 个历史点</small>
            </article>
          </div>

          {report.research_workflow ? (
            <Panel title="投研工作流" eyebrow="RESEARCH LOOP">
              <div className="research-report-summary">
                <article><BookOpenCheck size={17} /><div><strong>{report.research_workflow.active_projects}</strong><span>进行中项目</span></div></article>
                <article><CalendarClock size={17} /><div><strong>{report.research_workflow.due_projects}</strong><span>待复盘项目</span></div></article>
                <article><FileText size={17} /><div><strong>{report.research_workflow.macro_watchlist}</strong><span>自选宏观指标</span></div></article>
                <article><Download size={17} /><div><strong>按需</strong><span>FRED 观测值不落盘</span></div></article>
              </div>
              {report.research_workflow.recent_projects.length ? (
                <div className="report-project-strip">
                  {report.research_workflow.recent_projects.map((item) => (
                    <div key={item.id}><strong>{item.title}</strong><span>{item.status} · 置信度 {item.confidence}{item.next_review_date ? ` · ${item.next_review_date} 复盘` : ""}</span></div>
                  ))}
                </div>
              ) : null}
            </Panel>
          ) : null}

          <div className="two-column">
            <Panel title="收益率异动" eyebrow="BOND MOVERS">
              <div className="table-wrap compact">
                <table>
                  <thead><tr><th>债券</th><th className="num">收益率</th><th className="num">变动</th></tr></thead>
                  <tbody>{report.bond_movers.map((item) => (
                    <tr key={item.code + item.name}>
                      <td><strong>{item.name}</strong><small>{item.code}</small></td>
                      <td className="num mono">{formatNumber(item.yield, 4)}%</td>
                      <td className="num"><ChangeValue value={item.change_bp} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Panel>
            <Panel title="国债期货" eyebrow="CFFEX">
              <div className="future-stack">
                {report.futures.map((item) => (
                  <div className="future-row" key={item.product}>
                    <span className="product-badge">{item.product}</span>
                    <div><strong>{formatNumber(item.price, 3)}</strong><small>{item.contract}</small></div>
                    <ChangeValue value={item.change_pct} suffix="%" />
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <div className="two-column">
            <Panel title="发行事件" eyebrow="EVENTS">
              <EventGroup title="待发行" items={report.event_groups.upcoming} />
              <EventGroup title="近期已发行" items={report.event_groups.recent} />
            </Panel>
            <Panel title="数据说明" eyebrow="TRUST">
              {report.data_notes.length ? (
                <ul className="data-note-list">{report.data_notes.map((item) => <li key={item}>{item}</li>)}</ul>
              ) : (
                <div className="empty-state compact-empty"><FileText size={25} /><strong>本次数据无额外降级说明</strong></div>
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}

function reportModeLabel(mode: DailyReport["report_mode"]): string {
  return { intraday: "盘中快报", close: "收盘复盘", latest: "最近快照" }[mode];
}

function confidenceLabel(level: DailyReport["confidence"]["level"]): string {
  return { high: "高可信", medium: "中等可信", low: "低可信" }[level];
}

function localIsoDate(): string {
  const value = new Date();
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function healthStateLabel(state: HealthItem["state"]): string {
  return {
    healthy: "实时健康",
    cached: "新鲜缓存",
    degraded: "降级",
    unavailable: "不可用",
    not_checked: "未检查",
  }[state];
}

function trustStateLabel(level: HealthItem["trust_level"]): string {
  return {
    trusted: "可信",
    partial: "部分可用",
    suspicious: "含异常",
    unavailable: "不可研究",
  }[level];
}

function EventGroup({ title, items }: { title: string; items: DailyReport["events"] }) {
  return (
    <div className="event-group">
      <h3>{title}<span>{items.length}</span></h3>
      {items.length ? (
        <div className="event-list">
          {items.slice(0, 5).map((item, index) => (
            <div className="event-item" key={item.date + item.title + index}>
              <span className={"importance " + item.importance} />
              <div><small>{item.date} · {item.type}</small><strong>{item.title}</strong></div>
            </div>
          ))}
        </div>
      ) : <p className="muted">暂无记录</p>}
    </div>
  );
}
