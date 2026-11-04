// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { apiDownload, apiGet } from "../api";
import type { WeeklyReport } from "../types";
import { WeeklyReviewPage } from "./WeeklyReviewPage";

vi.mock("../api", () => ({ apiGet: vi.fn(), apiDownload: vi.fn() }));
vi.mock("./MarketPages", () => ({ PageHeading: ({ title }: { title: string }) => <h1>{title}</h1> }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const report = (date: string): WeeklyReport => ({
  start_date: date, end_date: date, generated_at: date, summary: { active_projects: 1, projects_updated: 0, notes: 0, counter_evidence: 0, tasks_done: 0, tasks_open: 1, release_reviews: 0 },
  due_projects: [], projects: [], activity: [], entries: [], conclusion_updates: [], next_reviews: [], release_reviews: [],
  open_tasks: [{ id: 77, project_id: 9, project_title: "利率跟踪", title: "检查反证" }], notice: "不生成自动结论",
});

it("links weekly tasks to the project id, not the task id", async () => {
  vi.mocked(apiGet).mockResolvedValue(report("2026-11-04"));
  const navigate = vi.fn();
  render(<WeeklyReviewPage refreshSeed={0} navigate={navigate} />);
  await userEvent.click(await screen.findByRole("button", { name: "利率跟踪 → 项目复盘" }));
  expect(navigate).toHaveBeenCalledExactlyOnceWith("projects", "9");
});

it("ignores a slow previous date and only exports the displayed report", async () => {
  let resolveOld!: (value: WeeklyReport) => void;
  vi.mocked(apiGet).mockImplementation(path => path.endsWith("2026-08-03") ? new Promise<WeeklyReport>(resolve => { resolveOld = resolve; }) : Promise.resolve(report(path.split("end=")[1])) as ReturnType<typeof apiGet>);
  render(<WeeklyReviewPage refreshSeed={0} />);
  await screen.findByRole("button", { name: "Markdown" });
  const date = screen.getByLabelText("周结束日");
  fireEvent.change(date, { target: { value: "2026-08-03" } });
  await waitFor(() => expect((screen.getByRole("button", { name: "Markdown" }) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.change(date, { target: { value: "2026-08-04" } });
  await screen.findByRole("heading", { name: "复盘区间 · 2026-08-04 至 2026-08-04" });
  await act(async () => { resolveOld(report("2026-08-03")); });
  expect(screen.queryByRole("heading", { name: /2026-08-03 至/ })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Markdown" }));
  expect(apiDownload).toHaveBeenCalledExactlyOnceWith("/research/weekly-report?format=markdown&end=2026-08-04", "akdesk-weekly.md");
});
