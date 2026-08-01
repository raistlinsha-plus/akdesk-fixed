import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "../api";
import type { Dataset } from "../types";

export function useDataset<T>(path: string, refreshSeed = 0) {
  const [dataset, setDataset] = useState<Dataset<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const previousRefreshSeed = useRef(refreshSeed);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    // AKShare work is serialized to protect its shared V8 runtime. A cold
    // dashboard can therefore legitimately queue behind another source.
    const timeout = window.setTimeout(() => controller.abort(), 75_000);
    setLoading(true);
    setError(null);
    const separator = path.includes("?") ? "&" : "?";
    const refreshChanged = previousRefreshSeed.current !== refreshSeed;
    previousRefreshSeed.current = refreshSeed;
    const requestPath =
      nonce > 0 || refreshChanged
        ? path + separator + "refresh=true&_=" + String(nonce + refreshSeed)
        : path;

    apiGet<Dataset<T>>(requestPath, { signal: controller.signal })
      .then((result) => {
        if (active) {
          setDataset(result);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof DOMException && reason.name === "AbortError"
              ? "数据请求超时，请稍后重试"
              : reason instanceof Error
                ? reason.message
                : "加载失败",
          );
        }
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [nonce, path, refreshSeed]);

  return { dataset, loading, error, reload };
}
