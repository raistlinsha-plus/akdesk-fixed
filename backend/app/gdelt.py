from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from . import __version__
from .database import Database
from .models import Dataset, GdeltEventRadarData, HealthItem, SourceMeta


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_SOURCE_URL = "https://www.gdeltproject.org/"
GDELT_TERMS_URL = "https://www.gdeltproject.org/about.html"
GDELT_ATTRIBUTION = "The GDELT Project"
GDELT_CACHE_TTL_SECONDS = 12 * 60 * 60
GDELT_REQUEST_INTERVAL_SECONDS = 5.0
GDELT_NOTICE = (
    "GDELT 匹配结果仅用于发现待核验事件线索；标题、覆盖量和来源分布不代表事实确认、"
    "风险概率或投资结论。请打开原文并交叉核验。"
)
_QUERY_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


class GdeltProviderError(RuntimeError):
    pass


class GdeltRateLimitError(GdeltProviderError):
    pass


def normalize_gdelt_query(query: str) -> str:
    normalized = " ".join(query.split())
    if not 2 <= len(normalized) <= 200 or _QUERY_CONTROL_PATTERN.search(normalized):
        raise ValueError("GDELT 检索词应为 2–200 个可见字符")
    return normalized


def _safe_http_url(value: Any) -> str | None:
    text = str(value or "").strip()
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text[:2_000]


def _seen_at(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            parsed = datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text[:40]


def _cache_key(query: str, days: int, limit: int, sort: str) -> str:
    encoded = json.dumps(
        {"query": query, "days": days, "limit": limit, "sort": sort},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class GdeltService:
    def __init__(
        self,
        database: Database,
        request_json: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database = database
        self._request_override = request_json
        self._sleep = sleep
        self._monotonic = monotonic
        self._request_lock = RLock()
        self._last_request_at: float | None = None
        self._failure_count = 0
        self._circuit_open_until: float | None = None
        self._health = HealthItem(
            adapter="gdelt_events",
            label="GDELT 事件线索",
            state="not_checked",
            market_status="daily",
            market_status_label="约 15 分钟滚动更新",
            execution_mode="in_process_http",
            trust_level="unavailable",
            message="等待首次按需事件检索",
        )

    def search(
        self,
        query: str,
        *,
        days: int = 7,
        limit: int = 20,
        sort: str = "datedesc",
        refresh: bool = False,
    ) -> Dataset[GdeltEventRadarData]:
        normalized_query = normalize_gdelt_query(query)
        if not 1 <= days <= 90:
            raise ValueError("GDELT 检索时间范围应为 1–90 天")
        if not 5 <= limit <= 50:
            raise ValueError("GDELT 单次最多返回 5–50 条线索")
        normalized_sort = sort.strip().lower()
        if normalized_sort not in {"datedesc", "hybridrel"}:
            raise ValueError("GDELT 排序方式不受支持")
        key = _cache_key(normalized_query, days, limit, normalized_sort)
        cached = self.database.get_gdelt_cache(key)
        if cached and not refresh and not cached["expired"]:
            return self._dataset_from_cache(cached, stale=False, fallback=False)

        started = time.perf_counter()
        try:
            self._begin_request()
            params = {
                "query": normalized_query,
                "mode": "artlist",
                "maxrecords": limit,
                "format": "json",
                "sort": "DateDesc" if normalized_sort == "datedesc" else "HybridRel",
                "timespan": f"{days}d",
            }
            payload = self._paced_request(params)
            data = self._normalize_response(
                payload,
                query=normalized_query,
                days=days,
                sort=normalized_sort,
                limit=limit,
            )
            fetched_at = datetime.now()
            expires_at = fetched_at + timedelta(seconds=GDELT_CACHE_TTL_SECONDS)
            self.database.upsert_gdelt_cache(
                cache_key=key,
                query=normalized_query,
                days=days,
                result_limit=limit,
                sort=normalized_sort,
                payload=data.model_dump(mode="json"),
                fetched_at=fetched_at.isoformat(),
                expires_at=expires_at.isoformat(),
            )
            self._record_success(
                started=started,
                rows=data.article_count,
                observation_time=data.latest_seen_at,
            )
            return self._dataset(
                data,
                fetched_at=fetched_at,
                stale=False,
                data_state="latest",
                cache_age_seconds=0,
            )
        except Exception as exc:
            provider_error = self._provider_error(exc)
            self._record_failure(provider_error, started)
            if cached:
                dataset = self._dataset_from_cache(cached, stale=True, fallback=True)
                dataset.meta.warnings.append(
                    f"GDELT 刷新失败，继续使用本地线索缓存：{str(provider_error)[:180]}"
                )
                dataset.meta.quality_issues = list(dataset.meta.warnings)
                dataset.meta.quality_score = 60
                return dataset
            raise provider_error from exc

    def _paced_request(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            now = self._monotonic()
            if self._last_request_at is not None:
                wait = GDELT_REQUEST_INTERVAL_SECONDS - (now - self._last_request_at)
                if wait > 0:
                    self._sleep(wait)
            try:
                return self._request_json(params)
            finally:
                self._last_request_at = self._monotonic()

    def _request_json(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._request_override is not None:
            payload = self._request_override(params)
            if not isinstance(payload, dict):
                raise GdeltProviderError("GDELT 返回格式异常")
            return payload
        try:
            response = httpx.get(
                GDELT_DOC_API,
                params=params,
                timeout=20,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        f"AKDesk-Fixed/{__version__} personal-research "
                        "(on-demand; cached)"
                    )
                },
            )
        except httpx.RequestError as exc:
            raise GdeltProviderError("GDELT 网络连接失败，请稍后重试") from exc
        text = response.text.strip()
        if response.status_code == 429 or text.lower().startswith(
            "please limit requests"
        ):
            raise GdeltRateLimitError("GDELT 请求频率受限，请稍后重试")
        if response.status_code >= 500:
            raise GdeltProviderError("GDELT 服务暂时不可用")
        if response.status_code >= 400:
            raise GdeltProviderError(f"GDELT 请求失败（HTTP {response.status_code}）")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GdeltProviderError("GDELT 返回了非 JSON 内容") from exc
        if not isinstance(payload, dict):
            raise GdeltProviderError("GDELT 返回格式异常")
        return payload

    def _normalize_response(
        self,
        payload: dict[str, Any],
        *,
        query: str,
        days: int,
        sort: str,
        limit: int,
    ) -> GdeltEventRadarData:
        raw_articles = payload.get("articles", [])
        if not isinstance(raw_articles, list):
            raise GdeltProviderError("GDELT 文章列表格式异常")
        articles: list[dict[str, Any]] = []
        known_urls: set[str] = set()
        for item in raw_articles[: max(limit * 2, limit)]:
            if not isinstance(item, dict):
                continue
            url = _safe_http_url(item.get("url"))
            title = " ".join(str(item.get("title") or "").split())[:500]
            if not url or not title or url in known_urls:
                continue
            known_urls.add(url)
            domain = str(item.get("domain") or urlparse(url).netloc).strip()[:200]
            seen_at = _seen_at(item.get("seendate") or item.get("date"))
            articles.append(
                {
                    "id": hashlib.sha256(url.encode()).hexdigest()[:20],
                    "title": title,
                    "url": url,
                    "domain": domain,
                    "seen_at": seen_at,
                    "language": str(item.get("language") or "").strip()[:80],
                    "source_country": str(item.get("sourcecountry") or "").strip()[
                        :80
                    ],
                    "image_url": _safe_http_url(item.get("socialimage")),
                }
            )
            if len(articles) >= limit:
                break
        source_counts = Counter(
            item["domain"] or "未知来源" for item in articles
        ).most_common(8)
        country_counts = Counter(
            item["source_country"] or "未知国家" for item in articles
        ).most_common(8)
        latest_seen_at = max(
            (item["seen_at"] for item in articles if item["seen_at"]),
            default=None,
        )
        return GdeltEventRadarData(
            query=query,
            days=days,
            sort=sort,
            article_count=len(articles),
            source_count=len({item["domain"] for item in articles if item["domain"]}),
            country_count=len(
                {
                    item["source_country"]
                    for item in articles
                    if item["source_country"]
                }
            ),
            latest_seen_at=latest_seen_at,
            source_distribution=[
                {"name": name, "count": count} for name, count in source_counts
            ],
            country_distribution=[
                {"name": name, "count": count} for name, count in country_counts
            ],
            articles=articles,
            attribution=GDELT_ATTRIBUTION,
            license_url=GDELT_TERMS_URL,
            notice=GDELT_NOTICE,
        )

    def _dataset_from_cache(
        self, cached: dict[str, Any], *, stale: bool, fallback: bool
    ) -> Dataset[GdeltEventRadarData]:
        data = GdeltEventRadarData.model_validate(cached["payload"])
        fetched_at = datetime.fromisoformat(str(cached["fetched_at"]))
        age = max(0, int((datetime.now() - fetched_at).total_seconds()))
        dataset = self._dataset(
            data,
            fetched_at=fetched_at,
            stale=stale,
            data_state="stale" if stale else "cached",
            cache_age_seconds=age,
        )
        if fallback:
            dataset.meta.trust_level = "partial"
        return dataset

    @staticmethod
    def _dataset(
        data: GdeltEventRadarData,
        *,
        fetched_at: datetime,
        stale: bool,
        data_state: str,
        cache_age_seconds: int,
    ) -> Dataset[GdeltEventRadarData]:
        warnings = [GDELT_NOTICE]
        return Dataset(
            data=data,
            meta=SourceMeta(
                source="GDELT DOC 2.0",
                source_url=GDELT_SOURCE_URL,
                observation_time=data.latest_seen_at,
                fetched_at=fetched_at,
                stale=stale,
                warnings=warnings,
                cache_age_seconds=cache_age_seconds,
                market_status="daily",
                market_status_label="约 15 分钟滚动更新",
                data_state=data_state,
                quality_score=70 if stale else 80,
                quality_issues=warnings,
                trust_level="partial",
            ),
        )

    def _begin_request(self) -> None:
        if self._circuit_open_until is None:
            return
        if self._monotonic() < self._circuit_open_until:
            seconds = max(1, round(self._circuit_open_until - self._monotonic()))
            raise GdeltProviderError(f"GDELT 暂时熔断，请在 {seconds} 秒后重试")
        self._health = self._health.model_copy(
            update={"circuit_state": "half_open", "next_retry_at": None}
        )

    @staticmethod
    def _provider_error(exc: Exception) -> GdeltProviderError:
        if isinstance(exc, GdeltProviderError):
            return exc
        if isinstance(exc, ValueError):
            return GdeltProviderError(str(exc))
        return GdeltProviderError("GDELT 事件线索加载失败")

    def _record_success(
        self, *, started: float, rows: int, observation_time: str | None
    ) -> None:
        now = datetime.now()
        self._failure_count = 0
        self._circuit_open_until = None
        self._health = HealthItem(
            adapter="gdelt_events",
            label="GDELT 事件线索",
            state="healthy",
            last_success_at=now,
            observation_time=observation_time,
            rows=rows,
            latency_ms=round((time.perf_counter() - started) * 1000),
            message="GDELT 按需查询成功；结果仍需打开原文人工核验",
            last_attempt_at=now,
            cache_persisted=True,
            market_status="daily",
            market_status_label="约 15 分钟滚动更新",
            execution_mode="in_process_http",
            trust_level="partial",
            quality_score=80,
            quality_issues=[GDELT_NOTICE],
            circuit_state="closed",
            next_refresh_at=now + timedelta(seconds=GDELT_CACHE_TTL_SECONDS),
        )

    def _record_failure(self, exc: Exception, started: float) -> None:
        self._failure_count += 1
        opened = self._failure_count >= 3
        stats = self.database.gdelt_stats()
        if opened:
            self._circuit_open_until = self._monotonic() + 60
        self._health = self._health.model_copy(
            update={
                "state": "degraded" if stats["queries"] else "unavailable",
                "last_failure_at": datetime.now(),
                "last_attempt_at": datetime.now(),
                "consecutive_failures": self._failure_count,
                "message": str(exc)[:300],
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "trust_level": "partial" if stats["queries"] else "unavailable",
                "cache_persisted": bool(stats["queries"]),
                "circuit_state": "open" if opened else "closed",
                "next_retry_at": (
                    datetime.now() + timedelta(seconds=60) if opened else None
                ),
            }
        )

    def health_item(self) -> HealthItem:
        stats = self.database.gdelt_stats()
        if self._health.state == "not_checked" and stats["queries"]:
            age = self._cache_age(stats.get("last_fetched_at"))
            stale = age is None or age > GDELT_CACHE_TTL_SECONDS
            return self._health.model_copy(
                update={
                    "state": "degraded" if stale else "cached",
                    "rows": int(stats["articles"]),
                    "message": (
                        "GDELT 本地线索缓存已过期，等待按需刷新"
                        if stale
                        else "GDELT 本地线索缓存可用，尚未完成本次远端验证"
                    ),
                    "cache_age_seconds": age,
                    "cache_persisted": True,
                    "trust_level": "partial",
                    "quality_score": 70 if stale else 80,
                    "quality_issues": [GDELT_NOTICE],
                }
            )
        return self._health.model_copy(
            update={
                "rows": int(stats["articles"]),
                "cache_persisted": bool(stats["queries"]),
                "cache_age_seconds": self._cache_age(stats.get("last_fetched_at")),
            }
        )

    @staticmethod
    def _cache_age(value: Any) -> int | None:
        if not value:
            return None
        try:
            return max(
                0,
                int((datetime.now() - datetime.fromisoformat(str(value))).total_seconds()),
            )
        except ValueError:
            return None

    def test_connection(self) -> dict[str, Any]:
        dataset = self.search(
            '"sovereign debt"', days=1, limit=5, sort="datedesc", refresh=True
        )
        return {
            "ok": True,
            "rows": len(dataset.data.articles),
            "fetched_at": dataset.meta.fetched_at,
            "notice": GDELT_NOTICE,
        }

    def clear_cache(self) -> None:
        self.database.clear_gdelt_cache()
        self._failure_count = 0
        self._circuit_open_until = None
        self._health = HealthItem(
            adapter="gdelt_events",
            label="GDELT 事件线索",
            state="not_checked",
            market_status="daily",
            market_status_label="约 15 分钟滚动更新",
            execution_mode="in_process_http",
            trust_level="unavailable",
            message="GDELT 线索缓存已清空，等待下次按需检索",
        )
