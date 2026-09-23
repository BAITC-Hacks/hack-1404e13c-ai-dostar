"""Tests for engine/oneoffs.py and engine/demand.py. Owner: Person 1 «Спрос» (task 1.3)."""

from dataclasses import replace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app import schema
from app.adapters import CLEAN_DIR, load_clean
from app.engine import demand, oneoffs

def sales_table(rows, supplier="IEK", sku="demo"):
    return schema.conform(pd.DataFrame([
        dict(supplier=supplier, sku=sku, date=pd.Timestamp(date), doc_id=str(i),
             qty=qty, unit="pcs", warehouse="A")
        for i, (date, qty) in enumerate(rows)
    ]), schema.SALES_LINES)


def stock_table(rows):
    return schema.conform(pd.DataFrame([
        dict(supplier="IEK", sku="demo", month=month, qty_start=qty)
        for month, qty in rows
    ]), schema.STOCK_MONTHLY)


def seasonal_table(coefficients):
    return schema.conform(pd.DataFrame([
        dict(supplier="IEK", month_num=month, coef=coef)
        for month, coef in coefficients
    ]), schema.SEASONALITY)


@pytest.fixture
def regular_sales():
    return sales_table([(f"2025-{month:02d}-{day:02d}", 10)
                        for month in range(1, 7) for day in range(1, 13)])


def test_injected_fifty_fold_line_is_reduced_to_typical(regular_sales):
    injected = sales_table([("2025-06-20", 500), ("2025-06-21", -25)])
    sales = pd.concat([regular_sales, injected], ignore_index=True)
    before = sales.copy(deep=True)
    flagged = oneoffs.flag_oneoffs(sales, schema.Params())
    assert flagged.iloc[-2].is_oneoff
    assert flagged.iloc[-2].oneoff_excess_qty == 490
    assert flagged.iloc[-2].oneoff_reason
    assert not flagged.iloc[-1].is_oneoff
    assert flagged.is_oneoff.sum() == 1
    assert_frame_equal(sales, before)


@pytest.mark.parametrize("months,expected", [([3, 4, 5], False), ([5, 5, 5], True)])
def test_recurrence_counts_distinct_months(regular_sales, months, expected):
    large = sales_table([(f"2025-{month:02d}-20", 500) for month in months])
    flagged = oneoffs.flag_oneoffs(pd.concat([regular_sales, large], ignore_index=True), schema.Params())
    assert flagged.iloc[-3:].is_oneoff.eq(expected).all()


def test_mad_threshold_and_supplier_isolation():
    small = sales_table([("2025-01-01", q) for q in [8, 10, 12] * 10])
    small = pd.concat([small, sales_table([("2025-02-10", 500)])], ignore_index=True)
    other = sales_table([("2025-01-01", 500)] * 30, supplier="SE")
    flagged = oneoffs.flag_oneoffs(pd.concat([small, other], ignore_index=True), schema.Params())
    assert flagged.loc[(flagged.supplier == "IEK") & (flagged.qty == 500), "is_oneoff"].all()
    assert not flagged.loc[flagged.supplier == "SE", "is_oneoff"].any()


def test_large_line_with_small_month_share_is_retained():
    sales = sales_table([("2025-01-01", 10)] * 150 + [("2025-01-20", 500)])
    assert not oneoffs.flag_oneoffs(sales, schema.Params()).is_oneoff.any()


def test_filter_can_be_disabled(regular_sales):
    sales = pd.concat([regular_sales, sales_table([("2025-06-20", 500)])], ignore_index=True)
    flagged = oneoffs.flag_oneoffs(sales, schema.Params(use_oneoff_filter=False))
    assert not flagged.is_oneoff.any()
    assert flagged.oneoff_excess_qty.eq(0).all()
    assert_frame_equal(flagged[list(schema.SALES_LINES)], schema.conform(sales, schema.SALES_LINES))


def test_oneoffs_include_cutoff_day_and_ignore_future_recurrence(regular_sales):
    large = sales_table([("2025-06-20 16:00", 500), ("2025-07-20", 500), ("2025-08-20", 500)])
    flagged = oneoffs.flag_oneoffs(pd.concat([regular_sales, large], ignore_index=True),
                                    schema.Params(as_of=pd.Timestamp("2025-06-20")))
    assert flagged.iloc[-3].is_oneoff
    assert not flagged.iloc[-2:].is_oneoff.any()


@pytest.fixture
def shortage_inputs():
    sales = sales_table([("2025-01-10", 100), ("2025-02-10", 100),
                         ("2025-03-15 16:00", 20), ("2025-04-01", 999)])
    stock = stock_table([("2025-01", 100), ("2025-02", 100), ("2025-03", 0)])
    flagged = oneoffs.flag_oneoffs(sales, schema.Params(use_oneoff_filter=False))
    return flagged, stock


@pytest.mark.parametrize("as_of,fraction", [("2025-03-31", 1), ("2025-03-15", 15 / 31)])
def test_seasonality_and_partial_month(shortage_inputs, as_of, fraction):
    sales, stock = shortage_inputs
    monthly = demand.build_monthly(sales, stock, schema.Params(), pd.Timestamp(as_of),
                                    seasonality=seasonal_table([(1, 1), (2, 1), (3, 2)]))
    last = monthly.iloc[-1]
    assert last.month == "2025-03"
    assert last.qty_raw == 20  # includes the afternoon of as_of; excludes April
    assert last.stockout
    assert last.qty_regular == pytest.approx(200 * fraction)
    assert last.stockout_uplift_qty == pytest.approx(200 * fraction - 20)
    assert monthly.iloc[:2].stockout_uplift_qty.eq(0).all()


def test_correction_and_seasonality_switches(shortage_inputs):
    sales, stock = shortage_inputs
    factors = seasonal_table([(1, 1), (2, 1), (3, 2)])
    params = schema.Params(use_stockout_fix=False)
    off = demand.build_monthly(sales, stock, params, pd.Timestamp("2025-03-31"), seasonality=factors)
    assert off.iloc[-1].qty_regular == 20
    assert off.stockout_uplift_qty.eq(0).all()
    assert off.iloc[-1].stockout
    neutral = demand.build_monthly(sales, stock, schema.Params(use_seasonality=False),
                                   pd.Timestamp("2025-03-31"), seasonality=factors)
    assert neutral.iloc[-1].qty_regular == 100


def test_no_uplift_before_first_activity_or_without_enough_history():
    sales = oneoffs.flag_oneoffs(sales_table([("2025-03-01", 100), ("2025-04-01", 100)]), schema.Params())
    stock = stock_table([("2025-03", 100), ("2025-04", 100)])
    monthly = demand.build_monthly(sales, stock, schema.Params(), pd.Timestamp("2025-05-31"))
    assert monthly.iloc[:2].qty_regular.eq(0).all()
    assert monthly.iloc[-1].qty_regular == 100
    short = demand.build_monthly(sales, stock.iloc[:1], schema.Params(), pd.Timestamp("2025-05-31"))
    assert short.stockout_uplift_qty.eq(0).all()


def test_returns_and_oneoff_exclusion_precede_uplift():
    sales = oneoffs.flag_oneoffs(sales_table([("2025-01-01", 100), ("2025-01-02", -20),
                                             ("2025-02-01", 500), ("2025-03-01", -10)]),
                                  schema.Params(use_oneoff_filter=False))
    sales.loc[sales.qty == 500, "oneoff_excess_qty"] = 420
    stock = stock_table([("2025-01", 100), ("2025-02", 100), ("2025-03", 0)])
    monthly = demand.build_monthly(sales, stock, schema.Params(), pd.Timestamp("2025-03-31"))
    assert monthly.qty_regular.tolist() == [80, 80, 80]
    assert monthly.iloc[-1].qty_raw == -10  # preserve signed invoice facts for audit
    assert monthly.iloc[-1].stockout_uplift_qty == 80


@pytest.mark.parametrize("coef", [0, -1, float("nan"), float("inf")])
def test_invalid_seasonality_is_rejected(shortage_inputs, coef):
    with pytest.raises(ValueError, match="positive finite"):
        demand.build_monthly(*shortage_inputs, schema.Params(), pd.Timestamp("2025-03-31"),
                              seasonality=seasonal_table([(3, coef)]))


def test_empty_inputs_keep_contract():
    flagged = oneoffs.flag_oneoffs(schema.empty(schema.SALES_LINES), schema.Params())
    monthly = demand.build_monthly(flagged, schema.empty(schema.STOCK_MONTHLY),
                                    schema.Params(), pd.Timestamp("2025-03-31"))
    assert_frame_equal(flagged, schema.empty(schema.SALES_FLAGGED))
    assert_frame_equal(monthly, schema.empty(schema.DEMAND_MONTHLY))


@pytest.fixture(scope="module")
def data():
    if not all((CLEAN_DIR / f"{name}.parquet").exists() for name in schema.INPUT_TABLES):
        pytest.skip("data/clean not built")
    return load_clean()


@pytest.fixture(scope="module")
def real_flagged(data):
    return oneoffs.flag_oneoffs(data["sales_lines"], schema.Params())


def test_real_loop_excluded_boxes_retained(real_flagged):
    loop = real_flagged.query("supplier == 'IEK' and sku == '130200305_' and qty == 210000")
    boxes = real_flagged.query("supplier == 'SE' and sku == '030200192_' and qty >= 36000")
    assert not loop.empty and loop.is_oneoff.all()
    assert loop.oneoff_excess_qty.gt(0).all()
    assert not boxes.empty and not boxes.is_oneoff.any()


def test_demand_monthly_contract(data, real_flagged):
    params = schema.Params()
    as_of = data["sales_lines"]["date"].max().normalize()
    monthly = demand.build_monthly(real_flagged, data["stock_monthly"], params, as_of,
                                    seasonality=data["seasonality"])
    assert list(monthly.columns) == list(schema.DEMAND_MONTHLY)
    assert monthly["qty_regular"].ge(0).all()
    assert not monthly.duplicated(["supplier", "sku", "month"]).any()
    off = demand.build_monthly(real_flagged, data["stock_monthly"],
                                replace(params, use_stockout_fix=False), as_of,
                                seasonality=data["seasonality"])
    assert monthly.qty_regular.sum() > off.qty_regular.sum()
    assert monthly.loc[monthly.stockout, "stockout_uplift_qty"].gt(0).all()
