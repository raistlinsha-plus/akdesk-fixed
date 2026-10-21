import { APP_VERSION, REPOSITORY_URL } from "./release";

export type FeedbackKind = "bug" | "data" | "feature";

const FEEDBACK_PAGES = new Set([
  "help", "demo", "market", "market-changes", "money", "curves", "bonds",
  "futures", "credit", "convertibles", "issuance", "forex", "macro",
  "sovereign", "chart-lab", "release-review", "report", "weekly-review",
  "research", "projects", "topics", "watchlist", "calculator", "health",
]);

export function feedbackUrl(kind: FeedbackKind, page = "help", mode = "unknown"): string {
  const templates = { bug: "bug_report.yml", data: "data_source.yml", feature: "feature_request.yml" };
  const prefixes = { bug: "Bug", data: "Data", feature: "Feature" };
  const query = new URLSearchParams({
    template: templates[kind],
    title: `[${prefixes[kind]}] v${APP_VERSION} `,
    version: `v${APP_VERSION}`,
    page: FEEDBACK_PAGES.has(page) ? page : "help",
    mode: mode === "demo" ? "演示模式" : mode === "live" ? "实时模式" : "不确定",
  });
  return `${REPOSITORY_URL}/issues/new?${query.toString()}`;
}

export interface DiagnosticReport {
  generated_at: string;
  app: { name: string; version: string; mode: string };
  environment: { os: string; os_version: string; python_version: string; architecture: string };
  storage: { type: string; exists: boolean; writable: boolean };
  adapters: Array<{
    adapter: string;
    state: string;
    research_status: string;
    trust_level: string;
    cache_age_seconds: number | null;
    consecutive_failures: number;
    error_category: string;
  }>;
}

// Values come from the server's allowlisted diagnostic endpoint, never /info or logs.
export function diagnosticMarkdown(report: DiagnosticReport): string {
  return [
    `# AKDesk Fixed v${report.app.version} 诊断摘要`, "",
    `- 生成时间：${report.generated_at}`,
    `- 模式：${report.app.mode === "demo" ? "演示" : "实时"}`,
    `- 系统：${report.environment.os} ${report.environment.os_version}`,
    `- Python：${report.environment.python_version}`,
    `- 架构：${report.environment.architecture}`,
    `- 存储类型：${report.storage.type}`,
    `- 目录存在：${report.storage.exists ? "是" : "否"}；可写：${report.storage.writable ? "是" : "否"}`,
    "", "## 数据源状态", "",
    "| 数据源 | 连接状态 | 研究可用性 | 可信状态 | 缓存秒数 | 连续失败 | 错误分类 |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    ...report.adapters.map((item) => `| ${item.adapter} | ${item.state} | ${item.research_status} | ${item.trust_level} | ${item.cache_age_seconds ?? "未缓存"} | ${item.consecutive_failures} | ${item.error_category} |`),
    "", "数据源状态是本地状态快照，不代表已确认产品缺陷；异常也可能来自上游、本机网络或未配置凭据。",
    "本摘要不含 API Key、个人绝对路径、原始错误日志、数据库或研究正文。由用户主动生成，没有自动上传。", "",
  ].join("\n");
}
