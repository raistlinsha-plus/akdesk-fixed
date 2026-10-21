from datetime import datetime

from app import demo_data
from app.database import Database
from app.models import Dataset, SourceMeta
from app.provider import DataService
from app.research import build_daily_report


def test_daily_report_provenance_preserves_mode_and_times_without_url_secrets(tmp_path):
    service = DataService()
    dataset = Dataset(
        data=demo_data.money_rates(),
        meta=SourceMeta(
            source="合成资金示例",
            source_url="https://example.com/rates?token=private#secret",
            observation_time="2026-07-27",
            fetched_at=datetime.fromisoformat("2026-07-27T16:00:00+08:00"),
            demo=True,
            data_state="demo",
        ),
    )
    service.cache.set("money_rates", dataset, 3600)
    report = build_daily_report(service, Database(tmp_path / "research.db"))
    sources = {source["adapter"]: source for source in report["data_sources"]}
    assert len(sources) == 5
    assert sources["money_rates"]["demo"] is True
    assert sources["money_rates"]["observation_time"] == "2026-07-27"
    assert sources["money_rates"]["fetched_at"] == "2026-07-27T16:00:00+08:00"
    assert sources["money_rates"]["source_url"] == "https://example.com/rates"
    assert "private" not in str(sources)
    assert sources["yield_curves"]["demo"] is None
    assert sources["yield_curves"]["data_state"] == "unavailable"
    assert sources["yield_curves"]["observation_time"] is None


def test_daily_report_does_not_emit_non_http_or_userinfo_source_urls(tmp_path):
    service = DataService()
    for adapter, url in (
        ("money_rates", "javascript:alert(1)"),
        ("yield_curves", "https://user:secret@example.com/rates"),
    ):
        data = demo_data.money_rates() if adapter == "money_rates" else demo_data.yield_curves()
        service.cache.set(
            adapter,
            Dataset(data=data, meta=SourceMeta(source="test", source_url=url, fetched_at=datetime.now())),
            3600,
        )
    report = build_daily_report(service, Database(tmp_path / "research.db"))
    assert all(source["source_url"] is None for source in report["data_sources"])


def test_daily_report_missing_data_never_implies_a_flat_market(tmp_path):
    report = build_daily_report(DataService(), Database(tmp_path / "empty.db"))
    assert report["funding"]["average_change_bp"] is None
    assert report["curve"]["ten_year_change_bp"] is None
    assert report["funding"]["tone"] == "变动待核验"
    assert report["headline"] == "资金面变动待核验，长端变动待核验"


def test_daily_report_real_zero_changes_still_describe_a_flat_market(tmp_path):
    service = DataService()
    for adapter, data in (
        ("money_rates", [{"name": "Shibor O/N", "value": 1.4, "change_bp": 0.0}]),
        ("yield_curves", {
            "tenors": ["10Y"],
            "series": [{"name": "中债国债·最新", "values": [1.8]}],
            "changes": [0.0],
        }),
    ):
        service.cache.set(
            adapter,
            Dataset(data=data, meta=SourceMeta(source="test", fetched_at=datetime.now())),
            3600,
        )
    report = build_daily_report(service, Database(tmp_path / "zeros.db"))
    assert report["headline"] == "资金面变化有限，长端窄幅波动"
    assert report["funding"]["average_change_bp"] == 0
    assert report["curve"]["ten_year_change_bp"] == 0


def test_daily_report_missing_ten_year_level_blocks_directional_headline(tmp_path):
    service = DataService()
    service.cache.set(
        "yield_curves",
        Dataset(
            data={
                "tenors": ["10Y"],
                "series": [{"name": "中债国债·最新", "values": [None]}],
                "changes": [2.0],
            },
            meta=SourceMeta(source="test", fetched_at=datetime.now()),
        ),
        3600,
    )
    report = build_daily_report(service, Database(tmp_path / "missing-level.db"))
    assert report["curve"]["ten_year_change_bp"] == 2.0
    assert report["curve"]["tenors"]["10Y"] is None
    assert "长端变动待核验" in report["headline"]
    assert "收益率上行" not in report["headline"]
