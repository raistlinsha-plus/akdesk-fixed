import type { BriefDocument } from "../brief";

export const DEMO_DATE = "2026-08-03";
export const DEMO_OBSERVATION = "2026-08-03T15:30:00+08:00";
export const DEMO_SOURCE = "AKDesk 内置合成样例";

export const DEMO_CURVE = {
  tenors: ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "30Y"],
  government: [1.32, 1.36, 1.4, 1.48, 1.55, 1.64, 1.72, 1.8, 1.98],
  previous: [1.34, 1.37, 1.42, 1.49, 1.56, 1.66, 1.73, 1.82, 1.97],
  policy: [1.42, 1.48, 1.55, 1.62, 1.69, 1.78, 1.86, 1.94, 2.14],
};

export interface DemoSignal {
  id: string;
  category: "funding" | "curve" | "future";
  categoryLabel: string;
  title: string;
  summary: string;
  value: string;
  direction: "up" | "down";
  label: string;
  evidence: string;
}

export const DEMO_SIGNALS: DemoSignal[] = [
  {
    id: "funding",
    category: "funding",
    categoryLabel: "资金",
    title: "短端资金分化，隔夜利率下行",
    summary: "Shibor O/N 较样例前值下降 2.10 BP，1W 上升 1.20 BP。观察不同期限，避免用单个指标概括整体资金面。",
    value: "−2.10 BP",
    direction: "down",
    label: "Shibor O/N · 样例变化",
    evidence: "样例 O/N 1.4250%，前值 1.4460%；差值 −0.0210 个百分点，即 −2.10 BP。所有数值为固定合成数据。",
  },
  {
    id: "curve",
    category: "curve",
    categoryLabel: "曲线",
    title: "10Y 国债收益率下行 2.00 BP",
    summary: "样例 10Y 收益率为 1.8000%，10Y–1Y 期限利差为 40.00 BP。可继续查看各期限与前值的对应变化。",
    value: "1.8000%",
    direction: "down",
    label: "10Y 国债 · 样例水平",
    evidence: "样例 10Y 1.8000%，前值 1.8200%；1Y 1.4000%。期限利差为 (1.8000 − 1.4000) × 100 = 40.00 BP。",
  },
  {
    id: "future",
    category: "future",
    categoryLabel: "期货",
    title: "T 合约上涨，超长端方向不同",
    summary: "样例 T 合约上涨 0.12%，TL 下跌 0.05%。保留不同期限的分歧，再决定需要核验什么。",
    value: "+0.12%",
    direction: "up",
    label: "T 合约 · 样例涨跌幅",
    evidence: "样例 T 108.055、涨跌幅 +0.12%；TL 118.920、涨跌幅 −0.05%。此处仅演示跨期限比较，不包含交易信号。",
  },
];

export const DEMO_BRIEF: BriefDocument = {
  date: DEMO_DATE,
  generatedAt: DEMO_OBSERVATION,
  marketStatus: "收盘样例 · 固定场景",
  headline: "资金期限分化，10Y 收益率下行，超长端期货方向不同",
  mode: "example",
  funding: {
    tone: "隔夜下行、1W 上行，需结合期限观察",
    averageChangeBp: -0.45,
    items: [
      { name: "Shibor O/N", value: 1.425, changeBp: -2.1 },
      { name: "Shibor 1W", value: 1.617, changeBp: 1.2 },
    ],
  },
  curve: {
    tenYear: 1.8,
    tenYearChangeBp: -2,
    spreadsBp: { "10Y-1Y": 40, "10Y-5Y": 16, "30Y-10Y": 18 },
  },
  futures: [
    { product: "TS", contract: "TS 示例合约", price: 102.218, changePct: 0.03 },
    { product: "TF", contract: "TF 示例合约", price: 105.48, changePct: 0.08 },
    { product: "T", contract: "T 示例合约", price: 108.055, changePct: 0.12 },
    { product: "TL", contract: "TL 示例合约", price: 118.92, changePct: -0.05 },
  ],
  sources: [
    { adapter: "money_rates", label: "资金样例", source: DEMO_SOURCE, observationTime: DEMO_OBSERVATION, fetchedAt: DEMO_OBSERVATION, dataState: "demo", trustLevel: "unavailable", demo: true },
    { adapter: "yield_curves", label: "曲线样例", source: DEMO_SOURCE, observationTime: DEMO_OBSERVATION, fetchedAt: DEMO_OBSERVATION, dataState: "demo", trustLevel: "unavailable", demo: true },
    { adapter: "treasury_futures", label: "期货样例", source: DEMO_SOURCE, observationTime: DEMO_OBSERVATION, fetchedAt: DEMO_OBSERVATION, dataState: "demo", trustLevel: "unavailable", demo: true },
  ],
  notes: [
    "本简报使用 AKDesk 内置合成样例，固定日期为 2026-08-03，不代表当日或当前真实行情。",
    "演示仅展示组织变化、核验数据和形成底稿的流程；真实使用需在本地版核对来源、观测时间与数据状态。",
  ],
};
