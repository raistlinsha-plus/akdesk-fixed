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
});
