from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir(project_root: Path) -> Path:
    """Resolve a stable user data home while preserving legacy local installs."""
    configured = os.getenv("AKDESK_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    legacy = project_root / "data"
    legacy_markers = (
        legacy / "akdesk-fixed.db",
        legacy / "market-cache.db",
        legacy / "backups",
    )
    if any(path.exists() for path in legacy_markers):
        return legacy

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "AKDesk Fixed"
    return home / ".local" / "share" / "akdesk-fixed"
