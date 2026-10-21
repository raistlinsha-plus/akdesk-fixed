import { useId, useRef, useState } from "react";
import { Check, Copy, Download, FileText, Printer } from "lucide-react";
import {
  briefMarkdown,
  briefMode,
  briefModeLabel,
  briefNumber,
  briefObservationRange,
  briefSourceState,
  briefTime,
  downloadBrief,
  printBriefElement,
  safeSourceUrl,
  type BriefDocument,
} from "../brief";
import "../brief.css";

export function OnePageBrief({
  document,
  compact = false,
  showActions = true,
  notes: controlledNotes,
  onNotesChange,
}: {
  document: BriefDocument;
  compact?: boolean;
  showActions?: boolean;
  notes?: string;
  onNotesChange?: (notes: string) => void;
}) {
  const [draftNotes, setDraftNotes] = useState("");
  const notes = controlledNotes ?? draftNotes;
  const setNotes = onNotesChange ?? setDraftNotes;
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const sheetRef = useRef<HTMLElement>(null);
  const noteId = useId();
  const mode = briefMode(document);

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(briefMarkdown(document, notes));
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <section className={`ak-brief${compact ? " ak-brief-compact" : ""}`} aria-label="一页固收简报">
      {showActions ? (
        <div className="ak-brief-toolbar">
          <div><FileText size={17} /><strong>一页固收简报</strong><span>带出处的研究底稿</span></div>
          <div className="ak-brief-actions">
            <button type="button" onClick={copyMarkdown}>
              {copyState === "copied" ? <Check size={15} /> : <Copy size={15} />}
              {copyState === "copied" ? "已复制" : "复制 Markdown"}
            </button>
            <button type="button" onClick={() => downloadBrief(document, notes)}><Download size={15} />下载 Markdown</button>
            <button type="button" onClick={() => sheetRef.current && printBriefElement(sheetRef.current)}><Printer size={15} />打印 / PDF</button>
          </div>
          {copyState !== "idle" ? <span className="ak-brief-copy-state" role="status">{copyState === "failed" ? "当前浏览器无法复制，请使用下载 Markdown。" : "已复制含来源与时点的 Markdown。"}</span> : null}
        </div>
      ) : null}
      <article className="ak-brief-sheet" ref={sheetRef}>
        <header className="ak-brief-header">
          <div><span className="ak-brief-eyebrow">AKDESK · FIXED INCOME BRIEF</span><h2>一页固收简报</h2></div>
          <div className="ak-brief-date"><strong>{document.date}</strong><span>{document.marketStatus}</span></div>
        </header>
        <div className={`ak-brief-mode ak-brief-mode-${mode}`}>{briefModeLabel(mode)}</div>
        <p className="ak-brief-headline">{document.headline}</p>
        <p className="ak-brief-generated">观测区间 {briefObservationRange(document)} · 生成于 {briefTime(document.generatedAt)} · 逐源时点见下方</p>

        <div className="ak-brief-columns">
          <section className="ak-brief-block">
            <h3>01 <span>资金面</span></h3>
            <div className="ak-brief-focus"><strong>{document.funding.tone}</strong><span>平均变动 {briefNumber(document.funding.averageChangeBp, 2, " BP", true)}</span></div>
            {document.funding.items.length ? (
              <table><thead><tr><th>指标</th><th>利率</th><th>变动</th></tr></thead><tbody>
                {document.funding.items.map((item) => <tr key={item.name}><td>{item.name}</td><td>{briefNumber(item.value, 4, "%")}</td><td>{briefNumber(item.changeBp, 2, " BP", true)}</td></tr>)}
              </tbody></table>
            ) : <p className="ak-brief-empty">暂无可用资金数据。</p>}
          </section>
          <section className="ak-brief-block">
            <h3>02 <span>收益率曲线</span></h3>
            <div className="ak-brief-focus"><strong>{briefNumber(document.curve.tenYear, 4, "%")}</strong><span>10Y 国债 · 日变动 {briefNumber(document.curve.tenYearChangeBp, 2, " BP", true)}</span></div>
            <table><thead><tr><th>期限利差</th><th>当前值</th></tr></thead><tbody>
              {["10Y-1Y", "10Y-5Y", "30Y-10Y"].map((key) => <tr key={key}><td>{key.replaceAll("-", "–")}</td><td>{briefNumber(document.curve.spreadsBp[key], 2, " BP")}</td></tr>)}
            </tbody></table>
          </section>
          <section className="ak-brief-block">
            <h3>03 <span>国债期货</span></h3>
            {document.futures.length ? (
              <table><thead><tr><th>合约</th><th>价格</th><th>日变动</th></tr></thead><tbody>
                {document.futures.map((item) => <tr key={item.product + item.contract}><td><strong>{item.product}</strong><small>{item.contract}</small></td><td>{briefNumber(item.price, 3)}</td><td>{briefNumber(item.changePct, 3, "%", true)}</td></tr>)}
              </tbody></table>
            ) : <p className="ak-brief-empty">暂无可用国债期货数据。</p>}
          </section>
        </div>

        <section className="ak-brief-review">
          <h3>待核验事项与数据缺口</h3>
          {document.notes.length ? <ul>{document.notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul> : <p>暂无额外缺口；使用前仍需核对来源与时点。</p>}
        </section>
        <section className="ak-brief-sources">
          <h3>来源与时点</h3>
          {document.sources.length ? <div className="ak-brief-source-list">{document.sources.map((source) => {
            const url = safeSourceUrl(source.sourceUrl);
            return <div className="ak-brief-source" key={source.adapter}>
              <div><strong>{source.label}</strong>{url ? <a href={url} target="_blank" rel="noreferrer">{source.source}</a> : <span>{source.source}</span>}<span>{briefSourceState(source)}</span></div>
              <p>观测 {briefTime(source.observationTime)} · 抓取 {briefTime(source.fetchedAt)}</p>
            </div>;
          })}</div> : <p className="ak-brief-empty">未提供逐源出处，当前简报待核验。</p>}
        </section>
        {notes.trim() ? <section className="ak-brief-user-notes"><h3>人工备注</h3><p>{notes.trim()}</p></section> : null}
        <footer className="ak-brief-footer"><span>AKDesk Fixed · {briefModeLabel(mode)}</span><span>仅供个人研究参考，不构成投资建议。</span></footer>
      </article>
      {showActions ? <div className="ak-brief-note-editor"><label htmlFor={noteId}>人工备注 <span>仅用于当前页面与导出，不自动保存</span></label><textarea id={noteId} value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={8000} rows={3} placeholder="补充自己的观察、分歧或下一步核验事项……" /></div> : null}
    </section>
  );
}
