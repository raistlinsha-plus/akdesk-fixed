import type { HealthItem } from "./types";

export function researchAvailability(items: HealthItem[]) {
  return {
    ready: items.filter((item) => item.research_status === "ready").length,
    limited: items.filter((item) => item.research_status === "limited").length,
    blocked: items.filter((item) => item.research_status === "blocked").length,
    unchecked: items.filter((item) => item.research_status === "unchecked").length,
  };
}

export function marketSessionLabel(items: HealthItem[], page: string): string {
  if (page === "macro" || page === "sovereign" || page === "chart-lab") {
    return "宏观数据按发布更新";
  }
  if (page === "fx") {
    const fx = items.find((item) => item.adapter === "fx_pairs");
    if (fx?.market_status === "trading") return "全球外汇交易中";
    if (fx?.market_status === "non_trading_day") return "全球外汇休市";
    return "全球外汇状态待检查";
  }
  const domestic = items.filter((item) => !item.adapter.startsWith("fx_"));
  if (domestic.some((item) => item.market_status === "trading")) {
    return "主要市场交易中";
  }
  if (domestic.some((item) => item.market_status === "session_break")) {
    return "主要市场午间休市";
  }
  if (domestic.some((item) => item.market_status === "pre_open")) {
    return "主要市场未开盘";
  }
  if (domestic.some((item) => item.market_status === "closed")) {
    return "主要市场已收盘";
  }
  if (domestic.some((item) => item.market_status === "non_trading_day")) {
    return "主要市场非交易日";
  }
  return "本地研究模式";
}
