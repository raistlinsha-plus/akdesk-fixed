// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChartLabPage } from "./ChartLabPage";

vi.mock("../api", () => ({
  apiGet: vi.fn(async (path: string) => {
    if (path === "/research/projects") return [];
    if (path === "/macro/catalog") return [{ series_id: "DGS10", title_zh: "10Y" }];
    return {
      data: {
        dates: ["2026-01-02"],
        series: [{ key: "DGS10", name: "API_SERIES_NAME", values: [4.12345], units: "API_UNITS", attribution: "API_ATTRIBUTION" }],
        transform: "level", years: 10, storage_mode: "request_scoped",
        terms_url: "https://fred.stlouisfed.org/legal/terms/",
      },
      meta: { source: "FRED", fetched_at: "2026-01-03T00:00:00Z", warnings: [], quality_issues: [] },
    };
  }),
  apiPost: vi.fn(),
}));
vi.mock("../components/Charts", () => ({ LineChart: () => <div>请求级图表</div> }));
vi.mock("../components/UI", () => ({
  Panel: ({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) => <section><h2>{title}</h2>{action}{children}</section>,
  SourceFooter: () => null,
  ErrorState: ({ message }: { message: string }) => <p>{message}</p>,
  LoadingState: () => <p>加载中</p>,
}));
vi.mock("./MarketPages", () => ({ PageHeading: () => <h1>图表研究室</h1> }));

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("offers only a query-reference download without exporting FRED response content", async () => {
  let exported: Blob | undefined;
  const OriginalURL = URL;
  vi.stubGlobal("URL", class extends OriginalURL {
    static createObjectURL(blob: Blob) { exported = blob; return "blob:query-reference"; }
    static revokeObjectURL() {}
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<ChartLabPage />);
  const button = await screen.findByRole("button", { name: "导出查询引用" });
  expect(screen.queryByRole("button", { name: "CSV" })).toBeNull();
  fireEvent.click(button);
  await waitFor(() => expect(exported).toBeDefined());
  expect(exported?.type).toBe("text/markdown;charset=utf-8");
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(exported!);
  });
  expect(content).toContain("[DGS10](https://fred.stlouisfed.org/series/DGS10)");
  expect(content).not.toMatch(/4\.12345|2026-01-02|2026-01-03|API_SERIES_NAME|API_UNITS|API_ATTRIBUTION/);
  expect((click.mock.instances[0] as HTMLAnchorElement).download).toMatch(/FRED查询引用-DGS10\.md$/);
});
