import { describe, expect, it } from "vitest";
import {
  buildMarketTodayTasks,
  buildResearchTodayTasks,
  guideProgress,
} from "./experienceGuide";

describe("low-friction experience guide", () => {
  it("guides a new market user from health to watchlist and review", () => {
    const tasks = buildMarketTodayTasks({
      readySources: 5,
      totalSources: 7,
      attentionSources: 2,
      watchlistItems: 0,
      recentPages: 0,
    });
    expect(tasks[0].status).toBe("attention");
    expect(tasks[1].page).toBe("bonds");
    expect(guideProgress(tasks)).toEqual({ completed: 0, total: 4, percent: 0 });
  });

  it("recognizes established market habits without hiding daily review", () => {
    const tasks = buildMarketTodayTasks({
      readySources: 7,
      totalSources: 7,
      attentionSources: 0,
      watchlistItems: 3,
      recentPages: 2,
    });
    expect(guideProgress(tasks).completed).toBe(3);
    expect(tasks[3].action).toBe("打开每日复盘");
  });

  it("turns existing research state into concrete next actions", () => {
    const tasks = buildResearchTodayTasks({
      activeProjects: 2,
      topics: 1,
      evidence: 3,
      evidenceBasket: 1,
      dueReviews: 2,
    });
    expect(guideProgress(tasks).completed).toBe(3);
    expect(tasks[3]).toMatchObject({ status: "attention", page: "weekly-review" });
  });
});
