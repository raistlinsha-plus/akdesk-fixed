// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "../api";
import { HelpPage } from "./HelpPage";

vi.mock("../api", () => ({ apiGet: vi.fn() }));
vi.mock("./MarketPages", () => ({ PageHeading: ({ title }: { title: string }) => <h1>{title}</h1> }));

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("HelpPage voluntary diagnostics", () => {
  it("does not request diagnostics until asked, and routes the first task locally", async () => {
    const navigate = vi.fn();
    const user = userEvent.setup();
    render(<HelpPage navigate={navigate} />);
    expect(apiGet).not.toHaveBeenCalled();
    const feedback = screen.getByRole("link", { name: /功能或界面问题/ });
    expect(new URL(feedback.getAttribute("href")!).searchParams.get("mode")).toBe("不确定");
    await user.click(screen.getByRole("button", { name: /查看市场变化/ }));
    expect(navigate).toHaveBeenCalledWith("market-changes");
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("shows service errors without uploading anything and permits a retry", async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error("请重新启动本地服务"));
    const user = userEvent.setup();
    render(<HelpPage navigate={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "生成诊断摘要" }));
    expect(await screen.findByRole("status")).toHaveProperty("textContent", "请重新启动本地服务");
    expect(apiGet).toHaveBeenCalledExactlyOnceWith("/diagnostics");
    expect((screen.getByRole("button", { name: "生成诊断摘要" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByRole("button", { name: "复制摘要" })).toBeNull();
  });
});
