// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { apiGet, apiPatch, apiPost } from "../api";
import type { ResearchProject } from "../types";
import { ProjectsPage } from "./ProjectsPage";

vi.mock("../api", async importOriginal => ({
  ...await importOriginal<typeof import("../api")>(),
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(),
}));
vi.mock("../components/AiInsightCard", () => ({ AiInsightCard: () => null }));
vi.mock("../components/ResearchActionPanel", () => ({ ResearchActionPanel: () => null }));
vi.mock("../components/ProjectReviewDelta", () => ({
  ProjectReviewDelta: ({ onReviewed }: { onReviewed: () => void }) => <button onClick={onReviewed}>模拟完成复盘</button>,
}));
vi.mock("./MarketPages", () => ({ PageHeading: () => <h1>研究项目</h1> }));

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("refreshes saved review records without discarding unsaved project edits", async () => {
  const user = userEvent.setup();
  const project: ResearchProject = {
    id: 1, title: "利率研究", question: "原始研究问题", hypothesis: "原始假设",
    status: "tracking", confidence: 50, horizon: "一周", tags: [], conclusion: "",
    created_at: "2026-11-01T10:00:00+08:00", updated_at: "2026-11-01T10:00:00+08:00",
    evidence: [], activity: [], entries: [],
  };
  const reviewed: ResearchProject = {
    ...project,
    updated_at: "2026-11-04T10:00:00+08:00",
    entries: [{ id: 4, project_id: 1, entry_type: "review", title: "明确复盘记录", content: "人工核验", status: "open", due_date: null, created_at: "2026-11-04T10:00:00+08:00", updated_at: "2026-11-04T10:00:00+08:00" }],
  };
  let detailReads = 0;
  vi.mocked(apiGet).mockImplementation(async path => {
    if (path === "/research/projects") return [project];
    if (path === "/research/templates") return [];
    if (path === "/research/backups") return null;
    if (path === "/research/projects/1") return ++detailReads === 1 ? project : reviewed;
    throw new Error(`Unexpected path: ${path}`);
  });
  render(<ProjectsPage initialQuery="1" navigate={vi.fn()} />);
  const question = await screen.findByLabelText("研究问题");
  await user.clear(question);
  await user.type(question, "尚未保存的研究问题");
  await user.click(screen.getByRole("button", { name: "模拟完成复盘" }));
  await screen.findByText("明确复盘记录");
  await waitFor(() => expect(detailReads).toBe(2));
  expect(screen.getByLabelText("研究问题")).toHaveProperty("value", "尚未保存的研究问题");
  expect(apiPost).not.toHaveBeenCalled();
  expect(apiPatch).not.toHaveBeenCalled();
});
