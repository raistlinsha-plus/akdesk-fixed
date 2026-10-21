"""Build a shareable report from allowlisted runtime metadata only."""

from __future__ import annotations

import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import __version__
from .models import HealthItem

_ADAPTERS = {
    "trade_calendar",
    "money_rates",
    "money_fr",
    "money_fdr",
    "money_lpr",
    "yield_curves",
    "spot_bonds",
    "treasury_futures",
    "fx_pairs",
    "fx_rmb_reference",
    "convertibles",
    "issuance_events",
    "fred_macro",
    "world_bank",
    "gdelt_events",
}


def error_category(message: str | None, state: str = "unavailable") -> str:
    """Classify locally; never return any fragment of the original error."""
    if state in {"healthy", "not_checked"}:
        return "none"
    text = (message or "").lower()
    categories = (
        ("certificate", ("certificate", "ssl", "证书", "tls")),
        ("rate_limit", ("429", "rate limit", "too many requests", "限流")),
        ("credentials", ("401", "403", "unauthorized", "api key", "凭据")),
        ("timeout", ("timeout", "timed out", "超时")),
        ("network", ("connection", "network", "dns", "resolve", "连接", "网络")),
        ("source_format", ("keyerror", "列名", "字段", "空表", "没有有效", "解析")),
        ("source_process", ("process", "worker", "进程", "崩溃")),
    )
    for category, markers in categories:
        if any(marker in text for marker in markers):
            return category
    return "upstream_unavailable" if state == "unavailable" else "unknown"


def storage_summary(data_dir: Path, project_root: Path) -> dict[str, object]:
    """Describe the directory without exposing a username or absolute path."""
    target = data_dir.expanduser().resolve()
    if os.getenv("AKDESK_DATA_DIR"):
        kind = "custom"
    elif target == (project_root / "data").resolve():
        kind = "legacy_project"
    elif target == (Path.home() / "Library/Application Support/AKDesk Fixed").resolve():
        kind = "macos_application_support"
    elif target == (Path.home() / ".local/share/akdesk-fixed").resolve():
        kind = "user_application_data"
    else:
        kind = "custom"
    ancestor = target
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return {
        "type": kind,
        "exists": target.is_dir(),
        "writable": ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK),
    }


def build_diagnostics(
    health_items: Iterable[HealthItem],
    *,
    data_dir: Path,
    project_root: Path,
    demo_only: bool,
) -> dict[str, object]:
    """No fetching, Keychain access, research queries or free-text passthrough."""
    os_name = platform.system()
    os_version = platform.mac_ver()[0] if os_name == "Darwin" else platform.release()
    # OS version and machine can be arbitrary strings on unusual hosts.
    safe_version = (
        os_version if re.fullmatch(r"[0-9][0-9.]{0,30}", os_version) else "unknown"
    )
    machine = platform.machine().lower()
    adapters = []
    for item in health_items:
        # Adapter identifiers are code-owned; reject unexpected free-form values.
        adapter = item.adapter if item.adapter in _ADAPTERS else "unknown"
        # A model default is not evidence that a source has been checked. Keep
        # this calibration local to the shareable report, not service health.
        trust_level = (
            "unavailable" if item.state == "not_checked" else item.trust_level
        )
        intentional_demo = (
            demo_only
            and item.execution_mode == "local_demo"
            and item.state == "degraded"
            and item.message == "演示模式"
        )
        adapters.append(
            {
                "adapter": adapter,
                "state": item.state,
                "research_status": item.research_status,
                "trust_level": trust_level,
                "market_status": item.market_status,
                "circuit_state": item.circuit_state,
                "cache_age_seconds": (
                    max(0, item.cache_age_seconds)
                    if item.cache_age_seconds is not None
                    else None
                ),
                "cache_persisted": item.cache_persisted,
                "refreshing": item.refreshing,
                "consecutive_failures": max(0, item.consecutive_failures),
                "error_category": (
                    "demo_mode"
                    if intentional_demo
                    else error_category(item.message, item.state)
                ),
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": "AKDesk Fixed",
            "version": __version__,
            "mode": "demo" if demo_only else "live",
        },
        "environment": {
            "os": "macOS"
            if os_name == "Darwin"
            else os_name
            if os_name in {"Linux", "Windows"}
            else "unknown",
            "os_version": safe_version,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "architecture": machine
            if machine in {"arm64", "aarch64", "x86_64", "amd64", "i386"}
            else "unknown",
        },
        "storage": storage_summary(data_dir, project_root),
        "adapters": adapters,
        "privacy": {
            "credentials_included": False,
            "absolute_paths_included": False,
            "raw_errors_included": False,
            "research_content_included": False,
            "automatic_upload": False,
        },
    }
