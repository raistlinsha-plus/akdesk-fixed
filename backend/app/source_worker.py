from __future__ import annotations

import json
import os
import sys

from .provider import (
    DataService,
    PUSH2_SOURCE,
    SOURCE_RESULT_MARKER,
    source_error_payload,
)


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
            error_type = service.source_error_type(adapter)
            payload = {
                "ok": False,
                "error": error,
                "error_type": error_type,
                "rate_limited": error_type == "rate_limit",
            }
            if adapter == "convertibles" and service.upstream_cooldowns():
                payload["upstream_source"] = PUSH2_SOURCE
        else:
            payload = {
                "ok": True,
                "data": dataset.data,
                "observation_time": dataset.meta.observation_time,
                "warnings": dataset.meta.warnings,
                "source": dataset.meta.source,
                "source_url": dataset.meta.source_url,
            }
    except Exception as exc:
        payload = {"ok": False, **source_error_payload(exc)}

    cooldowns = service.upstream_cooldowns()
    if cooldowns:
        payload["upstream_cooldowns"] = cooldowns

    print(SOURCE_RESULT_MARKER + json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
