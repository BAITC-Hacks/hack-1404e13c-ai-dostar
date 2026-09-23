"""One-off large order detection. Owner: Person 1 «Спрос» (docs/tasks.md 1.1, 1.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import schema


def flag_oneoffs(sales_lines: pd.DataFrame, params: schema.Params) -> pd.DataFrame:
    """Flag unusually large, nonrecurring invoice lines without changing sales."""
    out = sales_lines.copy().reset_index(drop=True)
    out["is_oneoff"] = False
    out["oneoff_excess_qty"] = 0.0
    out["oneoff_reason"] = ""
    if not params.use_oneoff_filter or out.empty:
        return schema.conform(out, schema.SALES_FLAGGED, "sales_flagged")

    eligible = out["qty"].gt(0)
    if params.as_of is not None:
        cutoff = pd.Timestamp(params.as_of).normalize() + pd.Timedelta(days=1)
        eligible &= out["date"].lt(cutoff)
    sales = out.loc[eligible, ["supplier", "sku", "date", "qty"]].copy()
    if sales.empty:
        return schema.conform(out, schema.SALES_FLAGGED, "sales_flagged")

    keys = [sales["supplier"], sales["sku"]]
    typical = sales.groupby(["supplier", "sku"])["qty"].transform("median")
    mad = (sales["qty"] - typical).abs().groupby(keys).transform("median")
    threshold = pd.Series(np.where(mad.gt(0), typical + params.oneoff_k * 1.4826 * mad,
                                   10 * typical), index=sales.index)

    # A SKU sold only once has no SKU-level baseline. Use its category only when
    # there are enough peer lines to make an extreme-volume comparison credible.
    one_line = sales.groupby(["supplier", "sku"])["qty"].transform("size").eq(1)
    if one_line.any():
        sales["category"] = sales["sku"].str.extract(r"^(\d{4})", expand=False)
        category_stats = sales.groupby(["supplier", "category"])["qty"].agg(
            peer_lines="size",
            typical=lambda qty: qty.quantile(0.90),
            extreme=lambda qty: qty.quantile(0.99),
        )
        sales = sales.join(category_stats, on=["supplier", "category"])
        category_fallback = one_line & sales["peer_lines"].ge(100)
        typical.loc[category_fallback] = sales.loc[category_fallback, "typical"]
        threshold.loc[category_fallback] = 10 * sales.loc[category_fallback, "extreme"]
    else:
        category_fallback = pd.Series(False, index=sales.index)

    sales["month"] = sales["date"].dt.strftime("%Y-%m")
    month_total = sales.groupby(["supplier", "sku", "month"])["qty"].transform("sum")
    share = sales["qty"] / month_total
    candidates = sales.loc[sales["qty"].gt(threshold) & share.gt(0.30)].copy()
    if candidates.empty:
        return schema.conform(out, schema.SALES_FLAGGED, "sales_flagged")

    # One maximum per month is enough to count months containing a comparable line.
    monthly_max = sales.groupby(["supplier", "sku", "month"], sort=False)["qty"].max()
    maxima_by_sku = {
        key: np.sort(group.to_numpy())
        for key, group in monthly_max.groupby(level=[0, 1], sort=False)
    }
    for idx, row in candidates.iterrows():
        maxima = maxima_by_sku[(row["supplier"], row["sku"])]
        comparable_months = len(maxima) - np.searchsorted(maxima, row["qty"] * 0.5,
                                                            side="left")
        if comparable_months >= params.oneoff_min_months:
            continue
        median = float(typical.loc[idx])
        out.at[idx, "is_oneoff"] = True
        out.at[idx, "oneoff_excess_qty"] = float(row["qty"] - median)
        source = "по категории" if category_fallback.loc[idx] else "по товару"
        out.at[idx, "oneoff_reason"] = (
            f"Разовая строка {row['qty']:g}; типичная {median:g} {source}, "
            f"доля месяца {share.loc[idx]:.0%}, сопоставимый объём "
            f"в {comparable_months} мес."
        )
    return schema.conform(out, schema.SALES_FLAGGED, "sales_flagged")


def report(sales_flagged: pd.DataFrame) -> pd.DataFrame:
    """Excluded one-off lines for the UI, largest first (task 1.4)."""
    cols = ["supplier", "sku", "date", "doc_id", "qty", "oneoff_excess_qty", "oneoff_reason"]
    return sales_flagged.loc[sales_flagged["is_oneoff"], cols].sort_values("qty", ascending=False)
