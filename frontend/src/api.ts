const API_ROOT = "/api/v1";
const sharedGetRequests = new Map<string, Promise<unknown>>();
const sharedGetCache = new Map<string, { expiresAt: number; value: unknown }>();
const LOCAL_SERVICE_UNAVAILABLE =
  "无法连接本地 AKDesk 服务。请确认 macOS 启动窗口仍在运行；若已关闭，请重新双击 start-macos.command 后重试。";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function isAbortError(reason: unknown) {
  return reason instanceof Error && reason.name === "AbortError";
}

async function fetchApi(
  input: string,
  init?: RequestInit,
  options?: { timeoutMs?: number; timeoutMessage?: string },
): Promise<Response> {
  const controller = options?.timeoutMs ? new AbortController() : null;
  let timedOut = false;
  const timer = controller
    ? window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, options?.timeoutMs)
    : null;
  try {
    return await fetch(input, {
      ...init,
      signal: controller?.signal ?? init?.signal,
    });
  } catch (reason) {
    if (timedOut) {
      throw new ApiError(
        0,
        options?.timeoutMessage ?? "本地服务响应超时，请稍后重试。",
      );
    }
    if (isAbortError(reason)) throw reason;
    throw new ApiError(0, LOCAL_SERVICE_UNAVAILABLE);
  } finally {
    if (timer != null) window.clearTimeout(timer);
  }
}

export async function apiGet<T>(
  path: string,
  options?: { signal?: AbortSignal },
): Promise<T> {
  const response = await fetchApi(API_ROOT + path, {
    signal: options?.signal,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  return response.json() as Promise<T>;
}

/** Share identical read requests and briefly reuse their result across widgets. */
export function apiGetShared<T>(
  path: string,
  options?: { ttlMs?: number; force?: boolean },
): Promise<T> {
  const ttlMs = Math.max(0, options?.ttlMs ?? 30_000);
  if (options?.force) sharedGetCache.delete(path);
  const cached = sharedGetCache.get(path);
  if (!options?.force && cached && cached.expiresAt > Date.now()) {
    return Promise.resolve(cached.value as T);
  }
  const pending = sharedGetRequests.get(path);
  if (!options?.force && pending) return pending as Promise<T>;

  const request = apiGet<T>(path)
    .then((value) => {
      if (ttlMs > 0 && sharedGetRequests.get(path) === request) {
        sharedGetCache.set(path, { expiresAt: Date.now() + ttlMs, value });
      }
      return value;
    })
    .finally(() => {
      if (sharedGetRequests.get(path) === request) sharedGetRequests.delete(path);
    });
  sharedGetRequests.set(path, request);
  return request;
}

export function clearSharedApiCache(pathPrefix = "") {
  for (const path of sharedGetCache.keys()) {
    if (!pathPrefix || path.startsWith(pathPrefix)) sharedGetCache.delete(path);
  }
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  options?: { timeoutMs?: number; timeoutMessage?: string },
): Promise<T> {
  const response = await fetchApi(
    API_ROOT + path,
    {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    },
    options,
  );
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetchApi(API_ROOT + path, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetchApi(API_ROOT + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  return response.json() as Promise<T>;
}

export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const response = await fetchApi(API_ROOT + path);
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = match?.[1] || fallbackName;
  link.click();
  URL.revokeObjectURL(url);
}

export async function apiPostFile<T>(path: string, file: File): Promise<T> {
  const response = await fetchApi(API_ROOT + path, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return response.json() as Promise<T>;
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? "请求失败（" + response.status + "）";
  } catch {
    return "请求失败（" + response.status + "）";
  }
}
