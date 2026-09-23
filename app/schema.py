"""Shared data contract between adapters, engine and UI.

Change a table here only after agreeing with the team: every module reads
and writes these exact column names. Semantics are described in
docs/architecture.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Supplier ids used in every table's `supplier` column.
SUPPLIERS = {
    "IEK": "IEK",
    "SE": "Systeme Electric",
}

# ---------------------------------------------------------------- inputs

# One invoice line. qty > 0 is a sale, qty < 0 a return. Only "Расходная накладная".
SALES_LINES = {
    "supplier": "string",
    "sku": "string",
    "date": "datetime64[ns]",
    "doc_id": "string",
    "qty": "float64",
    "unit": "string",
    "warehouse": "string",
}

# Net sold quantity per calendar month (sales minus returns), from the monthly report.
MONTHLY_SALES = {
    "supplier": "string",
    "sku": "string",
    "month": "string",  # YYYY-MM
    "qty": "float64",
}

# Stock at the start of each month. Missing cells in the source are 0.
STOCK_MONTHLY = {
    "supplier": "string",
    "sku": "string",
    "month": "string",  # YYYY-MM
    "qty_start": "float64",
}

# Current stock. free_qty = available for new orders (on hand minus reserve).
# source: "manager_file" (exact) or "estimated" (start-of-month stock minus
# sales since then; receipts in the month are unknown).
STOCK_NOW = {
    "supplier": "string",
    "sku": "string",
    "free_qty": "float64",
    "reserved_qty": "float64",
    "as_of": "datetime64[ns]",
    "source": "string",
}

# Open supplier orders. eta is the latest promised arrival date.
IN_TRANSIT = {
    "supplier": "string",
    "sku": "string",
    "qty": "float64",
    "eta": "datetime64[ns]",
    "order_ref": "string",
}

# Product directory. pack_multiple >= 1 (MOQ / shipment multiple from the supplier file).
PRODUCTS = {
    "supplier": "string",
    "sku": "string",
    "name": "string",
    "unit": "string",
    "category": "string",
    "supplier_article": "string",
    "pack_multiple": "float64",
}

# Company-level monthly seasonality coefficients (1.0 = average month).
SEASONALITY = {
    "supplier": "string",
    "month_num": "int64",  # 1..12
    "coef": "float64",
}

# The purchasing manager's current Excel calculation (SE only) for comparison.
MANAGER_BASELINE = {
    "supplier": "string",
    "sku": "string",
    "category_abc": "string",
    "avg_month_12": "float64",
    "growth_coef": "float64",
    "season_coef": "float64",
    "on_hand": "float64",
    "reserved_qty": "float64",
    "free_qty": "float64",
    "stock_months": "float64",
    "manager_order": "float64",
    "in_transit": "float64",
    "unit_cost": "float64",
}

INPUT_TABLES = {
    "sales_lines": SALES_LINES,
    "monthly_sales": MONTHLY_SALES,
    "stock_monthly": STOCK_MONTHLY,
    "stock_now": STOCK_NOW,
    "in_transit": IN_TRANSIT,
    "products": PRODUCTS,
    "seasonality": SEASONALITY,
    "manager_baseline": MANAGER_BASELINE,
}

# ---------------------------------------------------------------- engine intermediates

# sales_lines + one-off decision per invoice line (engine/oneoffs.py).
SALES_FLAGGED = {
    **SALES_LINES,
    "is_oneoff": "bool",
    "oneoff_excess_qty": "float64",  # part of qty removed from regular demand
    "oneoff_reason": "string",
}

# Regular monthly demand per SKU (engine/demand.py). Full month grid from 2025-01
# to the as_of month for every SKU with sales; months without sales are 0.
DEMAND_MONTHLY = {
    "supplier": "string",
    "sku": "string",
    "month": "string",  # YYYY-MM
    "qty_raw": "float64",  # net sales from invoices
    "oneoff_excluded_qty": "float64",
    "stockout": "bool",  # start-of-month stock <= 0
    "stockout_uplift_qty": "float64",  # estimated lost demand
    "qty_regular": "float64",  # qty_raw - oneoff_excluded_qty + stockout_uplift_qty, >= 0
    "days_in_month_observed": "int64",  # < days in month only for the current month
}

# Demand forecast for the replenishment horizon (engine/forecast.py).
FORECAST = {
    "supplier": "string",
    "sku": "string",
    "avg_daily_regular": "float64",
    "sigma_daily": "float64",
    "seasonal_index": "float64",
    "trend_factor": "float64",
    "growth_factor": "float64",
    "horizon_days": "int64",
    "forecast_H": "float64",
}

# Assortment lifecycle signals (engine/lifecycle.py). Advisory: quantities are not changed.
LIFECYCLE = {
    "supplier": "string",
    "sku": "string",
    "name": "string",
    "signal": "string",  # declining | new_item | replaced_by | replaces
    "related_sku": "string",  # the other model of a replacement pair
    "related_name": "string",
    "similarity": "float64",  # name similarity of the pair, 0..1
    "avg_last3": "float64",  # regular demand per month, last 3 full months
    "avg_prev9": "float64",  # regular demand per month, 9 months before
    "first_month": "string",  # first month with sales, YYYY-MM
    "note": "string",
}

# ---------------------------------------------------------------- output

ORDER_LINES = {
    "supplier": "string",
    "sku": "string",
    "name": "string",
    "category": "string",
    "unit": "string",
    "avg_daily_regular": "float64",  # regular demand after one-off and stockout corrections
    "seasonal_index": "float64",
    "trend_factor": "float64",
    "growth_factor": "float64",
    "horizon_days": "int64",  # lead_time + review_period
    "forecast_H": "float64",
    "safety_stock": "float64",
    "free_qty": "float64",
    "in_transit_H": "float64",  # only deliveries with eta within the horizon
    "oneoff_excluded_qty": "float64",
    "stockout_months": "int64",
    "stockout_uplift_qty": "float64",
    "recommended_qty": "float64",  # immutable model output
    "final_qty": "float64",  # edited by the manager
    "override_reason": "string",
    "days_of_cover": "float64",
    "urgency": "string",  # critical | high | normal
    "rationale": "string",
    "flags": "string",  # comma-separated, e.g. needs_review
    "status": "string",  # draft | approved | exported
}

URGENCY_LEVELS = ("critical", "high", "normal")
ORDER_STATUSES = ("draft", "approved", "exported")


@dataclass
class Params:
    lead_time_days: dict[str, int] = field(default_factory=lambda: {"IEK": 30, "SE": 30})
    review_period_days: int = 7
    service_level: float = 0.95
    growth_pct: dict[str, float] = field(default_factory=dict)  # category -> % on top of trend
    oneoff_k: float = 5.0  # MAD multiplier for a large invoice line
    oneoff_min_months: int = 3  # large lines seen in fewer months are one-off
    as_of: pd.Timestamp | None = None  # calculation date; default = last sale date
    use_oneoff_filter: bool = True
    use_stockout_fix: bool = True
    use_seasonality: bool = True
    use_trend: bool = True
    use_in_transit: bool = True
    forecast_method: str = "statistical"  # statistical | ml; ML is trained separately


@dataclass
class PipelineResult:
    order_lines: pd.DataFrame  # ORDER_LINES
    forecast: pd.DataFrame  # FORECAST
    demand_monthly: pd.DataFrame  # DEMAND_MONTHLY
    sales_flagged: pd.DataFrame  # SALES_FLAGGED
    params: Params
    as_of: pd.Timestamp
    forecast_details: dict | None = None  # ML provenance, validation and monthly curve
    lifecycle: pd.DataFrame | None = None  # LIFECYCLE signals, advisory


def empty(table: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame({col: pd.Series(dtype=dtype) for col, dtype in table.items()})


def conform(df: pd.DataFrame, table: dict[str, str], name: str = "") -> pd.DataFrame:
    """Check required columns, cast dtypes, drop extras, keep contract column order."""
    missing = [col for col in table if col not in df.columns]
    if missing:
        raise ValueError(f"{name or 'table'}: missing columns {missing}")
    out = df[list(table)].copy()
    for col, dtype in table.items():
        if dtype.startswith("datetime"):
            out[col] = pd.to_datetime(out[col])
        else:
            out[col] = out[col].astype(dtype)
    return out.reset_index(drop=True)
