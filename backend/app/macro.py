from __future__ import annotations

import math
import re
import statistics
import time
from datetime import date, datetime, timedelta
from threading import RLock
from typing import Any, Callable

import httpx

from . import __version__
from .database import Database
from .models import Dataset, HealthItem, SourceMeta
from .settings import FredSecretStore


FRED_NOTICE = (
    "This product uses the FRED® API but is not endorsed or certified by "
    "the Federal Reserve Bank of St. Louis."
)
FRED_TERMS_URL = "https://fred.stlouisfed.org/legal/terms/"
FRED_STORAGE_NOTICE = (
    "FRED 观测值仅在当前请求中处理，不写入本地数据库；研究项目只保存序列与变换引用。"
)


FRED_CURATED_SERIES: list[dict[str, str]] = [
    {"series_id": "DFF", "title_zh": "有效联邦基金利率", "topic": "政策与流动性", "units": "%", "frequency": "Daily"},
    {"series_id": "SOFR", "title_zh": "SOFR", "topic": "政策与流动性", "units": "%", "frequency": "Daily"},
    {"series_id": "DGS2", "title_zh": "美国国债 2Y", "topic": "美国利率", "units": "%", "frequency": "Daily"},
    {"series_id": "DGS10", "title_zh": "美国国债 10Y", "topic": "美国利率", "units": "%", "frequency": "Daily"},
    {"series_id": "DGS30", "title_zh": "美国国债 30Y", "topic": "美国利率", "units": "%", "frequency": "Daily"},
    {"series_id": "T10Y2Y", "title_zh": "美债 10Y–2Y 利差", "topic": "美国利率", "units": "%", "frequency": "Daily"},
    {"series_id": "T10Y3M", "title_zh": "美债 10Y–3M 利差", "topic": "美国利率", "units": "%", "frequency": "Daily"},
    {"series_id": "DFII10", "title_zh": "美国 10Y 实际利率", "topic": "通胀与实际利率", "units": "%", "frequency": "Daily"},
    {"series_id": "T10YIE", "title_zh": "美国 10Y 盈亏平衡通胀", "topic": "通胀与实际利率", "units": "%", "frequency": "Daily"},
    {"series_id": "CPIAUCSL", "title_zh": "美国 CPI", "topic": "通胀与实际利率", "units": "Index", "frequency": "Monthly"},
    {"series_id": "CPILFESL", "title_zh": "美国核心 CPI", "topic": "通胀与实际利率", "units": "Index", "frequency": "Monthly"},
    {"series_id": "PCEPI", "title_zh": "美国 PCE 价格指数", "topic": "通胀与实际利率", "units": "Index", "frequency": "Monthly"},
    {"series_id": "PCEPILFE", "title_zh": "美国核心 PCE 价格指数", "topic": "通胀与实际利率", "units": "Index", "frequency": "Monthly"},
    {"series_id": "PAYEMS", "title_zh": "美国非农就业", "topic": "就业与增长", "units": "Thousands", "frequency": "Monthly"},
    {"series_id": "UNRATE", "title_zh": "美国失业率", "topic": "就业与增长", "units": "%", "frequency": "Monthly"},
    {"series_id": "ICSA", "title_zh": "美国初请失业金人数", "topic": "就业与增长", "units": "Number", "frequency": "Weekly"},
    {"series_id": "GDPC1", "title_zh": "美国实际 GDP", "topic": "就业与增长", "units": "Billions", "frequency": "Quarterly"},
    {"series_id": "INDPRO", "title_zh": "美国工业生产指数", "topic": "就业与增长", "units": "Index", "frequency": "Monthly"},
    {"series_id": "RSAFS", "title_zh": "美国零售销售", "topic": "就业与增长", "units": "Millions", "frequency": "Monthly"},
    {"series_id": "M2SL", "title_zh": "美国 M2", "topic": "政策与流动性", "units": "Billions", "frequency": "Monthly"},
]

CURATED_BY_ID = {item["series_id"]: item for item in FRED_CURATED_SERIES}
SERIES_PATTERN = re.compile(r"^[A-Z0-9._-]{1,40}$")


class FredNotConfiguredError(RuntimeError):
    pass


class MacroProviderError(RuntimeError):
    pass


def transform_observations(
    observations: list[dict[str, Any]],
    transform: str,
    frequency: str,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in observations:
        raw = item.get("value")
        try:
            value = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and not math.isfinite(value):
            value = None
        prepared.append({**item, "value": value})
    if transform == "level":
        return prepared
    values = [item.get("value") for item in prepared]
    valid_values = [float(value) for value in values if value is not None]
    transformed: list[dict[str, Any]] = []
    if transform == "change":
        for index, item in enumerate(prepared):
            current = values[index]
            previous = values[index - 1] if index else None
            value = (
                float(current) - float(previous)
                if current is not None and previous is not None
                else None
            )
            transformed.append({**item, "value": value})
        return transformed
    if transform == "normalize":
        base = next((value for value in valid_values if value != 0), None)
        return [
            {
                **item,
                "value": float(value) / base * 100
                if value is not None and base is not None
                else None,
            }
            for item, value in zip(prepared, values, strict=True)
        ]
    if transform == "zscore":
        mean = statistics.fmean(valid_values) if valid_values else 0
        deviation = statistics.pstdev(valid_values) if len(valid_values) > 1 else 0
        return [
            {
                **item,
                "value": (float(value) - mean) / deviation
                if value is not None and deviation
                else (0.0 if value is not None and valid_values else None),
            }
            for item, value in zip(prepared, values, strict=True)
        ]
    if transform == "yoy":
        raise ValueError("同比必须使用 FRED 官方 pc1 口径")
    raise ValueError("不支持的序列变换")


class MacroService:
    def __init__(
        self,
        database: Database,
        secret_store: FredSecretStore | None = None,
        request_json: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database = database
        self.secret_store = secret_store or FredSecretStore()
        self._request_override = request_json
        self._sleep = sleep
        self._lock = RLock()
        self._verification_state = (
            "unverified" if self.secret_store.status().configured else "not_configured"
        )
        self._last_verified_at: datetime | None = None
        self._circuit_open_until: float | None = None
        self._failure_count = 0
        self.storage_calibration = self.database.calibrate_fred_storage()
        self._health = HealthItem(
            adapter="fred_macro",
            label="FRED 美国宏观",
            state="not_checked",
            market_status="daily",
            market_status_label="按发布更新",
            execution_mode="in_process_http",
            trust_level="unavailable",
            message=(
                "FRED API Key 已配置，等待连接验证"
                if self.secret_store.status().configured
                else "尚未配置 FRED API Key"
            ),
        )

    def start_scheduler(self) -> None:
        # FRED data is intentionally request-scoped in v0.6.0.1.  A background
        # scheduler would turn transient API responses back into an implicit
        # cache, so this lifecycle hook remains a no-op for compatibility.
        return None

    def stop_scheduler(self) -> None:
        return None

    def clear_cache(self) -> None:
        self.database.clear_macro_cache()
        self._health = self._health.model_copy(
            update={
                "state": "not_checked",
                "last_success_at": None,
                "observation_time": None,
                "rows": 0,
                "message": (
                    "等待首次 FRED 数据检查"
                    if self.secret_store.get()
                    else "尚未配置 FRED API Key"
                ),
                "cache_age_seconds": None,
                "cache_persisted": False,
                "trust_level": "unavailable",
            }
        )

    def integration_status(self) -> dict[str, Any]:
        status = self.secret_store.status()
        if not status.configured:
            self._verification_state = "not_configured"
            self._last_verified_at = None
        elif self._verification_state == "not_configured":
            self._verification_state = "unverified"
        return {
            "provider": "fred",
            "configured": status.configured,
            "verified": self._verification_state == "verified",
            "verification_state": self._verification_state,
            "last_verified_at": self._last_verified_at,
            "credential_source": status.source,
            "notice": FRED_NOTICE,
            "storage_notice": FRED_STORAGE_NOTICE,
            "storage_mode": "request_scoped",
            "terms_url": FRED_TERMS_URL,
        }

    def credential_changed(self) -> None:
        configured = self.secret_store.status().configured
        self._verification_state = "unverified" if configured else "not_configured"
        self._last_verified_at = None
        self._failure_count = 0
        self._circuit_open_until = None
        self._health = self._health.model_copy(
            update={
                "state": "not_checked",
                "message": (
                    "FRED API Key 已保存，等待连接验证"
                    if configured
                    else "尚未配置 FRED API Key"
                ),
                "trust_level": "unavailable",
                "circuit_state": "closed",
                "next_retry_at": None,
                "consecutive_failures": 0,
            }
        )

    def catalog(self, query: str = "", topic: str = "") -> list[dict[str, Any]]:
        term = query.strip().lower()
        results: list[dict[str, Any]] = []
        for curated in FRED_CURATED_SERIES:
            if topic and curated["topic"] != topic:
                continue
            merged = {
                **curated,
                "provider": "fred",
                "title": curated["title_zh"],
                "source_url": f"https://fred.stlouisfed.org/series/{curated['series_id']}",
                "cached": False,
                "storage_mode": "request_scoped",
                "last_updated": None,
            }
            haystack = " ".join(
                str(merged.get(key) or "")
                for key in ("series_id", "title", "title_zh", "topic")
            ).lower()
            if term and term not in haystack:
                continue
            results.append(merged)
        return results

    def _request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._request_override is not None:
            return self._request_override(endpoint, params)
        for attempt in range(3):
            try:
                response = httpx.get(
                    "https://api.stlouisfed.org/fred/" + endpoint,
                    params=params,
                    timeout=15,
                    follow_redirects=True,
                    headers={
                        "User-Agent": f"AKDesk-Fixed/{__version__} personal-research"
                    },
                )
            except httpx.RequestError as exc:
                if attempt < 2:
                    self._sleep(0.25 * (2**attempt))
                    continue
                raise MacroProviderError("FRED 网络连接失败，请稍后重试") from exc
            if response.status_code in {401, 403}:
                raise MacroProviderError("FRED API Key 验证失败")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(2.0, max(0.25, float(retry_after)))
                    except ValueError:
                        delay = 0.25 * (2**attempt)
                    self._sleep(delay)
                    continue
                message = (
                    "FRED 请求过于频繁，请稍后重试"
                    if response.status_code == 429
                    else "FRED 服务暂时不可用，请稍后重试"
                )
                raise MacroProviderError(message)
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MacroProviderError("FRED 返回了无法识别的数据") from exc
            if not isinstance(payload, dict):
                raise MacroProviderError("FRED 返回了无法识别的数据")
            return payload
        raise MacroProviderError("FRED 请求失败，请稍后重试")

    def _begin_request(self) -> None:
        if self._circuit_open_until is None:
            return
        now = time.monotonic()
        if now < self._circuit_open_until:
            seconds = max(1, round(self._circuit_open_until - now))
            raise MacroProviderError(f"FRED 暂时熔断，请在 {seconds} 秒后重试")
        self._health = self._health.model_copy(
            update={"circuit_state": "half_open", "next_retry_at": None}
        )

    def _record_failure(self, exc: Exception, started: float) -> None:
        self._failure_count += 1
        opened = self._failure_count >= 3
        next_retry = None
        if opened:
            self._circuit_open_until = time.monotonic() + 60
            next_retry = datetime.now() + timedelta(seconds=60)
        if "Key 验证失败" in str(exc):
            self._verification_state = "failed"
        self._health = self._health.model_copy(
            update={
                "state": "unavailable",
                "last_failure_at": datetime.now(),
                "last_attempt_at": datetime.now(),
                "consecutive_failures": self._failure_count,
                "message": str(exc)[:300],
                "latency_ms": round((time.perf_counter() - started) * 1_000),
                "trust_level": "unavailable",
                "cache_persisted": False,
                "circuit_state": "open" if opened else "closed",
                "next_retry_at": next_retry,
            }
        )

    def _record_success(
        self, *, started: float, observations: list[dict[str, Any]], message: str
    ) -> None:
        now = datetime.now()
        self._failure_count = 0
        self._circuit_open_until = None
        self._verification_state = "verified"
        self._last_verified_at = now
        self._health = HealthItem(
            adapter="fred_macro",
            label="FRED 美国宏观",
            state="healthy",
            last_success_at=now,
            observation_time=observations[-1]["date"] if observations else None,
            rows=len(observations),
            latency_ms=round((time.perf_counter() - started) * 1_000),
            message=message,
            last_attempt_at=now,
            cache_persisted=False,
            market_status="daily",
            market_status_label="按发布更新",
            execution_mode="in_process_http",
            trust_level="trusted",
            circuit_state="closed",
        )

    def _source_details(
        self, series_id: str, api_key: str
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        release: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        try:
            release_payload = self._request_json(
                "series/release",
                {"series_id": series_id, "api_key": api_key, "file_type": "json"},
            )
            release_rows = release_payload.get("releases")
            if isinstance(release_rows, list) and release_rows:
                release = release_rows[0] if isinstance(release_rows[0], dict) else {}
            release_id = release.get("id")
            if release_id is not None:
                source_payload = self._request_json(
                    "release/sources",
                    {
                        "release_id": release_id,
                        "api_key": api_key,
                        "file_type": "json",
                    },
                )
                source_rows = source_payload.get("sources")
                if isinstance(source_rows, list):
                    sources = [item for item in source_rows if isinstance(item, dict)]
        except MacroProviderError:
            warnings.append("原始来源机构查询失败，请通过 FRED 序列页核验")
        names = [str(item.get("name") or "").strip() for item in sources]
        names = [name for name in names if name]
        source_links = [str(item.get("link") or "").strip() for item in sources]
        source_links = [link for link in source_links if link]
        organization = "; ".join(names) or "See FRED series notes"
        return (
            {
                "release_name": release.get("name"),
                "release_url": release.get("link"),
                "source_organization": organization,
                "original_source_url": source_links[0] if source_links else release.get("link"),
            },
            warnings,
        )

    def series(
        self,
        series_id: str,
        *,
        years: int = 10,
        refresh: bool = False,
        observation_units: str = "lin",
    ) -> Dataset:
        normalized = series_id.strip().upper()
        if not SERIES_PATTERN.fullmatch(normalized) or normalized not in CURATED_BY_ID:
            raise KeyError(series_id)
        years = max(1, min(years, 50))
        start = (date.today() - timedelta(days=round(years * 365.25))).isoformat()
        api_key = self.secret_store.get()
        if not api_key:
            self._health = self._health.model_copy(
                update={
                    "state": "not_checked",
                    "message": "尚未配置 FRED API Key",
                    "last_attempt_at": datetime.now(),
                }
            )
            raise FredNotConfiguredError("请先在宏观数据库页面配置 FRED API Key")

        started = time.perf_counter()
        self._begin_request()
        try:
            with self._lock:
                series_payload = self._request_json(
                    "series",
                    {"series_id": normalized, "api_key": api_key, "file_type": "json"},
                )
                observations_payload = self._request_json(
                    "series/observations",
                    {
                        "series_id": normalized,
                        "api_key": api_key,
                        "file_type": "json",
                        "observation_start": start,
                        "sort_order": "asc",
                        "units": observation_units,
                    },
                )
                source_details, source_warnings = self._source_details(
                    normalized, api_key
                )
            series_rows = series_payload.get("seriess")
            observation_rows = observations_payload.get("observations")
            if not isinstance(series_rows, list) or not series_rows:
                raise MacroProviderError("FRED 未返回序列元数据")
            if not isinstance(observation_rows, list):
                raise MacroProviderError("FRED 未返回序列观测值")
            raw = series_rows[0]
            curated = CURATED_BY_ID[normalized]
            now = datetime.now().isoformat()
            organization = str(source_details.get("source_organization") or "")
            metadata = {
                "provider": "fred",
                "series_id": normalized,
                "title": str(raw.get("title") or curated["title_zh"]),
                "title_zh": curated["title_zh"],
                "topic": curated["topic"],
                "units": str(raw.get("units") or curated["units"]),
                "frequency": str(raw.get("frequency") or curated["frequency"]),
                "seasonal_adjustment": str(raw.get("seasonal_adjustment") or ""),
                "notes": str(raw.get("notes") or ""),
                **source_details,
                "source_url": f"https://fred.stlouisfed.org/series/{normalized}",
                "last_updated": raw.get("last_updated"),
                "realtime_start": raw.get("realtime_start"),
                "realtime_end": raw.get("realtime_end"),
                "license": "FRED Terms of Use and original source restrictions",
                "terms_url": FRED_TERMS_URL,
                "attribution": (
                    f"{organization}; retrieved via FRED ({normalized})"
                    if organization and organization != "See FRED series notes"
                    else f"Retrieved via FRED ({normalized}); see series notes for original source"
                ),
                "fetched_at": now,
                "storage_mode": "request_scoped",
                "observation_units": observation_units,
            }
            observations = [
                {
                    "date": str(item.get("date") or ""),
                    "value": self._number(item.get("value")),
                    "realtime_start": item.get("realtime_start"),
                    "realtime_end": item.get("realtime_end"),
                    "fetched_at": now,
                }
                for item in observation_rows
                if isinstance(item, dict) and item.get("date")
            ]
            self._record_success(
                started=started,
                observations=observations,
                message="FRED 实时请求成功；观测值未写入本地数据库",
            )
            return self._series_dataset(
                normalized, metadata, observations, warnings=source_warnings
            )
        except Exception as exc:
            if isinstance(exc, (FredNotConfiguredError, KeyError)):
                raise
            self._record_failure(exc, started)
            if isinstance(exc, MacroProviderError):
                raise
            raise MacroProviderError("FRED 数据加载失败") from exc

    def chart(
        self,
        series_ids: list[str],
        *,
        years: int,
        transform: str,
        refresh: bool = False,
    ) -> Dataset:
        if not series_ids or len(series_ids) > 6:
            raise ValueError("图表需选择 1–6 条序列")
        if transform not in {"level", "change", "yoy", "normalize", "zscore"}:
            raise ValueError("不支持的序列变换")
        loaded: list[dict[str, Any]] = []
        warnings: list[str] = []
        for series_id in dict.fromkeys(series_ids):
            try:
                dataset = self.series(
                    series_id,
                    years=years,
                    refresh=refresh,
                    observation_units="pc1" if transform == "yoy" else "lin",
                )
            except (MacroProviderError, FredNotConfiguredError) as exc:
                warnings.append(f"{series_id}: {exc}")
                continue
            metadata = dataset.data["series"]
            observations = (
                transform_observations(
                    dataset.data["observations"],
                    "level" if transform == "yoy" else transform,
                    str(metadata.get("frequency") or ""),
                )
            )
            loaded.append({"metadata": metadata, "observations": observations})
            warnings.extend(dataset.meta.warnings)
        if not loaded:
            if not self.secret_store.get():
                raise FredNotConfiguredError("请先在宏观数据库页面配置 FRED API Key")
            raise MacroProviderError("所选序列暂时没有可用数据")
        dates = sorted(
            {
                str(item["date"])
                for series in loaded
                for item in series["observations"]
            }
        )
        output_series = []
        for item in loaded:
            indexed_point = {
                str(point["date"]): point for point in item["observations"]
            }
            indexed = {
                str(point["date"]): point.get("value")
                for point in item["observations"]
            }
            metadata = item["metadata"]
            output_series.append(
                {
                    "key": metadata["series_id"],
                    "name": metadata.get("title_zh") or metadata.get("title"),
                    "values": [indexed.get(observed) for observed in dates],
                    "units": metadata.get("units"),
                    "frequency": metadata.get("frequency"),
                    "attribution": metadata.get("attribution"),
                    "source_url": metadata.get("source_url"),
                    "source_organization": metadata.get("source_organization"),
                    "original_source_url": metadata.get("original_source_url"),
                    "last_updated": metadata.get("last_updated"),
                    "fetched_at": metadata.get("fetched_at"),
                    "realtime_start": [
                        indexed_point.get(observed, {}).get("realtime_start")
                        for observed in dates
                    ],
                    "realtime_end": [
                        indexed_point.get(observed, {}).get("realtime_end")
                        for observed in dates
                    ],
                }
            )
        now = datetime.now()
        return Dataset(
            data={
                "dates": dates,
                "series": output_series,
                "transform": transform,
                "years": years,
                "transform_source": (
                    "FRED API units=pc1" if transform == "yoy" else "AKDesk local"
                ),
                "storage_mode": "request_scoped",
                "terms_url": FRED_TERMS_URL,
            },
            meta=SourceMeta(
                source="FRED",
                source_url="https://fred.stlouisfed.org/",
                observation_time=dates[-1] if dates else None,
                fetched_at=now,
                stale=False,
                warnings=list(dict.fromkeys(warnings)),
                market_status="daily",
                market_status_label="按发布更新",
                data_state="live",
                trust_level="partial" if warnings else "trusted",
                quality_score=80 if warnings else 100,
                quality_issues=list(dict.fromkeys(warnings)),
            ),
        )

    def release_calendar(self, refresh: bool = False) -> Dataset:
        api_key = self.secret_store.get()
        if not api_key:
            raise FredNotConfiguredError("请先配置 FRED API Key 后查看发布日历")
        start = date.today() - timedelta(days=14)
        end = date.today() + timedelta(days=45)
        started = time.perf_counter()
        self._begin_request()
        try:
            request_params = {
                "api_key": api_key,
                "file_type": "json",
                "limit": 1000,
                "order_by": "release_date",
                "sort_order": "asc",
                "realtime_start": start.isoformat(),
                "realtime_end": end.isoformat(),
                "include_release_dates_with_no_data": "true",
            }
            raw: list[Any] = []
            offset = 0
            while offset < 10_000:
                payload = self._request_json(
                    "releases/dates", {**request_params, "offset": offset}
                )
                page = payload.get("release_dates")
                if not isinstance(page, list):
                    raise MacroProviderError("FRED 未返回发布日历")
                raw.extend(page)
                try:
                    total = int(payload.get("count") or len(raw))
                except (TypeError, ValueError):
                    total = len(raw)
                if not page or len(raw) >= total or len(page) < 1000:
                    break
                offset += len(page)
        except Exception as exc:
            self._record_failure(exc, started)
            if isinstance(exc, MacroProviderError):
                raise
            raise MacroProviderError("FRED 发布日历加载失败") from exc
        events = []
        seen: set[tuple[str, Any, str]] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                released = date.fromisoformat(str(item.get("date") or ""))
            except ValueError:
                continue
            if start <= released <= end:
                name = str(item.get("release_name") or "FRED 数据发布")
                identity = (released.isoformat(), item.get("release_id"), name)
                if identity in seen:
                    continue
                seen.add(identity)
                events.append(
                    {
                        "date": released.isoformat(),
                        "release_id": item.get("release_id"),
                        "name": name,
                    }
                )
        events.sort(key=lambda item: item["date"])
        dataset = Dataset(
            data=events,
            meta=SourceMeta(
                source="FRED release calendar",
                source_url="https://fred.stlouisfed.org/releases/",
                observation_time=date.today().isoformat(),
                fetched_at=datetime.now(),
                market_status="daily",
                market_status_label="计划发布日期",
                data_state="live",
            ),
        )
        self._record_success(
            started=started,
            observations=[{"date": item["date"]} for item in events],
            message="FRED 发布日历实时请求成功；结果未持久化",
        )
        return dataset

    def test_connection(self) -> dict[str, Any]:
        dataset = self.series("DGS10", years=1, refresh=True)
        return {
            "ok": True,
            "series_id": "DGS10",
            "observations": len(dataset.data["observations"]),
            "observation_time": dataset.meta.observation_time,
        }

    def health_item(self) -> HealthItem:
        status = self.secret_store.status()
        if not status.configured:
            return self._health.model_copy(
                update={
                    "state": "not_checked",
                    "message": "尚未配置 FRED API Key；无本地观测值缓存",
                    "trust_level": "unavailable",
                    "cache_persisted": False,
                    "execution_mode": "in_process_http",
                }
            )
        if self._health.state == "not_checked":
            return self._health.model_copy(
                update={
                    "message": "FRED API Key 已配置，尚未完成本次连接验证",
                    "cache_persisted": False,
                    "execution_mode": "in_process_http",
                }
            )
        return self._health.model_copy(
            update={
                "cache_age_seconds": None,
                "cache_persisted": False,
                "execution_mode": "in_process_http",
            }
        )

    def _series_dataset(
        self,
        series_id: str,
        metadata: dict[str, Any],
        observations: list[dict[str, Any]],
        *,
        warnings: list[str] | None = None,
    ) -> Dataset:
        fetched_raw = metadata.get("fetched_at")
        try:
            fetched = datetime.fromisoformat(str(fetched_raw))
        except (TypeError, ValueError):
            fetched = datetime.now()
        warnings = warnings or []
        return Dataset(
            data={"series": metadata, "observations": observations},
            meta=SourceMeta(
                source="FRED",
                source_url=str(
                    metadata.get("source_url")
                    or f"https://fred.stlouisfed.org/series/{series_id}"
                ),
                observation_time=observations[-1]["date"] if observations else None,
                fetched_at=fetched,
                stale=False,
                warnings=warnings,
                cache_age_seconds=None,
                market_status="daily",
                market_status_label="按发布更新",
                data_state="live",
                quality_score=90 if warnings else 100,
                quality_issues=warnings,
                trust_level="partial" if warnings else "trusted",
            ),
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
