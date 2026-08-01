import { describe, expect, it } from "vitest";
import { activeWorkflowStep, projectProgress } from "./researchWorkflow";
import type { ResearchProject } from "./types";

function project(overrides: Partial<ResearchProject> = {}): ResearchProject {
  return {
    id: 1,
    title: "利率研究",
    question: "",
    hypothesis: "",
    status: "draft",
    confidence: 50,
    horizon: "",
    tags: [],
    next_review_date: null,
    conclusion: "",
    created_at: "2026-07-17T10:00:00",
    updated_at: "2026-07-17T10:00:00",
    entries: [],
    evidence: [],
    activity: [],
    ...overrides,
  };
}

describe("research workflow", () => {
  it("identifies the next incomplete research step", () => {
    expect(projectProgress(project()).nextStep).toContain("研究问题");
    expect(projectProgress(project({ question: "长端会如何变化？" })).nextStep)
      .toContain("初始假设");
  });

  it("moves the workflow from project to evidence and conclusion", () => {
    expect(activeWorkflowStep({ signals: 2, projects: 0, evidence: 0, conclusions: 0, due: 0 })).toBe(0);
    expect(activeWorkflowStep({ signals: 2, projects: 1, evidence: 0, conclusions: 0, due: 0 })).toBe(1);
    expect(activeWorkflowStep({ signals: 2, projects: 1, evidence: 2, conclusions: 0, due: 0 })).toBe(2);
    expect(activeWorkflowStep({ signals: 2, projects: 1, evidence: 2, conclusions: 1, due: 0 })).toBe(3);
  });
});
