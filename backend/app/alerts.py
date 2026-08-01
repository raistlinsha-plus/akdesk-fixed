from __future__ import annotations

import math
import os
import platform
import subprocess
from datetime import datetime, timedelta
from threading import RLock
from typing import Callable

from .database import Database
from .models import AlertCreate, AlertTriggerItem, Dataset


_ADAPTER_TYPES = {
    "spot_bonds": "bond",
    "treasury_futures": "future",
    "convertibles": "convertible",
}

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">": lambda value, threshold: value > threshold,
    ">=": lambda value, threshold: value >= threshold,
    "<": lambda value, threshold: value < threshold,
    "<=": lambda value, threshold: value <= threshold,
}


class AlertEngine:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._lock = RLock()

    def evaluate(self, adapter: str, dataset: Dataset) -> list[AlertTriggerItem]:
        object_type = _ADAPTER_TYPES.get(adapter)
        if (
            object_type is None
            or dataset.meta.demo
            or dataset.meta.stale
            or dataset.meta.trust_level in {"partial", "unavailable"}
        ):
            return []
        if not isinstance(dataset.data, list):
            return []

        alerts = self.database.enabled_alerts(object_type)
        if not alerts:
            return []

        triggered: list[AlertTriggerItem] = []
        now = datetime.now()
        with self._lock:
            for alert in alerts:
                item = self._find_item(dataset.data, object_type, alert.object_id)
                if item is None:
                    continue
                raw_value = item.get(alert.metric)
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value):
                    continue
                comparator = _OPERATORS[alert.operator]
                matched = comparator(value, alert.threshold)
                previously_matched = self.database.alert_last_matched(alert.id)
                if not matched:
                    self.database.set_alert_state(alert.id, False, value)
                    continue
                # Trigger on the first match or when the condition crosses
                # from false to true; a continuously true condition stays quiet.
                if previously_matched is True:
                    self.database.set_alert_state(alert.id, True, value)
                    continue
                if self._is_quiet_time(now, alert.quiet_start, alert.quiet_end):
                    continue
                if (
                    self.database.daily_trigger_count(alert.id, now.date())
                    >= alert.max_triggers_per_day
                ):
                    continue
                last_trigger = self.database.latest_trigger_at(alert.id)
                if last_trigger and now - last_trigger < timedelta(
                    minutes=alert.cooldown_minutes
                ):
                    continue
                self.database.set_alert_state(alert.id, True, value)
                record = self.database.add_alert_trigger(
                    alert,
                    trigger_value=value,
                    source=dataset.meta.source,
                    observation_time=dataset.meta.observation_time,
                )
                triggered.append(record)
                self._notify(record)
        return triggered

    def preview(
        self,
        adapter: str,
        dataset: Dataset | None,
        rule: AlertCreate,
    ) -> dict[str, object]:
        if dataset is None:
            return {
                "available": False,
                "matched": False,
                "value": None,
                "message": "当前没有可用行情",
            }
        if dataset.meta.demo or dataset.meta.stale or dataset.meta.trust_level in {
            "partial",
            "unavailable",
        }:
            return {
                "available": False,
                "matched": False,
                "value": None,
                "message": "当前数据不是可触发提醒的可信行情",
                "trust_level": dataset.meta.trust_level,
            }
        if not isinstance(dataset.data, list):
            return {
                "available": False,
                "matched": False,
                "value": None,
                "message": "当前行情格式不支持提醒试算",
            }
        item = self._find_item(dataset.data, rule.object_type, rule.object_id)
        if item is None:
            return {
                "available": False,
                "matched": False,
                "value": None,
                "message": "当前行情中未找到该标的或记录已被隔离",
            }
        try:
            value = float(item.get(rule.metric))
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value):
            return {
                "available": False,
                "matched": False,
                "value": None,
                "message": "该指标当前没有有效数值",
            }
        matched = _OPERATORS[rule.operator](value, rule.threshold)
        return {
            "available": True,
            "matched": matched,
            "value": value,
            "message": "当前条件满足" if matched else "当前条件未满足",
            "observation_time": dataset.meta.observation_time,
            "source": dataset.meta.source,
        }

    @staticmethod
    def _is_quiet_time(
        now: datetime,
        quiet_start: str | None,
        quiet_end: str | None,
    ) -> bool:
        if not quiet_start or not quiet_end:
            return False
        current = now.strftime("%H:%M")
        if quiet_start < quiet_end:
            return quiet_start <= current < quiet_end
        return current >= quiet_start or current < quiet_end

    @staticmethod
    def _find_item(
        data: list[object], object_type: str, object_id: str
    ) -> dict | None:
        identifiers = {
            "bond": ("code",),
            "convertible": ("code",),
            "future": ("product", "contract"),
        }[object_type]
        for raw in data:
            if not isinstance(raw, dict):
                continue
            if raw.get("quality_state") == "suspicious":
                continue
            if any(str(raw.get(key, "")) == object_id for key in identifiers):
                return raw
        return None

    @staticmethod
    def _notify(trigger: AlertTriggerItem) -> None:
        if os.getenv("AKDESK_NOTIFICATIONS", "1") != "1":
            return
        if platform.system() != "Darwin":
            return
        script = (
            "on run argv\n"
            "display notification (item 1 of argv) with title (item 2 of argv)\n"
            "end run"
        )
        body = (
            f"{trigger.name}：{trigger.metric} {trigger.trigger_value:g} "
            f"{trigger.operator} {trigger.threshold:g}"
        )
        try:
            subprocess.run(
                ["osascript", "-e", script, body, "AKDesk Fixed 提醒"],
                check=False,
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return
