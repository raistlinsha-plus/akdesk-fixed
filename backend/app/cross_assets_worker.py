"""Disposable AKShare worker, no keychain/database access."""
from __future__ import annotations

import json
import sys

from .cross_assets import ASSETS, MARKER
from .provider import is_rate_limit_error


def main() -> None:
    import akshare as ak

    mode, key = sys.argv[1:]
    try:
        if mode == "quote" and key == "index":
            frame = ak.stock_zh_index_spot_sina()
            symbols = {item["symbol"] for item in ASSETS.values() if item["kind"] == "index"}
            frame = frame[frame["代码"].isin(symbols)]
        elif mode == "quote" and key == "gold":
            frame = ak.spot_quotations_sge(symbol="Au99.99").tail(1)
        elif mode == "history" and key in ASSETS:
            spec = ASSETS[key]
            frame = ak.spot_hist_sge(symbol=spec["symbol"]) if spec["kind"] == "gold" else ak.stock_zh_index_daily(symbol=spec["symbol"])
        else:
            raise ValueError("unsupported request")
        records = json.loads(frame.to_json(orient="records", date_format="iso"))
        payload = {"ok": True, "records": records}
    except Exception as exc:
        payload = {"ok": False, "rate_limited": is_rate_limit_error(exc)}
    print(MARKER + json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
