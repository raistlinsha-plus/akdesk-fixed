import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Download, RefreshCcw, ArrowRight } from "lucide-react";
import { apiGet } from "../api";
import { Panel, WatchButton } from "../components/UI";
import { WorkflowCapture } from "../components/WorkflowCapture";
import { CROSS_ASSETS, CROSS_NOTICE, commonComparison, crossNumber, crossReferenceMarkdown, historyChange, syntheticHistory, syntheticQuotes, type CrossHistory, type CrossQuote, type CrossQuotes } from "../crossAssets";
import { downloadScenarioFile } from "../scenarios";
import { shanghaiDate } from "../researchUtils";
import { APP_VERSION } from "../release";
import { feedbackUrl } from "../feedback";
import "./crossAssets.css";

const LineChart = lazy(()=>import("../components/Charts").then(module=>({default:module.LineChart})));
async function read<T>(path:string, signal:AbortSignal):Promise<T> { return apiGet<T>(path,{signal}); }

function EtfPicker({synthetic,onLoaded,onChoose}:{synthetic:boolean;onLoaded:(quote:CrossQuote)=>void;onChoose:(id:string)=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const request=useRef<AbortController|null>(null),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;request.current?.abort();};},[]);
  async function load(id:string){
    if(busy)return;
    onChoose(id);
    setBusy(true);setError("");const controller=new AbortController();request.current=controller;
    const timeout=setTimeout(()=>controller.abort(),25_000);
    try{
      const result=synthetic?{data:syntheticQuotes().filter(item=>item.id===id)}:await read<CrossQuotes>(`/cross-assets/etf?asset_id=${encodeURIComponent(id)}`,controller.signal);
      if(mounted.current){const quote=result.data.find(item=>item.id===id);if(!quote)throw new Error("资料不匹配");onLoaded(quote);if(quote.price===null)setError("未取得有效日线；可能处于来源故障或冷却，未用实时价/净值补齐。");}
    }catch{if(mounted.current)setError("ETF日线读取失败或超时，请稍后重试；不会轮换接口绕过限制。");}
    finally{clearTimeout(timeout);if(mounted.current)setBusy(false);}
  }
  return <Panel title="精选ETF · 按需盘后观察" eyebrow="FOUR EXAMPLES · NOT A RANKING"><div className="cross-detail"><p>黄金、宽基、红利、国债各一个观察示例，不是优选排名或投资建议。只读取点选ETF的日线，不扫描全市场。未取得同一时点可靠净值，不计算折溢价或跟踪误差；不复权价格变化不是含分红和费用的投资回报。北京时间16:30前不采用当日日线。</p><div className="cross-controls">{CROSS_ASSETS.filter(item=>item.kind==="etf").map(item=><button className="secondary-button" key={item.id} disabled={busy} onClick={()=>void load(item.id)}>载入 {item.name}</button>)}</div>{busy?<p role="status">正在读取所选ETF日线…</p>:null}{error?<p role="alert">{error}</p>:null}<p>载入后选择报价卡，按需查看日线、加入自选或保存查询引用。源冷却与转债东方财富通道共享，不因切换ETF而解除。</p></div></Panel>;
}

export function CrossAssetPage({refreshSeed = 0, initialQuery = "", navigate, synthetic = false}:{refreshSeed?:number;initialQuery?:string;navigate?:(page:string,query?:string)=>void;synthetic?:boolean}) {
  const [quotes,setQuotes]=useState<CrossQuote[]>(synthetic ? syntheticQuotes() : []);
  const [loading,setLoading]=useState(!synthetic), [error,setError]=useState("");
  const [reload,setReload]=useState(0), [selected,setSelected]=useState(CROSS_ASSETS.some(item=>item.id===initialQuery) ? initialQuery : "");
  const [history,setHistory]=useState<CrossHistory|null>(null), [historyLoading,setHistoryLoading]=useState(false), [historyError,setHistoryError]=useState("");
  const [windowSize,setWindowSize]=useState(60), [compare,setCompare]=useState(""), [other,setOther]=useState<CrossHistory|null>(null);
  const [note,setNote]=useState(""), [brief,setBrief]=useState(false);
  const historyEpoch=useRef(0);
  const [routeError,setRouteError]=useState("");
  useEffect(()=>()=>{historyEpoch.current++;},[]);
  useEffect(()=>{
    if(synthetic || !CROSS_ASSETS.some(item=>item.id===initialQuery&&item.kind==="etf"))return;
    let active=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),25_000);setRouteError("");
    read<CrossQuotes>(`/cross-assets/etf?asset_id=${encodeURIComponent(initialQuery)}`,controller.signal).then(value=>{
      const quote=value.data.find(item=>item.id===initialQuery);
      if(active&&quote)setQuotes(current=>[...current.filter(item=>item.id!==quote.id),quote]);
    }).catch(()=>{if(active)setRouteError("自选ETF日线暂不可用，可在下方点选重试；未自动加载其他ETF。");}).finally(()=>clearTimeout(timeout));
    return()=>{active=false;controller.abort();clearTimeout(timeout);};
  },[initialQuery,synthetic]);
  useEffect(()=>{if (CROSS_ASSETS.some(item=>item.id===initialQuery)) setSelected(initialQuery);},[initialQuery]);
  useEffect(()=>{
    if(synthetic) return;
    let active=true, busy=false;
    let controller:AbortController|null=null;
    let timeout:ReturnType<typeof setTimeout>|undefined;
    async function load(){
      if(busy || document.visibilityState === "hidden") return;
      busy=true; controller=new AbortController(); setLoading(true); setError("");
      timeout=setTimeout(()=>controller?.abort(),25_000);
      const results=await Promise.allSettled([read<CrossQuotes>("/cross-assets/quotes?kind=index",controller.signal),read<CrossQuotes>("/cross-assets/quotes?kind=gold",controller.signal)]);
      if(active){
        const rows=results.flatMap(item=>item.status==="fulfilled"?item.value.data:[]);
        const problems=results.flatMap((item,index)=>{
          const label=index===0?"指数":"黄金";
          if(item.status==="rejected")return [`${label}：读取失败或超时`];
          return item.value.data.some(row=>row.price!==null&&Number.isFinite(row.price))?[]:[`${label}：暂未取得有效报价`];
        });
        setQuotes(current=>[...rows,...current.filter(item=>item.kind==="etf")]);
        setError(problems.join("；"));
        setLoading(false);
      }
      clearTimeout(timeout);busy=false;
    }
    void load(); const timer=setInterval(()=>void load(),300_000); const visible=()=>{if(document.visibilityState==="visible")void load();}; document.addEventListener("visibilitychange",visible);
    return()=>{active=false;controller?.abort();clearTimeout(timeout);clearInterval(timer);document.removeEventListener("visibilitychange",visible);};
  },[refreshSeed,reload,synthetic]);
  useEffect(()=>{setHistory(null);setOther(null);setCompare("");setHistoryError("");setHistoryLoading(false);historyEpoch.current++;},[selected]);
  const asset=quotes.find(item=>item.id===selected);
  async function loadHistory(id:string, comparison=false){
    const epoch=historyEpoch.current; setHistoryLoading(true);setHistoryError("");
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),25_000);
    try{
      const chosen=quotes.find(item=>item.id===id);
      const value=synthetic && chosen ? syntheticHistory(chosen) : await read<CrossHistory>(`/cross-assets/history?asset_id=${encodeURIComponent(id)}`,controller.signal);
      if(epoch===historyEpoch.current){if(comparison)setOther(value);else setHistory(value);}
    }catch{if(epoch===historyEpoch.current)setHistoryError("日线暂不可用或读取超时，请稍后重试；没有改用盘中报价补齐。");}
    finally{clearTimeout(timeout);if(epoch===historyEpoch.current)setHistoryLoading(false);}
  }
  const sliced=history?.data.slice(-windowSize)??[];
  const compared=history&&other?commonComparison(sliced,other.data):null;
  return <div className="page-stack cross-assets-page">
    <header className="cross-assets-heading"><div><span className="eyebrow">CROSS-ASSET · OBSERVE BEFORE YOU CONCLUDE</span><h1>股债金汇观察</h1><p>黄金与四个宽基指数，连接原有固收、外汇和研究工作流。</p></div><button className="secondary-button" disabled={loading||synthetic} onClick={()=>setReload(value=>value+1)}><RefreshCcw size={14}/>重新读取</button></header>
    <p className="cross-policy" role="note">{synthetic ? "固定 2026-08-03 合成体验，不连接行情/AI/研究库；允许导出本页合成样例。" : CROSS_NOTICE}</p>
    {navigate && !synthetic ? <button className="text-button" onClick={() => navigate("cross-asset-week")}>打开股债金汇周复盘 <ArrowRight size={14} /></button> : null}
    <nav className="cross-context-links" aria-label="原有市场模块">{[["money","资金面"],["curves","收益率曲线"],["futures","国债期货"],["fx","人民币与外汇"]].map(([page,label])=><button className="text-button" key={page} disabled={!navigate} onClick={()=>navigate?.(page)}>{label}<ArrowRight size={13}/></button>)}<button className="secondary-button" onClick={()=>setBrief(value=>!value)}>{brief?"收起观察底稿":"整理跨资产观察底稿"}</button></nav>
    {loading?<p role="status">正在按需读取公开源；每5分钟最多更新一次，后台标签页暂停轮询。</p>:null}
    {error?<div className="cross-policy"><p role="alert">{error}。缺失不代表价格为零；仍可查看其他来源。先检查数据健康，稍后再重新读取。</p>{navigate?<div className="cross-controls"><button className="secondary-button" onClick={()=>navigate("health")}>查看数据健康</button><button className="secondary-button" onClick={()=>navigate("help","start")}>改用明确标记的合成首任务</button></div>:null}</div>:null}
    <EtfPicker synthetic={synthetic} onChoose={id=>setSelected(id)} onLoaded={quote=>{setQuotes(current=>[...current.filter(item=>item.id!==quote.id),quote]);}}/>
    {routeError?<p role="alert">{routeError}</p>:null}
    <section className="cross-quote-grid" aria-label="黄金与指数报价">{quotes.map(item=><article key={item.id} className={selected===item.id?"selected":""}>
      <div className="cross-quote-title"><button onClick={()=>setSelected(item.id)} aria-pressed={selected===item.id}>{item.name}</button>{!synthetic?<WatchButton objectType={item.kind} objectId={item.id} name={item.name}/>:null}</div>
      <strong className="cross-price">{crossNumber(item.price)}<small>{item.unit}</small></strong><span>相对源前收盘 {crossNumber(item.change_pct)}%</span>
      <small>{item.demo?"合成样例":item.state==="stale"?"旧缓存 · 来源故障/冷却":item.state==="unavailable"?"来源不可用":item.quote_kind==="last_daily"?"最近可得盘后日线 · 非实时":"公开源报价 · 延时未知"}</small><small>观测 {item.observation_time??"未提供，不能视作今日实时"}</small><small>抓取 {item.fetched_at}</small>
      <details><summary>来源与可信边界</summary><p>{item.source}</p>{item.source_url?<a href={item.source_url} target="_blank" rel="noreferrer">查看原始页面</a>:null}{item.warnings.map(warning=><p key={warning}>{warning}</p>)}</details>
    </article>)}</section>
    {asset?<Panel title={`${asset.name} · 日线观察`} eyebrow="DAILY OBSERVATIONS · NOT TOTAL RETURN"><div className="cross-detail">
      <p>{asset.kind==="gold"?"Au99.99 是交易所黄金现货，不是金店零售、期货或黄金ETF价格；夜盘与交易日不能套用股票日历。" :asset.kind==="etf"?"ETF展示不复权盘后价格，不包含分红再投资和费用；没有可靠净值时不计算折溢价。":"指数价格变化不含所有分红再投资因素，不等于可实现的投资总回报。"}</p>
      <div className="cross-controls"><button className="secondary-button" disabled={historyLoading} onClick={()=>void loadHistory(asset.id)}>{historyLoading?"正在读取日线…":"按需载入／重读日线"}</button><label>展示范围<select value={windowSize} onChange={event=>setWindowSize(Number(event.target.value))}><option value={22}>近1个月</option><option value={60}>近3个月</option><option value={250}>近1年</option></select></label></div>
      {historyError?<p role="alert">{historyError}</p>:null}{history?<><p>{history.demo?"合成样例":`日线状态 ${history.state}`} · 样本 {history.data.length} 条 · 最后日期 {history.data.at(-1)?.date??"未提供"}</p><p>1／5／20个观测期价格变化：{[1,5,20].map(period=>`${crossNumber(historyChange(history.data,period))}%`).join(" / ")}。{history.notice}</p>
        {history.data.length?<Suspense fallback={<p role="status">正在载入图表…</p>}><LineChart categories={sliced.map(row=>row.date)} series={[{name:asset.name,values:sliced.map(row=>row.close)}]} unit={asset.unit}/></Suspense>:<p>没有有效日线；空值不补零。</p>}
        <label>共同日期比较（基期100）<select value={compare} disabled={historyLoading} onChange={event=>{setCompare(event.target.value);setOther(null);if(event.target.value)void loadHistory(event.target.value,true);}}><option value="">不比较</option>{quotes.filter(item=>item.kind===asset.kind&&item.id!==asset.id).map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        {other?(compared?<><p>仅共同日期 {compared.dates[0]} 至 {compared.dates.at(-1)}，{compared.dates.length}个观测；不填充缺失日，不解释因果。</p><Suspense fallback={<p>正在载入比较图…</p>}><LineChart categories={compared.dates} series={[{name:asset.name,values:compared.left},{name:other.asset.name,values:compared.right}]} unit="（基期100）"/></Suspense></>:<p>共同有效日期不足2条，不绘制比较。</p>):null}
      </>:<p>日线按需载入，不在后台扫描全部资产。</p>}
      {!synthetic?<WorkflowCapture source={{kind:"asset_reference",asset:{id:asset.id,name:asset.name}}} navigate={navigate}/>:null}
    </div></Panel>:<p className="cross-hint">选择一张报价卡，再按需载入日线、比较或保存查询引用。</p>}
    {brief?<Panel title="股债金汇观察底稿" eyebrow="YOUR NOTES · EXPLICIT EXPORT"><div className="cross-detail"><p>先从上方进入原有资金、曲线、期货和外汇模块核验，再写自己的观察。本版不将新行情写进旧日报归档；底稿导出仅包含查询引用与人工文字，合成模式除外。</p><label>自己的观察、分歧与下一步<textarea value={note} maxLength={8000} rows={5} onChange={event=>setNote(event.target.value)} placeholder="不要粘贴密钥、未公开研究或无权保存的数据。"/></label><button className="secondary-button" onClick={()=>downloadScenarioFile(crossReferenceMarkdown(quotes,note,synthetic),synthetic?"AKDesk-股债金汇-合成样例.md":"AKDesk-跨资产查询引用.md")}><Download size={14}/>{synthetic?"下载合成观察底稿":"下载查询引用与人工备注"}</button>{!synthetic?<WorkflowCapture source={{kind:"brief_note",reportDate:shanghaiDate(),note}} navigate={navigate}/>:null}</div></Panel>:null}
    <details className="cross-policy"><summary>主动反馈体验（先看发送范围）</summary><p>只在GitHub链接中预填版本、页面和模式，不携带备注、日线、项目或个人路径。打开GitHub后仍需你检查并自行提交；访问/Star不算任务完成或留存。</p><pre>version: v{APP_VERSION}{"\n"}page: cross-assets{"\n"}mode: {synthetic?"demo":"unknown"}</pre><a href={feedbackUrl("feature","cross-assets",synthetic?"demo":"unknown")} target="_blank" rel="noreferrer">前往GitHub分享任务、卡点与再次使用情况</a></details>
  </div>;
}
