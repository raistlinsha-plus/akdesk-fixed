from __future__ import annotations

import os
import resource
import threading
import time
from pathlib import Path
from typing import Any


_STARTED_AT = time.monotonic()


def _open_file_descriptor_count() -> int | None:
    """Return a cheap process FD count on macOS/Linux when available."""
    for directory in (Path("/proc/self/fd"), Path("/dev/fd")):
        try:
            if directory.is_dir():
                return len(os.listdir(directory))
        except OSError:
            continue
    return None


def _finite_limit(value: int) -> int | None:
    if value == resource.RLIM_INFINITY or value < 0:
        return None
    return int(value)


def runtime_diagnostics() -> dict[str, Any]:
    open_count = _open_file_descriptor_count()
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    soft_limit = _finite_limit(soft)
    hard_limit = _finite_limit(hard)
    utilization = None
    if open_count is not None and soft_limit:
        utilization = round(open_count / soft_limit * 100, 1)
    return {
        "process_id": os.getpid(),
        "uptime_seconds": max(0, round(time.monotonic() - _STARTED_AT)),
        "threads": threading.active_count(),
        "file_descriptors": {
            "open": open_count,
            "soft_limit": soft_limit,
            "hard_limit": hard_limit,
            "utilization_percent": utilization,
        },
    }
