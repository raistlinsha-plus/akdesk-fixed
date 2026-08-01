export function canWatchItem(
  objectId: string,
  qualityState?: "trusted" | "partial" | "suspicious",
): boolean {
  return Boolean(objectId.trim()) && qualityState !== "suspicious";
}
