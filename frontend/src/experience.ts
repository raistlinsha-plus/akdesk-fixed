import { CROSS_ASSETS, commonComparison } from "./crossAssets";
import { APP_VERSION, REPOSITORY_URL } from "./release";

export const EXPERIENCE_DATES = ["2026-07-30", "2026-07-31", "2026-08-03"] as const;
export const EXPERIENCE_ASSETS = [
  { ...CROSS_ASSETS[5], prices: [4, 4.04, 4.08] },
  { ...CROSS_ASSETS[6], prices: [4.1, null, 4.059] },
] as const;
export const EXPERIENCE_SOURCE = "AKDesk 内置固定合成样例";
export const EXPERIENCE_NOTE_LIMIT = 600;

const toSeries = (prices: readonly (number | null)[]) => prices.flatMap((close, index) =>
  close === null ? [] : [{ date: EXPERIENCE_DATES[index], close }]);
const comparison = commonComparison(toSeries(EXPERIENCE_ASSETS[0].prices), toSeries(EXPERIENCE_ASSETS[1].prices));
if (!comparison) throw new Error("首任务合成样例至少需要两个共同日期");
export const EXPERIENCE_COMPARISON = comparison;

export function experienceChange(series: number[]): string {
  const change = series[series.length - 1] - series[0];
  return `${change > 0 ? "+" : ""}${change.toFixed(2)}%`;
}

export function experienceMarkdown(note: string): string {
  const safe = note.trim().slice(0, EXPERIENCE_NOTE_LIMIT)
    .replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .split(/\r?\n/).map((line) => `> ${line}`).join("\n");
  return [
    "# AKDesk · 股债金汇首任务底稿", "",
    "**合成样例 · 非真实行情 · 非投资建议**", "",
    `来源：${EXPERIENCE_SOURCE}；AKDesk v${APP_VERSION}。`,
    `共同观测日期：${EXPERIENCE_COMPARISON.dates.join("、")}。`, "",
    `- ${EXPERIENCE_ASSETS[0].name}：共同区间价格变化 ${experienceChange(EXPERIENCE_COMPARISON.left)}。`,
    `- ${EXPERIENCE_ASSETS[1].name}：共同区间价格变化 ${experienceChange(EXPERIENCE_COMPARISON.right)}。`,
    "- 2026-07-31 的宽基 ETF 观测刻意留空；该日不纳入比较，不补零。",
    "- 仅比较共同日期的合成价格，不代表总回报、相同观测时点或因果关系。", "",
    "## 我的观察", safe || "> 尚未填写", "",
    "本文件由用户主动导出；未写入研究库，未发送反馈。", "",
  ].join("\n");
}

export const EXPERIENCE_FEEDBACK_OPTIONS = {
  result: { browsed: "只浏览了样例", completed: "已完成样例并打开底稿", blocked: "样例中途遇到阻碍" },
  install: { unknown: "未说明", "not-tried": "尚未安装", started: "本地版已启动", blocked: "安装或启动遇到阻碍" },
  reuse: { unknown: "尚未到复访时点或不确定", returned: "实际在七日内再次使用", "not-returned": "已观察七日，未再次使用" },
  interest: { unknown: "未选择", weekly: "跨资产周复盘", stock: "转债与正股联动", holdings: "本地持仓复盘" },
} as const;
export type ExperienceFeedbackField = keyof typeof EXPERIENCE_FEEDBACK_OPTIONS;

function allowedLabel(field: ExperienceFeedbackField, value: string, fallback: string) {
  const options: Record<string, string> = EXPERIENCE_FEEDBACK_OPTIONS[field];
  return Object.hasOwn(options, value) ? options[value] : fallback;
}

export function experienceFeedback(
  surface: "online" | "local",
  selections: Record<ExperienceFeedbackField, string>,
) {
  const fields = {
    version: `v${APP_VERSION}`,
    surface: surface === "local" ? "本地合成体验" : "静态在线演示",
    result: allowedLabel("result", selections.result, "未填写"),
    install: allowedLabel("install", selections.install, "未说明"),
    reuse: allowedLabel("reuse", selections.reuse, "尚未到复访时点或不确定"),
    interest: allowedLabel("interest", selections.interest, "未选择"),
  };
  const params = new URLSearchParams({ template: "experience_feedback.yml", title: `[Experience] v${APP_VERSION} 三分钟首任务`, ...fields });
  return {
    preview: Object.entries(fields).map(([key, value]) => `${key}: ${value}`).join("\n"),
    url: `${REPOSITORY_URL}/issues/new?${params.toString()}`,
  };
}
