export type AiInsightContext = "market" | "project" | "credit" | "topic";
export type AiInsightTrigger = "manual" | "data_change" | "daily";
export type AiInsightStatus =
  | "never_generated"
  | "generating"
  | "ready"
  | "stale"
  | "failed";

export interface AiInsightResponse {
  context_type: AiInsightContext;
  context_key: string;
  context_fingerprint: string;
  status: AiInsightStatus;
  job_state: "idle" | "queued" | "running";
  summary: string;
  context_summary: string[];
  cached_context_summary: string[];
  provider: string;
  model: string;
  model_label: string;
  generated_at?: string | null;
  updated_at?: string | null;
  last_error?: string | null;
  policy: { enabled: boolean; trigger: AiInsightTrigger };
  configured: boolean;
  auto_due: boolean;
  can_generate: boolean;
  usage: {
    calls: number;
    total_tokens: number;
    by_context?: Record<
      string,
      {
        calls: number;
        prompt_tokens: number;
        completion_tokens: number;
        total_tokens: number;
      }
    >;
    calls_remaining: number;
    tokens_remaining: number;
    limit_reached: boolean;
  };
  persistence_notice: string;
}

export const AI_INSIGHT_STATUS_LABELS: Record<AiInsightStatus, string> = {
  never_generated: "尚未生成",
  generating: "生成中",
  ready: "已更新",
  stale: "上下文已变化",
  failed: "生成失败",
};

export const AI_INSIGHT_TRIGGER_LABELS: Record<AiInsightTrigger, string> = {
  manual: "仅手动",
  data_change: "数据变化后自动更新",
  daily: "每日首次打开时更新",
};

export function aiInsightPath(
  context: AiInsightContext,
  projectId?: number | null,
  topicId?: number | null,
) {
  if (context === "project") {
    return `/ai/insights/project?project_id=${projectId ?? ""}`;
  }
  if (context === "topic") {
    return `/ai/insights/topic?topic_id=${topicId ?? ""}`;
  }
  return `/ai/insights/${context}`;
}

export function shouldAutoGenerate(
  insight: AiInsightResponse,
  attemptedFingerprint?: string | null,
) {
  return Boolean(
    insight.policy.enabled &&
      insight.policy.trigger !== "manual" &&
      insight.auto_due &&
      insight.can_generate &&
      insight.job_state === "idle" &&
      attemptedFingerprint !== insight.context_fingerprint,
  );
}
