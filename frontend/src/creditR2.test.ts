import { describe, expect, it } from "vitest";
import {
  buildCreditImportPath,
  calculateCreditWorkspaceScrollTop,
  filterCreditPortfolioMembers,
  filterCreditIssuers,
  filterCreditItems,
  nextCreditVisibleCount,
  toggleCreditMember,
} from "./creditR2";
import type { CreditCoverageItem, CreditIssuerSummary } from "./types";

const item = {
  id: 1,
  bond_code: "102600001",
  bond_name: "示例中票",
  normalized_issuer: "示例集团",
  rating: "AAA",
  sector: "城投",
  region: "上海",
  watch_status: "watch",
} as CreditCoverageItem;

describe("credit R2 workspace helpers", () => {
  it("filters bonds by entity text and watch state", () => {
    expect(filterCreditItems([item], "示例集团", "watch")).toEqual([item]);
    expect(filterCreditItems([item], "示例集团", "active")).toEqual([]);
    expect(filterCreditItems([item], "北京", "all")).toEqual([]);
  });

  it("filters issuer master by metadata", () => {
    const issuer = {
      issuer: "示例集团",
      sector: "城投",
      region: "上海",
      issuer_type: "地方国企",
    } as CreditIssuerSummary;
    expect(filterCreditIssuers([issuer], "地方国企")).toEqual([issuer]);
  });

  it("encodes filename and explicit field mapping", () => {
    const path = buildCreditImportPath("信用 数据.xlsx", false, { bond_code: "证券代码" });
    expect(path).toContain("filename=%E4%BF%A1%E7%94%A8+%E6%95%B0%E6%8D%AE.xlsx");
    expect(decodeURIComponent(path)).toContain('"bond_code":"证券代码"');
  });

  it("adds members without duplicates and removes them", () => {
    expect(toggleCreditMember([1], 1, true)).toEqual([1]);
    expect(toggleCreditMember([1], 2, true)).toEqual([1, 2]);
    expect(toggleCreditMember([1, 2], 1, false)).toEqual([2]);
  });

  it("filters portfolio candidates without hiding selected membership state", () => {
    const second = {
      ...item,
      id: 2,
      bond_code: "102600002",
      bond_name: "另一只债",
      normalized_issuer: "另一集团",
    } as CreditCoverageItem;
    expect(filterCreditPortfolioMembers([item, second], "示例", false, [2])).toEqual([item]);
    expect(filterCreditPortfolioMembers([item, second], "", true, [2])).toEqual([second]);
  });

  it.each([42, 100, 500])(
    "loads a %i-bond universe in bounded 20-row segments",
    (total) => {
      let visible = 20;
      expect(visible).toBeLessThanOrEqual(total);
      while (visible < total) {
        const next = nextCreditVisibleCount(visible, total);
        expect(next).toBeGreaterThan(visible);
        expect(next - visible).toBeLessThanOrEqual(20);
        visible = next;
      }
      expect(visible).toBe(total);
    },
  );

  it("repositions a replaced panel immediately below the sticky toolbar", () => {
    expect(calculateCreditWorkspaceScrollTop({
      currentScrollTop: 1697,
      panelTop: -1277,
      toolbarBottom: 134,
      gap: 12,
    })).toBe(274);
    expect(calculateCreditWorkspaceScrollTop({
      currentScrollTop: 20,
      panelTop: 80,
      toolbarBottom: 134,
    })).toBe(0);
  });
});
