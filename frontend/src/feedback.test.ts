import { describe, expect, it } from "vitest";
import { diagnosticMarkdown, feedbackUrl } from "./feedback";

describe("voluntary feedback", () => {
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
