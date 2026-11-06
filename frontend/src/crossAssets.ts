export type CrossKind = "index" | "gold" | "etf";
export interface CrossQuote {
  id: string; name: string; kind: CrossKind; symbol: string; unit: string; currency: string;
  price: number | null; previous_close: number | null; change_pct: number | null;
  source: string; source_url: string; terms_url: string; observation_time: string | null;
  fetched_at: string; state: string; quote_kind: string; demo: boolean; warnings: string[];
}
export interface CrossQuotes { data: CrossQuote[]; state: string; policy: { notice: string }; }
export interface CrossHistory { asset: CrossQuote; data: Array<{date: string; close: number}>; state: string; demo: boolean; notice: string; }
export const CROSS_ASSETS = [
  {id: "SSE:000001", name: "上证指数", kind: "index"},
  {id: "CSI:000300", name: "沪深300", kind: "index"},
  {id: "CSI:000905", name: "中证500", kind: "index"},
  {id: "SZSE:399006", name: "创业板指", kind: "index"},
  {id: "SGE:Au99.99", name: "黄金 Au99.99", kind: "gold"},
  {id: "SSE:518880", name: "黄金ETF（518880）", kind: "etf"},
  {id: "SSE:510300", name: "沪深300ETF（510300）", kind: "etf"},
  {id: "SSE:510880", name: "红利ETF（510880）", kind: "etf"},
  {id: "SSE:511010", name: "5年国债ETF（511010）", kind: "etf"},
] as const;
export const CROSS_NOTICE = "免费公开源预览 · 延时未知 · 数值只在内存展示，不落盘、不送AI。真实行情导出与研究只保存查询引用及人工备注；机构用途需另核验授权。";
export function crossNumber(value: number | null | undefined, digits = 2) { return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—"; }
export function historyChange(rows: CrossHistory["data"], periods: number): number | null {
  if (rows.length <= periods) return null;
  const current = rows[rows.length - 1].close, previous = rows[rows.length - 1 - periods].close;
  const change = current > 0 && previous > 0 ? (current / previous - 1) * 100 : NaN;
  return Number.isFinite(change) ? change : null;
}
export function commonComparison(a: CrossHistory["data"], b: CrossHistory["data"]) {
  const right = new Map(b.map(item => [item.date, item.close]));
  const common = a.filter(item => right.has(item.date) && item.close > 0 && right.get(item.date)! > 0);
  if (common.length < 2) return null;
  const leftValues=common.map(item=>item.close/common[0].close*100),rightValues=common.map(item=>right.get(item.date)!/right.get(common[0].date)!*100);
  return [...leftValues,...rightValues].every(Number.isFinite) ? {dates:common.map(item=>item.date),left:leftValues,right:rightValues} : null;
}
export function syntheticQuotes(): CrossQuote[] {
  return CROSS_ASSETS.map((item, index) => {
    const price = item.kind === "gold" ? 700 : item.kind === "etf" ? 4 + index * .1 : 3000 + index * 125;
    const previous = item.kind === "gold" ? 690 : item.kind === "etf" ? price - .01 : 2990 + index * 130;
    return {...item, symbol:item.id.split(":")[1], unit:item.kind === "gold" ? "元/克" : item.kind === "etf" ? "元/份" : "点", currency:"CNY", price, previous_close:previous, change_pct:(price/previous-1)*100, source:"AKDesk 手工合成样例", source_url:"", terms_url:"", observation_time:"2026-08-03", fetched_at:"2026-08-03T16:00:00+08:00", state:"demo", quote_kind:item.kind === "etf" ? "last_daily" : "synthetic", demo:true, warnings:["固定合成样例，不是任何交易所真实行情。"]};
  });
}
export function syntheticHistory(asset: CrossQuote): CrossHistory {
  const rows = Array.from({length:65}, (_, index) => {
    const day = new Date(Date.UTC(2026,7,3) - (64-index)*86_400_000);
    return {date:day.toISOString().slice(0,10),close:(asset.price ?? 100) * (1 + (index-64)*.0005)};
  }).filter(item=>![0,6].includes(new Date(item.date+"T00:00:00Z").getUTCDay()));
  return {asset,data:rows,state:"demo",demo:true,notice:"固定合成日线；不是投资回报或真实历史。"};
}
export function crossReferenceMarkdown(rows: CrossQuote[], note: string, synthetic: boolean) {
  const safe = note.trim().slice(0,8000).replaceAll("<", "&lt;").replaceAll(">", "&gt;").split("\n").map(line=>`> ${line}`).join("\n");
  return ["# AKDesk · 股债金汇观察底稿", "", synthetic ? "合成样例 · 非真实行情 · 样例日期 2026-08-03" : "查询引用版：不包含公开源行情数值、观测日期或历史快照；不是市场证据。", "", ...rows.map(item => synthetic ? `- ${item.name}：${crossNumber(item.price)} ${item.unit}；合成价格变动 ${crossNumber(item.change_pct)}%` : `- ${item.name}（${item.id}）：${item.source_url}；使用说明 ${item.terms_url}`), "", "## 人工备注（自行核验，不粘贴受限数据）", safe || "> 尚未填写", "", "此文件不自动保存到项目、不调用AI，不构成投资建议。黄金现货不是金店零售价，指数价格变化不是总回报，债券收益率变化不是债券价格回报。", ""].join("\n");
}
