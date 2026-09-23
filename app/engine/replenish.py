"""Order quantity, pack rounding and urgency. Owner: Person 2 «Расчет» (task 2.2)."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from app import schema


def calc(fc: pd.DataFrame, demand_monthly: pd.DataFrame, stock_now: pd.DataFrame,
         in_transit: pd.DataFrame, products: pd.DataFrame, params: schema.Params,
         as_of: pd.Timestamp) -> pd.DataFrame:
    """FORECAST + stock + transit -> ORDER_LINES (rationale filled later by explain)."""
    keys = ["supplier", "sku"]
    out = fc[fc["avg_daily_regular"] > 0].merge(
        products[keys + ["name", "category", "unit", "pack_multiple"]], on=keys, how="left")

    stock = stock_now.set_index(keys)["free_qty"]
    idx = pd.MultiIndex.from_frame(out[keys])
    out["free_qty"] = stock.reindex(idx).to_numpy()
    flags = np.where(out["free_qty"].isna(), "needs_review:no_stock", "")
    out["free_qty"] = out["free_qty"].fillna(0.0)

    horizon_end = as_of + pd.to_timedelta(out["horizon_days"], unit="D")
    transit = in_transit.merge(out[keys].assign(horizon_end=horizon_end), on=keys)
    transit = transit[transit["eta"] <= transit["horizon_end"]] if params.use_in_transit else transit.iloc[0:0]
    out["in_transit_H"] = transit.groupby(keys)["qty"].sum().reindex(idx).fillna(0.0).to_numpy()

    lead = out["supplier"].map(params.lead_time_days).fillna(30)
    z = NormalDist().inv_cdf(params.service_level)
    out["safety_stock"] = z * out["sigma_daily"] * np.sqrt(lead)

    q_raw = (out["forecast_H"] + out["safety_stock"] - out["free_qty"] - out["in_transit_H"]).clip(lower=0)
    pack = out["pack_multiple"].fillna(1.0)
    out["recommended_qty"] = np.where(q_raw > 0, np.ceil(q_raw / pack) * pack, 0.0)
    out["final_qty"] = out["recommended_qty"]
    out["override_reason"] = ""

    out["days_of_cover"] = (out["free_qty"] + out["in_transit_H"]) / out["avg_daily_regular"]
    out["urgency"] = np.select([out["days_of_cover"] < lead, out["days_of_cover"] < out["horizon_days"]],
                               ["critical", "high"], "normal")

    per_sku = demand_monthly.groupby(keys).agg(
        oneoff_excluded_qty=("oneoff_excluded_qty", "sum"),
        stockout_months=("stockout", "sum"),
        stockout_uplift_qty=("stockout_uplift_qty", "sum"),
    )
    for col in per_sku.columns:
        out[col] = per_sku[col].reindex(idx).fillna(0).to_numpy()

    out["rationale"] = ""
    out["flags"] = flags
    out["status"] = "draft"
    return schema.conform(out, schema.ORDER_LINES, "order_lines")
