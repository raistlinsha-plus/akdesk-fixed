import { useState } from "react";
import { SAMPLE_END, SAMPLE_ENDS, SAMPLE_WEEK, WEEK_NOTE_LIMIT, WEEK_SERIES, formatWeekChange, weeklyChange } from "../crossAssetWeek";
import { DOWNLOAD_URL, WEEK_FEEDBACK_URL } from "../release";
import { downloadScenarioFile } from "../scenarios";
import { ASSESSMENTS, journalMarkdown, type Assessment, type JournalEntry } from "../weekJournal";
import "../pages/crossAssetWeek.css";

const previousWeek = SAMPLE_ENDS[1];
const bond = WEEK_SERIES[1];

export function WeekContinuityDemo({ onReturn, mediaBase }: { onReturn?: () => void; mediaBase?: string }) {
  const [firstNote, setFirstNote] = useState("");
  const [question, setQuestion] = useState("");
  const [previous, setPrevious] = useState<JournalEntry | null>(null);
  const [status, setStatus] = useState<Assessment>("pending");
  const [reason, setReason] = useState("");
  const [nextNote, setNextNote] = useState("");
  const [nextQuestion, setNextQuestion] = useState("");
  const [message, setMessage] = useState("");
  const second: JournalEntry = {
    week_end: SAMPLE_END, revision: "demo-wk2", created_at: SAMPLE_END + "T16:00:00+08:00",
    judgment: nextNote, next_question: nextQuestion, assessment: status, assessment_note: reason,
    previous_revision: previous?.revision ?? null,
  };
  const ready = Boolean(previous && nextNote.trim() && (status === "pending" || reason.trim()));
  const markdown = ready ? journalMarkdown(second, previous, true) : "";
  const change = (end: string) => formatWeekChange(weeklyChange(bond, SAMPLE_WEEK.bond.points, end).change, bond.changeUnit);

  return <section className="asset-week">
    <header>
      <span className="asset-week-kicker">TWO WEEKS · PRACTICE</span>
      <h1>用两周做一次连续复盘</h1>
      <p>从一句判断开始，下周带着问题回来，用新观察核验。</p>
    </header>
    <p className="asset-week-notice" role="note">固定合成样例 · 非真实行情。无需账号或 API Key。文字只存在当前页面内存，不连接行情、研究库或 AI，也不自动反馈。</p>
    {mediaBase && <details><summary>观看 60 秒合成案例导览</summary>
      <video className="asset-week-video" controls playsInline preload="none" poster={mediaBase + "media/continuity-poster.png"} aria-label="连续复盘合成案例导览">
        <source src={mediaBase + "akdesk-continuity-60s.mp4"} type="video/mp4" />
        <track default kind="captions" src={mediaBase + "media/continuity.zh-CN.vtt"} srcLang="zh-CN" label="简体中文" />
      </video>
    </details>}
    {onReturn && <button className="asset-week-link" type="button" onClick={onReturn}>返回本地真实复盘</button>}
    <section className="asset-week-draft" aria-label="第一周">
      <h2>01 · {previousWeek}：留下一个判断</h2>
      <p>合成 10 年期国债收益率周变化：{change(previousWeek)}。可以记下自己想验证的方向。</p>
      <label>第一周判断<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={firstNote}
        onChange={event => { setFirstNote(event.target.value); setPrevious(null); setMessage(""); }} /></label>
      <label>下一周要核验什么？<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={question}
        onChange={event => { setQuestion(event.target.value); setPrevious(null); setMessage(""); }} /></label>
      <button className="asset-week-button" type="button" disabled={!firstNote.trim() || !question.trim()}
        onClick={() => {
          setPrevious({
            week_end: previousWeek, revision: "demo-wk1", created_at: previousWeek + "T16:00:00+08:00",
            judgment: firstNote, next_question: question, assessment: "", assessment_note: "", previous_revision: null,
          });
          setStatus("pending"); setReason(""); setNextNote(""); setNextQuestion(""); setMessage("");
        }}>保存样例并进入下一周</button>
    </section>
    {previous && <section className="asset-week-draft" aria-label="第二周">
      <h2>02 · {SAMPLE_END}：回来核验</h2>
      <p className="asset-week-user-text">上周判断：{previous.judgment}</p>
      <p className="asset-week-user-text">上周待核验：{previous.next_question}</p>
      <p>本周合成国债收益率变化：{change(SAMPLE_END)}。该周汇率缺前期观测；不要把缺失当作不变，也不要把两条变化写成因果。</p>
      <label>样例核验结果<select value={status} onChange={event => setStatus(event.target.value as Assessment)}>
        {Object.entries(ASSESSMENTS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </select></label>
      <label>我的核验依据<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label>第二周判断<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={nextNote} onChange={event => setNextNote(event.target.value)} /></label>
      <label>继续跟踪（可选）<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={nextQuestion} onChange={event => setNextQuestion(event.target.value)} /></label>
      <button className="asset-week-button" type="button" disabled={!ready} onClick={() => {
        try {
          downloadScenarioFile(markdown, "AKDesk-连续周复盘-两周合成样例.md");
          setMessage("已发起下载，文件明确标注合成样例。");
        } catch { setMessage("无法发起下载，请打开预览复制。"); }
      }}>下载两周合成底稿</button>
      {message && <p role="status">{message}</p>}
      {ready && <details><summary>预览两周底稿</summary><pre>{markdown}</pre></details>}
    </section>}
    {!onReturn && <aside className="asset-week-next" aria-label="体验后续">
      <p>真实版在本机保存你的判断和查询引用，不复制样例，不包含行情快照。</p>
      <div className="asset-week-card-actions">
        <a href={DOWNLOAD_URL} className="asset-week-button asset-week-secondary" target="_blank" rel="noreferrer">查看 macOS 安装包</a>
        <a href={WEEK_FEEDBACK_URL} className="asset-week-link" target="_blank" rel="noreferrer">自愿反馈是否做完、卡在哪、是否再次使用</a>
      </div>
    </aside>}
  </section>;
}
