import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpenCheck, Check, Download, RotateCcw, ShieldCheck } from "lucide-react";
import { OnePageBrief } from "../components/OnePageBrief";
import { ScenarioFeedback } from "../components/ScenarioFeedback";
import { DEMO_URL, DOWNLOAD_URL, REPOSITORY_URL } from "../release";
import {
  CREDIT_SAMPLE, DEFAULT_QUESTION, DEFAULT_REVIEW_DATE, DEFAULT_ROLES, DEFAULT_TASK, EVIDENCE_ROLES,
  SAMPLE_BRIEF, SAMPLE_DATE, SAMPLE_SIGNALS, SCENARIOS, creditSampleCsv, creditSampleMarkdown,
  downloadScenarioFile, ratesSampleMarkdown, sampleCurvePoint, scenarioById, validReviewDate,
  type EvidenceRole, type ScenarioId,
} from "../scenarios";
import "./scenarios.css";

export function ScenarioCards({ onSelect }: { onSelect: (id: ScenarioId) => void }) {
  return <div className="scenario-cards">{SCENARIOS.map((item, index) => <article className="scenario-card" key={item.id}><span className="scenario-kicker">0{index + 1} · {item.audience}</span><h3>{item.title}</h3><p>{item.question}</p><div className="scenario-card-outcome"><BookOpenCheck size={16} /><span>{item.outcome}</span></div><button className="scenario-button" onClick={() => onSelect(item.id)}>体验{item.title}<ArrowRight size={14} /></button></article>)}</div>;
}

export function ScenariosPage({ selectedId = "", onSelect, navigate, surface = "local" }: { selectedId?: string; onSelect: (id: ScenarioId | "") => void; navigate?: (page: string) => void; surface?: "online" | "local" }) {
  const scenario = scenarioById(selectedId);
  return <div className="scenario-page">
    <header className="scenario-heading"><span className="scenario-kicker">CASEBOOK · AKDESK</span><h1>{scenario?.title ?? "用一个场景，认识 AKDesk"}</h1><p>{scenario ? scenario.question : "不必先学会全部模块。用固定合成资料，走完一项约五分钟的样例任务，再决定是否进入本地工作台。"}</p></header>
    <div className="scenario-boundary" role="note"><ShieldCheck size={18} /><div><strong>独立样例区 · 非实时行情</strong><p>固定 {SAMPLE_DATE} 合成资料，不请求行情或 AI，不读取或写入研究库。编辑仅保留在当前案例，返回列表、切换案例、重置或刷新会清空；需要留存请先导出。</p></div></div>
    {!scenario ? <>{selectedId ? <p role="status">没有找到该案例，请从下方选择。未载入任何外部内容。</p> : null}<ScenarioCards onSelect={onSelect} /><p className="scenario-small">案例是学习路径，不是投资建议。来源、日期、缺失和人工确认比完整的数字更重要。</p><a className="scenario-doc-link" href={`${REPOSITORY_URL}/blob/main/docs/AKDesk-Fixed-v1.1.2-场景案例与使用指南.md`} target="_blank" rel="noreferrer">阅读中英双语案例与操作说明 →</a></> : <ScenarioWalkthrough key={scenario.id} id={scenario.id} surface={surface} navigate={navigate} onBack={() => onSelect("")} />}
  </div>;
}

function ScenarioWalkthrough({ id, surface, navigate, onBack }: { id: ScenarioId; surface: "online" | "local"; navigate?: (page: string) => void; onBack: () => void }) {
  const scenario = scenarioById(id)!;
  const [step, setStep] = useState(0);
  const [seed, setSeed] = useState(0);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [roles, setRoles] = useState({ ...DEFAULT_ROLES });
  const [task, setTask] = useState(DEFAULT_TASK);
  const [reviewDate, setReviewDate] = useState(DEFAULT_REVIEW_DATE);
  const [selected, setSelected] = useState<string[]>([]);
  const [tenor, setTenor] = useState("10Y");
  const [loaded, setLoaded] = useState(false);
  const [notes, setNotes] = useState("");
  const [copied, setCopied] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [step]);
  const point = sampleCurvePoint(tenor) ?? sampleCurvePoint("10Y")!;
  const markdown = id === "rates" ? ratesSampleMarkdown(question, roles, task, reviewDate) : creditSampleMarkdown(selected);

  function reset() {
    setStep(0); setQuestion(DEFAULT_QUESTION); setRoles({ ...DEFAULT_ROLES }); setTask(DEFAULT_TASK); setReviewDate(DEFAULT_REVIEW_DATE); setSelected([]); setTenor("10Y"); setLoaded(false); setNotes(""); setCopied(""); setSeed(value => value + 1);
  }
  async function copyLink() {
    try { await navigator.clipboard.writeText(`${DEMO_URL}#/scenarios?q=${id}`); setCopied("已复制公开案例链接，不含本页编辑内容。"); }
    catch { setCopied("浏览器不允许复制，请使用下方公开案例链接。"); }
  }

  return <>
    <div className="scenario-toolbar"><button className="scenario-button subtle" onClick={onBack}><ArrowLeft size={14} />返回案例库</button><button className="scenario-button subtle" onClick={reset}><RotateCcw size={14} />重置此案例</button></div>
    <nav className="scenario-steps" aria-label="案例步骤">{scenario.steps.map((label, index) => <button key={label} aria-current={step === index ? "step" : undefined} onClick={() => { setStep(index); setCopied(""); }}><span aria-hidden="true">0{index + 1}</span>{label}</button>)}</nav>
    <section className="scenario-workspace"><div className="scenario-step-heading"><span className="scenario-kicker">STEP {step + 1} / 3 · 浏览步骤不代表完成任务</span><h2 ref={heading} tabIndex={-1}>{scenario.steps[step]}</h2></div>
      {id === "daily" ? <>
        {step === 0 ? <div className="scenario-evidence-grid">{SAMPLE_SIGNALS.map(item => <article className="scenario-evidence" key={item.id}><span>{item.categoryLabel} · 合成样例</span><h3>{item.title}</h3><p>{item.summary}</p><details><summary>展开样例依据</summary><p>{item.evidence}</p></details></article>)}</div> : null}
        {step === 1 ? <div className="scenario-calculation"><label>选择样例期限<select value={tenor} onChange={event => setTenor(event.target.value)}>{["1Y", "5Y", "10Y", "30Y"].map(item => <option key={item}>{item}</option>)}</select></label><dl><div><dt>当前样例 / 前值</dt><dd>{point.value.toFixed(4)}% / {point.previous.toFixed(4)}%</dd></div><div><dt>变动（BP）</dt><dd>{point.changeBp > 0 ? "+" : ""}{point.changeBp.toFixed(2)} BP</dd></div></dl><p>计算：({point.value.toFixed(4)} − {point.previous.toFixed(4)}) × 100。1 BP＝0.01 个百分点；不同期限可能方向相反。</p><p>10Y–1Y 为 40.00 BP；这只是期限利差，不直接推出买卖或久期建议。</p></div> : null}
        {step === 2 ? <OnePageBrief key={seed} document={SAMPLE_BRIEF} notes={notes} onNotesChange={setNotes} /> : null}
      </> : null}
      {id === "rates" ? <>
        {step === 0 ? <div className="scenario-editor"><label>样例研究问题<textarea value={question} maxLength={1500} rows={3} onChange={event => setQuestion(event.target.value)} /></label><p>先写可验证的问题，不把“利率一定下行”当成已经成立的结论。请勿输入 Key、FRED 响应或私人研究材料。</p><div className="scenario-callout"><strong>本次样例假设</strong><p>隔夜资金走低并不等于所有期限同步宽松；长端下行仍需检查分歧。</p></div></div> : null}
        {step === 1 ? <div className="scenario-evidence-grid">{SAMPLE_SIGNALS.map(item => <article className="scenario-evidence" key={item.id}><h3>{item.title}</h3><p>{item.evidence}</p><label>{item.categoryLabel}样例的研究分类<select value={roles[item.id]} onChange={event => setRoles(current => ({ ...current, [item.id]: event.target.value as EvidenceRole }))}>{Object.entries(EVIDENCE_ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></article>)}<p className="scenario-small">分类由你选择；相同材料可能支持不同问题，软件不替你生成结论。这些均为合成样例，不是 FRED 证据。</p></div> : null}
        {step === 2 ? <div className="scenario-editor"><label>样例下次复盘日<input type="date" value={reviewDate} min="2026-08-04" onChange={event => setReviewDate(event.target.value)} /></label>{!validReviewDate(reviewDate) ? <p role="alert">请填写晚于样例观察日的有效日期；这不会设置真实提醒。</p> : null}<label>下一步验证任务<textarea value={task} maxLength={1500} rows={3} onChange={event => setTask(event.target.value)} /></label><ArtifactPreview markdown={markdown} disabled={!validReviewDate(reviewDate)} filename="AKDesk-rates-synthetic.md" /></div> : null}
      </> : null}
      {id === "credit" ? <>
        {step === 0 ? <><p>三条资料均为虚构。先载入固定导入预览，注意评级、日期和来源；这不是通用 CSV 解析器，也不会提交到真实信用库。</p><div className="scenario-actions"><button className="scenario-button" onClick={() => setLoaded(true)}>{loaded ? "已载入固定样例预览" : "载入三条合成资料预览"}</button><button className="scenario-button subtle" onClick={() => downloadScenarioFile(creditSampleCsv(), "AKDesk-credit-synthetic.csv", "text/csv;charset=utf-8")}><Download size={14} />下载合成 CSV</button></div>{loaded ? <CreditTable /> : <div className="scenario-callout">点击载入后查看样例字段，不需要选择个人文件。</div>}</> : null}
        {step === 1 ? <><p>以下是固定 fixture 的覆盖结果，已与后端真实门禁做契约回归；不会因经过演示步骤而变成业务可用数据。</p><CreditTable /><div className="scenario-evidence-grid">{CREDIT_SAMPLE.items.map(({ observation: row, expected }) => <article className="scenario-evidence" key={row.bond_code}><span>{expected.eligible ? "样例机械试算" : "门禁未通过"}</span><h3>{row.bond_name}</h3><strong>{expected.spreadBp === null ? "— 不计算利差" : `${expected.spreadBp.toFixed(2)} BP`}</strong><p>{expected.reason}</p>{expected.eligible ? <p>({row.yield_pct.toFixed(2)} − {row.benchmark_yield_pct.toFixed(2)}) × 100；不是评级或违约概率。</p> : null}</article>)}</div></> : null}
        {step === 2 ? <><p>选择需要人工复核的样例，生成临时清单。不选择不表示无需复核；不会创建正式研究任务。</p><div className="scenario-task-list">{CREDIT_SAMPLE.items.map(({ observation: row, expected }) => <label key={row.bond_code}><input type="checkbox" checked={selected.includes(row.bond_code)} onChange={event => setSelected(current => event.target.checked ? [...current, row.bond_code] : current.filter(value => value !== row.bond_code))} /><span><strong>{row.bond_name}</strong>{expected.task}</span></label>)}</div><ArtifactPreview markdown={markdown} filename="AKDesk-credit-review-synthetic.md" /></> : null}
      </> : null}
    </section>
    <div className="scenario-step-actions"><button className="scenario-button subtle" disabled={step === 0} onClick={() => setStep(value => value - 1)}>上一步</button>{step < 2 ? <button className="scenario-button" onClick={() => setStep(value => value + 1)}>下一步：{scenario.steps[step + 1]}<ArrowRight size={14} /></button> : <span><Check size={15} />到达成品页；是否完成由你自行判断</span>}</div>
    {step === 2 ? <><ScenarioFeedback key={`${id}-${seed}`} scenario={id} surface={surface} /><section className="scenario-continue"><h2>准备把这个方法用于自己的工作？</h2><p>离开样例区后，真实数据与保存规则以正式模块为准；本页内容不会自动带入。使用真实资料前先核验授权和时点。</p><div className="scenario-actions">{navigate ? scenario.localPages.map(item => <button className="scenario-button subtle" key={item.page} onClick={() => navigate(item.page)}>打开本地{item.label}<ArrowRight size={14} /></button>) : <a className="scenario-button" href={DOWNLOAD_URL} target="_blank" rel="noreferrer">查看本地版下载与要求 →</a>}</div></section></> : null}
    <section className="scenario-share"><div><strong>分享的是方法，不是你的研究资料</strong><p>公开链接只包含固定案例 ID，不包含临时输入、选择或个人路径。需在线站点已部署含本案例的版本；复制不代表部署完成。</p></div><button className="scenario-button subtle" onClick={copyLink}>复制公开案例链接</button><a className="scenario-doc-link" href={`${DEMO_URL}#/scenarios?q=${id}`} target="_blank" rel="noreferrer">公开样例链接 →</a>{copied ? <p role="status">{copied}</p> : null}</section>
  </>;
}

function CreditTable() {
  return <div className="scenario-table-wrap"><table><caption>固定合成单券资料 · 日期 {SAMPLE_DATE}</caption><thead><tr><th>样例</th><th>评级</th><th>收益率 % / 日期</th><th>3Y 基准 % / 日期</th></tr></thead><tbody>{CREDIT_SAMPLE.items.map(({ observation: row }) => <tr key={row.bond_code}><th scope="row">{row.bond_name}<small>{row.bond_code}</small></th><td>{row.rating || "— 缺失"}</td><td>{row.yield_pct.toFixed(2)}<small>{row.yield_observation_date}</small></td><td>{row.benchmark_yield_pct.toFixed(2)}<small>{row.benchmark_observation_date}</small></td></tr>)}</tbody></table></div>;
}

function ArtifactPreview({ markdown, filename, disabled = false }: { markdown: string; filename: string; disabled?: boolean }) {
  return <div className="scenario-artifact"><div className="scenario-artifact-heading"><h3>样例成品预览</h3><button className="scenario-button" disabled={disabled} onClick={() => downloadScenarioFile(markdown, filename)}><Download size={14} />下载样例 Markdown</button></div><pre tabIndex={0} aria-label="样例成品预览">{markdown}</pre><p>只导出当前样例与临时编辑，不写入研究库。下载不等于允许公开分享任何自行粘贴的内容。</p></div>;
}
