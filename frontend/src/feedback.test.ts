import { describe, expect, it } from "vitest";
import { diagnosticMarkdown, feedbackUrl, scenarioFeedback } from "./feedback";

describe("voluntary feedback", () => {
  it("only allows fixed scenario metadata, including against inherited object keys", () => {
    const result = scenarioFeedback("/Users/private?key=secret", "toString", "constructor", "private-host");
    expect(result.preview).toContain("未指定案例");
    expect(result.preview).toContain("未选择");
    expect(result.url).not.toContain("private");
    expect(result.url).not.toContain("secret");
    expect(new URL(result.url).searchParams.has("body")).toBe(false);
    const url = new URL(scenarioFeedback("credit", "completed", "no", "local").url);
    expect(url.searchParams.get("template")).toBe("scenario_feedback.yml");
    expect(url.searchParams.get("scenario")).toBe("信用观察与人工复核");
    expect(url.searchParams.get("result")).toBe("已完成样例任务");
    expect(url.searchParams.get("reuse")).toBe("暂时不会");
  });
  it("prefills only version, mode and sanitized page, without browser context", () => {
    const url = new URL(feedbackUrl("data", "/Users/private?key=hello", "demo"));
    expect(url.origin).toBe("https://github.com");
    expect(url.searchParams.get("template")).toBe("data_source.yml");
    expect(url.searchParams.get("mode")).toBe("演示模式");
    expect(url.searchParams.get("page")).toBe("help");
    expect(url.href).not.toContain("private");
    expect(url.href).not.toContain("hello");
    expect(url.searchParams.has("body")).toBe(false);
  });

  it("only prefills known route identifiers and explicit operating modes", () => {
    const secret = "sk-" + "test-only-placeholder";
    const url = new URL(feedbackUrl("bug", `/Users/alice?api_key=${secret}`, "local"));
    expect(url.href).not.toContain("alice");
    expect(url.href).not.toContain(secret);
    expect(url.searchParams.get("mode")).toBe("不确定");
    expect(new URL(feedbackUrl("bug", "market-changes", "live")).searchParams.get("page")).toBe("market-changes");
    expect(new URL(feedbackUrl("bug", "help", "live")).searchParams.get("mode")).toBe("实时模式");
  });

  it("distinguishes a missing cache from a zero-age cache", () => {
    const output = diagnosticMarkdown({
      generated_at: "2026-10-22T00:00:00Z",
      app: { name: "AKDesk Fixed", version: "1.1.0", mode: "demo" },
      environment: { os: "macOS", os_version: "15.0", python_version: "3.13.3", architecture: "arm64" },
      storage: { type: "custom", exists: true, writable: true },
      adapters: [null, 0].map((age, index) => ({ adapter: `source_${index}`, state: "cached", research_status: "limited", trust_level: "partial", cache_age_seconds: age, consecutive_failures: 0, error_category: "none" })),
    });
    expect(output).toContain("未缓存");
    expect(output).toContain("| 0 | 0 | none |");
    expect(output).toContain("没有自动上传");
  });
});
