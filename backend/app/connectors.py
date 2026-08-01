from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import ConnectorItem, HealthItem


_STATE_RANK = {
    "unavailable": 0,
    "not_checked": 1,
    "degraded": 2,
    "cached": 3,
    "healthy": 4,
}


def _latest_success(items: list[HealthItem]) -> datetime | None:
    values = [item.last_success_at for item in items if item.last_success_at]
    return max(values) if values else None


def _aggregate_market_health(items: list[HealthItem]) -> dict[str, Any]:
    if not items:
        return {
            "state": "not_checked",
            "research_status": "unchecked",
            "last_success_at": None,
            "adapter_count": 1,
            "available_adapters": 0,
        }
    ready = sum(item.research_status == "ready" for item in items)
    limited = sum(item.research_status == "limited" for item in items)
    blocked = sum(item.research_status == "blocked" for item in items)
    unchecked = sum(item.research_status == "unchecked" for item in items)
    available = ready + limited
    if ready == len(items):
        state = "healthy"
        research_status = "ready"
    elif available:
        state = "degraded"
        research_status = "limited"
    elif blocked:
        state = "unavailable"
        research_status = "blocked"
    else:
        state = max(items, key=lambda item: _STATE_RANK[item.state]).state
        research_status = "unchecked" if unchecked else "blocked"
    return {
        "state": state,
        "research_status": research_status,
        "last_success_at": _latest_success(items),
        "adapter_count": len(items),
        "available_adapters": available,
    }


def connector_catalog(
    *,
    market_health: list[HealthItem],
    fred_health: HealthItem,
    fred_status: dict[str, Any],
    world_bank_health: HealthItem,
    world_bank_stats: dict[str, Any],
    gdelt_health: HealthItem,
    gdelt_stats: dict[str, Any],
) -> dict[str, Any]:
    """Return one normalized, secret-free contract for every external provider."""

    market = _aggregate_market_health(market_health)
    connectors = [
        ConnectorItem(
            id="akshare",
            name="AKShare / AKTools",
            category="market",
            state=market["state"],
            research_status=market["research_status"],
            access_mode="public",
            credential_configured=True,
            credential_source="not_required",
            capabilities=["中国固收行情", "人民币参考价", "可转债", "发行日历"],
            storage_mode="mixed_upstream_cache",
            cache_ttl_seconds=None,
            persistence_notice=(
                "仅持久化经过质量门的市场快照与本地历史；上游网页口径和许可随适配器而异。"
            ),
            license_name="按各上游公开页面条款",
            license_url="https://akshare.akfamily.xyz/",
            attribution="AKShare / AKTools 及各原始公开数据页面",
            terms_url="https://akshare.akfamily.xyz/",
            docs_url="https://akshare.akfamily.xyz/",
            quota_notice="无统一配额；采用隔离进程、超时、熔断与错峰刷新。",
            boundary_notice="非交易所直连，不承诺逐笔、交易级实时性或全市场覆盖。",
            last_success_at=market["last_success_at"],
            cache_rows=0,
            adapter_count=market["adapter_count"],
            available_adapters=market["available_adapters"],
        ),
        ConnectorItem(
            id="fred",
            name="FRED",
            category="macro",
            state=fred_health.state,
            research_status=fred_health.research_status,
            access_mode="user_api_key",
            credential_configured=bool(fred_status.get("configured")),
            credential_source=str(fred_status.get("credential_source") or "none"),
            capabilities=["美国利率", "通胀", "就业与增长", "发布复盘"],
            storage_mode="request_scoped",
            cache_ttl_seconds=None,
            persistence_notice=(
                "观测值只在当前请求中处理，不写入 SQLite；项目只保存序列、变换与来源引用。"
            ),
            license_name="FRED API Terms of Use",
            license_url=str(fred_status.get("terms_url") or ""),
            attribution=(
                "This product uses the FRED® API but is not endorsed or "
                "certified by the Federal Reserve Bank of St. Louis."
            ),
            terms_url=str(fred_status.get("terms_url") or ""),
            docs_url="https://fred.stlouisfed.org/docs/api/fred/",
            quota_notice="使用用户自己的 API Key；请求按需发起，不进行后台观测值抓取。",
            boundary_notice="FRED 数据可能修订；版本复盘需记录 realtime_start。",
            last_success_at=fred_health.last_success_at,
            cache_rows=0,
            available_adapters=1 if fred_health.research_status in {"ready", "limited"} else 0,
        ),
        ConnectorItem(
            id="world_bank",
            name="World Bank",
            category="sovereign",
            state=world_bank_health.state,
            research_status=world_bank_health.research_status,
            access_mode="public",
            credential_configured=True,
            credential_source="not_required",
            capabilities=["全球主权比较", "增长与通胀", "财政与外部平衡"],
            storage_mode="persistent_cache",
            cache_ttl_seconds=7 * 24 * 60 * 60,
            persistence_notice="指标元数据和低频观测值在本地缓存 7 天并保留来源署名。",
            license_name="Creative Commons Attribution 4.0 (CC BY 4.0)",
            license_url="https://datacatalog.worldbank.org/public-licenses",
            attribution="World Bank, World Development Indicators",
            terms_url="https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
            docs_url="https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
            quota_notice="公开 API；仅在用户打开比较或主动刷新时请求。",
            boundary_notice="低频结构数据不能替代实时主权风险、市场价格或评级判断。",
            last_success_at=world_bank_health.last_success_at,
            cache_rows=int(world_bank_stats.get("points") or 0),
            available_adapters=(
                1
                if world_bank_health.research_status in {"ready", "limited"}
                else 0
            ),
        ),
        ConnectorItem(
            id="gdelt",
            name="GDELT DOC 2.0",
            category="events",
            state=gdelt_health.state,
            research_status=gdelt_health.research_status,
            access_mode="public",
            credential_configured=True,
            credential_source="not_required",
            capabilities=["新闻事件检索", "发行人线索", "国家与主题观察"],
            storage_mode="metadata_cache",
            cache_ttl_seconds=12 * 60 * 60,
            persistence_notice=(
                "只缓存查询、标题、链接、来源、语言和抓取时间；不抓取或保存文章正文。"
            ),
            license_name="GDELT open data terms",
            license_url="https://www.gdeltproject.org/about.html",
            attribution="The GDELT Project",
            terms_url="https://www.gdeltproject.org/about.html",
            docs_url="https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/",
            quota_notice="按需查询、同查询 12 小时缓存；远端请求至少间隔 5 秒。",
            boundary_notice=(
                "媒体匹配仅是待核验线索；覆盖量、语言和来源均存在偏差，不生成风险评分。"
            ),
            last_success_at=gdelt_health.last_success_at,
            cache_rows=int(gdelt_stats.get("articles") or 0),
            available_adapters=(
                1 if gdelt_health.research_status in {"ready", "limited"} else 0
            ),
        ),
    ]
    return {
        "generated_at": datetime.now(),
        "connectors": connectors,
        "policy": (
            "连接状态、缓存状态与研究可用性分开表达；所有凭据只返回配置状态，"
            "不通过 API 暴露明文。"
        ),
    }
