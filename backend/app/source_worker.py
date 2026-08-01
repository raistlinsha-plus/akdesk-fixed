from __future__ import annotations

import json
import os
import sys

from .provider import DataService, SOURCE_RESULT_MARKER


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.source_worker <adapter>")

    adapter = sys.argv[1]
    os.environ["AKDESK_SOURCE_WORKER"] = "1"
    os.environ["AKDESK_DEMO"] = "0"
    os.environ["AKDESK_NOTIFICATIONS"] = "0"
    service = DataService()

    try:
        dataset = service.refresh_adapter(adapter)
        if dataset.meta.demo:
            error = dataset.meta.warnings[0] if dataset.meta.warnings else "数据源不可用"
            payload = {"ok": False, "error": error}
        else:
            payload = {
                "ok": True,
                "data": dataset.data,
                "observation_time": dataset.meta.observation_time,
                "warnings": dataset.meta.warnings,
            }
    except Exception as exc:
        payload = {"ok": False, "error": DataService._safe_message(exc)}

    print(SOURCE_RESULT_MARKER + json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
