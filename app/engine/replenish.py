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
    # Only SKUs with a positive regular demand base get an order line; a SKU without
    # sales in the base window has nothing to replenish and stays visible in history only.
    out = fc[fc["avg_daily_regular"] > 0].merge(
        products[keys + ["name", "category", "unit", "pack_multiple"]], on=keys, how="left")
    idx = pd.MultiIndex.from_frame(out[keys])
    issues = [[] for _ in range(len(out))]

    def flag(mask, code: str) -> None:
        for i in np.flatnonzero(np.asarray(mask)):
            issues[i].append(f"needs_review:{code}")

    # Stock: missing -> 0; negative or non-numeric -> 0 and flagged (never invent stock).
    stock = stock_now.set_index(keys)["free_qty"]
    known = idx.isin(stock.index)
    free = pd.to_numeric(stock, errors="coerce").reindex(idx).to_numpy(dtype=float)
    flag(~known, "no_stock")
    flag(known & ~(np.isfinite(free) & (free >= 0)), "bad_stock")
    out["free_qty"] = np.where(np.isfinite(free) & (free > 0), free, 0.0)
    # The IEK adapter estimates stock from month-start stock minus sales;
    # receipts are not available. Surface the uncertainty without inventing stock.
    flag(out["supplier"].eq("IEK"), "estimated_stock")

    # In transit: only valid positive quantities with a known ETA inside the horizon count.
    horizon_end = as_of + pd.to_timedelta(out["horizon_days"], unit="D")
    transit = in_transit.merge(out[keys].assign(horizon_end=horizon_end), on=keys)
    transit_qty = pd.to_numeric(transit["qty"], errors="coerce")
    valid = transit_qty.gt(0) & np.isfinite(transit_qty) & transit["eta"].notna()
    bad = transit.loc[~valid, keys].drop_duplicates()
    flag(idx.isin(pd.MultiIndex.from_frame(bad)), "bad_transit")
    transit = transit[valid].assign(qty=transit_qty[valid])
    transit = transit[transit["eta"] <= transit["horizon_end"]] if params.use_in_transit else transit.iloc[0:0]
    out["in_transit_H"] = transit.groupby(keys)["qty"].sum().reindex(idx).fillna(0.0).to_numpy()

    # Pack multiple: missing, zero, negative or non-finite -> 1 and flagged.
    pack = pd.to_numeric(out["pack_multiple"], errors="coerce")
    bad_pack = ~(np.isfinite(pack) & pack.gt(0))
    flag(bad_pack & out["pack_multiple"].notna(), "bad_pack")
    pack = pack.where(~bad_pack, 1.0)
    flags = np.array([",".join(i) for i in issues], dtype=object)

    lead = out["supplier"].map(params.lead_time_days).fillna(30)
    z = NormalDist().inv_cdf(params.service_level)
    out["safety_stock"] = z * out["sigma_daily"] * np.sqrt(lead)

    q_raw = (out["forecast_H"] + out["safety_stock"] - out["free_qty"] - out["in_transit_H"]).clip(lower=0)
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
