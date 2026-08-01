from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, computed_field, model_validator

T = TypeVar("T")


class SourceMeta(BaseModel):
    source: str
    source_url: str | None = None
    observation_time: str | None = None
    fetched_at: datetime
    stale: bool = False
    demo: bool = False
    warnings: list[str] = Field(default_factory=list)
    cache_age_seconds: int | None = None
    market_status: Literal[
        "pre_open",
        "trading",
        "session_break",
        "closed",
        "non_trading_day",
        "daily",
        "unknown",
    ] = "unknown"
    market_status_label: str = "状态未知"
    data_state: Literal["live", "latest", "cached", "stale", "demo"] = "latest"
    quality_score: int = Field(default=100, ge=0, le=100)
    quality_issues: list[str] = Field(default_factory=list)
    trust_level: Literal[
        "trusted", "partial", "suspicious", "unavailable"
    ] = "trusted"
    suspicious_rows: int = Field(default=0, ge=0)


class Dataset(BaseModel, Generic[T]):
    data: T
    meta: SourceMeta


class HealthItem(BaseModel):
    adapter: str
    label: str
    state: Literal[
        "healthy", "cached", "degraded", "unavailable", "not_checked"
    ]
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    observation_time: str | None = None
    rows: int = 0
    latency_ms: int | None = None
    message: str | None = None
    last_attempt_at: datetime | None = None
    consecutive_failures: int = 0
    cache_age_seconds: int | None = None
    cache_persisted: bool = False
    market_status: Literal[
        "pre_open",
        "trading",
        "session_break",
        "closed",
        "non_trading_day",
        "daily",
        "unknown",
    ] = "unknown"
    market_status_label: str = "状态未知"
    quality_score: int = Field(default=100, ge=0, le=100)
    quality_issues: list[str] = Field(default_factory=list)
    trust_level: Literal[
        "trusted", "partial", "suspicious", "unavailable"
    ] = "trusted"
    suspicious_rows: int = Field(default=0, ge=0)
    execution_mode: Literal[
        "isolated_process", "in_process_http", "local_demo"
    ] = "isolated_process"
    refreshing: bool = False
    circuit_state: Literal["closed", "open", "half_open"] = "closed"
    next_retry_at: datetime | None = None
    next_refresh_at: datetime | None = None
    @computed_field
    @property
    def research_status(self) -> Literal["ready", "limited", "blocked", "unchecked"]:
        if self.state == "not_checked":
            return "unchecked"
        if self.state == "unavailable" or self.trust_level in {
            "suspicious",
            "unavailable",
        }:
            return "blocked"
        if self.state == "healthy" and self.trust_level == "trusted":
            return "ready"
        return "limited"


WatchObjectType = Literal["bond", "future", "convertible", "macro", "fx"]
ResearchProjectObjectType = Literal[
    "bond", "future", "convertible", "macro", "fx", "issuer"
]
ResearchStatus = Literal["draft", "tracking", "formed", "review", "archived"]


def _is_fred_evidence(source_summary: str, payload: dict[str, Any]) -> bool:
    if "FRED" in source_summary.upper():
        return True
    pending: list[Any] = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                normalized_key = str(key).lower()
                text = str(value or "").upper() if not isinstance(value, (dict, list)) else ""
                if normalized_key in {"provider", "source", "adapter"} and "FRED" in text:
                    return True
                if normalized_key in {"source_url", "original_source_url", "terms_url"} and (
                    "STLOUISFED.ORG" in text or "FRED" in text
                ):
                    return True
                pending.append(value)
        elif isinstance(current, list):
            pending.extend(current)
    return False


def _fred_payload_contains_values(payload: dict[str, Any]) -> bool:
    forbidden = {
        "actual",
        "actual_value",
        "chart",
        "data",
        "data_points",
        "dates",
        "observation",
        "observations",
        "value",
        "values",
    }
    pending: list[Any] = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            if forbidden.intersection(str(key).lower() for key in current):
                return True
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


class WatchlistCreate(BaseModel):
    object_type: WatchObjectType
    object_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)
    group_name: str = Field(default="默认分组", min_length=1, max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=20)
    research_status: ResearchStatus = "draft"
    pinned: bool = False
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )


class WatchlistItem(WatchlistCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class WatchlistUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    group_name: str | None = Field(default=None, min_length=1, max_length=60)
    tags: list[str] | None = Field(default=None, max_length=20)
    research_status: ResearchStatus | None = None
    pinned: bool | None = None
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )


class ResearchEvidenceCreate(BaseModel):
    evidence_type: Literal["chart", "table", "snapshot", "note"]
    title: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_summary: str = Field(default="", max_length=500)
    observation_start: str | None = Field(default=None, max_length=40)
    observation_end: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def validate_payload_boundary(self):
        encoded = json.dumps(self.payload, ensure_ascii=False, default=str).encode()
        if len(encoded) > 128 * 1024:
            raise ValueError("单条研究证据不得超过 128 KB")
        if _is_fred_evidence(self.source_summary, self.payload):
            if self.payload.get("storage_mode") != "reference_only":
                raise ValueError("FRED 研究证据仅允许保存引用，不保存观测值")
            if _fred_payload_contains_values(self.payload):
                raise ValueError("FRED 引用证据不得包含观测值")
        return self


class ResearchEvidenceItem(ResearchEvidenceCreate):
    id: int
    project_id: int
    created_at: datetime


class ResearchProjectActivityItem(BaseModel):
    id: int
    project_id: int
    event_type: Literal[
        "created",
        "updated",
        "evidence_added",
        "evidence_removed",
        "entry_added",
        "entry_updated",
        "entry_removed",
        "imported",
    ]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ResearchProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default="", max_length=2_000)
    hypothesis: str = Field(default="", max_length=2_000)
    status: ResearchStatus = "draft"
    confidence: int = Field(default=50, ge=0, le=100)
    horizon: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=30)
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    conclusion: str = Field(default="", max_length=4_000)


class ResearchProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    question: str | None = Field(default=None, max_length=2_000)
    hypothesis: str | None = Field(default=None, max_length=2_000)
    status: ResearchStatus | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    horizon: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=30)
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    conclusion: str | None = Field(default=None, max_length=4_000)


ResearchEntryType = Literal["note", "counter_evidence", "task", "review"]


class ResearchEntryCreate(BaseModel):
    entry_type: ResearchEntryType = "note"
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(default="", max_length=8_000)
    status: Literal["open", "done"] = "open"
    due_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )


class ResearchEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, max_length=8_000)
    status: Literal["open", "done"] | None = None
    due_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )


class ResearchEntryItem(ResearchEntryCreate):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime


ResearchActionType = Literal["task", "counter_evidence", "review"]
ResearchActionStatus = Literal["proposed", "accepted", "dismissed", "undone"]


class ResearchActionDraftItem(BaseModel):
    id: int
    project_id: int
    action_type: ResearchActionType
    title: str
    content: str = ""
    status: ResearchActionStatus
    source: str
    source_reference: str = ""
    created_entry_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ResearchActionAcceptRequest(BaseModel):
    draft_ids: list[int] = Field(min_length=1, max_length=20)
    confirm: Literal[True]

    @model_validator(mode="after")
    def normalize_draft_ids(self):
        self.draft_ids = list(dict.fromkeys(self.draft_ids))
        return self


class ResearchProjectItem(ResearchProjectCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    evidence: list[ResearchEvidenceItem] = Field(default_factory=list)
    activity: list[ResearchProjectActivityItem] = Field(default_factory=list)
    entries: list[ResearchEntryItem] = Field(default_factory=list)


ResearchObjectType = Literal[
    "rates_theme",
    "macro_theme",
    "country",
    "issuer",
    "security",
    "release_event",
]
ResearchTopicStatus = Literal["active", "review", "archived"]
ResearchTopicComponentType = Literal[
    "market_pulse",
    "market_history",
    "fred_chart",
    "sovereign_compare",
    "event_radar",
    "project_summary",
    "recent_evidence",
]


class ResearchObjectItem(BaseModel):
    id: int
    object_type: ResearchObjectType
    object_key: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ResearchTopicComponent(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    component_type: ResearchTopicComponentType
    title: str = Field(min_length=1, max_length=160)
    config: dict[str, Any] = Field(default_factory=dict)
    order: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_config_boundary(self):
        encoded = json.dumps(self.config, ensure_ascii=False, default=str).encode()
        if len(encoded) > 32 * 1024:
            raise ValueError("单个专题组件配置不得超过 32 KB")
        config = dict(self.config)

        def config_list(key: str, label: str, *, upper: bool = False) -> list[str]:
            raw = config.get(key, [])
            if not isinstance(raw, list):
                raise ValueError(f"{label}必须为列表")
            values = [str(item).strip() for item in raw if str(item).strip()]
            return [item.upper() for item in values] if upper else values

        if self.component_type == "market_history":
            adapter = str(config.get("adapter") or "").strip()
            metric = str(config.get("metric") or "").strip()
            series = config_list("series", "本地历史组件序列")
            days = int(config.get("days") or 120)
            if adapter not in {"yield_curves", "fx_rmb_reference"}:
                raise ValueError("本地历史组件的数据源不受支持")
            if not metric or not 1 <= len(dict.fromkeys(series)) <= 8:
                raise ValueError("本地历史组件需配置指标和 1–8 条序列")
            if not 7 <= days <= 3_650:
                raise ValueError("本地历史组件时间范围应为 7–3650 天")
            config.update(
                adapter=adapter,
                metric=metric,
                series=list(dict.fromkeys(series)),
                days=days,
                unit=str(config.get("unit") or "").strip()[:20],
            )
        elif self.component_type == "fred_chart":
            series = config_list("series", "FRED 组件序列", upper=True)
            years = int(config.get("years") or 5)
            transform = str(config.get("transform") or "level")
            if not 1 <= len(dict.fromkeys(series)) <= 8 or any(
                not re.fullmatch(r"[A-Z0-9_.-]{1,32}", item) for item in series
            ):
                raise ValueError("FRED 组件需配置 1–8 个有效序列")
            if not 1 <= years <= 30:
                raise ValueError("FRED 组件时间范围应为 1–30 年")
            if transform not in {"level", "change", "normalize", "zscore", "yoy"}:
                raise ValueError("FRED 组件变换方式不受支持")
            config.update(
                series=list(dict.fromkeys(series)),
                years=years,
                transform=transform,
            )
        elif self.component_type == "sovereign_compare":
            countries = config_list("countries", "主权组件经济体", upper=True)
            start_year = int(config.get("start_year") or 2000)
            end_year = int(config.get("end_year") or datetime.now().year)
            indicator = str(config.get("indicator") or "").strip().upper()
            view = str(config.get("view") or "level")
            if not 2 <= len(dict.fromkeys(countries)) <= 8 or any(
                not re.fullmatch(r"[A-Z]{3}", item) for item in countries
            ):
                raise ValueError("主权组件需配置 2–8 个三位经济体代码")
            if not indicator or len(indicator) > 80:
                raise ValueError("主权组件指标代码无效")
            if start_year < 1960 or end_year < start_year or end_year - start_year > 50:
                raise ValueError("主权组件时间范围无效或超过 51 年")
            if view not in {"level", "change", "rank", "zscore"}:
                raise ValueError("主权组件比较方式不受支持")
            config.update(
                countries=list(dict.fromkeys(countries)),
                indicator=indicator,
                start_year=start_year,
                end_year=end_year,
                view=view,
            )
        elif self.component_type == "event_radar":
            query = str(config.get("query") or "").strip()
            days = int(config.get("days") or 7)
            limit = int(config.get("limit") or 20)
            sort = str(config.get("sort") or "datedesc").strip().lower()
            if (
                not 2 <= len(query) <= 200
                or any(ord(character) < 32 for character in query)
            ):
                raise ValueError("事件雷达需配置 2–200 字符的有效检索词")
            if not 1 <= days <= 90:
                raise ValueError("事件雷达时间范围应为 1–90 天")
            if not 5 <= limit <= 50:
                raise ValueError("事件雷达返回数量应为 5–50 条")
            if sort not in {"datedesc", "hybridrel"}:
                raise ValueError("事件雷达排序方式不受支持")
            config.update(query=query, days=days, limit=limit, sort=sort)
        self.config = config
        return self


class ResearchTopicProjectItem(BaseModel):
    id: int
    title: str
    status: ResearchStatus
    confidence: int
    next_review_date: str | None = None
    updated_at: datetime


class ResearchTopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default="", max_length=2_000)
    description: str = Field(default="", max_length=4_000)
    status: ResearchTopicStatus = "active"
    object_type: ResearchObjectType = "macro_theme"
    object_key: str = Field(min_length=1, max_length=120)
    object_name: str = Field(min_length=1, max_length=160)
    object_description: str = Field(default="", max_length=1_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    components: list[ResearchTopicComponent] = Field(default_factory=list, max_length=20)
    project_ids: list[int] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def normalize_topic(self):
        self.object_key = self.object_key.strip()
        self.object_name = self.object_name.strip()
        if not self.object_key or not self.object_name:
            raise ValueError("研究对象缺少标识或名称")
        self.tags = list(dict.fromkeys(item.strip() for item in self.tags if item.strip()))
        self.project_ids = list(dict.fromkeys(self.project_ids))
        component_ids = [item.id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("专题组件 ID 不得重复")
        self.components = sorted(self.components, key=lambda item: (item.order, item.id))
        return self


class ResearchTopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    question: str | None = Field(default=None, max_length=2_000)
    description: str | None = Field(default=None, max_length=4_000)
    status: ResearchTopicStatus | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    components: list[ResearchTopicComponent] | None = Field(default=None, max_length=20)
    project_ids: list[int] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def normalize_topic_update(self):
        if self.tags is not None:
            self.tags = list(
                dict.fromkeys(item.strip() for item in self.tags if item.strip())
            )
        if self.project_ids is not None:
            self.project_ids = list(dict.fromkeys(self.project_ids))
        if self.components is not None:
            component_ids = [item.id for item in self.components]
            if len(component_ids) != len(set(component_ids)):
                raise ValueError("专题组件 ID 不得重复")
            self.components = sorted(
                self.components, key=lambda item: (item.order, item.id)
            )
        return self


class ResearchTopicItem(BaseModel):
    id: int
    title: str
    question: str
    description: str
    status: ResearchTopicStatus
    tags: list[str] = Field(default_factory=list)
    components: list[ResearchTopicComponent] = Field(default_factory=list)
    research_object: ResearchObjectItem
    projects: list[ResearchTopicProjectItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ResearchTopicTemplateCreate(BaseModel):
    template_id: Literal[
        "china_rates",
        "sino_us_rates",
        "rmb_rates",
        "global_inflation",
        "blank",
    ]
    title: str | None = Field(default=None, min_length=1, max_length=160)
    project_ids: list[int] = Field(default_factory=list, max_length=30)


class IssuerEventTopicCreate(BaseModel):
    issuer: str = Field(min_length=1, max_length=160)
    project_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def normalize_issuer(self):
        self.issuer = " ".join(self.issuer.split())
        if not self.issuer:
            raise ValueError("发行人名称不能为空")
        return self


class EvidenceBasketCreate(ResearchEvidenceCreate):
    origin_page: str = Field(default="", max_length=80)
    topic_id: int | None = None


class EvidenceBasketItem(ResearchEvidenceCreate):
    id: int
    origin_page: str
    topic_id: int | None = None
    research_object_id: int | None = None
    created_at: datetime


class EvidenceBasketCommit(BaseModel):
    project_id: int
    item_ids: list[int] = Field(min_length=1, max_length=50)
    topic_id: int | None = None

    @model_validator(mode="after")
    def normalize_item_ids(self):
        self.item_ids = list(dict.fromkeys(self.item_ids))
        return self


class EvidenceBasketDelete(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def normalize_item_ids(self):
        self.item_ids = list(dict.fromkeys(self.item_ids))
        return self


class GdeltEventItem(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=500)
    url: str
    domain: str = ""
    seen_at: str | None = None
    language: str = ""
    source_country: str = ""
    image_url: str | None = None


class GdeltEventRadarData(BaseModel):
    query: str
    days: int
    sort: Literal["datedesc", "hybridrel"]
    article_count: int
    source_count: int
    country_count: int
    latest_seen_at: str | None = None
    source_distribution: list[dict[str, Any]] = Field(default_factory=list)
    country_distribution: list[dict[str, Any]] = Field(default_factory=list)
    articles: list[GdeltEventItem] = Field(default_factory=list)
    storage_mode: Literal["metadata_cache"] = "metadata_cache"
    verification_status: Literal["unverified_clue"] = "unverified_clue"
    attribution: str
    license_url: str
    notice: str


class ConnectorItem(BaseModel):
    id: Literal["akshare", "fred", "world_bank", "gdelt"]
    name: str
    category: Literal["market", "macro", "sovereign", "events"]
    state: Literal[
        "healthy", "cached", "degraded", "unavailable", "not_checked"
    ]
    research_status: Literal["ready", "limited", "blocked", "unchecked"]
    enabled: bool = True
    access_mode: Literal["public", "user_api_key"]
    credential_configured: bool
    credential_source: Literal["none", "environment", "keychain", "not_required"]
    capabilities: list[str] = Field(default_factory=list)
    storage_mode: Literal[
        "persistent_cache", "request_scoped", "mixed_upstream_cache", "metadata_cache"
    ]
    cache_ttl_seconds: int | None = None
    persistence_notice: str
    license_name: str
    license_url: str
    attribution: str
    terms_url: str
    docs_url: str
    quota_notice: str
    boundary_notice: str
    last_success_at: datetime | None = None
    cache_rows: int = Field(default=0, ge=0)
    adapter_count: int = Field(default=1, ge=1)
    available_adapters: int = Field(default=0, ge=0)


class ResearchProjectTemplateCreate(BaseModel):
    template_id: Literal[
        "blank",
        "rates_direction",
        "macro_release",
        "convertible_event",
        "credit_observation",
        "sovereign_comparison",
    ] = "blank"
    object_type: ResearchProjectObjectType | None = None
    object_id: str | None = Field(default=None, max_length=80)
    object_name: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=300)
    observation_time: str | None = Field(default=None, max_length=40)
    question: str | None = Field(default=None, max_length=2_000)
    context_note: str = Field(default="", max_length=2_000)


class ResearchSignalSettings(BaseModel):
    funding_change_bp: float = Field(default=1.0, ge=0.1, le=50)
    curve_change_bp: float = Field(default=1.0, ge=0.1, le=50)
    curve_spread_bp: float = Field(default=20.0, ge=1, le=300)
    futures_change_pct: float = Field(default=0.1, ge=0.01, le=10)
    bond_change_bp: float = Field(default=2.0, ge=0.1, le=50)


class ReleaseReviewCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    series_id: str = Field(pattern=r"^[A-Z0-9._-]{1,40}$")
    release_name: str = Field(default="", max_length=160)
    release_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    observation_period: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    expected_value: float = Field(allow_inf_nan=False)
    expected_unit: str = Field(default="", max_length=40)
    project_id: int | None = None
    pre_window_days: int = Field(default=5, ge=1, le=60)
    post_window_days: int = Field(default=5, ge=1, le=60)
    notes: str = Field(default="", max_length=4_000)


class ReleaseReviewUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    series_id: str | None = Field(default=None, pattern=r"^[A-Z0-9._-]{1,40}$")
    release_name: str | None = Field(default=None, max_length=160)
    release_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    observation_period: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    expected_value: float | None = Field(default=None, allow_inf_nan=False)
    expected_unit: str | None = Field(default=None, max_length=40)
    project_id: int | None = None
    pre_window_days: int | None = Field(default=None, ge=1, le=60)
    post_window_days: int | None = Field(default=None, ge=1, le=60)
    notes: str | None = Field(default=None, max_length=4_000)
    reviewed_realtime_start: str | None = Field(default=None, max_length=40)
    reviewed_at: datetime | None = None


class ReleaseReviewItem(ReleaseReviewCreate):
    id: int
    reviewed_realtime_start: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreditObservationCreate(BaseModel):
    bond_code: str = Field(min_length=1, max_length=40)
    bond_name: str = Field(min_length=1, max_length=160)
    issuer: str = Field(default="", max_length=200)
    canonical_issuer: str = Field(default="", max_length=200)
    sector: str = Field(default="", max_length=120)
    region: str = Field(default="", max_length=120)
    issuer_type: str = Field(default="", max_length=80)
    maturity_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    put_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    rating: str = Field(default="", max_length=40)
    rating_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    yield_pct: float | None = Field(default=None, allow_inf_nan=False)
    yield_observation_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    benchmark_tenor: Literal["1Y", "3Y", "5Y", "7Y", "10Y"] | None = None
    benchmark_yield_pct: float | None = Field(default=None, allow_inf_nan=False)
    benchmark_observation_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    source_note: str = Field(default="", max_length=1_000)
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    watch_status: Literal["active", "watch", "review", "archived"] = "active"


class CreditObservationUpdate(BaseModel):
    issuer: str | None = Field(default=None, max_length=200)
    canonical_issuer: str | None = Field(default=None, max_length=200)
    sector: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    issuer_type: str | None = Field(default=None, max_length=80)
    maturity_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    put_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    rating: str | None = Field(default=None, max_length=40)
    rating_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    yield_pct: float | None = Field(default=None, allow_inf_nan=False)
    yield_observation_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    benchmark_tenor: Literal["1Y", "3Y", "5Y", "7Y", "10Y"] | None = None
    benchmark_yield_pct: float | None = Field(default=None, allow_inf_nan=False)
    benchmark_observation_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    source_note: str | None = Field(default=None, max_length=1_000)
    next_review_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    watch_status: Literal["active", "watch", "review", "archived"] | None = None


class CreditObservationItem(CreditObservationCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class CreditPortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    observation_ids: list[int] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def normalize_observation_ids(self):
        self.observation_ids = list(dict.fromkeys(self.observation_ids))
        return self


class CreditPortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1_000)
    observation_ids: list[int] | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def normalize_observation_ids(self):
        if self.observation_ids is not None:
            self.observation_ids = list(dict.fromkeys(self.observation_ids))
        return self


class CreditSignalConfirmationCreate(BaseModel):
    note: str = Field(default="", max_length=1_000)
    project_id: int | None = Field(default=None, ge=1)


class MarketSnapshotCreate(BaseModel):
    signal_ids: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=1_000)


class SovereignSnapshotCreate(BaseModel):
    country_codes: list[str] = Field(min_length=2, max_length=8)
    indicator_id: str = Field(min_length=1, max_length=80)
    start_year: int = Field(ge=1960, le=2100)
    end_year: int = Field(ge=1960, le=2100)
    view: Literal["level", "change", "rank", "zscore"] = "level"
    note: str = Field(default="", max_length=1_000)

    @model_validator(mode="after")
    def validate_years(self):
        if self.start_year > self.end_year:
            raise ValueError("起始年份不得晚于结束年份")
        if self.end_year - self.start_year > 50:
            raise ValueError("主权证据最多包含 51 个年度")
        normalized = [
            item.strip().upper() for item in self.country_codes if item.strip()
        ]
        if not 2 <= len(dict.fromkeys(normalized)) <= 8:
            raise ValueError("主权比较需选择 2–8 个不同经济体")
        self.country_codes = list(dict.fromkeys(normalized))
        self.indicator_id = self.indicator_id.strip().upper()
        return self


class FredSettingsUpdate(BaseModel):
    api_key: str = Field(pattern=r"^[a-z0-9]{32}$")


class AiHubMixSettingsUpdate(BaseModel):
    api_key: str = Field(pattern=r"^sk-[A-Za-z0-9_-]{20,200}$")


class AiInsightPolicyUpdate(BaseModel):
    enabled: bool = False
    trigger: Literal["manual", "data_change", "daily"] = "manual"


class AiRuntimeSettingsUpdate(BaseModel):
    daily_call_limit: int = Field(default=20, ge=1, le=200)
    daily_token_limit: int = Field(default=100_000, ge=1_000, le=2_000_000)
    page_insights: dict[
        Literal["market", "project", "credit", "topic"], AiInsightPolicyUpdate
    ]

    @model_validator(mode="after")
    def require_all_insight_policies(self):
        required = {"market", "project", "credit", "topic"}
        if set(self.page_insights) != required:
            raise ValueError("页面洞察设置必须同时包含市场、项目、信用和专题四个模块")
        return self


class AiInsightGenerateRequest(BaseModel):
    project_id: int | None = Field(default=None, ge=1)
    topic_id: int | None = Field(default=None, ge=1)
    trigger_reason: Literal["manual", "data_change", "daily"] = "manual"
    force: bool = False
    confirm_external_processing: bool = False


class AiAssistantRequest(BaseModel):
    scenario: Literal["help", "market", "research"]
    question: str = Field(min_length=2, max_length=1_200)
    project_id: int | None = Field(default=None, ge=1)
    current_page: str = Field(default="", max_length=80)
    confirm_external_processing: bool = False

    @model_validator(mode="after")
    def normalize_question(self):
        self.question = " ".join(self.question.split())
        self.current_page = self.current_page.strip()
        if len(self.question) < 2:
            raise ValueError("问题至少需要 2 个字符")
        return self


class AlertCreate(BaseModel):
    object_type: Literal["bond", "future", "convertible"]
    object_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    metric: Literal[
        "price",
        "yield",
        "change_bp",
        "change_pct",
        "volume",
        "open_interest",
        "premium_pct",
        "double_low",
        "ytm_pct",
    ]
    operator: Literal[">", ">=", "<", "<="]
    threshold: float = Field(allow_inf_nan=False)
    cooldown_minutes: int = Field(default=30, ge=1, le=10_080)
    max_triggers_per_day: int = Field(default=3, ge=1, le=50)
    quiet_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True

    @model_validator(mode="after")
    def validate_metric_for_object(self) -> "AlertCreate":
        allowed = {
            "bond": {"price", "yield", "change_bp"},
            "future": {"price", "change_pct", "volume", "open_interest"},
            "convertible": {
                "price",
                "change_pct",
                "premium_pct",
                "double_low",
                "ytm_pct",
            },
        }
        if self.metric not in allowed[self.object_type]:
            raise ValueError("该指标不适用于所选标的类型")
        if bool(self.quiet_start) != bool(self.quiet_end):
            raise ValueError("静默时段必须同时提供开始和结束时间")
        if self.quiet_start and self.quiet_start == self.quiet_end:
            raise ValueError("静默时段开始和结束不能相同")
        return self


class AlertItem(AlertCreate):
    id: int
    created_at: datetime
    last_matched: bool | None = None
    last_value: float | None = None
    last_evaluated_at: datetime | None = None


class AlertUpdate(BaseModel):
    enabled: bool


class AlertTriggerItem(BaseModel):
    id: int
    alert_id: int
    object_type: str
    object_id: str
    name: str
    metric: str
    operator: str
    threshold: float
    trigger_value: float
    source: str
    observation_time: str | None = None
    triggered_at: datetime
    read: bool = False


class SearchResult(BaseModel):
    object_type: Literal["bond", "future", "convertible", "macro", "fx", "topic"]
    object_id: str
    name: str
    subtitle: str = ""
    page: Literal[
        "bonds",
        "futures",
        "convertibles",
        "macro",
        "sovereign",
        "fx",
        "topics",
    ]
    updated_at: datetime


class BondCalculatorRequest(BaseModel):
    settlement_date: str
    maturity_date: str
    coupon_rate_pct: float = Field(ge=0, le=100)
    clean_price: float = Field(gt=0)
    face_value: float = Field(default=100, gt=0)
    frequency: Literal[1, 2, 4, 12] = 2
    position_face_value: float = Field(default=1_000_000, gt=0)
    day_count: Literal["ACT/365", "ACT/ACT", "30/360"] = "ACT/365"


class CashFlow(BaseModel):
    date: str
    years: float
    amount: float
    present_value: float


class BondCalculatorResult(BaseModel):
    accrued_interest: float
    dirty_price: float
    ytm_pct: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float
    scenario_prices: dict[str, float]
    cash_flows: list[CashFlow]
    methodology: str


JsonDict = dict[str, Any]
