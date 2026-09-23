"""Monthly regular demand with stockout compensation. Owner: Person 1 «Спрос» (task 1.2)."""

from __future__ import annotations

import pandas as pd

from app import schema

HISTORY_START = "2025-01"  # invoices before 2025 are sparse


def build_monthly(sales_flagged: pd.DataFrame, stock_monthly: pd.DataFrame,
                  params: schema.Params, as_of: pd.Timestamp) -> pd.DataFrame:
    """SALES_FLAGGED + STOCK_MONTHLY -> DEMAND_MONTHLY.

    Working: month grid, net sales, one-off exclusion from flags, stockout flag.
    STUB: stockout_uplift_qty = 0. To implement: expected demand for stockout months
    (median of available months x seasonality), respect params.use_stockout_fix.
    """
    sales = sales_flagged[(sales_flagged["date"] >= HISTORY_START) & (sales_flagged["date"] <= as_of)]
    sales = sales.assign(month=sales["date"].dt.strftime("%Y-%m"))
    agg = sales.groupby(["supplier", "sku", "month"]).agg(
        qty_raw=("qty", "sum"),
        oneoff_excluded_qty=("oneoff_excess_qty", "sum"),
    )

    months = pd.period_range(HISTORY_START, as_of, freq="M").strftime("%Y-%m")
    skus = sales[["supplier", "sku"]].drop_duplicates()
    grid = skus.merge(pd.DataFrame({"month": months}), how="cross")
    out = grid.merge(agg.reset_index(), on=["supplier", "sku", "month"], how="left").fillna(
        {"qty_raw": 0.0, "oneoff_excluded_qty": 0.0})

    stock = stock_monthly.set_index(["supplier", "sku", "month"])["qty_start"]
    key = pd.MultiIndex.from_frame(out[["supplier", "sku", "month"]])
    out["stockout"] = stock.reindex(key).fillna(0).le(0).to_numpy()
    out["stockout_uplift_qty"] = 0.0
    out["qty_regular"] = (out["qty_raw"] - out["oneoff_excluded_qty"] + out["stockout_uplift_qty"]).clip(lower=0)

    period = pd.PeriodIndex(out["month"], freq="M")
    out["days_in_month_observed"] = period.days_in_month
    current = out["month"] == as_of.strftime("%Y-%m")
    out.loc[current, "days_in_month_observed"] = as_of.day
    return schema.conform(out, schema.DEMAND_MONTHLY, "demand_monthly")
