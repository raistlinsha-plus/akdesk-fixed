import { describe, expect, it } from "vitest";
import {
  aiInsightPath,
  shouldAutoGenerate,
  type AiInsightResponse,
} from "./aiInsights";

const insight: AiInsightResponse = {
  context_type: "market",
  context_key: "today",
  context_fingerprint: "sha256:abc",
  status: "stale",
  job_state: "idle",
  summary: "旧摘要",
  context_summary: [],
  cached_context_summary: [],
  provider: "AIHubMix",
  model: "deepseek-v4-flash-think",
  model_label: "DeepSeek V4 Flash Thinking",
  policy: { enabled: true, trigger: "data_change" },
  configured: true,
  auto_due: true,
  can_generate: true,
  usage: {
    calls: 1,
    total_tokens: 100,
    calls_remaining: 19,
    tokens_remaining: 99_900,
    limit_reached: false,
  },
  persistence_notice: "只保存最终摘要",
};

describe("AI page insights", () => {
  it("builds project-scoped paths", () => {
    expect(aiInsightPath("market")).toBe("/ai/insights/market");
    expect(aiInsightPath("project", 42)).toBe(
      "/ai/insights/project?project_id=42",
    );
    expect(aiInsightPath("topic", null, 9)).toBe(
      "/ai/insights/topic?topic_id=9",
    );
  });

  it("auto-generates once per context fingerprint", () => {
    expect(shouldAutoGenerate(insight)).toBe(true);
    expect(shouldAutoGenerate(insight, "sha256:abc")).toBe(false);
    expect(
      shouldAutoGenerate({
        ...insight,
        policy: { enabled: true, trigger: "manual" },
      }),
    ).toBe(false);
  });
});
