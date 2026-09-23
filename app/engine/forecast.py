"""Demand forecast for the replenishment horizon. Owner: Person 2 «Расчет» (task 2.1)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import schema

BASE_MONTHS = 12


def forecast(demand_monthly: pd.DataFrame, monthly_sales: pd.DataFrame, seasonality: pd.DataFrame,
             products: pd.DataFrame, params: schema.Params, as_of: pd.Timestamp) -> pd.DataFrame:
    """DEMAND_MONTHLY -> FORECAST.

    Working: average daily regular demand over the last full months, category growth.
    STUB: seasonal_index = trend_factor = 1. To implement: SKU seasonality shrunk to the
    company profile, capped trend, respect params.use_seasonality / use_trend.
    """
    current = as_of.strftime("%Y-%m")
    full = demand_monthly[demand_monthly["month"] < current]
    last = full[full["month"] >= sorted(full["month"].unique())[-BASE_MONTHS]]
    days = last.groupby(["supplier", "sku"])["days_in_month_observed"].sum()
    grouped = last.groupby(["supplier", "sku"])["qty_regular"]
    out = pd.DataFrame({
        "avg_daily_regular": grouped.sum() / days,
        "sigma_daily": grouped.std(ddof=0).fillna(0) / np.sqrt(30.4),
    }).reset_index()

    out["seasonal_index"] = 1.0
    out["trend_factor"] = 1.0
    category = out.merge(products[["supplier", "sku", "category"]], on=["supplier", "sku"], how="left")["category"]
    out["growth_factor"] = 1 + category.map(params.growth_pct).fillna(0.0).to_numpy() / 100
    out["horizon_days"] = out["supplier"].map(params.lead_time_days).fillna(30).astype(int) + params.review_period_days
    out["forecast_H"] = (out["avg_daily_regular"] * out["horizon_days"]
                         * out["seasonal_index"] * out["trend_factor"] * out["growth_factor"])
    return schema.conform(out, schema.FORECAST, "forecast")
