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
            name="Python AKShare",
            category="market",
            state=market["state"],
            research_status=market["research_status"],
            access_mode="public",
            credential_configured=True,
            credential_source="not_required",
            capabilities=["中国固收行情", "人民币参考价", "可转债", "发行日历", "黄金与指数公开源预览（仅内存）"],
            storage_mode="mixed_upstream_cache",
            cache_ttl_seconds=None,
            persistence_notice=(
                "质量门通过后保存市场快照与本地历史；质量校验不是授权校验，保存与分享仍须遵守原始数据源条款。"
            ),
            license_name="AKShare 代码 MIT；数据另受上游条款约束",
            license_url="https://github.com/akfamily/akshare/blob/main/LICENSE",
            attribution="Python AKShare 及各原始数据提供方/取数中介；本产品未运行 AKTools 服务",
            terms_url="https://akshare.akfamily.xyz/introduction.html",
            docs_url="https://akshare.akfamily.xyz/",
            quota_notice="无统一配额；push2 明确限流后停止重试并在本进程冷却至少 5 分钟，不保证届时恢复；备用源成功不会解除主源冷却。",
            boundary_notice="官方声明用于学术研究；机构/商业使用、缓存和再分发需另核验原始数据源授权。非交易所直连，不承诺交易级实时性。",
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
                "FRED 内容（含 API 元数据）仅用于当前请求展示，不写入 SQLite；项目只保存用户选择的查询参数与应用生成的引用，不导出数值。"
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
            boundary_notice="自备 Key 不豁免条款；序列版权需分别核验。本产品保守排除 FRED 内容的 AI 处理，条款中的 AI 开发/训练限制不等于对所有推理情形的法律认定。",
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
            license_name="CC BY 4.0 为默认；数据集/指标另有标注优先",
            license_url="https://datacatalog.worldbank.org/public-licenses",
            attribution="World Bank, World Development Indicators",
            terms_url="https://datacatalog.worldbank.org/public-licenses",
            docs_url="https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
            quota_notice="公开 API；仅在用户打开比较或主动刷新时请求。",
            boundary_notice="保留署名和处理说明；第三方数据/指标可能有不同许可，以对应元数据为准。低频数据不替代实时主权风险或评级判断。",
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
                "GDELT 开放数据须署名并链接项目；这不授予新闻正文或图片的版权。媒体匹配仅为待核验线索，不生成风险评分。"
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
            "不通过 API 暴露明文。规则核验日期：2026-11-02；连接成功、数据质量与使用授权互不等同。"
        ),
    }
