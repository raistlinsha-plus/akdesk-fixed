import type { ResearchProject } from "./types";

export interface ResearchProgress {
  completed: number;
  total: number;
  percent: number;
  nextStep: string;
}

export function projectProgress(project: ResearchProject): ResearchProgress {
  const checks = [
    { done: Boolean(project.question.trim()), next: "补充一个可验证的研究问题" },
    { done: Boolean(project.hypothesis.trim()), next: "写下初始假设" },
    { done: project.evidence.length > 0, next: "保存第一条可信证据" },
    {
      done: project.entries.some((item) => item.entry_type === "counter_evidence"),
      next: "记录一条反证或失效条件",
    },
    { done: Boolean(project.conclusion.trim()), next: "更新当前结论与风险点" },
    { done: Boolean(project.next_review_date), next: "设置下一次复盘日期" },
  ];
  const completed = checks.filter((item) => item.done).length;
  return {
    completed,
    total: checks.length,
    percent: Math.round((completed / checks.length) * 100),
    nextStep: checks.find((item) => !item.done)?.next ?? "进入复盘并确认观点是否仍然成立",
  };
}

export interface WorkflowCounts {
  signals: number;
  projects: number;
  evidence: number;
  conclusions: number;
  due: number;
}

export function activeWorkflowStep(counts: WorkflowCounts): number {
  if (counts.projects === 0) return 0;
  if (counts.evidence === 0) return 1;
  if (counts.conclusions === 0) return 2;
  if (counts.due > 0) return 4;
  return 3;
}
