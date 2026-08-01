// @vitest-environment jsdom
import { Component, type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppErrorBoundary } from "./AppErrorBoundary";

class BrokenView extends Component<{ children?: ReactNode }> {
  render(): ReactNode {
    throw new Error("chunk failed");
  }
}

afterEach(() => vi.restoreAllMocks());

describe("AppErrorBoundary", () => {
  it("shows a recoverable local-data-safe fallback", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const onReload = vi.fn();
    render(
      <AppErrorBoundary onReload={onReload}>
        <BrokenView />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("alert").textContent).toContain("本地研究数据没有被删除");
    await userEvent.click(screen.getByRole("button", { name: "重新加载界面" }));
    expect(onReload).toHaveBeenCalledOnce();
  });
});
