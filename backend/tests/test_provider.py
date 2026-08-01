import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.models import Dataset, HealthItem, SourceMeta
from app.provider import (
    AUX_RESULT_MARKER,
    DataService,
    SOURCE_RESULT_MARKER,
    SourceTimeoutError,
)


def test_demo_mode_never_calls_network(monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_DEMO", "1")
    service = DataService()

    rates = service.money_rates()
    curves = service.yield_curves()

    assert rates.meta.demo is True
    assert rates.meta.stale is True
    assert len(rates.data) >= 4
    assert curves.data["tenors"]
    health = {item.adapter: item for item in service.health_items()}
    assert health["money_rates"].state == "degraded"
    assert health["money_rates"].observation_time is None
    assert health["money_rates"].research_status == "blocked"


class _PartialRatesAk:
    @staticmethod
    def macro_china_shibor_all():
        return pd.DataFrame(
            [
                {"日期": "2026-07-10", "O/N-定价": 1.35, "1W-定价": 1.55},
                {"日期": "2026-07-13", "O/N-定价": 1.37, "1W-定价": 1.56},
            ]
        )

    @staticmethod
    def repo_rate_query(*, symbol: str):
        raise RuntimeError(symbol + " unavailable")

    @staticmethod
    def macro_china_lpr():
        raise RuntimeError("LPR unavailable")


class _FuturesAk:
    @staticmethod
    def futures_zh_spot(**_kwargs):
        return pd.DataFrame(
            [
                {
                    "symbol": "2年期国债期货2609",
                    "time": "15:15:00",
                    "current_price": 102.632,
                    "hold": 91670,
                    "volume": 46366,
                },
                {
                    "symbol": "5年期国债期货2609",
                    "time": "15:15:00",
                    "current_price": 106.42,
                    "hold": 230531,
                    "volume": 67710,
                },
                {
                    "symbol": "10年期国债期货2609",
                    "time": "15:15:00",
                    "current_price": 109.16,
                    "hold": 384643,
                    "volume": 69344,
                },
                {
                    "symbol": "30年期国债期货2609",
                    "time": "15:15:00",
                    "current_price": 113.66,
                    "hold": 178937,
                    "volume": 84489,
                },
            ]
        )


class _SpotAk:
    @staticmethod
    def bond_spot_deal():
        return pd.DataFrame(
            [
                {
                    "债券代码": "240011",
                    "债券简称": "24附息国债11",
                    "债券类型": "国债",
                    "最新收益率": 1.8,
                    "涨跌": -1.2,
                    "成交净价": 102.3,
                    "交易量": 20,
                }
            ]
        )


def test_money_rates_keeps_core_data_when_optional_sources_fail(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.setenv("AKDESK_ENABLE_EXTENDED_RATES", "0")
    service = DataService()
    service._ak = _PartialRatesAk()

    result = service.money_rates()

    assert result.meta.demo is False
    assert [item["name"] for item in result.data] == ["Shibor O/N", "Shibor 1W"]
    assert result.meta.warnings == []


def test_futures_recognizes_current_chinese_symbol_schema(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    service = DataService()
    service._ak = _FuturesAk()

    result = service.treasury_futures()

    assert [item["product"] for item in result.data] == ["TS", "TF", "T", "TL"]
    assert result.data[0]["contract"] == "TS2609"
    assert result.data[-1]["contract"] == "TL2609"


def test_source_processes_use_bounded_concurrency(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_CONCURRENCY", "2")
    service = DataService()
    active = 0
    maximum_active = 0
    lock = Lock()

    def fake_run(*args, **_kwargs):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        payload = {
            "ok": True,
            "data": [{"value": 1}],
            "observation_time": "2026-07-13",
            "warnings": [],
        }
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=SOURCE_RESULT_MARKER + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(
            pool.map(
                lambda _value: service._call_with_timeout(
                    "fake_adapter", lambda: ([], None)
                ),
                range(5),
            )
        )

    assert maximum_active == 2
    assert len(results) == 5


def test_spot_bonds_do_not_fake_observation_time(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    service = DataService()
    service._ak = _SpotAk()

    result = service.spot_bonds()

    assert result.meta.observation_time is None
    assert result.meta.fetched_at is not None


def test_spot_bonds_conservatively_recover_standard_short_codes() -> None:
    service = DataService()
    dataset = Dataset(
        data=[
            {"code": "", "name": "24附息国债11", "type": "国债"},
            {"code": "", "name": "25国开10", "type": "政策金融债"},
            {"code": "", "name": "25某银行CD001", "type": "同业存单"},
        ],
        meta=SourceMeta(source="test", fetched_at=datetime.now()),
    )

    result = service._decorate_dataset("spot_bonds", dataset)

    assert [item["code"] for item in result.data] == ["240011", "250210", ""]
    assert result.data[0]["code_source"] == "standard_name_rule"
    assert result.data[0]["code_verified"] is False
    assert result.data[2]["code_available"] is False
    assert any("标准简称规则推导" in issue for issue in result.meta.quality_issues)


def test_market_status_distinguishes_trading_close_and_weekend() -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    service = DataService()

    assert service._market_status(
        "treasury_futures", datetime(2026, 7, 13, 8, 0, tzinfo=timezone)
    ) == ("pre_open", "未开盘")
    assert service._market_status(
        "treasury_futures", datetime(2026, 7, 13, 10, 0, tzinfo=timezone)
    ) == ("trading", "交易中")
    assert service._market_status(
        "treasury_futures", datetime(2026, 7, 13, 12, 0, tzinfo=timezone)
    ) == ("session_break", "午间休市")
    assert service._market_status(
        "treasury_futures", datetime(2026, 7, 13, 18, 0, tzinfo=timezone)
    ) == ("closed", "已收盘")
    assert service._market_status(
        "treasury_futures", datetime(2026, 7, 12, 10, 0, tzinfo=timezone)
    ) == ("non_trading_day", "非交易日")
    assert service._market_status("yield_curves") == ("daily", "日频数据")


def test_futures_time_without_trade_date_never_becomes_future() -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    service = DataService()
    service.cache.set(
        "trade_calendar",
        Dataset(
            data=["2026-07-14", "2026-07-15"],
            meta=SourceMeta(source="calendar", fetched_at=datetime.now()),
        ),
        ttl_seconds=86_400,
    )

    observation, inferred = service._intraday_observation_timestamp(
        "treasury_futures",
        "",
        "15:15:00",
        now=datetime(2026, 7, 15, 6, 30, tzinfo=timezone),
    )

    assert observation == "2026-07-14T15:15:00+08:00"
    assert inferred is True


def test_explicit_future_observation_is_rejected() -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    service = DataService()

    with pytest.raises(ValueError, match="未来观测时间"):
        service._intraday_observation_timestamp(
            "treasury_futures",
            "2026-07-15",
            "15:15:00",
            now=datetime(2026, 7, 15, 6, 30, tzinfo=timezone),
        )

    service.cache.set(
        "treasury_futures",
        Dataset(
            data=[{"product": "T", "contract": "T2609", "price": 109.0}],
            meta=SourceMeta(
                source="legacy",
                observation_time="2099-01-01T15:15:00",
                fetched_at=datetime.now(),
            ),
        ),
        ttl_seconds=3_600,
    )
    assert service._cached_dataset("treasury_futures") is None
    assert service.cache.get("treasury_futures", allow_stale=True) is None


def test_child_processes_receive_verified_ca_bundle(monkeypatch) -> None:
    service = DataService()
    captured_env: dict[str, str] = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        payload = {"ok": True, "result": {"rows": []}}
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=AUX_RESULT_MARKER + json.dumps(payload),
            stderr="",
        )

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)

    service._call_aux_worker("money_extensions")

    assert captured_env["SSL_CERT_FILE"].endswith("cacert.pem")
    assert captured_env["REQUESTS_CA_BUNDLE"] == captured_env["SSL_CERT_FILE"]


def test_research_status_is_independent_from_connection_state() -> None:
    suspicious = HealthItem(
        adapter="spot_bonds",
        label="现券成交",
        state="healthy",
        trust_level="suspicious",
    )
    cached = HealthItem(
        adapter="yield_curves",
        label="收益率曲线",
        state="cached",
        trust_level="trusted",
    )

    assert suspicious.research_status == "blocked"
    assert cached.research_status == "limited"


def test_open_circuit_uses_retry_time_as_next_check() -> None:
    service = DataService()
    service.cache.set(
        "spot_bonds",
        Dataset(
            data=[{"code": "240011", "name": "24附息国债11"}],
            meta=SourceMeta(source="test", fetched_at=datetime.now()),
        ),
        ttl_seconds=3_600,
    )
    service.health["spot_bonds"] = HealthItem(
        adapter="spot_bonds",
        label="现券成交",
        state="cached",
        trust_level="partial",
    )
    service._circuit_open_until["spot_bonds"] = time.time() + 120

    health = {item.adapter: item for item in service.health_items()}["spot_bonds"]

    assert health.circuit_state == "open"
    assert health.next_refresh_at == health.next_retry_at


def test_dataset_decoration_exposes_quality_and_cache_state() -> None:
    service = DataService()
    dataset = Dataset(
        data=[{"code": "240011", "name": "24附息国债11"}],
        meta=SourceMeta(source="test", fetched_at=datetime.now()),
    )

    result = service._decorate_dataset(
        "spot_bonds", dataset, cache_age_seconds=90
    )

    assert result.meta.data_state == "cached"
    assert result.meta.quality_score == 87
    assert result.meta.quality_issues == [
        "债券类型由名称推断 1/1",
        "源未提供可信市场时间",
    ]
    assert result.meta.trust_level == "partial"


def test_fresh_persistent_cache_restores_health_and_emits_once(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    cache_path = tmp_path / "market-cache.db"
    seeded = DataService(cache_path=cache_path)
    seeded.cache.set(
        "spot_bonds",
        Dataset(
            data=[
                {
                    "code": "240011",
                    "name": "24附息国债11",
                    "type": "国债",
                    "yield": 1.8,
                    "change_bp": -1.2,
                    "price": 102.3,
                    "volume": 20,
                }
            ],
            meta=SourceMeta(
                source="test",
                observation_time="2026-07-13",
                fetched_at=datetime.now(),
            ),
        ),
        ttl_seconds=3_600,
    )
    emitted: list[str] = []
    restarted = DataService(
        cache_path=cache_path,
        on_dataset=lambda adapter, _dataset: emitted.append(adapter),
    )

    first = restarted.spot_bonds()
    second = restarted.spot_bonds()
    health = {item.adapter: item for item in restarted.health_items()}

    assert first.meta.data_state == "cached"
    assert second.meta.data_state == "cached"
    assert health["spot_bonds"].state == "cached"
    assert health["spot_bonds"].rows == 1
    assert health["spot_bonds"].observation_time == "2026-07-13"
    assert emitted == ["spot_bonds"]


def test_suspicious_spot_move_is_annotated_for_quarantine() -> None:
    service = DataService()
    result = service._decorate_dataset(
        "spot_bonds",
        Dataset(
            data=[
                {
                    "code": "112233",
                    "name": "测试债券",
                    "type": "信用债",
                    "yield": 2.9,
                    "change_bp": 147.22,
                    "price": 99.5,
                    "volume": 10,
                }
            ],
            meta=SourceMeta(
                source="test",
                observation_time="2026-07-13",
                fetched_at=datetime.now(),
            ),
        ),
    )

    assert result.meta.trust_level == "suspicious"
    assert result.meta.suspicious_rows == 1
    assert result.data[0]["quality_state"] == "suspicious"
    assert "超过 50 BP" in result.data[0]["quality_issues"][0]


def test_timed_out_source_process_releases_concurrency_slot(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    service = DataService()

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="source", timeout=0.01)

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(SourceTimeoutError):
        service._call_with_timeout("fake_adapter", lambda: ([], None))

    assert service.source_activity()["active"] == 0


def test_trade_calendar_marks_weekday_holiday_as_non_trading() -> None:
    service = DataService()
    calendar = Dataset(
        data=["2026-09-30", "2026-10-09"],
        meta=SourceMeta(source="calendar", fetched_at=datetime.now()),
    )
    service.cache.set("trade_calendar", calendar, ttl_seconds=86_400)
    holiday = datetime(
        2026, 10, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )

    assert service._market_status("treasury_futures", holiday) == (
        "non_trading_day",
        "非交易日",
    )

    class CalendarAk:
        @staticmethod
        def tool_trade_date_hist_sina():
            return pd.DataFrame(
                {
                    "trade_date": [
                        date.today() - timedelta(days=1),
                        date.today() + timedelta(days=30),
                    ]
                }
            )

    live_service = DataService()
    live_service.is_source_worker = True
    live_service._ak = CalendarAk()
    result = live_service.trade_calendar()
    assert result.meta.observation_time == (
        date.today() - timedelta(days=1)
    ).isoformat()
    assert result.data[-1] == (date.today() + timedelta(days=30)).isoformat()


def test_repeated_source_failures_open_circuit_and_skip_loader(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.setenv("AKDESK_SOURCE_ATTEMPTS", "1")
    monkeypatch.setenv("AKDESK_CIRCUIT_THRESHOLD", "2")
    service = DataService()
    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        raise RuntimeError("source down")

    def load_once():
        return service._load(
            adapter="spot_bonds",
            label="现券成交",
            ttl_seconds=60,
            live_loader=fail,
            demo_loader=lambda: [{"code": "demo", "name": "demo"}],
            source="test",
            source_url="https://example.test",
            force=True,
        )

    assert load_once().meta.demo is True
    assert load_once().meta.demo is True
    assert service.source_activity()["circuits"] == {"spot_bonds": "open"}

    third = load_once()
    assert third.meta.demo is True
    assert "source down" in third.meta.warnings[0]
    assert calls == 2
    health = {item.adapter: item for item in service.health_items()}
    assert health["spot_bonds"].consecutive_failures == 2
    assert health["spot_bonds"].message == "RuntimeError: source down"
    assert service.request_refresh("spot_bonds") is False


def test_background_refresh_uses_fixed_worker_queue(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_CONCURRENCY", "2")
    service = DataService()
    active = 0
    maximum_active = 0
    completed: list[str] = []
    state_lock = Lock()

    def loader(adapter: str):
        def run() -> Dataset:
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1
                completed.append(adapter)
            return Dataset(
                data=[],
                meta=SourceMeta(source="queue-test", fetched_at=datetime.now()),
            )

        return run

    adapters = [item[0] for item in service.ADAPTERS[:6]]
    try:
        for adapter in adapters:
            assert service._background_refresh(adapter, loader(adapter)) is True
        deadline = time.time() + 2
        while len(completed) < len(adapters) and time.time() < deadline:
            time.sleep(0.01)

        assert sorted(completed) == sorted(adapters)
        assert maximum_active == 2
        assert service.source_activity()["refresh_queue_depth"] == 0
        assert service.source_activity()["refreshing"] == []
    finally:
        service.stop_scheduler()


def test_money_extensions_are_merged_without_endangering_core(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.setenv("AKDESK_ENABLE_EXTENDED_RATES", "1")
    service = DataService()
    service._ak = _PartialRatesAk()
    for adapter, row in (
        ("money_fr", {"name": "FR007", "tenor": "7D", "value": 1.7, "change_bp": 1.0}),
        ("money_fdr", {"name": "FDR007", "tenor": "7D", "value": 1.6, "change_bp": -1.0}),
    ):
        service.cache.set(
            adapter,
            Dataset(
                data=[row],
                meta=SourceMeta(
                    source="test",
                    observation_time="2026-07-13",
                    fetched_at=datetime.now(),
                ),
            ),
            ttl_seconds=1_800,
        )
    service.is_source_worker = False
    monkeypatch.setattr(
        service,
        "_call_with_timeout",
        lambda _adapter, loader: loader(),
    )

    result = service.money_rates()

    assert [item["name"] for item in result.data] == [
        "Shibor O/N",
        "Shibor 1W",
        "FR007",
        "FDR007",
    ]
    assert result.meta.warnings == ["独立扩展源尚未全部更新：LPR"]


def test_money_extension_sources_fail_independently(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.setenv("AKDESK_SOURCE_ATTEMPTS", "1")

    class ExtensionAk:
        @staticmethod
        def repo_rate_query(*, symbol: str):
            if symbol == "回购定盘利率":
                return pd.DataFrame(
                    [
                        {"date": "2026-07-10", "FR007": 1.7},
                        {"date": "2026-07-13", "FR007": 1.71},
                    ]
                )
            raise RuntimeError("FDR unavailable")

    service = DataService()
    service._ak = ExtensionAk()

    fr = service.money_fr()
    fdr = service.money_fdr()
    health = {item.adapter: item for item in service.health_items()}

    assert fr.meta.demo is False
    assert fr.data[0]["name"] == "FR007"
    assert fdr.meta.demo is True
    assert health["money_fr"].state == "healthy"
    assert health["money_fdr"].state == "unavailable"


def test_convertibles_switch_to_partial_fallback_source(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    service = DataService()

    def fake_aux(task: str, **_kwargs):
        if task == "convertibles_comparison":
            raise RuntimeError("primary down")
        return {
            "rows": [
                {
                    "code": "113000",
                    "name": "测试转债",
                    "price": 110.5,
                    "change_pct": 0.2,
                    "stock_name": "",
                    "convert_value": None,
                    "premium_pct": None,
                    "double_low": None,
                    "ytm_pct": None,
                    "redeem_status": "备用行情未提供",
                }
            ],
            "observation_time": "2026-07-13T15:00:00",
            "fallback": True,
        }

    monkeypatch.setattr(service, "_call_aux_worker", fake_aux)
    result = service.convertibles()

    assert result.meta.demo is False
    assert result.data[0]["price"] == 110.5
    assert result.data[0]["data_tier"] == "price_only"
    assert result.data[0]["research_eligible"] is False
    assert result.data[0]["quality_state"] == "partial"
    assert "新浪备用行情" in result.meta.warnings[0]
