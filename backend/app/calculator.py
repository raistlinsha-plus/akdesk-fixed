from __future__ import annotations

import calendar
from datetime import date

from .models import (
    BondCalculatorRequest,
    BondCalculatorResult,
    CashFlow,
)


def _subtract_months(value: date, months: int) -> date:
    total_months = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _coupon_schedule(settlement: date, maturity: date, frequency: int) -> list[date]:
    if frequency not in {1, 2, 4, 12}:
        raise ValueError("当前仅支持每年 1、2、4 或 12 次付息")
    months = 12 // frequency
    dates: list[date] = []
    current = maturity
    while current > settlement:
        dates.append(current)
        current = _subtract_months(current, months)
    return sorted(dates)


def _previous_coupon(settlement: date, maturity: date, frequency: int) -> date:
    months = 12 // frequency
    current = maturity
    while current > settlement:
        current = _subtract_months(current, months)
    return current


def _year_fraction(start: date, end: date, convention: str) -> float:
    if end < start:
        return -_year_fraction(end, start, convention)
    if convention == "ACT/365":
        return (end - start).days / 365.0
    if convention == "30/360":
        day1 = min(start.day, 30)
        day2 = min(end.day, 30) if day1 == 30 else end.day
        return (
            (end.year - start.year) * 360
            + (end.month - start.month) * 30
            + day2
            - day1
        ) / 360.0
    current = start
    result = 0.0
    while current < end:
        boundary = min(date(current.year + 1, 1, 1), end)
        denominator = 366 if calendar.isleap(current.year) else 365
        result += (boundary - current).days / denominator
        current = boundary
    return result


def _price_from_yield(
    annual_yield: float,
    flows: list[tuple[float, float]],
    frequency: int,
) -> float:
    base = 1 + annual_yield / frequency
    if base <= 0:
        return float("inf")
    return sum(amount / (base ** (years * frequency)) for years, amount in flows)


def _solve_yield(
    dirty_price: float,
    flows: list[tuple[float, float]],
    frequency: int,
) -> float:
    lower, upper = -0.95, 5.0
    lower_price = _price_from_yield(lower, flows, frequency)
    upper_price = _price_from_yield(upper, flows, frequency)
    if not (upper_price <= dirty_price <= lower_price):
        raise ValueError("在支持的收益率区间内无法求解 YTM")

    for _ in range(200):
        middle = (lower + upper) / 2
        price = _price_from_yield(middle, flows, frequency)
        if abs(price - dirty_price) < 1e-10:
            return middle
        if price > dirty_price:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def calculate_bond(request: BondCalculatorRequest) -> BondCalculatorResult:
    settlement = date.fromisoformat(request.settlement_date)
    maturity = date.fromisoformat(request.maturity_date)
    if settlement >= maturity:
        raise ValueError("结算日必须早于到期日")

    coupon_dates = _coupon_schedule(settlement, maturity, request.frequency)
    if not coupon_dates:
        raise ValueError("没有可计算的未来现金流")

    coupon_amount = (
        request.face_value * request.coupon_rate_pct / 100 / request.frequency
    )
    previous_coupon = _previous_coupon(settlement, maturity, request.frequency)
    next_coupon = coupon_dates[0]
    coupon_period = _year_fraction(previous_coupon, next_coupon, request.day_count)
    accrued_period = max(
        _year_fraction(previous_coupon, settlement, request.day_count), 0.0
    )
    accrued_interest = (
        coupon_amount * accrued_period / coupon_period if coupon_period else 0.0
    )
    dirty_price = request.clean_price + accrued_interest

    raw_flows: list[tuple[float, float]] = []
    for coupon_date in coupon_dates:
        years = _year_fraction(settlement, coupon_date, request.day_count)
        amount = coupon_amount
        if coupon_date == maturity:
            amount += request.face_value
        raw_flows.append((years, amount))

    annual_yield = _solve_yield(dirty_price, raw_flows, request.frequency)
    present_values = [
        amount
        / ((1 + annual_yield / request.frequency) ** (years * request.frequency))
        for years, amount in raw_flows
    ]
    macaulay = sum(
        years * present_value
        for (years, _), present_value in zip(
            raw_flows, present_values, strict=True
        )
    ) / dirty_price
    modified = macaulay / (1 + annual_yield / request.frequency)

    bump = 0.0001
    price_down = _price_from_yield(annual_yield - bump, raw_flows, request.frequency)
    price_up = _price_from_yield(annual_yield + bump, raw_flows, request.frequency)
    convexity = (price_down + price_up - 2 * dirty_price) / (
        dirty_price * bump * bump
    )

    position_market_value = (
        dirty_price / request.face_value * request.position_face_value
    )
    dv01 = modified * position_market_value * 0.0001

    scenarios: dict[str, float] = {}
    for bp in (-10, -5, -1, 1, 5, 10):
        scenario_yield = annual_yield + bp / 10_000
        scenarios[f"{bp:+d}BP"] = round(
            _price_from_yield(scenario_yield, raw_flows, request.frequency), 6
        )

    cash_flows = [
        CashFlow(
            date=coupon_date.isoformat(),
            years=round(years, 6),
            amount=round(amount, 6),
            present_value=round(present_value, 6),
        )
        for coupon_date, (years, amount), present_value in zip(
            coupon_dates,
            raw_flows,
            present_values,
            strict=True,
        )
    ]

    return BondCalculatorResult(
        accrued_interest=round(accrued_interest, 6),
        dirty_price=round(dirty_price, 6),
        ytm_pct=round(annual_yield * 100, 6),
        macaulay_duration=round(macaulay, 6),
        modified_duration=round(modified, 6),
        convexity=round(convexity, 6),
        dv01=round(dv01, 6),
        scenario_prices=scenarios,
        cash_flows=cash_flows,
        methodology=(
            f"{request.day_count}；固定票息现金流；名义年化 YTM；"
            "久期按贴现现金流计算；凸性采用 ±1BP 中心差分。"
        ),
    )
