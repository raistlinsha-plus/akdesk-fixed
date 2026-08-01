import { describe, expect, it } from "vitest";
import { activityDetailLines } from "./researchActivity";
import type { ResearchProjectActivity } from "./types";

function event(
  eventType: ResearchProjectActivity["event_type"],
  details: Record<string, unknown>,
): ResearchProjectActivity {
  return {
    id: 1,
    project_id: 1,
    event_type: eventType,
    summary: "测试事件",
    details,
    created_at: "2026-07-15T08:00:00",
  };
}

describe("research activity details", () => {
  it("renders created values as initial state instead of a transition", () => {
    expect(activityDetailLines(event("created", { confidence: 50, status: "draft" }))).toEqual([
      "初始置信度 50",
      "初始状态 草稿",
    ]);
  });

  it("renders before and after values for updates", () => {
    expect(
      activityDetailLines(
        event("updated", {
          confidence: { before: 50, after: 65 },
          status: { before: "draft", after: "tracking" },
        }),
      ),
    ).toEqual(["置信度 50 → 65", "状态 草稿 → 跟踪中"]);
  });

  it("ignores malformed transition details", () => {
    expect(activityDetailLines(event("updated", { confidence: 50 }))).toEqual([]);
  });
});

