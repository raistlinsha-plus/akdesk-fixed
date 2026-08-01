import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api";
import type { WatchlistItem } from "../types";

interface WatchlistContextValue {
  items: WatchlistItem[];
  loading: boolean;
  isSaved: (objectType: string, objectId: string) => boolean;
  isBusy: (objectType: string, objectId: string) => boolean;
  toggle: (objectType: string, objectId: string, name: string) => Promise<void>;
  update: (itemId: number, values: Record<string, unknown>) => Promise<WatchlistItem>;
  remove: (itemId: number) => Promise<void>;
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

function key(objectType: string, objectId: string): string {
  return objectType + ":" + objectId;
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    apiGet<WatchlistItem[]>("/watchlists")
      .then((result) => {
        if (active) setItems(result);
      })
      .catch(() => {
        if (active) setItems([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const indexed = useMemo(
    () => new Map(items.map((item) => [key(item.object_type, item.object_id), item])),
    [items],
  );

  const isSaved = useCallback(
    (objectType: string, objectId: string) => indexed.has(key(objectType, objectId)),
    [indexed],
  );

  const isBusy = useCallback(
    (objectType: string, objectId: string) => busy.has(key(objectType, objectId)),
    [busy],
  );

  async function toggle(objectType: string, objectId: string, name: string) {
    const itemKey = key(objectType, objectId);
    if (busy.has(itemKey)) return;
    setBusy((current) => new Set(current).add(itemKey));
    try {
      const existing = indexed.get(itemKey);
      if (existing) {
        await apiDelete("/watchlists/" + existing.id);
        setItems((current) => current.filter((item) => item.id !== existing.id));
      } else {
        const saved = await apiPost<WatchlistItem>("/watchlists", {
          object_type: objectType,
          object_id: objectId,
          name,
          note: "",
        });
        setItems((current) => [
          saved,
          ...current.filter((item) => item.id !== saved.id),
        ]);
      }
    } finally {
      setBusy((current) => {
        const next = new Set(current);
        next.delete(itemKey);
        return next;
      });
    }
  }

  async function remove(itemId: number) {
    await apiDelete("/watchlists/" + itemId);
    setItems((current) => current.filter((item) => item.id !== itemId));
  }

  async function update(itemId: number, values: Record<string, unknown>) {
    const saved = await apiPatch<WatchlistItem>("/watchlists/" + itemId, values);
    setItems((current) =>
      current
        .map((item) => (item.id === saved.id ? saved : item))
        .sort((left, right) => Number(right.pinned) - Number(left.pinned)),
    );
    return saved;
  }

  return (
    <WatchlistContext.Provider
      value={{ items, loading, isSaved, isBusy, toggle, update, remove }}
    >
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist(): WatchlistContextValue {
  const context = useContext(WatchlistContext);
  if (!context) {
    throw new Error("useWatchlist 必须在 WatchlistProvider 中使用");
  }
  return context;
}
