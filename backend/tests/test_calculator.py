from app.calculator import calculate_bond
from app.models import BondCalculatorRequest


def test_par_bond_has_near_coupon_yield() -> None:
    result = calculate_bond(
        BondCalculatorRequest(
            settlement_date="2026-01-01",
            maturity_date="2031-01-01",
            coupon_rate_pct=3.0,
            clean_price=100.0,
            face_value=100.0,
            frequency=2,
            position_face_value=1_000_000,
        )
    )
    assert 2.9 < result.ytm_pct < 3.1
    assert result.modified_duration > 4
    assert result.dv01 > 400


def test_discount_bond_has_higher_yield() -> None:
    result = calculate_bond(
        BondCalculatorRequest(
            settlement_date="2026-01-01",
            maturity_date="2031-01-01",
            coupon_rate_pct=3.0,
            clean_price=95.0,
            face_value=100.0,
            frequency=2,
            position_face_value=1_000_000,
        )
    )
    assert result.ytm_pct > 3.0
    assert result.scenario_prices["-10BP"] > result.dirty_price
    assert result.scenario_prices["+10BP"] < result.dirty_price


def test_day_count_convention_changes_accrued_interest() -> None:
    common = {
        "settlement_date": "2026-02-28",
        "maturity_date": "2031-01-31",
        "coupon_rate_pct": 3.0,
        "clean_price": 100.0,
        "face_value": 100.0,
        "frequency": 2,
        "position_face_value": 1_000_000,
    }

    actual = calculate_bond(BondCalculatorRequest(**common, day_count="ACT/365"))
    thirty = calculate_bond(BondCalculatorRequest(**common, day_count="30/360"))

    assert actual.accrued_interest != thirty.accrued_interest
    assert actual.methodology.startswith("ACT/365")
    assert thirty.methodology.startswith("30/360")
