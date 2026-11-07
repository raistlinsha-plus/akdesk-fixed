import { useId, useRef, useState } from "react";
import { ArrowRight, Download, ExternalLink } from "lucide-react";
import { crossNumber } from "../crossAssets";
import {
  EXPERIENCE_ASSETS, EXPERIENCE_COMPARISON, EXPERIENCE_DATES, EXPERIENCE_FEEDBACK_OPTIONS,
  EXPERIENCE_NOTE_LIMIT, EXPERIENCE_SOURCE, experienceChange, experienceFeedback,
  experienceMarkdown, type ExperienceFeedbackField,
} from "../experience";
import { downloadScenarioFile } from "../scenarios";
import "./experienceTask.css";

const STEPS = ["观察变化", "核验依据", "写下判断并导出"] as const;
const LABELS: Record<ExperienceFeedbackField, string> = {
  result: "样例任务结果", install: "本地安装状态", reuse: "七日内实际再次使用", interest: "下一步更需要什么",
};
const DEFAULT_FEEDBACK = { result: "", install: "unknown", reuse: "unknown", interest: "unknown" };

function ExperienceFeedback({ surface }: { surface: "online" | "local" }) {
  const [fields, setFields] = useState(DEFAULT_FEEDBACK);
  const [preview, setPreview] = useState(false);
  const feedback = experienceFeedback(surface, fields);
  return <details className="first-task-feedback">
    <summary>主动反馈完成情况或卡点</summary>
    <p>样例完成、安装成功和实际复访分别记录；打开页面或点击下载不会被自动算作完成。</p>
    <div className="first-task-feedback-fields">
      {(Object.keys(LABELS) as ExperienceFeedbackField[]).map((field) =>
        <label key={field}>{LABELS[field]}<select value={fields[field]} onChange={(event) => {
          setFields((current) => ({ ...current, [field]: event.target.value }));
          setPreview(false);
        }}>
          {field === "result" ? <option value="">请选择实际结果</option> : null}
          {Object.entries(EXPERIENCE_FEEDBACK_OPTIONS[field]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>,
      )}
    </div>
    <button className="first-task-button" disabled={!fields.result} onClick={() => setPreview(true)}>预览反馈字段</button>
    {preview ? <div className="first-task-preview">
      <pre aria-label="首任务反馈预览">{feedback.preview}</pre>
      <p>只预填上面这些固定字段，不附带判断、文件、浏览记录或个人路径。不自动发送；请在 GitHub 核对后自行提交公开反馈。反馈模板随本版发布后生效。</p>
      <a href={feedback.url} target="_blank" rel="noreferrer">前往 GitHub 核对并提交 <ExternalLink size={14} aria-hidden="true" /></a>
    </div> : null}
  </details>;
}

export function ExperienceTask({ surface }: { surface: "online" | "local" }) {
  const id = useId();
  const [step, setStep] = useState(0);
  const [verified, setVerified] = useState(false);
  const [note, setNote] = useState("");
  const [exportState, setExportState] = useState<"idle" | "requested" | "failed">("idle");
  const [resetCount, setResetCount] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const hasDraft = Boolean(note.trim());

  function go(next: number) {
    setStep(next);
    heading.current?.focus();
  }

  function reset() {
    setVerified(false);
    setNote("");
    setExportState("idle");
    setResetCount((value) => value + 1);
    go(0);
  }

  function download() {
    if (!verified || !hasDraft) return;
    try {
      downloadScenarioFile(experienceMarkdown(note), "AKDesk-股债金汇首任务-合成底稿.md");
      setExportState("requested");
    } catch {
      setExportState("failed");
    }
  }

  return <section className="first-task" aria-labelledby={id}>
    <div className="first-task-header">
      <div><span className="first-task-kicker">约 3 分钟 · 合成体验</span><h1 id={id}>带走一份股债金汇观察底稿</h1>
        <p>只做一个任务：比较黄金 ETF 和宽基 ETF 的合成变化，说明你能看出什么、还需要核验什么。</p></div>
      <button className="first-task-button" onClick={reset}>重做首任务</button>
    </div>
    <p className="first-task-notice">固定合成数据，非真实行情。本任务不调用行情、AI 或研究保存接口；判断只在当前页面，离开、刷新或重置会清空。</p>
    <ol className="first-task-steps" aria-label="首任务进度">{STEPS.map((label, index) =>
      <li key={label} aria-current={step === index ? "step" : undefined}><span>0{index + 1}</span> {label}</li>,
    )}</ol>
    <div className="first-task-panel">
      <h2 ref={heading} tabIndex={-1}>{STEPS[step]}</h2>
      {step === 0 ? <>
        <p>先看两只 ETF 在共同日期区间的合成价格变化。它们这次是同向，还是分化？</p>
        <div className="first-task-cards">{EXPERIENCE_ASSETS.map((asset, index) =>
          <article key={asset.id}><h3>{asset.name}</h3><strong>{experienceChange(index === 0 ? EXPERIENCE_COMPARISON.left : EXPERIENCE_COMPARISON.right)}</strong><small>共同日期价格变化 · 非总回报</small></article>,
        )}</div>
      </> : null}
      {step === 1 ? <>
        <p>来源：{EXPERIENCE_SOURCE}。比较仅使用 {EXPERIENCE_COMPARISON.dates.join("、")} 两个共同日期；不是同一时点或因果分析。</p>
        <div className="first-task-table"><table>
          <caption>合成日线 · 单位：元/份</caption>
          <thead><tr><th scope="col">样例日期</th><th scope="col">黄金 ETF</th><th scope="col">宽基 ETF</th></tr></thead>
          <tbody>{EXPERIENCE_DATES.map((date, index) => <tr key={date}>
            <th scope="row">{date}</th><td>{crossNumber(EXPERIENCE_ASSETS[0].prices[index], 3)}</td>
            <td>{EXPERIENCE_ASSETS[1].prices[index] === null ? "—（缺失）" : crossNumber(EXPERIENCE_ASSETS[1].prices[index], 3)}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="first-task-notice">7 月 31 日宽基样本刻意留空：跳过该日，不补零，也不拿其他产品代替。</p>
        <label className="first-task-check"><input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} /> 已核对合成来源、共同日期和缺失项</label>
      </> : null}
      {step === 2 ? <>
        <label className="first-task-note">我的观察<textarea value={note} maxLength={EXPERIENCE_NOTE_LIMIT} rows={4} placeholder="例如：这段样例方向分化；还要核对其他日期，不能据此判断因果。"
          onChange={(event) => { setNote(event.target.value); setExportState("idle"); }} /></label>
        <p>写一句自己的判断即可。底稿只包含合成样例、核验口径和这段文字；不随反馈发送。</p>
        {exportState === "requested" ? <p role="status">已向浏览器发起下载。请打开底稿核对；只有你确认完成，才在下方选择相应反馈。</p> : null}
        {exportState === "failed" ? <p role="alert">未能发起下载。草稿仍在，请重试，或从下方预览手动复制。</p> : null}
        {hasDraft ? <details><summary>预览合成底稿</summary><pre className="first-task-markdown">{experienceMarkdown(note)}</pre></details> : null}
      </> : null}
      <div className="first-task-actions">
        {step > 0 ? <button className="first-task-button" onClick={() => go(step - 1)}>上一步</button> : null}
        {step < 2 ? <button className="first-task-button first-task-primary" disabled={step === 1 && !verified} onClick={() => go(step + 1)}>
          {step === 0 ? "核验样例依据" : "写下我的判断"} <ArrowRight size={15} aria-hidden="true" />
        </button> : <button className="first-task-button first-task-primary" disabled={!hasDraft || !verified} onClick={download}>
          <Download size={15} aria-hidden="true" /> 下载合成底稿
        </button>}
      </div>
    </div>
    <ExperienceFeedback key={resetCount} surface={surface} />
  </section>;
}
