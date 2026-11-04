import { DEMO_BRIEF, DEMO_CURVE, DEMO_DATE, DEMO_SIGNALS } from "./demo/demoData";
import creditFixture from "./scenarios/creditFixture.json";
import { APP_VERSION } from "./release";

export type ScenarioId = "daily" | "rates" | "credit";
export type EvidenceRole = "support" | "counter" | "pending";
export const EVIDENCE_ROLES: Record<EvidenceRole, string> = { support: "支持线索", counter: "反证 / 分歧", pending: "待核验" };
export const SCENARIOS: Array<{ id: ScenarioId; title: string; audience: string; question: string; outcome: string; steps: string[]; localPages: Array<{ page: string; label: string }> }> = [
  { id: "daily", title: "每日固收观察", audience: "先看市场 · 约 5 分钟", question: "今天哪些变化值得回到原始数据核验？", outcome: "一页带来源、时点与人工备注的合成简报", steps: ["观察变化", "核验数值", "带走简报"], localPages: [{ page: "market-changes", label: "市场变化" }, { page: "curves", label: "收益率曲线" }, { page: "report", label: "每日复盘" }] },
  { id: "rates", title: "跟踪一个利率观点", audience: "建立研究节奏 · 约 5 分钟", question: "长端下行是否得到资金与不同期限的共同支持？", outcome: "包含问题、支持线索、反证和下次验证的样例研究底稿", steps: ["提出问题", "区分证据", "安排验证"], localPages: [{ page: "projects", label: "研究项目" }, { page: "topics", label: "专题投研" }, { page: "weekly-review", label: "每周复盘" }] },
  { id: "credit", title: "信用观察与人工复核", audience: "理解信用门禁 · 约 5 分钟", question: "这三条单券资料，哪些还不能计算利差？", outcome: "三条合成单券的导入样例与人工复核清单", steps: ["预览合成资料", "检查覆盖门禁", "选择复核任务"], localPages: [{ page: "credit", label: "信用观察 R2" }, { page: "projects", label: "研究项目" }] },
];
export const SAMPLE_DATE = DEMO_DATE;
export const SAMPLE_BRIEF = DEMO_BRIEF;
export const SAMPLE_SIGNALS = DEMO_SIGNALS;
export const CREDIT_SAMPLE = creditFixture;
export const DEFAULT_QUESTION = "长端利率下行是否得到短端资金与曲线的共同支持？";
export const DEFAULT_REVIEW_DATE = "2026-08-10";
export const DEFAULT_TASK = "比较随后一周资金期限分化、曲线变化与超长端分歧；若不一致，重新检查初始假设。";
export const DEFAULT_ROLES: Record<string, EvidenceRole> = { funding: "counter", curve: "support", future: "pending" };

export function scenarioById(value: string) { return SCENARIOS.find(item => item.id === value); }

export function sampleCurvePoint(tenor: string) {
  const index = DEMO_CURVE.tenors.indexOf(tenor);
  if (index < 0) return null;
  return { tenor, value: DEMO_CURVE.government[index], previous: DEMO_CURVE.previous[index], changeBp: Number(((DEMO_CURVE.government[index] - DEMO_CURVE.previous[index]) * 100).toFixed(2)) };
}

export function validReviewDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value && value > SAMPLE_DATE;
}

function quoteText(value: string) {
  return value.trim().slice(0, 2000).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").split("\n").map(line => `> ${line.replace(/[\\`[\]()!*_]/g, "\\$&")}`).join("\n");
}

function artifactHeader(title: string): string[] {
  return [`# ${title}`, "", `AKDesk Fixed v${APP_VERSION} · 固定样例日期 ${SAMPLE_DATE}`, "", "**合成样例 · 非真实行情 / 主体 / 评级 · 不构成投资或信用结论。**", "来源：AKDesk 手工合成 fixture，非 AKShare/FRED 官方响应。用户编辑内容仅为临时练习，未核验。", ""];
}

export function ratesSampleMarkdown(question: string, roles: Record<string, EvidenceRole>, task: string, reviewDate: string): string {
  return [...artifactHeader("利率观点跟踪 · 合成样例底稿"), "## 研究问题（用户临时编辑）", quoteText(question) || "> 尚未填写", "", "## 样例证据分类（不是自动结论）", ...SAMPLE_SIGNALS.map(item => `- ${EVIDENCE_ROLES[roles[item.id]] ?? "待核验"}：${item.title}。${item.evidence}`), "", "## 下一次验证", `- 样例复盘日：${validReviewDate(reviewDate) ? reviewDate : "待填写有效日期（须晚于样例观察日）"}`, quoteText(task) || "> 尚未填写验证任务", "", "此文件不自动创建项目、保存证据或设置提醒；需在本地正式模块自行核验和确认。不要粘贴受限 API 内容、密钥或私人材料。", ""].join("\n");
}

export function creditSampleMarkdown(selected: string[]): string {
  const selectedRows = CREDIT_SAMPLE.items.filter(item => selected.includes(item.observation.bond_code));
  return [...artifactHeader("信用人工复核清单 · 合成样例"), "## 固定样例覆盖结果", ...CREDIT_SAMPLE.items.map(({ observation: row, expected }) => `- ${row.bond_name}（${row.bond_code}）：${expected.reason}；机械利差 ${expected.spreadBp === null ? "—（缺失不是 0）" : `${expected.spreadBp.toFixed(2)} BP`}。`), "", "## 用户选择的复核任务", ...(selectedRows.length ? selectedRows.map(({ observation: row, expected }) => `- [ ] ${row.bond_name}：${expected.task}`) : ["尚未选择；没有选择不表示无需复核。"]), "", "固定样例结果用于解释产品门禁，不是通用文件校验器。没有导入真实信用库或建立正式任务。", "仅在确认有权使用的数据上开展业务复核；不得把机械利差视为评级、违约概率或交易建议。", ""].join("\n");
}

export function creditSampleCsv(): string {
  const fields = Object.keys(CREDIT_SAMPLE.items[0].observation) as Array<keyof typeof CREDIT_SAMPLE.items[0]["observation"]>;
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return "\uFEFF" + [fields, ...CREDIT_SAMPLE.items.map(item => fields.map(field => item.observation[field]))].map(row => row.map(escape).join(",")).join("\r\n");
}

export function downloadScenarioFile(text: string, filename: string, type = "text/markdown;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
