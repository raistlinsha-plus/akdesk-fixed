from __future__ import annotations

import math
import statistics
import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Callable

import httpx

from . import __version__
from .database import Database
from .models import Dataset, HealthItem, SourceMeta


WORLD_BANK_API = "https://api.worldbank.org/v2"
WORLD_BANK_SOURCE_URL = "https://data.worldbank.org/"
WORLD_BANK_LICENSE_URL = "https://datacatalog.worldbank.org/public-licenses"
WORLD_BANK_LICENSE = "Creative Commons Attribution 4.0 (CC BY 4.0)"
WORLD_BANK_ATTRIBUTION = "World Bank, World Development Indicators"
WORLD_BANK_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


WORLD_BANK_COUNTRIES: list[dict[str, str]] = [
    {"country_code": "CHN", "name": "China", "name_zh": "中国"},
    {"country_code": "USA", "name": "United States", "name_zh": "美国"},
    {"country_code": "JPN", "name": "Japan", "name_zh": "日本"},
    {"country_code": "DEU", "name": "Germany", "name_zh": "德国"},
    {"country_code": "GBR", "name": "United Kingdom", "name_zh": "英国"},
    {"country_code": "FRA", "name": "France", "name_zh": "法国"},
    {"country_code": "IND", "name": "India", "name_zh": "印度"},
    {"country_code": "BRA", "name": "Brazil", "name_zh": "巴西"},
    {"country_code": "ZAF", "name": "South Africa", "name_zh": "南非"},
    {"country_code": "IDN", "name": "Indonesia", "name_zh": "印度尼西亚"},
]

WORLD_BANK_INDICATORS: list[dict[str, str]] = [
    {
        "indicator_id": "NY.GDP.MKTP.KD.ZG",
        "title_zh": "GDP 实际增速",
        "name": "GDP growth (annual %)",
        "topic": "增长与通胀",
        "unit": "%",
    },
    {
        "indicator_id": "FP.CPI.TOTL.ZG",
        "title_zh": "居民消费价格通胀",
        "name": "Inflation, consumer prices (annual %)",
        "topic": "增长与通胀",
        "unit": "%",
    },
    {
        "indicator_id": "GC.DOD.TOTL.GD.ZS",
        "title_zh": "中央政府债务占 GDP",
        "name": "Central government debt, total (% of GDP)",
        "topic": "财政与债务",
        "unit": "% GDP",
    },
    {
        "indicator_id": "GC.NLD.TOTL.GD.ZS",
        "title_zh": "财政净借贷占 GDP",
        "name": "Net lending (+) / net borrowing (-) (% of GDP)",
        "topic": "财政与债务",
        "unit": "% GDP",
    },
    {
        "indicator_id": "BN.CAB.XOKA.GD.ZS",
        "title_zh": "经常账户余额占 GDP",
        "name": "Current account balance (% of GDP)",
        "topic": "外部平衡",
        "unit": "% GDP",
    },
    {
        "indicator_id": "FI.RES.TOTL.MO",
        "title_zh": "外汇储备可覆盖进口月数",
        "name": "Total reserves in months of imports",
        "topic": "外部平衡",
        "unit": "月",
    },
    {
        "indicator_id": "DT.DOD.DECT.GN.ZS",
        "title_zh": "外债存量占 GNI",
        "name": "External debt stocks (% of GNI)",
        "topic": "外部平衡",
        "unit": "% GNI",
    },
    {
        "indicator_id": "NY.GNP.PCAP.CD",
        "title_zh": "人均 GNI",
        "name": "GNI per capita, Atlas method (current US$)",
        "topic": "收入与结构",
        "unit": "美元",
    },
    {
        "indicator_id": "NV.IND.TOTL.ZS",
        "title_zh": "工业增加值占 GDP",
        "name": "Industry value added (% of GDP)",
        "topic": "收入与结构",
        "unit": "% GDP",
    },
    {
        "indicator_id": "SP.POP.GROW",
        "title_zh": "人口增速",
        "name": "Population growth (annual %)",
        "topic": "收入与结构",
        "unit": "%",
    },
]

COUNTRY_BY_CODE = {item["country_code"]: item for item in WORLD_BANK_COUNTRIES}
INDICATOR_BY_ID = {item["indicator_id"]: item for item in WORLD_BANK_INDICATORS}


class WorldBankProviderError(RuntimeError):
    pass


class WorldBankService:
    def __init__(
        self,
        database: Database,
        request_json: Callable[[str, dict[str, Any]], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database = database
        self._request_override = request_json
        self._sleep = sleep
        self._lock = RLock()
        self._failure_count = 0
        self._circuit_open_until: float | None = None
        self._health = HealthItem(
            adapter="world_bank",
            label="World Bank 主权数据",
            state="not_checked",
            market_status="daily",
            market_status_label="低频结构数据",
            execution_mode="in_process_http",
            trust_level="unavailable",
            message="等待首次主权比较请求",
        )

    def catalog(self) -> dict[str, Any]:
        cached_countries = {
            item["country_code"]: item for item in self.database.world_bank_countries()
        }
        countries = [
            {
                **item,
                **cached_countries.get(item["country_code"], {}),
                "country_code": item["country_code"],
                "name_zh": item["name_zh"],
            }
            for item in WORLD_BANK_COUNTRIES
        ]
        indicators = []
        for item in WORLD_BANK_INDICATORS:
            cached = self.database.world_bank_indicator(item["indicator_id"]) or {}
            indicators.append(
                {
                    **item,
                    **cached,
                    "indicator_id": item["indicator_id"],
                    "title_zh": item["title_zh"],
                    "topic": item["topic"],
                    "unit": item["unit"],
                    "source_url": f"https://data.worldbank.org/indicator/{item['indicator_id']}",
                }
            )
        return {
            "countries": countries,
            "indicators": indicators,
            "views": [
                {"id": "level", "label": "水平值"},
                {"id": "change", "label": "单年变化"},
                {"id": "rank", "label": "横截面数值排名"},
                {"id": "zscore", "label": "横截面 Z-Score"},
            ],
            "source": "World Bank Indicators API v2",
            "source_url": WORLD_BANK_SOURCE_URL,
            "license": WORLD_BANK_LICENSE,
            "license_url": WORLD_BANK_LICENSE_URL,
            "attribution": WORLD_BANK_ATTRIBUTION,
            "cache_policy": "成功请求按国家、指标和年份持久化，本地缓存 7 天内直接复用。",
        }

    def compare(
        self,
        country_codes: list[str],
        indicator_id: str,
        *,
        start_year: int,
        end_year: int,
        view: str = "level",
        refresh: bool = False,
    ) -> Dataset:
        countries = list(
            dict.fromkeys(item.strip().upper() for item in country_codes if item.strip())
        )
        indicator = indicator_id.strip().upper()
        if not 2 <= len(countries) <= 8:
            raise ValueError("主权比较需选择 2–8 个经济体")
        if any(item not in COUNTRY_BY_CODE for item in countries):
            raise ValueError("包含不支持的经济体")
        if indicator not in INDICATOR_BY_ID:
            raise ValueError("不支持的 World Bank 指标")
        current_year = datetime.now().year
        if start_year < 1960 or end_year > current_year or start_year > end_year:
            raise ValueError("年份范围无效")
        if end_year - start_year > 50:
            raise ValueError("单次比较最多 51 个年度")
        if view not in {"level", "change", "rank", "zscore"}:
            raise ValueError("不支持的比较视图")

        cache_age = self.database.world_bank_cache_age(
            countries, indicator, start_year, end_year
        )
        if (
            not refresh
            and cache_age is not None
            and cache_age <= WORLD_BANK_CACHE_TTL_SECONDS
        ):
            return self._dataset_from_cache(
                countries,
                indicator,
                start_year,
                end_year,
                view,
                cache_age=cache_age,
                stale=False,
                freshly_fetched=False,
            )

        started = time.perf_counter()
        self._begin_request()
        warnings: list[str] = []
        try:
            with self._lock:
                metadata, metadata_warning = self._indicator_metadata(indicator)
                if metadata_warning:
                    warnings.append(metadata_warning)
                country_metadata, country_warning = self._country_metadata(countries)
                if country_warning:
                    warnings.append(country_warning)
                observations, last_updated = self._fetch_observations(
                    countries, indicator, start_year, end_year
                )
            fetched_at = datetime.now().isoformat()
            metadata.update(
                {
                    "title_zh": INDICATOR_BY_ID[indicator]["title_zh"],
                    "topic": INDICATOR_BY_ID[indicator]["topic"],
                    "unit": metadata.get("unit")
                    or INDICATOR_BY_ID[indicator]["unit"],
                    "last_updated": last_updated,
                    "fetched_at": fetched_at,
                }
            )
            self.database.upsert_world_bank_indicator(metadata)
            self.database.upsert_world_bank_countries(
                [
                    {
                        **COUNTRY_BY_CODE[item["country_code"]],
                        **item,
                        "fetched_at": fetched_at,
                    }
                    for item in country_metadata
                ]
            )
            indexed = {
                (item["country_code"], int(item["year"])): item
                for item in observations
            }
            completed = [
                indexed.get(
                    (country, year),
                    {
                        "country_code": country,
                        "indicator_id": indicator,
                        "year": year,
                        "value": None,
                        "obs_status": "",
                        "decimal_places": None,
                    },
                )
                for country in countries
                for year in range(start_year, end_year + 1)
            ]
            self.database.upsert_world_bank_observations(
                completed, fetched_at=fetched_at
            )
            self._record_success(
                started=started,
                rows=len(completed),
                observation_time=str(
                    max(
                        (
                            item["year"]
                            for item in completed
                            if item.get("value") is not None
                        ),
                        default=end_year,
                    )
                ),
                message="World Bank 官方数据请求成功，已写入低频本地缓存",
            )
            dataset = self._dataset_from_cache(
                countries,
                indicator,
                start_year,
                end_year,
                view,
                cache_age=0,
                stale=False,
                freshly_fetched=True,
            )
            dataset.meta.warnings = list(dict.fromkeys(warnings))
            if warnings:
                dataset.meta.trust_level = "partial"
                dataset.meta.quality_score = 90
                dataset.meta.quality_issues = dataset.meta.warnings
            return dataset
        except Exception as exc:
            self._record_failure(exc, started)
            cached = self.database.world_bank_observations(
                countries, indicator, start_year, end_year
            )
            if cached:
                fallback_age = self.database.world_bank_cache_age(
                    countries, indicator, start_year, end_year
                )
                dataset = self._dataset_from_cache(
                    countries,
                    indicator,
                    start_year,
                    end_year,
                    view,
                    cache_age=fallback_age,
                    stale=True,
                    freshly_fetched=False,
                )
                dataset.meta.warnings.append(
                    f"官方刷新失败，继续使用本地缓存：{str(exc)[:180]}"
                )
                dataset.meta.quality_issues = list(dataset.meta.warnings)
                dataset.meta.trust_level = "partial"
                dataset.meta.quality_score = 75
                return dataset
            if isinstance(exc, (WorldBankProviderError, ValueError)):
                raise
            raise WorldBankProviderError("World Bank 数据加载失败") from exc

    def _request_json(self, path: str, params: dict[str, Any]) -> Any:
        if self._request_override is not None:
            return self._request_override(path, params)
        last_request_error: httpx.RequestError | None = None
        for attempt in range(3):
            # Some local proxy clients reset World Bank TLS connections. Prefer a
            # clean direct connection, then retain the system proxy as a fallback
            # for networks where direct access is unavailable.
            for trust_env in (False, True):
                try:
                    with httpx.Client(
                        http2=True,
                        trust_env=trust_env,
                        timeout=20,
                        follow_redirects=True,
                        headers={
                            "User-Agent": (
                                f"AKDesk-Fixed/{__version__} personal-research"
                            )
                        },
                    ) as client:
                        response = client.get(WORLD_BANK_API + path, params=params)
                except httpx.RequestError as exc:
                    last_request_error = exc
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        break
                    raise WorldBankProviderError("World Bank 服务暂时不可用")
                try:
                    response.raise_for_status()
                    return response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise WorldBankProviderError(
                        "World Bank 返回了无法识别的数据"
                    ) from exc
            if attempt < 2:
                self._sleep(0.25 * (2**attempt))
        raise WorldBankProviderError("World Bank 网络连接失败") from last_request_error

    def _paged_rows(self, path: str, params: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        rows: list[Any] = []
        page = 1
        metadata: dict[str, Any] = {}
        while page <= 100:
            payload = self._request_json(
                path, {**params, "format": "json", "page": page, "per_page": 1000}
            )
            if not isinstance(payload, list) or len(payload) < 2:
                raise WorldBankProviderError("World Bank 返回结构不完整")
            current_meta = payload[0] if isinstance(payload[0], dict) else {}
            current_rows = payload[1] if isinstance(payload[1], list) else []
            metadata = current_meta
            rows.extend(current_rows)
            try:
                pages = int(current_meta.get("pages") or 1)
            except (TypeError, ValueError):
                pages = 1
            if page >= pages:
                break
            page += 1
        return rows, metadata

    def _fetch_observations(
        self,
        countries: list[str],
        indicator_id: str,
        start_year: int,
        end_year: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        rows, metadata = self._paged_rows(
            f"/country/{';'.join(countries)}/indicator/{indicator_id}",
            {"date": f"{start_year}:{end_year}", "source": "2"},
        )
        observations: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            country = str(item.get("countryiso3code") or "").strip().upper()
            try:
                year = int(item.get("date"))
            except (TypeError, ValueError):
                continue
            if country not in countries or not start_year <= year <= end_year:
                continue
            observations.append(
                {
                    "country_code": country,
                    "indicator_id": indicator_id,
                    "year": year,
                    "value": self._number(item.get("value")),
                    "obs_status": str(item.get("obs_status") or ""),
                    "decimal_places": item.get("decimal"),
                }
            )
        return observations, (
            str(metadata.get("lastupdated")) if metadata.get("lastupdated") else None
        )

    def _indicator_metadata(
        self, indicator_id: str
    ) -> tuple[dict[str, Any], str | None]:
        fallback = {
            **INDICATOR_BY_ID[indicator_id],
            "source_id": "2",
            "source_name": "World Development Indicators",
            "source_note": "",
            "source_organization": "World Bank",
            "source_url": f"https://data.worldbank.org/indicator/{indicator_id}",
            "license": WORLD_BANK_LICENSE,
            "attribution": WORLD_BANK_ATTRIBUTION,
        }
        try:
            payload = self._request_json(
                f"/indicator/{indicator_id}", {"format": "json", "source": "2"}
            )
            rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
            raw = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
            if raw is None:
                return fallback, "指标元数据未返回，使用精选目录说明"
            source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
            return (
                {
                    **fallback,
                    "name": str(raw.get("name") or fallback["name"]),
                    "unit": str(raw.get("unit") or fallback["unit"]),
                    "source_id": str(source.get("id") or "2"),
                    "source_name": str(
                        source.get("value") or "World Development Indicators"
                    ),
                    "source_note": str(raw.get("sourceNote") or ""),
                    "source_organization": str(
                        raw.get("sourceOrganization") or "World Bank"
                    ),
                },
                None,
            )
        except WorldBankProviderError:
            return fallback, "指标元数据刷新失败，使用精选目录说明"

    def _country_metadata(
        self, countries: list[str]
    ) -> tuple[list[dict[str, Any]], str | None]:
        fallback = [
            {
                **COUNTRY_BY_CODE[code],
                "iso2_code": "",
                "region_id": "",
                "region_name": "",
                "income_level_id": "",
                "income_level_name": "",
                "capital_city": "",
                "longitude": None,
                "latitude": None,
            }
            for code in countries
        ]
        try:
            rows, _ = self._paged_rows(f"/country/{';'.join(countries)}", {})
            parsed: dict[str, dict[str, Any]] = {}
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                code = str(raw.get("id") or "").strip().upper()
                if code not in countries:
                    continue
                region = raw.get("region") if isinstance(raw.get("region"), dict) else {}
                income = (
                    raw.get("incomeLevel")
                    if isinstance(raw.get("incomeLevel"), dict)
                    else {}
                )
                parsed[code] = {
                    **COUNTRY_BY_CODE[code],
                    "iso2_code": str(raw.get("iso2Code") or ""),
                    "name": str(raw.get("name") or COUNTRY_BY_CODE[code]["name"]),
                    "region_id": str(region.get("id") or ""),
                    "region_name": str(region.get("value") or ""),
                    "income_level_id": str(income.get("id") or ""),
                    "income_level_name": str(income.get("value") or ""),
                    "capital_city": str(raw.get("capitalCity") or ""),
                    "longitude": self._number(raw.get("longitude")),
                    "latitude": self._number(raw.get("latitude")),
                }
            return [parsed.get(code, fallback[index]) for index, code in enumerate(countries)], None
        except WorldBankProviderError:
            return fallback, "国家元数据刷新失败，使用精选目录名称"

    def _dataset_from_cache(
        self,
        countries: list[str],
        indicator_id: str,
        start_year: int,
        end_year: int,
        view: str,
        *,
        cache_age: int | None,
        stale: bool,
        freshly_fetched: bool,
    ) -> Dataset:
        rows = self.database.world_bank_observations(
            countries, indicator_id, start_year, end_year
        )
        fetched_times: list[datetime] = []
        for item in rows:
            try:
                fetched_times.append(datetime.fromisoformat(str(item["fetched_at"])))
            except (KeyError, TypeError, ValueError):
                continue
        actual_fetched_at = min(fetched_times, default=datetime.now())
        indexed = {
            (str(item["country_code"]), int(item["year"])): item.get("value")
            for item in rows
        }
        years = list(range(start_year, end_year + 1))
        raw_values = {
            country: [indexed.get((country, year)) for year in years]
            for country in countries
        }
        display_values = self._transform(raw_values, view)
        country_metadata = {
            item["country_code"]: item
            for item in self.database.world_bank_countries(countries)
        }
        indicator = {
            **INDICATOR_BY_ID[indicator_id],
            **(self.database.world_bank_indicator(indicator_id) or {}),
            "indicator_id": indicator_id,
            "source_url": f"https://data.worldbank.org/indicator/{indicator_id}",
            "license_url": WORLD_BANK_LICENSE_URL,
        }
        series = [
            {
                "key": country,
                "name": COUNTRY_BY_CODE[country]["name_zh"],
                "values": display_values[country],
                "raw_values": raw_values[country],
            }
            for country in countries
        ]
        latest_any = next(
            (
                year
                for index, year in reversed(list(enumerate(years)))
                if sum(raw_values[country][index] is not None for country in countries)
                >= 2
            ),
            None,
        )
        latest_comparable = next(
            (
                year
                for index, year in reversed(list(enumerate(years)))
                if all(raw_values[country][index] is not None for country in countries)
            ),
            None,
        )
        summary_year = latest_comparable or latest_any
        latest_rows: list[dict[str, Any]] = []
        if summary_year is not None:
            index = years.index(summary_year)
            available = [
                (country, raw_values[country][index])
                for country in countries
                if raw_values[country][index] is not None
            ]
            ranks = {
                country: rank
                for rank, (country, _value) in enumerate(
                    sorted(available, key=lambda item: float(item[1]), reverse=True),
                    start=1,
                )
            }
            latest_rows = [
                {
                    "country_code": country,
                    "country_name": COUNTRY_BY_CODE[country]["name_zh"],
                    "value": raw_values[country][index],
                    "display_value": display_values[country][index],
                    "rank": ranks.get(country),
                }
                for country in countries
            ]
        available_points = sum(
            value is not None for values in raw_values.values() for value in values
        )
        total_points = len(countries) * len(years)
        observation_time = str(
            max(
                (
                    year
                    for index, year in enumerate(years)
                    if any(raw_values[country][index] is not None for country in countries)
                ),
                default=end_year,
            )
        )
        warnings = ["官方刷新失败，当前使用过期缓存"] if stale else []
        return Dataset(
            data={
                "indicator": indicator,
                "countries": [
                    {
                        **COUNTRY_BY_CODE[country],
                        **country_metadata.get(country, {}),
                        "country_code": country,
                        "name_zh": COUNTRY_BY_CODE[country]["name_zh"],
                    }
                    for country in countries
                ],
                "years": [str(year) for year in years],
                "series": series,
                "view": view,
                "latest_available_year": latest_any,
                "latest_comparable_year": latest_comparable,
                "summary_year": summary_year,
                "latest_rows": latest_rows,
                "coverage": {
                    "available": available_points,
                    "total": total_points,
                    "ratio": (
                        round(available_points / total_points, 4)
                        if total_points
                        else 0.0
                    ),
                    "by_country": {
                        country: {
                            "available": sum(
                                value is not None for value in raw_values[country]
                            ),
                            "total": len(years),
                        }
                        for country in countries
                    },
                },
                "source": "World Bank Indicators API v2",
                "source_url": WORLD_BANK_SOURCE_URL,
                "license": WORLD_BANK_LICENSE,
                "license_url": WORLD_BANK_LICENSE_URL,
                "attribution": WORLD_BANK_ATTRIBUTION,
                "storage_mode": "persistent_cache",
                "comparison_notice": (
                    "缺失年份保持为空，不做跨年填充。排名仅表示当年数值由高到低，"
                    "不代表主权质量或投资建议。"
                ),
            },
            meta=SourceMeta(
                source="World Bank / World Development Indicators",
                source_url=WORLD_BANK_SOURCE_URL,
                observation_time=observation_time,
                fetched_at=actual_fetched_at,
                stale=stale,
                warnings=warnings,
                cache_age_seconds=cache_age,
                market_status="daily",
                market_status_label="年度结构数据",
                data_state=(
                    "stale" if stale else "latest" if freshly_fetched else "cached"
                ),
                quality_score=75 if stale else 100,
                quality_issues=warnings,
                trust_level="partial" if stale else "trusted",
            ),
        )

    @staticmethod
    def _transform(
        raw_values: dict[str, list[float | None]], view: str
    ) -> dict[str, list[float | None]]:
        if view == "level":
            return {key: list(values) for key, values in raw_values.items()}
        if view == "change":
            return {
                key: [
                    (
                        float(value) - float(values[index - 1])
                        if index
                        and value is not None
                        and values[index - 1] is not None
                        else None
                    )
                    for index, value in enumerate(values)
                ]
                for key, values in raw_values.items()
            }
        countries = list(raw_values)
        length = len(next(iter(raw_values.values()), []))
        output = {country: [None] * length for country in countries}
        for index in range(length):
            available = [
                (country, raw_values[country][index])
                for country in countries
                if raw_values[country][index] is not None
            ]
            if view == "rank":
                for rank, (country, _value) in enumerate(
                    sorted(available, key=lambda item: float(item[1]), reverse=True),
                    start=1,
                ):
                    output[country][index] = float(rank)
            elif view == "zscore" and len(available) >= 2:
                numbers = [float(item[1]) for item in available]
                deviation = statistics.pstdev(numbers)
                mean = statistics.fmean(numbers)
                for country, value in available:
                    output[country][index] = (
                        (float(value) - mean) / deviation if deviation else 0.0
                    )
        return output

    def _begin_request(self) -> None:
        if self._circuit_open_until is None:
            return
        if time.monotonic() < self._circuit_open_until:
            seconds = max(1, round(self._circuit_open_until - time.monotonic()))
            raise WorldBankProviderError(
                f"World Bank 暂时熔断，请在 {seconds} 秒后重试"
            )
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
        stats = self.database.world_bank_stats()
        self._health = self._health.model_copy(
            update={
                "state": "degraded" if stats["points"] else "unavailable",
                "last_failure_at": datetime.now(),
                "last_attempt_at": datetime.now(),
                "consecutive_failures": self._failure_count,
                "message": str(exc)[:300],
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "trust_level": "partial" if stats["points"] else "unavailable",
                "cache_persisted": bool(stats["points"]),
                "circuit_state": "open" if opened else "closed",
                "next_retry_at": next_retry,
            }
        )

    def _record_success(
        self, *, started: float, rows: int, observation_time: str, message: str
    ) -> None:
        now = datetime.now()
        self._failure_count = 0
        self._circuit_open_until = None
        self._health = HealthItem(
            adapter="world_bank",
            label="World Bank 主权数据",
            state="healthy",
            last_success_at=now,
            observation_time=observation_time,
            rows=rows,
            latency_ms=round((time.perf_counter() - started) * 1000),
            message=message,
            last_attempt_at=now,
            cache_persisted=True,
            market_status="daily",
            market_status_label="低频结构数据",
            execution_mode="in_process_http",
            trust_level="trusted",
            circuit_state="closed",
            next_refresh_at=now + timedelta(days=7),
        )

    def health_item(self) -> HealthItem:
        stats = self.database.world_bank_stats()
        age = None
        if stats.get("last_fetched_at"):
            try:
                age = max(
                    0,
                    int(
                        (
                            datetime.now()
                            - datetime.fromisoformat(str(stats["last_fetched_at"]))
                        ).total_seconds()
                    ),
                )
            except ValueError:
                age = None
        if self._health.state == "not_checked" and stats["points"]:
            stale = age is None or age > WORLD_BANK_CACHE_TTL_SECONDS
            return self._health.model_copy(
                update={
                    "state": "degraded" if stale else "cached",
                    "observation_time": (
                        str(stats["newest"]) if stats["newest"] is not None else None
                    ),
                    "rows": int(stats["points"]),
                    "message": (
                        "World Bank 本地缓存已过期，等待刷新"
                        if stale
                        else "World Bank 本地缓存可用，尚未完成本次官方验证"
                    ),
                    "cache_age_seconds": age,
                    "cache_persisted": True,
                    "trust_level": "partial" if stale else "trusted",
                }
            )
        if (
            self._health.state == "healthy"
            and stats["points"]
            and (age is None or age > WORLD_BANK_CACHE_TTL_SECONDS)
        ):
            return self._health.model_copy(
                update={
                    "state": "degraded",
                    "message": "World Bank 本地缓存已过期，等待下次请求刷新",
                    "cache_age_seconds": age,
                    "cache_persisted": True,
                    "rows": int(stats["points"]),
                    "trust_level": "partial",
                }
            )
        return self._health.model_copy(
            update={
                "cache_persisted": bool(stats["points"]),
                "rows": int(stats["points"]),
                "cache_age_seconds": age,
            }
        )

    def test_connection(self) -> dict[str, Any]:
        year = datetime.now().year
        dataset = self.compare(
            ["CHN", "USA"],
            "NY.GDP.MKTP.KD.ZG",
            start_year=year - 3,
            end_year=year,
            refresh=True,
        )
        return {
            "ok": True,
            "countries": 2,
            "indicator_id": "NY.GDP.MKTP.KD.ZG",
            "observation_time": dataset.meta.observation_time,
            "points": dataset.data["coverage"]["available"],
        }

    def clear_cache(self) -> None:
        self.database.clear_world_bank_cache()
        self._failure_count = 0
        self._circuit_open_until = None
        self._health = HealthItem(
            adapter="world_bank",
            label="World Bank 主权数据",
            state="not_checked",
            market_status="daily",
            market_status_label="低频结构数据",
            execution_mode="in_process_http",
            trust_level="unavailable",
            message="World Bank 本地缓存已清空",
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
