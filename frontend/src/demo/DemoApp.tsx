import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChartNoAxesCombined,
  ChevronRight,
  Clock3,
  Download,
  FileText,
  Github,
  MessageSquare,
  RotateCcw,
  Waves,
} from "lucide-react";
import { OnePageBrief } from "../components/OnePageBrief";
import { feedbackUrl } from "../feedback";
import { DOWNLOAD_URL, REPOSITORY_URL } from "../release";
import { DEMO_BRIEF, DEMO_CURVE, DEMO_DATE, DEMO_SIGNALS } from "./demoData";
import { demoTourUrl, demoTourPosterUrl, demoTourCaptionsUrl } from "./demoMedia";

const LineChart = lazy(() => import("../components/Charts").then((module) => ({ default: module.LineChart })));
const BarChart = lazy(() => import("../components/Charts").then((module) => ({ default: module.BarChart })));
const FEEDBACK = feedbackUrl("feature", "demo", "demo");
type DemoPage = "overview" | "changes" | "curves" | "brief";
const PAGES: Array<{ id: DemoPage; label: string; step?: string }> = [
  { id: "overview", label: "产品概览" },
  { id: "changes", label: "市场变化", step: "01" },
  { id: "curves", label: "曲线核验", step: "02" },
  { id: "brief", label: "一页简报", step: "03" },
];

function pageFromHash(): DemoPage {
  const id = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return PAGES.some((page) => page.id === id) ? id as DemoPage : "overview";
}

function navigate(page: DemoPage) {
  window.location.hash = `/${page}`;
}

function ChartPlaceholder() {
  return <div className="demo-chart-loading" role="status">正在载入示例图表…</div>;
}

function SourceNote() {
  return (
    <div className="demo-source-note">
      <Clock3 size={15} aria-hidden="true" />
      <span>样例日期 {DEMO_DATE} · 内置合成数据 · 未连接行情服务</span>
    </div>
  );
}

export function DemoApp() {
  const [page, setPage] = useState<DemoPage>(pageFromHash);
  const [category, setCategory] = useState("all");
  const [comparePrevious, setComparePrevious] = useState(true);
  const [curveKind, setCurveKind] = useState("government");
  const [resetSeed, setResetSeed] = useState(0);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const onRoute = () => {
      setPage(pageFromHash());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onRoute);
    window.addEventListener("popstate", onRoute);
    return () => {
      window.removeEventListener("hashchange", onRoute);
      window.removeEventListener("popstate", onRoute);
    };
  }, []);

  useEffect(() => {
    document.title = `AKDesk Fixed · ${PAGES.find((item) => item.id === page)?.label}在线体验`;
  }, [page]);

  function resetDemo() {
    setCategory("all");
    setComparePrevious(true);
    setCurveKind("government");
    setResetSeed((value) => value + 1);
    navigate("overview");
  }

  const visibleSignals = DEMO_SIGNALS.filter((signal) => category === "all" || signal.category === category);
  const curveValues = curveKind === "government" ? DEMO_CURVE.government : DEMO_CURVE.policy;
  const curveName = curveKind === "government" ? "国债 · 固定样例" : "国开债 · 固定样例";
  const chartSeries = [{ name: curveName, values: curveValues }, ...(comparePrevious && curveKind === "government" ? [{ name: "国债前值 · 固定样例", values: DEMO_CURVE.previous }] : [])];
  const changes = DEMO_CURVE.government.map((value, index) => Number(((value - DEMO_CURVE.previous[index]) * 100).toFixed(2)));

  return (
    <div className="demo-shell">
      <a className="demo-skip-link" href="#demo-main" onClick={(event) => { event.preventDefault(); mainRef.current?.focus(); mainRef.current?.scrollIntoView?.({ block: "start" }); }}>跳到主要内容</a>
      <header className="demo-header">
        <a href="#/overview" className="demo-brand" aria-label="AKDesk Fixed 产品概览">
          <span className="demo-brand-icon" aria-hidden="true"><i /><i /><i /></span>
          <span><strong>AKDesk <em>Fixed</em></strong><small>LOCAL-FIRST · OPEN SOURCE</small></span>
        </a>
        <div className="demo-header-actions">
          <a className="demo-button demo-button-subtle demo-github-link" href={REPOSITORY_URL} target="_blank" rel="noreferrer"><Github size={16} /> GitHub</a>
          <a className="demo-button demo-button-primary" href={DOWNLOAD_URL} target="_blank" rel="noreferrer"><Download size={15} /> 下载本地版</a>
        </div>
      </header>

      <div className="demo-sample-strip" role="note">
        <span className="demo-sample-tag">在线演示</span>
        <span>固定合成示例，非实时行情。无需安装、登录或 API Key。</span>
        <button className="demo-reset" onClick={resetDemo}><RotateCcw size={13} /> 重置体验</button>
      </div>

      <nav className="demo-nav" aria-label="在线演示导航">
        {PAGES.map((item) => (
          <a href={`#/${item.id}`} key={item.id} className={page === item.id ? "is-active" : undefined} aria-current={page === item.id ? "page" : undefined}>
            {item.step ? <span>{item.step}</span> : <ChartNoAxesCombined size={15} />}{item.label}
          </a>
        ))}
      </nav>

      <main id="demo-main" ref={mainRef} className="demo-main" tabIndex={-1}>
        {page === "overview" ? (
          <>
            <section className="demo-intro">
              <div className="demo-intro-copy">
                <p className="demo-eyebrow">YOUR FIRST FIXED-INCOME BRIEF</p>
                <h1>看懂一组市场变化，<br />带走一页研究底稿。</h1>
                <p className="demo-intro-description">AKDesk 把资金、曲线和国债期货的变化整理到同一条路径：先观察，再核验，最后形成带来源与时点的简报。</p>
                <div className="demo-intro-actions">
                  <button className="demo-button demo-button-primary" onClick={() => navigate("changes")}>开始 3 步体验 <ArrowRight size={16} /></button>
                  <button className="demo-button demo-button-outline" onClick={() => navigate("brief")}>先看简报成品 <FileText size={15} /></button>
                </div>
                <ul className="demo-proof-points">
                  <li><Check size={14} /> 免费开源 · MIT</li>
                  <li><Check size={14} /> 本地版面向 macOS</li>
                  <li><Check size={14} /> 数据与研究留在本机</li>
                </ul>
              </div>
              <article className="demo-output-preview" aria-label="示例简报预览">
                <div className="demo-preview-caption"><span><FileText size={14} /> 一页固收简报</span><span className="demo-example-pill">示例</span></div>
                <h2>资金期限分化，长端收益率下行</h2>
                <p className="demo-preview-date">{DEMO_DATE} · 固定场景</p>
                <dl className="demo-preview-metrics">
                  <div><dt>Shibor O/N</dt><dd>1.4250<span>%</span></dd><small className="demo-value-down">−2.10 BP</small></div>
                  <div><dt>10Y 国债</dt><dd>1.8000<span>%</span></dd><small className="demo-value-down">−2.00 BP</small></div>
                  <div><dt>T 示例合约</dt><dd>108.055</dd><small className="demo-value-up">+0.12%</small></div>
                </dl>
                <div className="demo-preview-note"><span>下一步核验</span><p>关注隔夜与 1W 的分化；对照曲线前值，保留超长端期货的方向差异。</p></div>
                <div className="demo-preview-footer"><span>内置合成数据 · 非实时</span><button onClick={() => navigate("brief")}>查看完整简报 <ArrowUpRight size={14} /></button></div>
              </article>
            </section>

            <section className="demo-journey" aria-labelledby="demo-journey-heading">
              <div className="demo-section-title"><h2 id="demo-journey-heading">从变化到产出，只走一条路径</h2><span>这次体验不需要配置任何数据源</span></div>
              <div className="demo-step-grid">
                <button className="demo-step-card" onClick={() => navigate("changes")}><span className="demo-step-number">01</span><Waves size={20} /><h3>观察市场变化</h3><p>查看三项示例变化，展开出处与计算口径。</p><span className="demo-step-link">打开市场变化 <ArrowRight size={14} /></span></button>
                <button className="demo-step-card" onClick={() => navigate("curves")}><span className="demo-step-number">02</span><ChartNoAxesCombined size={20} /><h3>核验收益率曲线</h3><p>对照最新与前值，理解期限利差和 BP 变化。</p><span className="demo-step-link">核验曲线 <ArrowRight size={14} /></span></button>
                <button className="demo-step-card" onClick={() => navigate("brief")}><span className="demo-step-number">03</span><FileText size={20} /><h3>形成一页简报</h3><p>添加临时备注，复制、导出 Markdown 或打印。</p><span className="demo-step-link">查看简报 <ArrowRight size={14} /></span></button>
              </div>
            </section>

            <section className="demo-full-version"><div><h2>继续使用真实数据和本地研究工作流</h2><p>本地版还包括现券、信用观察、统一自选、研究项目、专题和周期复盘。普通使用需 macOS 与 Python 3.11–3.13。</p></div><a className="demo-button demo-button-outline" href={DOWNLOAD_URL} target="_blank" rel="noreferrer">查看安装说明 <ArrowUpRight size={15} /></a></section>
            <section className="demo-video" aria-labelledby="demo-video-heading">
              <div className="demo-section-title"><div><h2 id="demo-video-heading">60 秒看完这条研究路径</h2><p>真实界面截图导览，固定合成示例。可直接播放，也可下载分享。</p></div><a className="demo-button demo-button-outline" href={demoTourUrl} download="AKDesk-60秒导览.mp4"><Download size={15} /> 下载视频</a></div>
              <video controls preload="none" playsInline poster={demoTourPosterUrl} aria-label="AKDesk Fixed 60秒界面截图导览，固定合成数据，非实时录屏">
                <source src={demoTourUrl} type="video/mp4" />
                <track kind="captions" src={demoTourCaptionsUrl} srcLang="zh-CN" label="简体中文" />
                你的浏览器暂不支持视频播放，请使用上方按钮下载导览。
              </video>
              <p className="demo-video-caption">片中界面使用固定合成数据，示例日期为 2026-08-03；此演示不连接后台、行情源或 AI 服务，无需 API Key。</p>
            </section>
            <section className="demo-faq" aria-labelledby="demo-faq-heading">
              <h2 id="demo-faq-heading">开始之前，你可能想知道</h2>
              <details><summary>在线演示和本地版有什么区别？</summary><p>演示使用固定合成数据，只展示市场变化、曲线核验和简报导出的流程。本地版在你的 Mac 上运行，可连接真实公开数据，并保存自选、研究项目和复盘。在线演示不检查你的本机环境，也不会替你安装任何软件。</p></details>
              <details><summary>需要账号、FRED 或 AI 的 API Key 吗？</summary><p>这次在线体验不需要任何账号或 Key。使用本地版的中国固收市场功能也不需要 FRED 或 AI Key；FRED 宏观数据和 AI 助手为独立可选功能，启用时再由用户配置自己的 Key。</p></details>
            </section>
          </>
        ) : null}

        {page === "changes" ? (
          <>
            <div className="demo-page-heading"><div><p className="demo-eyebrow">01 / OBSERVE</p><h1>市场变化</h1><p>从三条变化开始，展开数据依据，再进入曲线核验。</p></div><SourceNote /></div>
            <div className="demo-context-bar"><span>当前场景</span><strong>资金期限分化 · 10Y 下行 · 超长端期货分歧</strong><span className="demo-example-pill">固定合成示例</span></div>
            <div className="demo-filter-row"><div role="group" aria-label="筛选示例类别">{[{ id: "all", label: "全部变化" }, { id: "funding", label: "资金" }, { id: "curve", label: "曲线" }, { id: "future", label: "期货" }].map((item) => <button key={item.id} aria-pressed={category === item.id} className={category === item.id ? "is-active" : undefined} onClick={() => setCategory(item.id)}>{item.label}</button>)}</div><span>显示 {visibleSignals.length} / 3 条示例</span></div>
            <ol className="demo-signal-list">
              {visibleSignals.map((signal) => (
                <li className="demo-signal-card" key={signal.id}>
                  <div className="demo-signal-main"><div className="demo-signal-heading"><span className="demo-category-tag">{signal.categoryLabel}</span><h2>{signal.title}</h2></div><p>{signal.summary}</p><details><summary>查看数据依据与计算口径 <ChevronRight size={13} /></summary><p>{signal.evidence}</p><SourceNote /></details></div>
                  <div className="demo-signal-value"><strong className={`demo-value-${signal.direction}`}>{signal.direction === "down" ? <ArrowDownRight size={19} /> : <ArrowUpRight size={19} />}{signal.value}</strong><span>{signal.label}</span><small>示例变化 · 不触发提醒</small></div>
                </li>
              ))}
            </ol>
            <div className="demo-next-step"><div><span>下一步 · 02</span><h2>变化有没有对应的数据依据？</h2><p>打开期限结构，对照国债曲线最新样例与前值。</p></div><button className="demo-button demo-button-primary" onClick={() => navigate("curves")}>核验收益率曲线 <ArrowRight size={16} /></button></div>
          </>
        ) : null}

        {page === "curves" ? (
          <>
            <div className="demo-page-heading"><div><p className="demo-eyebrow">02 / VERIFY</p><h1>曲线核验</h1><p>切换曲线并对照前值，确认变化的期限、数值与单位。</p></div><SourceNote /></div>
            <div className="demo-metric-grid"><div><span>10Y 国债 · 样例</span><strong>1.8000<small>%</small></strong><p>最新样例水平</p></div><div><span>10Y 较前值</span><strong className="demo-value-down">−2.00<small> BP</small></strong><p>前值 1.8200%</p></div><div><span>10Y–1Y 期限利差</span><strong>40.00<small> BP</small></strong><p>(1.8000% − 1.4000%) × 100</p></div></div>
            <section className="demo-chart-panel"><header><div><h2>国债与政策金融债曲线</h2><p>横轴为期限，纵轴为收益率（%）</p></div><div className="demo-chart-controls"><label>查看曲线<select value={curveKind} onChange={(event) => setCurveKind(event.target.value)}><option value="government">国债样例</option><option value="policy">国开债样例</option></select></label><label className="demo-compare-label"><input type="checkbox" checked={comparePrevious} disabled={curveKind !== "government"} onChange={(event) => setComparePrevious(event.target.checked)} /> 对照国债前值</label></div></header><Suspense fallback={<ChartPlaceholder />}><LineChart categories={DEMO_CURVE.tenors} series={chartSeries} height={310} /></Suspense><SourceNote /></section>
            <div className="demo-curve-secondary"><section className="demo-chart-panel"><header><div><h2>国债各期限较前值变化</h2><p>−2.00 BP 等于收益率下降 0.02 个百分点</p></div></header><Suspense fallback={<ChartPlaceholder />}><BarChart categories={DEMO_CURVE.tenors} values={changes} height={240} /></Suspense></section><section className="demo-calculation-card"><span className="demo-eyebrow">VERIFY THE NUMBERS</span><h2>把变化算清楚</h2><dl><div><dt>10Y 日变化</dt><dd>(1.80 − 1.82) × 100<br /><strong>−2.00 BP</strong></dd></div><div><dt>10Y–1Y 期限利差</dt><dd>(1.80 − 1.40) × 100<br /><strong>40.00 BP</strong></dd></div></dl><p>这里使用固定合成样例。本地版会显示真实数据来源、观测时间和抓取状态；历史缺失时保留为空。</p></section></div>
            <div className="demo-next-step"><div><span>下一步 · 03</span><h2>把核验后的信息整理成底稿</h2><p>加入你的备注，导出带样例标识和出处的一页简报。</p></div><button className="demo-button demo-button-primary" onClick={() => navigate("brief")}>生成一页简报 <ArrowRight size={16} /></button></div>
          </>
        ) : null}

        {page === "brief" ? (
          <>
            <div className="demo-page-heading"><div><p className="demo-eyebrow">03 / TAKE AWAY</p><h1>一页固收简报</h1><p>在下方添加临时备注，复制或下载 Markdown，也可以打印为 PDF。</p></div><SourceNote /></div>
            <OnePageBrief key={resetSeed} document={DEMO_BRIEF} />
            <section className="demo-completion"><div className="demo-completion-icon"><Check size={22} /></div><div><h2>你已经完成一条从变化到产出的路径</h2><p>喜欢这个工作方式？下载本地版连接真实数据，或告诉我们哪一步最需要改善。</p></div><div><a className="demo-button demo-button-primary" href={DOWNLOAD_URL} target="_blank" rel="noreferrer"><Download size={15} /> 下载本地版</a><a className="demo-button demo-button-outline" href={FEEDBACK} target="_blank" rel="noreferrer"><MessageSquare size={15} /> 提交反馈</a></div></section>
          </>
        ) : null}
      </main>

      <footer className="demo-footer"><div><strong>AKDesk Fixed</strong><span>MIT 开源 · 本地优先 · 个人研究</span></div><p>当前为固定合成样例，不代表真实行情。本地版使用公开数据，适合个人学习与研究。</p><a href={FEEDBACK} target="_blank" rel="noreferrer">反馈体验 <ArrowUpRight size={13} /></a></footer>
    </div>
  );
}
