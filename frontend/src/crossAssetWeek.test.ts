import { expect, it } from "vitest";
import {
  WEEK_SERIES, SAMPLE_END, SAMPLE_WEEK, formatWeekChange, lastCompletedFriday,
  validWeekDate, weekMarkdown, weeklyChange, weeklyWindow,
} from "./crossAssetWeek";

it("uses two adjacent seven-day windows without falling back to outside dates", () => {
  expect(weeklyWindow("2026-01-02")).toEqual({ start: "2025-12-27", previousStart: "2025-12-20", previousEnd: "2025-12-26" });
  expect(lastCompletedFriday("2026-11-07")).toBe("2026-11-06");
  expect(lastCompletedFriday("2026-11-06")).toBe("2026-10-30");
  expect(validWeekDate("2026-02-30")).toBe(false);
  const points = [
    { date: "2026-07-31", value: 110 },
    { date: "2026-08-01", value: 200 },
    { date: "2026-07-17", value: 90 },
    { date: "2026-07-25", value: 0 },
  ];
  const result = weeklyChange(WEEK_SERIES[0], points, SAMPLE_END);
  expect(result.current?.value).toBe(110);
  expect(result.previous).toBeUndefined();
  expect(result.change).toBeNull();
});

it("uses BP for bond yields and independently selects the last unambiguous dates", () => {
  expect(formatWeekChange(weeklyChange(WEEK_SERIES[1], SAMPLE_WEEK.bond.points, SAMPLE_END).change, "BP")).toBe("-3.00 BP");
  expect(formatWeekChange(weeklyChange(WEEK_SERIES[2], SAMPLE_WEEK.gold.points, SAMPLE_END).change, "%")).toBe("+1.00%");
  const result = weeklyChange(WEEK_SERIES[1], [
    { date: "2026-07-31", value: 0.2 },
    { date: "2026-07-31", value: 0.3 },
    { date: "2026-07-30", value: 0 },
    { date: "2026-07-24", value: -0.01 },
    { date: "2026-07-23", value: Infinity },
  ], SAMPLE_END);
  expect(result.current?.date).toBe("2026-07-30");
  expect(result.change).toBe(1);
});

it("does not serialize real points, observed dates or derived changes", () => {
  const draft = weekMarkdown(SAMPLE_END, { gold: { state: "latest", points: SAMPLE_WEEK.gold.points } }, "<测试>", false);
  expect(draft).toContain("上金所日线");
  expect(draft).toContain("&lt;测试&gt;");
  expect(draft).not.toMatch(/787\.8|2026-07-30|\+1\.00%/);
  expect(weekMarkdown(SAMPLE_END, SAMPLE_WEEK, "", true)).toContain("-3.00 BP");
});
