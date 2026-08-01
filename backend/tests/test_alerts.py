from datetime import datetime

from pydantic import ValidationError
import pytest

from app.alerts import AlertEngine
from app.database import Database
from app.models import AlertCreate, Dataset, SourceMeta


def _dataset(*, stale: bool = False, demo: bool = False) -> Dataset:
    return Dataset(
        data=[{"code": "240011", "yield": 2.15, "price": 101.2}],
        meta=SourceMeta(
            source="test source",
            observation_time="2026-07-13T15:00:00",
            fetched_at=datetime.now(),
            stale=stale,
            demo=demo,
        ),
    )


def _dataset_with_yield(value: float) -> Dataset:
    dataset = _dataset()
    dataset.data[0]["yield"] = value
    return dataset


def test_alert_triggers_once_within_cooldown(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_NOTIFICATIONS", "0")
    database = Database(tmp_path / "test.db")
    database.add_alert(
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="收益率突破",
            metric="yield",
            operator=">=",
            threshold=2.0,
            cooldown_minutes=30,
        )
    )
    engine = AlertEngine(database)

    assert len(engine.evaluate("spot_bonds", _dataset())) == 1
    assert engine.evaluate("spot_bonds", _dataset()) == []
    assert database.unread_alert_count() == 1


@pytest.mark.parametrize("stale,demo", [(True, False), (False, True)])
def test_alert_does_not_trigger_from_untrusted_data(
    tmp_path, monkeypatch, stale: bool, demo: bool
) -> None:
    monkeypatch.setenv("AKDESK_NOTIFICATIONS", "0")
    database = Database(tmp_path / "test.db")
    database.add_alert(
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="收益率突破",
            metric="yield",
            operator=">",
            threshold=2.0,
        )
    )

    assert AlertEngine(database).evaluate(
        "spot_bonds", _dataset(stale=stale, demo=demo)
    ) == []


def test_alert_rejects_metric_for_wrong_object_type() -> None:
    with pytest.raises(ValidationError):
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="错误规则",
            metric="premium_pct",
            operator=">",
            threshold=10,
        )


def test_alert_triggers_when_condition_crosses_from_false_to_true(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AKDESK_NOTIFICATIONS", "0")
    database = Database(tmp_path / "test.db")
    database.add_alert(
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="收益率上穿",
            metric="yield",
            operator=">",
            threshold=2.0,
        )
    )
    engine = AlertEngine(database)

    assert engine.evaluate("spot_bonds", _dataset_with_yield(1.9)) == []
    assert len(engine.evaluate("spot_bonds", _dataset_with_yield(2.1))) == 1
    assert engine.evaluate("spot_bonds", _dataset_with_yield(2.2)) == []
    saved = database.list_alerts()[0]
    assert saved.last_matched is True
    assert saved.last_value == 2.2
    assert saved.last_evaluated_at is not None


def test_alert_preview_does_not_mutate_trigger_history(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    engine = AlertEngine(database)
    rule = AlertCreate(
        object_type="bond",
        object_id="240011",
        name="收益率试算",
        metric="yield",
        operator=">",
        threshold=2.0,
    )

    preview = engine.preview("spot_bonds", _dataset(), rule)

    assert preview["available"] is True
    assert preview["matched"] is True
    assert preview["value"] == 2.15
    assert database.list_alert_triggers() == []


def test_daily_trigger_limit_suppresses_repeated_crossing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_NOTIFICATIONS", "0")
    database = Database(tmp_path / "test.db")
    database.add_alert(
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="收益率上穿",
            metric="yield",
            operator=">",
            threshold=2.0,
            max_triggers_per_day=1,
        )
    )
    engine = AlertEngine(database)

    assert len(engine.evaluate("spot_bonds", _dataset_with_yield(2.1))) == 1
    assert engine.evaluate("spot_bonds", _dataset_with_yield(1.9)) == []
    assert engine.evaluate("spot_bonds", _dataset_with_yield(2.2)) == []
    assert len(database.list_alert_triggers()) == 1


def test_quiet_hours_support_overnight_ranges() -> None:
    assert AlertEngine._is_quiet_time(
        datetime(2026, 7, 13, 23, 0), "22:00", "08:00"
    ) is True
    assert AlertEngine._is_quiet_time(
        datetime(2026, 7, 13, 12, 0), "22:00", "08:00"
    ) is False
