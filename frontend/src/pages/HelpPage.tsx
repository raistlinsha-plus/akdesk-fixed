import { useState } from "react";
import { ArrowRight, Check, Clipboard, Download, ExternalLink, LifeBuoy, RefreshCcw } from "lucide-react";
import { apiGet } from "../api";
import { diagnosticMarkdown, feedbackUrl, type DiagnosticReport } from "../feedback";
import { APP_VERSION, DEMO_URL, DOWNLOAD_URL, REPOSITORY_URL } from "../release";
import { PageHeading } from "./MarketPages";
import "./help.css";
import { DATA_RULES_REVIEWED_AT, DATA_USAGE_NOTICE, FRED_USAGE_NOTICE } from "../dataUsage";
import { ScenarioCards } from "./ScenariosPage";
import { ExperienceTask } from "../components/ExperienceTask";

export function HelpPage({ navigate, initialQuery = "" }: { navigate: (page: string, query?: string) => void; initialQuery?: string }) {
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const markdown = report ? diagnosticMarkdown(report) : "";

  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      setReport(await apiGet<DiagnosticReport>("/diagnostics"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "诊断摘要暂时无法生成，请先确认本地服务仍在运行。");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      setMessage("已复制。请检查内容后，自行粘贴到反馈中。");
    } catch {
      setMessage("浏览器未允许复制，请下载摘要或在预览中手动选择文字。");
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `AKDesk-diagnostics-v${APP_VERSION}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (initialQuery === "start") return <div className="page-stack help-page">
    <div><button className="secondary-button" onClick={() => navigate("help")}>返回使用与反馈</button></div>
    <ExperienceTask surface="local" />
  </div>;

  return <div className="page-stack help-page">
    <PageHeading eyebrow="GET STARTED & FEEDBACK" title="使用与反馈" description={`AKDesk Fixed v${APP_VERSION} · 从一份简报开始，遇到问题也能找到下一步。`} />
    <section className="help-start panel"><div><LifeBuoy size={24} /><h2>先做三分钟首任务</h2><p>用合成资料核对两只 ETF，写下判断并带走底稿。不需要设置数据源或创建项目。</p></div><button className="secondary-button" onClick={() => navigate("help", "start")}>开始三分钟首任务 <ArrowRight size={15} /></button></section>
    <section className="help-diagnostics panel"><h2>区分启动故障和行情缺失</h2><p>网页打不开：先看原启动窗口的预检提示，确认服务仍在运行。已能打开网页但行情为“—”：先核对观测日期、来源与缓存状态，不必重新安装。</p><button className="secondary-button" onClick={() => navigate("health")}>查看数据健康 <ArrowRight size={15} /></button></section>
    <section className="help-casebook panel"><span className="eyebrow">FIVE-MINUTE CASEBOOK</span><h2>选一个任务，先用合成资料练习</h2><p>独立样例不会写入研究库。先看方法与成品，再进入正式模块；不需要 FRED 或 AI Key。</p><ScenarioCards onSelect={id => navigate("scenarios", id)} /></section>
    <section className="help-start panel">
      <div><LifeBuoy size={24} /><h2>先完成一次市场复盘</h2><p>查看变化，回到曲线核验，再把资金、曲线与期货整理成带出处的简报。</p></div>
      <div className="help-steps">
        <button onClick={() => navigate("market-changes")}><span>01</span>查看市场变化<ArrowRight size={16} /></button>
        <button onClick={() => navigate("curves")}><span>02</span>核验收益率曲线<ArrowRight size={16} /></button>
        <button onClick={() => navigate("report")}><span>03</span>导出一页简报<ArrowRight size={16} /></button>
      </div>
    </section>
    <section className="help-diagnostics panel" aria-labelledby="data-usage-title">
      <span className="eyebrow">DATA USAGE · {DATA_RULES_REVIEWED_AT}</span>
      <h2 id="data-usage-title">连接成功，不代表已经获得使用授权</h2>
      <p>软件代码的 MIT 许可不包含第三方行情数据授权。AKShare 官方声明用于学术研究，机构或商业场景应先核验原始数据源条款。</p>
      <p>{FRED_USAGE_NOTICE} 不要向 AI 粘贴 FRED 数值、API 元数据或受限原文；未标来源的手工内容无法自动识别。</p>
      <p>{DATA_USAGE_NOTICE} World Bank 默认开放许可存在数据集/指标例外；GDELT 开放数据也不包含新闻正文和图片的版权。</p>
      <a href={`${REPOSITORY_URL}/blob/main/DATA_USAGE.md`} target="_blank" rel="noreferrer">查看数据使用规则与版本核验记录 <ExternalLink size={14} /></a>
    </section>
    <section className="help-feedback-grid" aria-label="选择反馈类型">
      <a href={feedbackUrl("bug", "help", report?.app.mode ?? "unknown")} target="_blank" rel="noreferrer"><strong>功能或界面问题</strong><span>描述操作步骤、预期与实际结果。</span><ExternalLink size={16} /></a>
      <a href={feedbackUrl("data", "help", report?.app.mode ?? "unknown")} target="_blank" rel="noreferrer"><strong>行情或连接异常</strong><span>先查看数据健康，再提供状态与发生时间。</span><ExternalLink size={16} /></a>
      <a href={feedbackUrl("feature", "help", report?.app.mode ?? "unknown")} target="_blank" rel="noreferrer"><strong>分享你的使用场景</strong><span>告诉我们哪项任务可以更省时间。</span><ExternalLink size={16} /></a>
    </section>
    <section className="help-diagnostics panel">
      <div className="help-section-title"><div><span className="eyebrow">LOCAL DIAGNOSTICS</span><h2>生成可分享的诊断摘要</h2></div><button className="secondary-button" onClick={generate} disabled={busy}><RefreshCcw size={15} className={busy ? "spin" : ""} />{busy ? "正在生成" : report ? "重新生成" : "生成诊断摘要"}</button></div>
      <p>只整理系统版本、Python、存储类型和数据源状态。摘要在本机生成，不包含 Key、个人路径、原始错误、数据库或研究内容，不会自动上传。</p>
      {report ? <><div className="help-report-actions"><span><Check size={15} />请先预览，再决定是否分享</span><button className="secondary-button" onClick={copy}><Clipboard size={15} />复制摘要</button><button className="secondary-button" onClick={download}><Download size={15} />下载 Markdown</button></div><pre className="help-report-preview" tabIndex={0} aria-label="诊断摘要预览">{markdown}</pre></> : <div className="help-empty">点击后会显示完整预览，提交反馈由你决定。</div>}
      {message ? <p className="help-message" role="status">{message}</p> : null}
    </section>
    <section className="help-links panel"><a href={`${REPOSITORY_URL}/blob/main/docs/AKDesk-Fixed-v1.3.1-用户手册.md`} target="_blank" rel="noreferrer">用户手册<ExternalLink size={14} /></a><a href={DEMO_URL} target="_blank" rel="noreferrer">在线示例<ExternalLink size={14} /></a><a href={DOWNLOAD_URL} target="_blank" rel="noreferrer">下载正式版<ExternalLink size={14} /></a><a href={`${REPOSITORY_URL}/discussions/16`} target="_blank" rel="noreferrer">分享体验<ExternalLink size={14} /></a><a href={`${REPOSITORY_URL}/blob/main/ROADMAP.md`} target="_blank" rel="noreferrer">公开路线图<ExternalLink size={14} /></a></section>
  </div>;
}
