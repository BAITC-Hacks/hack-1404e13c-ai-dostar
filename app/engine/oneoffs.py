"""One-off large order detection. Owner: Person 1 «Спрос» (docs/tasks.md 1.1, 1.4)."""

from __future__ import annotations

import pandas as pd

from app import schema


def flag_oneoffs(sales_lines: pd.DataFrame, params: schema.Params) -> pd.DataFrame:
    """sales_lines -> SALES_FLAGGED.

    STUB: flags nothing. To implement (task 1.1): robust median/MAD threshold per SKU,
    share of the SKU's month, and irregularity (large lines seen in fewer than
    params.oneoff_min_months months). Respect params.use_oneoff_filter.
    """
    out = sales_lines.copy()
    out["is_oneoff"] = False
    out["oneoff_excess_qty"] = 0.0
    out["oneoff_reason"] = ""
    return schema.conform(out, schema.SALES_FLAGGED, "sales_flagged")


def report(sales_flagged: pd.DataFrame) -> pd.DataFrame:
    """Excluded one-off lines for the UI, largest first (task 1.4)."""
    cols = ["supplier", "sku", "date", "doc_id", "qty", "oneoff_excess_qty", "oneoff_reason"]
    return sales_flagged.loc[sales_flagged["is_oneoff"], cols].sort_values("qty", ascending=False)
