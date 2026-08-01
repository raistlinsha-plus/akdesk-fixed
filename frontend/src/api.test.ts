import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiGetShared, clearSharedApiCache } from "./api";

afterEach(() => {
  clearSharedApiCache();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("shared API reads", () => {
  it("maps browser network failures to a local service recovery message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(apiGet("/health")).rejects.toThrow(
      "无法连接本地 AKDesk 服务",
    );
  });

  it("deduplicates in-flight reads and reuses the short cache", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ value: 42 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const [first, second] = await Promise.all([
      apiGetShared<{ value: number }>("/macro/chart?series=DGS10"),
      apiGetShared<{ value: number }>("/macro/chart?series=DGS10"),
    ]);
    const third = await apiGetShared<{ value: number }>(
      "/macro/chart?series=DGS10",
    );

    expect(first.value).toBe(42);
    expect(second).toEqual(first);
    expect(third).toEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retain failed reads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGetShared("/sovereign/compare")).rejects.toThrow();
    await expect(apiGetShared("/sovereign/compare")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("forces a fresh read and replaces the cached value", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ value: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ value: 2 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGetShared<{ value: number }>("/history?adapter=yields"))
      .resolves.toEqual({ value: 1 });
    await expect(
      apiGetShared<{ value: number }>("/history?adapter=yields", { force: true }),
    ).resolves.toEqual({ value: 2 });
    await expect(apiGetShared<{ value: number }>("/history?adapter=yields"))
      .resolves.toEqual({ value: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
