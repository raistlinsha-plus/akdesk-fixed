export type AiScenario = "help" | "market" | "research";

export const AI_FRED_BOUNDARY_NOTICE = "产品保守隔离：已识别的 FRED 来源证据、序列和元数据不发送给 AI；混合项目仅使用其余内容。";
export const AI_USER_CONTENT_NOTICE = "请勿粘贴 FRED 来源数据。系统无法全面识别未标来源的手工问题、笔记或标题，发送前请自行检查。";

export const AI_SCENARIO_LABELS: Record<AiScenario, string> = {
  help: "产品向导",
  market: "市场观察",
  research: "研究教练",
};

export const AI_QUESTION_SUGGESTIONS: Record<AiScenario, string[]> = {
  help: [
    "我第一次使用，应该从哪里开始？",
    "数据不可用时应该怎样排查？",
  ],
  market: [
    "基于当前可信线索，整理今天最值得核验的三件事。",
    "当前市场数据有哪些可信边界？",
  ],
  research: [
    "指出当前研究最缺的证据和反证。",
    "帮我整理下一步验证清单。",
  ],
};

export function aiContextPreview(
  scenario: AiScenario,
  hasProject: boolean,
): string[] {
  if (scenario === "help") {
    return ["你的问题与当前页面", "产品模块导航", "推荐研究闭环与能力边界", AI_FRED_BOUNDARY_NOTICE, AI_USER_CONTENT_NOTICE];
  }
  if (scenario === "market") {
    return [
      "最多 8 条当前市场线索",
      "来源、观测时间、可信状态与质量分",
      "不发送完整行情表或历史数据库",
      AI_FRED_BOUNDARY_NOTICE,
      AI_USER_CONTENT_NOTICE,
    ];
  }
  return hasProject
    ? [
        "所选项目的问题、假设、当前结论与复盘日期",
        "最多 8 条证据标题与来源摘要",
        "最多 12 条研究记录标题与状态，不发送记录正文",
        AI_FRED_BOUNDARY_NOTICE,
        AI_USER_CONTENT_NOTICE,
      ]
    : ["项目数量与状态", "最多 8 个最近项目标题", "不发送研究正文", AI_FRED_BOUNDARY_NOTICE, AI_USER_CONTENT_NOTICE];
}

export function buildAiAssistantRequest({
  scenario,
  question,
  projectId,
  currentPage,
  confirmed,
}: {
  scenario: AiScenario;
  question: string;
  projectId: number | null;
  currentPage: string;
  confirmed: boolean;
}) {
  return {
    scenario,
    question: question.trim(),
    project_id: scenario === "research" ? projectId : null,
    current_page: currentPage,
    confirm_external_processing: confirmed,
  };
}
