import { useEffect, useState, type ReactNode } from "react";
import { ApiError, apiGet, apiPost } from "../api";
import { WEEK_NOTE_LIMIT } from "../crossAssetWeek";
import { downloadScenarioFile } from "../scenarios";
import {
  ASSESSMENTS, fromEntry, journalMarkdown,
  type Assessment, type JournalDraft, type JournalEntry, type JournalList, type JournalState,
} from "../weekJournal";

const requestOptions = { timeoutMs: 15_000, timeoutMessage: "本地响应超时；请先重新读取确认是否保存，草稿仍保留。" };
const reasonText = (reason: unknown) => reason instanceof Error ? reason.message : "本地记录操作失败。";

export function WeekJournal({ date, draft, onDraft, onSelectDate, children }: {
  date: string;
  draft?: JournalDraft;
  onDraft: (draft: JournalDraft | undefined, expected?: JournalDraft) => void;
  onSelectDate: (date: string) => void;
  children: ReactNode;
}) {
  const path = "/week-journal/" + date;
  const [state, setState] = useState<JournalState | null>(null);
  const [load, reload] = useState(0);
  const [reading, setReading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [readError, setReadError] = useState("");
  const [message, setMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [selectedRevision, selectRevision] = useState<JournalEntry | null>(null);
  const [history, showHistory] = useState(false);
  const [versions, showVersions] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15_000);
    setReading(true);
    setReadError("");
    apiGet<JournalState>(path, { signal: controller.signal }).then(value => {
      if (!active) return;
      if (value.week_end !== date) throw Error("本地记录日期与当前页不符。");
      setState(value);
      setConflict(false);
    }).catch((reason: unknown) => {
      if (active) setReadError(controller.signal.aborted ? "本地记录读取超时。" : reasonText(reason));
    }).finally(() => {
      window.clearTimeout(timer);
      if (active) setReading(false);
    });
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [date, path, load]);

  const editor = draft ?? fromEntry(state?.current ?? null);
  const latestRevision = state?.current?.revision ?? null;
  const stale = Boolean(state && draft && draft.expected_revision !== latestRevision);
  const previous = editor.previous_revision
    ? [state?.assessed, state?.previous].find(item => item?.revision === editor.previous_revision) ?? null
    : state?.previous ?? null;
  const savedPrevious = state?.current?.previous_revision ? state.assessed : null;
  const canSave = state && draft && !reading && !busy && !readError && !stale && !conflict &&
    (editor.judgment.trim() || editor.next_question.trim() || editor.assessment);

  function update(changes: Partial<JournalDraft>) {
    onDraft({ ...editor, ...changes });
    setMessage("");
    setSaveError("");
  }

  async function mutate(remove: boolean) {
    if (!state || reading || busy || readError || stale || conflict) return;
    if (remove ? !latestRevision || !confirmDelete : !canSave) return;
    setBusy(true);
    setSaveError("");
    setMessage("");
    try {
      if (remove) {
        await apiPost(path + "/delete", { expected_revision: latestRevision, confirmed: true }, requestOptions);
        setState({ ...state, current: null, assessed: null });
        selectRevision(null);
        setConfirmDelete(false);
        setMessage("本周及其修订已从当前研究库删除。既有备份和导出未变动。");
      } else {
        const saved = await apiPost<JournalEntry>(path, {
          ...editor, previous_revision: editor.previous_revision ?? previous?.revision ?? null,
        }, requestOptions);
        if (saved.week_end !== date || !saved.revision) throw Error("保存响应与当前周不符，请重新读取。");
        setState({ ...state, current: saved, assessed: saved.previous_revision ? previous : null });
        selectRevision(null);
        onDraft(undefined, draft);
        setMessage("已保存到本机。");
      }
      showHistory(false);
      showVersions(false);
    } catch (reason) {
      setConflict(reason instanceof ApiError && reason.status === 409);
      setSaveError(reasonText(reason));
    } finally {
      setBusy(false);
    }
  }

  const showStatus = Boolean(editor.assessment || previous?.next_question);
  const markdown = state?.current ? journalMarkdown(state.current, savedPrevious) : "";

  return <>
    <section className="asset-week-draft" aria-label="上一周记录">
      <h2>接着上一周复盘</h2>
      {reading ? <p role="status">正在读取本地周复盘…</p> : null}
      {readError ? <p role="alert">{readError} 行情查看不受影响。</p> : null}
      {state && previous ? <>
        <p>{previous.week_end} · 用户自撰记录 · 不是行情快照</p>
        <p className="asset-week-user-text">{previous.judgment || "上周未写判断。"}</p>
        {previous.next_question ? <p className="asset-week-user-text">上周待核验：{previous.next_question}</p> : null}
        {state.previous?.revision && state.previous.revision !== previous.revision && <div>
          <p>当前显示已引用的修订；上一周另有较新记录。</p>
          <button className="asset-week-link" type="button" disabled={busy}
            onClick={() => update({ previous_revision: state.previous?.revision ?? null, assessment: "", assessment_note: "" })}>改用上一周最新修订，重新核验</button>
        </div>}
      </> : state && !reading ? <p>{editor.previous_revision ? "原核验所引用的修订已不可用。" : "尚无上周复盘。只查找恰好早七天的同口径周，不把其他日期当作上周。"}</p> : null}
      {!previous && editor.previous_revision && <button className="asset-week-link" type="button" disabled={busy}
        onClick={() => update({ previous_revision: state?.previous?.revision ?? null, assessment: "", assessment_note: "" })}>
        {state?.previous ? "改用上一周最新修订，重新核验" : "移除缺失引用与原核验结果"}
      </button>}
      <div className="asset-week-card-actions">
        <button className="asset-week-button asset-week-secondary" type="button" onClick={() => { setConfirmDelete(false); reload(value => value + 1); }} disabled={reading || busy}>重新读取本地记录</button>
        <button className="asset-week-link" type="button" aria-expanded={history} onClick={() => showHistory(!history)}>周复盘历史</button>
      </div>
      {history && <JournalBrowser onChoose={item => onSelectDate(item.week_end)} />}
    </section>
    {children}
    <section className="asset-week-draft" aria-label="本周复盘记录">
      <h2>保存本周判断</h2>
      <p>{draft ? "有未保存修改" : state?.current ? "已保存 · " + new Date(state.current.created_at).toLocaleString("zh-CN") : "尚未保存"}。保存与导出分开；写一句就能保存，无需补齐全部行情。</p>
      {(stale || conflict) && <p role="alert">本地记录与草稿基线不同，未自动覆盖。先重新读取，再决定采用哪一份。</p>}
      {stale && !conflict && !readError && <div className="asset-week-card-actions">
        <button className="asset-week-button asset-week-secondary" type="button" disabled={busy || reading}
          onClick={() => update({ expected_revision: latestRevision })}>保留草稿，在最新修订基础上编辑</button>
        <button className="asset-week-link" type="button" disabled={busy || reading}
          onClick={() => { if (window.confirm("放弃此周未保存草稿，加载本机记录？")) onDraft(undefined); }}>放弃草稿，载入已保存记录</button>
      </div>}
      <label>本周判断<textarea rows={3} maxLength={WEEK_NOTE_LIMIT} value={editor.judgment} disabled={busy}
        onChange={event => update({ judgment: event.target.value })} /></label>
      <label>下周待核验事项<textarea rows={2} maxLength={WEEK_NOTE_LIMIT} value={editor.next_question} disabled={busy}
        onChange={event => update({ next_question: event.target.value })} /></label>
      {showStatus && <>
        <label>对上一周的人工核验<select value={editor.assessment} disabled={busy}
          onChange={event => {
            const assessment = event.target.value as Assessment;
            if (!assessment) update({ assessment: "", assessment_note: "", previous_revision: null });
            else if (previous?.next_question) update({ assessment, previous_revision: previous.revision });
          }}>
          <option value="">未标记</option>
          {Object.entries(ASSESSMENTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        {editor.assessment && <label>人工核验说明<textarea rows={2} maxLength={WEEK_NOTE_LIMIT}
          value={editor.assessment_note} disabled={busy} onChange={event => update({ assessment_note: event.target.value })} /></label>}
      </>}
      <p>只保存用户文字、区间、修订及引用关系。请勿粘贴凭据或受限行情。来源可以重新查询，不代表复原历史行情。</p>
      <div className="asset-week-card-actions">
        <button className="asset-week-button" disabled={!canSave} type="button" onClick={() => void mutate(false)}>{busy ? "处理中…" : "保存到本机"}</button>
        {state?.current && <>
          <button className="asset-week-button asset-week-secondary" type="button" disabled={busy || reading || Boolean(readError)}
            onClick={() => {
              try {
                downloadScenarioFile(markdown, "AKDesk-连续周复盘-" + date + "-查询引用.md");
                setMessage("已发起下载，导出的是已保存版本。");
              } catch { setSaveError("下载失败，可以打开预览后复制。"); }
            }}>导出已保存底稿</button>
          <button className="asset-week-link" type="button" aria-expanded={versions} onClick={() => showVersions(!versions)}>本周修订</button>
          <button className="asset-week-link" type="button" disabled={busy || reading || Boolean(readError) || Boolean(draft) || conflict}
            onClick={() => setConfirmDelete(!confirmDelete)}>删除本周</button>
        </>}
      </div>
      {confirmDelete && !draft && !readError && !conflict && <div className="asset-week-notice">
        <p>将删除 {date} 的本地记录及全部修订，无法在应用内撤销。其他周可能显示引用已不可用；已导出的文件和备份不会被删除。</p>
        <button type="button" className="asset-week-button" disabled={busy || reading} onClick={() => void mutate(true)}>确认删除本周及修订</button>
        <button type="button" className="asset-week-link" disabled={busy} onClick={() => setConfirmDelete(false)}>取消删除</button>
      </div>}
      {message && <p role="status">{message}</p>}
      {saveError && <p role="alert">{saveError}</p>}
      {markdown && <details><summary>预览已保存 Markdown</summary><pre>{markdown}</pre></details>}
      {versions && <JournalBrowser date={date} onChoose={selectRevision} />}
      {versions && selectedRevision && <div className="asset-week-notice">
        <h2>查看修订 · {new Date(selectedRevision.created_at).toLocaleString("zh-CN")}</h2>
        <p className="asset-week-user-text">{selectedRevision.judgment || "未写判断"}</p>
        <p className="asset-week-user-text">下周待核验：{selectedRevision.next_question || "未填写"}</p>
        <p className="asset-week-user-text">人工核验：{ASSESSMENTS[selectedRevision.assessment as keyof typeof ASSESSMENTS] ?? "未标记"}；{selectedRevision.assessment_note || "未填写说明"}</p>
      </div>}
    </section>
  </>;
}

function JournalBrowser({ date, onChoose }: { date?: string; onChoose: (entry: JournalEntry) => void }) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<JournalList | null>(null);
  const [error, setError] = useState("");
  const [reload, retry] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    const endpoint = date ? "/week-journal/" + date + "/revisions?offset=" + offset
      : "/week-journal?q=" + encodeURIComponent(query) + "&offset=" + offset;
    setResult(null);
    setError("");
    apiGet<JournalList>(endpoint, { signal: controller.signal }).then(value => {
      if (active) setResult(value);
    }).catch((reason: unknown) => {
      if (active) setError(controller.signal.aborted ? "本地列表读取超时。" : reasonText(reason));
    }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [date, query, offset, reload]);
  return <div className="asset-week-notice">
    {!date && <form className="asset-week-toolbar" onSubmit={event => {
      event.preventDefault(); setQuery(input.trim()); setOffset(0); retry(value => value + 1);
    }}>
      <label>搜索周复盘<input value={input} maxLength={80} onChange={event => setInput(event.target.value)} /></label>
      <button type="submit" className="asset-week-button asset-week-secondary">搜索</button>
    </form>}
    {!result && !error && <p role="status">正在读取列表…</p>}
    {error && <p role="alert">{error} <button className="asset-week-link" type="button" onClick={() => retry(value => value + 1)}>重试</button></p>}
    {result && <>
      {result.items.length ? <ul className="asset-week-record-list">{result.items.map(item => <li key={item.revision}>
        <button type="button" className="asset-week-link" onClick={() => onChoose(item)}>
          {date ? new Date(item.created_at).toLocaleString("zh-CN") + " · " + item.revision.slice(0, 8) : item.week_end}
          {" · "}{(item.judgment || item.next_question || item.assessment_note || "人工核验").slice(0, 52)}
        </button>
      </li>)}</ul> : <p>没有匹配的本地记录。</p>}
      {offset > 0 && <button type="button" className="asset-week-link" onClick={() => setOffset(offset - 30)}>上一页</button>}
      {result.more && <button type="button" className="asset-week-link" onClick={() => setOffset(offset + 30)}>下一页</button>}
    </>}
  </div>;
}
