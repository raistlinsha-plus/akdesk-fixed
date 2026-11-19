// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost } from "../api";
import { downloadScenarioFile } from "../scenarios";
import { journalMarkdown, type JournalDraft, type JournalEntry } from "../weekJournal";
import { WeekContinuityDemo } from "./WeekContinuityDemo";
import { WeekJournal } from "./WeekJournal";

vi.mock("../api", async importOriginal => ({
  ...await importOriginal<typeof import("../api")>(),
  apiGet: vi.fn(), apiPost: vi.fn(),
}));
vi.mock("../scenarios", async importOriginal => ({
  ...await importOriginal<typeof import("../scenarios")>(), downloadScenarioFile: vi.fn(),
}));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const date = "2026-07-31";
const first: JournalEntry = {
  week_end: "2026-07-24", created_at: "2026-07-24T08:00:00Z", revision: "a".repeat(32),
  judgment: "上周观察", next_question: "是否继续？", assessment: "", assessment_note: "", previous_revision: null,
};
const current = { ...first, week_end: date, revision: "b".repeat(32), judgment: "旧的本周判断",
  previous_revision: first.revision };
function Harness() {
  const [draft, setDraft] = useState<JournalDraft>();
  return <WeekJournal date={date} draft={draft} onDraft={setDraft} onSelectDate={vi.fn()}>行情区不依赖记录保存</WeekJournal>;
}

it("writes without having to query market data and exports only the saved revision", async () => {
  vi.mocked(apiGet).mockResolvedValue({ week_end: date, current: null, previous: first, assessed: null });
  vi.mocked(apiPost).mockResolvedValue({ ...current, judgment: "重新核验方向", assessment: "pending" });
  render(<Harness />);
  await screen.findByText("上周待核验：是否继续？");
  fireEvent.change(screen.getByLabelText("本周判断"), { target: { value: "重新核验方向" } });
  fireEvent.change(screen.getByLabelText("对上一周的人工核验"), { target: { value: "pending" } });
  fireEvent.click(screen.getByRole("button", { name: "保存到本机" }));
  await screen.findByText("已保存到本机。");
  expect(apiPost).toHaveBeenCalledWith("/week-journal/" + date, expect.objectContaining({
    judgment: "重新核验方向", expected_revision: null, previous_revision: first.revision, assessment: "pending",
  }), expect.anything());
  fireEvent.change(screen.getByLabelText("本周判断"), { target: { value: "未保存文字" } });
  fireEvent.click(screen.getByRole("button", { name: "导出已保存底稿" }));
  const [markdown] = vi.mocked(downloadScenarioFile).mock.calls[0];
  expect(markdown).toContain("重新核验方向");
  expect(markdown).not.toContain("未保存文字");
  expect(vi.mocked(apiGet).mock.calls.every(([path]) => path.startsWith("/week-journal/"))).toBe(true);
});

it("preserves the edit on a 409 and only rebases after explicit review", async () => {
  vi.mocked(apiGet).mockResolvedValue({ week_end: date, current, previous: first, assessed: first });
  vi.mocked(apiPost).mockRejectedValue(new ApiError(409, "另一标签已修改"));
  render(<Harness />);
  await screen.findByDisplayValue("旧的本周判断");
  fireEvent.change(screen.getByLabelText("本周判断"), { target: { value: "我的修改" } });
  fireEvent.click(screen.getByRole("button", { name: "保存到本机" }));
  await screen.findByText("另一标签已修改");
  expect(screen.getByDisplayValue("我的修改")).toBeTruthy();
  vi.mocked(apiGet).mockResolvedValue({ week_end: date, current: { ...current, revision: "c".repeat(32) }, previous: first, assessed: first });
  fireEvent.click(screen.getByRole("button", { name: "重新读取本地记录" }));
  fireEvent.click(await screen.findByRole("button", { name: "保留草稿，在最新修订基础上编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "保存到本机" }));
  await waitFor(() => expect(vi.mocked(apiPost).mock.calls[1][1]).toMatchObject({
    judgment: "我的修改", expected_revision: "c".repeat(32),
  }));
});

it("does not export arbitrary source payload and escapes user Markdown markup", () => {
  const text = journalMarkdown({ ...current, judgment: "<script>![外链](https://example.org)</script>" }, null);
  expect(text).toContain("&lt;script&gt;");
  expect(text).toContain("原核验所引用的修订已不可用");
  expect(text).not.toContain("<script>");
  expect(text).not.toContain("![外链]");
});

it("completes both synthetic weeks without making an API request or storage write", () => {
  render(<WeekContinuityDemo />);
  fireEvent.change(screen.getByLabelText("第一周判断"), { target: { value: "第一周文字" } });
  fireEvent.change(screen.getByLabelText("下一周要核验什么？"), { target: { value: "核验问题" } });
  fireEvent.click(screen.getByRole("button", { name: "保存样例并进入下一周" }));
  expect(screen.getByText("上周待核验：核验问题")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("第二周判断"), { target: { value: "第二周文字" } });
  fireEvent.click(screen.getByRole("button", { name: "下载两周合成底稿" }));
  expect(downloadScenarioFile).toHaveBeenCalledWith(expect.stringContaining("固定合成样例"), expect.stringContaining("两周"));
  expect(apiPost).not.toHaveBeenCalled();
  expect(apiGet).not.toHaveBeenCalled();
});
