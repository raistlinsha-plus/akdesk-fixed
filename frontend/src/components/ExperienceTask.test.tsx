// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ExperienceTask } from "./ExperienceTask";
import { downloadScenarioFile } from "../scenarios";
import { experienceFeedback } from "../experience";

vi.mock("../scenarios", () => ({ downloadScenarioFile: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function enterWriting() {
  fireEvent.click(screen.getByRole("button", { name: "核验样例依据" }));
  expect(screen.getByText("—（缺失）")).toBeTruthy();
  const next = screen.getByRole<HTMLButtonElement>("button", { name: "写下我的判断" });
  expect(next.disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: /已核对/ }));
  fireEvent.click(next);
}

it("guides observation, explicit verification, writing and synthetic export", () => {
  render(<ExperienceTask surface="online" />);
  expect(screen.getByText("+2.00%")).toBeTruthy();
  expect(screen.getByText("-1.00%")).toBeTruthy();
  enterWriting();
  const download = screen.getByRole<HTMLButtonElement>("button", { name: "下载合成底稿" });
  expect(download.disabled).toBe(true);
  const note = screen.getByLabelText("我的观察");
  fireEvent.change(note, { target: { value: "方向分化\n<不作因果判断>" } });
  fireEvent.click(download);
  expect(downloadScenarioFile).toHaveBeenCalledExactlyOnceWith(
    expect.stringContaining("共同观测日期：2026-07-30、2026-08-03"),
    "AKDesk-股债金汇首任务-合成底稿.md",
  );
  const markdown = vi.mocked(downloadScenarioFile).mock.calls[0][0];
  expect(markdown).toContain("合成样例 · 非真实行情");
  expect(markdown).toContain("> &lt;不作因果判断&gt;");
  expect(markdown).toContain("不补零");
  expect(screen.getByRole("status").textContent).toContain("已向浏览器发起下载");
  expect((screen.getByLabelText("样例任务结果") as HTMLSelectElement).value).toBe("");
  fireEvent.click(screen.getByRole("button", { name: "上一步" }));
  fireEvent.click(screen.getByRole("button", { name: "写下我的判断" }));
  expect((screen.getByLabelText("我的观察") as HTMLTextAreaElement).value).toContain("方向分化");
  fireEvent.click(screen.getByRole("button", { name: "重做首任务" }));
  enterWriting();
  expect((screen.getByLabelText("我的观察") as HTMLTextAreaElement).value).toBe("");
});

it("preserves a draft on browser export failure and sends no private draft in feedback", () => {
  render(<ExperienceTask surface="local" />);
  enterWriting();
  fireEvent.change(screen.getByLabelText("我的观察"), { target: { value: "不公开的观察" } });
  vi.mocked(downloadScenarioFile).mockImplementationOnce(() => { throw new Error("browser blocked"); });
  fireEvent.click(screen.getByRole("button", { name: "下载合成底稿" }));
  expect(screen.getByRole("alert").textContent).toContain("草稿仍在");
  fireEvent.click(screen.getByText("主动反馈完成情况或卡点"));
  fireEvent.change(screen.getByLabelText("样例任务结果"), { target: { value: "blocked" } });
  fireEvent.change(screen.getByLabelText("本地安装状态"), { target: { value: "started" } });
  fireEvent.change(screen.getByLabelText("七日内实际再次使用"), { target: { value: "returned" } });
  fireEvent.click(screen.getByRole("button", { name: "预览反馈字段" }));
  const preview = screen.getByLabelText("首任务反馈预览").textContent;
  expect(preview).toContain("本地版已启动");
  expect(preview).toContain("实际在七日内再次使用");
  const url = new URL(screen.getByRole<HTMLAnchorElement>("link", { name: /前往 GitHub/ }).href);
  expect(url.searchParams.get("template")).toBe("experience_feedback.yml");
  expect(url.searchParams.get("surface")).toBe("本地合成体验");
  expect(decodeURIComponent(url.href)).not.toContain("不公开的观察");
  fireEvent.change(screen.getByLabelText("下一步更需要什么"), { target: { value: "weekly" } });
  expect(screen.queryByLabelText("首任务反馈预览")).toBeNull();
});

it("drops arbitrary, inherited and non-allowlisted feedback values", () => {
  const result = experienceFeedback("online", {
    result: "sensitive note", install: "__proto__", reuse: "private/path", interest: "weekly",
  });
  expect(decodeURIComponent(result.url)).not.toMatch(/sensitive|__proto__|private\/path/);
  expect(result.preview).toContain("跨资产周复盘");
  expect(result.preview).toContain("install: 未说明");
});

it("does not presume whether the local edition has been installed", () => {
  render(<ExperienceTask surface="local" />);
  expect((screen.getByLabelText("本地安装状态") as HTMLSelectElement).value).toBe("unknown");
});
