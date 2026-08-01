from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .models import (
    AlertCreate,
    AlertItem,
    AlertTriggerItem,
    SearchResult,
    Dataset,
    CreditObservationCreate,
    CreditObservationItem,
    CreditObservationUpdate,
    CreditPortfolioCreate,
    CreditPortfolioUpdate,
    ReleaseReviewCreate,
    ReleaseReviewItem,
    ReleaseReviewUpdate,
    ResearchEntryCreate,
    ResearchEntryItem,
    ResearchEntryUpdate,
    ResearchActionDraftItem,
    ResearchEvidenceCreate,
    ResearchEvidenceItem,
    EvidenceBasketCommit,
    EvidenceBasketCreate,
    EvidenceBasketItem,
    ResearchObjectItem,
    ResearchProjectActivityItem,
    ResearchProjectCreate,
    ResearchProjectItem,
    ResearchProjectUpdate,
    ResearchTopicCreate,
    ResearchTopicItem,
    ResearchTopicProjectItem,
    ResearchTopicUpdate,
    WatchlistCreate,
    WatchlistItem,
    WatchlistUpdate,
)

RESEARCH_OBJECT_TYPES = {
    "rates_theme",
    "macro_theme",
    "country",
    "issuer",
    "security",
    "release_event",
}


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            # sqlite3.Connection.__exit__ only commits or rolls back; it does
            # not close the file descriptor. Keep those transaction semantics
            # while making every database operation release its handle.
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS watchlist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    group_name TEXT NOT NULL DEFAULT '默认分组',
                    tags TEXT NOT NULL DEFAULT '[]',
                    research_status TEXT NOT NULL DEFAULT 'draft',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    next_review_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(object_type, object_id)
                );
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
                    max_triggers_per_day INTEGER NOT NULL DEFAULT 3,
                    quiet_start TEXT,
                    quiet_end TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alert_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    trigger_value REAL NOT NULL,
                    source TEXT NOT NULL,
                    observation_time TEXT,
                    triggered_at TEXT NOT NULL,
                    read INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(alert_id) REFERENCES alert_rules(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_alert_triggers_alert_time
                    ON alert_triggers(alert_id, triggered_at DESC);
                CREATE TABLE IF NOT EXISTS alert_state (
                    alert_id INTEGER PRIMARY KEY,
                    last_matched INTEGER NOT NULL,
                    last_value REAL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(alert_id) REFERENCES alert_rules(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS instrument_index (
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    subtitle TEXT NOT NULL DEFAULT '',
                    aliases TEXT NOT NULL DEFAULT '',
                    page TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(object_type, object_id)
                );
                CREATE INDEX IF NOT EXISTS idx_instrument_index_name
                    ON instrument_index(name);
                CREATE TABLE IF NOT EXISTS market_history (
                    adapter TEXT NOT NULL,
                    series_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    observation_time TEXT NOT NULL,
                    value REAL NOT NULL,
                    source TEXT NOT NULL,
                    quality_score INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(adapter, series_key, metric, observation_time)
                );
                CREATE INDEX IF NOT EXISTS idx_market_history_lookup
                    ON market_history(adapter, metric, observation_time);
                CREATE TABLE IF NOT EXISTS daily_reports (
                    report_date TEXT PRIMARY KEY,
                    report_mode TEXT NOT NULL,
                    confidence_level TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    hypothesis TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    confidence INTEGER NOT NULL DEFAULT 50,
                    horizon TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    next_review_date TEXT,
                    conclusion TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_projects_status_review
                    ON research_projects(status, next_review_date, updated_at DESC);
                CREATE TABLE IF NOT EXISTS research_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    evidence_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    source_summary TEXT NOT NULL DEFAULT '',
                    observation_start TEXT,
                    observation_end TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_research_evidence_project
                    ON research_evidence(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS research_project_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_research_project_activity
                    ON research_project_activity(project_id, created_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS research_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    entry_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    due_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_research_entries_project
                    ON research_entries(project_id, created_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS research_action_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'proposed',
                    source TEXT NOT NULL,
                    source_reference TEXT NOT NULL DEFAULT '',
                    created_entry_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(created_entry_id) REFERENCES research_entries(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_action_drafts_project
                    ON research_action_drafts(project_id, status, created_at DESC);
                CREATE TABLE IF NOT EXISTS research_project_origins (
                    project_id INTEGER PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(template_id, object_type, object_id),
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS release_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    release_name TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL,
                    observation_period TEXT NOT NULL,
                    expected_value REAL NOT NULL,
                    expected_unit TEXT NOT NULL DEFAULT '',
                    project_id INTEGER,
                    pre_window_days INTEGER NOT NULL DEFAULT 5,
                    post_window_days INTEGER NOT NULL DEFAULT 5,
                    notes TEXT NOT NULL DEFAULT '',
                    reviewed_realtime_start TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_release_reviews_date
                    ON release_reviews(release_date DESC, id DESC);
                CREATE TABLE IF NOT EXISTS credit_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bond_code TEXT NOT NULL UNIQUE,
                    bond_name TEXT NOT NULL,
                    issuer TEXT NOT NULL DEFAULT '',
                    canonical_issuer TEXT NOT NULL DEFAULT '',
                    sector TEXT NOT NULL DEFAULT '',
                    region TEXT NOT NULL DEFAULT '',
                    issuer_type TEXT NOT NULL DEFAULT '',
                    maturity_date TEXT,
                    put_date TEXT,
                    rating TEXT NOT NULL DEFAULT '',
                    rating_date TEXT,
                    yield_pct REAL,
                    yield_observation_date TEXT,
                    benchmark_tenor TEXT,
                    benchmark_yield_pct REAL,
                    benchmark_observation_date TEXT,
                    source_note TEXT NOT NULL DEFAULT '',
                    next_review_date TEXT,
                    watch_status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credit_observation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observation_id INTEGER NOT NULL,
                    bond_code TEXT NOT NULL,
                    bond_name TEXT NOT NULL,
                    issuer TEXT NOT NULL DEFAULT '',
                    canonical_issuer TEXT NOT NULL DEFAULT '',
                    maturity_date TEXT,
                    put_date TEXT,
                    rating TEXT NOT NULL DEFAULT '',
                    rating_date TEXT,
                    yield_pct REAL,
                    yield_observation_date TEXT,
                    benchmark_tenor TEXT,
                    benchmark_yield_pct REAL,
                    benchmark_observation_date TEXT,
                    source_note TEXT NOT NULL DEFAULT '',
                    fingerprint TEXT NOT NULL UNIQUE,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(observation_id) REFERENCES credit_observations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_credit_history_observation
                    ON credit_observation_history(observation_id, yield_observation_date, recorded_at);
                CREATE TABLE IF NOT EXISTS credit_portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credit_portfolio_members (
                    portfolio_id INTEGER NOT NULL,
                    observation_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(portfolio_id, observation_id),
                    FOREIGN KEY(portfolio_id) REFERENCES credit_portfolios(id) ON DELETE CASCADE,
                    FOREIGN KEY(observation_id) REFERENCES credit_observations(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS credit_signal_confirmations (
                    signal_id TEXT PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    confirmed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(object_type, object_key)
                );
                CREATE INDEX IF NOT EXISTS idx_research_objects_name
                    ON research_objects(name);
                CREATE TABLE IF NOT EXISTS research_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    tags TEXT NOT NULL DEFAULT '[]',
                    components TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(object_id) REFERENCES research_objects(id) ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_research_topics_status
                    ON research_topics(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS research_topic_projects (
                    topic_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(topic_id, project_id),
                    FOREIGN KEY(topic_id) REFERENCES research_topics(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS research_project_objects (
                    project_id INTEGER NOT NULL,
                    object_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, object_id),
                    FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(object_id) REFERENCES research_objects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS research_evidence_objects (
                    evidence_id INTEGER NOT NULL,
                    object_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(evidence_id, object_id),
                    FOREIGN KEY(evidence_id) REFERENCES research_evidence(id) ON DELETE CASCADE,
                    FOREIGN KEY(object_id) REFERENCES research_objects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS research_evidence_basket (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER,
                    object_id INTEGER,
                    evidence_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    source_summary TEXT NOT NULL DEFAULT '',
                    observation_start TEXT,
                    observation_end TEXT,
                    origin_page TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(topic_id) REFERENCES research_topics(id) ON DELETE SET NULL,
                    FOREIGN KEY(object_id) REFERENCES research_objects(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_evidence_basket_created
                    ON research_evidence_basket(created_at DESC);
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS macro_series (
                    provider TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    title_zh TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    units TEXT NOT NULL DEFAULT '',
                    frequency TEXT NOT NULL DEFAULT '',
                    seasonal_adjustment TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    source_organization TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    last_updated TEXT,
                    license TEXT NOT NULL DEFAULT '',
                    attribution TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(provider, series_id)
                );
                CREATE TABLE IF NOT EXISTS macro_observations (
                    provider TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    observation_period TEXT NOT NULL,
                    value REAL,
                    realtime_start TEXT NOT NULL,
                    realtime_end TEXT,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(provider, series_id, observation_period, realtime_start)
                );
                CREATE INDEX IF NOT EXISTS idx_macro_observations_lookup
                    ON macro_observations(provider, series_id, observation_period);
                CREATE TABLE IF NOT EXISTS world_bank_countries (
                    country_code TEXT PRIMARY KEY,
                    iso2_code TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    name_zh TEXT NOT NULL DEFAULT '',
                    region_id TEXT NOT NULL DEFAULT '',
                    region_name TEXT NOT NULL DEFAULT '',
                    income_level_id TEXT NOT NULL DEFAULT '',
                    income_level_name TEXT NOT NULL DEFAULT '',
                    capital_city TEXT NOT NULL DEFAULT '',
                    longitude REAL,
                    latitude REAL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS world_bank_indicators (
                    indicator_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    title_zh TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    source_id TEXT NOT NULL DEFAULT '2',
                    source_name TEXT NOT NULL DEFAULT 'World Development Indicators',
                    source_note TEXT NOT NULL DEFAULT '',
                    source_organization TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT 'CC BY 4.0',
                    attribution TEXT NOT NULL DEFAULT '',
                    last_updated TEXT,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS world_bank_observations (
                    country_code TEXT NOT NULL,
                    indicator_id TEXT NOT NULL,
                    observation_year INTEGER NOT NULL,
                    value REAL,
                    obs_status TEXT NOT NULL DEFAULT '',
                    decimal_places INTEGER,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(country_code, indicator_id, observation_year)
                );
                CREATE INDEX IF NOT EXISTS idx_world_bank_observations_lookup
                    ON world_bank_observations(indicator_id, observation_year, country_code);
                CREATE TABLE IF NOT EXISTS gdelt_query_cache (
                    cache_key TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    result_limit INTEGER NOT NULL,
                    sort TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gdelt_query_cache_fetched
                    ON gdelt_query_cache(fetched_at DESC);
                CREATE TABLE IF NOT EXISTS ai_usage_daily (
                    usage_date TEXT PRIMARY KEY,
                    calls INTEGER NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usage_date TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    context_key TEXT NOT NULL DEFAULT '',
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_usage_events_date_context
                    ON ai_usage_events(usage_date, context_type, created_at DESC);
                CREATE TABLE IF NOT EXISTS ai_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context_type TEXT NOT NULL,
                    context_key TEXT NOT NULL,
                    context_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'never_generated',
                    summary TEXT NOT NULL DEFAULT '',
                    context_summary TEXT NOT NULL DEFAULT '[]',
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    generated_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(context_type, context_key)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_insights_status
                    ON ai_insights(status, updated_at DESC);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (700, 'v0.7.0 research, release review and credit R1', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (701, 'v0.7.0.1 trusted candidate gates and project origins', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (800, 'v0.8.0 World Bank sovereign comparison cache', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (900, 'v0.9.0 topic research workspace and evidence basket', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (1100, 'v0.11.0 credit observation R2', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (1201, 'v0.12.1 GDELT event radar metadata cache', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (1301, 'v0.13.1 AI runtime budget and insight cache foundation', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (1410, 'v0.14.1 AI insight operations and scoped usage ledger', ?)
                """,
                (datetime.now().isoformat(),),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                VALUES (1600, 'v0.16.0 explicit research action drafts and undo ledger', ?)
                """,
                (datetime.now().isoformat(),),
            )
            credit_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(credit_observations)")
            }
            credit_migrations = {
                "canonical_issuer": "TEXT NOT NULL DEFAULT ''",
                "sector": "TEXT NOT NULL DEFAULT ''",
                "region": "TEXT NOT NULL DEFAULT ''",
                "issuer_type": "TEXT NOT NULL DEFAULT ''",
                "put_date": "TEXT",
                "next_review_date": "TEXT",
                "watch_status": "TEXT NOT NULL DEFAULT 'active'",
            }
            for column, definition in credit_migrations.items():
                if column not in credit_columns:
                    connection.execute(
                        f"ALTER TABLE credit_observations ADD COLUMN {column} {definition}"
                    )
            for row in connection.execute("SELECT * FROM credit_observations"):
                self._save_credit_history(
                    connection, row, str(row["updated_at"] or datetime.now().isoformat())
                )
            connection.execute("PRAGMA user_version=1600")
            watchlist_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(watchlist_items)")
            }
            watchlist_migrations = {
                "group_name": "TEXT NOT NULL DEFAULT '默认分组'",
                "tags": "TEXT NOT NULL DEFAULT '[]'",
                "research_status": "TEXT NOT NULL DEFAULT 'draft'",
                "pinned": "INTEGER NOT NULL DEFAULT 0",
                "next_review_date": "TEXT",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in watchlist_migrations.items():
                if column not in watchlist_columns:
                    connection.execute(
                        f"ALTER TABLE watchlist_items ADD COLUMN {column} {definition}"
                    )
            connection.execute(
                "UPDATE watchlist_items SET updated_at = created_at WHERE updated_at = ''"
            )
            alert_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(alert_rules)")
            }
            if "max_triggers_per_day" not in alert_columns:
                connection.execute(
                    "ALTER TABLE alert_rules ADD COLUMN max_triggers_per_day INTEGER NOT NULL DEFAULT 3"
                )
            if "quiet_start" not in alert_columns:
                connection.execute(
                    "ALTER TABLE alert_rules ADD COLUMN quiet_start TEXT"
                )
            if "quiet_end" not in alert_columns:
                connection.execute(
                    "ALTER TABLE alert_rules ADD COLUMN quiet_end TEXT"
                )
            connection.execute(
                """
                INSERT INTO research_project_activity
                    (project_id, event_type, summary, details, created_at)
                SELECT id, 'created', '项目记录开始', '{}', created_at
                FROM research_projects AS project
                WHERE NOT EXISTS (
                    SELECT 1 FROM research_project_activity AS activity
                    WHERE activity.project_id = project.id
                )
                """
            )

    @staticmethod
    def _history_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _future_observation(
        value: object, *, now: datetime | None = None
    ) -> bool:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return False
        try:
            observed = datetime.fromisoformat(text)
        except ValueError:
            try:
                return date.fromisoformat(text[:10]) > (now or datetime.now()).date()
            except ValueError:
                return False
        current = now or datetime.now(observed.tzinfo)
        if observed.tzinfo is None and current.tzinfo is not None:
            observed = observed.replace(tzinfo=current.tzinfo)
        elif observed.tzinfo is not None and current.tzinfo is None:
            current = current.replace(tzinfo=observed.tzinfo)
        return observed > current

    def calibrate_market_history(self, *, now: datetime | None = None) -> dict[str, int]:
        """Remove future-dated points produced by the pre-v0.6.1.1 futures bug."""
        current = now or datetime.now()
        today = current.date().isoformat()
        with self._connect() as connection:
            future = int(
                connection.execute(
                    "SELECT COUNT(*) FROM market_history WHERE observation_time > ?",
                    (today,),
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM market_history WHERE observation_time > ?", (today,)
            )
            pre_open = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM market_history
                    WHERE adapter = 'treasury_futures'
                      AND observation_time = ?
                      AND substr(recorded_at, 1, 10) = ?
                      AND substr(recorded_at, 12, 8) < '09:30:00'
                    """,
                    (today, today),
                ).fetchone()[0]
            )
            connection.execute(
                """
                DELETE FROM market_history
                WHERE adapter = 'treasury_futures'
                  AND observation_time = ?
                  AND substr(recorded_at, 1, 10) = ?
                  AND substr(recorded_at, 12, 8) < '09:30:00'
                """,
                (today, today),
            )
        return {
            "future_points_deleted": future,
            "pre_open_futures_deleted": pre_open,
        }

    def record_market_history(self, adapter: str, dataset: Dataset) -> int:
        """Persist compact, trusted research series instead of full market tables."""
        if (
            dataset.meta.demo
            or dataset.meta.stale
            or dataset.meta.trust_level == "unavailable"
            or (
                dataset.meta.trust_level == "partial"
                and dataset.meta.observation_time is None
            )
        ):
            return 0
        if dataset.meta.trust_level == "suspicious" and not isinstance(
            dataset.data, list
        ):
            return 0

        source = dataset.meta.source
        quality = dataset.meta.quality_score
        recorded_at = datetime.now().isoformat()
        raw_observation = (
            dataset.meta.observation_time
            or dataset.meta.fetched_at.date().isoformat()
        )
        if self._future_observation(raw_observation):
            return 0
        # Research history is intentionally daily: intraday refreshes update
        # the same point instead of growing large quote tables on a laptop.
        default_observation = (
            str(raw_observation).replace(" ", "T").split("T", 1)[0]
        )
        rows: list[tuple[str, str, str, str, str, float, str, int, str]] = []

        def add(
            series_key: object,
            label: object,
            metric: str,
            value: object,
            observation_time: object = default_observation,
        ) -> None:
            number = self._history_number(value)
            key = str(series_key or "").strip()
            observed = str(observation_time or "").strip()
            if number is None or not key or not observed:
                return
            rows.append(
                (
                    adapter,
                    key,
                    str(label or key),
                    metric,
                    observed,
                    number,
                    source,
                    quality,
                    recorded_at,
                )
            )

        data = dataset.data
        if adapter == "yield_curves" and isinstance(data, dict):
            history = data.get("history")
            if isinstance(history, list):
                for snapshot in history:
                    if not isinstance(snapshot, dict):
                        continue
                    observed = snapshot.get("date", default_observation)
                    values = snapshot.get("values", {})
                    spreads = snapshot.get("spreads_bp", {})
                    if isinstance(values, dict):
                        for tenor, value in values.items():
                            add(tenor, f"国债 {tenor}", "yield", value, observed)
                    if isinstance(spreads, dict):
                        for spread, value in spreads.items():
                            add(spread, spread, "spread_bp", value, observed)
        elif adapter == "fx_rmb_reference" and isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                history = item.get("history")
                if not isinstance(history, list):
                    continue
                for point in history:
                    if not isinstance(point, dict):
                        continue
                    add(
                        item.get("code"),
                        item.get("name"),
                        "mid",
                        point.get("mid"),
                        point.get("date"),
                    )
        elif isinstance(data, list):
            specifications: dict[str, tuple[str, str, tuple[str, ...]]] = {
                "money_rates": ("name", "name", ("value", "change_bp")),
                "money_fr": ("name", "name", ("value", "change_bp")),
                "money_fdr": ("name", "name", ("value", "change_bp")),
                "money_lpr": ("name", "name", ("value", "change_bp")),
                "spot_bonds": (
                    "code",
                    "name",
                    ("yield", "price", "change_bp", "volume"),
                ),
                "treasury_futures": (
                    "product",
                    "contract",
                    ("price", "change_pct", "volume", "open_interest"),
                ),
                "convertibles": (
                    "code",
                    "name",
                    ("price", "change_pct", "premium_pct", "double_low", "ytm_pct"),
                ),
            }
            specification = specifications.get(adapter)
            if specification:
                key_field, label_field, metrics = specification
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if item.get("quality_state") == "suspicious":
                        continue
                    for metric in metrics:
                        add(
                            item.get(key_field),
                            item.get(label_field),
                            metric,
                            item.get(metric),
                        )

        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO market_history
                    (adapter, series_key, label, metric, observation_time,
                     value, source, quality_score, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(adapter, series_key, metric, observation_time)
                DO UPDATE SET
                    label = excluded.label,
                    value = excluded.value,
                    source = excluded.source,
                    quality_score = excluded.quality_score,
                    recorded_at = excluded.recorded_at
                """,
                rows,
            )
            cutoff = (date.today() - timedelta(days=400)).isoformat()
            connection.execute(
                "DELETE FROM market_history WHERE observation_time < ?",
                (cutoff,),
            )
        return len(rows)

    def market_history(
        self,
        adapter: str,
        metric: str,
        *,
        series_keys: list[str] | None = None,
        days: int = 90,
    ) -> dict[str, Any]:
        cutoff = (date.today() - timedelta(days=max(1, min(days, 400)))).isoformat()
        parameters: list[Any] = [adapter, metric, cutoff]
        series_clause = ""
        cleaned_keys = [item.strip() for item in (series_keys or []) if item.strip()]
        if cleaned_keys:
            placeholders = ",".join("?" for _ in cleaned_keys)
            series_clause = f" AND series_key IN ({placeholders})"
            parameters.extend(cleaned_keys)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT series_key, label, observation_time, value
                FROM market_history
                WHERE adapter = ? AND metric = ? AND observation_time >= ?
                    {series_clause}
                ORDER BY observation_time ASC, series_key ASC
                """,
                parameters,
            ).fetchall()

        dates = sorted({str(row["observation_time"]) for row in rows})
        labels: dict[str, str] = {}
        values: dict[str, dict[str, float]] = {}
        for row in rows:
            key = str(row["series_key"])
            observed = str(row["observation_time"])
            labels[key] = str(row["label"])
            values.setdefault(key, {})[observed] = float(row["value"])
        unit = {
            "yield": "%",
            "value": "%",
            "spread_bp": "BP",
            "change_bp": "BP",
            "change_pct": "%",
            "price": "",
            "volume": "",
            "open_interest": "",
            "premium_pct": "%",
            "double_low": "",
            "ytm_pct": "%",
            "mid": "CNY",
        }.get(metric, "")
        return {
            "adapter": adapter,
            "metric": metric,
            "unit": unit,
            "dates": dates,
            "series": [
                {
                    "key": key,
                    "name": labels[key],
                    "values": [values[key].get(observed) for observed in dates],
                }
                for key in sorted(values)
            ],
        }

    def history_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS points,
                       COUNT(DISTINCT adapter) AS adapters,
                       MIN(observation_time) AS oldest,
                       MAX(observation_time) AS newest
                FROM market_history
                """
            ).fetchone()
        return dict(row) if row else {"points": 0, "adapters": 0, "oldest": None, "newest": None}

    def save_daily_report(self, report: dict[str, Any]) -> None:
        report_date = str(report.get("report_date") or "").strip()
        if not report_date:
            raise ValueError("日报缺少 report_date")
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_reports
                    (report_date, report_mode, confidence_level, payload,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    report_mode = excluded.report_mode,
                    confidence_level = excluded.confidence_level,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    report_date,
                    str(report.get("report_mode") or "intraday"),
                    str((report.get("confidence") or {}).get("level") or "low"),
                    json.dumps(report, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )

    def get_daily_report(self, report_date: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM daily_reports WHERE report_date = ?",
                (report_date,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def list_daily_reports(self, limit: int = 120) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT report_date, report_mode, confidence_level, updated_at
                FROM daily_reports
                ORDER BY report_date DESC
                LIMIT ?
                """,
                (max(1, min(limit, 400)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_watchlist(self) -> list[WatchlistItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM watchlist_items
                ORDER BY pinned DESC, updated_at DESC, created_at DESC
                """
            ).fetchall()
        return [self._watchlist_from_row(row) for row in rows]

    def add_watchlist(self, item: WatchlistCreate) -> WatchlistItem:
        now = datetime.now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlist_items
                (object_type, object_id, name, note, group_name, tags,
                 research_status, pinned, next_review_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_type, object_id)
                DO UPDATE SET
                    name=excluded.name,
                    note=excluded.note,
                    group_name=excluded.group_name,
                    tags=excluded.tags,
                    research_status=excluded.research_status,
                    pinned=excluded.pinned,
                    next_review_date=excluded.next_review_date,
                    updated_at=excluded.updated_at
                """,
                (
                    item.object_type,
                    item.object_id,
                    item.name,
                    item.note,
                    item.group_name,
                    json.dumps(item.tags, ensure_ascii=False),
                    item.research_status,
                    int(item.pinned),
                    item.next_review_date,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM watchlist_items
                WHERE object_type = ? AND object_id = ?
                """,
                (item.object_type, item.object_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("自选保存失败")
        return self._watchlist_from_row(row)

    def update_watchlist(
        self, item_id: int, update: WatchlistUpdate
    ) -> WatchlistItem | None:
        values = update.model_dump(exclude_unset=True)
        if not values:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM watchlist_items WHERE id = ?", (item_id,)
                ).fetchone()
            return self._watchlist_from_row(row) if row else None
        allowed = {
            "note",
            "group_name",
            "tags",
            "research_status",
            "pinned",
            "next_review_date",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for field, value in values.items():
            if field not in allowed:
                continue
            assignments.append(f"{field} = ?")
            if field == "tags":
                value = json.dumps(value or [], ensure_ascii=False)
            elif field == "pinned":
                value = int(bool(value))
            parameters.append(value)
        assignments.append("updated_at = ?")
        parameters.extend([datetime.now().isoformat(), item_id])
        with self._connect() as connection:
            connection.execute(
                f"UPDATE watchlist_items SET {', '.join(assignments)} WHERE id = ?",
                parameters,
            )
            row = connection.execute(
                "SELECT * FROM watchlist_items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._watchlist_from_row(row) if row else None

    def find_watchlist(self, object_type: str, object_id: str) -> WatchlistItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM watchlist_items
                WHERE object_type = ? AND object_id = ?
                """,
                (object_type, object_id),
            ).fetchone()
        return self._watchlist_from_row(row) if row else None

    def delete_watchlist(self, item_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM watchlist_items WHERE id = ?", (item_id,))

    def list_research_projects(self) -> list[ResearchProjectItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_projects
                ORDER BY CASE status WHEN 'archived' THEN 1 ELSE 0 END,
                         next_review_date IS NULL, next_review_date, updated_at DESC
                """
            ).fetchall()
        return [self._research_project_from_row(row, [], [], []) for row in rows]

    def get_research_project(self, project_id: int) -> ResearchProjectItem | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_projects WHERE id = ?", (project_id,)
            ).fetchone()
            evidence_rows = connection.execute(
                """
                SELECT * FROM research_evidence
                WHERE project_id = ? ORDER BY created_at DESC
                """,
                (project_id,),
            ).fetchall()
            activity_rows = connection.execute(
                """
                SELECT * FROM research_project_activity
                WHERE project_id = ? ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (project_id,),
            ).fetchall()
            entry_rows = connection.execute(
                """
                SELECT * FROM research_entries
                WHERE project_id = ? ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        if row is None:
            return None
        evidence = [self._research_evidence_from_row(item) for item in evidence_rows]
        activity = [self._research_activity_from_row(item) for item in activity_rows]
        entries = [self._research_entry_from_row(item) for item in entry_rows]
        return self._research_project_from_row(row, evidence, activity, entries)

    def find_research_project_by_origin(
        self, template_id: str, object_type: str, object_id: str
    ) -> ResearchProjectItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT project.id
                FROM research_project_origins AS origin
                JOIN research_projects AS project ON project.id = origin.project_id
                WHERE origin.template_id = ? AND origin.object_type = ?
                      AND origin.object_id = ?
                """,
                (template_id.strip(), object_type.strip() or "research", object_id.strip()),
            ).fetchone()
        return self.get_research_project(int(row["id"])) if row else None

    def set_research_project_origin(
        self,
        project_id: int,
        template_id: str,
        object_type: str,
        object_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_project_origins
                    (project_id, template_id, object_type, object_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(template_id, object_type, object_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    created_at = excluded.created_at
                """,
                (
                    project_id,
                    template_id.strip(),
                    object_type.strip() or "research",
                    object_id.strip(),
                    datetime.now().isoformat(),
                ),
            )

    def add_research_project(
        self, item: ResearchProjectCreate
    ) -> ResearchProjectItem:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_projects
                    (title, question, hypothesis, status, confidence, horizon,
                     tags, next_review_date, conclusion, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.title,
                    item.question,
                    item.hypothesis,
                    item.status,
                    item.confidence,
                    item.horizon,
                    json.dumps(item.tags, ensure_ascii=False),
                    item.next_review_date,
                    item.conclusion,
                    now,
                    now,
                ),
            )
            project_id = int(cursor.lastrowid or 0)
            self._insert_research_activity(
                connection,
                project_id,
                "created",
                "创建研究项目",
                {"status": item.status, "confidence": item.confidence},
                now,
            )
        saved = self.get_research_project(project_id)
        if saved is None:
            raise RuntimeError("研究项目保存失败")
        return saved

    def update_research_project(
        self, project_id: int, update: ResearchProjectUpdate
    ) -> ResearchProjectItem | None:
        current = self.get_research_project(project_id)
        if current is None:
            return None
        values = update.model_dump(exclude_unset=True)
        if values:
            allowed = {
                "title",
                "question",
                "hypothesis",
                "status",
                "confidence",
                "horizon",
                "tags",
                "next_review_date",
                "conclusion",
            }
            assignments: list[str] = []
            parameters: list[Any] = []
            changed_fields: list[str] = []
            activity_details: dict[str, Any] = {"fields": changed_fields}
            for field, value in values.items():
                if field not in allowed:
                    continue
                previous = getattr(current, field)
                if previous == value:
                    continue
                assignments.append(f"{field} = ?")
                parameters.append(
                    json.dumps(value or [], ensure_ascii=False)
                    if field == "tags"
                    else value
                )
                changed_fields.append(field)
                if field in {"status", "confidence"}:
                    activity_details[field] = {"before": previous, "after": value}
            if assignments:
                now = datetime.now().isoformat()
                assignments.append("updated_at = ?")
                parameters.extend([now, project_id])
                labels = {
                    "title": "标题",
                    "question": "研究问题",
                    "hypothesis": "初始假设",
                    "status": "状态",
                    "confidence": "置信度",
                    "horizon": "研究期限",
                    "tags": "标签",
                    "next_review_date": "复盘日期",
                    "conclusion": "结论与风险点",
                }
                summary = "更新" + "、".join(labels[field] for field in changed_fields)
                with self._connect() as connection:
                    connection.execute(
                        f"UPDATE research_projects SET {', '.join(assignments)} WHERE id = ?",
                        parameters,
                    )
                    self._insert_research_activity(
                        connection,
                        project_id,
                        "updated",
                        summary,
                        activity_details,
                        now,
                    )
        return self.get_research_project(project_id)

    def delete_research_project(self, project_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM research_projects WHERE id = ?", (project_id,)
            )
        return cursor.rowcount > 0

    def upsert_research_object(
        self,
        *,
        object_type: str,
        object_key: str,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> ResearchObjectItem:
        now = datetime.now().isoformat()
        normalized_key = object_key.strip()
        normalized_name = name.strip()
        if object_type not in RESEARCH_OBJECT_TYPES:
            raise ValueError("不支持的研究对象类型")
        if not normalized_key or not normalized_name:
            raise ValueError("研究对象缺少标识或名称")
        normalized_tags = list(
            dict.fromkeys(item.strip() for item in (tags or []) if item.strip())
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_objects
                    (object_type, object_key, name, description, tags,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_type, object_key) DO UPDATE SET
                    name = excluded.name,
                    description = CASE
                        WHEN excluded.description != '' THEN excluded.description
                        ELSE research_objects.description
                    END,
                    tags = CASE
                        WHEN excluded.tags != '[]' THEN excluded.tags
                        ELSE research_objects.tags
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    object_type,
                    normalized_key,
                    normalized_name,
                    description.strip(),
                    json.dumps(normalized_tags, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM research_objects
                WHERE object_type = ? AND object_key = ?
                """,
                (object_type, normalized_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("研究对象保存失败")
        return self._research_object_from_row(row)

    def list_research_topics(
        self,
        *,
        query: str = "",
        status: str | None = None,
        limit: int = 200,
    ) -> list[ResearchTopicItem]:
        clauses: list[str] = []
        parameters: list[Any] = []
        term = query.strip()
        if term:
            pattern = f"%{term}%"
            clauses.append(
                "(topic.title LIKE ? COLLATE NOCASE "
                "OR topic.question LIKE ? COLLATE NOCASE "
                "OR topic.description LIKE ? COLLATE NOCASE "
                "OR topic.tags LIKE ? COLLATE NOCASE "
                "OR object.name LIKE ? COLLATE NOCASE)"
            )
            parameters.extend([pattern] * 5)
        if status:
            clauses.append("topic.status = ?")
            parameters.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT topic.*, object.object_type, object.object_key,
                       object.name AS object_name,
                       object.description AS object_description,
                       object.tags AS object_tags,
                       object.created_at AS object_created_at,
                       object.updated_at AS object_updated_at
                FROM research_topics AS topic
                JOIN research_objects AS object ON object.id = topic.object_id
                {where}
                ORDER BY CASE topic.status WHEN 'archived' THEN 1 ELSE 0 END,
                         topic.updated_at DESC, topic.id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            if not rows:
                return []
            topic_ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in topic_ids)
            project_rows = connection.execute(
                f"""
                SELECT link.topic_id, project.id, project.title, project.status,
                       project.confidence, project.next_review_date,
                       project.updated_at
                FROM research_topic_projects AS link
                JOIN research_projects AS project ON project.id = link.project_id
                WHERE link.topic_id IN ({placeholders})
                ORDER BY CASE project.status WHEN 'archived' THEN 1 ELSE 0 END,
                         project.updated_at DESC
                """,
                topic_ids,
            ).fetchall()
        projects_by_topic: dict[int, list[sqlite3.Row]] = {}
        for project_row in project_rows:
            projects_by_topic.setdefault(int(project_row["topic_id"]), []).append(
                project_row
            )
        return [
            self._research_topic_from_row(
                row,
                projects_by_topic.get(int(row["id"]), []),
            )
            for row in rows
        ]

    def get_research_topic(self, topic_id: int) -> ResearchTopicItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT topic.*, object.object_type, object.object_key,
                       object.name AS object_name,
                       object.description AS object_description,
                       object.tags AS object_tags,
                       object.created_at AS object_created_at,
                       object.updated_at AS object_updated_at
                FROM research_topics AS topic
                JOIN research_objects AS object ON object.id = topic.object_id
                WHERE topic.id = ?
                """,
                (topic_id,),
            ).fetchone()
            project_rows = connection.execute(
                """
                SELECT project.id, project.title, project.status,
                       project.confidence, project.next_review_date,
                       project.updated_at
                FROM research_topic_projects AS link
                JOIN research_projects AS project ON project.id = link.project_id
                WHERE link.topic_id = ?
                ORDER BY CASE project.status WHEN 'archived' THEN 1 ELSE 0 END,
                         project.updated_at DESC
                """,
                (topic_id,),
            ).fetchall()
        if row is None:
            return None
        return self._research_topic_from_row(row, project_rows)

    def add_research_topic(self, item: ResearchTopicCreate) -> ResearchTopicItem:
        self._validate_project_ids(item.project_ids)
        research_object = self.upsert_research_object(
            object_type=item.object_type,
            object_key=item.object_key,
            name=item.object_name,
            description=item.object_description,
            tags=item.tags,
        )
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_topics
                    (object_id, title, question, description, status, tags,
                     components, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    research_object.id,
                    item.title,
                    item.question,
                    item.description,
                    item.status,
                    json.dumps(item.tags, ensure_ascii=False),
                    json.dumps(
                        [component.model_dump(mode="json") for component in item.components],
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                ),
            )
            topic_id = int(cursor.lastrowid or 0)
            self._replace_topic_projects(
                connection,
                topic_id,
                research_object.id,
                item.project_ids,
                now,
            )
        saved = self.get_research_topic(topic_id)
        if saved is None:
            raise RuntimeError("专题研究保存失败")
        return saved

    def update_research_topic(
        self, topic_id: int, update: ResearchTopicUpdate
    ) -> ResearchTopicItem | None:
        current = self.get_research_topic(topic_id)
        if current is None:
            return None
        values = update.model_dump(exclude_unset=True, mode="json")
        project_ids = values.pop("project_ids", None)
        if project_ids is not None:
            self._validate_project_ids(project_ids)
        allowed = {
            "title",
            "question",
            "description",
            "status",
            "tags",
            "components",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for field, value in values.items():
            if field not in allowed:
                continue
            assignments.append(f"{field} = ?")
            if field in {"tags", "components"}:
                value = json.dumps(value or [], ensure_ascii=False)
            parameters.append(value)
        now = datetime.now().isoformat()
        with self._connect() as connection:
            if assignments:
                assignments.append("updated_at = ?")
                parameters.extend([now, topic_id])
                connection.execute(
                    f"UPDATE research_topics SET {', '.join(assignments)} WHERE id = ?",
                    parameters,
                )
            if project_ids is not None:
                self._replace_topic_projects(
                    connection,
                    topic_id,
                    current.research_object.id,
                    project_ids,
                    now,
                )
                connection.execute(
                    "UPDATE research_topics SET updated_at = ? WHERE id = ?",
                    (now, topic_id),
                )
        return self.get_research_topic(topic_id)

    def delete_research_topic(self, topic_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT object_id FROM research_topics WHERE id = ?", (topic_id,)
            ).fetchone()
            if row is None:
                return False
            object_id = int(row["object_id"])
            cursor = connection.execute(
                "DELETE FROM research_topics WHERE id = ?", (topic_id,)
            )
            if cursor.rowcount > 0:
                self._delete_research_object_if_unreferenced(connection, object_id)
        return cursor.rowcount > 0

    def topic_timeline(
        self, topic_id: int, limit: int | None = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        topic = self.get_research_topic(topic_id)
        if topic is None:
            raise KeyError(topic_id)
        project_ids = [project.id for project in topic.projects]
        if not project_ids:
            return []
        placeholders = ",".join("?" for _ in project_ids)
        with self._connect() as connection:
            evidence_rows = connection.execute(
                f"""
                SELECT evidence.id, evidence.project_id, project.title AS project_title,
                       evidence.title, evidence.evidence_type, evidence.payload,
                       evidence.source_summary, evidence.observation_start,
                       evidence.observation_end, evidence.created_at
                FROM research_evidence AS evidence
                JOIN research_projects AS project ON project.id = evidence.project_id
                JOIN research_evidence_objects AS object_link
                  ON object_link.evidence_id = evidence.id
                WHERE evidence.project_id IN ({placeholders})
                  AND object_link.object_id = ?
                """,
                [*project_ids, topic.research_object.id],
            ).fetchall()
            entry_rows = connection.execute(
                f"""
                SELECT entry.id, entry.project_id, project.title AS project_title,
                       entry.entry_type, entry.title, entry.content, entry.status,
                       entry.due_date, entry.updated_at AS created_at
                FROM research_entries AS entry
                JOIN research_projects AS project ON project.id = entry.project_id
                WHERE entry.project_id IN ({placeholders})
                """,
                project_ids,
            ).fetchall()
            activity_rows = connection.execute(
                f"""
                SELECT activity.id, activity.project_id,
                       project.title AS project_title, activity.event_type,
                       activity.summary, activity.details, activity.created_at
                FROM research_project_activity AS activity
                JOIN research_projects AS project ON project.id = activity.project_id
                WHERE activity.project_id IN ({placeholders})
                  AND activity.event_type IN ('created', 'updated', 'imported')
                """,
                project_ids,
            ).fetchall()
            release_rows = connection.execute(
                f"""
                SELECT review.id, review.project_id,
                       project.title AS project_title, review.title,
                       review.series_id, review.release_date,
                       review.observation_period, review.updated_at AS created_at
                FROM release_reviews AS review
                JOIN research_projects AS project ON project.id = review.project_id
                WHERE review.project_id IN ({placeholders})
                """,
                project_ids,
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in evidence_rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            snapshot_type = str(payload.get("snapshot_type") or "")
            provider = str(payload.get("provider") or "")
            event_type = (
                "market_snapshot"
                if snapshot_type == "market_brief"
                else "sovereign_update"
                if snapshot_type == "world_bank_sovereign_comparison"
                else "fred_reference"
                if provider.upper() == "FRED" or "FRED" in row["source_summary"].upper()
                else "gdelt_clue"
                if provider.upper() == "GDELT"
                or "GDELT" in row["source_summary"].upper()
                else "evidence"
            )
            events.append(
                {
                    "id": f"evidence-{row['id']}",
                    "event_type": event_type,
                    "title": row["title"],
                    "summary": row["source_summary"],
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "event_time": row["created_at"],
                    "observation_time": row["observation_end"]
                    or row["observation_start"],
                    "metadata": {
                        "evidence_type": row["evidence_type"],
                        "snapshot_type": snapshot_type or None,
                    },
                }
            )
        for row in entry_rows:
            events.append(
                {
                    "id": f"entry-{row['id']}",
                    "event_type": row["entry_type"],
                    "title": row["title"],
                    "summary": row["content"],
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "event_time": row["created_at"],
                    "observation_time": row["due_date"],
                    "metadata": {"status": row["status"]},
                }
            )
        for row in activity_rows:
            try:
                details = json.loads(row["details"] or "{}")
            except (TypeError, json.JSONDecodeError):
                details = {}
            events.append(
                {
                    "id": f"activity-{row['id']}",
                    "event_type": f"project_{row['event_type']}",
                    "title": row["summary"],
                    "summary": "",
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "event_time": row["created_at"],
                    "observation_time": None,
                    "metadata": details if isinstance(details, dict) else {},
                }
            )
        for row in release_rows:
            events.append(
                {
                    "id": f"release-{row['id']}",
                    "event_type": "release_review",
                    "title": row["title"],
                    "summary": f"{row['series_id']} · 目标观测期 {row['observation_period']}",
                    "project_id": row["project_id"],
                    "project_title": row["project_title"],
                    "event_time": row["created_at"],
                    "observation_time": row["release_date"],
                    "metadata": {"series_id": row["series_id"]},
                }
            )
        ordered = sorted(
            events, key=lambda item: (item["event_time"], item["id"]), reverse=True
        )
        start = max(0, offset)
        if limit is None:
            return ordered[start:]
        safe_limit = max(1, min(limit, 10_000))
        return ordered[start : start + safe_limit]

    def topic_timeline_page(
        self,
        topic_id: int,
        limit: int = 100,
        offset: int = 0,
        before_time: str | None = None,
        before_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a stable timeline page without hiding the total history size."""
        ordered = self.topic_timeline(topic_id, limit=None)
        safe_limit = max(1, min(limit, 200))
        safe_offset = max(0, offset)
        if before_time and before_id:
            eligible = [
                item
                for item in ordered
                if (item["event_time"], item["id"]) < (before_time, before_id)
            ]
            safe_offset = 0
        else:
            eligible = ordered
        items = eligible[safe_offset : safe_offset + safe_limit]
        total = len(ordered)
        has_more = safe_offset + len(items) < len(eligible)
        next_cursor = None
        if items and has_more:
            next_cursor = {
                "event_time": items[-1]["event_time"],
                "id": items[-1]["id"],
            }
        return {
            "items": items,
            "total": total,
            "offset": safe_offset,
            "limit": safe_limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def topic_workspace(
        self, topic_id: int, timeline_limit: int = 100
    ) -> dict[str, Any] | None:
        """Return one coherent local workspace snapshot for the topic page."""
        topic = self.get_research_topic(topic_id)
        if topic is None:
            return None
        summaries = [
            summary
            for project in topic.projects
            if (summary := self.project_summary(project.id)) is not None
        ]
        timeline_page = self.topic_timeline_page(topic_id, timeline_limit)
        return {
            "topic": topic,
            "timeline": timeline_page["items"],
            "timeline_total": timeline_page["total"],
            "timeline_has_more": timeline_page["has_more"],
            "timeline_next_cursor": timeline_page["next_cursor"],
            "project_summaries": summaries,
            "generated_at": datetime.now().isoformat(),
        }

    def project_summary(self, project_id: int) -> dict[str, Any] | None:
        project = self.get_research_project(project_id)
        if project is None:
            return None
        supporting = [
            {
                "id": item.id,
                "title": item.title,
                "source": item.source_summary,
                "observation_end": item.observation_end,
                "created_at": item.created_at.isoformat(),
            }
            for item in project.evidence[:5]
        ]
        counter_evidence = [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "status": item.status,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in project.entries
            if item.entry_type == "counter_evidence"
        ][:5]
        open_tasks = [
            {
                "id": item.id,
                "title": item.title,
                "due_date": item.due_date,
                "content": item.content,
            }
            for item in project.entries
            if item.entry_type == "task" and item.status == "open"
        ][:10]
        conclusion_changes = [
            {
                "summary": item.summary,
                "created_at": item.created_at.isoformat(),
                "details": item.details,
            }
            for item in project.activity
            if item.event_type == "updated"
            and "conclusion" in item.details.get("fields", [])
        ][:5]
        gaps: list[str] = []
        if not project.question.strip():
            gaps.append("尚未填写研究问题")
        if not project.hypothesis.strip():
            gaps.append("尚未填写初始假设")
        if not project.evidence:
            gaps.append("尚无研究证据")
        if not counter_evidence:
            gaps.append("尚未记录反证")
        if not project.next_review_date:
            gaps.append("尚未设置下次复盘")
        return {
            "project_id": project.id,
            "title": project.title,
            "status": project.status,
            "confidence": project.confidence,
            "question": project.question,
            "hypothesis": project.hypothesis,
            "conclusion": project.conclusion,
            "supporting_evidence": supporting,
            "counter_evidence": counter_evidence,
            "open_tasks": open_tasks,
            "recent_conclusion_changes": conclusion_changes,
            "next_review_date": project.next_review_date,
            "gaps": gaps,
            "generated_at": datetime.now().isoformat(),
            "notice": "该摘要由固定规则整理本地项目字段，不生成投资建议。",
        }

    def list_evidence_basket(
        self,
        *,
        topic_id: int | None = None,
        include_unassigned: bool = True,
        source: str | None = None,
        origin_page: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[EvidenceBasketItem]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if topic_id is not None:
            clauses.append(
                "(topic_id = ? OR topic_id IS NULL)"
                if include_unassigned
                else "topic_id = ?"
            )
            parameters.append(topic_id)
        elif not include_unassigned:
            clauses.append("topic_id IS NOT NULL")
        if source:
            clauses.append("LOWER(source_summary) LIKE ?")
            parameters.append(f"%{source.strip().lower()}%")
        if origin_page:
            clauses.append("origin_page = ?")
            parameters.append(origin_page.strip())
        if date_from:
            clauses.append("DATE(created_at) >= DATE(?)")
            parameters.append(date_from)
        if date_to:
            clauses.append("DATE(created_at) <= DATE(?)")
            parameters.append(date_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_evidence_basket
                {where}
                ORDER BY created_at DESC, id DESC
                """,
                parameters,
            ).fetchall()
        return [self._evidence_basket_from_row(row) for row in rows]

    def add_evidence_basket(self, item: EvidenceBasketCreate) -> EvidenceBasketItem:
        object_id: int | None = None
        if item.topic_id is not None:
            topic = self.get_research_topic(item.topic_id)
            if topic is None:
                raise ValueError("关联专题不存在")
            object_id = topic.research_object.id
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_evidence_basket
                    (topic_id, object_id, evidence_type, title, payload,
                     source_summary, observation_start, observation_end,
                     origin_page, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.topic_id,
                    object_id,
                    item.evidence_type,
                    item.title,
                    json.dumps(item.payload, ensure_ascii=False, default=str),
                    item.source_summary,
                    item.observation_start,
                    item.observation_end,
                    item.origin_page,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM research_evidence_basket WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:
            raise RuntimeError("证据篮保存失败")
        return self._evidence_basket_from_row(row)

    def delete_evidence_basket(self, item_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT object_id FROM research_evidence_basket WHERE id = ?",
                (item_id,),
            ).fetchone()
            cursor = connection.execute(
                "DELETE FROM research_evidence_basket WHERE id = ?", (item_id,)
            )
            if cursor.rowcount > 0 and row is not None and row["object_id"] is not None:
                self._delete_research_object_if_unreferenced(
                    connection, int(row["object_id"])
                )
        return cursor.rowcount > 0

    def delete_evidence_basket_items(self, item_ids: list[int]) -> int:
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        with self._connect() as connection:
            object_ids = {
                int(row["object_id"])
                for row in connection.execute(
                    f"""
                    SELECT DISTINCT object_id FROM research_evidence_basket
                    WHERE id IN ({placeholders}) AND object_id IS NOT NULL
                    """,
                    unique_ids,
                ).fetchall()
            }
            cursor = connection.execute(
                f"DELETE FROM research_evidence_basket WHERE id IN ({placeholders})",
                unique_ids,
            )
            for object_id in object_ids:
                self._delete_research_object_if_unreferenced(connection, object_id)
        return cursor.rowcount

    def commit_evidence_basket(
        self, request: EvidenceBasketCommit
    ) -> list[ResearchEvidenceItem]:
        project = self.get_research_project(request.project_id)
        if project is None:
            raise ValueError("目标研究项目不存在")
        placeholders = ",".join("?" for _ in request.item_ids)
        now = datetime.now().isoformat()
        saved_ids: list[int] = []
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_evidence_basket
                WHERE id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                request.item_ids,
            ).fetchall()
            if len(rows) != len(request.item_ids):
                raise ValueError("证据篮中有项目已不存在")
            topic_object_id: int | None = None
            if request.topic_id is not None:
                topic_row = connection.execute(
                    "SELECT object_id FROM research_topics WHERE id = ?",
                    (request.topic_id,),
                ).fetchone()
                if topic_row is None:
                    raise ValueError("关联专题不存在")
                topic_object_id = int(topic_row["object_id"])
                self._replace_topic_projects(
                    connection,
                    request.topic_id,
                    topic_object_id,
                    list(
                        dict.fromkeys(
                            [
                                *[
                                    int(row["project_id"])
                                    for row in connection.execute(
                                        """
                                        SELECT project_id FROM research_topic_projects
                                        WHERE topic_id = ?
                                        """,
                                        (request.topic_id,),
                                    ).fetchall()
                                ],
                                request.project_id,
                            ]
                        )
                    ),
                    now,
                )
            for row in rows:
                cursor = connection.execute(
                    """
                    INSERT INTO research_evidence
                        (project_id, evidence_type, title, payload, source_summary,
                         observation_start, observation_end, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.project_id,
                        row["evidence_type"],
                        row["title"],
                        row["payload"],
                        row["source_summary"],
                        row["observation_start"],
                        row["observation_end"],
                        now,
                    ),
                )
                evidence_id = int(cursor.lastrowid or 0)
                saved_ids.append(evidence_id)
                object_ids = {
                    int(object_id)
                    for object_id in (row["object_id"], topic_object_id)
                    if object_id is not None
                }
                if object_ids:
                    connection.executemany(
                        """
                        INSERT OR IGNORE INTO research_evidence_objects
                            (evidence_id, object_id, created_at)
                        VALUES (?, ?, ?)
                        """,
                        [
                            (evidence_id, object_id, now)
                            for object_id in sorted(object_ids)
                        ],
                    )
                    connection.executemany(
                        """
                        INSERT OR IGNORE INTO research_project_objects
                            (project_id, object_id, created_at)
                        VALUES (?, ?, ?)
                        """,
                        [
                            (request.project_id, object_id, now)
                            for object_id in sorted(object_ids)
                        ],
                    )
                self._insert_research_activity(
                    connection,
                    request.project_id,
                    "evidence_added",
                    f"从证据篮加入证据：{row['title']}",
                    {
                        "evidence_type": row["evidence_type"],
                        "source_summary": row["source_summary"],
                        "basket_item_id": row["id"],
                    },
                    now,
                )
            connection.execute(
                f"DELETE FROM research_evidence_basket WHERE id IN ({placeholders})",
                request.item_ids,
            )
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (now, request.project_id),
            )
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_evidence
                WHERE id IN ({','.join('?' for _ in saved_ids)})
                ORDER BY id
                """,
                saved_ids,
            ).fetchall()
        return [self._research_evidence_from_row(row) for row in rows]

    def _validate_project_ids(self, project_ids: list[int]) -> None:
        if not project_ids:
            return
        placeholders = ",".join("?" for _ in project_ids)
        with self._connect() as connection:
            count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM research_projects WHERE id IN ({placeholders})",
                    project_ids,
                ).fetchone()[0]
            )
        if count != len(project_ids):
            raise ValueError("专题关联的研究项目不存在")

    @staticmethod
    def _delete_research_object_if_unreferenced(
        connection: sqlite3.Connection, object_id: int
    ) -> None:
        references = connection.execute(
            """
            SELECT
                EXISTS(SELECT 1 FROM research_topics WHERE object_id = ?) OR
                EXISTS(SELECT 1 FROM research_project_objects WHERE object_id = ?) OR
                EXISTS(SELECT 1 FROM research_evidence_objects WHERE object_id = ?) OR
                EXISTS(SELECT 1 FROM research_evidence_basket WHERE object_id = ?)
            """,
            (object_id, object_id, object_id, object_id),
        ).fetchone()
        if references is not None and not bool(references[0]):
            connection.execute(
                "DELETE FROM research_objects WHERE id = ?", (object_id,)
            )

    @staticmethod
    def _replace_topic_projects(
        connection: sqlite3.Connection,
        topic_id: int,
        object_id: int,
        project_ids: list[int],
        created_at: str,
    ) -> None:
        connection.execute(
            "DELETE FROM research_topic_projects WHERE topic_id = ?", (topic_id,)
        )
        if not project_ids:
            return
        connection.executemany(
            """
            INSERT INTO research_topic_projects(topic_id, project_id, created_at)
            VALUES (?, ?, ?)
            """,
            [(topic_id, project_id, created_at) for project_id in project_ids],
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO research_project_objects
                (project_id, object_id, created_at)
            VALUES (?, ?, ?)
            """,
            [(project_id, object_id, created_at) for project_id in project_ids],
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO research_evidence_objects
                (evidence_id, object_id, created_at)
            SELECT id, ?, ?
            FROM research_evidence
            WHERE project_id = ?
            """,
            [
                (object_id, created_at, project_id)
                for project_id in project_ids
            ],
        )

    def add_research_entry(
        self, project_id: int, item: ResearchEntryCreate
    ) -> ResearchEntryItem | None:
        if self.get_research_project(project_id) is None:
            return None
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_entries
                    (project_id, entry_type, title, content, status, due_date,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    item.entry_type,
                    item.title,
                    item.content,
                    item.status,
                    item.due_date,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM research_entries WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            self._insert_research_activity(
                connection,
                project_id,
                "entry_added",
                f"新增{self._entry_type_label(item.entry_type)}：{item.title}",
                {"entry_type": item.entry_type, "status": item.status},
                now,
            )
        return self._research_entry_from_row(row) if row else None

    def update_research_entry(
        self, entry_id: int, update: ResearchEntryUpdate
    ) -> ResearchEntryItem | None:
        values = update.model_dump(exclude_unset=True)
        allowed = {"title", "content", "status", "due_date"}
        assignments: list[str] = []
        parameters: list[Any] = []
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM research_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if current is None:
                return None
            changed: list[str] = []
            details: dict[str, Any] = {
                "entry_type": current["entry_type"],
                "fields": changed,
            }
            for field, value in values.items():
                if field not in allowed or current[field] == value:
                    continue
                assignments.append(f"{field} = ?")
                parameters.append(value)
                changed.append(field)
                if field == "status":
                    details["status"] = {
                        "before": current["status"],
                        "after": value,
                    }
            if assignments:
                now = datetime.now().isoformat()
                assignments.append("updated_at = ?")
                parameters.extend([now, entry_id])
                connection.execute(
                    f"UPDATE research_entries SET {', '.join(assignments)} WHERE id = ?",
                    parameters,
                )
                connection.execute(
                    "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                    (now, current["project_id"]),
                )
                self._insert_research_activity(
                    connection,
                    int(current["project_id"]),
                    "entry_updated",
                    f"更新{self._entry_type_label(current['entry_type'])}：{current['title']}",
                    details,
                    now,
                )
            row = connection.execute(
                "SELECT * FROM research_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._research_entry_from_row(row) if row else None

    def delete_research_entry(self, entry_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            cursor = connection.execute(
                "DELETE FROM research_entries WHERE id = ?", (entry_id,)
            )
            if row:
                now = datetime.now().isoformat()
                connection.execute(
                    "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                    (now, row["project_id"]),
                )
                self._insert_research_activity(
                    connection,
                    int(row["project_id"]),
                    "entry_removed",
                    f"移除{self._entry_type_label(row['entry_type'])}：{row['title']}",
                    {"entry_type": row["entry_type"]},
                    now,
                )
        return cursor.rowcount > 0

    def list_research_action_drafts(
        self, project_id: int
    ) -> list[ResearchActionDraftItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_action_drafts
                WHERE project_id = ?
                ORDER BY CASE status
                    WHEN 'proposed' THEN 0
                    WHEN 'accepted' THEN 1
                    WHEN 'undone' THEN 2
                    ELSE 3 END,
                    created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [self._research_action_draft_from_row(row) for row in rows]

    def replace_research_action_drafts(
        self,
        project_id: int,
        drafts: list[dict[str, str]],
    ) -> list[ResearchActionDraftItem]:
        if self.get_research_project(project_id) is None:
            raise KeyError(project_id)
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM research_action_drafts
                WHERE project_id = ? AND status = 'proposed'
                """,
                (project_id,),
            )
            connection.executemany(
                """
                INSERT INTO research_action_drafts
                    (project_id, action_type, title, content, status, source,
                     source_reference, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?, ?)
                """,
                [
                    (
                        project_id,
                        item["action_type"],
                        item["title"],
                        item.get("content", ""),
                        item["source"],
                        item.get("source_reference", ""),
                        now,
                        now,
                    )
                    for item in drafts
                ],
            )
        return self.list_research_action_drafts(project_id)

    def accept_research_action_drafts(
        self, project_id: int, draft_ids: list[int]
    ) -> list[ResearchActionDraftItem]:
        if not draft_ids:
            return self.list_research_action_drafts(project_id)
        placeholders = ",".join("?" for _ in draft_ids)
        now = datetime.now().isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_action_drafts
                WHERE project_id = ? AND id IN ({placeholders})
                """,
                [project_id, *draft_ids],
            ).fetchall()
            if len(rows) != len(set(draft_ids)):
                raise KeyError("研究行动草稿不存在")
            for row in rows:
                if row["status"] != "proposed":
                    raise ValueError("仅可采纳待确认的研究行动")
                cursor = connection.execute(
                    """
                    INSERT INTO research_entries
                        (project_id, entry_type, title, content, status, due_date,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'open', NULL, ?, ?)
                    """,
                    (
                        project_id,
                        row["action_type"],
                        row["title"],
                        row["content"],
                        now,
                        now,
                    ),
                )
                entry_id = int(cursor.lastrowid or 0)
                connection.execute(
                    """
                    UPDATE research_action_drafts
                    SET status = 'accepted', created_entry_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (entry_id, now, row["id"]),
                )
                self._insert_research_activity(
                    connection,
                    project_id,
                    "entry_added",
                    f"采纳行动建议：{row['title']}",
                    {
                        "entry_type": row["action_type"],
                        "status": "open",
                        "action_draft_id": row["id"],
                        "source": row["source"],
                    },
                    now,
                )
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        return self.list_research_action_drafts(project_id)

    def undo_research_action_draft(
        self, project_id: int, draft_id: int
    ) -> ResearchActionDraftItem | None:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_action_drafts
                WHERE id = ? AND project_id = ?
                """,
                (draft_id, project_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "accepted" or row["created_entry_id"] is None:
                raise ValueError("该行动尚未采纳或已经撤销")
            connection.execute(
                "DELETE FROM research_entries WHERE id = ? AND project_id = ?",
                (row["created_entry_id"], project_id),
            )
            connection.execute(
                """
                UPDATE research_action_drafts
                SET status = 'undone', created_entry_id = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, draft_id),
            )
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            self._insert_research_activity(
                connection,
                project_id,
                "entry_removed",
                f"撤销行动建议：{row['title']}",
                {
                    "entry_type": row["action_type"],
                    "action_draft_id": draft_id,
                },
                now,
            )
            saved = connection.execute(
                "SELECT * FROM research_action_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return self._research_action_draft_from_row(saved) if saved else None

    @staticmethod
    def _entry_type_label(entry_type: str) -> str:
        return {
            "note": "研究笔记",
            "counter_evidence": "反证",
            "task": "任务",
            "review": "复盘",
        }.get(entry_type, "研究记录")

    def add_research_evidence(
        self, project_id: int, item: ResearchEvidenceCreate
    ) -> ResearchEvidenceItem | None:
        if self.get_research_project(project_id) is None:
            return None
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_evidence
                    (project_id, evidence_type, title, payload, source_summary,
                     observation_start, observation_end, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    item.evidence_type,
                    item.title,
                    json.dumps(item.payload, ensure_ascii=False, default=str),
                    item.source_summary,
                    item.observation_start,
                    item.observation_end,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM research_evidence WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.execute(
                """
                INSERT OR IGNORE INTO research_evidence_objects
                    (evidence_id, object_id, created_at)
                SELECT ?, object_id, ?
                FROM research_project_objects
                WHERE project_id = ?
                """,
                (cursor.lastrowid, now, project_id),
            )
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            self._insert_research_activity(
                connection,
                project_id,
                "evidence_added",
                f"新增证据：{item.title}",
                {
                    "evidence_type": item.evidence_type,
                    "source_summary": item.source_summary,
                },
                now,
            )
        return self._research_evidence_from_row(row) if row else None

    def delete_research_evidence(self, evidence_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, title, evidence_type FROM research_evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()
            cursor = connection.execute(
                "DELETE FROM research_evidence WHERE id = ?", (evidence_id,)
            )
            if row:
                now = datetime.now().isoformat()
                connection.execute(
                    "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                    (now, row["project_id"]),
                )
                self._insert_research_activity(
                    connection,
                    int(row["project_id"]),
                    "evidence_removed",
                    f"移除证据：{row['title']}",
                    {"evidence_type": row["evidence_type"]},
                    now,
                )
        return cursor.rowcount > 0

    def get_setting(self, key: str, default: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM app_settings WHERE setting_key = ?", (key,)
            ).fetchone()
        if row is None:
            return dict(default)
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return dict(default)
        return payload if isinstance(payload, dict) else dict(default)

    def set_setting(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings(setting_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(payload, ensure_ascii=False), now),
            )
        return payload

    def get_ai_usage(self, usage_date: str) -> dict[str, int | str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT usage_date, calls, prompt_tokens, completion_tokens, total_tokens
                FROM ai_usage_daily
                WHERE usage_date = ?
                """,
                (usage_date,),
            ).fetchone()
        if row is None:
            return {
                "usage_date": usage_date,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        return {
            "usage_date": str(row["usage_date"]),
            "calls": int(row["calls"]),
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "total_tokens": int(row["total_tokens"]),
        }

    def record_ai_usage(
        self,
        *,
        usage_date: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        context_type: str = "assistant",
        context_key: str = "",
    ) -> dict[str, int | str]:
        prompt = max(0, int(prompt_tokens or 0))
        completion = max(0, int(completion_tokens or 0))
        total = max(0, int(total_tokens or prompt + completion))
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_usage_daily(
                    usage_date, calls, prompt_tokens, completion_tokens,
                    total_tokens, updated_at
                )
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(usage_date) DO UPDATE SET
                    calls = calls + 1,
                    prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                    completion_tokens = completion_tokens + excluded.completion_tokens,
                    total_tokens = total_tokens + excluded.total_tokens,
                    updated_at = excluded.updated_at
                """,
                (usage_date, prompt, completion, total, now),
            )
            connection.execute(
                """
                INSERT INTO ai_usage_events(
                    usage_date, context_type, context_key, prompt_tokens,
                    completion_tokens, total_tokens, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_date,
                    str(context_type or "assistant")[:80],
                    str(context_key or "")[:160],
                    prompt,
                    completion,
                    total,
                    now,
                ),
            )
        return self.get_ai_usage(usage_date)

    def get_ai_usage_by_context(self, usage_date: str) -> dict[str, dict[str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT context_type, COUNT(*) AS calls,
                       SUM(prompt_tokens) AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens,
                       SUM(total_tokens) AS total_tokens
                FROM ai_usage_events
                WHERE usage_date = ?
                GROUP BY context_type
                ORDER BY context_type
                """,
                (usage_date,),
            ).fetchall()
        return {
            str(row["context_type"]): {
                "calls": int(row["calls"] or 0),
                "prompt_tokens": int(row["prompt_tokens"] or 0),
                "completion_tokens": int(row["completion_tokens"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
            }
            for row in rows
        }

    @staticmethod
    def _ai_insight_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        try:
            context_summary = json.loads(row["context_summary"])
        except (TypeError, json.JSONDecodeError):
            context_summary = []
        return {
            "id": int(row["id"]),
            "context_type": str(row["context_type"]),
            "context_key": str(row["context_key"]),
            "context_fingerprint": str(row["context_fingerprint"]),
            "status": str(row["status"]),
            "summary": str(row["summary"] or ""),
            "context_summary": (
                context_summary if isinstance(context_summary, list) else []
            ),
            "provider": str(row["provider"] or ""),
            "model": str(row["model"] or ""),
            "generated_at": row["generated_at"],
            "last_error": row["last_error"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def get_ai_insight(
        self, context_type: str, context_key: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM ai_insights
                WHERE context_type = ? AND context_key = ?
                """,
                (context_type, context_key),
            ).fetchone()
        return self._ai_insight_row(row)

    def delete_ai_insight(self, context_type: str, context_key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM ai_insights
                WHERE context_type = ? AND context_key = ?
                """,
                (context_type, context_key),
            )
        return cursor.rowcount > 0

    def save_ai_insight(
        self,
        *,
        context_type: str,
        context_key: str,
        context_fingerprint: str,
        status: str,
        summary: str = "",
        context_summary: list[str] | None = None,
        provider: str = "",
        model: str = "",
        generated_at: str | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_insights(
                    context_type, context_key, context_fingerprint, status,
                    summary, context_summary, provider, model, generated_at,
                    last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(context_type, context_key) DO UPDATE SET
                    context_fingerprint = excluded.context_fingerprint,
                    status = excluded.status,
                    summary = excluded.summary,
                    context_summary = excluded.context_summary,
                    provider = excluded.provider,
                    model = excluded.model,
                    generated_at = excluded.generated_at,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    context_type,
                    context_key,
                    context_fingerprint,
                    status,
                    summary,
                    json.dumps(context_summary or [], ensure_ascii=False),
                    provider,
                    model,
                    generated_at,
                    last_error,
                    now,
                    now,
                ),
            )
        insight = self.get_ai_insight(context_type, context_key)
        assert insight is not None
        return insight

    def fail_interrupted_ai_insights(self) -> int:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_insights
                SET status = 'failed',
                    last_error = '上次生成因本地服务停止而中断，请重新生成',
                    updated_at = ?
                WHERE status = 'generating'
                """,
                (now,),
            )
        return cursor.rowcount

    def project_bundle(self, project_id: int) -> dict[str, Any] | None:
        project = self.get_research_project(project_id)
        if project is None:
            return None
        project_fields = project.model_dump(
            mode="json",
            exclude={"id", "created_at", "updated_at", "evidence", "activity", "entries"},
        )
        evidence = [
            item.model_dump(mode="json", exclude={"id", "project_id", "created_at"})
            for item in project.evidence
        ]
        entries = [
            item.model_dump(
                mode="json",
                exclude={"id", "project_id", "created_at", "updated_at"},
            )
            for item in project.entries
        ]
        with self._connect() as connection:
            object_rows = connection.execute(
                """
                SELECT object.object_type, object.object_key, object.name,
                       object.description, object.tags
                FROM research_project_objects AS link
                JOIN research_objects AS object ON object.id = link.object_id
                WHERE link.project_id = ?
                ORDER BY object.name
                """,
                (project_id,),
            ).fetchall()
        research_objects: list[dict[str, Any]] = []
        for row in object_rows:
            try:
                tags = json.loads(row["tags"] or "[]")
            except (TypeError, json.JSONDecodeError):
                tags = []
            research_objects.append(
                {
                    "object_type": row["object_type"],
                    "object_key": row["object_key"],
                    "name": row["name"],
                    "description": row["description"],
                    "tags": tags if isinstance(tags, list) else [],
                }
            )
        return {
            "schema": "akdesk-research-project",
            "schema_version": 1,
            "exported_at": datetime.now().isoformat(),
            "project": project_fields,
            "evidence": evidence,
            "entries": entries,
            "research_objects": research_objects,
            "notice": "FRED evidence contains references only; observations are not included.",
        }

    def import_project_bundle(self, bundle: dict[str, Any]) -> ResearchProjectItem:
        if bundle.get("schema") != "akdesk-research-project" or bundle.get(
            "schema_version"
        ) != 1:
            raise ValueError("不支持的研究项目导入格式")
        raw_project = bundle.get("project")
        raw_evidence = bundle.get("evidence", [])
        raw_entries = bundle.get("entries", [])
        raw_objects = bundle.get("research_objects", [])
        if not isinstance(raw_project, dict):
            raise ValueError("研究项目导入文件缺少 project")
        if (
            not isinstance(raw_evidence, list)
            or not isinstance(raw_entries, list)
            or not isinstance(raw_objects, list)
        ):
            raise ValueError("研究项目导入文件结构错误")
        project_data = dict(raw_project)
        title = str(project_data.get("title") or "").strip()
        project_data["title"] = f"{title}（导入）" if title else "导入研究项目"
        project_item = ResearchProjectCreate.model_validate(project_data)
        evidence_items = [
            ResearchEvidenceCreate.model_validate(item) for item in raw_evidence
        ]
        entry_items = [ResearchEntryCreate.model_validate(item) for item in raw_entries]
        object_items: list[dict[str, Any]] = []
        for item in raw_objects:
            if not isinstance(item, dict):
                raise ValueError("研究对象导入结构错误")
            object_key = str(item.get("object_key") or "").strip()
            object_name = str(item.get("name") or "").strip()
            object_type = str(item.get("object_type") or "macro_theme")
            if not object_key or not object_name:
                raise ValueError("研究对象导入缺少标识或名称")
            if object_type not in RESEARCH_OBJECT_TYPES:
                raise ValueError("不支持的研究对象类型")
            object_items.append(
                {
                    "object_type": object_type,
                    "object_key": object_key,
                    "name": object_name,
                    "description": str(item.get("description") or ""),
                    "tags": (
                        [str(tag) for tag in item.get("tags", [])]
                        if isinstance(item.get("tags"), list)
                        else []
                    ),
                }
            )

        saved = self.add_research_project(project_item)
        for item in object_items:
            research_object = self.upsert_research_object(
                object_type=item["object_type"],
                object_key=item["object_key"],
                name=item["name"],
                description=item["description"],
                tags=item["tags"],
            )
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO research_project_objects
                        (project_id, object_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (saved.id, research_object.id, datetime.now().isoformat()),
                )
        for item in evidence_items:
            self.add_research_evidence(saved.id, item)
        for item in entry_items:
            self.add_research_entry(saved.id, item)
        now = datetime.now().isoformat()
        with self._connect() as connection:
            self._insert_research_activity(
                connection,
                saved.id,
                "imported",
                "从 AKDesk 项目包导入",
                {
                    "evidence": len(evidence_items),
                    "entries": len(entry_items),
                    "research_objects": len(object_items),
                    "source_exported_at": bundle.get("exported_at"),
                },
                now,
            )
        imported = self.get_research_project(saved.id)
        if imported is None:
            raise RuntimeError("研究项目导入失败")
        return imported

    def backup_to(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()

    def restore_from(self, source_path: Path) -> None:
        self.validate_backup(source_path)
        source = sqlite3.connect(source_path)
        try:
            with self._connect() as target:
                source.backup(target)
        finally:
            source.close()
        self._init_schema()

    @staticmethod
    def validate_backup(path: Path) -> None:
        connection = sqlite3.connect(path)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise ValueError("备份文件完整性检查失败")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            required = {
                "research_projects",
                "research_evidence",
                "watchlist_items",
                "alert_rules",
            }
            if not required.issubset(tables):
                raise ValueError("备份文件不是有效的 AKDesk 研究数据库")
        finally:
            connection.close()

    def list_release_reviews(self) -> list[ReleaseReviewItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM release_reviews ORDER BY release_date DESC, id DESC"
            ).fetchall()
        return [self._release_review_from_row(row) for row in rows]

    def get_release_review(self, review_id: int) -> ReleaseReviewItem | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM release_reviews WHERE id = ?", (review_id,)
            ).fetchone()
        return self._release_review_from_row(row) if row else None

    def add_release_review(self, item: ReleaseReviewCreate) -> ReleaseReviewItem:
        if item.project_id is not None and self.get_research_project(item.project_id) is None:
            raise ValueError("关联研究项目不存在")
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO release_reviews
                    (title, series_id, release_name, release_date,
                     observation_period, expected_value, expected_unit,
                     project_id, pre_window_days, post_window_days, notes,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.title,
                    item.series_id,
                    item.release_name,
                    item.release_date,
                    item.observation_period,
                    item.expected_value,
                    item.expected_unit,
                    item.project_id,
                    item.pre_window_days,
                    item.post_window_days,
                    item.notes,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM release_reviews WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("发布复盘保存失败")
        return self._release_review_from_row(row)

    def update_release_review(
        self, review_id: int, update: ReleaseReviewUpdate
    ) -> ReleaseReviewItem | None:
        values = update.model_dump(exclude_unset=True, mode="json")
        if (
            "project_id" in values
            and values["project_id"] is not None
            and self.get_research_project(int(values["project_id"])) is None
        ):
            raise ValueError("关联研究项目不存在")
        if {"series_id", "observation_period"}.intersection(values):
            values.setdefault("reviewed_realtime_start", None)
            values.setdefault("reviewed_at", None)
        allowed = {
            "title",
            "series_id",
            "release_name",
            "release_date",
            "observation_period",
            "expected_value",
            "expected_unit",
            "project_id",
            "pre_window_days",
            "post_window_days",
            "notes",
            "reviewed_realtime_start",
            "reviewed_at",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for field, value in values.items():
            if field in allowed:
                assignments.append(f"{field} = ?")
                parameters.append(value)
        if not assignments:
            return self.get_release_review(review_id)
        assignments.append("updated_at = ?")
        parameters.extend([datetime.now().isoformat(), review_id])
        with self._connect() as connection:
            connection.execute(
                f"UPDATE release_reviews SET {', '.join(assignments)} WHERE id = ?",
                parameters,
            )
        return self.get_release_review(review_id)

    def delete_release_review(self, review_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM release_reviews WHERE id = ?", (review_id,)
            )
        return cursor.rowcount > 0

    def market_window(
        self, event_date: str, *, pre_days: int, post_days: int
    ) -> dict[str, Any]:
        anchor = date.fromisoformat(event_date)
        start = (anchor - timedelta(days=pre_days)).isoformat()
        end = (anchor + timedelta(days=post_days)).isoformat()
        selections = {
            ("money_rates", "Shibor O/N", "value"),
            ("yield_curves", "10Y", "yield"),
            ("yield_curves", "10Y-1Y", "spread_bp"),
            ("treasury_futures", "T", "price"),
        }
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT adapter, series_key, label, metric, observation_time,
                       value, source, quality_score
                FROM market_history
                WHERE observation_time BETWEEN ? AND ?
                ORDER BY observation_time ASC
                """,
                (start, end),
            ).fetchall()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row["adapter"], row["series_key"], row["metric"])
            if key in selections:
                grouped.setdefault(key, []).append(dict(row))
        series: list[dict[str, Any]] = []
        for (adapter, key, metric), points in sorted(grouped.items()):
            before = next(
                (item for item in reversed(points) if item["observation_time"] < event_date),
                None,
            )
            after = next(
                (item for item in points if item["observation_time"] >= event_date),
                None,
            )
            series.append(
                {
                    "adapter": adapter,
                    "series_key": key,
                    "metric": metric,
                    "label": (before or after or {}).get("label", key),
                    "before": before,
                    "after": after,
                    "change": (
                        round(float(after["value"]) - float(before["value"]), 6)
                        if before and after
                        else None
                    ),
                }
            )
        return {
            "event_date": event_date,
            "start": start,
            "end": end,
            "series": series,
            "notice": "中国市场窗口来自本地可信历史；缺失日期保持为空。",
        }

    def weekly_workspace_stats(self, start: str, end: str) -> dict[str, Any]:
        start_time = f"{start}T00:00:00"
        end_time = f"{end}T23:59:59.999999"
        with self._connect() as connection:
            projects = connection.execute(
                """
                SELECT id, title, status, confidence, conclusion,
                       next_review_date, updated_at
                FROM research_projects
                WHERE status != 'archived'
                ORDER BY updated_at DESC
                """
            ).fetchall()
            activity = connection.execute(
                """
                SELECT activity.*, project.title AS project_title
                FROM research_project_activity AS activity
                JOIN research_projects AS project ON project.id = activity.project_id
                WHERE activity.created_at BETWEEN ? AND ?
                ORDER BY activity.created_at DESC, activity.id DESC
                LIMIT 200
                """,
                (start_time, end_time),
            ).fetchall()
            entries = connection.execute(
                """
                SELECT entry.*, project.title AS project_title
                FROM research_entries AS entry
                JOIN research_projects AS project ON project.id = entry.project_id
                WHERE entry.updated_at BETWEEN ? AND ?
                   OR (entry.status = 'open' AND entry.due_date <= ?)
                ORDER BY entry.updated_at DESC, entry.id DESC
                """,
                (start_time, end_time, end),
            ).fetchall()
            open_tasks = connection.execute(
                """
                SELECT entry.*, project.title AS project_title
                FROM research_entries AS entry
                JOIN research_projects AS project ON project.id = entry.project_id
                WHERE entry.entry_type = 'task' AND entry.status = 'open'
                  AND project.status != 'archived'
                ORDER BY
                    CASE WHEN entry.due_date IS NULL THEN 1 ELSE 0 END,
                    entry.due_date,
                    entry.updated_at DESC
                LIMIT 100
                """
            ).fetchall()
            releases = connection.execute(
                """
                SELECT * FROM release_reviews
                WHERE release_date BETWEEN ? AND ?
                ORDER BY release_date, id
                """,
                (start, end),
            ).fetchall()
        return {
            "projects": [dict(row) for row in projects],
            "activity": [dict(row) for row in activity],
            "entries": [dict(row) for row in entries],
            "open_tasks": [dict(row) for row in open_tasks],
            "release_reviews": [dict(row) for row in releases],
        }

    def list_credit_observations(self) -> list[CreditObservationItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM credit_observations ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._credit_observation_from_row(row) for row in rows]

    def add_credit_observation(
        self, item: CreditObservationCreate
    ) -> CreditObservationItem:
        with self._connect() as connection:
            row = self._upsert_credit_observation(connection, item)
        if row is None:
            raise RuntimeError("信用观察保存失败")
        return self._credit_observation_from_row(row)

    def add_credit_observations(
        self, items: list[CreditObservationCreate]
    ) -> dict[str, Any]:
        ordered = sorted(
            enumerate(items),
            key=lambda pair: (pair[1].yield_observation_date or "", pair[0]),
        )
        observation_ids: set[int] = set()
        with self._connect() as connection:
            imported_codes = list(dict.fromkeys(item.bond_code for item in items))
            existing_rows: dict[str, sqlite3.Row] = {}
            if imported_codes:
                placeholders = ", ".join("?" for _ in imported_codes)
                existing_rows = {
                    str(row["bond_code"]): row
                    for row in connection.execute(
                        f"SELECT * FROM credit_observations WHERE bond_code IN ({placeholders})",
                        imported_codes,
                    )
                }
            for _, item in ordered:
                row = self._upsert_credit_observation(connection, item)
                observation_ids.add(int(row["id"]))
            latest_imported = {
                code: max(
                    (
                        item.yield_observation_date or ""
                        for item in items
                        if item.bond_code == code
                    ),
                    default="",
                )
                for code in imported_codes
            }
            for code, existing in existing_rows.items():
                if str(existing["yield_observation_date"] or "") > latest_imported[code]:
                    current = CreditObservationCreate(
                        **{
                            field: existing[field]
                            for field in CreditObservationCreate.model_fields
                        }
                    )
                    row = self._upsert_credit_observation(connection, current)
                    observation_ids.add(int(row["id"]))
        return {
            "imported_rows": len(items),
            "observations": len(observation_ids),
        }

    def _upsert_credit_observation(
        self, connection: sqlite3.Connection, item: CreditObservationCreate
    ) -> sqlite3.Row:
        now = datetime.now().isoformat()
        payload = item.model_dump()
        if not payload.get("canonical_issuer") and payload.get("issuer"):
            payload["canonical_issuer"] = (
                re.sub(r"\s+", "", str(payload["issuer"]))
                .replace("（", "(")
                .replace("）", ")")
            )
        columns = list(payload)
        updates = [
            f"{field}=excluded.{field}" for field in columns if field != "bond_code"
        ]
        connection.execute(
            f"""
            INSERT INTO credit_observations
                ({', '.join(columns)}, created_at, updated_at)
            VALUES ({', '.join('?' for _ in columns)}, ?, ?)
            ON CONFLICT(bond_code) DO UPDATE SET
                {', '.join(updates)},
                updated_at=excluded.updated_at
            """,
            (*payload.values(), now, now),
        )
        row = connection.execute(
            "SELECT * FROM credit_observations WHERE bond_code = ?",
            (item.bond_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError("信用观察保存失败")
        self._save_credit_history(connection, row, now)
        return row

    @staticmethod
    def _save_credit_history(
        connection: sqlite3.Connection, row: sqlite3.Row, recorded_at: str
    ) -> None:
        fields = [
            "observation_id",
            "bond_code",
            "bond_name",
            "issuer",
            "canonical_issuer",
            "maturity_date",
            "put_date",
            "rating",
            "rating_date",
            "yield_pct",
            "yield_observation_date",
            "benchmark_tenor",
            "benchmark_yield_pct",
            "benchmark_observation_date",
            "source_note",
        ]
        payload = {
            "observation_id": int(row["id"]),
            **{field: row[field] for field in fields if field != "observation_id"},
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        columns = [*fields, "fingerprint", "recorded_at"]
        connection.execute(
            f"""
            INSERT OR IGNORE INTO credit_observation_history ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            """,
            (*payload.values(), fingerprint, recorded_at),
        )

    def update_credit_observation(
        self, item_id: int, update: CreditObservationUpdate
    ) -> CreditObservationItem | None:
        values = update.model_dump(exclude_unset=True)
        if not values:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM credit_observations WHERE id = ?", (item_id,)
                ).fetchone()
            return self._credit_observation_from_row(row) if row else None
        assignments = [f"{field} = ?" for field in values]
        parameters = [*values.values(), datetime.now().isoformat(), item_id]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE credit_observations SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                parameters,
            )
            row = connection.execute(
                "SELECT * FROM credit_observations WHERE id = ?", (item_id,)
            ).fetchone()
            if row is not None:
                self._save_credit_history(
                    connection, row, datetime.now().isoformat()
                )
        return self._credit_observation_from_row(row) if row else None

    def list_credit_history(self, observation_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM credit_observation_history"
        parameters: tuple[object, ...] = ()
        if observation_id is not None:
            query += " WHERE observation_id = ?"
            parameters = (observation_id,)
        query += " ORDER BY yield_observation_date DESC, recorded_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def delete_credit_observation(self, item_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM credit_observations WHERE id = ?", (item_id,)
            )
        return cursor.rowcount > 0

    def list_credit_portfolios(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            portfolios = connection.execute(
                "SELECT * FROM credit_portfolios ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            members = connection.execute(
                "SELECT portfolio_id, observation_id FROM credit_portfolio_members ORDER BY created_at, observation_id"
            ).fetchall()
        member_map: dict[int, list[int]] = {}
        for member in members:
            member_map.setdefault(int(member["portfolio_id"]), []).append(
                int(member["observation_id"])
            )
        return [
            {**dict(row), "observation_ids": member_map.get(int(row["id"]), [])}
            for row in portfolios
        ]

    def add_credit_portfolio(self, item: CreditPortfolioCreate) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO credit_portfolios (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (item.name.strip(), item.description.strip(), now, now),
            )
            portfolio_id = int(cursor.lastrowid)
            self._replace_credit_portfolio_members(
                connection, portfolio_id, item.observation_ids, now
            )
        return next(
            item for item in self.list_credit_portfolios() if item["id"] == portfolio_id
        )

    def update_credit_portfolio(
        self, portfolio_id: int, update: CreditPortfolioUpdate
    ) -> dict[str, Any] | None:
        values = update.model_dump(exclude_unset=True)
        observation_ids = values.pop("observation_ids", None)
        now = datetime.now().isoformat()
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM credit_portfolios WHERE id = ?", (portfolio_id,)
            ).fetchone()
            if not exists:
                return None
            if values:
                assignments = [f"{field} = ?" for field in values]
                connection.execute(
                    f"UPDATE credit_portfolios SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                    (*values.values(), now, portfolio_id),
                )
            if observation_ids is not None:
                self._replace_credit_portfolio_members(
                    connection, portfolio_id, observation_ids, now
                )
        return next(
            item for item in self.list_credit_portfolios() if item["id"] == portfolio_id
        )

    @staticmethod
    def _replace_credit_portfolio_members(
        connection: sqlite3.Connection,
        portfolio_id: int,
        observation_ids: list[int],
        created_at: str,
    ) -> None:
        connection.execute(
            "DELETE FROM credit_portfolio_members WHERE portfolio_id = ?",
            (portfolio_id,),
        )
        for observation_id in observation_ids:
            connection.execute(
                "INSERT INTO credit_portfolio_members (portfolio_id, observation_id, created_at) VALUES (?, ?, ?)",
                (portfolio_id, observation_id, created_at),
            )

    def delete_credit_portfolio(self, portfolio_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM credit_portfolios WHERE id = ?", (portfolio_id,)
            )
        return cursor.rowcount > 0

    def list_credit_signal_confirmations(self) -> dict[str, dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM credit_signal_confirmations"
            ).fetchall()
        return {str(row["signal_id"]): dict(row) for row in rows}

    def confirm_credit_signal(self, signal_id: str, note: str) -> dict[str, str]:
        confirmed_at = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO credit_signal_confirmations (signal_id, note, confirmed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    note=excluded.note,
                    confirmed_at=excluded.confirmed_at
                """,
                (signal_id, note.strip(), confirmed_at),
            )
        return {
            "signal_id": signal_id,
            "note": note.strip(),
            "confirmed_at": confirmed_at,
        }

    def upsert_macro_series(self, metadata: dict[str, Any]) -> None:
        now = str(metadata.get("fetched_at") or datetime.now().isoformat())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO macro_series
                    (provider, series_id, title, title_zh, topic, units,
                     frequency, seasonal_adjustment, notes,
                     source_organization, source_url, last_updated, license,
                     attribution, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, series_id) DO UPDATE SET
                    title = excluded.title,
                    title_zh = excluded.title_zh,
                    topic = excluded.topic,
                    units = excluded.units,
                    frequency = excluded.frequency,
                    seasonal_adjustment = excluded.seasonal_adjustment,
                    notes = excluded.notes,
                    source_organization = excluded.source_organization,
                    source_url = excluded.source_url,
                    last_updated = excluded.last_updated,
                    license = excluded.license,
                    attribution = excluded.attribution,
                    fetched_at = excluded.fetched_at
                """,
                (
                    str(metadata.get("provider") or "fred"),
                    str(metadata.get("series_id") or ""),
                    str(metadata.get("title") or metadata.get("series_id") or ""),
                    str(metadata.get("title_zh") or ""),
                    str(metadata.get("topic") or ""),
                    str(metadata.get("units") or ""),
                    str(metadata.get("frequency") or ""),
                    str(metadata.get("seasonal_adjustment") or ""),
                    str(metadata.get("notes") or ""),
                    str(metadata.get("source_organization") or ""),
                    str(metadata.get("source_url") or ""),
                    metadata.get("last_updated"),
                    str(metadata.get("license") or ""),
                    str(metadata.get("attribution") or ""),
                    now,
                ),
            )

    def upsert_macro_observations(
        self,
        provider: str,
        series_id: str,
        observations: list[dict[str, Any]],
        *,
        fetched_at: str | None = None,
    ) -> int:
        fetched = fetched_at or datetime.now().isoformat()
        rows: list[tuple[str, str, str, float | None, str, str | None, str]] = []
        for item in observations:
            observed = str(item.get("date") or item.get("observation_period") or "")
            if not observed:
                continue
            value = self._history_number(item.get("value"))
            realtime_start = str(
                item.get("realtime_start") or fetched.split("T", 1)[0]
            )
            rows.append(
                (
                    provider,
                    series_id,
                    observed,
                    value,
                    realtime_start,
                    str(item.get("realtime_end") or "") or None,
                    fetched,
                )
            )
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO macro_observations
                    (provider, series_id, observation_period, value,
                     realtime_start, realtime_end, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, series_id, observation_period, realtime_start)
                DO UPDATE SET
                    value = excluded.value,
                    realtime_end = excluded.realtime_end,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
        return len(rows)

    def macro_series_metadata(
        self, provider: str, series_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM macro_series
                WHERE provider = ? AND series_id = ?
                """,
                (provider, series_id),
            ).fetchone()
        return dict(row) if row else None

    def macro_observations(
        self,
        provider: str,
        series_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["provider = ?", "series_id = ?"]
        parameters: list[Any] = [provider, series_id]
        if start:
            clauses.append("observation_period >= ?")
            parameters.append(start)
        if end:
            clauses.append("observation_period <= ?")
            parameters.append(end)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT observation_period AS date, value, realtime_start,
                       realtime_end, fetched_at
                FROM macro_observations AS current
                WHERE {' AND '.join(clauses)}
                  AND realtime_start = (
                    SELECT MAX(version.realtime_start)
                    FROM macro_observations AS version
                    WHERE version.provider = current.provider
                      AND version.series_id = current.series_id
                      AND version.observation_period = current.observation_period
                  )
                ORDER BY observation_period ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def macro_cache_age(self, provider: str, series_id: str) -> int | None:
        metadata = self.macro_series_metadata(provider, series_id)
        if not metadata or not metadata.get("fetched_at"):
            return None
        try:
            fetched = datetime.fromisoformat(str(metadata["fetched_at"]))
        except ValueError:
            return None
        return max(0, int((datetime.now() - fetched).total_seconds()))

    def macro_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT provider || ':' || series_id) AS series,
                       COUNT(*) AS points,
                       MIN(observation_period) AS oldest,
                       MAX(observation_period) AS newest
                FROM macro_observations
                """
            ).fetchone()
        return dict(row) if row else {
            "series": 0,
            "points": 0,
            "oldest": None,
            "newest": None,
        }

    def clear_macro_cache(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM macro_observations")
            connection.execute("DELETE FROM macro_series")

    def upsert_world_bank_countries(self, countries: list[dict[str, Any]]) -> int:
        rows: list[tuple[Any, ...]] = []
        for item in countries:
            code = str(item.get("country_code") or item.get("id") or "").strip().upper()
            if not code:
                continue
            rows.append(
                (
                    code,
                    str(item.get("iso2_code") or item.get("iso2Code") or ""),
                    str(item.get("name") or code),
                    str(item.get("name_zh") or ""),
                    str(item.get("region_id") or ""),
                    str(item.get("region_name") or ""),
                    str(item.get("income_level_id") or ""),
                    str(item.get("income_level_name") or ""),
                    str(item.get("capital_city") or ""),
                    self._history_number(item.get("longitude")),
                    self._history_number(item.get("latitude")),
                    str(item.get("fetched_at") or datetime.now().isoformat()),
                )
            )
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO world_bank_countries
                    (country_code, iso2_code, name, name_zh, region_id,
                     region_name, income_level_id, income_level_name,
                     capital_city, longitude, latitude, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(country_code) DO UPDATE SET
                    iso2_code = excluded.iso2_code,
                    name = excluded.name,
                    name_zh = excluded.name_zh,
                    region_id = excluded.region_id,
                    region_name = excluded.region_name,
                    income_level_id = excluded.income_level_id,
                    income_level_name = excluded.income_level_name,
                    capital_city = excluded.capital_city,
                    longitude = excluded.longitude,
                    latitude = excluded.latitude,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
        return len(rows)

    def world_bank_countries(
        self, country_codes: list[str] | None = None
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        clause = ""
        if country_codes:
            normalized = [item.strip().upper() for item in country_codes if item.strip()]
            if not normalized:
                return []
            clause = f"WHERE country_code IN ({','.join('?' for _ in normalized)})"
            parameters.extend(normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM world_bank_countries
                {clause}
                ORDER BY country_code
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_world_bank_indicator(self, indicator: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO world_bank_indicators
                    (indicator_id, name, title_zh, topic, unit, source_id,
                     source_name, source_note, source_organization, source_url,
                     license, attribution, last_updated, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator_id) DO UPDATE SET
                    name = excluded.name,
                    title_zh = excluded.title_zh,
                    topic = excluded.topic,
                    unit = excluded.unit,
                    source_id = excluded.source_id,
                    source_name = excluded.source_name,
                    source_note = excluded.source_note,
                    source_organization = excluded.source_organization,
                    source_url = excluded.source_url,
                    license = excluded.license,
                    attribution = excluded.attribution,
                    last_updated = excluded.last_updated,
                    fetched_at = excluded.fetched_at
                """,
                (
                    str(indicator.get("indicator_id") or ""),
                    str(indicator.get("name") or ""),
                    str(indicator.get("title_zh") or ""),
                    str(indicator.get("topic") or ""),
                    str(indicator.get("unit") or ""),
                    str(indicator.get("source_id") or "2"),
                    str(
                        indicator.get("source_name")
                        or "World Development Indicators"
                    ),
                    str(indicator.get("source_note") or ""),
                    str(indicator.get("source_organization") or ""),
                    str(indicator.get("source_url") or ""),
                    str(indicator.get("license") or "CC BY 4.0"),
                    str(indicator.get("attribution") or ""),
                    indicator.get("last_updated"),
                    str(indicator.get("fetched_at") or datetime.now().isoformat()),
                ),
            )

    def world_bank_indicator(self, indicator_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM world_bank_indicators WHERE indicator_id = ?
                """,
                (indicator_id.strip().upper(),),
            ).fetchone()
        return dict(row) if row else None

    def upsert_world_bank_observations(
        self, observations: list[dict[str, Any]], *, fetched_at: str
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for item in observations:
            code = str(item.get("country_code") or "").strip().upper()
            indicator = str(item.get("indicator_id") or "").strip().upper()
            try:
                year = int(item.get("year"))
            except (TypeError, ValueError):
                continue
            if not code or not indicator:
                continue
            rows.append(
                (
                    code,
                    indicator,
                    year,
                    self._history_number(item.get("value")),
                    str(item.get("obs_status") or ""),
                    (
                        int(item["decimal_places"])
                        if item.get("decimal_places") is not None
                        else None
                    ),
                    fetched_at,
                )
            )
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO world_bank_observations
                    (country_code, indicator_id, observation_year, value,
                     obs_status, decimal_places, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(country_code, indicator_id, observation_year)
                DO UPDATE SET
                    value = excluded.value,
                    obs_status = excluded.obs_status,
                    decimal_places = excluded.decimal_places,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
        return len(rows)

    def world_bank_observations(
        self,
        country_codes: list[str],
        indicator_id: str,
        start_year: int,
        end_year: int,
    ) -> list[dict[str, Any]]:
        normalized = [item.strip().upper() for item in country_codes if item.strip()]
        if not normalized:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT country_code, indicator_id,
                       observation_year AS year, value, obs_status,
                       decimal_places, fetched_at
                FROM world_bank_observations
                WHERE country_code IN ({','.join('?' for _ in normalized)})
                  AND indicator_id = ?
                  AND observation_year BETWEEN ? AND ?
                ORDER BY observation_year, country_code
                """,
                [*normalized, indicator_id.strip().upper(), start_year, end_year],
            ).fetchall()
        return [dict(row) for row in rows]

    def world_bank_cache_age(
        self,
        country_codes: list[str],
        indicator_id: str,
        start_year: int,
        end_year: int,
    ) -> int | None:
        normalized = [item.strip().upper() for item in country_codes if item.strip()]
        if not normalized:
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT MIN(fetched_at) AS fetched_at, COUNT(*) AS count
                FROM world_bank_observations
                WHERE country_code IN ({','.join('?' for _ in normalized)})
                  AND indicator_id = ?
                  AND observation_year BETWEEN ? AND ?
                """,
                [*normalized, indicator_id.strip().upper(), start_year, end_year],
            ).fetchone()
        expected = len(normalized) * (end_year - start_year + 1)
        if row is None or int(row["count"] or 0) < expected or not row["fetched_at"]:
            return None
        try:
            fetched = datetime.fromisoformat(str(row["fetched_at"]))
        except ValueError:
            return None
        return max(0, int((datetime.now() - fetched).total_seconds()))

    def world_bank_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            observation = connection.execute(
                """
                SELECT COUNT(DISTINCT country_code) AS countries,
                       COUNT(DISTINCT indicator_id) AS indicators,
                       COUNT(*) AS points,
                       MIN(observation_year) AS oldest,
                       MAX(observation_year) AS newest,
                       MAX(fetched_at) AS last_fetched_at
                FROM world_bank_observations
                """
            ).fetchone()
        return dict(observation) if observation else {
            "countries": 0,
            "indicators": 0,
            "points": 0,
            "oldest": None,
            "newest": None,
            "last_fetched_at": None,
        }

    def clear_world_bank_cache(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM world_bank_observations")
            connection.execute("DELETE FROM world_bank_indicators")
            connection.execute("DELETE FROM world_bank_countries")

    def upsert_gdelt_cache(
        self,
        *,
        cache_key: str,
        query: str,
        days: int,
        result_limit: int,
        sort: str,
        payload: dict[str, Any],
        fetched_at: str,
        expires_at: str,
    ) -> None:
        articles = payload.get("articles", [])
        row_count = len(articles) if isinstance(articles, list) else 0
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=str
        )
        if len(encoded.encode()) > 512 * 1024:
            raise ValueError("GDELT 单次缓存不得超过 512 KB")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO gdelt_query_cache
                    (cache_key, query, days, result_limit, sort, payload,
                     row_count, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    query = excluded.query,
                    days = excluded.days,
                    result_limit = excluded.result_limit,
                    sort = excluded.sort,
                    payload = excluded.payload,
                    row_count = excluded.row_count,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    query,
                    days,
                    result_limit,
                    sort,
                    encoded,
                    row_count,
                    fetched_at,
                    expires_at,
                ),
            )

    def get_gdelt_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM gdelt_query_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload"]))
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            expired = datetime.fromisoformat(str(row["expires_at"])) <= datetime.now()
        except ValueError:
            expired = True
        return {**dict(row), "payload": payload, "expired": expired}

    def gdelt_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS queries,
                       COALESCE(SUM(row_count), 0) AS articles,
                       MAX(fetched_at) AS last_fetched_at,
                       MAX(expires_at) AS newest_expiry
                FROM gdelt_query_cache
                """
            ).fetchone()
        return dict(row) if row else {
            "queries": 0,
            "articles": 0,
            "last_fetched_at": None,
            "newest_expiry": None,
        }

    def clear_gdelt_cache(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM gdelt_query_cache")

    def calibrate_fred_storage(self) -> dict[str, int]:
        """Remove legacy FRED values and reduce old evidence to references.

        v0.6.0 persisted FRED observations and complete chart payloads.  The
        current FRED terms prohibit that storage model, so the calibration is
        deliberately idempotent and runs before the application serves data.
        """
        migrated = 0
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, payload, source_summary, observation_start,
                       observation_end, created_at
                FROM research_evidence
                """
            ).fetchall()
            for row in rows:
                source_summary = str(row["source_summary"] or "")
                try:
                    payload = json.loads(row["payload"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                source_name = str(
                    ((payload.get("source_meta") or {}).get("source") or "")
                    if isinstance(payload.get("source_meta"), dict)
                    else ""
                )
                is_fred = source_summary.strip().upper().startswith("FRED") or (
                    source_name.strip().upper().startswith("FRED")
                )
                if not is_fred or payload.get("storage_mode") == "reference_only":
                    continue

                chart = payload.get("chart") if isinstance(payload.get("chart"), dict) else {}
                series_rows = chart.get("series") if isinstance(chart, dict) else []
                references: list[dict[str, Any]] = []
                if isinstance(series_rows, list):
                    for item in series_rows:
                        if not isinstance(item, dict):
                            continue
                        series_id = str(item.get("key") or "").strip().upper()
                        if not series_id:
                            continue
                        references.append(
                            {
                                "series_id": series_id,
                                "name": str(item.get("name") or series_id),
                                "units": item.get("units"),
                                "frequency": item.get("frequency"),
                                "attribution": item.get("attribution"),
                                "source_url": item.get("source_url"),
                            }
                        )
                if not references:
                    suffix = source_summary.split("·", 1)[-1]
                    for series_id in suffix.split(","):
                        normalized = series_id.strip().upper()
                        if normalized:
                            references.append(
                                {"series_id": normalized, "name": normalized}
                            )
                replacement = {
                    "schema_version": 2,
                    "storage_mode": "reference_only",
                    "provider": "FRED",
                    "captured_at": payload.get("captured_at") or row["created_at"],
                    "series": references,
                    "transform": chart.get("transform") if isinstance(chart, dict) else None,
                    "years": chart.get("years") if isinstance(chart, dict) else None,
                    "observation_start": row["observation_start"],
                    "observation_end": row["observation_end"],
                    "terms_url": "https://fred.stlouisfed.org/legal/terms/",
                    "notice": "FRED 证据已校准为引用；观测值不在本地持久化。",
                    "migrated_from": "v0.6.0_frozen_payload",
                }
                connection.execute(
                    "UPDATE research_evidence SET payload = ? WHERE id = ?",
                    (json.dumps(replacement, ensure_ascii=False), row["id"]),
                )
                migrated += 1
            observation_rows = connection.execute(
                "SELECT COUNT(*) AS count FROM macro_observations"
            ).fetchone()["count"]
            series_rows = connection.execute(
                "SELECT COUNT(*) AS count FROM macro_series"
            ).fetchone()["count"]
            connection.execute("DELETE FROM macro_observations")
            connection.execute("DELETE FROM macro_series")
        return {
            "evidence_migrated": migrated,
            "observations_deleted": int(observation_rows),
            "series_deleted": int(series_rows),
        }

    def list_alerts(self) -> list[AlertItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT alert_rules.*,
                       alert_state.last_matched,
                       alert_state.last_value,
                       alert_state.evaluated_at AS last_evaluated_at
                FROM alert_rules
                LEFT JOIN alert_state ON alert_state.alert_id = alert_rules.id
                ORDER BY alert_rules.created_at DESC
                """
            ).fetchall()
        return [self._alert_from_row(row) for row in rows]

    def add_alert(self, item: AlertCreate) -> AlertItem:
        now = datetime.now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alert_rules
                (object_type, object_id, name, metric, operator, threshold,
                 cooldown_minutes, max_triggers_per_day, quiet_start, quiet_end,
                 enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.object_type,
                    item.object_id,
                    item.name,
                    item.metric,
                    item.operator,
                    item.threshold,
                    item.cooldown_minutes,
                    item.max_triggers_per_day,
                    item.quiet_start,
                    item.quiet_end,
                    int(item.enabled),
                    now.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM alert_rules WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("提醒保存失败")
        return self._alert_from_row(row)

    def set_alert_enabled(self, item_id: int, enabled: bool) -> AlertItem | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE alert_rules SET enabled = ? WHERE id = ?",
                (int(enabled), item_id),
            )
            row = connection.execute(
                "SELECT * FROM alert_rules WHERE id = ?", (item_id,)
            ).fetchone()
        return self._alert_from_row(row) if row else None

    def enabled_alerts(self, object_type: str) -> list[AlertItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_rules
                WHERE enabled = 1 AND object_type = ?
                ORDER BY created_at DESC
                """,
                (object_type,),
            ).fetchall()
        return [self._alert_from_row(row) for row in rows]

    def delete_alert(self, item_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM alert_rules WHERE id = ?", (item_id,))

    def latest_trigger_at(self, alert_id: int) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT triggered_at FROM alert_triggers
                WHERE alert_id = ? ORDER BY triggered_at DESC LIMIT 1
                """,
                (alert_id,),
            ).fetchone()
        return datetime.fromisoformat(row["triggered_at"]) if row else None

    def daily_trigger_count(self, alert_id: int, observed: date | None = None) -> int:
        day = (observed or date.today()).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM alert_triggers
                WHERE alert_id = ? AND substr(triggered_at, 1, 10) = ?
                """,
                (alert_id, day),
            ).fetchone()
        return int(row["total"]) if row else 0

    def alert_last_matched(self, alert_id: int) -> bool | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT last_matched FROM alert_state WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        return bool(row["last_matched"]) if row else None

    def set_alert_state(
        self, alert_id: int, matched: bool, value: float | None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO alert_state
                    (alert_id, last_matched, last_value, evaluated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    last_matched = excluded.last_matched,
                    last_value = excluded.last_value,
                    evaluated_at = excluded.evaluated_at
                """,
                (alert_id, int(matched), value, datetime.now().isoformat()),
            )

    def add_alert_trigger(
        self,
        alert: AlertItem,
        trigger_value: float,
        source: str,
        observation_time: str | None,
    ) -> AlertTriggerItem:
        now = datetime.now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alert_triggers
                    (alert_id, object_type, object_id, name, metric, operator,
                     threshold, trigger_value, source, observation_time,
                     triggered_at, read)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    alert.id,
                    alert.object_type,
                    alert.object_id,
                    alert.name,
                    alert.metric,
                    alert.operator,
                    alert.threshold,
                    trigger_value,
                    source,
                    observation_time,
                    now.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM alert_triggers WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("提醒触发记录保存失败")
        return self._trigger_from_row(row)

    def list_alert_triggers(
        self,
        *,
        limit: int = 100,
        unread_only: bool = False,
    ) -> list[AlertTriggerItem]:
        where = "WHERE read = 0" if unread_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM alert_triggers {where} ORDER BY triggered_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._trigger_from_row(row) for row in rows]

    def mark_alert_triggers_read(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE alert_triggers SET read = 1 WHERE read = 0"
            )
        return cursor.rowcount

    def unread_alert_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM alert_triggers WHERE read = 0"
            ).fetchone()
        return int(row["total"]) if row else 0

    def upsert_instruments(
        self, adapter: str, data: object, *, demo: bool = False
    ) -> None:
        if not isinstance(data, list):
            return
        now = datetime.now().isoformat()
        subtitle_prefix = "演示 · " if demo else ""
        records: list[tuple[str, str, str, str, str, str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("quality_state") == "suspicious":
                continue
            if adapter == "spot_bonds":
                verification_prefix = (
                    "需核验 · " if item.get("code_verified") is False else ""
                )
                records.append(
                    (
                        "bond",
                        str(item.get("code", "")),
                        str(item.get("name", "")),
                        subtitle_prefix
                        + verification_prefix
                        + str(item.get("type", "现券")),
                        str(item.get("type", "")),
                        "bonds",
                        now,
                    )
                )
            elif adapter == "treasury_futures":
                records.append(
                    (
                        "future",
                        str(item.get("product", "")),
                        str(item.get("contract", item.get("product", ""))),
                        subtitle_prefix + "国债期货",
                        str(item.get("product", "")),
                        "futures",
                        now,
                    )
                )
            elif adapter == "convertibles":
                records.append(
                    (
                        "convertible",
                        str(item.get("code", "")),
                        str(item.get("name", "")),
                        subtitle_prefix + str(item.get("stock_name", "可转债")),
                        str(item.get("stock_name", "")),
                        "convertibles",
                        now,
                    )
                )
            elif adapter in {"fx_pairs", "fx_rmb_reference"}:
                source_label = (
                    "外币对即时询价"
                    if adapter == "fx_pairs"
                    else "人民币日频参考价"
                )
                records.append(
                    (
                        "fx",
                        str(item.get("code", "")),
                        str(item.get("name", item.get("pair", ""))),
                        subtitle_prefix + source_label,
                        " ".join(
                            [
                                str(item.get("pair", "")),
                                str(item.get("base", "")),
                                str(item.get("quote", "")),
                            ]
                        ).strip(),
                        "fx",
                        now,
                    )
                )
        records = [record for record in records if record[1] and record[2]]
        if not records:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO instrument_index
                    (object_type, object_id, name, subtitle, aliases, page, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_type, object_id) DO UPDATE SET
                    name = excluded.name,
                    subtitle = excluded.subtitle,
                    aliases = excluded.aliases,
                    page = excluded.page,
                    updated_at = excluded.updated_at
                """,
                records,
            )

    def search_instruments(self, query: str, limit: int = 20) -> list[SearchResult]:
        term = query.strip()
        if not term:
            return []
        pattern = f"%{term}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT object_type, object_id, name, subtitle, page, updated_at
                FROM instrument_index
                WHERE object_id LIKE ? COLLATE NOCASE
                   OR name LIKE ? COLLATE NOCASE
                   OR aliases LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE WHEN object_id = ? COLLATE NOCASE THEN 0 ELSE 1 END,
                    updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, term, max(1, min(limit, 50))),
            ).fetchall()
        return [SearchResult(**dict(row)) for row in rows]

    def search_research_topics(
        self, query: str, limit: int = 20
    ) -> list[SearchResult]:
        term = query.strip()
        if not term:
            return []
        pattern = f"%{term}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT topic.id, topic.title, topic.question, topic.updated_at,
                       object.name AS object_name, object.object_key
                FROM research_topics AS topic
                JOIN research_objects AS object ON object.id = topic.object_id
                WHERE topic.title LIKE ? COLLATE NOCASE
                   OR topic.question LIKE ? COLLATE NOCASE
                   OR topic.description LIKE ? COLLATE NOCASE
                   OR topic.tags LIKE ? COLLATE NOCASE
                   OR object.name LIKE ? COLLATE NOCASE
                   OR object.object_key LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE WHEN topic.title = ? COLLATE NOCASE THEN 0 ELSE 1 END,
                    CASE topic.status WHEN 'archived' THEN 1 ELSE 0 END,
                    topic.updated_at DESC
                LIMIT ?
                """,
                (
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    term,
                    max(1, min(limit, 50)),
                ),
            ).fetchall()
        return [
            SearchResult(
                object_type="topic",
                object_id=str(row["id"]),
                name=row["title"],
                subtitle=f"专题研究 · {row['object_name']}",
                page="topics",
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _watchlist_from_row(row: sqlite3.Row) -> WatchlistItem:
        payload = dict(row)
        try:
            tags = json.loads(payload.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        payload["tags"] = tags if isinstance(tags, list) else []
        payload["pinned"] = bool(payload.get("pinned"))
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(
            payload.get("updated_at") or payload["created_at"].isoformat()
        )
        return WatchlistItem(**payload)

    @staticmethod
    def _research_object_from_row(row: sqlite3.Row) -> ResearchObjectItem:
        payload = dict(row)
        try:
            tags = json.loads(payload.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        payload["tags"] = tags if isinstance(tags, list) else []
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        return ResearchObjectItem(**payload)

    @classmethod
    def _research_topic_from_row(
        cls,
        row: sqlite3.Row,
        project_rows: list[sqlite3.Row],
    ) -> ResearchTopicItem:
        payload = dict(row)
        try:
            tags = json.loads(payload.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        try:
            components = json.loads(payload.get("components") or "[]")
        except (TypeError, json.JSONDecodeError):
            components = []
        try:
            object_tags = json.loads(payload.get("object_tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            object_tags = []
        research_object = ResearchObjectItem(
            id=int(payload["object_id"]),
            object_type=payload["object_type"],
            object_key=payload["object_key"],
            name=payload["object_name"],
            description=payload["object_description"],
            tags=object_tags if isinstance(object_tags, list) else [],
            created_at=datetime.fromisoformat(payload["object_created_at"]),
            updated_at=datetime.fromisoformat(payload["object_updated_at"]),
        )
        projects = [
            ResearchTopicProjectItem(
                id=int(project["id"]),
                title=project["title"],
                status=project["status"],
                confidence=int(project["confidence"]),
                next_review_date=project["next_review_date"],
                updated_at=datetime.fromisoformat(project["updated_at"]),
            )
            for project in project_rows
        ]
        return ResearchTopicItem(
            id=int(payload["id"]),
            title=payload["title"],
            question=payload["question"],
            description=payload["description"],
            status=payload["status"],
            tags=tags if isinstance(tags, list) else [],
            components=components if isinstance(components, list) else [],
            research_object=research_object,
            projects=projects,
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )

    @staticmethod
    def _evidence_basket_from_row(row: sqlite3.Row) -> EvidenceBasketItem:
        payload = dict(row)
        try:
            decoded = json.loads(payload.get("payload") or "{}")
        except (TypeError, json.JSONDecodeError):
            decoded = {}
        payload["payload"] = decoded if isinstance(decoded, dict) else {}
        payload["research_object_id"] = payload.pop("object_id", None)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return EvidenceBasketItem(**payload)

    @staticmethod
    def _research_evidence_from_row(row: sqlite3.Row) -> ResearchEvidenceItem:
        payload = dict(row)
        try:
            decoded = json.loads(payload.get("payload") or "{}")
        except (TypeError, json.JSONDecodeError):
            decoded = {}
        payload["payload"] = decoded if isinstance(decoded, dict) else {}
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return ResearchEvidenceItem(**payload)

    @staticmethod
    def _insert_research_activity(
        connection: sqlite3.Connection,
        project_id: int,
        event_type: str,
        summary: str,
        details: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO research_project_activity
                (project_id, event_type, summary, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                event_type,
                summary,
                json.dumps(details, ensure_ascii=False, default=str),
                created_at,
            ),
        )

    @staticmethod
    def _research_activity_from_row(
        row: sqlite3.Row,
    ) -> ResearchProjectActivityItem:
        payload = dict(row)
        try:
            details = json.loads(payload.get("details") or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        payload["details"] = details if isinstance(details, dict) else {}
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return ResearchProjectActivityItem(**payload)

    @staticmethod
    def _research_entry_from_row(row: sqlite3.Row) -> ResearchEntryItem:
        payload = dict(row)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        return ResearchEntryItem(**payload)

    @staticmethod
    def _research_action_draft_from_row(
        row: sqlite3.Row,
    ) -> ResearchActionDraftItem:
        payload = dict(row)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        return ResearchActionDraftItem(**payload)

    @staticmethod
    def _research_project_from_row(
        row: sqlite3.Row,
        evidence: list[ResearchEvidenceItem],
        activity: list[ResearchProjectActivityItem],
        entries: list[ResearchEntryItem],
    ) -> ResearchProjectItem:
        payload = dict(row)
        try:
            tags = json.loads(payload.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            tags = []
        payload["tags"] = tags if isinstance(tags, list) else []
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        payload["evidence"] = evidence
        payload["activity"] = activity
        payload["entries"] = entries
        return ResearchProjectItem(**payload)

    @staticmethod
    def _release_review_from_row(row: sqlite3.Row) -> ReleaseReviewItem:
        payload = dict(row)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        if payload.get("reviewed_at"):
            payload["reviewed_at"] = datetime.fromisoformat(payload["reviewed_at"])
        return ReleaseReviewItem(**payload)

    @staticmethod
    def _credit_observation_from_row(row: sqlite3.Row) -> CreditObservationItem:
        payload = dict(row)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        return CreditObservationItem(**payload)

    @staticmethod
    def _alert_from_row(row: sqlite3.Row) -> AlertItem:
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        if payload.get("last_matched") is not None:
            payload["last_matched"] = bool(payload["last_matched"])
        if payload.get("last_evaluated_at"):
            payload["last_evaluated_at"] = datetime.fromisoformat(
                payload["last_evaluated_at"]
            )
        return AlertItem(**payload)

    @staticmethod
    def _trigger_from_row(row: sqlite3.Row) -> AlertTriggerItem:
        payload = dict(row)
        payload["read"] = bool(payload["read"])
        payload["triggered_at"] = datetime.fromisoformat(payload["triggered_at"])
        return AlertTriggerItem(**payload)
