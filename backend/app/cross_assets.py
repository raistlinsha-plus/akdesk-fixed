"""Small, on-demand public-market preview. No numeric disk cache or AI use."""
from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
MARKER = "__AKDESK_CROSS__="
POLICY = {
    "storage_mode": "memory_only", "numeric_export": False,
    "numeric_evidence": False, "ai_processing_allowed": False,
    "authorization": "not_granted_by_akdesk",
    "notice": "免费公开源研究预览，不是授权实时行情。数值不落盘、不进入AI；导出/研究仅保存查询引用与自己的备注。机构用途需另核验上游授权。",
}
ASSETS: dict[str, dict[str, str]] = {
    "SSE:000001": {"name": "上证指数", "kind": "index", "symbol": "sh000001", "unit": "点", "currency": "CNY"},
    "CSI:000300": {"name": "沪深300", "kind": "index", "symbol": "sh000300", "unit": "点", "currency": "CNY"},
    "CSI:000905": {"name": "中证500", "kind": "index", "symbol": "sh000905", "unit": "点", "currency": "CNY"},
    "SZSE:399006": {"name": "创业板指", "kind": "index", "symbol": "sz399006", "unit": "点", "currency": "CNY"},
    "SGE:Au99.99": {"name": "黄金 Au99.99", "kind": "gold", "symbol": "Au99.99", "unit": "元/克", "currency": "CNY"},
}


def asset_spec(asset_id: str) -> dict[str, Any]:
    if asset_id not in ASSETS:
        raise ValueError("不支持的资产标识")
    item = ASSETS[asset_id]
    gold = item["kind"] == "gold"
    return {"id": asset_id, **item,
        "source": "上金所公开页面 / AKShare" if gold else "新浪公开行情 / AKShare",
        "source_url": "https://www.sge.com.cn/sjzx/mrhq" if gold else f'https://finance.sina.com.cn/realstock/company/{item["symbol"]}/nc.shtml',
        "terms_url": "https://akshare.akfamily.xyz/introduction.html"}


def reference_payload(asset_id: str) -> dict[str, Any]:
    spec = asset_spec(asset_id)
    return {"schema_version": 1, "storage_mode": "reference_only", "provider": "AKShare public preview",
        "asset_id": asset_id, "symbol": spec["symbol"], "source_url": spec["source_url"],
        "terms_url": spec["terms_url"], "ai_processing_allowed": False,
        "notice": "这是用户选择的查询引用，不含行情数值、观测日期或历史快照；重新查询可能变化。"}


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def observation(value: Any, now: datetime) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("年", "-").replace("月", "-").replace("日", "").replace("Z", "+00:00")
    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            return text if day <= now.date() else None
        stamp = datetime.fromisoformat(text)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=SHANGHAI)
        return stamp.isoformat() if stamp <= now + timedelta(minutes=2) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_history(records: list[dict], now: datetime, limit: int = 800) -> list[dict]:
    by_date: dict[str, float] = {}
    duplicate: set[str] = set()
    for row in records:
        raw = row.get("date", row.get("日期"))
        observed = observation(str(raw)[:10], now) if raw is not None else None
        close = number(row.get("close", row.get("收盘")))
        if observed is None or close is None or close <= 0:
            continue
        if observed in by_date and by_date[observed] != close:
            duplicate.add(observed)
        by_date[observed] = close
    return [{"date": day, "close": close} for day, close in sorted(by_date.items()) if day not in duplicate][-limit:]


def normalize_quote(spec: dict, row: dict, now: datetime) -> dict:
    price = number(row.get("price", row.get("最新价", row.get("现价"))))
    previous = number(row.get("previous_close", row.get("昨收")))
    price = price if price is not None and price > 0 else None
    previous = previous if previous is not None and previous > 0 else None
    observed = observation(row.get("observation_time", row.get("更新时间")), now)
    return {**spec, "price": price, "previous_close": previous,
        "change_pct": round((price / previous - 1) * 100, 6) if price and previous else None,
        "observation_time": observed, "fetched_at": now.isoformat(),
        "quote_kind": "public_quote" if price is not None else "unavailable",
        "state": "latest" if price is not None else "unavailable", "demo": False,
        "delay_seconds": None, "quality": "limited" if price is not None else "blocked",
        "warnings": ["延时未知；抓取时间不代表观测时间。"] + ([] if observed else ["源未提供可核验的观测日期/时点，不推定为今日实时行情。"])}


def isolated_request(mode: str, key: str) -> list[dict]:
    # Whitelist before creating a process; there is no arbitrary URL or symbol API.
    if mode not in {"quote", "history"} or (key not in {"index", "gold"} if mode == "quote" else key not in ASSETS):
        raise ValueError("不支持的行情请求")
    env = {**os.environ, "AKDESK_NO_BROWSER": "1", "AKDESK_NOTIFICATIONS": "0"}
    for name in ("AKDESK_FRED_API_KEY", "FRED_API_KEY", "AKDESK_AIHUBMIX_API_KEY", "AIHUBMIX_API_KEY"):
        env.pop(name, None)
    result = subprocess.run([sys.executable, "-m", "app.cross_assets_worker", mode, key],
        capture_output=True, text=True, timeout=18, env=env)
    lines = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
    if not lines or len(lines[-1]) > 8_000_000:
        raise RuntimeError("行情源未返回有效结果")
    value = json.loads(lines[-1])
    if value.get("rate_limited"):
        raise CrossRateLimit("来源限流，暂停请求")
    if not value.get("ok") or not isinstance(value.get("records"), list):
        raise RuntimeError("公开行情暂时不可用")
    return value["records"]


class CrossRateLimit(RuntimeError):
    pass


class CrossAssetService:
    def __init__(self, runner: Callable = isolated_request, *, demo: bool | None = None, clock: Callable = time.monotonic):
        self.runner, self.clock = runner, clock
        self.demo = os.getenv("AKDESK_DEMO") == "1" if demo is None else demo
        self._lock = threading.RLock()
        self._gates = {"sge": threading.RLock(), "sina": threading.RLock()}
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cooldown: dict[str, float] = {}

    def catalog(self) -> dict:
        return {"assets": [asset_spec(key) for key in ASSETS], "policy": copy.deepcopy(POLICY)}

    def _read(self, mode: str, key: str, ttl: int) -> tuple[Any, str, int]:
        cache_key = f"{mode}:{key}"
        upstream = "sge" if key == "gold" or key.startswith("SGE:") else "sina"
        # One bounded, sequential upstream request per process; concurrent pages dedupe.
        with self._gates[upstream]:
            now = self.clock()
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < ttl:
                return copy.deepcopy(cached[1]), "cached", int(now - cached[0])
            if self._cooldown.get(upstream, 0) > now:
                return (copy.deepcopy(cached[1]), "stale", int(now - cached[0])) if cached else (None, "unavailable", 0)
            try:
                data = self._demo(mode, key) if self.demo else self.runner(mode, key)
                if not isinstance(data, list) or not data:
                    raise ValueError("空数据")
                # Save normalized values, not provider exceptions/credentials/raw metadata.
                stamp = datetime.now(SHANGHAI)
                if mode == "history":
                    data = normalize_history(data, stamp)
                else:
                    rows = []
                    for asset_id in ASSETS:
                        spec = asset_spec(asset_id)
                        if spec["kind"] != key:
                            continue
                        matches = [row for row in data if str(row.get("symbol", row.get("代码", row.get("品种", "")))) == spec["symbol"]]
                        row = normalize_quote(spec, matches[-1] if matches else {}, stamp)
                        row["demo"] = self.demo
                        if self.demo:
                            row["observation_time"] = "2026-08-03"
                        rows.append(row)
                    data = rows
                    if not any(row["price"] is not None for row in rows):
                        raise ValueError("没有有效报价")
                if not data:
                    raise ValueError("没有有效观测")
                self._cache[cache_key] = (now, data)
                return copy.deepcopy(data), "demo" if self.demo else "latest", 0
            except Exception:
                # No immediate retry or source rotation on failure/limit.
                self._cooldown[upstream] = self.clock() + 600
                return (copy.deepcopy(cached[1]), "stale", int(now - cached[0])) if cached else (None, "unavailable", 0)

    def quotes(self, kind: str) -> dict:
        if kind not in {"index", "gold"}:
            raise ValueError("不支持的资产类别")
        rows, state, age = self._read("quote", kind, 300)
        if rows is None:
            rows = [normalize_quote(asset_spec(key), {}, datetime.now(SHANGHAI)) for key in ASSETS if ASSETS[key]["kind"] == kind]
        for row in rows:
            if row["price"] is not None:
                row["state"] = "demo" if row["demo"] else state
            if state in {"stale", "unavailable"}:
                row["warnings"].append("来源请求未完成或冷却中；不将旧缓存视为当前行情。")
            row["cache_age_seconds"] = age
        return {"data": rows, "policy": copy.deepcopy(POLICY), "state": state,
            "refresh_after_seconds": 300, "cooldown_seconds": 600 if state in {"stale", "unavailable"} else 0}

    def history(self, asset_id: str) -> dict:
        spec = asset_spec(asset_id)
        rows, state, age = self._read("history", asset_id, 21600)
        return {"asset": spec, "data": rows or [], "state": state, "demo": self.demo,
            "cache_age_seconds": age, "policy": copy.deepcopy(POLICY),
            "notice": "日频、非总回报序列；缺失日期不填充，不与盘中报价拼接计算收益。休市展示最后有效日期，源失败与休市分别说明。"}

    def peek(self, asset_id: str) -> dict | None:
        """Cached watchlist decoration must never trigger market IO."""
        spec = asset_spec(asset_id)
        with self._lock:
            cached = self._cache.get(f'quote:{spec["kind"]}')
            if not cached:
                return None
            row = next((copy.deepcopy(row) for row in cached[1] if row["id"] == asset_id), None)
            if row and self.clock() - cached[0] >= 300:
                row["state"] = "stale"
            return row

    def health_items(self):
        from .models import HealthItem
        items = []
        for kind, label in (("index", "股票指数公开源"), ("gold", "黄金公开源")):
            cached = self._cache.get(f"quote:{kind}")
            upstream = "sge" if kind == "gold" else "sina"
            cooling = self._cooldown.get(upstream, 0) > self.clock()
            rows = cached[1] if cached else []
            stale = bool(cached and self.clock() - cached[0] >= 300)
            items.append(HealthItem(adapter=f"cross_{kind}", label=label,
                state="degraded" if cached else "unavailable" if cooling else "not_checked",
                rows=sum(row["price"] is not None for row in rows),
                trust_level="partial" if cached else "unavailable" if cooling else "partial",
                quality_score=50 if cached else 0, cache_persisted=False,
                cache_age_seconds=int(self.clock()-cached[0]) if cached else None,
                message="公开源预览；观测时点和延时分别核验，数值不落盘。" + ("旧缓存；来源冷却中。" if stale or cooling else "尚未按需读取。" if not cached else "")))
        return items

    @staticmethod
    def _demo(mode: str, key: str) -> list[dict]:
        if mode == "quote":
            return [{"symbol": item["symbol"], "price": 700.0 if item["kind"] == "gold" else 3000 + index * 125,
                "previous_close": 690 if item["kind"] == "gold" else 2990 + index * 130}
                for index, item in enumerate(ASSETS.values()) if item["kind"] == key]
        return [{"date": (date(2026, 8, 3) - timedelta(days=offset)).isoformat(), "close": 700 - offset * .3 if key.startswith("SGE:") else 3000 - offset * 2}
            for offset in range(89, -1, -1) if (date(2026, 8, 3) - timedelta(days=offset)).weekday() < 5]
