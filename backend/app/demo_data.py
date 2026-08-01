from __future__ import annotations

from datetime import date, datetime, timedelta


def money_rates() -> list[dict]:
    return [
        {"name": "Shibor O/N", "tenor": "O/N", "value": 1.425, "change_bp": -2.1},
        {"name": "Shibor 1W", "tenor": "1W", "value": 1.617, "change_bp": 1.2},
        {"name": "FR007", "tenor": "7D", "value": 1.760, "change_bp": 3.0},
        {"name": "FDR007", "tenor": "7D", "value": 1.690, "change_bp": 1.4},
        {"name": "LPR 1Y", "tenor": "1Y", "value": 3.000, "change_bp": 0.0},
        {"name": "LPR 5Y", "tenor": "5Y", "value": 3.500, "change_bp": 0.0},
    ]


def yield_curves() -> dict:
    tenors = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "30Y"]
    today = [1.32, 1.36, 1.40, 1.48, 1.55, 1.64, 1.72, 1.80, 1.98]
    previous = [1.34, 1.37, 1.42, 1.49, 1.56, 1.66, 1.73, 1.82, 1.97]
    policy = [1.42, 1.48, 1.55, 1.62, 1.69, 1.78, 1.86, 1.94, 2.14]
    observations = [
        (date.today() - timedelta(days=1)).isoformat(),
        date.today().isoformat(),
    ]
    history_values = [previous, today]
    return {
        "tenors": tenors,
        "series": [
            {"name": "中债国债·最新", "values": today},
            {"name": "中债国债·前值", "values": previous},
            {"name": "国开债·最新", "values": policy},
        ],
        "changes": [
            round((current - old) * 100, 2)
            for current, old in zip(today, previous, strict=True)
        ],
        "history": [
            {
                "date": observed,
                "values": dict(zip(tenors, values, strict=True)),
                "spreads_bp": {
                    "10Y-1Y": round((values[7] - values[2]) * 100, 2),
                    "10Y-5Y": round((values[7] - values[5]) * 100, 2),
                    "30Y-10Y": round((values[8] - values[7]) * 100, 2),
                },
            }
            for observed, values in zip(observations, history_values, strict=True)
        ],
    }


def spot_bonds() -> list[dict]:
    return [
        {"code": "240011", "name": "24附息国债11", "type": "国债", "yield": 1.806, "change_bp": -1.8, "price": 102.31, "volume": 38.6},
        {"code": "240210", "name": "24国开10", "type": "政策金融债", "yield": 1.934, "change_bp": -1.2, "price": 103.08, "volume": 31.2},
        {"code": "250004", "name": "25附息国债04", "type": "国债", "yield": 1.665, "change_bp": 0.6, "price": 100.94, "volume": 26.9},
        {"code": "250305", "name": "25进出05", "type": "政策金融债", "yield": 1.887, "change_bp": 1.1, "price": 101.26, "volume": 19.4},
        {"code": "112599001", "name": "25示例CD001", "type": "同业存单", "yield": 1.712, "change_bp": 2.3, "price": 99.73, "volume": 12.8},
    ]


def futures() -> list[dict]:
    return [
        {"product": "TS", "contract": "TS主力", "price": 102.218, "change_pct": 0.03, "volume": 32510, "open_interest": 68720},
        {"product": "TF", "contract": "TF主力", "price": 105.480, "change_pct": 0.08, "volume": 52640, "open_interest": 112390},
        {"product": "T", "contract": "T主力", "price": 108.055, "change_pct": 0.12, "volume": 78130, "open_interest": 186420},
        {"product": "TL", "contract": "TL主力", "price": 118.920, "change_pct": -0.05, "volume": 49380, "open_interest": 97240},
    ]


def fx_pairs() -> list[dict]:
    return [
        {
            "code": "EURUSD",
            "pair": "EUR/USD",
            "name": "欧元/美元",
            "bid": 1.14364,
            "ask": 1.14365,
            "mid": 1.143645,
            "spread_pips": 0.1,
            "change_pct": None,
        },
        {
            "code": "USDJPY",
            "pair": "USD/JPY",
            "name": "美元/日元",
            "bid": 162.495,
            "ask": 162.496,
            "mid": 162.4955,
            "spread_pips": 0.1,
            "change_pct": None,
        },
        {
            "code": "GBPUSD",
            "pair": "GBP/USD",
            "name": "英镑/美元",
            "bid": 1.34680,
            "ask": 1.34682,
            "mid": 1.34681,
            "spread_pips": 0.2,
            "change_pct": None,
        },
        {
            "code": "AUDUSD",
            "pair": "AUD/USD",
            "name": "澳元/美元",
            "bid": 0.69935,
            "ask": 0.69935,
            "mid": 0.69935,
            "spread_pips": 0.0,
            "change_pct": None,
        },
        {
            "code": "USDHKD",
            "pair": "USD/HKD",
            "name": "美元/港币",
            "bid": 7.83999,
            "ask": 7.84006,
            "mid": 7.840025,
            "spread_pips": 0.7,
            "change_pct": None,
        },
    ]


def fx_rmb_reference() -> list[dict]:
    current = date.today()
    history_dates = [
        (current - timedelta(days=offset)).isoformat()
        for offset in range(12, -1, -1)
        if (current - timedelta(days=offset)).weekday() < 5
    ]
    specifications = (
        ("USDCNY", "美元/人民币", "USD", 1, 6.7909),
        ("EURCNY", "欧元/人民币", "EUR", 1, 7.7690),
        ("JPYCNY", "日元/人民币", "JPY", 100, 4.1815),
    )
    rows: list[dict] = []
    for index, (code, name, base, basis, value) in enumerate(specifications):
        history = [
            {
                "date": observed,
                "mid": round(value * (1 + (position - len(history_dates)) * 0.0008 + index * 0.0001), 6),
            }
            for position, observed in enumerate(history_dates)
        ]
        latest = history[-1]["mid"]
        previous = history[-2]["mid"] if len(history) > 1 else None
        rows.append(
            {
                "code": code,
                "name": name,
                "base": base,
                "quote": "CNY",
                "display_basis": basis,
                "mid": latest,
                "bid": round(latest * 0.997, 6),
                "ask": round(latest * 1.001, 6),
                "change_pct": (
                    round((latest / previous - 1) * 100, 4)
                    if previous
                    else None
                ),
                "observation_date": history_dates[-1],
                "reference_type": "央行中间价",
                "history": history,
            }
        )
    return rows


def convertibles() -> list[dict]:
    return [
        {"code": "113000", "name": "示例转债A", "price": 118.42, "change_pct": 0.86, "stock_name": "示例正股A", "convert_value": 105.31, "premium_pct": 12.45, "double_low": 130.87, "ytm_pct": -1.12, "redeem_status": "正常"},
        {"code": "123000", "name": "示例转债B", "price": 108.76, "change_pct": -0.32, "stock_name": "示例正股B", "convert_value": 99.82, "premium_pct": 8.96, "double_low": 117.72, "ytm_pct": 1.04, "redeem_status": "正常"},
        {"code": "110000", "name": "示例转债C", "price": 132.18, "change_pct": 1.42, "stock_name": "示例正股C", "convert_value": 122.67, "premium_pct": 7.75, "double_low": 139.93, "ytm_pct": -3.26, "redeem_status": "关注强赎"},
        {"code": "127000", "name": "示例转债D", "price": 101.44, "change_pct": 0.05, "stock_name": "示例正股D", "convert_value": 82.36, "premium_pct": 23.17, "double_low": 124.61, "ytm_pct": 2.41, "redeem_status": "正常"},
    ]


def events() -> list[dict]:
    today = date.today()
    return [
        {"date": today.isoformat(), "type": "国债发行", "title": "记账式附息国债招标", "importance": "high"},
        {"date": (today + timedelta(days=1)).isoformat(), "type": "数据发布", "title": "中国关键宏观数据日程", "importance": "medium"},
        {"date": (today + timedelta(days=2)).isoformat(), "type": "可转债", "title": "示例转债上市提醒", "importance": "low"},
    ]


def observation_time() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def trade_calendar() -> list[str]:
    start = date.today() - timedelta(days=370)
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(740)
        if (start + timedelta(days=offset)).weekday() < 5
    ]
