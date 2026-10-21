import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OnePageBrief } from "./OnePageBrief";
import type { BriefDocument } from "../brief";

describe("OnePageBrief", () => {
  it("renders sample boundaries and missing numbers with accessible export actions", () => {
    const document: BriefDocument = {
      date: "2026-07-27", generatedAt: "2026-07-27T16:30:00+08:00", marketStatus: "固定场景", headline: "曲线示例", mode: "example",
      funding: { tone: "待核验", averageChangeBp: null, items: [] },
      curve: { tenYear: null, tenYearChangeBp: 0, spreadsBp: {} },
      futures: [], notes: ["请核对来源。"],
      sources: [{ adapter: "yield_curves", label: "曲线", source: "合成示例", observationTime: "2026-07-27", fetchedAt: "2026-07-27T16:00:00+08:00", dataState: "demo", trustLevel: "unavailable", demo: true }],
    };
    const html = renderToStaticMarkup(<OnePageBrief document={document} />);
    expect(html).toContain("示例数据 · 非实时");
    expect(html).toContain("2026-07-27");
    expect(html).toContain("日变动 0.00 BP");
    expect(html).toContain("复制 Markdown");
    expect(html).toContain("下载 Markdown");
    expect(html).toContain("打印 / PDF");
    expect(html).toContain("仅用于当前页面与导出，不自动保存");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("可信可行动");
  });
});
