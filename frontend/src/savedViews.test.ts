import { describe, expect, it } from "vitest";
import {
  clampPage,
  parseSavedViews,
  serializeSavedViews,
  upsertSavedView,
} from "./savedViews";

interface FilterView {
  filter: string;
}

const isFilterView = (value: unknown): value is FilterView =>
  Boolean(
    value &&
      typeof value === "object" &&
      "filter" in value &&
      typeof value.filter === "string",
  );

describe("saved views", () => {
  it("loads versioned and legacy views while rejecting invalid entries", () => {
    const valid = { id: "one", name: "高收益", value: { filter: "high" } };
    expect(
      parseSavedViews(serializeSavedViews([valid]), isFilterView).views,
    ).toEqual([valid]);
    expect(parseSavedViews(JSON.stringify([valid]), isFilterView).views).toEqual([
      valid,
    ]);

    const damaged = parseSavedViews(
      JSON.stringify([valid, { id: "bad", name: "损坏", value: {} }]),
      isFilterView,
    );
    expect(damaged.views).toEqual([valid]);
    expect(damaged.warning).toContain("损坏");
  });

  it("safely ignores malformed storage", () => {
    expect(parseSavedViews("{bad-json", isFilterView)).toEqual({
      views: [],
      warning: "保存视图无法解析，已安全忽略",
    });
  });

  it("overwrites a same-name view without changing its id", () => {
    const original = [{ id: "one", name: "我的视图", value: { filter: "old" } }];
    const result = upsertSavedView(
      original,
      { filter: "new" },
      "我的视图",
      () => "two",
    );
    expect(result).toEqual({
      views: [{ id: "one", name: "我的视图", value: { filter: "new" } }],
      id: "one",
      overwritten: true,
    });
  });

  it("clamps pagination after filters shrink a result set", () => {
    expect(clampPage(5, 51, 50)).toBe(2);
    expect(clampPage(5, 0, 50)).toBe(1);
  });
});
