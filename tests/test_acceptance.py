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


def test_1_in_transit_reduces_order(data, base):
    line = base.order_lines[base.order_lines["recommended_qty"] > 0].iloc[0]
    changed = {**data, "in_transit": data["in_transit"].copy()}
    extra = schema.conform(
        pd.DataFrame([{
            "supplier": line.supplier, "sku": line.sku, "qty": line.recommended_qty,
            "eta": base.as_of, "order_ref": "test"}]), schema.IN_TRANSIT)
    changed["in_transit"] = pd.concat([changed["in_transit"], extra], ignore_index=True)
    assert qty(run(changed), line.supplier, line.sku) < line.recommended_qty


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


@pytest.mark.xfail(reason="task 1.2: stockout uplift not implemented yet", strict=False)
def test_3_stockout_fix_raises_demand(data):
    on = run(data).demand_monthly
    off = run(data, dataclasses.replace(schema.Params(), use_stockout_fix=False)).demand_monthly
    assert on["qty_regular"].sum() > off["qty_regular"].sum()


@pytest.mark.xfail(reason="task 1.1: one-off detection not implemented yet", strict=False)
def test_4_loop_one_off_excluded(base):
    flagged = base.sales_flagged
    assert flagged.query("sku == '130200305_' and qty == 210000")["is_oneoff"].all()
    assert not flagged.query("sku == '030200192_' and qty >= 36000")["is_oneoff"].any()
