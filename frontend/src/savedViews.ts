export interface SavedView<T> {
  id: string;
  name: string;
  value: T;
}

interface SavedViewEnvelope<T> {
  version: 1;
  views: Array<SavedView<T>>;
}

export function parseSavedViews<T>(
  raw: string | null,
  validateValue: (value: unknown) => value is T,
): { views: Array<SavedView<T>>; warning: string | null } {
  if (!raw) return { views: [], warning: null };
  try {
    const parsed: unknown = JSON.parse(raw);
    const candidates = Array.isArray(parsed)
      ? parsed
      : parsed &&
          typeof parsed === "object" &&
          "version" in parsed &&
          parsed.version === 1 &&
          "views" in parsed &&
          Array.isArray(parsed.views)
        ? parsed.views
        : null;
    if (!candidates) {
      return { views: [], warning: "保存视图格式已失效，已安全忽略" };
    }
    const views = candidates.filter(
      (item): item is SavedView<T> =>
        Boolean(
          item &&
            typeof item === "object" &&
            "id" in item &&
            "name" in item &&
            "value" in item &&
            typeof item.id === "string" &&
            typeof item.name === "string" &&
            item.name.trim() &&
            validateValue(item.value),
        ),
    );
    return {
      views,
      warning:
        views.length === candidates.length
          ? null
          : "部分损坏的保存视图已安全忽略",
    };
  } catch {
    return { views: [], warning: "保存视图无法解析，已安全忽略" };
  }
}

export function serializeSavedViews<T>(views: Array<SavedView<T>>): string {
  const envelope: SavedViewEnvelope<T> = { version: 1, views };
  return JSON.stringify(envelope);
}

export function upsertSavedView<T>(
  views: Array<SavedView<T>>,
  value: T,
  rawName: string,
  createId: () => string = () => `${Date.now()}`,
): { views: Array<SavedView<T>>; id: string; overwritten: boolean } | null {
  const name = rawName.trim();
  if (!name) return null;
  const existing = views.find((item) => item.name === name);
  const id = existing?.id ?? createId();
  return {
    views: [
      ...views.filter((item) => item.name !== name),
      { id, name, value },
    ],
    id,
    overwritten: Boolean(existing),
  };
}

export function clampPage(page: number, total: number, pageSize: number): number {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return Math.max(1, Math.min(page, pages));
}
