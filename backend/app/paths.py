from __future__ import annotations

import os
import sys
from hashlib import sha256
from pathlib import Path


def default_data_dir(project_root: Path) -> Path:
    """Resolve a stable user data home while preserving legacy local installs."""
    configured = os.getenv("AKDESK_DATA_DIR")
    if configured:
        return (project_root / Path(configured).expanduser()).resolve()

    home = Path.home()
    if os.getenv("AKDESK_DEMO") == "1":
        return (
            home / "Library" / "Application Support" / "AKDesk Fixed Demo"
            if sys.platform == "darwin"
            else home / ".local" / "share" / "akdesk-fixed-demo"
        ).resolve()

    legacy = project_root / "data"
    legacy_markers = (
        legacy / "akdesk-fixed.db",
        legacy / "market-cache.db",
        legacy / "backups",
    )
    if any(path.exists() for path in legacy_markers):
        return legacy.resolve()

    if sys.platform == "darwin":
        return (home / "Library" / "Application Support" / "AKDesk Fixed").resolve()
    return (home / ".local" / "share" / "akdesk-fixed").resolve()


def path_id(path: Path) -> str:
    return sha256(os.fsencode(path.resolve())).hexdigest()


def launch_port() -> int:
    value = os.getenv("AKDESK_PORT", "8765")
    if not value.isascii() or not value.isdecimal() or len(value) > 5:
        raise ValueError("AKDESK_PORT 必须是 1–65535 的端口号")
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("AKDESK_PORT 必须是 1–65535 的端口号")
    return port
