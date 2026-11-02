import { describe, expect, it } from "vitest";
import {
  aiContextPreview,
  buildAiAssistantRequest,
} from "./aiAssistant";

describe("AI assistant request boundary", () => {
  it("only attaches a project in research mode", () => {
    expect(buildAiAssistantRequest({
      scenario: "market",
      question: "  今天看什么？ ",
      projectId: 9,
      currentPage: "dashboard",
      confirmed: true,
    })).toEqual({
      scenario: "market",
      question: "今天看什么？",
      project_id: null,
      current_page: "dashboard",
      confirm_external_processing: true,
    });
  });

  it("describes the minimized research context before sending", () => {
    const preview = aiContextPreview("research", true);
    expect(preview.join(" ")).toContain("不发送记录正文");
    expect(preview.join(" ")).toContain("证据标题");
  });

  it.each(["help", "market", "research"] as const)("states the conservative FRED boundary before %s sends", (scenario) => {
    const preview = aiContextPreview(scenario, true).join(" ");
    expect(preview).toContain("保守隔离");
    expect(preview).toContain("FRED 来源证据、序列和元数据不发送");
    expect(preview).toContain("无法全面识别");
    expect(preview).toContain("发送前请自行检查");
  });
});
