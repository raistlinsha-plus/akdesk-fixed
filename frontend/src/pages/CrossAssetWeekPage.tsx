import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Download, RefreshCcw } from "lucide-react";
import {
  SAMPLE_END, SAMPLE_WEEK, WEEK_NOTE_LIMIT, WEEK_SERIES, formatWeekChange,
  lastCompletedFriday, readWeekSeries, shiftWeekDate, validWeekDate,
  weekMarkdown, weeklyChange, weeklyWindow,
  type WeekDraft, type WeekRows, type WeekResult, type WeekSeries, type WeekSeriesId,
} from "../crossAssetWeek";
import { shanghaiDate } from "../researchUtils";
import { downloadScenarioFile } from "../scenarios";
import "./crossAssetWeek.css";

const STATES: Record<WeekResult["state"], string> = {
  latest: "已读取日线", cached: "内存缓存", stale: "旧缓存 · 来源可能不可用",
  local: "本地历史 · 未主动刷新上游", sample: "固定合成样例",
  "demo-only": "当前服务为演示模式",
  unavailable: "无可用真实序列", failed: "读取失败或超时",
  "not-read": "尚未读取",
};

type Pending = { controller: AbortController; timer: ReturnType<typeof setTimeout> };
type SourceLink = { page: string; query: string; date: string };
type Report = { end: string; rows: Partial<WeekRows> };

function cancelReads(reads: Map<WeekSeriesId, Pending>) {
  for (const { controller, timer } of reads.values()) {
    clearTimeout(timer);
    controller.abort();
  }
  reads.clear();
}

function gapMessage(row: WeekResult, missing: string) {
  if (row.state === "not-read") return "未请求这一项，不能判断区间是否缺数。";
  if (row.state === "failed") return "暂时未读到结果，不能判断该周是否缺数。可以只重读这项。";
  if (row.state === "demo-only") return "未使用演示值代替真实行情。可打开固定合成样例，或停止演示服务后启动正式版。";
  if (row.state === "unavailable") return "来源未返回可用真实日线。可到原模块核验，不自动换源。";
  if (row.state === "local") return `${missing}没有本地观测。可到原模块补充历史，再回来仅重读此项。`;
  return `${missing}没有有效观测，不跨期取值或补零。`;
}

export function CrossAssetWeekPage({ sample = false, navigate, draft, onDraftChange, onSource }: {
  sample?: boolean;
  navigate?: (page: string, query?: string) => void;
  draft?: WeekDraft | null;
  onDraftChange?: (draft: WeekDraft) => void;
  onSource?: (link: SourceLink) => void;
}) {
  const today = shanghaiDate();
  const earliest = shiftWeekDate(today, -90);
  const latest = shiftWeekDate(today, -1);
  const completedFriday = lastCompletedFriday(today);
  const [localDraft, setLocalDraft] = useState<WeekDraft>(() => ({
    date: sample ? SAMPLE_END : lastCompletedFriday(),
    notes: {},
  }));
  const selected = !sample && draft ? draft : localDraft;
  const date = selected.date;
  const note = selected.notes[date] ?? "";
  const saveDraft = !sample && onDraftChange ? onDraftChange : setLocalDraft;
  const [report, setReport] = useState<Report | null>(
    sample ? { end: SAMPLE_END, rows: SAMPLE_WEEK } : null,
  );
  const [downloadStatus, setDownloadStatus] = useState("");
  const requests = useRef(new Map<WeekSeriesId, Pending>());
  useEffect(() => {
    const active = requests.current;
    return () => cancelReads(active);
  }, []);

  const dateValid = validWeekDate(date) && date >= earliest && date <= latest;
  const current = report?.end === date ? report : null;
  const period = current ? weeklyWindow(current.end) : null;
  const cards = useMemo(() => current ? WEEK_SERIES.map(spec => {
    const row = current.rows[spec.id];
    return { spec, row, values: row ? weeklyChange(spec, row.points, date) : null };
  }) : [], [current, date]);
  const pendingCount = cards.filter(card => !card.row).length;
  const readyCount = cards.filter(card => card.values && card.values.change !== null).length;
  const unreadCount = cards.filter(card => card.row?.state === "not-read").length;
  const unavailableCount = cards.length - readyCount - pendingCount - unreadCount;
  const canExport = current !== null && pendingCount + unreadCount < WEEK_SERIES.length;
  const markdown = canExport ? weekMarkdown(date, current.rows, note, sample) : "";
  const reviewed = !current && WEEK_SERIES.find(spec => spec.id === selected.reviewedSource);

  function selectDate(next: string) {
    if (next === date) return;
    cancelReads(requests.current);
    setReport(null);
    setDownloadStatus("");
    saveDraft({ ...selected, date: next, reviewedSource: undefined });
  }

  function read(spec: WeekSeries) {
    if (sample || !dateValid || requests.current.has(spec.id)) return;
    const controller = new AbortController();
    const finish = (row: WeekResult) => {
      const pending = requests.current.get(spec.id);
      if (pending?.controller !== controller) return;
      requests.current.delete(spec.id);
      clearTimeout(pending.timer);
      setReport(previous => previous?.end === date
        ? { end: date, rows: { ...previous.rows, [spec.id]: row } }
        : previous);
    };
    const failure: WeekResult = { state: "failed", points: [] };
    const timer = setTimeout(() => { finish(failure); controller.abort(); }, 35_000);
    requests.current.set(spec.id, { controller, timer });
    void readWeekSeries(spec, controller.signal).then(finish, () => finish(failure));
  }

  function load() {
    if (sample || !dateValid || requests.current.size) return;
    setReport({ end: date, rows: {} });
    setDownloadStatus("");
    WEEK_SERIES.forEach(read);
  }

  function retry(spec: WeekSeries) {
    if (sample || !dateValid || requests.current.has(spec.id)) return;
    setReport(previous => {
      const rows: Partial<WeekRows> = previous?.end === date ? previous.rows : {
        stock: { state: "not-read", points: [] }, bond: { state: "not-read", points: [] },
        gold: { state: "not-read", points: [] }, fx: { state: "not-read", points: [] },
      };
      return { end: date, rows: { ...rows, [spec.id]: undefined } };
    });
    setDownloadStatus("");
    read(spec);
  }

  function openSource(spec: WeekSeries) {
    const query = "asset" in spec ? spec.asset : spec.id === "fx" ? spec.series : "";
    if (onSource) {
      saveDraft({ ...selected, reviewedSource: spec.id });
      onSource({ page: spec.page, query, date });
    } else {
      navigate?.(spec.page, query);
    }
  }

  function download() {
    if (!canExport) return;
    try {
      downloadScenarioFile(markdown, `AKDesk-股债金汇周复盘-${date}-${sample ? "合成样例" : "查询引用"}.md`);
      setDownloadStatus("已发起下载，请打开文件核对。");
    } catch {
      setDownloadStatus("下载未能发起，可打开预览复制。");
    }
  }

  return <section className="asset-week">
    <header>
      <span className="asset-week-kicker">CROSS-ASSET · WEEKLY REVIEW</span>
      <h1>股债金汇周复盘</h1>
      <p>用四条固定序列回顾一周，核验各自的观测日，再写下你的判断与下周关注点。</p>
    </header>
    <p className="asset-week-notice" role="note">{sample
      ? "固定合成样例 · 非真实行情。本样例不调用行情、研究或 AI 接口。黄金样例少一天、汇率缺前期值。"
      : "股、金按需读取既有日线；债、汇只读本地历史。未取得有效观测不补零，不拿实时价、抓取时间或合成样例替代。"}</p>
    {navigate ? <button className="asset-week-link" type="button" onClick={() => navigate("cross-asset-week", sample ? "" : "sample")}>
      {sample ? "返回本地真实数据入口" : "先看固定合成周复盘"} <ArrowRight size={14} aria-hidden="true" />
    </button> : null}
    {!sample ? <div className="asset-week-toolbar">
      <label>周结束日 <input type="date" value={date} min={earliest} max={latest}
        onChange={event => selectDate(event.target.value)} /></label>
      <div className="asset-week-dates-actions" aria-label="切换复盘日期" role="group">
        <button type="button" className="asset-week-button asset-week-secondary"
          disabled={!dateValid || date < shiftWeekDate(earliest, 7)} onClick={() => selectDate(shiftWeekDate(date, -7))}>前一周</button>
        <button type="button" className="asset-week-button asset-week-secondary"
          disabled={!dateValid || date > shiftWeekDate(latest, -7)} onClick={() => selectDate(shiftWeekDate(date, 7))}>后一周</button>
        <button type="button" className="asset-week-button asset-week-secondary"
          disabled={date === completedFriday} onClick={() => selectDate(completedFriday)}>最近已过周五</button>
      </div>
      <button type="button" className="asset-week-button" disabled={!dateValid || pendingCount > 0} onClick={load}>
        <RefreshCcw size={15} aria-hidden="true" />{pendingCount > 0 ? "正在读取…" : "读取本周"}
      </button>
      {reviewed && dateValid ? <button type="button" className="asset-week-button asset-week-secondary"
        onClick={() => retry(reviewed)}>仅重读{reviewed.name}</button> : null}
      {!dateValid ? <span role="alert">请选择过去 90 天内、早于今天的周结束日。</span> : null}
    </div> : null}
    {current && period ? <>
      <p className="asset-week-period">本期 {period.start} 至 {date} · 对照 {period.previousStart} 至 {period.previousEnd}。每项取各区间最后一个有效观测；日期不一定相同，不计算组合回报或归因。</p>
      <p className="asset-week-coverage" role="status">可计算 {readyCount}/4 项
        {pendingCount > 0 ? ` · ${pendingCount} 项读取中，其余可先看` : ""}
        {unavailableCount > 0 ? ` · ${unavailableCount} 项暂不可计算` : ""}
        {unreadCount > 0 ? ` · ${unreadCount} 项尚未读取` : ""}</p>
      <div className="asset-week-grid">
        {cards.map(({ spec, row, values }) => {
          const missing = !values?.previous && !values?.current ? "前期和本期" : !values?.previous ? "前期" : "本期";
          const missingLabel = !row ? "待返回" : row.state === "not-read" ? "未读取" : "缺失";
          const retryable = !sample && row && row.state !== "demo-only" &&
            (values?.change === null || row.state === "stale");
          return <article key={spec.id} className="asset-week-card" aria-busy={!row}>
            <div className="asset-week-card-top"><span>{spec.label}</span><small>{row ? STATES[row.state] : "正在读取"}</small></div>
            <h2>{spec.name}</h2>
            <strong>{formatWeekChange(values?.change ?? null, spec.changeUnit)}</strong>
            <p className="asset-week-dates">
              <span>前期观测 {values?.previous?.date ?? missingLabel}</span>
              <span>本期观测 {values?.current?.date ?? missingLabel}</span>
            </p>
            {row && values?.change === null ? <p>{gapMessage(row, missing)}</p> : null}
            <p>{spec.method}。{sample ? "来源：AKDesk 固定合成样例。" : `来源：${spec.source}。`}</p>
            {!sample ? <div className="asset-week-card-actions">
              {onSource || navigate ? <button className="asset-week-link" type="button" onClick={() => openSource(spec)}>
                到原模块核验 <ArrowRight size={14} aria-hidden="true" />
              </button> : null}
              {retryable ? <button className="asset-week-button asset-week-secondary" type="button"
                aria-label={`仅重读${spec.name}`} onClick={() => retry(spec)}>仅重读此项</button> : null}
            </div> : null}
          </article>;
        })}
      </div>
    </> : <p>选好日期后点击「读取本周」。切换日期不会自动取数，也不会沿用上一周的结果。</p>}
    {current || (dateValid && note) ? <div className="asset-week-draft">
      <h2>整理周复盘底稿</h2>
      <label>我的判断与下周待核验事项<textarea rows={4} value={note} maxLength={WEEK_NOTE_LIMIT}
        placeholder="例如：哪些方向一致？哪些因观测日不同还需要核验？"
        onChange={event => {
          saveDraft({ ...selected, notes: { ...selected.notes, [date]: event.target.value } });
          setDownloadStatus("");
        }} /></label>
      <p>{sample ? "样例文字只留在当前页面，导出可带合成变化。" : "按周保留在当前标签页的应用内存中；回到原模块再返回不会丢失，重载或关闭标签页后清空。导出仅含查询引用、所选区间及人工备注，不含观测日期、行情数值或派生变化。"}请勿把受限数据粘贴到备注。</p>
      <button type="button" className="asset-week-button" disabled={!canExport} onClick={download}><Download size={15} aria-hidden="true" />{sample ? "下载合成周复盘" : "下载查询引用底稿"}</button>
      {downloadStatus ? <p role="status">{downloadStatus}</p> : null}
      {canExport ? <details><summary>预览 Markdown</summary><pre>{markdown}</pre></details> : null}
    </div> : null}
  </section>;
}
