from __future__ import annotations

import math
import os
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from itertools import count
from pathlib import Path
from queue import Empty, Full, PriorityQueue
from threading import Event, RLock, Semaphore, Thread
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
import certifi

from . import demo_data
from .cache import MemoryCache, PersistentCache
from .models import Dataset, HealthItem, SourceMeta


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
        if value in {"", "-", "--", "—"}:
            return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _pick(row: pd.Series, *candidates: str, default: Any = None) -> Any:
    for candidate in candidates:
        if candidate in row and not pd.isna(row[candidate]):
            return row[candidate]
    return default


def _last_two(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series | None]:
    if frame.empty:
        raise ValueError("数据源返回空表")
    current = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else None
    return current, previous


class SourceTimeoutError(TimeoutError):
    pass


class SourceCircuitOpenError(RuntimeError):
    pass


SOURCE_RESULT_MARKER = "__AKDESK_SOURCE_RESULT__="
AUX_RESULT_MARKER = "__AKDESK_AUX_RESULT__="


def _trusted_subprocess_env() -> dict[str, str]:
    """Give macOS child processes an explicit, verified CA bundle."""
    env = os.environ.copy()
    ca_bundle = certifi.where()
    env.setdefault("SSL_CERT_FILE", ca_bundle)
    env.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    return env


class _IsolatedSourceRunner:
    """Execute AKShare adapters in killable, isolated subprocesses."""

    def __init__(self, max_concurrency: int) -> None:
        self.max_concurrency = max(1, min(max_concurrency, 4))
        self._slots = Semaphore(self.max_concurrency)
        self._backend_root = Path(__file__).resolve().parents[1]
        self._state_lock = RLock()
        self._active = 0
        self._waiting = 0

    def call(
        self,
        adapter: str,
        *,
        execution_timeout: float,
        queue_timeout: float,
    ) -> tuple[Any, str | None] | tuple[Any, str | None, list[str]]:
        with self._state_lock:
            self._waiting += 1
        acquired = self._slots.acquire(timeout=queue_timeout)
        with self._state_lock:
            self._waiting -= 1
            if acquired:
                self._active += 1
        if not acquired:
            raise SourceTimeoutError(
                f"数据源排队超过 {queue_timeout:g} 秒仍未开始"
            )
        try:
            env = _trusted_subprocess_env()
            env.update(
                {
                    "AKDESK_DEMO": "0",
                    "AKDESK_NOTIFICATIONS": "0",
                    "AKDESK_SOURCE_WORKER": "1",
                    "AKDESK_SOURCE_ATTEMPTS": "1",
                    "PYTHONPATH": str(self._backend_root)
                    + (
                        os.pathsep + env["PYTHONPATH"]
                        if env.get("PYTHONPATH")
                        else ""
                    ),
                }
            )
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "app.source_worker", adapter],
                    cwd=self._backend_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=execution_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SourceTimeoutError(
                    f"数据源超过 {execution_timeout:g} 秒仍未返回，已终止隔离进程"
                ) from exc

            marker_line = next(
                (
                    line
                    for line in reversed(completed.stdout.splitlines())
                    if line.startswith(SOURCE_RESULT_MARKER)
                ),
                None,
            )
            if marker_line is None:
                detail = (completed.stderr or completed.stdout).strip()[-500:]
                raise RuntimeError(
                    f"隔离数据进程异常退出（{completed.returncode}）：{detail or '无输出'}"
                )
            payload = json.loads(marker_line.removeprefix(SOURCE_RESULT_MARKER))
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error") or "隔离数据进程调用失败")
            warnings = payload.get("warnings") or []
            result = (payload["data"], payload.get("observation_time"))
            return (*result, warnings) if warnings else result
        finally:
            with self._state_lock:
                self._active -= 1
            self._slots.release()

    def stats(self) -> dict[str, int]:
        with self._state_lock:
            return {
                "active": self._active,
                "waiting": self._waiting,
                "max_concurrency": self.max_concurrency,
            }


class DataService:
    ADAPTERS = [
        ("trade_calendar", "交易日历"),
        ("money_rates", "Shibor 资金面"),
        ("money_fr", "FR 定盘利率"),
        ("money_fdr", "FDR 定盘利率"),
        ("money_lpr", "LPR 贷款市场报价"),
        ("yield_curves", "收益率曲线"),
        ("spot_bonds", "现券成交"),
        ("treasury_futures", "国债期货"),
        ("fx_pairs", "全球外币对"),
        ("fx_rmb_reference", "人民币汇率参考"),
        ("convertibles", "可转债"),
        ("issuance_events", "国债发行"),
    ]
    DAILY_ADAPTERS = {
        "trade_calendar",
        "money_rates",
        "money_fr",
        "money_fdr",
        "money_lpr",
        "yield_curves",
        "fx_rmb_reference",
        "issuance_events",
    }
    MARKET_SESSIONS = {
        "spot_bonds": (((9, 0), (12, 0)), ((13, 30), (16, 30))),
        "treasury_futures": (((9, 30), (11, 30)), ((13, 0), (15, 15))),
        "fx_pairs": (((0, 0), (23, 59)),),
        "convertibles": (((9, 30), (11, 30)), ((13, 0), (15, 0))),
    }
    REQUIRED_FIELDS = {
        "money_rates": ("name", "value"),
        "money_fr": ("name", "value"),
        "money_fdr": ("name", "value"),
        "money_lpr": ("name", "value"),
        "spot_bonds": ("code", "name"),
        "treasury_futures": ("product", "contract", "price"),
        "fx_pairs": ("code", "name", "bid", "ask", "mid"),
        "fx_rmb_reference": ("code", "name", "mid", "observation_date"),
        "convertibles": ("code", "name", "price"),
        "issuance_events": ("date", "title"),
    }
    BASE_TTLS = {
        "trade_calendar": 86_400,
        "money_rates": 1_800,
        "money_fr": 1_800,
        "money_fdr": 1_800,
        "money_lpr": 21_600,
        "yield_curves": 3_600,
        "spot_bonds": 60,
        "treasury_futures": 30,
        "fx_pairs": 120,
        "fx_rmb_reference": 21_600,
        "convertibles": 120,
        "issuance_events": 21_600,
    }

    def __init__(
        self,
        cache_path: Path | None = None,
        on_dataset: Callable[[str, Dataset], None] | None = None,
    ) -> None:
        self.cache = PersistentCache(cache_path) if cache_path else MemoryCache()
        self.demo_only = os.getenv("AKDESK_DEMO", "0") == "1"
        self.health: dict[str, HealthItem] = {}
        self._health_lock = RLock()
        self._adapter_locks = {adapter: RLock() for adapter, _ in self.ADAPTERS}
        self._refresh_lock = RLock()
        self._refreshing: set[str] = set()
        self._circuit_lock = RLock()
        self._circuit_failures: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self._circuit_half_open: set[str] = set()
        self.circuit_threshold = max(
            1, int(os.getenv("AKDESK_CIRCUIT_THRESHOLD", "3"))
        )
        self.circuit_cooldown_seconds = max(
            30.0, float(os.getenv("AKDESK_CIRCUIT_COOLDOWN", "300"))
        )
        self._scheduler_stop = Event()
        self._scheduler_thread: Thread | None = None
        self._prewarm_thread: Thread | None = None
        self._refresh_queue: PriorityQueue[
            tuple[int, int, str, Callable[[], Dataset]]
        ] = PriorityQueue(maxsize=32)
        self._refresh_sequence = count()
        self._refresh_workers: list[Thread] = []
        self._refresh_workers_lock = RLock()
        self._on_dataset = on_dataset
        self._event_lock = RLock()
        self._emitted_cache_versions: set[tuple[str, str]] = set()
        self._event_errors: dict[str, str] = {}
        self.is_source_worker = os.getenv("AKDESK_SOURCE_WORKER", "0") == "1"
        self._source_runner = _IsolatedSourceRunner(
            int(os.getenv("AKDESK_SOURCE_CONCURRENCY", "2"))
        )
        self.timeout_seconds = max(
            1.0, float(os.getenv("AKDESK_SOURCE_TIMEOUT", "40"))
        )
        self.queue_timeout_seconds = max(
            self.timeout_seconds,
            float(os.getenv("AKDESK_SOURCE_QUEUE_TIMEOUT", "45")),
        )
        self.retry_attempts = max(1, int(os.getenv("AKDESK_SOURCE_ATTEMPTS", "2")))
        self._ak: Any | None = None

    @property
    def ak(self) -> Any:
        if self._ak is None:
            import akshare as ak

            self._ak = ak
        return self._ak

    def _update_health(
        self,
        adapter: str,
        label: str,
        state: str,
        started: float,
        rows: int,
        observation_time: str | None,
        message: str | None = None,
        *,
        count_failure: bool = True,
        dataset: Dataset | None = None,
    ) -> None:
        now = datetime.now()
        market_status, market_label = self._market_status(adapter)
        quality_score = dataset.meta.quality_score if dataset else 100
        quality_issues = dataset.meta.quality_issues if dataset else []
        trust_level = dataset.meta.trust_level if dataset else "trusted"
        suspicious_rows = dataset.meta.suspicious_rows if dataset else 0
        with self._health_lock:
            previous = self.health.get(adapter)
            if state == "healthy":
                failures = 0
            elif state in {"degraded", "unavailable"} and count_failure:
                failures = (previous.consecutive_failures if previous else 0) + 1
            else:
                failures = previous.consecutive_failures if previous else 0
            circuit_state, next_retry_at = self._circuit_status(adapter)
            self.health[adapter] = HealthItem(
                adapter=adapter,
                label=label,
                state=state,
                last_success_at=(
                    now
                    if state == "healthy"
                    else dataset.meta.fetched_at
                    if state == "cached" and dataset is not None
                    else previous.last_success_at
                    if previous
                    else None
                ),
                last_failure_at=(
                    now
                    if state in {"degraded", "unavailable"} and count_failure
                    else previous.last_failure_at
                    if previous
                    else None
                ),
                observation_time=observation_time,
                rows=rows,
                latency_ms=round((time.perf_counter() - started) * 1000),
                message=message,
                last_attempt_at=now,
                consecutive_failures=failures,
                cache_age_seconds=self.cache.age_seconds(adapter),
                cache_persisted=self.cache.is_persisted(adapter),
                market_status=market_status,
                market_status_label=market_label,
                quality_score=quality_score,
                quality_issues=quality_issues,
                trust_level=trust_level,
                suspicious_rows=suspicious_rows,
                execution_mode=(
                    "local_demo" if self.demo_only else "isolated_process"
                ),
                circuit_state=circuit_state,
                next_retry_at=next_retry_at,
            )

    def _circuit_status(
        self, adapter: str
    ) -> tuple[str, datetime | None]:
        with self._circuit_lock:
            open_until = self._circuit_open_until.get(adapter)
            if open_until is not None and open_until > time.time():
                return "open", datetime.fromtimestamp(open_until)
            if adapter in self._circuit_half_open:
                return "half_open", None
            return "closed", None

    def _guard_circuit(self, adapter: str) -> None:
        with self._circuit_lock:
            open_until = self._circuit_open_until.get(adapter)
            if open_until is None:
                return
            remaining = open_until - time.time()
            if remaining > 0:
                raise SourceCircuitOpenError(
                    f"数据源熔断中，约 {max(1, round(remaining))} 秒后自动重试"
                )
            self._circuit_open_until.pop(adapter, None)
            self._circuit_half_open.add(adapter)

    def _record_source_success(self, adapter: str) -> None:
        with self._circuit_lock:
            self._circuit_failures.pop(adapter, None)
            self._circuit_open_until.pop(adapter, None)
            self._circuit_half_open.discard(adapter)

    def _record_source_failure(self, adapter: str) -> None:
        with self._circuit_lock:
            failures = self._circuit_failures.get(adapter, 0) + 1
            was_half_open = adapter in self._circuit_half_open
            self._circuit_failures[adapter] = failures
            self._circuit_half_open.discard(adapter)
            if failures >= self.circuit_threshold or was_half_open:
                self._circuit_open_until[adapter] = (
                    time.time() + self.circuit_cooldown_seconds
                )

    def _reset_circuit(self, adapter: str) -> None:
        with self._circuit_lock:
            self._circuit_failures.pop(adapter, None)
            self._circuit_open_until.pop(adapter, None)
            self._circuit_half_open.discard(adapter)

    def _emit_dataset(self, adapter: str, dataset: Dataset) -> None:
        if self._on_dataset is None:
            return
        try:
            self._on_dataset(adapter, dataset)
            self._event_errors.pop(adapter, None)
        except Exception as exc:
            # Search indexing and alert evaluation must never break market data.
            self._event_errors[adapter] = self._safe_message(exc)
            return

    def _emit_cached_dataset_once(self, adapter: str, dataset: Dataset) -> None:
        version = (adapter, dataset.meta.fetched_at.isoformat())
        with self._event_lock:
            if version in self._emitted_cache_versions:
                return
            self._emitted_cache_versions.add(version)
        self._emit_dataset(adapter, dataset)

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        message = f"{type(exc).__name__}: {exc}"
        message = re.sub(r"(https?://[^?\s]+)\?[^\s]+", r"\1?…", message)
        message = message.replace(str(Path.home()), "~")
        return message[:500]

    def _market_status(
        self, adapter: str, now: datetime | None = None
    ) -> tuple[str, str]:
        if adapter in self.DAILY_ADAPTERS:
            return "daily", "日频数据"
        current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        calendar = self.cache.get("trade_calendar", allow_stale=True)
        known_trade_dates = (
            set(calendar.data)
            if calendar is not None
            and not calendar.meta.demo
            and isinstance(calendar.data, list)
            else None
        )
        if current.weekday() >= 5:
            return "non_trading_day", "非交易日"
        if (
            adapter != "fx_pairs"
            and known_trade_dates is not None
            and current.date().isoformat() not in known_trade_dates
        ):
            return "non_trading_day", "非交易日"
        minute = current.hour * 60 + current.minute
        sessions = self.MARKET_SESSIONS.get(adapter)
        if sessions is None:
            return "unknown", "状态未知"
        normalized_sessions: list[tuple[int, int]] = []
        for start, end in sessions:
            start_minute = start[0] * 60 + start[1]
            end_minute = end[0] * 60 + end[1]
            normalized_sessions.append((start_minute, end_minute))
            if start_minute <= minute <= end_minute:
                return "trading", "交易中"
        if minute < normalized_sessions[0][0]:
            return "pre_open", "未开盘"
        if any(
            previous[1] < minute < following[0]
            for previous, following in zip(
                normalized_sessions, normalized_sessions[1:]
            )
        ):
            return "session_break", "午间休市"
        return "closed", "已收盘"

    def _recent_trade_date(
        self, current_date: date, *, include_current: bool
    ) -> date:
        calendar = self.cache.get("trade_calendar", allow_stale=True)
        if (
            calendar is not None
            and not calendar.meta.demo
            and isinstance(calendar.data, list)
        ):
            candidates: list[date] = []
            for value in calendar.data:
                try:
                    candidate = date.fromisoformat(str(value)[:10])
                except ValueError:
                    continue
                if candidate < current_date or (
                    include_current and candidate == current_date
                ):
                    candidates.append(candidate)
            if candidates:
                return max(candidates)

        if self.is_source_worker:
            try:
                frame = self.ak.tool_trade_date_hist_sina()
                if not frame.empty and "trade_date" in frame:
                    dates = sorted(
                        {
                            pd.to_datetime(value).date().isoformat()
                            for value in frame["trade_date"].tolist()
                        }
                    )
                    self.cache.set(
                        "trade_calendar",
                        Dataset(
                            data=dates,
                            meta=SourceMeta(
                                source="AKShare / Sina Finance",
                                observation_time=dates[-1] if dates else None,
                                fetched_at=datetime.now(),
                            ),
                        ),
                        ttl_seconds=86_400,
                        persist=False,
                    )
                    return self._recent_trade_date(
                        current_date, include_current=include_current
                    )
            except Exception:
                pass

        candidate = current_date if include_current else current_date - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    @staticmethod
    def _parse_source_date(value: Any) -> date | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return pd.to_datetime(text, errors="raise").date()
        except (TypeError, ValueError):
            raise ValueError(f"数据源交易日无法识别：{text[:30]}") from None

    @staticmethod
    def _parse_source_time(value: Any) -> tuple[int, int, int] | None:
        text = str(value or "").strip()
        if not text:
            return None
        match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if not match:
            raise ValueError(f"数据源市场时间无法识别：{text[:30]}")
        hour, minute, second = (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3) or 0),
        )
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"数据源市场时间无效：{text[:30]}")
        return hour, minute, second

    def _intraday_observation_timestamp(
        self,
        adapter: str,
        raw_date: Any,
        raw_time: Any,
        *,
        now: datetime | None = None,
    ) -> tuple[str | None, bool]:
        """Return a non-future market timestamp and whether its date was inferred."""
        current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        if current.tzinfo is None:
            current = current.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_date = self._parse_source_date(raw_date)
        observed_time = self._parse_source_time(raw_time)
        inferred = observed_date is None

        if observed_date is None:
            if observed_time is None:
                return None, False
            source_clock = current.replace(
                hour=observed_time[0],
                minute=observed_time[1],
                second=observed_time[2],
                microsecond=0,
            )
            today_is_trade_day = self._recent_trade_date(
                current.date(), include_current=True
            ) == current.date()
            observed_date = self._recent_trade_date(
                current.date(),
                include_current=today_is_trade_day and source_clock <= current,
            )

        if observed_time is None:
            if observed_date > current.date():
                raise ValueError(f"{adapter} 返回未来交易日 {observed_date.isoformat()}")
            return observed_date.isoformat(), inferred

        observed = datetime(
            observed_date.year,
            observed_date.month,
            observed_date.day,
            *observed_time,
            tzinfo=current.tzinfo,
        )
        if observed > current:
            raise ValueError(
                f"{adapter} 返回未来观测时间 {observed.isoformat(timespec='seconds')}"
            )
        return observed.isoformat(timespec="seconds"), inferred

    @staticmethod
    def _reject_future_observation(
        adapter: str, observation: str | None, *, now: datetime | None = None
    ) -> None:
        if not observation:
            return
        text = str(observation).strip().replace("Z", "+00:00")
        try:
            observed = datetime.fromisoformat(text)
        except ValueError:
            try:
                observed_date = date.fromisoformat(text[:10])
            except ValueError:
                return
            if observed_date > (now or datetime.now()).date():
                raise ValueError(f"{adapter} 返回未来交易日 {observed_date.isoformat()}")
            return
        current = now or datetime.now(observed.tzinfo)
        if observed.tzinfo is None and current.tzinfo is not None:
            observed = observed.replace(tzinfo=current.tzinfo)
        elif observed.tzinfo is not None and current.tzinfo is None:
            current = current.replace(tzinfo=observed.tzinfo)
        if observed > current:
            raise ValueError(f"{adapter} 返回未来观测时间 {observation}")

    @classmethod
    def _apply_data_contract(
        cls,
        adapter: str,
        data: Any,
    ) -> tuple[Any, list[str], int, int]:
        """Annotate questionable rows without hiding them from the user.

        Suspicious rows remain visible for diagnosis, but downstream research,
        history and alerts can exclude them deterministically.
        """
        issues: list[str] = []
        penalty = 0
        suspicious_rows = 0
        if not isinstance(data, list):
            return data, issues, suspicious_rows, penalty

        invalid_codes = 0
        inferred_codes = 0
        inferred_types = 0
        price_only_convertibles = 0
        incomplete_convertibles = 0
        for raw in data:
            if not isinstance(raw, dict):
                continue
            raw.pop("quality_state", None)
            raw.pop("quality_issues", None)
            row_issues: list[str] = []
            partial_issues: list[str] = []

            if adapter == "spot_bonds":
                name = str(raw.get("name") or "").strip()
                code = str(raw.get("code") or "").strip()
                existing_code_source = str(raw.get("code_source") or "")
                valid_code = (
                    code != name
                    and bool(re.fullmatch(r"[A-Za-z0-9.]{4,24}", code))
                    and sum(character.isdigit() for character in code) >= 3
                )
                if not valid_code:
                    inferred_code = cls._infer_bond_code(name)
                    if inferred_code:
                        raw["code"] = inferred_code
                        raw["code_available"] = True
                        raw["code_verified"] = False
                        raw["code_source"] = "standard_name_rule"
                        inferred_codes += 1
                        partial_issues.append("债券代码由标准简称规则推导，使用前需核验")
                    else:
                        raw["code"] = ""
                        raw["code_available"] = False
                        raw["code_verified"] = False
                        raw["code_source"] = "unavailable"
                        invalid_codes += 1
                        partial_issues.append("源未提供可信债券代码")
                else:
                    raw["code_available"] = True
                    if existing_code_source == "standard_name_rule":
                        raw["code_verified"] = False
                        inferred_codes += 1
                        partial_issues.append("债券代码由标准简称规则推导，使用前需核验")
                    else:
                        raw["code_verified"] = True
                        raw["code_source"] = "source"

                source_type = str(raw.get("type") or "").strip()
                if not source_type or source_type == "现券":
                    inferred = cls._infer_bond_type(name)
                    raw["type"] = inferred
                    raw["type_inferred"] = True
                    inferred_types += 1
                else:
                    raw["type_inferred"] = False

                yield_value = _number(raw.get("yield"))
                change = _number(raw.get("change_bp"))
                price = _number(raw.get("price"))
                volume = _number(raw.get("volume"))
                if yield_value is not None and not (-2 <= yield_value <= 30):
                    row_issues.append("收益率超出合理范围")
                if change is not None and abs(change) > 50:
                    row_issues.append("单日收益率变动超过 50 BP")
                if price is not None and not (0 < price <= 300):
                    row_issues.append("净价超出合理范围")
                if volume is not None and volume < 0:
                    row_issues.append("成交量为负数")

            elif adapter == "convertibles":
                code = str(raw.get("code") or "").strip()
                name = str(raw.get("name") or "").strip()
                price = _number(raw.get("price"))
                if not re.fullmatch(r"(?:110|111|113|118|123|127|128)\d{3}", code):
                    row_issues.append("转债代码不在有效交易代码范围")
                if not name or "退市" in name or name.endswith("退"):
                    row_issues.append("标的名称疑似失效")
                if price is None or not (0 < price <= 500):
                    row_issues.append("价格为空、为零或超出合理范围")
                range_rules = (
                    ("change_pct", -50, 50, "涨跌幅"),
                    ("premium_pct", -100, 1_000, "转股溢价率"),
                    ("double_low", 0, 1_000, "双低值"),
                    ("ytm_pct", -100, 100, "到期收益率"),
                )
                for field, minimum, maximum, label in range_rules:
                    value = _number(raw.get(field))
                    if value is not None and not (minimum <= value <= maximum):
                        row_issues.append(f"{label}超出合理范围")
                core_fields = ("convert_value", "premium_pct", "double_low")
                covered_fields = sum(
                    _number(raw.get(field)) is not None for field in core_fields
                )
                data_tier = str(raw.get("data_tier") or "").strip()
                if data_tier == "price_only" or covered_fields == 0:
                    data_tier = "price_only"
                elif covered_fields == len(core_fields):
                    data_tier = "comparison"
                else:
                    data_tier = "partial_comparison"
                raw["data_tier"] = data_tier
                raw["field_coverage"] = covered_fields
                raw["research_eligible"] = (
                    data_tier == "comparison"
                    and covered_fields == len(core_fields)
                    and not row_issues
                )
                if data_tier == "price_only":
                    price_only_convertibles += 1
                    partial_issues.append("当前仅有价格字段，不进入研究立项")
                elif data_tier == "partial_comparison":
                    incomplete_convertibles += 1
                    partial_issues.append("比价核心字段不完整")

            elif adapter == "treasury_futures":
                product = str(raw.get("product") or "")
                contract = str(raw.get("contract") or "")
                price = _number(raw.get("price"))
                if product not in {"TS", "TF", "T", "TL"}:
                    row_issues.append("期货品种不可识别")
                if not re.fullmatch(r"(?:TS|TF|T|TL)\d{4}", contract):
                    row_issues.append("期货合约代码格式异常")
                if price is None or not (50 <= price <= 200):
                    row_issues.append("期货价格超出合理范围")
                change = _number(raw.get("change_pct"))
                if change is not None and abs(change) > 10:
                    row_issues.append("期货涨跌幅超出合理范围")

            elif adapter in {"fx_pairs", "fx_rmb_reference"}:
                code = str(raw.get("code") or "")
                bid = _number(raw.get("bid"))
                ask = _number(raw.get("ask"))
                mid = _number(raw.get("mid"))
                if not re.fullmatch(r"[A-Z]{6}", code):
                    row_issues.append("货币对代码格式异常")
                if mid is None or mid <= 0:
                    row_issues.append("汇率中间值为空或非正数")
                if bid is None or ask is None or bid <= 0 or ask <= 0:
                    row_issues.append("买卖报价为空或非正数")
                elif ask < bid:
                    row_issues.append("卖报价低于买报价")
                change = _number(raw.get("change_pct"))
                if change is not None and abs(change) > 20:
                    row_issues.append("单日汇率变化超出合理范围")

            elif adapter in {"money_rates", "money_fr", "money_fdr", "money_lpr"}:
                value = _number(raw.get("value"))
                change = _number(raw.get("change_bp"))
                if value is None or not (-5 <= value <= 20):
                    row_issues.append("利率值超出合理范围")
                if change is not None and abs(change) > 200:
                    row_issues.append("利率变动超过 200 BP")

            if row_issues:
                raw["quality_state"] = "suspicious"
                raw["quality_issues"] = row_issues + partial_issues
                suspicious_rows += 1
            elif partial_issues:
                raw["quality_state"] = "partial"
                raw["quality_issues"] = partial_issues

        total = max(len(data), 1)
        if invalid_codes:
            issues.append(f"债券代码不可用 {invalid_codes}/{total}")
            penalty += min(20, max(5, round(invalid_codes / total * 20)))
        if inferred_codes:
            issues.append(f"债券代码由标准简称规则推导 {inferred_codes}/{total}")
            penalty += min(8, max(3, round(inferred_codes / total * 8)))
        if inferred_types:
            issues.append(f"债券类型由名称推断 {inferred_types}/{total}")
            penalty += min(8, max(2, round(inferred_types / total * 8)))
        if suspicious_rows:
            issues.append(f"异常记录已隔离 {suspicious_rows}/{total}")
            penalty += min(40, max(10, round(suspicious_rows / total * 40)))
        if price_only_convertibles:
            issues.append(f"可转债仅价格记录 {price_only_convertibles}/{total}")
            penalty += min(35, max(10, round(price_only_convertibles / total * 35)))
        if incomplete_convertibles:
            issues.append(f"可转债比价字段不完整 {incomplete_convertibles}/{total}")
            penalty += min(20, max(5, round(incomplete_convertibles / total * 20)))
        return data, issues, suspicious_rows, penalty

    @staticmethod
    def _infer_bond_type(name: str) -> str:
        upper = name.upper()
        if "CD" in upper or "存单" in name:
            return "同业存单"
        if any(keyword in name for keyword in ("国开", "农发", "进出")):
            return "政策金融债"
        if "国债" in name:
            return "国债"
        if "地方" in name:
            return "地方政府债"
        if any(keyword in name for keyword in ("金融债", "银行债", "二级资本债")):
            return "金融债"
        if any(keyword in name for keyword in ("中票", "短融", "企业债", "公司债")):
            return "信用债"
        return "其他现券"

    @staticmethod
    def _infer_bond_code(name: str) -> str | None:
        """Conservatively recover standard sovereign/policy-bank short codes."""
        normalized = re.sub(r"\s+", "", name).upper()
        treasury = re.fullmatch(r"(?P<year>\d{2})附息国债(?P<sequence>\d{1,3})", normalized)
        if treasury:
            return treasury.group("year") + treasury.group("sequence").zfill(4)
        policy = re.fullmatch(
            r"(?P<year>\d{2})(?P<issuer>国开|进出|农发)(?P<sequence>\d{1,2})",
            normalized,
        )
        if policy:
            issuer_code = {"国开": "02", "进出": "03", "农发": "04"}[
                policy.group("issuer")
            ]
            return policy.group("year") + issuer_code + policy.group("sequence").zfill(2)
        return None

    @classmethod
    def _assess_quality(
        cls,
        adapter: str,
        data: Any,
        observation_time: str | None,
        warnings: list[str],
        *,
        demo: bool = False,
    ) -> tuple[int, list[str], str, int]:
        if demo:
            return 0, ["演示数据不参与质量评分"], "unavailable", 0
        score = 100
        issues: list[str] = []
        data, contract_issues, suspicious_rows, contract_penalty = (
            cls._apply_data_contract(adapter, data)
        )
        issues.extend(contract_issues)
        score -= contract_penalty
        if observation_time is None and adapter not in cls.DAILY_ADAPTERS:
            score -= 5
            issues.append("源未提供可信市场时间")
        if isinstance(data, list):
            required = cls.REQUIRED_FIELDS.get(adapter, ())
            total = max(len(data), 1)
            for field_name in required:
                missing = sum(
                    1
                    for item in data
                    if not isinstance(item, dict)
                    or item.get(field_name) in {None, ""}
                )
                if missing:
                    ratio = missing / total
                    score -= min(30, max(5, round(ratio * 30)))
                    issues.append(f"{field_name} 缺失 {missing}/{total}")
        elif adapter == "yield_curves":
            if not isinstance(data, dict) or not data.get("tenors") or not data.get(
                "series"
            ):
                score -= 40
                issues.append("曲线期限或序列不完整")
            else:
                tenors = data.get("tenors", [])
                latest = next(
                    (
                        item
                        for item in data.get("series", [])
                        if isinstance(item, dict) and "最新" in str(item.get("name", ""))
                    ),
                    None,
                )
                values = latest.get("values", []) if latest else []
                missing = sum(
                    1
                    for index, _tenor in enumerate(tenors)
                    if index >= len(values) or _number(values[index]) is None
                )
                if missing:
                    score -= min(20, missing * 4)
                    issues.append(f"最新曲线缺失 {missing}/{len(tenors)} 个期限")
        if warnings:
            score -= min(15, len(warnings) * 5)
        if any("备用行情" in warning for warning in warnings):
            score = min(score, 60)
            issues.append("当前仅有价格备用数据，研究字段不完整")
        score = max(0, score)
        trust_level = (
            "suspicious"
            if suspicious_rows
            else "partial"
            if warnings or score < 90 or (observation_time is None and adapter not in cls.DAILY_ADAPTERS)
            else "trusted"
        )
        return score, list(dict.fromkeys(issues)), trust_level, suspicious_rows

    def _decorate_dataset(
        self,
        adapter: str,
        dataset: Dataset,
        *,
        cache_age_seconds: int | None = None,
        from_cache: bool = False,
    ) -> Dataset:
        result = dataset.model_copy(deep=True)
        market_status, market_label = self._market_status(adapter)
        result.meta.market_status = market_status
        result.meta.market_status_label = market_label
        result.meta.cache_age_seconds = cache_age_seconds
        if result.meta.demo:
            result.meta.data_state = "demo"
        elif result.meta.stale:
            result.meta.data_state = "stale"
        elif from_cache or (cache_age_seconds is not None and cache_age_seconds > 0):
            result.meta.data_state = "cached"
        elif market_status == "trading":
            result.meta.data_state = "live"
        else:
            result.meta.data_state = "latest"
        quality_score, quality_issues, trust_level, suspicious_rows = self._assess_quality(
            adapter,
            result.data,
            result.meta.observation_time,
            result.meta.warnings,
            demo=result.meta.demo,
        )
        result.meta.quality_score = quality_score
        result.meta.quality_issues = quality_issues
        result.meta.trust_level = trust_level
        result.meta.suspicious_rows = suspicious_rows
        return result

    def _effective_ttl(self, adapter: str, base_ttl: int) -> int:
        market_status, _ = self._market_status(adapter)
        if market_status in {"pre_open", "closed"}:
            return max(base_ttl, 1_800)
        if market_status == "non_trading_day":
            return max(base_ttl, 21_600)
        return base_ttl

    def _call_with_timeout(
        self,
        adapter: str,
        loader: Callable[
            [], tuple[Any, str | None] | tuple[Any, str | None, list[str]]
        ],
    ) -> tuple[Any, str | None] | tuple[Any, str | None, list[str]]:
        if self.is_source_worker:
            return loader()
        return self._source_runner.call(
            adapter,
            execution_timeout=self.timeout_seconds,
            queue_timeout=self.queue_timeout_seconds,
        )

    def _call_aux_worker(
        self, task: str, *, timeout: float = 10
    ) -> dict[str, Any]:
        """Run an optional or fallback source without risking the core adapter."""
        completed = subprocess.run(
            [sys.executable, "-m", "app.aux_worker", task],
            cwd=Path(__file__).resolve().parents[1],
            env=_trusted_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        marker_line = next(
            (
                line
                for line in reversed(completed.stdout.splitlines())
                if line.startswith(AUX_RESULT_MARKER)
            ),
            None,
        )
        if marker_line is None:
            detail = (completed.stderr or completed.stdout).strip()[-400:]
            raise RuntimeError(detail or f"扩展数据进程异常退出（{completed.returncode}）")
        payload = json.loads(marker_line.removeprefix(AUX_RESULT_MARKER))
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "扩展数据进程调用失败")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("扩展数据进程返回格式错误")
        return result

    def _load_live(
        self,
        adapter: str,
        loader: Callable[
            [], tuple[Any, str | None] | tuple[Any, str | None, list[str]]
        ],
    ) -> tuple[Any, str | None] | tuple[Any, str | None, list[str]]:
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts):
            try:
                return self._call_with_timeout(adapter, loader)
            except SourceTimeoutError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.retry_attempts:
                    time.sleep(0.25 * (2**attempt))
        if last_error is None:
            raise RuntimeError("数据源调用失败")
        raise last_error

    def _ensure_refresh_workers(self) -> None:
        if self.demo_only or self.is_source_worker or self._scheduler_stop.is_set():
            return
        with self._refresh_workers_lock:
            self._refresh_workers = [
                worker for worker in self._refresh_workers if worker.is_alive()
            ]
            missing = self._source_runner.max_concurrency - len(
                self._refresh_workers
            )
            for index in range(missing):
                worker = Thread(
                    target=self._refresh_worker,
                    daemon=True,
                    name=f"akdesk-refresh-worker-{len(self._refresh_workers) + index + 1}",
                )
                self._refresh_workers.append(worker)
                worker.start()

    def _refresh_worker(self) -> None:
        while not self._scheduler_stop.is_set():
            try:
                _priority, _sequence, adapter, loader = self._refresh_queue.get(
                    timeout=0.5
                )
            except Empty:
                continue
            try:
                if not self._scheduler_stop.is_set():
                    loader()
            finally:
                with self._refresh_lock:
                    self._refreshing.discard(adapter)
                self._refresh_queue.task_done()

    def _background_refresh(
        self,
        adapter: str,
        loader: Callable[[], Dataset],
        *,
        priority: int = 10,
    ) -> bool:
        if self._scheduler_stop.is_set():
            return False
        circuit_state, _next_retry = self._circuit_status(adapter)
        if circuit_state == "open":
            return False
        with self._refresh_lock:
            if adapter in self._refreshing:
                return False
            self._refreshing.add(adapter)
        self._ensure_refresh_workers()
        try:
            self._refresh_queue.put_nowait(
                (priority, next(self._refresh_sequence), adapter, loader)
            )
        except Full:
            with self._refresh_lock:
                self._refreshing.discard(adapter)
            return False
        return True

    def _restore_cached_dataset(
        self,
        adapter: str,
        label: str,
        cached: Dataset,
        started: float,
        *,
        stale: bool = False,
        emit: bool = True,
    ) -> Dataset:
        result = cached.model_copy(deep=True)
        result.meta.stale = stale
        if stale:
            result.meta.warnings = list(
                dict.fromkeys(
                    ["本地缓存已过期，正在后台刷新。", *result.meta.warnings]
                )
            )
        result = self._decorate_dataset(
            adapter,
            result,
            cache_age_seconds=self.cache.age_seconds(adapter),
            from_cache=True,
        )
        message = (
            "使用过期持久缓存，后台刷新中"
            if stale
            else "持久缓存可用，尚未完成本次实时验证"
        )
        self._update_health(
            adapter,
            label,
            "degraded" if stale else "cached",
            started,
            len(result.data) if isinstance(result.data, list) else 1,
            result.meta.observation_time,
            message,
            count_failure=False,
            dataset=result,
        )
        if emit:
            self._emit_cached_dataset_once(adapter, result)
        return result

    def _cached_dataset(
        self, adapter: str, *, allow_stale: bool = False
    ) -> Dataset | None:
        cached = self.cache.get(adapter, allow_stale=allow_stale)
        if not isinstance(cached, Dataset):
            return None
        try:
            self._reject_future_observation(
                adapter, cached.meta.observation_time
            )
        except ValueError:
            self.cache.delete(adapter)
            return None
        return cached

    def _load(
        self,
        *,
        adapter: str,
        label: str,
        ttl_seconds: int,
        live_loader: Callable[
            [], tuple[Any, str | None] | tuple[Any, str | None, list[str]]
        ],
        demo_loader: Callable[[], Any],
        source: str,
        source_url: str,
        force: bool = False,
        _background: bool = False,
    ) -> Dataset:
        started = time.perf_counter()
        ttl_seconds = self._effective_ttl(adapter, ttl_seconds)
        if self.demo_only:
            data = demo_loader()
            observation = None
            dataset = Dataset(
                data=data,
                meta=SourceMeta(
                    source="内置演示数据",
                    observation_time=observation,
                    fetched_at=datetime.now(),
                    stale=True,
                    demo=True,
                    warnings=["当前运行在 AKDESK_DEMO=1 演示模式。"],
                ),
            )
            dataset = self._decorate_dataset(adapter, dataset, cache_age_seconds=0)
            self.cache.set(adapter, dataset, ttl_seconds, persist=False)
            self._update_health(
                adapter,
                label,
                "degraded",
                started,
                len(data) if isinstance(data, list) else 1,
                observation,
                "演示模式",
                count_failure=False,
                dataset=dataset,
            )
            self._emit_dataset(adapter, dataset)
            return dataset

        if not force:
            cached = self._cached_dataset(adapter)
            if cached is not None:
                return self._restore_cached_dataset(
                    adapter, label, cached, started
                )

            stale_cached = self._cached_dataset(adapter, allow_stale=True)
            if stale_cached is not None:
                result = self._restore_cached_dataset(
                    adapter, label, stale_cached, started, stale=True
                )
                self._background_refresh(
                    adapter,
                    lambda: self._load(
                        adapter=adapter,
                        label=label,
                        ttl_seconds=ttl_seconds,
                        live_loader=live_loader,
                        demo_loader=demo_loader,
                        source=source,
                        source_url=source_url,
                        force=True,
                        _background=True,
                    ),
                )
                return result

        with self._adapter_locks[adapter]:
            if not force:
                cached = self._cached_dataset(adapter)
                if cached is not None:
                    return self._restore_cached_dataset(
                        adapter, label, cached, started
                    )
            try:
                self._guard_circuit(adapter)
                loaded = self._load_live(adapter, live_loader)
                data, observation = loaded[0], loaded[1]
                self._reject_future_observation(adapter, observation)
                source_warnings = loaded[2] if len(loaded) == 3 else []
                rows = len(data) if isinstance(data, list) else 1
                if rows == 0:
                    raise ValueError("数据源返回空结果")
                dataset = Dataset(
                    data=data,
                    meta=SourceMeta(
                        source=source,
                        source_url=source_url,
                        observation_time=observation,
                        fetched_at=datetime.now(),
                        warnings=source_warnings,
                        cache_age_seconds=0,
                    ),
                )
                dataset = self._decorate_dataset(
                    adapter, dataset, cache_age_seconds=0
                )
                self._record_source_success(adapter)
                self.cache.set(adapter, dataset, ttl_seconds, persist=True)
                self._update_health(
                    adapter,
                    label,
                    "healthy",
                    started,
                    rows,
                    observation,
                    dataset=dataset,
                )
                self._emit_dataset(adapter, dataset)
                return dataset
            except Exception as exc:
                if not isinstance(exc, SourceCircuitOpenError):
                    self._record_source_failure(adapter)
                cached = self._cached_dataset(adapter, allow_stale=True)
                circuit_blocked = isinstance(exc, SourceCircuitOpenError)
                message = self._safe_message(exc)
                if circuit_blocked:
                    with self._health_lock:
                        previous_health = self.health.get(adapter)
                    if previous_health and previous_health.message:
                        message = previous_health.message
                if cached is not None:
                    result = cached.model_copy(deep=True)
                    result.meta.stale = True
                    result.meta.warnings = list(
                        dict.fromkeys(
                            [
                                f"实时更新失败，正在使用最近真实缓存：{message}",
                                *result.meta.warnings,
                            ]
                        )
                    )
                    result = self._decorate_dataset(
                        adapter,
                        result,
                        cache_age_seconds=self.cache.age_seconds(adapter),
                    )
                    self._update_health(
                        adapter,
                        label,
                        "degraded",
                        started,
                        len(result.data) if isinstance(result.data, list) else 1,
                        result.meta.observation_time,
                        message,
                        count_failure=not circuit_blocked,
                        dataset=result,
                    )
                    return result

                data = demo_loader()
                observation = None
                dataset = Dataset(
                    data=data,
                    meta=SourceMeta(
                        source="内置演示数据",
                        observation_time=observation,
                        fetched_at=datetime.now(),
                        stale=True,
                        demo=True,
                        warnings=[f"实时数据不可用，已切换演示数据：{message}"],
                    ),
                )
                dataset = self._decorate_dataset(
                    adapter, dataset, cache_age_seconds=0
                )
                self.cache.set(
                    adapter,
                    dataset,
                    min(ttl_seconds, 60),
                    persist=False,
                )
                self._update_health(
                    adapter,
                    label,
                    "unavailable",
                    started,
                    len(data) if isinstance(data, list) else 1,
                    observation,
                    message,
                    count_failure=not circuit_blocked,
                    dataset=dataset,
                )
                self._emit_dataset(adapter, dataset)
                return dataset

    def trade_calendar(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[str], str | None]:
            frame = self.ak.tool_trade_date_hist_sina()
            if frame.empty or "trade_date" not in frame:
                raise ValueError("交易日历为空或字段缺失")
            dates = sorted(
                {
                    pd.Timestamp(value).date().isoformat()
                    for value in frame["trade_date"].dropna()
                }
            )
            if not dates:
                raise ValueError("交易日历没有有效日期")
            latest_known = max(
                (value for value in dates if value <= date.today().isoformat()),
                default=None,
            )
            return dates, latest_known

        return self._load(
            adapter="trade_calendar",
            label="交易日历",
            ttl_seconds=86_400,
            live_loader=live,
            demo_loader=demo_data.trade_calendar,
            source="AKShare / Sina Calendar",
            source_url="https://akshare.akfamily.xyz/data/tool/tool.html",
            force=force,
        )

    def money_rates(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[dict], str]:
            rows: list[dict] = []

            shibor = self.ak.macro_china_shibor_all()
            current, previous = _last_two(shibor)
            for tenor, label in (("O/N", "Shibor O/N"), ("1W", "Shibor 1W")):
                value = _number(_pick(current, f"{tenor}-定价"))
                old = (
                    _number(_pick(previous, f"{tenor}-定价"))
                    if previous is not None
                    else None
                )
                if value is not None:
                    rows.append(
                        {
                            "name": label,
                            "tenor": tenor,
                            "value": value,
                            "change_bp": (
                                round((value - old) * 100, 3)
                                if old is not None
                                else None
                            ),
                        }
                    )

            observation = str(_pick(current, "日期", default="")) or date.today().isoformat()
            return rows, observation

        core = self._load(
            adapter="money_rates",
            label="Shibor 资金面",
            ttl_seconds=1_800,
            live_loader=live,
            demo_loader=demo_data.money_rates,
            source="AKShare / Shibor",
            source_url="https://akshare.akfamily.xyz/data/interest_rate/interest_rate.html",
            force=force,
        )
        if self.is_source_worker or core.meta.demo:
            return core
        return self._merge_money_extensions(core)

    def _merge_money_extensions(self, core: Dataset) -> Dataset:
        result = core.model_copy(deep=True)
        rows = list(result.data) if isinstance(result.data, list) else []
        missing: list[str] = []
        if os.getenv("AKDESK_ENABLE_EXTENDED_RATES", "1") == "1":
            for adapter, label in (
                ("money_fr", "FR"),
                ("money_fdr", "FDR"),
                ("money_lpr", "LPR"),
            ):
                extension = self.cache.get(adapter)
                if not isinstance(extension, Dataset) or extension.meta.demo:
                    missing.append(label)
                    continue
                if isinstance(extension.data, list):
                    rows.extend(
                        item for item in extension.data if isinstance(item, dict)
                    )
        else:
            missing.extend(("FR", "FDR", "LPR"))
        result.data = rows
        result.meta.source = "AKShare / 独立资金适配器"
        result.meta.warnings = (
            ["独立扩展源尚未全部更新：" + "、".join(missing)] if missing else []
        )
        return self._decorate_dataset(
            "money_rates",
            result,
            cache_age_seconds=result.meta.cache_age_seconds,
            from_cache=result.meta.data_state == "cached",
        )

    def _money_extension(
        self,
        *,
        adapter: str,
        label: str,
        field_specs: tuple[tuple[str, str, str], ...],
        loader: Callable[[], pd.DataFrame],
        date_fields: tuple[str, ...],
        ttl_seconds: int,
        force: bool,
    ) -> Dataset:
        def live() -> tuple[list[dict], str | None]:
            frame = loader()
            current, previous = _last_two(frame)
            rows: list[dict[str, Any]] = []
            for field, name, tenor in field_specs:
                value = _number(_pick(current, field))
                old = _number(_pick(previous, field)) if previous is not None else None
                if value is None:
                    continue
                rows.append(
                    {
                        "name": name,
                        "tenor": tenor,
                        "value": value,
                        "change_bp": (
                            round((value - old) * 100, 3) if old is not None else None
                        ),
                    }
                )
            if not rows:
                raise ValueError(f"{label} 没有有效记录")
            observation = str(_pick(current, *date_fields, default="")) or None
            return rows, observation

        return self._load(
            adapter=adapter,
            label=label,
            ttl_seconds=ttl_seconds,
            live_loader=live,
            demo_loader=lambda: [],
            source=f"AKShare / {label}",
            source_url="https://akshare.akfamily.xyz/data/interest_rate/interest_rate.html",
            force=force,
        )

    def money_fr(self, force: bool = False) -> Dataset:
        return self._money_extension(
            adapter="money_fr",
            label="FR 定盘利率",
            field_specs=(("FR007", "FR007", "7D"),),
            loader=lambda: self.ak.repo_rate_query(symbol="回购定盘利率"),
            date_fields=("date", "日期"),
            ttl_seconds=1_800,
            force=force,
        )

    def money_fdr(self, force: bool = False) -> Dataset:
        return self._money_extension(
            adapter="money_fdr",
            label="FDR 定盘利率",
            field_specs=(("FDR007", "FDR007", "7D"),),
            loader=lambda: self.ak.repo_rate_query(symbol="银银间回购定盘利率"),
            date_fields=("date", "日期"),
            ttl_seconds=1_800,
            force=force,
        )

    def money_lpr(self, force: bool = False) -> Dataset:
        return self._money_extension(
            adapter="money_lpr",
            label="LPR 贷款市场报价",
            field_specs=(("LPR1Y", "LPR 1Y", "1Y"), ("LPR5Y", "LPR 5Y", "5Y")),
            loader=self.ak.macro_china_lpr,
            date_fields=("TRADE_DATE", "日期"),
            ttl_seconds=21_600,
            force=force,
        )

    def yield_curves(self, force: bool = False) -> Dataset:
        def live() -> tuple[dict, str]:
            end = date.today()
            start = end - timedelta(days=21)
            frame = self.ak.bond_china_yield(
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            if frame.empty:
                raise ValueError("收益率曲线为空")

            date_column = "日期"
            curve_column = "曲线名称"
            frame[date_column] = frame[date_column].astype(str)
            all_dates = sorted(frame[date_column].dropna().unique())
            if not all_dates:
                raise ValueError("收益率曲线没有有效日期")
            latest_date = all_dates[-1]
            previous_date = all_dates[-2] if len(all_dates) > 1 else latest_date

            tenors = ["3月", "6月", "1年", "2年", "3年", "5年", "7年", "10年", "30年"]
            labels = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "30Y"]
            series: list[dict] = []
            latest_government: list[float | None] | None = None
            previous_government: list[float | None] | None = None

            preferred_curves = [
                ("中债国债收益率曲线", "中债国债"),
                ("中债国开债收益率曲线", "国开债"),
                ("中债政策性金融债收益率曲线", "政策金融债"),
            ]
            for source_name, display_name in preferred_curves:
                curve_rows = frame[frame[curve_column] == source_name]
                if curve_rows.empty:
                    continue
                latest_rows = curve_rows[curve_rows[date_column] == latest_date]
                if latest_rows.empty:
                    continue
                latest = latest_rows.iloc[-1]
                values = [_number(_pick(latest, tenor)) for tenor in tenors]
                series.append({"name": f"{display_name}·最新", "values": values})

                previous_rows = curve_rows[curve_rows[date_column] == previous_date]
                if not previous_rows.empty:
                    old = previous_rows.iloc[-1]
                    old_values = [_number(_pick(old, tenor)) for tenor in tenors]
                    if source_name == "中债国债收益率曲线":
                        latest_government = values
                        previous_government = old_values
                        series.append(
                            {"name": f"{display_name}·前值", "values": old_values}
                        )

            if latest_government is None:
                government = frame[
                    frame[curve_column].astype(str).str.contains("国债收益率曲线")
                ]
                if government.empty:
                    raise ValueError("未找到国债收益率曲线")
                latest = government[government[date_column] == latest_date].iloc[-1]
                latest_government = [_number(_pick(latest, tenor)) for tenor in tenors]
                series.insert(
                    0, {"name": "中债国债·最新", "values": latest_government}
                )

            changes = [
                (
                    round((current - old) * 100, 3)
                    if current is not None and old is not None
                    else None
                )
                for current, old in zip(
                    latest_government,
                    previous_government or [None] * len(tenors),
                    strict=True,
                )
            ]
            government_history = frame[
                frame[curve_column] == "中债国债收益率曲线"
            ]
            if government_history.empty:
                government_history = frame[
                    frame[curve_column].astype(str).str.contains("国债收益率曲线")
                ]
            history: list[dict[str, Any]] = []
            for observed in all_dates:
                observed_rows = government_history[
                    government_history[date_column] == observed
                ]
                if observed_rows.empty:
                    continue
                row = observed_rows.iloc[-1]
                values = {
                    label: _number(_pick(row, tenor))
                    for tenor, label in zip(tenors, labels, strict=True)
                }

                def spread(long_tenor: str, short_tenor: str) -> float | None:
                    long_value = values.get(long_tenor)
                    short_value = values.get(short_tenor)
                    if long_value is None or short_value is None:
                        return None
                    return round((long_value - short_value) * 100, 3)

                history.append(
                    {
                        "date": observed,
                        "values": values,
                        "spreads_bp": {
                            "10Y-1Y": spread("10Y", "1Y"),
                            "10Y-5Y": spread("10Y", "5Y"),
                            "30Y-10Y": spread("30Y", "10Y"),
                        },
                    }
                )
            return {
                "tenors": labels,
                "series": series,
                "changes": changes,
                "history": history,
            }, latest_date

        return self._load(
            adapter="yield_curves",
            label="收益率曲线",
            ttl_seconds=3_600,
            live_loader=live,
            demo_loader=demo_data.yield_curves,
            source="AKShare / ChinaBond",
            source_url="https://akshare.akfamily.xyz/data/bond/bond.html",
            force=force,
        )

    def spot_bonds(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[dict], str | None]:
            frame = self.ak.bond_spot_deal()
            if frame.empty:
                raise ValueError("现券成交为空")
            rows: list[dict] = []
            for _, row in frame.head(250).iterrows():
                name = str(_pick(row, "债券简称", "债券名称", default="未知债券"))
                rows.append(
                    {
                        "code": str(_pick(row, "债券代码", "代码", default="")),
                        "name": name,
                        "type": str(_pick(row, "债券类型", default="")),
                        "yield": _number(_pick(row, "最新收益率")),
                        "change_bp": _number(_pick(row, "涨跌")),
                        "price": _number(_pick(row, "成交净价")),
                        "volume": _number(_pick(row, "交易量"), 0),
                    }
                )
            # The spot table does not expose a trustworthy market timestamp.
            # fetched_at is recorded separately by _load.
            return rows, None

        return self._load(
            adapter="spot_bonds",
            label="现券成交",
            ttl_seconds=60,
            live_loader=live,
            demo_loader=demo_data.spot_bonds,
            source="AKShare / Chinamoney",
            source_url="https://akshare.akfamily.xyz/data/bond/bond.html",
            force=force,
        )

    def treasury_futures(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[dict], str | None, list[str]]:
            today = date.today()
            delivery_months = [3, 6, 9, 12]
            candidates: list[str] = []
            candidate_year = today.year
            while len(candidates) < 3:
                for month in delivery_months:
                    if candidate_year == today.year and month < today.month:
                        continue
                    candidates.append(f"{candidate_year % 100:02d}{month:02d}")
                    if len(candidates) == 3:
                        break
                candidate_year += 1
            subscription = ",".join(
                f"{product}{suffix}"
                for product in ("TS", "TF", "T", "TL")
                for suffix in candidates
            )
            frame = self.ak.futures_zh_spot(
                symbol=subscription,
                market="FF",
                adjust="0",
            )
            if frame.empty:
                raise ValueError("国债期货行情为空")
            best_by_product: dict[str, dict] = {}
            for _, row in frame.iterrows():
                contract_code = str(
                    _pick(row, "symbol", "contract", "合约代码", default="")
                )
                contract_name = str(_pick(row, "name", "品种", default=""))
                identity = f"{contract_code} {contract_name}".strip()
                product = next(
                    (
                        item
                        for item in ("TS", "TF", "TL", "T")
                        if contract_code.upper().startswith(item)
                    ),
                    "",
                )
                chinese_product = next(
                    (
                        code
                        for keyword, code in (
                            ("2年", "TS"),
                            ("5年", "TF"),
                            ("10年", "T"),
                            ("30年", "TL"),
                        )
                        if keyword in identity
                    ),
                    "",
                )
                product = chinese_product or product
                if product not in {"TS", "TF", "T", "TL"}:
                    continue
                suffix_match = re.search(r"(\d{4})$", identity)
                display_contract = (
                    f"{product}{suffix_match.group(1)}"
                    if suffix_match
                    else identity
                )
                current = _number(
                    _pick(row, "current_price", "trade", "最新价", "close")
                )
                previous = _number(
                    _pick(row, "presettlement", "pre_settlement", "昨结")
                )
                candidate = {
                    "product": product,
                    "contract": display_contract,
                    "price": current,
                    "change_pct": (
                        round((current / previous - 1) * 100, 4)
                        if current is not None and previous
                        else None
                    ),
                    "volume": _integer(_pick(row, "volume", "成交量")),
                    "open_interest": _integer(
                        _pick(row, "hold", "position", "持仓量")
                    ),
                }
                existing = best_by_product.get(product)
                if existing is None or candidate["volume"] > existing["volume"]:
                    best_by_product[product] = candidate
            rows = list(best_by_product.values())
            if not rows:
                raise ValueError("未识别到 TS/TF/T/TL 合约")
            order = {"TS": 0, "TF": 1, "T": 2, "TL": 3}
            rows.sort(key=lambda item: order[item["product"]])
            raw_date = _pick(frame.iloc[0], "tradedate", "日期", default="")
            raw_time = _pick(
                frame.iloc[0], "time", "ticktime", "时间", default=""
            )
            observation, inferred = self._intraday_observation_timestamp(
                "treasury_futures", raw_date, raw_time
            )
            warnings = (
                ["源未提供交易日，观测日期按最近已发生的交易时点推断。"]
                if inferred
                else []
            )
            return rows, observation, warnings

        return self._load(
            adapter="treasury_futures",
            label="国债期货",
            ttl_seconds=30,
            live_loader=live,
            demo_loader=demo_data.futures,
            source="AKShare / Sina Futures",
            source_url="https://akshare.akfamily.xyz/data/futures/futures.html",
            force=force,
        )

    def fx_pairs(self, force: bool = False) -> Dataset:
        names = {
            "AUD/USD": "澳元/美元",
            "EUR/JPY": "欧元/日元",
            "EUR/USD": "欧元/美元",
            "GBP/USD": "英镑/美元",
            "USD/CAD": "美元/加元",
            "USD/CHF": "美元/瑞郎",
            "USD/SEK": "美元/瑞典克朗",
            "USD/NOK": "美元/挪威克朗",
            "USD/DKK": "美元/丹麦克朗",
            "USD/HKD": "美元/港币",
            "USD/JPY": "美元/日元",
            "USD/SGD": "美元/新加坡元",
            "NZD/USD": "新西兰元/美元",
            "EUR/GBP": "欧元/英镑",
            "EUR/CHF": "欧元/瑞郎",
            "USD/CNH": "美元/离岸人民币",
        }

        def live() -> tuple[list[dict], None]:
            frame = self.ak.fx_pair_quote()
            if frame.empty:
                raise ValueError("银行间外币对报价为空")
            rows: list[dict[str, Any]] = []
            for _, row in frame.iterrows():
                pair = str(_pick(row, "货币对", default="")).strip().upper()
                code = re.sub(r"[^A-Z]", "", pair)
                bid = _number(_pick(row, "买报价"))
                ask = _number(_pick(row, "卖报价"))
                if len(code) != 6 or bid is None or ask is None:
                    continue
                pip_multiplier = 100 if code.endswith("JPY") else 10_000
                rows.append(
                    {
                        "code": code,
                        "pair": pair,
                        "name": names.get(pair, pair),
                        "bid": bid,
                        "ask": ask,
                        "mid": round((bid + ask) / 2, 6),
                        "spread_pips": round((ask - bid) * pip_multiplier, 3),
                        "change_pct": None,
                    }
                )
            if not rows:
                raise ValueError("银行间外币对报价没有有效记录")
            preferred = {
                "EURUSD": 0,
                "USDJPY": 1,
                "GBPUSD": 2,
                "AUDUSD": 3,
                "USDHKD": 4,
                "USDSGD": 5,
            }
            rows.sort(key=lambda item: (preferred.get(item["code"], 100), item["code"]))
            # The source describes the table as the latest current quote but
            # does not expose a trustworthy market timestamp.
            return rows, None

        return self._load(
            adapter="fx_pairs",
            label="全球外币对",
            ttl_seconds=120,
            live_loader=live,
            demo_loader=demo_data.fx_pairs,
            source="AKShare / Chinamoney FX",
            source_url="https://akshare.akfamily.xyz/data/fx/fx.html",
            force=force,
        )

    def fx_rmb_reference(self, force: bool = False) -> Dataset:
        specifications = (
            ("美元", "USDCNY", "美元/人民币", "USD", 1, 100),
            ("欧元", "EURCNY", "欧元/人民币", "EUR", 1, 100),
            ("日元", "JPYCNY", "日元/人民币", "JPY", 100, 1),
        )

        def live() -> tuple[list[dict], str, list[str]]:
            start = (date.today() - timedelta(days=45)).strftime("%Y%m%d")
            end = date.today().strftime("%Y%m%d")
            results: dict[str, dict[str, Any]] = {}
            missing: list[str] = []
            observations: list[str] = []

            def load_reference(
                specification: tuple[str, str, str, str, int, int],
            ) -> tuple[str, str, dict[str, Any]]:
                symbol, code, name, base, display_basis, divisor = specification
                frame = self.ak.currency_boc_sina(
                    symbol=symbol,
                    start_date=start,
                    end_date=end,
                )
                if frame.empty:
                    raise ValueError("空表")
                normalized: list[dict[str, Any]] = []
                for _, source_row in frame.iterrows():
                    observed = self._parse_source_date(
                        _pick(source_row, "日期", default="")
                    )
                    # Weekends may contain a BOC conversion rate but no PBOC
                    # central parity. Do not silently mix those definitions.
                    raw_mid = _number(_pick(source_row, "央行中间价"))
                    if observed is None or raw_mid is None:
                        continue
                    bid_value = _number(_pick(source_row, "中行汇买价"))
                    ask_value = _number(
                        _pick(source_row, "中行钞卖价/汇卖价")
                    )
                    normalized.append(
                        {
                            "date": observed.isoformat(),
                            "mid": round(raw_mid / divisor, 6),
                            "bid": (
                                round(bid_value / divisor, 6)
                                if bid_value is not None
                                else None
                            ),
                            "ask": (
                                round(ask_value / divisor, 6)
                                if ask_value is not None
                                else None
                            ),
                        }
                    )
                normalized.sort(key=lambda item: item["date"])
                if not normalized:
                    raise ValueError("没有有效央行中间价")
                current = normalized[-1]
                previous = normalized[-2] if len(normalized) > 1 else None
                return (
                    symbol,
                    code,
                    {
                        "code": code,
                        "name": name,
                        "base": base,
                        "quote": "CNY",
                        "display_basis": display_basis,
                        "mid": current["mid"],
                        "bid": current["bid"],
                        "ask": current["ask"],
                        "change_pct": (
                            round(
                                (current["mid"] / previous["mid"] - 1) * 100,
                                4,
                            )
                            if previous and previous["mid"]
                            else None
                        ),
                        "observation_date": current["date"],
                        "reference_type": "央行中间价",
                        "history": [
                            {"date": item["date"], "mid": item["mid"]}
                            for item in normalized[-31:]
                        ],
                    },
                )

            for specification in specifications:
                symbol = specification[0]
                try:
                    _symbol, code, row = load_reference(specification)
                except Exception:
                    missing.append(symbol)
                    continue
                results[code] = row
                observations.append(row["observation_date"])
            rows = [
                results[code]
                for _symbol, code, _name, _base, _basis, _divisor in specifications
                if code in results
            ]
            if not rows:
                raise ValueError("人民币汇率参考价全部不可用")
            warnings = (
                ["部分人民币参考币种暂不可用：" + "、".join(missing)]
                if missing
                else []
            )
            return rows, max(observations), warnings

        return self._load(
            adapter="fx_rmb_reference",
            label="人民币汇率参考",
            ttl_seconds=21_600,
            live_loader=live,
            demo_loader=demo_data.fx_rmb_reference,
            source="AKShare / BOC / Sina",
            source_url="https://akshare.akfamily.xyz/data/fx/fx.html",
            force=force,
        )

    def convertibles(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[dict], str | None, list[str]]:
            warnings: list[str] = []
            try:
                result = self._call_aux_worker(
                    "convertibles_comparison", timeout=8
                )
            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError):
                result = self._call_aux_worker("convertibles_spot", timeout=20)
                warnings.append(
                    "比价主源不可用，已切换新浪备用行情；溢价率、双低与 YTM 暂缺。"
                )
                rejected = _integer(result.get("rejected_rows"))
                if rejected:
                    warnings.append(f"备用行情已隔离 {rejected} 条零价或失效记录。")
            rows = result.get("rows", [])
            if not isinstance(rows, list) or not rows:
                raise ValueError("可转债数据源返回空结果")
            observation = result.get("observation_time")
            return (
                [item for item in rows if isinstance(item, dict)],
                str(observation) if observation else None,
                warnings,
            )

        return self._load(
            adapter="convertibles",
            label="可转债",
            ttl_seconds=120,
            live_loader=live,
            demo_loader=demo_data.convertibles,
            source="AKShare / Eastmoney / Sina fallback",
            source_url="https://akshare.akfamily.xyz/data/bond/bond.html",
            force=force,
        )

    def issuance_events(self, force: bool = False) -> Dataset:
        def live() -> tuple[list[dict], str]:
            start = date.today() - timedelta(days=7)
            end = date.today() + timedelta(days=45)
            frame = self.ak.bond_treasure_issue_cninfo(
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            rows: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for _, row in frame.head(100).iterrows():
                event_date = _pick(
                    row,
                    "发行起始日",
                    "公告日期",
                    default=date.today().isoformat(),
                )
                title = str(
                    _pick(row, "债券名称", "债券简称", default="国债发行")
                )
                key = (str(event_date), title)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "date": key[0],
                        "type": "国债发行",
                        "title": title,
                        "importance": "high",
                    }
                )
            return rows, date.today().isoformat()

        return self._load(
            adapter="issuance_events",
            label="发行事件",
            ttl_seconds=21_600,
            live_loader=live,
            demo_loader=demo_data.events,
            source="AKShare / CNInfo",
            source_url="https://akshare.akfamily.xyz/data/bond/bond.html",
            force=force,
        )

    def health_items(self) -> list[HealthItem]:
        for adapter, label in self.ADAPTERS:
            with self._health_lock:
                known = adapter in self.health
            if known:
                continue
            cached = self._cached_dataset(adapter, allow_stale=True)
            if isinstance(cached, Dataset):
                entry = self.cache.entry(adapter)
                self._restore_cached_dataset(
                    adapter,
                    label,
                    cached,
                    time.perf_counter(),
                    stale=bool(entry and not entry.fresh),
                    emit=False,
                )
        with self._health_lock:
            items = [
                self.health.get(
                    adapter,
                    HealthItem(
                        adapter=adapter,
                        label=label,
                        state="not_checked",
                        message=(
                            "已有持久缓存，尚未检查实时数据"
                            if self.cache.is_persisted(adapter)
                            else "尚未请求"
                        ),
                        quality_score=0,
                    ),
                )
                for adapter, label in self.ADAPTERS
            ]
        results: list[HealthItem] = []
        for item in items:
            result = item.model_copy(deep=True)
            market_status, market_label = self._market_status(item.adapter)
            result.market_status = market_status
            result.market_status_label = market_label
            result.cache_age_seconds = self.cache.age_seconds(item.adapter)
            result.cache_persisted = self.cache.is_persisted(item.adapter)
            result.execution_mode = (
                "local_demo" if self.demo_only else "isolated_process"
            )
            result.circuit_state, result.next_retry_at = self._circuit_status(
                item.adapter
            )
            entry = self.cache.entry(item.adapter)
            if entry is not None:
                expected_ttl = self._effective_ttl(
                    item.adapter,
                    self.BASE_TTLS.get(item.adapter, entry.ttl_seconds),
                )
                remaining = max(0, expected_ttl - entry.age_seconds)
                result.next_refresh_at = (
                    result.next_retry_at
                    if result.circuit_state == "open" and result.next_retry_at
                    else datetime.now() + timedelta(seconds=remaining)
                )
            elif result.circuit_state == "open":
                result.next_refresh_at = result.next_retry_at
            with self._refresh_lock:
                result.refreshing = item.adapter in self._refreshing
            results.append(result)
        return results

    def _adapter_methods(self) -> dict[str, Callable[[bool], Dataset]]:
        return {
            "trade_calendar": self.trade_calendar,
            "money_rates": self.money_rates,
            "money_fr": self.money_fr,
            "money_fdr": self.money_fdr,
            "money_lpr": self.money_lpr,
            "yield_curves": self.yield_curves,
            "spot_bonds": self.spot_bonds,
            "treasury_futures": self.treasury_futures,
            "fx_pairs": self.fx_pairs,
            "fx_rmb_reference": self.fx_rmb_reference,
            "convertibles": self.convertibles,
            "issuance_events": self.issuance_events,
        }

    def prewarm(self) -> None:
        if self.demo_only or self.is_source_worker:
            return
        if self._prewarm_thread and self._prewarm_thread.is_alive():
            return
        methods = self._adapter_methods()

        def prewarm_adapter(adapter: str) -> None:
            with self._refresh_lock:
                if adapter in self._refreshing:
                    return
                self._refreshing.add(adapter)
            try:
                methods[adapter](False)
            finally:
                with self._refresh_lock:
                    self._refreshing.discard(adapter)

        def run() -> None:
            # Two-source waves match the process concurrency limit, so a slow
            # optional endpoint cannot leave core adapters expiring in a long
            # queue during laptop startup.
            batches = (
                ("trade_calendar", "money_rates"),
                ("yield_curves", "treasury_futures"),
                ("spot_bonds", "convertibles"),
                ("fx_pairs", "fx_rmb_reference"),
                ("money_fr", "money_fdr"),
                ("money_lpr", "issuance_events"),
            )
            for batch in batches:
                workers = [
                    Thread(
                        target=prewarm_adapter,
                        args=(adapter,),
                        daemon=True,
                        name=f"akdesk-prewarm-{adapter}",
                    )
                    for adapter in batch
                ]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join()

        self._prewarm_thread = Thread(
            target=run,
            daemon=True,
            name="akdesk-prewarm-coordinator",
        )
        self._prewarm_thread.start()

    def start_scheduler(self) -> None:
        if self.demo_only or self.is_source_worker:
            return
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_stop.clear()
        self._ensure_refresh_workers()

        def run() -> None:
            methods = self._adapter_methods()
            while not self._scheduler_stop.wait(15):
                if self._prewarm_thread and self._prewarm_thread.is_alive():
                    continue
                for adapter, method in methods.items():
                    if self._circuit_status(adapter)[0] == "open":
                        continue
                    entry = self.cache.entry(adapter)
                    expected_ttl = self._effective_ttl(
                        adapter, self.BASE_TTLS[adapter]
                    )
                    needs_refresh = (
                        entry is None
                        or not entry.fresh
                        or entry.age_seconds >= expected_ttl
                    )
                    if needs_refresh:
                        self._background_refresh(
                            adapter,
                            lambda method=method: method(True),
                            priority=10,
                        )

        self._scheduler_thread = Thread(
            target=run,
            daemon=True,
            name="akdesk-refresh-scheduler",
        )
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
        while True:
            try:
                _priority, _sequence, adapter, _loader = (
                    self._refresh_queue.get_nowait()
                )
            except Empty:
                break
            with self._refresh_lock:
                self._refreshing.discard(adapter)
            self._refresh_queue.task_done()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=1)
        with self._refresh_workers_lock:
            workers = list(self._refresh_workers)
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=0.2)

    def source_activity(self) -> dict[str, Any]:
        with self._refresh_lock:
            refreshing = sorted(self._refreshing)
        return {
            **self._source_runner.stats(),
            "refreshing": refreshing,
            "execution_mode": (
                "local_demo" if self.demo_only else "isolated_process"
            ),
            "scheduler_running": bool(
                self._scheduler_thread and self._scheduler_thread.is_alive()
            ),
            "prewarm_running": bool(
                self._prewarm_thread and self._prewarm_thread.is_alive()
            ),
            "refresh_queue_depth": self._refresh_queue.qsize(),
            "circuits": {
                adapter: state
                for adapter, _label in self.ADAPTERS
                if (state := self._circuit_status(adapter)[0]) != "closed"
            },
            "event_errors": dict(self._event_errors),
        }

    def refresh_adapter(self, adapter: str) -> Dataset:
        methods = self._adapter_methods()
        if adapter not in methods:
            raise KeyError(adapter)
        self._reset_circuit(adapter)
        return methods[adapter](True)

    def request_refresh(self, adapter: str, *, priority: int = 0) -> bool:
        methods = self._adapter_methods()
        if adapter not in methods:
            raise KeyError(adapter)
        method = methods[adapter]
        return self._background_refresh(
            adapter,
            lambda: method(True),
            priority=priority,
        )

    def clear_cache(self) -> None:
        self.cache.clear()
        with self._health_lock:
            self.health.clear()
        with self._event_lock:
            self._emitted_cache_versions.clear()
        self._event_errors.clear()

    def cache_stats(self) -> dict[str, int]:
        return self.cache.stats()
