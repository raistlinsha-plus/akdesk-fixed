import { expect,it } from "vitest";
import { commonComparison,crossReferenceMarkdown,historyChange,syntheticHistory,syntheticQuotes } from "./crossAssets";

it("compares only common dates without filling and needs two observations",()=>{
  const a=[{date:"2026-08-01",close:100},{date:"2026-08-02",close:120},{date:"2026-08-03",close:110}];
  const b=[{date:"2026-08-01",close:200},{date:"2026-08-03",close:180}];
  expect(commonComparison(a,b)).toEqual({dates:["2026-08-01","2026-08-03"],left:[100,110.00000000000001],right:[100,90]});
  expect(commonComparison(a,b.slice(1))).toBeNull();
  expect(historyChange(a,5)).toBeNull();
});
it("real export contains references and own text but no quote values or dates",()=>{
  const rows=syntheticQuotes().map(item=>({...item,demo:false,source_url:"https://example.com/asset",terms_url:"https://example.com/terms"}));
  const text=crossReferenceMarkdown(rows,"自己的观察",false);
  expect(text).toContain("查询引用版");expect(text).toContain("自己的观察");expect(text).toContain("https://example.com/asset");
  expect(text).not.toContain("700.00");expect(text).not.toContain("2026-08-03");
});
it("synthetic export is explicit and fixture history ends on sample day",()=>{
  const rows=syntheticQuotes();
  expect(crossReferenceMarkdown(rows,"",true)).toContain("合成样例");
  expect(syntheticHistory(rows[0]).data.at(-1)?.date).toBe("2026-08-03");
});
