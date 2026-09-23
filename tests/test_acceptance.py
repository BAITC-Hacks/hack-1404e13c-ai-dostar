"""Acceptance checks for the ТЗ must-haves. Owner: Person 2 «Расчет» (task 2.4).

Each must-have gets a controlled intervention on real data through pipeline.run.
Tests marked xfail are waiting for the engine step that makes them pass.
"""

import dataclasses

import pandas as pd
import pytest

from app import schema
from app.adapters import CLEAN_DIR, load_clean
from app.engine import forecast
from app.pipeline import run

pytestmark = pytest.mark.skipif(not (CLEAN_DIR / "sales_lines.parquet").exists(),
                                reason="data/clean not built")


@pytest.fixture(scope="module")
def data():
    return load_clean()


@pytest.fixture(scope="module")
def base(data):
    return run(data)


def qty(result, supplier, sku):
    row = result.order_lines.query("supplier == @supplier and sku == @sku")
    return float(row["recommended_qty"].iloc[0]) if len(row) else 0.0


def test_output_follows_contract(base):
    assert list(base.order_lines.columns) == list(schema.ORDER_LINES)
    assert set(base.order_lines["supplier"]) == {"IEK", "SE"}
    assert base.order_lines["rationale"].str.len().gt(0).all()


def test_pack_rounding(base, data):
    lines = base.order_lines.merge(data["products"][["supplier", "sku", "pack_multiple"]], on=["supplier", "sku"])
    positive = lines[lines["recommended_qty"] > 0]
    assert (positive["recommended_qty"] % positive["pack_multiple"] == 0).all()


def _line(result, supplier, sku) -> pd.Series:
    return result.order_lines.set_index(["supplier", "sku"]).loc[(supplier, sku)]


@pytest.fixture(scope="module")
def target(base):
    """A regular SKU that is ordered and has free stock: every source can move it."""
    lines = base.order_lines
    pick = lines[(lines["recommended_qty"] > 0) & (lines["free_qty"] > 0) & (lines["flags"] == "")]
    return pick.sort_values("recommended_qty", ascending=False).iloc[0]


def _with(data, name, frame):
    return {**data, name: frame}


# ---- Must-have 1: every input source is reflected in the result -------------

def test_1_in_transit_reduces_order(data, base, target):
    extra = schema.conform(pd.DataFrame([{
        "supplier": target.supplier, "sku": target.sku, "qty": target.recommended_qty,
        "eta": base.as_of, "order_ref": "test"}]), schema.IN_TRANSIT)
    changed = run(_with(data, "in_transit", pd.concat([data["in_transit"], extra], ignore_index=True)))
    assert _line(changed, target.supplier, target.sku)["recommended_qty"] < target.recommended_qty


def test_1_late_transit_is_ignored(data, base, target):
    late = schema.conform(pd.DataFrame([{
        "supplier": target.supplier, "sku": target.sku, "qty": target.recommended_qty,
        "eta": base.as_of + pd.Timedelta(days=365), "order_ref": "late"}]), schema.IN_TRANSIT)
    changed = run(_with(data, "in_transit", pd.concat([data["in_transit"], late], ignore_index=True)))
    assert _line(changed, target.supplier, target.sku)["recommended_qty"] == target.recommended_qty


def test_1_lower_stock_raises_order(data, target):
    stock = data["stock_now"].copy()
    stock.loc[(stock["supplier"] == target.supplier) & (stock["sku"] == target.sku), "free_qty"] = 0.0
    changed = _line(run(_with(data, "stock_now", stock)), target.supplier, target.sku)
    assert changed["recommended_qty"] > target.recommended_qty


def test_1_more_sales_raise_forecast(data, target):
    sales = data["sales_lines"].copy()
    mask = (sales["supplier"] == target.supplier) & (sales["sku"] == target.sku)
    sales.loc[mask, "qty"] *= 2
    changed = _line(run(_with(data, "sales_lines", sales)), target.supplier, target.sku)
    assert changed["forecast_H"] > 1.5 * target.forecast_H


def test_1_category_growth_forecast_applied(data, target):
    params = schema.Params(growth_pct={target.category: 20.0})
    changed = _line(run(data, params), target.supplier, target.sku)
    assert changed["growth_factor"] == pytest.approx(1.2)
    assert changed["forecast_H"] == pytest.approx(1.2 * target.forecast_H)
    assert changed["recommended_qty"] >= target.recommended_qty


def test_1_pack_multiple_applied(data, target):
    products = data["products"].copy()
    products.loc[(products["supplier"] == target.supplier) & (products["sku"] == target.sku), "pack_multiple"] = 1000.0
    changed = _line(run(_with(data, "products", products)), target.supplier, target.sku)
    assert changed["recommended_qty"] > 0 and changed["recommended_qty"] % 1000 == 0


def test_1_seasonality_sources_used(data, base):
    """Monthly report (2024 shape) and company seasonality both change the forecast."""
    no_report = run(_with(data, "monthly_sales", schema.empty(schema.MONTHLY_SALES))).forecast
    flat_company = data["seasonality"].assign(coef=1.0)
    no_company = run(_with(data, "seasonality", flat_company)).forecast
    assert not no_report["forecast_H"].equals(base.forecast["forecast_H"])
    assert not no_company["forecast_H"].equals(base.forecast["forecast_H"])


def test_1_stock_history_marks_stockouts(data, base, target):
    """Zero stock in weak months -> those months become stockouts and demand is restored."""
    monthly = base.demand_monthly.query("supplier == @target.supplier and sku == @target.sku")
    full = monthly[monthly["month"] < base.as_of.strftime("%Y-%m")]
    weak = full.loc[full["qty_regular"] < full["qty_regular"].median(), "month"]
    stock = data["stock_monthly"].copy()
    mask = (stock["supplier"] == target.supplier) & (stock["sku"] == target.sku) & stock["month"].isin(weak)
    stock.loc[mask, "qty_start"] = 0.0
    changed = _line(run(_with(data, "stock_monthly", stock)), target.supplier, target.sku)
    assert changed["stockout_months"] > target.stockout_months
    assert changed["stockout_uplift_qty"] > target.stockout_uplift_qty
    assert changed["forecast_H"] > target.forecast_H


SEASONAL_SKU = ("IEK", "130300792_")  # гибкая труба Ø50: пик в октябре, провал в феврале в 2024 и 2025


def _forecast_at(data, base, as_of, **overrides):
    params = dataclasses.replace(schema.Params(), **overrides)
    monthly = base.demand_monthly[base.demand_monthly["month"] <= as_of.strftime("%Y-%m")]
    fc = forecast.forecast(monthly, data["monthly_sales"], data["seasonality"], data["products"], params, as_of)
    return fc.set_index(["supplier", "sku"]).loc[SEASONAL_SKU]


def test_2_seasonal_pattern_not_flat_average(data, base):
    peak = _forecast_at(data, base, pd.Timestamp("2025-09-22"))
    trough = _forecast_at(data, base, pd.Timestamp("2026-01-22"))
    assert peak["seasonal_index"] > 1.3 and trough["seasonal_index"] < 0.8
    # Прогноз на пиковый горизонт заметно выше простого среднего по истории.
    flat = _forecast_at(data, base, pd.Timestamp("2025-09-22"), use_seasonality=False)
    assert peak["forecast_H"] > 1.3 * flat["forecast_H"]


def test_2_sustained_growth_raises_forecast():
    months = pd.period_range("2025-01", "2026-08", freq="M").strftime("%Y-%m")
    rows = []
    for i, month in enumerate(months):
        rows.append({"sku": "grow", "qty": 100 + 10 * i})
        rows.append({"sku": "flat", "qty": 150 + (15 if i % 2 else -15)})
    demand = pd.DataFrame(rows).assign(
        supplier="IEK", month=[m for m in months for _ in (0, 1)], qty_raw=lambda d: d["qty"],
        oneoff_excluded_qty=0.0, stockout=False, stockout_uplift_qty=0.0, qty_regular=lambda d: d["qty"],
        days_in_month_observed=30)
    products = pd.DataFrame({"supplier": "IEK", "sku": ["grow", "flat"], "category": "0000"})
    seasonality = pd.DataFrame({"supplier": "IEK", "month_num": range(1, 13), "coef": 1.0})
    fc = forecast.forecast(demand, schema.empty(schema.MONTHLY_SALES), seasonality, products,
                           schema.Params(use_seasonality=False), pd.Timestamp("2026-09-01")).set_index("sku")
    assert fc.loc["grow", "trend_factor"] > 1.05
    assert fc.loc["flat", "trend_factor"] == 1.0


def test_3_stockout_fix_raises_demand(data):
    on = run(data).demand_monthly
    off = run(data, dataclasses.replace(schema.Params(), use_stockout_fix=False)).demand_monthly
    assert on["qty_regular"].sum() > off["qty_regular"].sum()


def test_4_loop_one_off_excluded(base):
    flagged = base.sales_flagged
    assert flagged.query("sku == '130200305_' and qty == 210000")["is_oneoff"].all()
    assert not flagged.query("sku == '030200192_' and qty >= 36000")["is_oneoff"].any()


def test_4_injected_one_off_does_not_inflate_order(data, base):
    """A one-off line of 50x the typical size barely moves the regular recommendation."""
    sales = data["sales_lines"]
    recent = sales[(sales["qty"] > 0) & (sales["date"] >= "2025-01-01")]
    stats = recent.groupby(["supplier", "sku"])["qty"].agg(["median", "max", "size"])
    ordered = base.order_lines.set_index(["supplier", "sku"])["recommended_qty"]
    # A steadily sold SKU with no large lines in its history: a 50x line is clearly unprecedented.
    stats = stats[(stats["size"] >= 60) & (stats["max"] <= 10 * stats["median"])].join(ordered, how="inner")
    supplier, sku = stats["recommended_qty"].idxmax()  # large enough that 10% is a meaningful bound
    median = stats.loc[(supplier, sku), "median"]

    spike = schema.conform(pd.DataFrame([{
        "supplier": supplier, "sku": sku, "date": pd.Timestamp("2026-05-15 12:00"), "doc_id": "TEST-SPIKE",
        "qty": 50 * median, "unit": "шт", "warehouse": "Алматы"}]), schema.SALES_LINES)
    injected = _with(data, "sales_lines", pd.concat([sales, spike], ignore_index=True))

    # ТЗ: «не вызывает значительного роста рекомендуемого регулярного количества».
    # Сравниваем регулярную потребность (прогноз + страховой запас): итоговый заказ —
    # это разность с остатком и в процентах усиливает любое малое изменение.
    def need(line):
        return line["forecast_H"] + line["safety_stock"]

    before = need(_line(base, supplier, sku))
    filtered = _line(run(injected), supplier, sku)
    unfiltered = _line(run(injected, schema.Params(use_oneoff_filter=False)), supplier, sku)
    assert need(filtered) <= 1.10 * before
    assert need(unfiltered) > 1.3 * before  # без фильтра разовая строка раздувает потребность
