from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook

from app.credit import credit_workspace
from app.credit_import import credit_history_csv, credit_observations_csv, parse_credit_file
from app.database import Database
from app.models import CreditPortfolioCreate
from app.models import CreditObservationCreate, CreditObservationUpdate


CSV_CONTENT = """债券代码,债券名称,发行人,主体归一名,到期日,回售日,债项评级,评级日期,到期收益率(%),收益率日期,基准期限,基准收益率(%),基准日期,来源说明,下次复盘日,观察状态
102600001,示例中票,示例集团有限公司,示例集团有限公司,2031-07-15,2026-12-01,AAA,2025-06-30,2.10,2026-06-15,5Y,1.80,2026-06-15,人工核验：成交与评级公告,2026-07-10,重点关注
102600001,示例中票,示例集团有限公司,示例集团有限公司,2031-07-15,2026-12-01,AAA,2025-06-30,2.60,2026-07-15,5Y,1.80,2026-07-15,人工核验：成交与评级公告,2026-07-10,重点关注
"""


def test_credit_r2_import_history_signals_and_portfolio(tmp_path) -> None:
    preview = parse_credit_file(
        CSV_CONTENT.encode("utf-8"), "credit-observations.csv"
    )
    assert preview["valid_rows"] == 2
    assert preview["invalid_rows"] == 0
    assert preview["mapping"]["bond_code"] == "债券代码"

    database = Database(tmp_path / "credit-r2.db")
    imported = database.add_credit_observations(preview["items"])
    assert imported == {"imported_rows": 2, "observations": 1}

    observation = database.list_credit_observations()[0]
    portfolio = database.add_credit_portfolio(
        CreditPortfolioCreate(
            name="城投重点观察",
            description="人工维护组合",
            observation_ids=[observation.id],
        )
    )
    assert portfolio["observation_ids"] == [observation.id]

    workspace = credit_workspace(database, as_of=date(2026, 7, 18))
    item = workspace["items"][0]
    assert item["history_points"] == 2
    assert item["spread_change_bp"] == 50.0
    assert item["spread_percentile"] == 100.0
    assert workspace["summary"]["issuers"] == 1
    assert workspace["portfolios"][0]["spread_range_bp"] == {
        "minimum": 80.0,
        "maximum": 80.0,
        "count": 1,
    }
    assert {signal["kind"] for signal in workspace["signals"]} >= {
        "spread_move",
        "rating_review",
        "review_due",
    }
    assert any(event["kind"] == "put" for event in workspace["calendar"])

    signal = workspace["signals"][0]
    confirmed = database.confirm_credit_signal(signal["id"], "已核对原始公告")
    assert confirmed["note"] == "已核对原始公告"
    refreshed = credit_workspace(database, as_of=date(2026, 7, 18))
    assert next(item for item in refreshed["signals"] if item["id"] == signal["id"])[
        "confirmation"
    ]["note"] == "已核对原始公告"


def test_credit_r2_excel_preview_and_mapping_override() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["证券编号", "证券简称", "主体", "行情日", "收益率"])
    sheet.append([102600002, "Excel 中票", "测试发行人", date(2026, 7, 15), 2.45])
    content = BytesIO()
    workbook.save(content)
    workbook.close()

    preview = parse_credit_file(
        content.getvalue(),
        "credit.xlsx",
        {
            "bond_code": "证券编号",
            "bond_name": "证券简称",
            "issuer": "主体",
            "yield_observation_date": "行情日",
            "yield_pct": "收益率",
        },
    )
    assert preview["valid_rows"] == 1
    assert preview["items"][0].bond_code == "102600002"
    assert preview["items"][0].yield_observation_date == "2026-07-15"
    assert preview["preview_rows"][0]["eligible"] is False
    assert any("缺少" in note for note in preview["preview_rows"][0]["quality_notes"])


def test_credit_r2_import_rejects_missing_required_mapping() -> None:
    preview = parse_credit_file("发行人,评级\n测试主体,AAA\n".encode(), "bad.csv")
    assert preview["valid_rows"] == 0
    assert preview["errors"][0]["row"] == 1
    assert "必填字段映射" in preview["errors"][0]["message"]


def test_credit_r2_import_accepts_blank_optional_tenor_column() -> None:
    content = (
        "债券代码,债券名称,基准期限,基准收益率(%)\n"
        "BLANK001,可选列留空,,\n"
    ).encode()
    preview = parse_credit_file(content, "blank-optional.csv")
    assert preview["valid_rows"] == 1
    assert preview["invalid_rows"] == 0
    assert preview["items"][0].benchmark_tenor is None


def test_credit_r2_current_export_round_trips() -> None:
    items = [
        CreditObservationCreate(
            bond_code="EXPORT001",
            bond_name="导出回环测试",
            issuer="测试主体",
            benchmark_tenor=None,
            watch_status="watch",
        )
    ]
    exported = credit_observations_csv(items)
    preview = parse_credit_file(exported.encode(), "credit-export.csv")
    assert preview["valid_rows"] == 1
    assert preview["items"][0].bond_code == "EXPORT001"
    assert preview["items"][0].benchmark_tenor is None
    assert preview["items"][0].watch_status == "watch"


def test_credit_r2_history_export_round_trips_all_snapshots(tmp_path) -> None:
    database = Database(tmp_path / "history-export.db")
    preview = parse_credit_file(CSV_CONTENT.encode(), "history.csv")
    database.add_credit_observations(preview["items"])
    exported = credit_history_csv(
        database.list_credit_observations(), database.list_credit_history()
    )
    round_trip = parse_credit_file(exported.encode(), "history-export.csv")
    assert round_trip["valid_rows"] == 2
    assert [item.yield_observation_date for item in round_trip["items"]] == [
        "2026-06-15",
        "2026-07-15",
    ]


def test_credit_r2_history_export_does_not_backfill_historical_nulls(tmp_path) -> None:
    database = Database(tmp_path / "history-nulls.db")
    saved = database.add_credit_observation(
        CreditObservationCreate(
            bond_code="NULL001",
            bond_name="历史空值",
            issuer="测试主体",
            yield_pct=2.1,
            yield_observation_date="2026-06-15",
        )
    )
    database.update_credit_observation(
        saved.id,
        CreditObservationUpdate(
            rating="AAA",
            source_note="后续补充资料",
            yield_pct=2.2,
            yield_observation_date="2026-07-15",
        ),
    )

    exported = credit_history_csv(
        database.list_credit_observations(), database.list_credit_history()
    )
    round_trip = parse_credit_file(exported.encode(), "history-nulls.csv")
    assert [item.rating for item in round_trip["items"]] == ["", "AAA"]
    assert [item.source_note for item in round_trip["items"]] == [
        "",
        "后续补充资料",
    ]


def test_credit_r2_historical_import_does_not_replace_newer_current_snapshot(tmp_path) -> None:
    database = Database(tmp_path / "current.db")
    database.add_credit_observation(
        CreditObservationCreate(
            bond_code="CURRENT001",
            bond_name="当前观察",
            yield_pct=2.5,
            yield_observation_date="2026-07-18",
        )
    )
    database.add_credit_observations(
        [
            CreditObservationCreate(
                bond_code="CURRENT001",
                bond_name="历史观察",
                yield_pct=2.1,
                yield_observation_date="2026-06-18",
            )
        ]
    )

    current = database.list_credit_observations()[0]
    assert current.bond_name == "当前观察"
    assert current.yield_observation_date == "2026-07-18"
    assert len(database.list_credit_history(current.id)) == 2
