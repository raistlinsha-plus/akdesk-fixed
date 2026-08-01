export type ExperienceTaskStatus = "done" | "attention" | "next";

export interface ExperienceTask {
  id: string;
  title: string;
  description: string;
  action: string;
  page: string;
  status: ExperienceTaskStatus;
}

export function guideProgress(tasks: ExperienceTask[]) {
  const completed = tasks.filter((task) => task.status === "done").length;
  return {
    completed,
    total: tasks.length,
    percent: tasks.length ? Math.round((completed / tasks.length) * 100) : 0,
  };
}

export function buildMarketTodayTasks({
  readySources,
  totalSources,
  attentionSources,
  watchlistItems,
  recentPages,
}: {
  readySources: number;
  totalSources: number;
  attentionSources: number;
  watchlistItems: number;
  recentPages: number;
}): ExperienceTask[] {
  const sourcesReady = totalSources > 0 && readySources === totalSources && attentionSources === 0;
  const pendingSources = Math.max(0, totalSources - readySources - attentionSources);
  const sourceDescription = [
    `${readySources}/${totalSources} 个首页数据源已返回`,
    attentionSources ? `${attentionSources} 个需要留意` : "",
    pendingSources ? `${pendingSources} 个正在读取` : "",
  ].filter(Boolean).join("，");
  return [
    {
      id: "market-health",
      title: "确认数据可用状态",
      description: sourcesReady
        ? `${readySources}/${totalSources} 个首页数据源已经返回`
        : sourceDescription,
      action: sourcesReady ? "查看数据健康" : "排查不可用数据",
      page: "health",
      status: sourcesReady ? "done" : "attention",
    },
    {
      id: "market-watchlist",
      title: "建立自己的观察清单",
      description: watchlistItems
        ? `已有 ${watchlistItems} 个自选，市场异动可集中查看`
        : "把常看的债券、期货、宏观或外汇加入自选",
      action: watchlistItems ? "打开我的自选" : "开始添加自选",
      page: watchlistItems ? "watchlist" : "bonds",
      status: watchlistItems ? "done" : "next",
    },
    {
      id: "market-module",
      title: "进入一个专业市场模块",
      description: recentPages
        ? `最近访问过 ${recentPages} 个市场模块`
        : "从收益率曲线开始，熟悉来源、时点与可信状态",
      action: recentPages ? "继续查看曲线" : "打开收益率曲线",
      page: "curves",
      status: recentPages ? "done" : "next",
    },
    {
      id: "market-review",
      title: "形成今日复盘",
      description: "把资金、曲线、期货与事件整理为可回看的日度记录",
      action: "打开每日复盘",
      page: "report",
      status: "next",
    },
  ];
}

export function buildResearchTodayTasks({
  activeProjects,
  topics,
  evidence,
  evidenceBasket,
  dueReviews,
}: {
  activeProjects: number;
  topics: number;
  evidence: number;
  evidenceBasket: number;
  dueReviews: number;
}): ExperienceTask[] {
  return [
    {
      id: "research-project",
      title: "提出一个可验证的问题",
      description: activeProjects
        ? `已有 ${activeProjects} 个进行中的研究项目`
        : "用模板立项，先写清研究问题与初始假设",
      action: activeProjects ? "继续研究项目" : "创建研究项目",
      page: "projects",
      status: activeProjects ? "done" : "next",
    },
    {
      id: "research-topic",
      title: "建立长期观察专题",
      description: topics
        ? `已有 ${topics} 个专题工作台`
        : "一键创建中国利率示例专题，理解跨源研究视图",
      action: topics ? "打开专题库" : "创建示例专题",
      page: "topics",
      status: topics ? "done" : "next",
    },
    {
      id: "research-evidence",
      title: "保存第一份研究证据",
      description: evidence || evidenceBasket
        ? `项目证据 ${evidence} 项，证据篮待归档 ${evidenceBasket} 项`
        : "从图表研究室保存序列、变换与来源引用",
      action: evidence || evidenceBasket ? "查看图表研究室" : "收集研究证据",
      page: "chart-lab",
      status: evidence || evidenceBasket ? "done" : "next",
    },
    {
      id: "research-review",
      title: "处理到期复盘",
      description: dueReviews
        ? `有 ${dueReviews} 项需要复核观点或下一步任务`
        : "当前没有到期项目，可安排下一次复盘日期",
      action: dueReviews ? "处理待复盘" : "查看每周复盘",
      page: "weekly-review",
      status: dueReviews ? "attention" : "done",
    },
  ];
}
