import type {
  CurveSeries,
  EvidenceBasketItem,
  ResearchTopic,
  ResearchTopicComponent,
  ResearchTopicStatus,
  ResearchTopicTimelineItem,
} from "./types";

export function hasTimeSeriesData(
  categories: string[],
  series: CurveSeries[],
): boolean {
  return categories.length > 0 && series.some((item) =>
    item.values.some((value) => typeof value === "number" && Number.isFinite(value)),
  );
}

export type EvidenceBasketScope = "all" | "topic" | "unassigned";
export type EvidenceBasketSource = "all" | "fred" | "world_bank" | "gdelt" | "market";
export type TopicLibraryStatus = "all" | ResearchTopicStatus;
export type TopicTimelineCategory =
  | "all"
  | "evidence"
  | "research"
  | "project"
  | "release";

const EVIDENCE_EVENTS = new Set([
  "market_snapshot",
  "sovereign_update",
  "fred_reference",
  "gdelt_clue",
  "evidence",
]);

export function topicEvidenceEvents(
  timeline: ResearchTopicTimelineItem[],
): ResearchTopicTimelineItem[] {
  return timeline.filter((item) => EVIDENCE_EVENTS.has(item.event_type));
}

export function mergeTopicTimeline(
  current: ResearchTopicTimelineItem[],
  incoming: ResearchTopicTimelineItem[],
): ResearchTopicTimelineItem[] {
  const known = new Set(current.map((item) => item.id));
  return [...current, ...incoming.filter((item) => !known.has(item.id))];
}

export function addTopicComponent(
  components: ResearchTopicComponent[],
  candidate: ResearchTopicComponent,
): ResearchTopicComponent[] {
  if (components.some((item) => item.id === candidate.id)) return components;
  return [...components, candidate].sort(
    (left, right) => left.order - right.order || left.id.localeCompare(right.id),
  );
}

export function toggleNumericId(ids: number[], id: number): number[] {
  return ids.includes(id)
    ? ids.filter((item) => item !== id)
    : [...ids, id];
}

export function evidenceBasketSource(item: EvidenceBasketItem): EvidenceBasketSource {
  const source = `${item.source_summary} ${JSON.stringify(item.payload)}`.toUpperCase();
  if (source.includes("FRED")) return "fred";
  if (source.includes("WORLD BANK")) return "world_bank";
  if (source.includes("GDELT")) return "gdelt";
  return "market";
}

export function filterEvidenceBasket(
  items: EvidenceBasketItem[],
  filters: {
    scope: EvidenceBasketScope;
    source: EvidenceBasketSource;
    dateFrom: string;
    topicId: number | null;
  },
): EvidenceBasketItem[] {
  return items.filter((item) => {
    if (filters.scope === "topic" && item.topic_id !== filters.topicId) return false;
    if (filters.scope === "unassigned" && item.topic_id !== null) return false;
    if (filters.source !== "all" && evidenceBasketSource(item) !== filters.source) {
      return false;
    }
    if (filters.dateFrom && item.created_at.slice(0, 10) < filters.dateFrom) return false;
    return true;
  });
}

export function isRemoteTopicComponent(component: ResearchTopicComponent): boolean {
  return [
    "market_pulse",
    "market_history",
    "fred_chart",
    "sovereign_compare",
    "event_radar",
  ].includes(component.component_type);
}

export function filterTopicLibrary(
  topics: ResearchTopic[],
  query: string,
  status: TopicLibraryStatus,
): ResearchTopic[] {
  const term = query.trim().toLowerCase();
  return topics.filter((topic) => {
    if (status !== "all" && topic.status !== status) return false;
    if (!term) return true;
    return [
      topic.title,
      topic.question,
      topic.description,
      topic.research_object.name,
      ...topic.tags,
    ].some((value) => value.toLowerCase().includes(term));
  });
}

export function filterTopicTimeline(
  timeline: ResearchTopicTimelineItem[],
  filters: {
    category: TopicTimelineCategory;
    projectId: number | null;
    query: string;
  },
): ResearchTopicTimelineItem[] {
  const term = filters.query.trim().toLowerCase();
  return timeline.filter((item) => {
    if (filters.projectId !== null && item.project_id !== filters.projectId) return false;
    if (term && !`${item.title} ${item.summary} ${item.project_title}`.toLowerCase().includes(term)) {
      return false;
    }
    if (filters.category === "evidence") return EVIDENCE_EVENTS.has(item.event_type);
    if (filters.category === "research") {
      return ["note", "counter_evidence", "task", "review"].includes(item.event_type);
    }
    if (filters.category === "project") return item.event_type.startsWith("project_");
    if (filters.category === "release") return item.event_type === "release_review";
    return true;
  });
}
