import type { ResearchProjectActivity, ResearchStatus } from "./types";

const statusLabels: Record<ResearchStatus, string> = {
  draft: "草稿",
  tracking: "跟踪中",
  formed: "已形成观点",
  review: "待复盘",
  archived: "已归档",
};

function statusLabel(value: unknown): string {
  const key = String(value) as ResearchStatus;
  return statusLabels[key] || String(value ?? "—");
}

function transition(value: unknown): { before: unknown; after: unknown } | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  if (!("before" in candidate) || !("after" in candidate)) return null;
  return { before: candidate.before, after: candidate.after };
}

export function activityDetailLines(event: ResearchProjectActivity): string[] {
  const confidence = event.details.confidence;
  const status = event.details.status;
  if (event.event_type === "created") {
    return [
      ...(typeof confidence === "number" ? [`初始置信度 ${confidence}`] : []),
      ...(typeof status === "string" ? [`初始状态 ${statusLabel(status)}`] : []),
    ];
  }

  const confidenceChange = transition(confidence);
  const statusChange = transition(status);
  return [
    ...(confidenceChange
      ? [`置信度 ${String(confidenceChange.before ?? "—")} → ${String(confidenceChange.after ?? "—")}`]
      : []),
    ...(statusChange
      ? [`状态 ${statusLabel(statusChange.before)} → ${statusLabel(statusChange.after)}`]
      : []),
  ];
}

