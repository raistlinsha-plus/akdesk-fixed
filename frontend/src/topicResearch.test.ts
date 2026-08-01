import { describe, expect, it } from "vitest";
import {
  addTopicComponent,
  filterEvidenceBasket,
  filterTopicLibrary,
  filterTopicTimeline,
  hasTimeSeriesData,
  isRemoteTopicComponent,
  mergeTopicTimeline,
  toggleNumericId,
  topicEvidenceEvents,
} from "./topicResearch";
import type {
  EvidenceBasketItem,
  ResearchTopicComponent,
  ResearchTopic,
  ResearchTopicTimelineItem,
} from "./types";

describe("topic research helpers", () => {
  it("keeps saved components unique and ordered", () => {
    const summary: ResearchTopicComponent = {
      id: "summary",
      component_type: "project_summary",
      title: "项目摘要",
      config: {},
      order: 30,
    };
    const market: ResearchTopicComponent = {
      id: "market",
      component_type: "market_pulse",
      title: "市场",
      config: {},
      order: 10,
    };
    expect(addTopicComponent([summary], market).map((item) => item.id)).toEqual([
      "market",
      "summary",
    ]);
    expect(addTopicComponent([market, summary], market)).toHaveLength(2);
  });

  it("separates evidence events from project administration", () => {
    const events = [
      { id: "1", event_type: "fred_reference" },
      { id: "2", event_type: "project_updated" },
      { id: "3", event_type: "market_snapshot" },
    ] as ResearchTopicTimelineItem[];
    expect(topicEvidenceEvents(events).map((item) => item.id)).toEqual(["1", "3"]);
  });

  it("merges cursor pages without duplicating overlapping records", () => {
    const current = [{ id: "1" }, { id: "2" }] as ResearchTopicTimelineItem[];
    const incoming = [{ id: "2" }, { id: "3" }] as ResearchTopicTimelineItem[];
    expect(mergeTopicTimeline(current, incoming).map((item) => item.id)).toEqual(["1", "2", "3"]);
  });

  it("toggles project and basket selections without duplicates", () => {
    expect(toggleNumericId([1, 2], 2)).toEqual([1]);
    expect(toggleNumericId([1], 3)).toEqual([1, 3]);
  });

  it("filters evidence basket by topic, source and date", () => {
    const items = [
      {
        id: 1,
        topic_id: 7,
        source_summary: "FRED · DGS10",
        payload: { provider: "FRED" },
        created_at: "2026-07-10T10:00:00",
      },
      {
        id: 2,
        topic_id: null,
        source_summary: "AKShare · ChinaBond",
        payload: {},
        created_at: "2026-07-15T10:00:00",
      },
      {
        id: 3,
        topic_id: 7,
        source_summary: "GDELT 事件线索（待核验）",
        payload: { provider: "GDELT" },
        created_at: "2026-07-16T10:00:00",
      },
    ] as EvidenceBasketItem[];

    expect(
      filterEvidenceBasket(items, {
        scope: "topic",
        source: "fred",
        dateFrom: "2026-07-01",
        topicId: 7,
      }).map((item) => item.id),
    ).toEqual([1]);
    expect(
      filterEvidenceBasket(items, {
        scope: "unassigned",
        source: "all",
        dateFrom: "2026-07-12",
        topicId: 7,
      }).map((item) => item.id),
    ).toEqual([2]);
    expect(
      filterEvidenceBasket(items, {
        scope: "topic",
        source: "gdelt",
        dateFrom: "",
        topicId: 7,
      }).map((item) => item.id),
    ).toEqual([3]);
  });

  it("identifies only data-fetching components as remote", () => {
    expect(isRemoteTopicComponent({ component_type: "fred_chart" } as ResearchTopicComponent)).toBe(true);
    expect(isRemoteTopicComponent({ component_type: "event_radar" } as ResearchTopicComponent)).toBe(true);
    expect(isRemoteTopicComponent({ component_type: "project_summary" } as ResearchTopicComponent)).toBe(false);
  });

  it("treats empty or all-null history as unavailable for charting", () => {
    expect(hasTimeSeriesData([], [])).toBe(false);
    expect(hasTimeSeriesData(["2026-07-17"], [{ name: "10Y", values: [null] }])).toBe(false);
    expect(hasTimeSeriesData(["2026-07-17"], [{ name: "10Y", values: [1.75] }])).toBe(true);
  });

  it("filters a large topic library by status and searchable fields", () => {
    const topics = [
      { id: 1, title: "中国利率", question: "曲线如何变化", description: "", status: "active", tags: ["久期"], research_object: { name: "中国国债" } },
      { id: 2, title: "人民币", question: "汇率压力", description: "外汇", status: "review", tags: [], research_object: { name: "人民币利率" } },
    ] as ResearchTopic[];
    expect(filterTopicLibrary(topics, "久期", "all").map((item) => item.id)).toEqual([1]);
    expect(filterTopicLibrary(topics, "人民币", "review").map((item) => item.id)).toEqual([2]);
  });

  it("filters timeline events by category, project and text", () => {
    const events = [
      { id: "1", event_type: "fred_reference", project_id: 1, title: "DGS10", summary: "利率", project_title: "美债" },
      { id: "2", event_type: "task", project_id: 1, title: "核对数据", summary: "", project_title: "美债" },
      { id: "3", event_type: "project_updated", project_id: 2, title: "结论变化", summary: "", project_title: "人民币" },
    ] as ResearchTopicTimelineItem[];
    expect(filterTopicTimeline(events, { category: "evidence", projectId: 1, query: "DGS" }).map((item) => item.id)).toEqual(["1"]);
    expect(filterTopicTimeline(events, { category: "project", projectId: null, query: "人民币" }).map((item) => item.id)).toEqual(["3"]);
  });
});
