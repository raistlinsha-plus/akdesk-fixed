import sys
from types import SimpleNamespace

import pandas as pd

from app.aux_worker import convertibles_spot


def test_convertible_fallback_filters_invalid_rows_and_keeps_date_unknown(
    monkeypatch,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "code": "810011",
                "name": "无效转债",
                "trade": 100,
                "ticktime": "15:00:00",
            },
            {
                "code": "113001",
                "name": "零价转债",
                "trade": 0,
                "ticktime": "15:00:00",
            },
            {
                "code": "113002",
                "name": "有效转债",
                "trade": 112.5,
                "changepercent": 0.3,
                "ticktime": "15:00:00",
            },
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(bond_zh_hs_cov_spot=lambda: frame),
    )

    result = convertibles_spot()

    assert [item["code"] for item in result["rows"]] == ["113002"]
    assert result["rows"][0]["data_tier"] == "price_only"
    assert result["observation_time"] is None
    assert result["rejected_rows"] == 2
