import { WEEK_SERIES, weeklyWindow } from "./crossAssetWeek";

export const ASSESSMENTS = {
  supported: "支持",
  partial: "部分支持",
  unsupported: "不支持",
  pending: "仍待核验",
} as const;
export type Assessment = keyof typeof ASSESSMENTS | "";
export interface JournalContent {
  judgment: string;
  next_question: string;
  assessment: Assessment;
  assessment_note: string;
  previous_revision: string | null;
}
export interface JournalEntry extends JournalContent {
  week_end: string;
  revision: string;
  created_at: string;
}
export interface JournalState {
  week_end: string;
  current: JournalEntry | null;
  previous: JournalEntry | null;
  assessed: JournalEntry | null;
}
export interface JournalDraft extends JournalContent {
  expected_revision: string | null;
}
export interface JournalList {
  items: JournalEntry[];
  more: boolean;
}

export const EMPTY_JOURNAL: JournalDraft = {
  expected_revision: null, judgment: "", next_question: "", assessment: "",
  assessment_note: "", previous_revision: null,
};

export function fromEntry(entry: JournalEntry | null): JournalDraft {
  return entry ? {
    expected_revision: entry.revision, judgment: entry.judgment, next_question: entry.next_question,
    assessment: entry.assessment, assessment_note: entry.assessment_note,
    previous_revision: entry.previous_revision,
  } : { ...EMPTY_JOURNAL };
}

function quote(value: string): string {
  return (value.trim() || "未记录").replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replace(/[\\`*_{}[\]()#!|]/g, "\\$&")
    .split(/\r\n|\n|\r/).map(line => "> " + line).join("\n");
}

export function journalMarkdown(
  entry: JournalEntry, previous: JournalEntry | null, sample = false,
): string {
  const { start, previousStart, previousEnd } = weeklyWindow(entry.week_end);
  return [
    "# AKDesk · 连续周复盘",
    "",
    sample ? "**固定合成样例 · 非真实行情**" : "用户自撰记录与查询引用 · 不是历史行情快照。",
    "",
    "复盘区间：" + start + " 至 " + entry.week_end,
    "保存时间：" + entry.created_at + " · 修订 " + entry.revision.slice(0, 8),
    "",
    "## 上一周 · " + previousStart + " 至 " + previousEnd,
    "",
    ...(previous ? [quote(previous.judgment), "", "当时的待核验事项：", quote(previous.next_question),
      "", "引用修订：" + previous.revision.slice(0, 8)] :
      [entry.previous_revision ? "原核验所引用的修订已不可用。" : "尚无上一周记录。"]),
    "",
    "## 本次人工核验",
    "",
    (entry.assessment ? ASSESSMENTS[entry.assessment] : "未标记") + " · 用户判断，不代表数据已验证。",
    quote(entry.assessment_note),
    "",
    "## 本周判断",
    "",
    quote(entry.judgment),
    "",
    "## 下周待核验",
    "",
    quote(entry.next_question),
    "",
    "## 查询引用",
    "",
    ...(sample ? ["- AKDesk 两周合成案例；不调用行情源。"] : WEEK_SERIES.map(spec =>
      "- " + spec.name + "：[" + spec.source + "](" + spec.url + ")；" + spec.method + "。")),
    "",
    "不包含行情值、派生变化或来源观测日期。不构成投资建议。",
    "",
  ].join("\n");
}
