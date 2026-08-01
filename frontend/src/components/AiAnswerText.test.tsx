import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AiAnswerText } from "./AiAnswerText";

describe("AiAnswerText", () => {
  it("renders common model markdown without exposing raw markers", () => {
    const markup = renderToStaticMarkup(
      <AiAnswerText
        text={"**结论**\n1. 检查 `health`\n- 保存证据\n---\n> 仅供研究"}
      />,
    );

    expect(markup).toContain("<strong>结论</strong>");
    expect(markup).toContain("<code>health</code>");
    expect(markup).toContain("<blockquote>仅供研究</blockquote>");
    expect(markup).toContain("检查 ");
    expect(markup).not.toContain("**结论**");
  });
});
