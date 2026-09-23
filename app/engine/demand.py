"""Monthly regular demand with stockout compensation. Owner: Person 1 «Спрос» (task 1.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import schema

HISTORY_START = "2025-01"  # invoices before 2025 are sparse


def build_monthly(sales_flagged: pd.DataFrame, stock_monthly: pd.DataFrame,
                  params: schema.Params, as_of: pd.Timestamp, *,
                  seasonality: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build regular demand; estimate shortages from at least two stocked months.

    Optional company coefficients use the SEASONALITY contract. Missing factors
    default to 1; no external files are read. Partial months are prorated.
    """
    as_of = pd.Timestamp(as_of).normalize()
    if pd.isna(as_of):
        raise ValueError("as_of must be a valid date")
    sales = sales_flagged[(sales_flagged["date"] >= HISTORY_START)
                          & (sales_flagged["date"] < as_of + pd.Timedelta(days=1))]
    if sales.empty:
        return schema.empty(schema.DEMAND_MONTHLY)
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
    out["qty_start"] = stock.reindex(key).fillna(0).to_numpy()
    out["qty_regular"] = (out["qty_raw"] - out["oneoff_excluded_qty"]).clip(lower=0)

    period = pd.PeriodIndex(out["month"], freq="M")
    out["days_in_month_observed"] = period.days_in_month
    current = out["month"] == as_of.strftime("%Y-%m")
    out.loc[current, "days_in_month_observed"] = as_of.day

    out["coef"] = 1.0
    if params.use_seasonality and seasonality is not None and not seasonality.empty:
        factors = schema.conform(seasonality, schema.SEASONALITY, "seasonality")
        if (factors.duplicated(["supplier", "month_num"]).any()
                or not factors["month_num"].between(1, 12).all()
                or not (np.isfinite(factors["coef"]) & factors["coef"].gt(0)).all()):
            raise ValueError("seasonality requires unique supplier/month keys and positive finite coefficients")
        lookup = factors.set_index(["supplier", "month_num"])["coef"]
        month_keys = pd.MultiIndex.from_arrays([out["supplier"], period.month])
        out["coef"] = lookup.reindex(month_keys).fillna(1.0).to_numpy()

    # Only complete, stocked months provide evidence of unconstrained demand.
    complete = out["days_in_month_observed"].eq(period.days_in_month)
    available = out.loc[out["qty_start"].gt(0) & complete]
    baselines = available.groupby(["supplier", "sku"]).agg(
        typical_qty=("qty_regular", "median"),
        mean_coef=("coef", "mean"),
        available_months=("month", "size"),
    )
    out = out.join(baselines, on=["supplier", "sku"])
    expected = (out["typical_qty"] * out["coef"] / out["mean_coef"]
                * out["days_in_month_observed"] / period.days_in_month).fillna(0.0)

    # Do not invent shortages before the first evidence of this product's activity.
    first_seen = out.loc[out["qty_start"].gt(0) | out["qty_raw"].gt(0)].groupby(
        ["supplier", "sku"])["month"].min().rename("first_seen")
    out = out.join(first_seen, on=["supplier", "sku"])
    out["stockout"] = (out["qty_start"].le(0) & out["available_months"].ge(2)
                       & out["month"].ge(out["first_seen"])
                       & out["qty_regular"].lt(expected))
    out["stockout_uplift_qty"] = 0.0
    if params.use_stockout_fix:
        out.loc[out["stockout"], "stockout_uplift_qty"] = (
            expected - out["qty_regular"])[out["stockout"]]
    out["qty_regular"] += out["stockout_uplift_qty"]
    return schema.conform(out, schema.DEMAND_MONTHLY, "demand_monthly")
