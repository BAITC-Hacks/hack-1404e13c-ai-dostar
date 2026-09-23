"""Acceptance checks for the ТЗ must-haves. Owner: Person 2 «Расчет» (task 2.4).

Each must-have gets a controlled intervention on real data through pipeline.run.
Tests marked xfail are waiting for the engine step that makes them pass.
"""

import dataclasses

import pytest

from app import schema
from app.adapters import CLEAN_DIR, load_clean
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
        __import__("pandas").DataFrame([{
            "supplier": line.supplier, "sku": line.sku, "qty": line.recommended_qty,
            "eta": base.as_of, "order_ref": "test"}]), schema.IN_TRANSIT)
    changed["in_transit"] = __import__("pandas").concat([changed["in_transit"], extra], ignore_index=True)
    assert qty(run(changed), line.supplier, line.sku) < line.recommended_qty


@pytest.mark.xfail(reason="task 2.1: seasonality not implemented yet", strict=False)
def test_2_seasonality_changes_forecast(data):
    on = run(data).forecast
    off = run(data, dataclasses.replace(schema.Params(), use_seasonality=False)).forecast
    assert (on["seasonal_index"] != 1).any() and not on["forecast_H"].equals(off["forecast_H"])


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
