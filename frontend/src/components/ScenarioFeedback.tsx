import { useState } from "react";
import { ExternalLink, MessageSquare } from "lucide-react";
import { scenarioFeedback, type ScenarioOutcome, type ReuseIntent } from "../feedback";
import type { ScenarioId } from "../scenarios";

export function ScenarioFeedback({ scenario, surface }: { scenario: ScenarioId; surface: "online" | "local" }) {
  const [outcome, setOutcome] = useState<ScenarioOutcome | "">("");
  const [reuse, setReuse] = useState<ReuseIntent>("unsure");
  const [preview, setPreview] = useState(false);
  const feedback = scenarioFeedback(scenario, outcome, reuse, surface);
  return <section className="scenario-feedback" aria-labelledby="scenario-feedback-title">
    <span className="scenario-kicker"><MessageSquare size={15} /> OPTIONAL FEEDBACK</span>
    <h2 id="scenario-feedback-title">这条路径对你有用吗？</h2>
    <p>不自动统计完成，不追踪身份。请选择实际体验；“愿意再试”只是意愿，不代表七日留存。</p>
    <div className="scenario-form-row">
      <label>这次体验结果<select value={outcome} onChange={event => { setOutcome(event.target.value as ScenarioOutcome | ""); setPreview(false); }}><option value="">请选择实际状态</option><option value="completed">已完成样例任务</option><option value="blocked">中途遇到阻碍</option><option value="browsed">只浏览了案例</option></select></label>
      <label>下周是否愿意再试<select value={reuse} onChange={event => { setReuse(event.target.value as ReuseIntent); setPreview(false); }}><option value="unsure">不确定</option><option value="yes">愿意尝试</option><option value="no">暂时不会</option></select></label>
      <button className="scenario-button" disabled={!outcome} onClick={() => setPreview(true)}>预览反馈信息</button>
    </div>
    {preview ? <div className="scenario-feedback-preview"><pre aria-label="反馈预填预览">{feedback.preview}</pre><p>只预填版本、固定场景、样例模式、体验结果和复用意愿。不会附带本页问题、笔记、所选任务、诊断或研究内容。点击仅打开 GitHub，需登录并核对后自行提交；未提交不会收到反馈。新反馈模板需仓库发布本版后可用，本地预览不代表已发布。</p><a className="scenario-button" href={feedback.url} target="_blank" rel="noreferrer">前往 GitHub 核对并提交 <ExternalLink size={14} /></a></div> : null}
  </section>;
}
